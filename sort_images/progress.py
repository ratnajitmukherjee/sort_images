"""Progress bars for the slow phases.

Reading EXIF means opening every file, and copying means writing every byte, so
both can run for minutes on a large library with nothing on screen. A bar makes
that visible.

The bar is deliberately kept out of the planner and executor: they take a
plain ``progress`` callable, so their logic stays testable without tqdm and the
choice of whether to draw anything belongs to the CLI.

Bars are written to stderr, never stdout, so the report stays pipeable:

    python main.py -i ~/Pictures > report.txt      # bar still visible
    python main.py -i ~/Pictures 2>/dev/null       # bar suppressed
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import TextIO, TypeVar

T = TypeVar("T")

#: A callable that wraps an iterable, optionally decorating it with a bar.
ProgressFactory = Callable[[Iterable[T]], Iterable[T]]

#: Below this many items a bar is more noise than information.
MIN_ITEMS_FOR_BAR = 2


def iter_with_progress(
    items: Iterable[T],
    *,
    description: str,
    total: int | None = None,
    enabled: bool = True,
    stream: TextIO | None = None,
) -> Iterator[T]:
    """Yield every item from ``items``, showing a progress bar when useful.

    Falls back to plain iteration -- yielding exactly the same items -- when
    the bar is switched off, when tqdm is unavailable, or when the output is
    not a terminal. The caller never has to care which happened.

    ``stream`` overrides where the bar is drawn (default: stderr). Passing one
    also forces the bar on, since an explicit destination means the caller
    wants output there; this is what makes the rendering testable.
    """
    if total is None:
        try:
            total = len(items)  # type: ignore[arg-type]
        except TypeError:
            total = None

    if not enabled or (total is not None and total < MIN_ITEMS_FOR_BAR):
        yield from items
        return

    try:
        from tqdm import tqdm
    except ImportError:  # pragma: no cover - tqdm is a declared dependency
        yield from items
        return

    explicit_stream = stream is not None
    yield from tqdm(
        items,
        desc=description,
        total=total,
        unit="file",
        file=stream,
        # With no explicit stream, disable=None makes tqdm suppress itself when
        # stderr is not a terminal, which keeps piped and redirected runs clean.
        disable=False if explicit_stream else None,
        # On a terminal, tqdm's default 0.1s throttle avoids pointless redraws.
        # An explicit stream is being captured rather than watched, so record
        # every frame instead of whatever happened to fall on a tick.
        mininterval=0 if explicit_stream else 0.1,
        leave=False,
        dynamic_ncols=True,
    )


def progress_factory(
    description: str,
    enabled: bool = True,
    stream: TextIO | None = None,
) -> ProgressFactory:
    """Build the ``progress`` callable that planner and executor accept."""

    def _wrap(items: Iterable[T]) -> Iterable[T]:
        return iter_with_progress(
            items, description=description, enabled=enabled, stream=stream
        )

    return _wrap
