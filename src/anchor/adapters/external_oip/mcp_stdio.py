"""MCP stdio transport adapter for an external OIP producer process."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, Tool

from anchor.adapters.external_oip.gateway import ProducerSpec

_REQUEST_TIMEOUT_SECONDS = 20.0
_SHUTDOWN_TIMEOUT_SECONDS = 5.0


@dataclass
class _Request:
    operation: Literal["list_tools", "call_tool", "close"]
    future: asyncio.Future[Any]
    name: str | None = None
    arguments: dict[str, Any] | None = None


class McpStdioProducerClient:
    """Own one MCP process in one worker task from startup through shutdown."""

    def __init__(self, spec: ProducerSpec) -> None:
        self._spec = spec
        self._queue: asyncio.Queue[_Request] = asyncio.Queue()
        self._ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(
            self._run(),
            name=f"oip-producer:{spec.name}",
        )
        self._failure: BaseException | None = None

    @classmethod
    async def start(cls, spec: ProducerSpec) -> McpStdioProducerClient:
        client = cls(spec)
        try:
            await asyncio.wait_for(
                asyncio.shield(client._ready),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except BaseException:
            await client.close()
            raise
        return client

    async def list_tools(self) -> list[Tool]:
        return await self._request("list_tools")

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        return await self._request("call_tool", name=name, arguments=arguments)

    async def close(self) -> None:
        if self._task.done():
            await _consume_task(self._task)
            return
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self._queue.put(_Request(operation="close", future=future))
        try:
            await asyncio.wait_for(
                asyncio.shield(self._task),
                timeout=_SHUTDOWN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            self._task.cancel()
            await _consume_task(self._task)

    async def _request(
        self,
        operation: Literal["list_tools", "call_tool"],
        *,
        name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        if self._failure is not None:
            raise RuntimeError(
                f"producer process {self._spec.name!r} is unavailable: "
                f"{self._failure}"
            ) from self._failure
        if self._task.done():
            raise RuntimeError(f"producer process {self._spec.name!r} stopped")
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self._queue.put(
            _Request(
                operation=operation,
                future=future,
                name=name,
                arguments=arguments,
            )
        )
        return await asyncio.wait_for(future, timeout=_REQUEST_TIMEOUT_SECONDS)

    async def _run(self) -> None:
        current: _Request | None = None
        try:
            params = StdioServerParameters(
                command=self._spec.command,
                args=list(self._spec.args),
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=_REQUEST_TIMEOUT_SECONDS),
                ) as session:
                    await session.initialize()
                    self._ready.set_result(None)
                    while True:
                        current = await self._queue.get()
                        if current.operation == "close":
                            current.future.set_result(None)
                            break
                        try:
                            if current.operation == "list_tools":
                                current.future.set_result(await _list_all_tools(session))
                            else:
                                current.future.set_result(
                                    await session.call_tool(
                                        current.name or "",
                                        current.arguments or {},
                                    )
                                )
                        except BaseException as exc:
                            current.future.set_exception(exc)
                        finally:
                            current = None
        except BaseException as exc:
            self._failure = exc
            if not self._ready.done():
                self._ready.set_exception(exc)
            if current is not None and not current.future.done():
                current.future.set_exception(exc)
            self._fail_pending(exc)
        finally:
            if not self._ready.done():
                self._ready.set_exception(
                    RuntimeError(f"producer process {self._spec.name!r} stopped during startup")
                )

    def _fail_pending(self, exc: BaseException) -> None:
        while not self._queue.empty():
            request = self._queue.get_nowait()
            if not request.future.done():
                request.future.set_exception(exc)


async def _list_all_tools(session: ClientSession) -> list[Tool]:
    result = await session.list_tools()
    tools = list(result.tools)
    while result.nextCursor:
        result = await session.list_tools(result.nextCursor)
        tools.extend(result.tools)
    return tools


async def _consume_task(task: asyncio.Task[None]) -> None:
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def connect_mcp_stdio(spec: ProducerSpec) -> McpStdioProducerClient:
    """Start one isolated producer process without shell interpretation."""
    return await McpStdioProducerClient.start(spec)
