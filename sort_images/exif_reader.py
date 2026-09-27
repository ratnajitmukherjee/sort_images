"""Extract the capture timestamp from inside an image file.

No single library reads every format, so backends are chained and the first one
to produce a usable date wins:

1. ``exifread``  -- pure Python; JPEG and every TIFF-derived raw (DNG, NEF,
   CR2, ARW, ORF, PEF, SRW, ...).
2. ``Pillow``    -- HEIC/HEIF/AVIF via ``pillow-heif``, plus PNG/WebP/TIFF.
3. ``exiftool``  -- optional external binary. Skipped when not installed; when
   present it catches the exotic formats the first two cannot decode.

Tags are consulted in order of trustworthiness: DateTimeOriginal is the moment
the shutter fired, DateTimeDigitized is when it was written to card, and
DateTime is a plain modification stamp that editing software rewrites.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# exifread logs parse warnings for many raw files; they are expected noise.
logging.getLogger("exifread").setLevel(logging.CRITICAL)

#: Earliest plausible photograph, used to reject garbage timestamps.
MIN_YEAR = 1826
MAX_YEAR = 2100

EXIFTOOL_TIMEOUT_SECONDS = 20

#: Preferred order of EXIF date tags, most trustworthy first.
_EXIFREAD_TAGS = (
    "EXIF DateTimeOriginal",
    "EXIF DateTimeDigitized",
    "Image DateTime",
)

#: Pillow tag ids, same ordering.
_PILLOW_TAGS = (
    (36867, "DateTimeOriginal"),
    (36868, "DateTimeDigitized"),
    (306, "DateTime"),
)
_PILLOW_EXIF_IFD = 0x8769

_EXIFTOOL_TAGS = (
    "DateTimeOriginal",
    "CreateDate",
    "SubSecDateTimeOriginal",
    "ModifyDate",
)

# Accepts "2023:05:14 12:30:45", "2023-05-14T12:30:45", "2023:05:14", and
# tolerates trailing subsecond / timezone suffixes by simply ignoring them.
_DATETIME_RE = re.compile(
    r"^\s*(\d{4})[:\-/](\d{1,2})[:\-/](\d{1,2})"
    r"(?:[T ]\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?"
)


@dataclass(frozen=True, slots=True)
class ExifDate:
    """A capture timestamp plus where it came from."""

    value: datetime
    tag: str
    backend: str


def parse_exif_datetime(raw: object) -> datetime | None:
    """Parse an EXIF datetime string, returning None when it is unusable.

    Cameras emit malformed placeholders such as ``0000:00:00 00:00:00`` when the
    clock was never set; those are rejected rather than silently bucketed.
    """
    if raw is None:
        return None

    match = _DATETIME_RE.match(str(raw).replace("\x00", " "))
    if match is None:
        return None

    year, month, day = (int(part) for part in match.group(1, 2, 3))
    hour, minute, second = (int(part or 0) for part in match.group(4, 5, 6))

    if not MIN_YEAR <= year <= MAX_YEAR:
        return None

    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        # Impossible calendar dates (month 0, 31 February, hour 25, ...).
        return None


def _first_valid(
    candidates: list[tuple[str, object]], backend: str
) -> ExifDate | None:
    """Return the first candidate whose raw value parses into a datetime."""
    for tag, raw in candidates:
        parsed = parse_exif_datetime(raw)
        if parsed is not None:
            return ExifDate(value=parsed, tag=tag, backend=backend)
    return None


def _read_with_exifread(path: Path) -> ExifDate | None:
    try:
        import exifread
    except ImportError:  # pragma: no cover - dependency is declared
        return None

    try:
        with path.open("rb") as handle:
            # details=False skips makernotes and thumbnails, which is a large
            # speed win on raw files and irrelevant for date tags.
            tags = exifread.process_file(handle, details=False)
    except Exception:
        return None

    if not tags:
        return None

    candidates = [(tag, tags[tag]) for tag in _EXIFREAD_TAGS if tag in tags]
    return _first_valid(candidates, backend="exifread")


def _read_with_pillow(path: Path) -> ExifDate | None:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - dependency is declared
        return None

    _register_heif_opener()

    try:
        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return None
            # DateTimeOriginal lives in the Exif sub-IFD, not the base IFD.
            sub_ifd = exif.get_ifd(_PILLOW_EXIF_IFD) or {}
    except Exception:
        return None

    candidates = [
        (name, sub_ifd.get(tag_id, exif.get(tag_id)))
        for tag_id, name in _PILLOW_TAGS
    ]
    return _first_valid(candidates, backend="pillow")


def _read_with_exiftool(path: Path) -> ExifDate | None:
    binary = _exiftool_path()
    if binary is None:
        return None

    args = [binary, "-json", "-n", "-d", "%Y:%m:%d %H:%M:%S"]
    args += [f"-{tag}" for tag in _EXIFTOOL_TAGS]
    args.append(str(path))

    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=EXIFTOOL_TIMEOUT_SECONDS,
            check=False,
        )
        payload = json.loads(completed.stdout or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None

    if not payload:
        return None

    record = payload[0]
    candidates = [(tag, record.get(tag)) for tag in _EXIFTOOL_TAGS]
    return _first_valid(candidates, backend="exiftool")


@lru_cache(maxsize=1)
def _exiftool_path() -> str | None:
    """Locate the optional exiftool binary once per process."""
    return shutil.which("exiftool")


@lru_cache(maxsize=1)
def _register_heif_opener() -> bool:
    """Teach Pillow to open HEIC/AVIF. Safe to call repeatedly."""
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        return True
    except Exception:  # pragma: no cover - optional capability
        return False


#: Backends in the order they are attempted.
BACKENDS = (_read_with_exifread, _read_with_pillow, _read_with_exiftool)


def read_capture_date(path: Path) -> ExifDate | None:
    """Return the capture timestamp stored inside ``path``, or None.

    Every backend is tried in turn; failures are swallowed so that one
    unreadable file never aborts a whole run.
    """
    for backend in BACKENDS:
        result = backend(path)
        if result is not None:
            logger.debug(
                "%s: %s = %s (via %s)",
                path.name, result.tag, result.value, result.backend,
            )
            return result
        logger.debug("%s: no date from %s", path.name, backend.__name__)

    logger.debug("%s: no usable capture date from any backend", path.name)
    return None


def exiftool_available() -> bool:
    """True when the optional exiftool fallback can be used."""
    return _exiftool_path() is not None
