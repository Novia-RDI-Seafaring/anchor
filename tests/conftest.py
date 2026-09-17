import importlib

import pytest

# Load onnxruntime once up front so numpy is initialized via it exactly once;
# otherwise a later onnxruntime import after numpy is already loaded raises
# numpy's "cannot load module more than once per process" on Linux CI.
# See issue #206 (follow-up to #198's per-file mocks).
try:
    importlib.import_module("onnxruntime")
except Exception:
    # onnxruntime is optional in minimal/non-ingest test envs; the guard is
    # only needed when it is installed, so a missing backend is fine here.
    pass


@pytest.fixture(autouse=True)
def _reset_actor_context():
    """Isolate the #322 actor ContextVar between tests.

    The CLI's `anchor canvas` callback (and any test using
    `set_current_actor` directly) sets the ambient actor for the whole
    process context — fine for a one-shot CLI process, but in pytest it
    would leak attribution into unrelated tests."""
    from anchor.core.events.actor import reset_current_actor, set_current_actor

    token = set_current_actor(None)
    yield
    reset_current_actor(token)
