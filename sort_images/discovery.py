"""Find the image files inside the input folder that are candidates for sorting."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path

from .filetypes import looks_like_image

logger = logging.getLogger(__name__)

#: Folders created by a previous run, e.g. "2023-05".
DEST_DIR_RE = re.compile(r"^\d{4}-\d{2}$")

#: Folder for files with no determinable date.
UNDATED_DIR_NAME = "undated"

#: Bookkeeping folders that never hold photographs. Windows and NAS volumes do
#: not follow the dot-prefix convention macOS hides files with, so an NTFS
#: drive plugged into a Mac exposes these in plain sight. Matched
#: case-insensitively, since NTFS itself is.
SYSTEM_DIR_NAMES = frozenset(
    {
        "system volume information",   # NTFS
        "$recycle.bin",                # Windows recycle bin
        "recycler",                    # older Windows recycle bin
        "found.000",                   # chkdsk recovery
        "@eadir",                      # Synology thumbnails
        ".trashes",                    # macOS
        ".spotlight-v100",
        ".fseventsd",
        ".temporaryitems",
        ".documentrevisions-v100",
    }
)


def is_system_dir(path: Path) -> bool:
    """True for bookkeeping folders that should never be scanned."""
    return path.name.lower() in SYSTEM_DIR_NAMES


def is_destination_dir(path: Path) -> bool:
    """True when ``path`` is a folder this tool would itself create."""
    return bool(DEST_DIR_RE.match(path.name)) or path.name == UNDATED_DIR_NAME


def is_under(path: Path, ancestor: Path) -> bool:
    """True when ``path`` is ``ancestor`` or sits inside it."""
    return path == ancestor or ancestor in path.parents


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def should_skip_dir(directory: Path, output_root: Path | None) -> bool:
    """Decide whether a recursive scan should descend into ``directory``.

    Two cases are skipped:

    * The output folder itself -- otherwise a run with ``-o`` pointing inside
      ``-i`` would immediately re-process everything it just wrote.
    * ``YYYY-MM`` / ``undated`` folders *belonging to the output folder*, which
      is what makes re-running over an already sorted library a no-op.

    Sorted-looking folders in the input are only skipped when they are part of
    the output. Pointing ``-o`` somewhere new therefore re-files an
    already-sorted library instead of silently ignoring it.

    System folders are skipped unconditionally -- they hold no photographs, and
    on an external NTFS drive they are often large.
    """
    if is_system_dir(directory):
        return True
    if output_root is None:
        return False
    if directory == output_root:
        return True
    return is_destination_dir(directory) and is_under(directory, output_root)


def iter_candidate_files(
    root: Path, recursive: bool = False, output_root: Path | None = None
) -> Iterator[Path]:
    """Yield image files under ``root``, in stable sorted order.

    Hidden files are skipped, and non-image files are left entirely alone --
    they are never moved.
    """
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if _is_hidden(entry):
            continue

        if entry.is_dir():
            if not recursive:
                continue
            if should_skip_dir(entry, output_root):
                logger.debug("skipping folder %s", entry)
                continue
            yield from iter_candidate_files(entry, True, output_root)
            continue

        if entry.is_file():
            if looks_like_image(entry):
                yield entry
            else:
                logger.debug("not an image, leaving alone: %s", entry)


def find_images(
    root: Path, recursive: bool = False, output_root: Path | None = None
) -> tuple[Path, ...]:
    """Return all candidate image files under ``root`` as an immutable tuple."""
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    return tuple(iter_candidate_files(root, recursive, output_root))
