"""Tests for the read-only source case: an NTFS drive mounted on macOS.

macOS mounts NTFS read-only without a third-party driver, which breaks a run
two different ways. Both must be caught before the scan, not one file at a
time afterwards.
"""

from __future__ import annotations

import errno
import os
from datetime import datetime
from pathlib import Path

import pytest

from sort_images import cli, filesystem
from sort_images.cli import EXIT_FAILURES, EXIT_OK, check_filesystems, main

skip_if_root = pytest.mark.skipif(
    os.geteuid() == 0, reason="root bypasses permission checks"
)


@pytest.fixture
def read_only_everywhere(monkeypatch: pytest.MonkeyPatch):
    """Make every writability probe report a read-only filesystem."""

    def _refuse(*args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    monkeypatch.setattr(filesystem.tempfile, "NamedTemporaryFile", _refuse)


@pytest.fixture
def read_only_input(monkeypatch: pytest.MonkeyPatch):
    """Make probes fail only inside a nominated folder."""
    real = filesystem.tempfile.NamedTemporaryFile

    def _factory(locked: Path) -> None:
        def _maybe_refuse(*args, **kwargs):
            target = Path(kwargs.get("dir", "."))
            if target == locked or locked in target.parents:
                raise OSError(errno.EROFS, "Read-only file system")
            return real(*args, **kwargs)

        monkeypatch.setattr(filesystem.tempfile, "NamedTemporaryFile", _maybe_refuse)

    return _factory


def test_sorting_in_place_on_a_read_only_drive_is_refused(
    tmp_path: Path, jpeg_factory, read_only_everywhere,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The default (-o omitted) writes to the source, which cannot work."""
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    exit_code = main(["-i", str(tmp_path), "--yes"])

    assert exit_code == EXIT_FAILURES
    error = capsys.readouterr().err
    assert "cannot write to the output folder" in error
    assert "read-only filesystem" in error
    assert "NTFS" in error
    assert "--copy" in error


def test_moving_off_a_read_only_drive_is_refused(
    tmp_path: Path, jpeg_factory, read_only_input,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Moving unlinks the original, which a read-only volume forbids."""
    source_dir = tmp_path / "ntfs_drive"
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=source_dir)
    read_only_input(source_dir)

    exit_code = main(
        ["-i", str(source_dir), "-o", str(tmp_path / "library"), "--yes"]
    )

    assert exit_code == EXIT_FAILURES
    error = capsys.readouterr().err
    assert "cannot move files out of" in error
    assert "Use --copy" in error


def test_copying_off_a_read_only_drive_is_allowed(
    tmp_path: Path, jpeg_factory, read_only_input
) -> None:
    """--copy never touches the source, so a read-only drive is fine."""
    source_dir = tmp_path / "ntfs_drive"
    dest_dir = tmp_path / "library"
    source = jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=source_dir)
    read_only_input(source_dir)

    exit_code = main(
        ["-i", str(source_dir), "-o", str(dest_dir), "--copy", "--yes"]
    )

    assert exit_code == EXIT_OK
    assert source.is_file()
    assert (dest_dir / "2023-05" / "IMG_0001.jpg").is_file()


def test_dry_run_still_works_on_a_read_only_drive(
    tmp_path: Path, jpeg_factory, read_only_everywhere,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Surveying a read-only drive is useful and writes nothing."""
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    exit_code = main(["-i", str(tmp_path), "--dry-run"])

    assert exit_code == EXIT_OK
    captured = capsys.readouterr()
    assert "warning:" in captured.err
    assert "Continuing anyway" in captured.err
    assert "2023-05" in captured.out


def test_the_check_runs_before_the_scan(
    tmp_path: Path, jpeg_factory, read_only_everywhere,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failing fast is the point: no EXIF reading on a doomed run."""
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    def _should_not_run(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("scanned the drive despite an unwritable output")

    monkeypatch.setattr(cli, "find_images", _should_not_run)

    assert main(["-i", str(tmp_path), "--yes"]) == EXIT_FAILURES


def test_no_problems_reported_for_a_normal_setup(tmp_path: Path) -> None:
    assert check_filesystems(tmp_path, tmp_path, copy_mode=False) == []


def test_copy_mode_does_not_require_a_writable_source(
    tmp_path: Path, read_only_input
) -> None:
    source_dir = tmp_path / "ntfs_drive"
    source_dir.mkdir()
    read_only_input(source_dir)

    problems = check_filesystems(
        source_dir, tmp_path / "library", copy_mode=True
    )

    assert problems == []


@skip_if_root
def test_permission_problems_do_not_mention_ntfs(tmp_path: Path) -> None:
    """The NTFS hint would be misleading for a plain permissions problem."""
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        problems = check_filesystems(tmp_path, locked, copy_mode=True)

        assert len(problems) == 1
        assert "permission denied" in problems[0]
        assert "NTFS" not in problems[0]
    finally:
        locked.chmod(0o755)


def test_suggestion_names_a_writable_destination(
    tmp_path: Path, read_only_everywhere
) -> None:
    """Sorting in place has no useful -o to echo back, so suggest one."""
    problems = check_filesystems(tmp_path, tmp_path, copy_mode=True)

    assert len(problems) == 1
    assert str(tmp_path) in problems[0]
    assert "--copy" in problems[0]
    assert "-o" in problems[0]
