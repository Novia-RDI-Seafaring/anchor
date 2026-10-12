"""The actual MCP entrypoint exits after an initialized client closes stdin."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import anchor

_CHILD_CODE = """
from pathlib import Path
import sys
from anchor.infra import environment, environment_storage

root = Path(sys.argv[1])
environment.ANCHOR_HOME = root
environment_storage.ANCHOR_HOME = root
environment.LEGACY_DATA_DIR = root / "legacy"
environment_storage.LEGACY_DATA_DIR = root / "legacy"
environment.create_env("stdio-lifecycle", settings={"provider": "local", "local_only": True})

from anchor.adapters.mcp.stdio_main import main
sys.argv = ["anchor-mcp", "--env", "stdio-lifecycle"]
main()
"""


def test_initialized_mcp_child_exits_on_stdin_eof(tmp_path):
    child_env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ANCHOR_") and name != "OPENAI_API_KEY"
    }
    child_env["PYTHONPATH"] = str(Path(anchor.__file__).resolve().parent.parent)
    child_env["HF_HUB_OFFLINE"] = "1"
    child_env["TRANSFORMERS_OFFLINE"] = "1"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    responses: queue.Queue[str | None] = queue.Queue()
    stderr_lines: list[str] = []

    with subprocess.Popen(
        [sys.executable, "-c", _CHILD_CODE, str(tmp_path / "registry")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        env=child_env,
        creationflags=flags,
        start_new_session=os.name != "nt",
    ) as child:
        def read_stdout():
            for line in child.stdout:
                responses.put(line)
            responses.put(None)

        def read_stderr():
            stderr_lines.extend(child.stderr)

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        def send(message):
            child.stdin.write(json.dumps(message) + "\n")
            child.stdin.flush()

        def expect_response(request_id):
            line = responses.get(timeout=20)
            assert line is not None, "MCP child exited before replying: " + "".join(stderr_lines)
            response = json.loads(line)
            assert response["id"] == request_id, response
            assert "result" in response, response

        try:
            send({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "stdio-lifecycle-test", "version": "1"},
                },
            })
            expect_response(1)
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "ping"})
            expect_response(2)

            child.stdin.close()
            assert child.wait(timeout=5) == 0, "".join(stderr_lines)
        finally:
            # A regression must not leave another orphan in the test runner.
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
