"""Project management — list / create / remove / rename in an environment.

The HTTP peer of the ``anchor project`` CLI group and the ``list_projects`` /
``create_project`` / ``remove_project`` / ``rename_project`` MCP tools. Per the
v2 adapter-parity rule, all three surfaces reach the same core ops in
``anchor.infra.environment``.

A project is an environment-level concern (a corpus registered in the env's
``projects.toml``), not a property of the single served workspace, so these
endpoints resolve the environment by name — ``?env=<name>`` or the resolved
default — independently of which project this server happens to be serving.
``move`` is deliberately CLI-only: crossing a trust boundary is human-only.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from anchor.adapters.http.schemas import CreateProjectRequest, RenameProjectRequest
from anchor.core.ids import InvalidProjectNameError
from anchor.infra.environment import (
    Environment,
    NoEnvironmentError,
    NoProjectError,
    ProjectNotEmptyError,
    create_project,
    project_meta,
    remove_project,
    rename_project,
    resolve_environment,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _resolve_initialized_env(env: str | None) -> Environment:
    try:
        environment = resolve_environment(env)
    except ValueError as exc:  # invalid env name
        raise HTTPException(400, str(exc)) from exc
    if not environment.initialized:
        raise HTTPException(404, f"environment {environment.name!r} is not set up")
    return environment


@router.get("")
async def list_projects(env: str | None = Query(None)):
    environment = _resolve_initialized_env(env)
    return {
        "environment": environment.name,
        "projects": [
            {"name": name, "description": project_meta(environment, name).description}
            for name in environment.list_project_names()
        ],
    }


@router.post("", status_code=201)
async def create_project_endpoint(
    req: CreateProjectRequest, env: str | None = Query(None)
):
    environment = _resolve_initialized_env(env)
    try:
        create_project(environment, req.name, description=req.description)
    except InvalidProjectNameError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "created": req.name,
        "environment": environment.name,
        "data_dir": str(environment.project_dir(req.name)),
    }


@router.delete("/{name}")
async def remove_project_endpoint(
    name: str,
    env: str | None = Query(None),
    delete_data: bool = Query(False),
    force: bool = Query(False),
):
    environment = _resolve_initialized_env(env)
    try:
        return remove_project(
            environment, name, delete_data=delete_data, force=force
        )
    except InvalidProjectNameError as exc:
        raise HTTPException(400, str(exc)) from exc
    except NoProjectError as exc:
        raise HTTPException(404, str(exc)) from exc
    except NoEnvironmentError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProjectNotEmptyError as exc:
        raise HTTPException(
            409,
            detail={
                "message": str(exc),
                "project": exc.name,
                "documents": exc.documents,
                "canvases": exc.canvases,
            },
        ) from exc


@router.patch("/{name}")
async def rename_project_endpoint(
    name: str, req: RenameProjectRequest, env: str | None = Query(None)
):
    environment = _resolve_initialized_env(env)
    try:
        return rename_project(environment, name, req.new)
    except InvalidProjectNameError as exc:
        raise HTTPException(400, str(exc)) from exc
    except NoProjectError as exc:
        raise HTTPException(404, str(exc)) from exc
    except NoEnvironmentError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
