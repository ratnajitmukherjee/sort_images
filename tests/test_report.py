"""Tests for output formatting."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sort_images.date_source import DateOrigin, FallbackPolicy, ResolvedDate
from sort_images.executor import ExecutionReport, execute_plan
from sort_images.planner import build_plan
from sort_images.report import (
    count_moves,
    format_date_sources,
    format_execution_summary,
    format_plan_summary,
    format_undated_hint,
    format_verbose_lines,
)


def _resolver_for(value: datetime | None):
    def _resolve(path: Path, policy: FallbackPolicy) -> ResolvedDate:
        if value is None:
            return ResolvedDate(value=None)
        return ResolvedDate(value=value, origin=DateOrigin.EXIF, detail="test tag")

    return _resolve


def test_empty_plan_summary(tmp_path: Path) -> None:
    assert format_plan_summary(()) == ["No image files found."]


def test_plan_summary_counts_per_folder(tmp_path: Path) -> None:
    plan = build_plan(
        [tmp_path / "a.jpg", tmp_path / "b.jpg"],
        tmp_path,
        resolver=_resolver_for(datetime(2023, 5, 14)),
    )

    text = "\n".join(format_plan_summary(plan))

    assert "2023-05" in text
    assert "2 file(s)" in text


def test_undated_sorts_last(tmp_path: Path) -> None:
    dated = build_plan(
        [tmp_path / "a.jpg"], tmp_path, resolver=_resolver_for(datetime(2023, 5, 1))
    )
    undated = build_plan(
        [tmp_path / "b.jpg"], tmp_path, resolver=_resolver_for(None)
    )

    lines = format_plan_summary(dated + undated)

    assert "undated" in lines[-1]


def test_date_sources_are_reported(tmp_path: Path) -> None:
    plan = build_plan(
        [tmp_path / "a.jpg"], tmp_path, resolver=_resolver_for(datetime(2023, 5, 1))
    )

    text = "\n".join(format_date_sources(plan))

    assert "exif" in text


def test_date_sources_of_empty_plan_is_empty() -> None:
    assert format_date_sources(()) == []


def test_undated_hint_suppressed_when_fallbacks_enabled(tmp_path: Path) -> None:
    plan = build_plan([tmp_path / "a.jpg"], tmp_path, resolver=_resolver_for(None))

    assert format_undated_hint(plan, fallbacks_enabled=True) == []
    assert format_undated_hint(plan, fallbacks_enabled=False) != []


def test_undated_hint_absent_when_everything_is_dated(tmp_path: Path) -> None:
    plan = build_plan(
        [tmp_path / "a.jpg"], tmp_path, resolver=_resolver_for(datetime(2023, 5, 1))
    )

    assert format_undated_hint(plan, fallbacks_enabled=False) == []


def test_summary_of_nothing_to_do() -> None:
    text = "\n".join(format_execution_summary(ExecutionReport((), dry_run=False)))
    assert "nothing to do" in text


def test_summary_flags_dry_run() -> None:
    text = "\n".join(format_execution_summary(ExecutionReport((), dry_run=True)))
    assert "Dry run" in text


def test_summary_lists_failures(tmp_path: Path) -> None:
    plan = build_plan(
        [tmp_path / "vanished.jpg"],
        tmp_path,
        resolver=_resolver_for(datetime(2023, 5, 1)),
    )
    report = execute_plan(plan)

    text = "\n".join(format_execution_summary(report))

    assert "Failures:" in text
    assert "vanished.jpg" in text


def test_verbose_lines_cover_moves_and_skips(
    tmp_path: Path, jpeg_factory
) -> None:
    moved = jpeg_factory("moving.jpg", datetime(2023, 5, 14))
    skipped = jpeg_factory("staying.jpg", datetime(2023, 5, 14), root=tmp_path / "2023-05")
    plan = build_plan(
        [moved, skipped], tmp_path, resolver=_resolver_for(datetime(2023, 5, 14))
    )
    report = execute_plan(plan, dry_run=True)

    text = "\n".join(format_verbose_lines(report, tmp_path))

    assert "moving.jpg  ->  2023-05/moving.jpg" in text
    assert "skip" in text
    assert "test tag" in text


def test_verbose_handles_paths_outside_root(tmp_path: Path) -> None:
    """Paths that are not under the scan root are shown in full."""
    outside = tmp_path.parent / "elsewhere.jpg"
    plan = build_plan(
        [outside], tmp_path, resolver=_resolver_for(datetime(2023, 5, 1))
    )
    report = execute_plan(plan, dry_run=True)

    text = "\n".join(format_verbose_lines(report, tmp_path))

    assert "elsewhere.jpg" in text


def test_count_moves_excludes_skips(tmp_path: Path, jpeg_factory) -> None:
    moved = jpeg_factory("moving.jpg", datetime(2023, 5, 14))
    skipped = jpeg_factory(
        "staying.jpg", datetime(2023, 5, 14), root=tmp_path / "2023-05"
    )
    plan = build_plan(
        [moved, skipped], tmp_path, resolver=_resolver_for(datetime(2023, 5, 14))
    )

    assert count_moves(plan) == 1
