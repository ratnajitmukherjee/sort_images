"""Tests for applying a plan safely to the filesystem."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sort_images.date_source import DateOrigin, FallbackPolicy, ResolvedDate
from sort_images.executor import (
    Outcome,
    execute_plan,
    file_digest,
    files_are_identical,
)
from sort_images.planner import ActionKind, PlannedAction, build_plan

TAKEN = datetime(2023, 5, 14, 12, 30, 45)


def _resolver(path: Path, policy: FallbackPolicy) -> ResolvedDate:
    return ResolvedDate(value=TAKEN, origin=DateOrigin.EXIF, detail="test")


def _plan_for(paths, root: Path, copy: bool = False):
    return build_plan(paths, root, copy=copy, resolver=_resolver)


def test_moves_file_into_year_month_folder(tmp_path: Path, jpeg_factory) -> None:
    source = jpeg_factory("IMG_0001.jpg", TAKEN)

    report = execute_plan(_plan_for([source], tmp_path))

    assert report.count(Outcome.MOVED) == 1
    assert (tmp_path / "2023-05" / "IMG_0001.jpg").is_file()
    assert not source.exists()


def test_dry_run_changes_nothing(tmp_path: Path, jpeg_factory) -> None:
    source = jpeg_factory("IMG_0001.jpg", TAKEN)

    report = execute_plan(_plan_for([source], tmp_path), dry_run=True)

    assert report.dry_run is True
    assert report.count(Outcome.MOVED) == 1          # reports what it would do
    assert source.exists()                            # but nothing moved
    assert not (tmp_path / "2023-05").exists()


def test_copy_leaves_the_original_in_place(tmp_path: Path, jpeg_factory) -> None:
    source = jpeg_factory("IMG_0001.jpg", TAKEN)

    report = execute_plan(_plan_for([source], tmp_path, copy=True))

    assert report.count(Outcome.COPIED) == 1
    assert source.exists()
    assert (tmp_path / "2023-05" / "IMG_0001.jpg").is_file()


def test_identical_file_at_destination_is_reported_as_duplicate(
    tmp_path: Path, jpeg_factory
) -> None:
    """Re-running over a partly sorted folder must not create copies."""
    source = jpeg_factory("IMG_0001.jpg", TAKEN)
    already = tmp_path / "2023-05" / "IMG_0001.jpg"
    already.parent.mkdir()
    already.write_bytes(source.read_bytes())

    report = execute_plan(_plan_for([source], tmp_path))

    assert report.count(Outcome.DUPLICATE) == 1
    assert source.exists()                            # left untouched
    assert not (tmp_path / "2023-05" / "IMG_0001_1.jpg").exists()


def test_different_file_with_same_name_is_never_overwritten(
    tmp_path: Path, jpeg_factory
) -> None:
    source = jpeg_factory("IMG_0001.jpg", TAKEN, colour="red")
    existing = tmp_path / "2023-05" / "IMG_0001.jpg"
    existing.parent.mkdir()
    jpeg_factory("IMG_0001.jpg", TAKEN, colour="blue", root=existing.parent)
    original_bytes = existing.read_bytes()

    report = execute_plan(_plan_for([source], tmp_path))

    assert report.count(Outcome.MOVED) == 1
    assert existing.read_bytes() == original_bytes    # untouched
    assert (tmp_path / "2023-05" / "IMG_0001_1.jpg").is_file()


def test_skip_action_is_reported_as_skipped(tmp_path: Path, jpeg_factory) -> None:
    source = jpeg_factory("IMG_0001.jpg", TAKEN, root=tmp_path / "2023-05")

    report = execute_plan(_plan_for([source], tmp_path))

    assert report.count(Outcome.SKIPPED) == 1
    assert source.exists()


def test_failure_is_recorded_and_run_continues(
    tmp_path: Path, jpeg_factory
) -> None:
    """A vanished source must not abort the remaining files."""
    good = jpeg_factory("good.jpg", TAKEN)
    missing = tmp_path / "gone.jpg"

    plan = (
        PlannedAction(
            source=missing,
            destination=tmp_path / "2023-05" / "gone.jpg",
            kind=ActionKind.MOVE,
            folder="2023-05",
            resolved=ResolvedDate(value=TAKEN, origin=DateOrigin.EXIF),
        ),
        *_plan_for([good], tmp_path),
    )
    report = execute_plan(plan)

    assert report.count(Outcome.FAILED) == 1
    assert report.count(Outcome.MOVED) == 1
    assert (tmp_path / "2023-05" / "good.jpg").is_file()
    assert report.failed[0].action.source == missing


def test_dry_run_and_live_run_agree_on_collision_names(
    tmp_path: Path, jpeg_factory
) -> None:
    """Two same-named sources must get the same names in both modes."""
    sources = [
        jpeg_factory("IMG_0001.jpg", TAKEN, root=tmp_path / "a"),
        jpeg_factory("IMG_0001.jpg", TAKEN, root=tmp_path / "b"),
    ]
    plan = _plan_for(sources, tmp_path)

    dry = execute_plan(plan, dry_run=True)
    live = execute_plan(plan)

    dry_names = [r.final_destination.name for r in dry.results]
    live_names = [r.final_destination.name for r in live.results]
    assert dry_names == live_names == ["IMG_0001.jpg", "IMG_0001_1.jpg"]


def test_identical_files_are_detected(tmp_path: Path, jpeg_factory) -> None:
    a = jpeg_factory("a.jpg", TAKEN, colour="red")
    b = tmp_path / "b.jpg"
    b.write_bytes(a.read_bytes())
    c = jpeg_factory("c.jpg", TAKEN, colour="blue")

    assert files_are_identical(a, b) is True
    assert files_are_identical(a, c) is False
    assert file_digest(a) == file_digest(b)


def test_comparison_with_missing_file_is_false(
    tmp_path: Path, jpeg_factory
) -> None:
    a = jpeg_factory("a.jpg", TAKEN)
    assert files_are_identical(a, tmp_path / "nope.jpg") is False


def test_copy_survives_a_filesystem_that_rejects_metadata(
    tmp_path: Path, jpeg_factory, monkeypatch
) -> None:
    """Copying off NTFS can reject copystat; the photo still arrived.

    Reporting FAILED here would tell the user their photo did not copy, when
    in fact only the timestamp was lost.
    """
    import shutil as shutil_module

    from sort_images import executor as executor_module

    source = jpeg_factory("IMG_0001.jpg", TAKEN)

    def _refuse_metadata(*args, **kwargs):
        raise OSError("[Errno 45] Operation not supported")

    monkeypatch.setattr(executor_module.shutil, "copystat", _refuse_metadata)

    report = execute_plan(_plan_for([source], tmp_path, copy=True))

    assert report.count(Outcome.COPIED) == 1
    assert report.count(Outcome.FAILED) == 0
    copied = tmp_path / "2023-05" / "IMG_0001.jpg"
    assert copied.is_file()
    assert copied.read_bytes() == source.read_bytes()
    assert "not preserved" in report.results[0].message
    assert shutil_module is not None  # import kept meaningful


def test_copy_preserves_metadata_when_the_filesystem_allows_it(
    tmp_path: Path, jpeg_factory
) -> None:
    source = jpeg_factory("IMG_0001.jpg", TAKEN)
    import os

    stamp = datetime(2022, 9, 1, 10, 0, 0).timestamp()
    os.utime(source, (stamp, stamp))

    report = execute_plan(_plan_for([source], tmp_path, copy=True))

    copied = tmp_path / "2023-05" / "IMG_0001.jpg"
    assert report.count(Outcome.COPIED) == 1
    assert report.results[0].message == ""
    assert copied.stat().st_mtime == pytest.approx(stamp, abs=1)


def test_empty_plan_produces_empty_report() -> None:
    report = execute_plan(())
    assert report.results == ()
    assert report.count(Outcome.MOVED) == 0
