"""Tests for date resolution: EXIF first, fallbacks only when asked for."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from sort_images.date_source import (
    DateOrigin,
    FallbackPolicy,
    date_from_filename,
    date_from_mtime,
    resolve_date,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("IMG_20230514_123045.jpg", datetime(2023, 5, 14, 12, 30, 45)),
        ("PXL_20230514_123045123.jpg", datetime(2023, 5, 14, 12, 30, 45)),
        ("20230514_123045.jpg", datetime(2023, 5, 14, 12, 30, 45)),
        ("2023-05-14 12.30.45.jpg", datetime(2023, 5, 14, 12, 30, 45)),
        ("2023_05_14.jpg", datetime(2023, 5, 14)),
        ("IMG-20230514-WA0001.jpg", datetime(2023, 5, 14)),
        ("Screenshot 2023-05-14 at 09.11.02.png", datetime(2023, 5, 14, 9, 11, 2)),
        ("signal-2023-05-14-120000.jpg", datetime(2023, 5, 14, 12, 0, 0)),
    ],
)
def test_extracts_iso_dates_from_filenames(name: str, expected: datetime) -> None:
    assert date_from_filename(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "IMG_0001.jpg",              # plain counter
        "DSC_9987.jpg",
        "holiday.jpg",
        "14-05-2023.jpg",            # day-first: ambiguous, deliberately ignored
        "IMG_20231345.jpg",          # month 13
        "IMG_20230532.jpg",          # day 32
        "IMG_15000514.jpg",          # implausible year
        "123456789012.jpg",          # long digit run, not a date
    ],
)
def test_ignores_names_without_an_unambiguous_date(name: str) -> None:
    assert date_from_filename(name) is None


def test_exif_beats_a_contradictory_filename(jpeg_factory) -> None:
    """The whole point of the tool: metadata wins, the name is not trusted.

    A file *named* 2020-01-01 but *shot* on 2023-05-14 belongs in 2023-05.
    """
    path = jpeg_factory("2020-01-01_holiday.jpg", datetime(2023, 5, 14, 12, 30))

    resolved = resolve_date(path, FallbackPolicy(use_filename=True))

    assert resolved.origin is DateOrigin.EXIF
    assert resolved.value == datetime(2023, 5, 14, 12, 30)


def test_filename_fallback_used_only_when_enabled(jpeg_factory) -> None:
    path = jpeg_factory("20230514_123045.jpg", None)

    assert resolve_date(path, FallbackPolicy()).found is False

    resolved = resolve_date(path, FallbackPolicy(use_filename=True))
    assert resolved.origin is DateOrigin.FILENAME
    assert resolved.value == datetime(2023, 5, 14, 12, 30, 45)


def test_mtime_fallback_used_only_when_enabled(jpeg_factory) -> None:
    path = jpeg_factory("undatable.jpg", None)
    stamp = datetime(2022, 9, 1, 10, 0, 0).timestamp()
    os.utime(path, (stamp, stamp))

    assert resolve_date(path, FallbackPolicy()).found is False

    resolved = resolve_date(path, FallbackPolicy(use_mtime=True))
    assert resolved.origin is DateOrigin.MTIME
    assert resolved.value == datetime(2022, 9, 1, 10, 0, 0)


def test_filename_fallback_takes_precedence_over_mtime(jpeg_factory) -> None:
    path = jpeg_factory("20230514_123045.jpg", None)
    stamp = datetime(2022, 9, 1, 10, 0, 0).timestamp()
    os.utime(path, (stamp, stamp))

    resolved = resolve_date(
        path, FallbackPolicy(use_filename=True, use_mtime=True)
    )

    assert resolved.origin is DateOrigin.FILENAME


def test_no_date_when_nothing_is_available(jpeg_factory) -> None:
    path = jpeg_factory("mystery.jpg", None)

    resolved = resolve_date(path, FallbackPolicy())

    assert resolved.found is False
    assert resolved.value is None
    assert resolved.origin is None


def test_mtime_of_missing_file_is_none(tmp_path: Path) -> None:
    assert date_from_mtime(tmp_path / "gone.jpg") is None
