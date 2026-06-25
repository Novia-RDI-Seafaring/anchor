"""``anchor models`` — provision local models for offline / no-egress ingests.

A locked-down host running confidential documents cannot let docling or the
sentence-transformer embedder reach ``huggingface.co`` on first run. ``anchor
models prefetch`` warms the HuggingFace cache once (with network), so a later
local-only ingest loads only cached weights and makes no outbound connection.
``anchor models list`` reports the resolved model set without downloading.

This is a one-time provisioning / ops command, so it is CLI-only: it does not
sit on the per-call ingest path that the HTTP and MCP adapters expose. The
egress *posture* it serves (local-only) is honored identically across CLI, HTTP
and MCP via ``AnchorConfig.local_only``.
"""
from __future__ import annotations

import json

import typer

models_app = typer.Typer(help="Provision local models for offline / no-egress ingests.")


def _resolve_embed_model(env: str | None) -> str:
    """The embed model the active environment's default project would use."""
    from anchor.infra.environment import (
        DEFAULT_PROJECT,
        resolve_environment,
        resolve_project_config,
    )
    from anchor.infra.models import DEFAULT_EMBED_MODEL

    try:
        environment = resolve_environment(env)
        cfg = resolve_project_config(environment, DEFAULT_PROJECT)
        return cfg.embed_model
    except Exception:  # noqa: BLE001 - fall back to the default before any env exists
        return DEFAULT_EMBED_MODEL


@models_app.command("list")
def list_models(
    env: str = typer.Option(None, "--env", help="Environment NAME (default: the default env)."),
) -> None:
    """List the local models a no-egress ingest needs, without downloading."""
    from anchor.infra.models import offline_active, required_models

    embed_model = _resolve_embed_model(env)
    specs = required_models(embed_model)
    typer.echo(
        json.dumps(
            {
                "embed_model": embed_model,
                "offline_env_active": offline_active(),
                "models": [
                    {"repo_id": s.repo_id, "kind": s.kind, "note": s.note} for s in specs
                ],
            },
            indent=2,
        )
    )


@models_app.command("prefetch")
def prefetch(
    env: str = typer.Option(None, "--env", help="Environment NAME (default: the default env)."),
    embed_model: str = typer.Option(
        None, "--embed-model", help="Override the embed model to fetch (default: the env's)."
    ),
) -> None:
    """Download the local model set so a later offline ingest works.

    Loads the embedder + docling models exactly as ingest would, populating the
    HuggingFace cache. Needs network access; run it once before going offline.
    Exits non-zero if any model fails to fetch, so a provisioning script can gate
    on it.
    """
    from anchor.infra.models import prefetch_models

    target = embed_model or _resolve_embed_model(env)
    typer.echo(f"Prefetching local models (embed: {target}) … this needs network.", err=True)
    results = prefetch_models(target)
    typer.echo(json.dumps({"prefetched": results}, indent=2))
    if any(not r["ok"] for r in results):
        failed = [str(r["repo_id"]) for r in results if not r["ok"]]
        typer.echo(f"Prefetch incomplete: {', '.join(failed)} failed.", err=True)
        raise typer.Exit(code=1)
    typer.echo("All models cached ✓  a local-only ingest can now run offline.", err=True)
