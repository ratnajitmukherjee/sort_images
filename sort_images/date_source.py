"""Decide which date represents a photo, and record where that date came from.

EXIF is always the authority: the file is opened and its metadata read, whatever
the filename happens to say. Two opt-in fallbacks exist for files that carry no
EXIF at all (screenshots, exports stripped by messaging apps, scans):

* ``--fallback-filename`` -- parse an unambiguous ``YYYYMMDD`` run in the name.
* ``--fallback-mtime``    -- trust the filesystem modification time.

Both are off by default, because a wrong date silently files a photo under the
wrong month. Whatever is used is reported, so a run is always auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from .exif_reader import MAX_YEAR, MIN_YEAR, read_capture_date


class DateOrigin(str, Enum):
    """Where a resolved date came from."""

    EXIF = "exif"
    FILENAME = "filename"
    MTIME = "mtime"


# Matches YYYY-MM-DD / YYYYMMDD / YYYY_MM_DD with a consistent separator,
# optionally followed by HHMMSS. Only ISO ordering is accepted: day-first names
# such as "14-05-2023" are ambiguous and are deliberately left unmatched.
#
# The time part is fussy on purpose. The separator is restricted to real
# separators (or the macOS " at " idiom) so that "IMG-20230514-WA0001.jpg" does
# not read "0001" as a time, while a trailing run of up to three digits is
# tolerated for Pixel's "PXL_20230514_123045123.jpg" millisecond suffix.
_FILENAME_DATE_RE = re.compile(
    r"(?<!\d)(\d{4})([-_:.]?)(0[1-9]|1[0-2])\2(0[1-9]|[12]\d|3[01])(?!\d)"
    r"(?:(?:[-_ T.]|\sat\s)\s*"
    r"(\d{2})[-_:.]?(\d{2})(?:[-_:.]?(\d{2}))?(?!\d{4}))?"
)


@dataclass(frozen=True, slots=True)
class FallbackPolicy:
    """Which non-EXIF sources a run is allowed to consult."""

    use_filename: bool = False
    use_mtime: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedDate:
    """The outcome of resolving a single file's date.

    ``value`` is None when no permitted source produced a usable date, in which
    case the file is routed to the undated folder rather than guessed at.
    """

    value: datetime | None
    origin: DateOrigin | None = None
    detail: str = ""

    @property
    def found(self) -> bool:
        return self.value is not None


NO_DATE = ResolvedDate(value=None, origin=None, detail="no usable date found")


def date_from_filename(name: str) -> datetime | None:
    """Extract a date from an ISO-ordered ``YYYYMMDD`` run inside ``name``."""
    match = _FILENAME_DATE_RE.search(name)
    if match is None:
        return None

    year, month, day = int(match.group(1)), int(match.group(3)), int(match.group(4))
    hour, minute, second = (int(part or 0) for part in match.group(5, 6, 7))

    if not MIN_YEAR <= year <= MAX_YEAR:
        return None

    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def date_from_mtime(path: Path) -> datetime | None:
    """Return the filesystem modification time of ``path``."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except (OSError, OverflowError, ValueError):
        return None


def resolve_date(path: Path, policy: FallbackPolicy | None = None) -> ResolvedDate:
    """Resolve the capture date for ``path``, trying EXIF before any fallback."""
    policy = policy or FallbackPolicy()

    exif = read_capture_date(path)
    if exif is not None:
        return ResolvedDate(
            value=exif.value,
            origin=DateOrigin.EXIF,
            detail=f"{exif.tag} via {exif.backend}",
        )

    if policy.use_filename:
        from_name = date_from_filename(path.name)
        if from_name is not None:
            return ResolvedDate(
                value=from_name,
                origin=DateOrigin.FILENAME,
                detail="parsed from filename",
            )

    if policy.use_mtime:
        from_mtime = date_from_mtime(path)
        if from_mtime is not None:
            return ResolvedDate(
                value=from_mtime,
                origin=DateOrigin.MTIME,
                detail="filesystem modification time",
            )

    return NO_DATE
