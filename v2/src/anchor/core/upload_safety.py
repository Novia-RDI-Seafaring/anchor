"""Pure helpers for normalising and validating user-supplied upload paths.

The HTTP upload routes accept a client-controlled `filename` and an
extension catalogue chooses where on disk it lands. Without containment
those filenames are a path-traversal vector: a crafted name like
``../../etc/passwd.pdf`` or ``..\\..\\evil.fmu`` would otherwise escape
the storage root. We push the policy here so HTTP, MCP, and CLI all
share one implementation, and the import-linter contract keeps the core
free of FastAPI / Starlette types.

Two helpers:

- :func:`safe_upload_name` — strip path components, reject the obvious
  exploits, enforce an extension allow-list. Returns the cleaned name.
- :func:`assert_within` — last-line-of-defence containment check at the
  filesystem store: resolve both paths and assert the target is a
  descendant of the storage root.

Both raise :class:`UnsafeUploadError`; routes translate that to HTTP 400.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


class UnsafeUploadError(ValueError):
    """Raised when an upload filename or destination path is rejected."""


_CONTROL_CHARS = {chr(i) for i in range(32)} | {chr(127)}


def safe_upload_name(filename: str | None, *, allowed_extensions: set[str]) -> str:
    """Return a path-component-free filename or raise :class:`UnsafeUploadError`.

    The filename is checked against four properties:

    - non-empty and free of NUL / control characters
    - contains no POSIX or Windows path separators after normalisation
    - is not a relative-traversal token (``..`` / ``.``)
    - lower-cased extension is in ``allowed_extensions`` (each entry like
      ``".pdf"`` — leading dot, lower-case)

    The returned value is safe to ``join`` against a storage root. Callers
    should *still* apply :func:`assert_within` after constructing the
    target path, since slugify-style transforms downstream are a second
    line of defence.
    """
    if not filename:
        raise UnsafeUploadError("filename missing")
    if any(c in filename for c in _CONTROL_CHARS):
        raise UnsafeUploadError("filename contains control characters")

    # Reject either separator regardless of host platform. We want a
    # Linux server to refuse a Windows-style ``..\\evil.pdf`` payload.
    posix_name = PurePosixPath(filename).name
    windows_name = PureWindowsPath(filename).name
    if posix_name != filename or windows_name != filename:
        raise UnsafeUploadError("filename must not contain path components")

    if filename in {".", ".."}:
        raise UnsafeUploadError("filename must not be a traversal token")

    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise UnsafeUploadError(f"extension {ext!r} not allowed (expected one of: {allowed})")

    return filename


def assert_within(target: Path, root: Path) -> Path:
    """Resolve ``target`` and assert it stays under ``root``.

    Defensive against symlink escapes and any residual traversal that
    survived earlier checks. Returns the resolved target so callers can
    use it directly (e.g. for ``write_bytes``). Raises
    :class:`UnsafeUploadError` if the resolved target is outside ``root``.
    """
    resolved_root = root.resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise UnsafeUploadError(
            f"path {target!s} escapes storage root {root!s}"
        ) from exc
    return resolved
