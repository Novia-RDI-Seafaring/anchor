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

from anchor.infra.config import AnchorConfig, discover_config_file
from anchor.infra.providers import get_provider, normalize_base_url

# Providers that authenticate against an endpoint (mirror of init's set).
_KEYED_PROVIDERS = ("openai", "azure", "custom")


def _rewrite_base_url(config_path, old: str, new: str) -> bool:
    """Replace the openai_base_url value in the toml in place. True on success."""
    text = config_path.read_text()
    needle = f'openai_base_url = "{old}"'
    if needle not in text:
        return False
    config_path.write_text(text.replace(needle, f'openai_base_url = "{new}"'))
    return True


def check(
    probe: bool = typer.Option(
        False, "--probe", help="Make one tiny live call to confirm the deployment + key work."
    ),
    fix: bool = typer.Option(
        False, "--fix", help="Apply any safe endpoint repair without prompting."
    ),
) -> None:
    """Verify the resolved data zone + config for this project."""
    config_path = discover_config_file()
    cfg = AnchorConfig()
    prov = get_provider(cfg.provider) if cfg.provider else None

    typer.echo("Data zone")
    if config_path:
        typer.echo(f"  config         : {config_path}")
    else:
        typer.echo("  config         : (none found — using ANCHOR_* env + defaults)")
    if prov:
        typer.echo(f"  provider       : {prov.label} — {prov.zone}")
    elif cfg.provider:
        typer.echo(f"  provider       : {cfg.provider}")
    # Be honest when the resolved data dir is not on disk yet: a fresh project
    # has none until first ingest, but a bare path here reads as "all set" and
    # has masked a misconfigured zone before. Say so rather than imply it exists.
    data_dir_note = (
        "" if cfg.data_dir.exists() else "  (does not exist yet, created on first ingest)"
    )
    typer.echo(f"  data dir       : {cfg.data_dir}{data_dir_note}")
    embed_remote = cfg.embed_model.startswith("text-embedding-")
    typer.echo(
        f"  embed model    : {cfg.embed_model}  "
        f"({'remote — sent to your endpoint' if embed_remote else 'local, no egress'})"
    )
    provider_key = (cfg.provider or "").lower()
    if provider_key == "harness":
        typer.echo("  vision         : your agent harness — gold extraction runs through")
        typer.echo("                   ingest sessions (begin → submit pages → finalize)")
    else:
        typer.echo(f"  vision endpoint: {cfg.openai_base_url or 'api.openai.com (public)'}")
        typer.echo(f"  vision model   : {cfg.region_model}")

    problems: list[str] = []
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
                and typer.confirm("    Fix it in anchor.toml now?", default=True)
            )
            if apply and config_path and _rewrite_base_url(config_path, cfg.openai_base_url, fixed):
                typer.echo("    fixed.")
                cfg = AnchorConfig()  # reload so the probe uses the repaired URL
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
