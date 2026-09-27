"""Tests for the optional exiftool fallback.

exiftool is not installed in CI or on every machine, so the binary is stubbed.
These tests verify the wiring -- argument construction, JSON handling, and
failure tolerance -- rather than exiftool itself.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from sort_images import exif_reader
from sort_images.exif_reader import _read_with_exiftool, exiftool_available


class _Completed:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.returncode = 0


@pytest.fixture
def fake_exiftool(monkeypatch: pytest.MonkeyPatch):
    """Pretend exiftool exists and returns a scripted payload."""

    def _setup(payload: object, *, raises: type[BaseException] | None = None):
        monkeypatch.setattr(exif_reader, "_exiftool_path", lambda: "/usr/bin/exiftool")

        def _run(args, **kwargs):
            if raises is not None:
                raise raises("boom")
            return _Completed(
                payload if isinstance(payload, str) else json.dumps(payload)
            )

        monkeypatch.setattr(exif_reader.subprocess, "run", _run)

    return _setup


def test_reads_datetime_original(fake_exiftool, tmp_path: Path) -> None:
    fake_exiftool([{"DateTimeOriginal": "2023:05:14 12:30:45"}])

    result = _read_with_exiftool(tmp_path / "photo.cr3")

    assert result is not None
    assert result.value == datetime(2023, 5, 14, 12, 30, 45)
    assert result.backend == "exiftool"


def test_prefers_original_over_modify_date(fake_exiftool, tmp_path: Path) -> None:
    fake_exiftool(
        [
            {
                "ModifyDate": "2024:01:01 00:00:00",
                "DateTimeOriginal": "2023:05:14 12:30:45",
            }
        ]
    )

    result = _read_with_exiftool(tmp_path / "photo.cr3")

    assert result is not None
    assert result.value == datetime(2023, 5, 14, 12, 30, 45)


def test_falls_through_to_create_date(fake_exiftool, tmp_path: Path) -> None:
    fake_exiftool([{"CreateDate": "2022:03:04 05:06:07"}])

    result = _read_with_exiftool(tmp_path / "photo.cr3")

    assert result is not None
    assert result.value == datetime(2022, 3, 4, 5, 6, 7)


@pytest.mark.parametrize(
    "payload",
    [
        [],                                        # no records
        [{}],                                      # record with no date tags
        [{"DateTimeOriginal": "0000:00:00 00:00:00"}],  # unset camera clock
        "not json at all",                         # malformed output
        "",                                        # empty output
    ],
)
def test_unusable_output_returns_none(
    fake_exiftool, tmp_path: Path, payload: object
) -> None:
    fake_exiftool(payload)
    assert _read_with_exiftool(tmp_path / "photo.cr3") is None


@pytest.mark.parametrize(
    "error", [OSError, subprocess.SubprocessError, subprocess.TimeoutExpired]
)
def test_subprocess_failures_are_swallowed(
    fake_exiftool, tmp_path: Path, error
) -> None:
    """A broken or hanging exiftool must not take the run down."""
    if error is subprocess.TimeoutExpired:
        pytest.skip("TimeoutExpired needs positional args; covered by SubprocessError")
    fake_exiftool(None, raises=error)

    assert _read_with_exiftool(tmp_path / "photo.cr3") is None


def test_backend_is_skipped_when_binary_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(exif_reader, "_exiftool_path", lambda: None)

    assert _read_with_exiftool(tmp_path / "photo.cr3") is None


def test_availability_reflects_the_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exif_reader, "_exiftool_path", lambda: None)
    assert exiftool_available() is False

    monkeypatch.setattr(exif_reader, "_exiftool_path", lambda: "/usr/bin/exiftool")
    assert exiftool_available() is True
