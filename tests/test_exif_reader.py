"""Tests for EXIF timestamp parsing and the backend chain."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sort_images.exif_reader import (
    ExifDate,
    parse_exif_datetime,
    read_capture_date,
)
from tests.conftest import DATETIME, DATETIME_DIGITIZED, DATETIME_ORIGINAL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2023:05:14 12:30:45", datetime(2023, 5, 14, 12, 30, 45)),
        ("2023-05-14 12:30:45", datetime(2023, 5, 14, 12, 30, 45)),
        ("2023-05-14T12:30:45", datetime(2023, 5, 14, 12, 30, 45)),
        ("2023:05:14", datetime(2023, 5, 14, 0, 0, 0)),
        ("2023:05:14 12:30", datetime(2023, 5, 14, 12, 30, 0)),
        # Subsecond and timezone suffixes are tolerated and ignored.
        ("2023:05:14 12:30:45.123", datetime(2023, 5, 14, 12, 30, 45)),
        ("2023:05:14 12:30:45+05:30", datetime(2023, 5, 14, 12, 30, 45)),
        ("  2023:05:14 12:30:45  ", datetime(2023, 5, 14, 12, 30, 45)),
    ],
)
def test_parses_valid_timestamps(raw: str, expected: datetime) -> None:
    assert parse_exif_datetime(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "not a date",
        "0000:00:00 00:00:00",   # camera clock never set
        "2023:13:01 00:00:00",   # month 13
        "2023:02:30 00:00:00",   # 30th of February
        "2023:00:14 00:00:00",   # month 0
        "1500:05:14 00:00:00",   # before photography existed
        "9999:05:14 00:00:00",   # implausible future
    ],
)
def test_rejects_unusable_timestamps(raw: object) -> None:
    assert parse_exif_datetime(raw) is None


def test_reads_datetime_original_from_jpeg(jpeg_factory) -> None:
    taken = datetime(2023, 5, 14, 12, 30, 45)
    path = jpeg_factory("photo.jpg", taken)

    result = read_capture_date(path)

    assert isinstance(result, ExifDate)
    assert result.value == taken
    assert "DateTimeOriginal" in result.tag


def test_falls_back_to_lower_priority_tag(jpeg_factory) -> None:
    """A file carrying only DateTime still yields a date."""
    taken = datetime(2019, 3, 8, 9, 15, 0)
    path = jpeg_factory("legacy.jpg", taken, tag=DATETIME)

    result = read_capture_date(path)

    assert result is not None
    assert result.value == taken


def test_datetime_digitized_is_read(jpeg_factory) -> None:
    taken = datetime(2020, 7, 4, 18, 0, 0)
    path = jpeg_factory("digitized.jpg", taken, tag=DATETIME_DIGITIZED)

    result = read_capture_date(path)

    assert result is not None
    assert result.value == taken


def test_image_without_exif_returns_none(jpeg_factory) -> None:
    path = jpeg_factory("bare.jpg", None)
    assert read_capture_date(path) is None


def test_corrupt_file_returns_none_instead_of_raising(tmp_path: Path) -> None:
    """One unreadable file must never abort a whole run."""
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)  # JPEG header, junk body

    assert read_capture_date(broken) is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert read_capture_date(tmp_path / "does_not_exist.jpg") is None


def test_datetime_original_wins_over_datetime(jpeg_factory) -> None:
    """DateTimeOriginal outranks the editable DateTime tag."""
    from PIL import Image

    from tests.conftest import EXIF_IFD, exif_timestamp

    path = jpeg_factory("both.jpg", None)
    exif = Image.Exif()
    exif[DATETIME] = exif_timestamp(datetime(2024, 1, 1, 0, 0, 0))
    exif[EXIF_IFD] = {
        DATETIME_ORIGINAL: exif_timestamp(datetime(2023, 5, 14, 12, 30, 45))
    }
    Image.new("RGB", (8, 8), "blue").save(path, exif=exif)

    result = read_capture_date(path)

    assert result is not None
    assert result.value == datetime(2023, 5, 14, 12, 30, 45)
