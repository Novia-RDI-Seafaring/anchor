"""``anchor check`` — verify the data zone and configuration before ingesting.

Onboarding's hardest question for a sensitive-document user is "will my files
actually stay where I think?" ``check`` answers it: it resolves the active
project config, prints the data zone (provider, endpoint, data dir, models,
whether the key is present), validates the endpoint shape, and — only with
``--probe`` — makes one tiny call to confirm the deployment resolves and the key
authenticates, sending no document content. It exits non-zero when something
would break a real ingest, so an agent or script can gate on it.
"""
from __future__ import annotations

import os

import typer

from anchor.infra.config import AnchorConfig
from anchor.infra.providers import get_provider, normalize_base_url

# Providers that authenticate against an endpoint (mirror of init's set).
_KEYED_PROVIDERS = ("openai", "azure", "custom")


def _rewrite_base_url(config_path, old: str, new: str) -> bool:
    """Replace the openai_base_url value in the toml in place. True on success."""
    text = config_path.read_text(encoding="utf-8")
    needle = f'openai_base_url = "{old}"'
    if needle not in text:
        return False
    config_path.write_text(text.replace(needle, f'openai_base_url = "{new}"'), encoding="utf-8")
    return True


def check(
    probe: bool = typer.Option(
        False, "--probe", help="Make one tiny live call to confirm the deployment + key work."
    ),
    fix: bool = typer.Option(
        False, "--fix", help="Apply any safe endpoint repair without prompting."
    ),
    env: str = typer.Option(
        None, "--env", help="Environment NAME to check (default: the default env)."
    ),
) -> None:
    """Verify the resolved data zone + config for this environment."""
    from anchor.infra.environment import (
        DEFAULT_PROJECT,
        LEGACY_DATA_DIR,
        resolve_environment,
        resolve_project_config,
    )

    env = resolve_environment(env)
    cfg = resolve_project_config(env, DEFAULT_PROJECT)
    default_dir = env.project_dir(DEFAULT_PROJECT)
    config_path = env.config_path  # the env.toml, target of endpoint repair
    prov = get_provider(cfg.provider) if cfg.provider else None

    typer.echo("Data zone")
    typer.echo(f"  environment    : {env.name}")
    # The "environment" is a named provider/data-zone/trust profile, not a .env
    # dotfile of secrets. The config below is env.toml; an API key (if any) lives
    # in ANCHOR_OPENAI_API_KEY, never in env.toml.
    if env.initialized:
        typer.echo(f"  config         : {env.config_path}  (env.toml; not a .env dotfile)")
    else:
        typer.echo("  config         : (env not set up yet — defaults; `anchor env create`)")
    if prov:
        typer.echo(f"  provider       : {prov.label} — {prov.zone}")
    elif cfg.provider:
        typer.echo(f"  provider       : {cfg.provider}")
    # Be honest when the project dir is not on disk yet: a fresh project has
    # none until first ingest, but a bare path here reads as "all set" and has
    # masked a misconfigured zone before. Say so rather than imply it exists.
    data_dir_note = (
        "" if default_dir.exists() else "  (created on first ingest)"
    )
    typer.echo(f"  default project: {default_dir}{data_dir_note}")
    embed_remote = cfg.embed_model.startswith("text-embedding-")
    typer.echo(
        f"  embed model    : {cfg.embed_model}  "
        f"({'remote — sent to your endpoint' if embed_remote else 'local, no egress'})"
    )
    # Local-only / no-egress posture: a single asserted line. When active, no
    # OpenAI client is built for any stage and model loading is pinned offline.
    if cfg.local_only:
        from anchor.infra.models import offline_active, required_models

        typer.echo("  local-only     : ON — no external egress; polish + regions disabled")
        cached = "offline env set ✓" if offline_active() else (
            "run `anchor models prefetch` once, then set HF_HUB_OFFLINE=1 to verify"
        )
        typer.echo(f"  offline models : {cached}")
        for spec in required_models(cfg.embed_model):
            typer.echo(f"                   - {spec.repo_id} ({spec.note})")
    provider_key = (cfg.provider or "").lower()
    if cfg.local_only:
        # Vision (polish + regions) is disabled in no-egress mode; printing an
        # endpoint here would falsely imply an outbound call could happen.
        typer.echo("  vision         : disabled (no egress) — bronze/silver + local search only")
    elif provider_key == "harness":
        typer.echo("  vision         : your agent harness — gold extraction runs through")
        typer.echo("                   ingest sessions (begin → submit pages → finalize)")
    else:
        typer.echo(f"  vision endpoint: {cfg.openai_base_url or 'api.openai.com (public)'}")
        typer.echo(f"  vision model   : {cfg.region_model}")

    # Lean one-time awareness: an existing ~/anchor-data still serving the
    # default project, but the user should know they can fold it into the env.
    if default_dir == LEGACY_DATA_DIR and LEGACY_DATA_DIR.is_dir():
        typer.echo("")
        typer.echo(f"  note           : using legacy {LEGACY_DATA_DIR}.")
        typer.echo("                   Run `anchor migrate` to adopt it as this "
                   "environment's default project.")

    # OCR backend probe: onnxruntime is a declared dependency but may be absent
    # when an editable install pre-dates the dep declaration and has not been
    # force-reinstalled. Report FAIL with a remediation hint so the user (or
    # an agent driving setup) knows exactly what to do; never crash the rest
    # of the check output.
    typer.echo("")
    typer.echo("OCR backend")
    ocr_ok, ocr_detail = _probe_ocr_backend()
    problems: list[str] = []
    if ocr_ok:
        typer.echo("  onnxruntime    : importable ✓")
    elif ocr_detail == "missing":
        # Genuinely not installed -- a force-reinstall re-syncs the dep.
        typer.echo("  onnxruntime    : NOT installed")
        typer.echo(
            "                   OCR backend not installed -- your editable install may be "
            "stale; run `uv tool install --force --editable .` to re-sync dependencies."
        )
        problems.append(
            "OCR backend not installed -- your editable install may be stale; "
            "run `uv tool install --force --editable .`."
        )
    else:
        # Present but fails to import (ABI mismatch, numpy double-load, ...).
        # A reinstall does NOT fix this; report the actual import error.
        typer.echo("  onnxruntime    : present but failed to import")
        typer.echo(
            f"                   OCR backend present but failed to import: {ocr_detail}"
        )
        problems.append(
            f"OCR backend present but failed to import: {ocr_detail}"
        )
    personal = bool(os.environ.get("OPENAI_API_KEY"))
    # local/ollama/harness keep content on-host → no key. openai accepts a
    # personal OPENAI_API_KEY. azure/custom (and any configured endpoint) need
    # the endpoint's own key in ANCHOR_OPENAI_API_KEY — a personal key is wrong there.
    if provider_key in ("local", "ollama", "harness"):
        needs_key = False
        key_ok = True
    elif provider_key == "openai":
        needs_key = True
        key_ok = bool(cfg.openai_api_key) or personal
    else:  # azure, custom, or an unknown provider that still names an endpoint
        needs_key = bool(cfg.openai_base_url) or embed_remote or provider_key in _KEYED_PROVIDERS
        key_ok = bool(cfg.openai_api_key)

    if needs_key:
        if cfg.openai_api_key:
            typer.echo("  api key        : ANCHOR_OPENAI_API_KEY detected ✓")
        elif key_ok:  # openai + personal key
            typer.echo("  api key        : using OPENAI_API_KEY ✓")
        else:
            typer.echo("  api key        : NOT set")
            if personal:
                typer.echo("                   (a personal OPENAI_API_KEY is set but is the wrong "
                           "credential for this endpoint)")
            problems.append(
                "API key missing — set ANCHOR_OPENAI_API_KEY in your environment or a .env "
                "(e.g. echo 'ANCHOR_OPENAI_API_KEY=…' >> .env)."
            )
    elif provider_key == "harness":
        typer.echo("  api key        : not needed — ingestion happens through the agent")
    else:
        typer.echo("  api key        : not needed (no egress)")

    # Harness mode: surface in-flight ingest sessions so a half-submitted
    # document is visible and actionable, not silently parked in staging.
    if provider_key == "harness":
        open_sessions = _open_ingest_sessions(cfg)
        typer.echo("")
        typer.echo("Harness ingest sessions")
        if not open_sessions:
            typer.echo("  none open — ready for `ingest_begin` (agent) or "
                       "`anchor ingest-session begin <pdf>`")
        for entry in open_sessions:
            typer.echo(
                f"  {entry['session_id']}  {entry['slug']}: "
                f"{entry['submitted']}/{entry['page_count']} pages submitted "
                f"({entry['state']}) — resume with ingest_status / finalize"
            )

    # Endpoint shape — repair an Azure URL that is missing /openai/v1/.
    if cfg.openai_base_url:
        fixed = normalize_base_url(provider_key, cfg.openai_base_url)
        if fixed and fixed != cfg.openai_base_url.strip():
            typer.echo("")
            typer.echo(f"  ! endpoint looks wrong for Azure: {cfg.openai_base_url}")
            typer.echo(f"    should be: {fixed}")
            apply = fix or (
                config_path is not None
                and typer.confirm("    Fix it in env.toml now?", default=True)
            )
            if apply and config_path and _rewrite_base_url(config_path, cfg.openai_base_url, fixed):
                typer.echo("    fixed.")
                # Reload so the probe uses the repaired URL.
                cfg = resolve_project_config(resolve_environment(env.name), DEFAULT_PROJECT)
            else:
                problems.append("Azure endpoint is missing the /openai/v1/ suffix.")

    # Optional live probe — confirms deployment + auth without sending documents.
    if probe:
        typer.echo("")
        typer.echo("Probe (tiny live call, no document content)")
        if not key_ok:
            typer.echo("  skipped — no usable key to authenticate with.")
            problems.append("Cannot probe without a key.")
        else:
            _probe(cfg, embed_remote, problems)

    typer.echo("")
    if problems:
        typer.echo("Not ready:")
        for p in problems:
            typer.echo(f"  - {p}")
        raise typer.Exit(code=1)
    typer.echo("Ready ✓  config resolves and the data zone is what you expect.")


