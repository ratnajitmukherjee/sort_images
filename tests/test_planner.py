"""Tests for building the move plan."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sort_images.date_source import DateOrigin, FallbackPolicy, ResolvedDate
from sort_images.planner import (
    ActionKind,
    build_plan,
    destination_folders,
    folder_for_date,
)


def fixed_resolver(value: datetime | None):
    """A resolver that returns the same date for every file."""

    def _resolve(path: Path, policy: FallbackPolicy) -> ResolvedDate:
        if value is None:
            return ResolvedDate(value=None)
        return ResolvedDate(value=value, origin=DateOrigin.EXIF, detail="test")

    return _resolve


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2023, 5, 14), "2023-05"),
        (datetime(2023, 12, 1), "2023-12"),
        (datetime(1999, 1, 31), "1999-01"),
        (datetime(2024, 10, 9), "2024-10"),
    ],
)
def test_folder_names_are_zero_padded(value: datetime, expected: str) -> None:
    assert folder_for_date(value) == expected


def test_plans_move_into_year_month_folder(tmp_path: Path) -> None:
    source = tmp_path / "IMG_0001.jpg"
    plan = build_plan(
        [source], tmp_path, resolver=fixed_resolver(datetime(2023, 5, 14))
    )

    assert len(plan) == 1
    action = plan[0]
    assert action.kind is ActionKind.MOVE
    assert action.folder == "2023-05"
    assert action.destination == tmp_path / "2023-05" / "IMG_0001.jpg"


def test_undated_files_go_to_undated_folder(tmp_path: Path) -> None:
    source = tmp_path / "mystery.jpg"
    plan = build_plan([source], tmp_path, resolver=fixed_resolver(None))

    assert plan[0].folder == "undated"
    assert plan[0].is_undated is True
    assert plan[0].destination == tmp_path / "undated" / "mystery.jpg"


def test_file_already_in_correct_folder_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "2023-05" / "IMG_0001.jpg"
    plan = build_plan(
        [source], tmp_path, resolver=fixed_resolver(datetime(2023, 5, 14))
    )

    assert plan[0].kind is ActionKind.SKIP
    assert plan[0].destination == source


def test_same_name_from_different_folders_is_disambiguated(
    tmp_path: Path,
) -> None:
    """Recursive scans routinely hit several IMG_0001.JPG files."""
    sources = [
        tmp_path / "a" / "IMG_0001.jpg",
        tmp_path / "b" / "IMG_0001.jpg",
        tmp_path / "c" / "IMG_0001.jpg",
    ]
    plan = build_plan(
        sources, tmp_path, resolver=fixed_resolver(datetime(2023, 5, 14))
    )

    destinations = [action.destination.name for action in plan]
    assert destinations == ["IMG_0001.jpg", "IMG_0001_1.jpg", "IMG_0001_2.jpg"]
    assert len(set(destinations)) == 3


def test_copy_mode_produces_copy_actions(tmp_path: Path) -> None:
    plan = build_plan(
        [tmp_path / "a.jpg"],
        tmp_path,
        copy=True,
        resolver=fixed_resolver(datetime(2023, 5, 14)),
    )
    assert plan[0].kind is ActionKind.COPY


def test_destination_folders_are_deduplicated(tmp_path: Path) -> None:
    sources = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    plan = build_plan(
        sources, tmp_path, resolver=fixed_resolver(datetime(2023, 5, 14))
    )

    assert destination_folders(plan) == (tmp_path / "2023-05",)


def test_planning_does_not_touch_the_filesystem(tmp_path: Path) -> None:
    """Planning is pure -- this is what makes --dry-run trustworthy."""
    before = set(tmp_path.iterdir())

    build_plan(
        [tmp_path / "a.jpg"],
        tmp_path,
        resolver=fixed_resolver(datetime(2023, 5, 14)),
    )

    assert set(tmp_path.iterdir()) == before


def test_empty_input_produces_empty_plan(tmp_path: Path) -> None:
    assert build_plan([], tmp_path) == ()
