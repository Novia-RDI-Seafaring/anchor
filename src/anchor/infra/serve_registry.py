"""Runtime registry of running ``anchor serve`` processes.

A multi-project setup can have several servers up at once, each bound to a
different project on a different port. Nothing on disk used to tie a port to a
project, so an agent could not tell which serve hosts its canvas and a printed
``http://...:8002/c/<slug>`` URL was a guess (anchor#177, anchor#179).

Each ``anchor serve`` writes a small JSON record here when it binds and removes
it on shutdown. The record carries the bound env + project, the data dir, and
the *actual* host:port (after the free-port bump). Discovery then resolves a
URL against a server that really serves a given data dir instead of guessing
the default port.

The records live under ``<ANCHOR_HOME>/serves/<pid>.json`` so they are scoped
to the same trust boundary as the environments. A record whose PID is no longer
alive is stale (a crash skipped cleanup); readers prune those so a stale entry
never masquerades as a live serve.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from anchor.infra.environment import anchor_home, identify_data_dir

#: Runtime records live here, one JSON file per running serve.
SERVES_DIRNAME = "serves"


def serves_dir() -> Path:
    return anchor_home() / SERVES_DIRNAME


@dataclass(frozen=True)
class ServeRecord:
    """One running ``anchor serve`` and the project it is bound to."""

    pid: int
    host: str
    port: int
    data_dir: str
    env: str | None
    project: str | None
    started_at: str

    @property
    def url_host(self) -> str:
        """Host to put in a browser URL.

        A server bound to ``0.0.0.0`` / ``::`` listens on all interfaces but is
        reached over loopback from the same machine; rewrite to ``127.0.0.1``
        so the printed URL actually resolves.
        """
        return "127.0.0.1" if self.host in ("0.0.0.0", "::", "") else self.host

    def base_url(self) -> str:
        return f"http://{self.url_host}:{self.port}"

    def to_dict(self) -> dict:
        return asdict(self)


def _pid_alive(pid: int) -> bool:
    """True if a process with ``pid`` exists. Signal 0 only checks existence."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but owned by another user — still a live process.
        return True
    except OSError:
        return False
    return True


def register_serve(
    *, host: str, port: int, data_dir: Path | str, started_at: str
) -> Path:
    """Write this process's serve record and return its path.

    Resolves the bound env + project from the data dir so the record is
    self-describing. Best-effort: a failure to write must never stop the
    server from coming up, so the caller treats this as advisory.
    """
    env_name, project_name = identify_data_dir(data_dir)
    record = ServeRecord(
        pid=os.getpid(),
        host=host,
        port=port,
        data_dir=str(Path(data_dir)),
        env=env_name,
        project=project_name,
        started_at=started_at,
    )
    target = serves_dir() / f"{record.pid}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
    return target


def unregister_serve(path: Path | None = None) -> None:
    """Remove this process's serve record (best-effort)."""
    target = path if path is not None else serves_dir() / f"{os.getpid()}.json"
    try:
        target.unlink()
    except OSError:
        pass


def _load_record(path: Path) -> ServeRecord | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return ServeRecord(
            pid=int(data["pid"]),
            host=str(data.get("host", "127.0.0.1")),
            port=int(data["port"]),
            data_dir=str(data.get("data_dir", "")),
            env=data.get("env"),
            project=data.get("project"),
            started_at=str(data.get("started_at", "")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def list_serves(*, prune_stale: bool = True) -> list[ServeRecord]:
    """All live serve records. Stale (dead-PID) records are pruned by default."""
    root = serves_dir()
    if not root.is_dir():
        return []
    out: list[ServeRecord] = []
    for path in sorted(root.glob("*.json")):
        record = _load_record(path)
        if record is None or not _pid_alive(record.pid):
            if prune_stale:
                try:
                    path.unlink()
                except OSError:
                    pass
            continue
        out.append(record)
    return out


def find_serve_for_data_dir(data_dir: Path | str) -> ServeRecord | None:
    """The running serve bound to ``data_dir``, or ``None`` if none is up.

    Compares resolved absolute paths so ``~`` / relative spellings of the same
    project match. When several serves share a data dir (unusual), the
    lowest-port one wins so the answer is stable.
    """
    want = Path(os.path.expandvars(str(data_dir))).expanduser().resolve()
    matches = [
        record
        for record in list_serves()
        if Path(record.data_dir).expanduser().resolve() == want
    ]
    if not matches:
        return None
    return min(matches, key=lambda r: r.port)
