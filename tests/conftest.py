import importlib

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