def _open_ingest_sessions(cfg: AnchorConfig) -> list[dict]:
    """Open/finalizing harness sessions from <data_dir>/staging/ingest/."""
    import json

    staging = cfg.data_dir / "staging" / "ingest"
    if not staging.is_dir():
        return []
    out: list[dict] = []
    for session_file in sorted(staging.glob("*/session.json")):
        try:
            session = json.loads(session_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if session.get("state") not in ("open", "finalizing"):
            continue
        pages = session.get("pages") or {}
        out.append({
            "session_id": session.get("session_id", session_file.parent.name),
            "slug": session.get("slug", "?"),
            "state": session.get("state"),
            "page_count": session.get("page_count", len(pages)),
            "submitted": sum(
                1 for info in pages.values() if info.get("status") == "submitted"
            ),
        })
    return out


def _probe_ocr_backend() -> tuple[bool, str | None]:
    """Probe the onnxruntime OCR backend.

    Returns ``(ok, detail)``. ``ok`` is True when ``onnxruntime`` imports
    cleanly. When it does not, ``detail`` distinguishes the two failure modes
    so the caller can give the right remediation:

    - ``ModuleNotFoundError`` -> ``"missing"``: the backend is genuinely not
      installed (e.g. an editable install pre-dates the dep declaration). A
      force-reinstall fixes it.
    - any other ``ImportError`` -> the error string: the backend is present
      but fails to import (ABI mismatch, numpy double-load, ...). A reinstall
      does NOT help and the wrong hint already misdirected analysis once
      (issue #195, #174).

    Importing ``onnxruntime`` directly is the most faithful test: it is the
    backend ``RapidOcrOptions(backend='onnxruntime')`` resolves at ingest time.
    """
    try:
        import importlib

        importlib.import_module("onnxruntime")
        return True, None
    except ModuleNotFoundError:
        return False, "missing"
    except ImportError as exc:
        return False, str(exc)


def _probe(cfg: AnchorConfig, embed_remote: bool, problems: list[str]) -> None:
    """Make minimal calls to confirm the chat (and remote embed) deployments work."""
    from anchor.extensions.anchor_pdfs.infra.llm.openai_client import make_openai_client

    key = cfg.openai_api_key.get_secret_value() if cfg.openai_api_key else None
    client = make_openai_client(key, cfg.openai_base_url)
    try:
        # No token-cap parameter: it isn't portable. Newer models (gpt-5.x,
        # o-series) reject ``max_tokens`` and want ``max_completion_tokens``,
        # while older models and some OpenAI-compatible endpoints only accept
        # ``max_tokens``. The ingestion path sends neither, so the probe matches
        # it; a "ping" response is tiny regardless.
        client.chat.completions.create(
            model=cfg.region_model,
            messages=[{"role": "user", "content": "ping"}],
        )
        typer.echo(f"  chat deployment '{cfg.region_model}' : reachable ✓")
    except Exception as exc:  # noqa: BLE001 - surface the endpoint's own error
        typer.echo(f"  chat deployment '{cfg.region_model}' : FAILED — {exc}")
        problems.append(f"Vision/region deployment '{cfg.region_model}' did not respond.")
    if embed_remote:
        try:
            client.embeddings.create(model=cfg.embed_model, input=["ping"])
            typer.echo(f"  embed deployment '{cfg.embed_model}' : reachable ✓")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"  embed deployment '{cfg.embed_model}' : FAILED — {exc}")
            problems.append(f"Embedding deployment '{cfg.embed_model}' did not respond.")
