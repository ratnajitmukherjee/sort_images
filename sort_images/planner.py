"""Turn a list of files into an immutable plan of where each one should go.

The planner performs no filesystem writes. It decides destinations only; the
executor applies them. That split is what makes ``--dry-run`` trustworthy --
the exact same plan is built either way, and dry-run simply stops before the
executor touches anything.

Disk-level collisions are intentionally *not* resolved here. Only the executor
knows the state of the filesystem at write time, so it owns that decision.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from .date_source import FallbackPolicy, ResolvedDate, resolve_date
from .discovery import UNDATED_DIR_NAME
from .progress import ProgressFactory

DateResolver = Callable[[Path, FallbackPolicy], ResolvedDate]


class ActionKind(str, Enum):
    """What the executor should do with a planned file."""

    MOVE = "move"
    COPY = "copy"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class PlannedAction:
    """One file's fate. Immutable: planning never rewrites a decision."""

    source: Path
    destination: Path
    kind: ActionKind
    folder: str
    resolved: ResolvedDate
    reason: str = ""

    @property
    def is_undated(self) -> bool:
        return self.folder == UNDATED_DIR_NAME


def folder_for_date(value: datetime) -> str:
    """Return the ``YYYY-MM`` folder name for a timestamp."""
    return f"{value.year:04d}-{value.month:02d}"


def _unique_within_plan(destination: Path, claimed: set[Path]) -> Path:
    """Disambiguate two source files that would land on the same name.

    Only guards against collisions *inside this plan* (common when scanning
    recursively, where several folders each hold an ``IMG_0001.JPG``).
    """
    if destination not in claimed:
        return destination

    stem, suffix = destination.stem, destination.suffix
    counter = 1
    while True:
        candidate = destination.with_name(f"{stem}_{counter}{suffix}")
        if candidate not in claimed:
            return candidate
        counter += 1


def build_plan(
    files: Iterable[Path],
    output_root: Path,
    *,
    policy: FallbackPolicy | None = None,
    copy: bool = False,
    resolver: DateResolver = resolve_date,
    progress: ProgressFactory | None = None,
) -> tuple[PlannedAction, ...]:
    """Build the full set of actions placing ``files`` under ``output_root``.

    ``output_root`` is where the ``YYYY-MM`` folders are created. It may be the
    same folder the files came from (sorting in place) or a separate one.

    ``progress`` optionally wraps the iteration so the caller can draw a bar --
    this is the slow phase, since every file has to be opened and read.
    """
    policy = policy or FallbackPolicy()
    move_kind = ActionKind.COPY if copy else ActionKind.MOVE

    actions: list[PlannedAction] = []
    claimed: set[Path] = set()

    sources = tuple(files)
    for source in progress(sources) if progress else sources:
        resolved = resolver(source, policy)
        folder = (
            folder_for_date(resolved.value)
            if resolved.value is not None
            else UNDATED_DIR_NAME
        )
        ideal = output_root / folder / source.name

        # Already sitting in the right folder -- leave it untouched so repeat
        # runs are idempotent.
        if source.parent == ideal.parent:
            actions.append(
                PlannedAction(
                    source=source,
                    destination=source,
                    kind=ActionKind.SKIP,
                    folder=folder,
                    resolved=resolved,
                    reason="already in the correct folder",
                )
            )
            continue

        destination = _unique_within_plan(ideal, claimed)
        claimed.add(destination)
        actions.append(
            PlannedAction(
                source=source,
                destination=destination,
                kind=move_kind,
                folder=folder,
                resolved=resolved,
                reason="renamed to avoid a clash within this run"
                if destination != ideal
                else "",
            )
        )

    return tuple(actions)


def destination_folders(plan: Iterable[PlannedAction]) -> tuple[Path, ...]:
    """Return the distinct folders the plan needs, sorted for stable output."""
    folders = {
        action.destination.parent
        for action in plan
        if action.kind is not ActionKind.SKIP
    }
    return tuple(sorted(folders))
