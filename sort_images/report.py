"""Render human-readable output for a run.

Formatting is kept separate from doing the work, and every function returns a
list of lines rather than printing, so output is straightforward to assert on
in tests.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .date_source import DateOrigin
from .discovery import UNDATED_DIR_NAME
from .executor import ExecutionReport, Outcome
from .planner import ActionKind, PlannedAction

_OUTCOME_ORDER = (
    Outcome.MOVED,
    Outcome.COPIED,
    Outcome.DUPLICATE,
    Outcome.SKIPPED,
    Outcome.FAILED,
)


def _relative(path: Path, root: Path) -> str:
    """Show paths relative to the scanned folder when possible."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def format_plan_summary(plan: tuple[PlannedAction, ...]) -> list[str]:
    """Show how many files land in each destination folder."""
    if not plan:
        return ["No image files found."]

    counts = Counter(action.folder for action in plan)
    # Undated always sorts last; real months sort chronologically.
    folders = sorted(counts, key=lambda name: (name == UNDATED_DIR_NAME, name))

    width = max(len(name) for name in folders)
    lines = ["", "Destination folders:"]
    lines += [
        f"  {name:<{width}}  {counts[name]:>5} file(s)" for name in folders
    ]
    return lines


def format_date_sources(plan: tuple[PlannedAction, ...]) -> list[str]:
    """Report which source supplied each date, so a run stays auditable."""
    counts = Counter(
        action.resolved.origin.value if action.resolved.origin else "none"
        for action in plan
    )
    if not counts:
        return []

    rows = [
        (origin.value if origin else "no date found", counts[key])
        for origin, key in (
            *((origin, origin.value) for origin in DateOrigin),
            (None, "none"),
        )
        if counts.get(key)
    ]
    if not rows:
        return []

    width = max(len(label) for label, _ in rows)
    return ["", "Dates came from:"] + [
        f"  {label:<{width}}  {count:>5} file(s)" for label, count in rows
    ]


def format_verbose_lines(
    report: ExecutionReport, input_root: Path, output_root: Path | None = None
) -> list[str]:
    """One line per file, showing where it went and why.

    Sources are shown relative to the input folder and destinations relative to
    the output folder, so the two stay readable even when they differ.
    """
    output_root = output_root or input_root
    lines: list[str] = []
    for result in report.results:
        action = result.action
        source = _relative(action.source, input_root)

        if result.outcome is Outcome.SKIPPED:
            lines.append(f"  skip      {source}  ({result.message})")
            continue

        destination = (
            _relative(result.final_destination, output_root)
            if result.final_destination
            else "-"
        )
        detail = action.resolved.detail
        suffix = f"  [{detail}]" if detail else ""
        note = f"  ({result.message})" if result.message else ""
        lines.append(
            f"  {result.outcome.value:<9} {source}  ->  {destination}{suffix}{note}"
        )
    return lines


def format_execution_summary(report: ExecutionReport) -> list[str]:
    """Totals per outcome, plus any failures spelled out."""
    lines = ["", "Summary:"]
    for outcome in _OUTCOME_ORDER:
        count = report.count(outcome)
        if count:
            lines.append(f"  {outcome.value:<10}  {count:>5}")

    if not any(report.count(o) for o in _OUTCOME_ORDER):
        lines.append("  nothing to do")

    failures = report.failed
    if failures:
        lines += ["", "Failures:"]
        lines += [
            f"  {failure.action.source.name}: {failure.message}"
            for failure in failures
        ]

    if report.dry_run:
        lines += [
            "",
            "Dry run -- nothing was changed. Re-run without --dry-run to apply.",
        ]
    return lines


def format_undated_hint(
    plan: tuple[PlannedAction, ...], fallbacks_enabled: bool
) -> list[str]:
    """Nudge toward the fallback flags when EXIF alone left files undated."""
    undated = sum(1 for action in plan if action.is_undated)
    if not undated or fallbacks_enabled:
        return []
    return [
        "",
        f"{undated} file(s) had no EXIF capture date and went to "
        f"'{UNDATED_DIR_NAME}'.",
        "  Try --fallback-filename and/or --fallback-mtime to place them.",
    ]


def count_moves(plan: tuple[PlannedAction, ...]) -> int:
    """Number of files the plan would actually relocate."""
    return sum(1 for action in plan if action.kind is not ActionKind.SKIP)
