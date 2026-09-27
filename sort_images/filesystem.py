"""Work out what a filesystem will actually let us do, before we try it.

This exists because of read-only volumes. macOS mounts NTFS drives read-only
unless a third-party driver is installed, and an external archive disk may be
mounted read-only deliberately. Discovering that one file at a time -- after a
long EXIF scan -- is a miserable way to find out, so the checks here run first.

Mount flags alone are not enough (a writable mount can still hold a folder you
lack permission on), so writability is established by actually writing.
"""

from __future__ import annotations

import errno
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: Probe files are removed immediately; the prefix only matters if a crash
#: leaves one behind, so it is recognisable.
_PROBE_PREFIX = ".sort_images_write_probe_"


@dataclass(frozen=True, slots=True)
class Writability:
    """Whether a location can be written to, and why not when it cannot."""

    writable: bool
    reason: str = ""
    read_only_mount: bool = False

    def __bool__(self) -> bool:
        return self.writable


def nearest_existing_ancestor(path: Path) -> Path:
    """Return ``path`` if it exists, else the closest ancestor that does.

    Output folders are created on demand, so the useful question is whether the
    place they *would* be created is writable.
    """
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            return current
        current = parent
    return current


def is_read_only_mount(path: Path) -> bool:
    """True when ``path`` sits on a filesystem mounted read-only."""
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except (OSError, AttributeError, ValueError):
        return False


def check_writable(path: Path) -> Writability:
    """Establish whether files can be created under ``path``.

    Writes a probe file rather than trusting mount flags or permission bits,
    because only an actual write accounts for ACLs, quotas and driver quirks.
    """
    target = nearest_existing_ancestor(path)
    read_only = is_read_only_mount(target)

    try:
        with tempfile.NamedTemporaryFile(dir=target, prefix=_PROBE_PREFIX):
            pass
    except OSError as error:
        if error.errno == errno.EROFS:
            reason = "read-only filesystem"
            read_only = True
        elif error.errno in (errno.EACCES, errno.EPERM):
            reason = "permission denied"
        elif error.errno == errno.ENOSPC:
            reason = "no space left on device"
        else:
            reason = error.strerror or str(error)
        return Writability(writable=False, reason=reason, read_only_mount=read_only)

    return Writability(writable=True, read_only_mount=read_only)
