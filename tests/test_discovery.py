"""Tests for locating candidate image files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sort_images.discovery import find_images, is_destination_dir


@pytest.mark.parametrize("name", ["2023-05", "1999-12", "2024-01", "undated"])
def test_recognises_its_own_output_folders(tmp_path: Path, name: str) -> None:
    assert is_destination_dir(tmp_path / name) is True


@pytest.mark.parametrize("name", ["holiday", "2023", "2023-5", "May-2023", "raw"])
def test_other_folders_are_not_destinations(tmp_path: Path, name: str) -> None:
    assert is_destination_dir(tmp_path / name) is False


def test_finds_images_and_ignores_other_files(photo_folder: Path) -> None:
    found = find_images(photo_folder)
    names = {path.name for path in found}

    assert "IMG_0001.JPG" in names
    assert "no_exif_at_all.jpg" in names
    assert "notes.txt" not in names
    assert len(found) == 5


def test_hidden_files_are_ignored(tmp_path: Path, jpeg_factory) -> None:
    jpeg_factory("visible.jpg", datetime(2023, 5, 14))
    jpeg_factory(".hidden.jpg", datetime(2023, 5, 14))
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x01")

    assert {p.name for p in find_images(tmp_path)} == {"visible.jpg"}


def test_subfolders_are_skipped_without_recursive(
    tmp_path: Path, jpeg_factory
) -> None:
    jpeg_factory("top.jpg", datetime(2023, 5, 14))
    jpeg_factory("nested.jpg", datetime(2023, 5, 14), root=tmp_path / "sub")

    assert {p.name for p in find_images(tmp_path)} == {"top.jpg"}


def test_recursive_scan_includes_subfolders(tmp_path: Path, jpeg_factory) -> None:
    jpeg_factory("top.jpg", datetime(2023, 5, 14))
    jpeg_factory("nested.jpg", datetime(2023, 5, 14), root=tmp_path / "sub")

    found = {p.name for p in find_images(tmp_path, recursive=True)}
    assert found == {"top.jpg", "nested.jpg"}


def test_recursive_scan_skips_sorted_folders_belonging_to_the_output(
    tmp_path: Path, jpeg_factory
) -> None:
    """Re-running in place over a sorted library must not reshuffle it."""
    jpeg_factory("new.jpg", datetime(2023, 5, 14))
    jpeg_factory("old.jpg", datetime(2021, 1, 2), root=tmp_path / "2021-01")

    found = find_images(tmp_path, recursive=True, output_root=tmp_path)

    assert {p.name for p in found} == {"new.jpg"}


def test_sorted_folders_are_scanned_when_output_is_elsewhere(
    tmp_path: Path, jpeg_factory
) -> None:
    """A sorted library re-filed into a new output must not be skipped."""
    source = tmp_path / "old_library"
    jpeg_factory("old.jpg", datetime(2021, 1, 2), root=source / "2021-01")

    found = find_images(
        source, recursive=True, output_root=tmp_path / "new_library"
    )

    assert {p.name for p in found} == {"old.jpg"}


def test_output_folder_nested_in_input_is_never_scanned(
    tmp_path: Path, jpeg_factory
) -> None:
    """Otherwise a run would immediately re-process what it just wrote."""
    jpeg_factory("fresh.jpg", datetime(2023, 5, 14))
    jpeg_factory("already.jpg", datetime(2023, 5, 14), root=tmp_path / "sorted" / "2023-05")

    found = find_images(
        tmp_path, recursive=True, output_root=tmp_path / "sorted"
    )

    assert {p.name for p in found} == {"fresh.jpg"}


def test_without_an_output_root_nothing_is_skipped(
    tmp_path: Path, jpeg_factory
) -> None:
    jpeg_factory("new.jpg", datetime(2023, 5, 14))
    jpeg_factory("old.jpg", datetime(2021, 1, 2), root=tmp_path / "2021-01")

    found = find_images(tmp_path, recursive=True)

    assert {p.name for p in found} == {"new.jpg", "old.jpg"}


@pytest.mark.parametrize(
    "name",
    [
        "System Volume Information",
        "$RECYCLE.BIN",
        "$Recycle.Bin",
        "RECYCLER",
        "FOUND.000",
        "@eaDir",
        ".Trashes",
        ".Spotlight-V100",
    ],
)
def test_windows_and_nas_bookkeeping_folders_are_skipped(
    tmp_path: Path, jpeg_factory, name: str
) -> None:
    """An NTFS drive exposes these in plain sight; they hold no photographs."""
    jpeg_factory("real.jpg", datetime(2023, 5, 14))
    jpeg_factory("junk.jpg", datetime(2023, 5, 14), root=tmp_path / name)

    found = find_images(tmp_path, recursive=True, output_root=tmp_path)

    assert {p.name for p in found} == {"real.jpg"}


def test_system_folder_matching_ignores_case(tmp_path: Path) -> None:
    from sort_images.discovery import is_system_dir

    assert is_system_dir(tmp_path / "system volume information") is True
    assert is_system_dir(tmp_path / "SYSTEM VOLUME INFORMATION") is True
    assert is_system_dir(tmp_path / "Holiday Photos") is False


def test_missing_folder_raises(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        find_images(tmp_path / "nope")
