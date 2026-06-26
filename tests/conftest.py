# Import onnxruntime once up front so numpy is initialized via it exactly
# once; otherwise a later onnxruntime import after numpy is already loaded
# raises numpy's "cannot load module more than once per process" on Linux CI.
# See issue #206 (follow-up to #198's per-file mocks).
try:
    import onnxruntime  # noqa: F401
except Exception:
    pass
