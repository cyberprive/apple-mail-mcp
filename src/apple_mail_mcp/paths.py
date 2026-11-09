"""Where attachments may be written.

Invariant: nothing this MCP saves lands outside the attachments folder
(SETTINGS.attachments_dir), whatever `target_dir` the caller passes.

The caller is a model that has just read untrusted email, so `target_dir` is
untrusted input. It is resolved here — `~`, `..` and symlinks included — and
refused if the real path is not the folder or something under it. The file
*name* comes from the sender and is sanitized in scripts/save_attachments.js.
"""
from __future__ import annotations

import os
from pathlib import Path


class PathOutsideRootError(ValueError):
    """target_dir resolves to somewhere outside the attachments folder."""


def resolve_target_dir(target_dir: str | None, root: Path, *, create: bool = True) -> Path:
    """Return the real directory to save into, or raise.

    Args:
        target_dir: None/empty means the folder itself. A relative path is taken
            relative to the folder. An absolute path must already be inside it.
        root: The attachments folder.
        create: Create the directory (and the folder) if missing. The check runs
            before anything is created, so a refused path creates nothing.

    Raises:
        PathOutsideRootError: The resolved path is outside `root`.
        ValueError: The path is malformed (e.g. contains a NUL byte).
        OSError: The directory could not be created.
    """
    root_real = Path(os.path.realpath(Path(root).expanduser()))
    if target_dir is None or not str(target_dir).strip():
        candidate = root_real
    else:
        p = Path(str(target_dir)).expanduser()
        candidate = p if p.is_absolute() else root_real / p

    resolved = Path(os.path.realpath(candidate))
    if resolved != root_real and root_real not in resolved.parents:
        raise PathOutsideRootError(
            f"target_dir {str(target_dir)!r} is outside the attachments folder "
            f"{str(root_real)!r}. Pass a path inside it, or a relative one. "
            "The folder is set by APPLE_MAIL_MCP_ATTACHMENTS_DIR."
        )
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved
