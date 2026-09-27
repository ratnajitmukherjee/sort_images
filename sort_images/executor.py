"""Apply a plan to the filesystem, without ever destroying data.

Three rules govern every write:

* An existing file is never overwritten.
* If the destination already holds a byte-identical file, the source is left
  alone and reported as a duplicate rather than being copied twice.
* A failure on one file is recorded and the run continues; one unreadable photo
  does not abort the batch.

``dry_run`` walks the identical code path but stops short of mutating anything,
so what it prints is what a real run would do.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .planner import ActionKind, PlannedAction
from .progress import ProgressFactory

#: Chunk size for duplicate detection.
_HASH_CHUNK_BYTES = 1024 * 1024


class Outcome(str, Enum):
    """What actually happened to a file."""

    MOVED = "moved"
    COPIED = "copied"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExecutedAction:
    """The result of applying one planned action."""

    action: PlannedAction
    outcome: Outcome
    final_destination: Path | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """Everything that happened during a run."""

    results: tuple[ExecutedAction, ...]
    dry_run: bool

    def by_outcome(self, outcome: Outcome) -> tuple[ExecutedAction, ...]:
        return tuple(r for r in self.results if r.outcome is outcome)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for r in self.results if r.outcome is outcome)

    @property
    def failed(self) -> tuple[ExecutedAction, ...]:
        return self.by_outcome(Outcome.FAILED)


def file_digest(path: Path, chunk_size: int = _HASH_CHUNK_BYTES) -> str:
    """Return the SHA-256 hex digest of ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def files_are_identical(left: Path, right: Path) -> bool:
    """True when both paths hold the same bytes.

    Sizes are compared first, which rejects the overwhelming majority of
    non-duplicates without reading a single byte of content.
    """
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        return file_digest(left) == file_digest(right)
    except OSError:
        return False


def copy_with_metadata(source: Path, destination: Path) -> str:
    """Copy the data, then make a best effort at timestamps and permissions.

    Returns a note when the metadata step failed. Copying off a foreign
    filesystem -- an NTFS drive onto APFS, say -- can reject that step even
    though the image itself landed intact. Losing a timestamp is a caveat worth
    reporting, not a reason to call the copy a failure and leave the user
    thinking the photo did not arrive.
    """
    shutil.copyfile(source, destination)
    try:
        shutil.copystat(source, destination)
    except OSError as error:
        return (
            "copied, but timestamps/permissions were not preserved "
            f"({error.strerror or error})"
        )
    return ""


def _resolve_conflict(
    destination: Path, reserved: set[Path]
) -> tuple[Path, bool]:
    """Find a free destination path.

    Returns ``(path, renamed)``. ``reserved`` tracks names handed out earlier in
    this run so dry-run and live runs agree even before files exist on disk.
    """
    if destination not in reserved and not destination.exists():
        return destination, False

    stem, suffix = destination.stem, destination.suffix
    counter = 1
    while True:
        candidate = destination.with_name(f"{stem}_{counter}{suffix}")
        if candidate not in reserved and not candidate.exists():
            return candidate, True
        counter += 1


def _apply_one(
    action: PlannedAction, reserved: set[Path], dry_run: bool
) -> ExecutedAction:
    """Apply a single action, translating any failure into a FAILED result."""
    if action.kind is ActionKind.SKIP:
        return ExecutedAction(
            action=action,
            outcome=Outcome.SKIPPED,
            final_destination=action.source,
            message=action.reason,
        )

    # An identical file already parked at the destination means this photo has
    # been sorted before -- most likely a re-run over a partly sorted folder.
    if action.destination.exists() and files_are_identical(
        action.source, action.destination
    ):
        return ExecutedAction(
            action=action,
            outcome=Outcome.DUPLICATE,
            final_destination=action.destination,
            message="identical file already present at destination",
        )

    destination, renamed = _resolve_conflict(action.destination, reserved)
    reserved.add(destination)

    if dry_run:
        return ExecutedAction(
            action=action,
            outcome=Outcome.MOVED
            if action.kind is ActionKind.MOVE
            else Outcome.COPIED,
            final_destination=destination,
            message="renamed to avoid overwriting an existing file"
            if renamed
            else "",
        )

    note = ""
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if action.kind is ActionKind.COPY:
            note = copy_with_metadata(action.source, destination)
            outcome = Outcome.COPIED
        else:
            shutil.move(str(action.source), str(destination))
            outcome = Outcome.MOVED
    except (OSError, shutil.Error) as error:
        return ExecutedAction(
            action=action,
            outcome=Outcome.FAILED,
            final_destination=None,
            message=str(error),
        )

    notes = [
        text
        for text in (
            "renamed to avoid overwriting an existing file" if renamed else "",
            note,
        )
        if text
    ]
    return ExecutedAction(
        action=action,
        outcome=outcome,
        final_destination=destination,
        message="; ".join(notes),
    )


def execute_plan(
    plan: Iterable[PlannedAction],
    dry_run: bool = False,
    progress: ProgressFactory | None = None,
) -> ExecutionReport:
    """Apply every action in ``plan``, collecting results.

    ``progress`` optionally wraps the iteration so the caller can draw a bar;
    copying a large library is slow enough to be worth watching.
    """
    reserved: set[Path] = set()
    actions = tuple(plan)
    stream = progress(actions) if progress else actions
    results = tuple(_apply_one(action, reserved, dry_run) for action in stream)
    return ExecutionReport(results=results, dry_run=dry_run)
