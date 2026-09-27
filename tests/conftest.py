"""Shared fixtures: builders for real image files carrying real EXIF tags.

Tests run against genuine encoded images rather than mocks, so the EXIF reading
path is exercised the same way it will be in production.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

EXIF_IFD = 0x8769
DATETIME_ORIGINAL = 36867
DATETIME_DIGITIZED = 36868
DATETIME = 306


def exif_timestamp(value: datetime) -> str:
    """Format a datetime the way EXIF stores it."""
    return value.strftime("%Y:%m:%d %H:%M:%S")


def write_jpeg(
    path: Path,
    taken: datetime | None = None,
    *,
    tag: int = DATETIME_ORIGINAL,
    colour: str = "red",
) -> Path:
    """Write a tiny JPEG, optionally stamped with an EXIF date."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (8, 8), colour)

    if taken is None:
        image.save(path)
        return path

    exif = Image.Exif()
    if tag == DATETIME:
        exif[DATETIME] = exif_timestamp(taken)
    else:
        exif[EXIF_IFD] = {tag: exif_timestamp(taken)}
    image.save(path, exif=exif)
    return path


@pytest.fixture
def jpeg_factory(tmp_path: Path):
    """Create JPEGs inside the test's temporary folder."""

    def _factory(
        name: str,
        taken: datetime | None = None,
        *,
        tag: int = DATETIME_ORIGINAL,
        colour: str = "red",
        root: Path | None = None,
    ) -> Path:
        return write_jpeg(
            (root or tmp_path) / name, taken, tag=tag, colour=colour
        )

    return _factory


@pytest.fixture
def photo_folder(tmp_path: Path, jpeg_factory) -> Path:
    """A realistic unsorted folder: mixed naming, mixed months, some undated."""
    jpeg_factory("IMG_0001.JPG", datetime(2023, 5, 14, 12, 30, 45))
    jpeg_factory("DSC_9987.jpg", datetime(2023, 5, 2, 8, 0, 0))
    jpeg_factory("holiday-beach.jpeg", datetime(2023, 6, 20, 17, 5, 0))
    jpeg_factory("_MG_4410.jpg", datetime(2021, 12, 31, 23, 59, 0))
    jpeg_factory("no_exif_at_all.jpg", None)
    (tmp_path / "notes.txt").write_text("not an image")
    return tmp_path
