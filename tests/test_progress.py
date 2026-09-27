"""Tests for the progress bar wrapper.

The bar is cosmetic, so the contract that matters is that it never changes,
drops, or reorders the items flowing through it -- whatever the circumstances.
"""

from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

import pytest

from sort_images.progress import (
    MIN_ITEMS_FOR_BAR,
    iter_with_progress,
    progress_factory,
)


@pytest.mark.parametrize("enabled", [True, False])
def test_all_items_pass_through_unchanged(enabled: bool) -> None:
    items = list(range(50))

    result = list(iter_with_progress(items, description="test", enabled=enabled))

    assert result == items


def test_empty_input_yields_nothing() -> None:
    assert list(iter_with_progress([], description="test")) == []


def test_single_item_skips_the_bar_but_still_yields() -> None:
    """A bar for one file is noise, but the item must still come through."""
    assert list(iter_with_progress(["only"], description="test")) == ["only"]
    assert MIN_ITEMS_FOR_BAR == 2


def test_generators_without_a_length_are_supported() -> None:
    result = list(iter_with_progress((n for n in range(5)), description="test"))
    assert result == [0, 1, 2, 3, 4]


def test_explicit_total_is_honoured() -> None:
    result = list(
        iter_with_progress((n for n in range(5)), description="test", total=5)
    )
    assert result == [0, 1, 2, 3, 4]


def test_falls_back_to_plain_iteration_without_tqdm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing tqdm must degrade to plain iteration, not crash."""
    monkeypatch.setitem(sys.modules, "tqdm", None)

    result = list(iter_with_progress(list(range(10)), description="test"))

    assert result == list(range(10))


def test_bar_is_actually_drawn() -> None:
    """Assert the bar renders, rather than assuming it does."""
    stream = io.StringIO()

    list(iter_with_progress(range(10), description="Reading EXIF", stream=stream))

    drawn = stream.getvalue()
    assert "Reading EXIF" in drawn
    assert "100%" in drawn
    assert "10/10" in drawn


def test_bar_counts_every_item() -> None:
    stream = io.StringIO()

    list(iter_with_progress(range(120), description="Reading EXIF", stream=stream))

    assert "120/120" in stream.getvalue()


def test_disabled_bar_draws_nothing() -> None:
    stream = io.StringIO()

    result = list(
        iter_with_progress(
            range(10), description="test", enabled=False, stream=stream
        )
    )

    assert result == list(range(10))
    assert stream.getvalue() == ""


def test_bar_is_drawn_during_a_real_exif_read(
    tmp_path: Path, jpeg_factory
) -> None:
    """The bar must advance over the phase the user actually waits on."""
    from sort_images.planner import build_plan

    for index in range(5):
        jpeg_factory(f"IMG_{index}.jpg", datetime(2023, 5, index + 1))
    stream = io.StringIO()

    build_plan(
        sorted(tmp_path.glob("*.jpg")),
        tmp_path,
        progress=progress_factory("Reading EXIF", stream=stream),
    )

    drawn = stream.getvalue()
    assert "Reading EXIF" in drawn
    assert "5/5" in drawn


def test_factory_produces_a_working_wrapper() -> None:
    wrap = progress_factory("test")
    assert list(wrap([1, 2, 3])) == [1, 2, 3]


def test_disabled_factory_produces_a_working_wrapper() -> None:
    wrap = progress_factory("test", enabled=False)
    assert list(wrap([1, 2, 3])) == [1, 2, 3]


def test_plan_is_identical_with_and_without_a_bar(
    tmp_path: Path, jpeg_factory
) -> None:
    """Progress reporting must not influence the plan in any way."""
    from sort_images.planner import build_plan

    for index in range(4):
        jpeg_factory(f"IMG_{index}.jpg", datetime(2023, 5, index + 1))
    files = sorted(tmp_path.glob("*.jpg"))

    plain = build_plan(files, tmp_path)
    barred = build_plan(files, tmp_path, progress=progress_factory("x"))

    assert plain == barred


def test_execution_is_identical_with_and_without_a_bar(
    tmp_path: Path, jpeg_factory
) -> None:
    from sort_images.executor import Outcome, execute_plan
    from sort_images.planner import build_plan

    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))
    jpeg_factory("IMG_0002.jpg", datetime(2023, 6, 14))
    plan = build_plan(sorted(tmp_path.glob("*.jpg")), tmp_path)

    report = execute_plan(plan, progress=progress_factory("x"))

    assert report.count(Outcome.MOVED) == 2
    assert (tmp_path / "2023-05" / "IMG_0001.jpg").is_file()
    assert (tmp_path / "2023-06" / "IMG_0002.jpg").is_file()


def test_bar_is_drawn_while_moving_files(tmp_path: Path, jpeg_factory) -> None:
    """The write phase must be watchable, not just the EXIF read."""
    from sort_images.executor import execute_plan
    from sort_images.planner import build_plan

    for index in range(6):
        jpeg_factory(f"IMG_{index}.jpg", datetime(2023, 5, index + 1))
    plan = build_plan(sorted(tmp_path.glob("*.jpg")), tmp_path)
    stream = io.StringIO()

    execute_plan(plan, progress=progress_factory("Moving", stream=stream))

    drawn = stream.getvalue()
    assert "Moving" in drawn
    assert "6/6" in drawn
    assert "100%" in drawn


def test_bar_is_drawn_while_copying_files(tmp_path: Path, jpeg_factory) -> None:
    from sort_images.executor import execute_plan
    from sort_images.planner import build_plan

    source_dir = tmp_path / "card"
    for index in range(4):
        jpeg_factory(f"IMG_{index}.jpg", datetime(2023, 5, index + 1), root=source_dir)
    plan = build_plan(
        sorted(source_dir.glob("*.jpg")), tmp_path / "library", copy=True
    )
    stream = io.StringIO()

    execute_plan(plan, progress=progress_factory("Copying", stream=stream))

    drawn = stream.getvalue()
    assert "Copying" in drawn
    assert "4/4" in drawn


def test_write_bar_advances_once_per_file(tmp_path: Path, jpeg_factory) -> None:
    """Every file must be accounted for, including ones that are skipped."""
    from sort_images.executor import execute_plan
    from sort_images.planner import build_plan

    jpeg_factory("moving.jpg", datetime(2023, 5, 14))
    jpeg_factory("staying.jpg", datetime(2023, 5, 14), root=tmp_path / "2023-05")
    files = sorted(tmp_path.rglob("*.jpg"))
    plan = build_plan(files, tmp_path)
    stream = io.StringIO()

    execute_plan(plan, progress=progress_factory("Moving", stream=stream))

    assert "2/2" in stream.getvalue()
