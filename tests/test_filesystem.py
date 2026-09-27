"""Tests for detecting what a filesystem will let us do.

Read-only volumes are simulated two ways: by removing write permission from a
directory (the real behaviour of an unwritable folder) and by faking the mount
flag (the real behaviour of a read-only NTFS mount). Neither test needs an
actual external drive.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from sort_images import filesystem
from sort_images.filesystem import (
    check_writable,
    is_read_only_mount,
    nearest_existing_ancestor,
)

running_as_root = os.geteuid() == 0
skip_if_root = pytest.mark.skipif(
    running_as_root, reason="root bypasses permission checks"
)


def test_writable_folder_is_reported_writable(tmp_path: Path) -> None:
    state = check_writable(tmp_path)

    assert state.writable is True
    assert bool(state) is True
    assert state.reason == ""


def test_probe_file_is_cleaned_up(tmp_path: Path) -> None:
    """The check must not leave litter behind."""
    before = set(tmp_path.iterdir())

    check_writable(tmp_path)

    assert set(tmp_path.iterdir()) == before


@skip_if_root
def test_unwritable_folder_is_detected(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        state = check_writable(locked)

        assert state.writable is False
        assert bool(state) is False
        assert "permission" in state.reason.lower()
    finally:
        locked.chmod(0o755)


def test_read_only_filesystem_is_named_as_such(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EROFS must be reported as read-only, not as a generic error."""

    def _refuse(*args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    monkeypatch.setattr(filesystem.tempfile, "NamedTemporaryFile", _refuse)

    state = check_writable(tmp_path)

    assert state.writable is False
    assert state.reason == "read-only filesystem"
    assert state.read_only_mount is True


def test_out_of_space_is_named_as_such(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse(*args, **kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(filesystem.tempfile, "NamedTemporaryFile", _refuse)

    assert check_writable(tmp_path).reason == "no space left on device"


def test_unexpected_errors_are_still_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse(*args, **kwargs):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(filesystem.tempfile, "NamedTemporaryFile", _refuse)

    state = check_writable(tmp_path)

    assert state.writable is False
    assert "Input/output error" in state.reason


def test_writability_of_a_folder_yet_to_be_created(tmp_path: Path) -> None:
    """An output folder is created on demand, so its parent is what matters."""
    future = tmp_path / "does" / "not" / "exist" / "yet"

    assert check_writable(future).writable is True


def test_nearest_existing_ancestor_finds_the_real_parent(tmp_path: Path) -> None:
    future = tmp_path / "a" / "b" / "c"

    assert nearest_existing_ancestor(future) == tmp_path


def test_nearest_existing_ancestor_of_an_existing_path_is_itself(
    tmp_path: Path,
) -> None:
    assert nearest_existing_ancestor(tmp_path) == tmp_path


def test_normal_volume_is_not_a_read_only_mount(tmp_path: Path) -> None:
    assert is_read_only_mount(tmp_path) is False


def test_read_only_mount_flag_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Stat:
        f_flag = os.ST_RDONLY

    monkeypatch.setattr(filesystem.os, "statvfs", lambda path: _Stat())

    assert is_read_only_mount(tmp_path) is True


def test_mount_check_survives_a_failing_statvfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _explode(path):
        raise OSError("statvfs not supported here")

    monkeypatch.setattr(filesystem.os, "statvfs", _explode)

    assert is_read_only_mount(tmp_path) is False
