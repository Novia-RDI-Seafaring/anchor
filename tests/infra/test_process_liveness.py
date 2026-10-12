"""Process probes use isolated children, never the runner or its parent."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from anchor.infra import serve_registry as sr


def test_live_and_exited_child(monkeypatch):
    if os.name == "nt":
        monkeypatch.setattr(os, "kill", Mock(side_effect=AssertionError("signal sent")))
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        start_new_session=os.name != "nt",
    ) as child:
        try:
            assert sr._pid_alive(child.pid)
            child.communicate(timeout=10)
            assert not sr._pid_alive(child.pid)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


@pytest.mark.parametrize("pid", [0, -1])
def test_invalid_pid_never_signals(pid, monkeypatch):
    monkeypatch.setattr(os, "kill", Mock(side_effect=AssertionError("signal sent")))
    assert not sr._pid_alive(pid)


@pytest.mark.parametrize("error,expected", [(5, True), (87, False)])
def test_windows_denied_and_missing_process(error, expected, monkeypatch):
    kernel = SimpleNamespace(OpenProcess=Mock(return_value=None),
                             WaitForSingleObject=Mock(), CloseHandle=Mock())
    monkeypatch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error, raising=False)
    assert sr._windows_pid_alive(1234) is expected
    kernel.WaitForSingleObject.assert_not_called()
    kernel.CloseHandle.assert_not_called()


@pytest.mark.parametrize("status,expected", [(0, False), (258, True), (0xFFFFFFFF, True)])
def test_windows_wait_releases_handle(status, expected, monkeypatch):
    kernel = SimpleNamespace(OpenProcess=Mock(return_value=42),
                             WaitForSingleObject=Mock(return_value=status),
                             CloseHandle=Mock())
    monkeypatch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
    assert sr._windows_pid_alive(1234) is expected
    kernel.OpenProcess.assert_called_once_with(0x00100000, False, 1234)
    kernel.WaitForSingleObject.assert_called_once_with(42, 0)
    kernel.CloseHandle.assert_called_once_with(42)


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only signal-zero behavior")
@pytest.mark.parametrize("error,expected", [(PermissionError, True), (ProcessLookupError, False)])
def test_posix_errors(error, expected, monkeypatch):
    monkeypatch.setattr(os, "kill", Mock(side_effect=error))
    assert sr._pid_alive(1234) is expected
