"""`anchor serve` falls through to the next free port when one is taken."""
from __future__ import annotations

import socket

from anchor.adapters.cli.serve import _find_free_port


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
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        busy = taken.getsockname()[1]
        chosen = _find_free_port("127.0.0.1", busy)
        assert chosen > busy  # didn't pick the in-use port
