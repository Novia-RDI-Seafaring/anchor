"""`anchor serve` preserves its port unless walking is explicitly enabled."""
from __future__ import annotations

import importlib
import socket
import sys
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from anchor.adapters.cli.serve import _find_free_port

serve_module = importlib.import_module("anchor.adapters.cli.serve")


def test_returns_a_bindable_port():
    # Grab an OS-assigned free port, release it, and confirm we can get one.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        start = s.getsockname()[1]
    chosen = _find_free_port("127.0.0.1", start)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", chosen))  # bindable -> no error


def test_skips_a_port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        busy = taken.getsockname()[1]
        chosen = _find_free_port("127.0.0.1", busy)
        assert chosen > busy  # didn't pick the in-use port


def test_single_port_probe_reports_the_bind_failure():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        busy = taken.getsockname()[1]

        with pytest.raises(OSError) as failure:
            _find_free_port("127.0.0.1", busy, limit=1)

        assert failure.value.errno is not None
        assert "no free port" not in str(failure.value)


@pytest.mark.skipif(sys.platform == "win32", reason="TIME_WAIT reuse follows POSIX semantics")
def test_reuses_port_after_a_closed_connection():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.settimeout(2)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen()
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(2)
                connection.shutdown(socket.SHUT_WR)
                assert client.recv(1) == b""
                client.shutdown(socket.SHUT_WR)
                assert connection.recv(1) == b""

    assert _find_free_port("127.0.0.1", port, limit=1) == port


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_probe_uses_safe_platform_socket_options(monkeypatch, platform):
    calls = []

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def setsockopt(self, *args):
            calls.append(("option", args))

        def bind(self, address):
            calls.append(("bind", address))

        def listen(self):
            calls.append(("listen",))

    monkeypatch.setattr(serve_module, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(socket, "SO_EXCLUSIVEADDRUSE", -5, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *_: Probe())

    assert _find_free_port("127.0.0.1", 8031, limit=1) == 8031
    option = socket.SO_EXCLUSIVEADDRUSE if platform == "win32" else socket.SO_REUSEADDR
    assert calls == [
        ("option", (socket.SOL_SOCKET, option, 1)),
        ("bind", ("127.0.0.1", 8031)),
        ("listen",),
    ]


@pytest.fixture
def serve_cli(monkeypatch, tmp_path):
    import uvicorn

    from anchor.adapters.http import app as http_module
    from anchor.infra import serve_registry

    calls = {}
    app_ = SimpleNamespace(state=SimpleNamespace())

    def build_runtime(data_dir, **kwargs):
        calls["base_url"] = kwargs["base_url"]
        return SimpleNamespace(config=SimpleNamespace(data_dir=data_dir))

    def run(app, **kwargs):
        calls["run"] = kwargs
        calls["binding"] = app.state.serve_binding

    monkeypatch.setattr(serve_module, "build_project_runtime_for_data_dir", build_runtime)
    monkeypatch.setattr(serve_module, "_migrate_bbox_origin", lambda _: None)
    monkeypatch.setattr(http_module, "build_app", lambda *_args, **_kwargs: app_)
    monkeypatch.setattr(serve_registry, "identify_data_dir", lambda _: ("study", "pumps"))
    monkeypatch.setattr(serve_registry, "register_serve", lambda **_: tmp_path / "serve.json")
    monkeypatch.setattr(serve_registry, "unregister_serve", lambda _: None)
    monkeypatch.setattr(uvicorn, "run", run)
    app = typer.Typer()
    app.command()(serve_module.serve)
    return app, calls


@pytest.mark.parametrize("port_args", [[], ["--port", "8031"]])
def test_cli_fails_on_unavailable_port_by_default(serve_cli, monkeypatch, tmp_path, port_args):
    app, calls = serve_cli
    probes = []

    def unavailable(host, port, *, limit):
        probes.append((host, port, limit))
        raise OSError("address already in use")

    monkeypatch.setattr(serve_module, "_find_free_port", unavailable)
    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path), *port_args])

    port = 8031 if port_args else 8002
    assert result.exit_code == 1
    assert probes == [("127.0.0.1", port, 1)]
    assert f"cannot bind 127.0.0.1:{port}: address already in use" in result.output
    assert "--port-walk" in result.output
    assert calls == {}


def test_cli_port_walk_reports_and_uses_the_selected_port(serve_cli, monkeypatch, tmp_path):
    app, calls = serve_cli
    probes = []

    def next_port(host, port, *, limit):
        probes.append((host, port, limit))
        return port + 1

    monkeypatch.setattr(serve_module, "_find_free_port", next_port)
    result = CliRunner().invoke(
        app, ["--data-dir", str(tmp_path), "--port", "8031", "--port-walk"]
    )

    assert result.exit_code == 0, result.output
    assert probes == [("127.0.0.1", 8031, 20)]
    assert "Warning: port 8031 is unavailable -- serving on 8032 instead" in result.stderr
    assert "http://127.0.0.1:8032" in result.stdout
    assert calls["base_url"] == "http://localhost:8032"
    assert calls["run"] == {"host": "127.0.0.1", "port": 8032}
    assert calls["binding"]["port"] == 8032


def test_direct_serve_call_does_not_enable_port_walk(serve_cli, monkeypatch, tmp_path):
    _, calls = serve_cli
    probes = []

    def same_port(host, port, *, limit):
        probes.append((host, port, limit))
        return port

    monkeypatch.setattr(serve_module, "_find_free_port", same_port)
    serve_module.serve(data_dir=tmp_path, host="127.0.0.1", port=8031)

    assert probes == [("127.0.0.1", 8031, 1)]
    assert calls["run"]["port"] == 8031
