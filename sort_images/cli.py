"""Command-line entry point for sorting photos into YYYY-MM folders."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .date_source import FallbackPolicy
from .discovery import find_images
from .executor import execute_plan
from .exif_reader import exiftool_available
from .filesystem import check_writable
from .planner import build_plan
from .progress import progress_factory
from .report import (
    count_moves,
    format_date_sources,
    format_execution_summary,
    format_plan_summary,
    format_undated_hint,
    format_verbose_lines,
)

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_ABORTED = 3

_DESCRIPTION = """\
Sort photos into YYYY-MM folders by the date the picture was taken.

The capture date is read from the EXIF metadata inside each file, so it works
regardless of how the file is named -- JPEG, HEIC, DNG, NEF, CR2, ARW and other
raw formats are all read the same way.
"""

_EPILOG = """\
examples:
  # look first, change nothing
  sort-images -i ~/Pictures/holiday --dry-run

  # sort in place (output defaults to the input folder)
  sort-images -i ~/Pictures/holiday

  # sort into a separate folder, leaving the originals untouched
  sort-images -i /Volumes/CARD/DCIM -o ~/Pictures/library --recursive --copy

  # place files that have no EXIF date at all
  sort-images -i ~/Pictures/scans --fallback-filename --fallback-mtime
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sort-images",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input_dir",
        type=Path,
        required=True,
        metavar="INPUT_DIR",
        help="folder containing the images to sort",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        type=Path,
        default=None,
        metavar="OUTPUT_DIR",
        help="where the YYYY-MM folders are created (default: the input folder)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would happen without changing anything",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="also scan subfolders of the input folder",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="copy files into place instead of moving them",
    )
    parser.add_argument(
        "--fallback-filename",
        action="store_true",
        help="if a file has no EXIF date, try to read a YYYYMMDD date from its name",
    )
    parser.add_argument(
        "--fallback-mtime",
        action="store_true",
        help="if a file has no EXIF date, fall back to its modification time",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="list every file and where it goes",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="do not ask for confirmation before moving files",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print detailed diagnostics: which backend read which file, and why "
        "a file was skipped",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


#: Libraries that dump hundreds of lines per image at DEBUG level.
_NOISY_LOGGERS = ("PIL", "exifread", "pillow_heif")


def configure_logging(debug: bool) -> None:
    """Send diagnostics to stderr so they never pollute the report on stdout."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    # Keep --debug readable: our own decisions, not every TIFF tag Pillow reads.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)


def _confirm(prompt: str) -> bool:
    """Ask before touching files. Proceeds when there is no terminal to ask."""
    if not sys.stdin.isatty():
        return True
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _emit(lines: list[str]) -> None:
    for line in lines:
        print(line)


def resolve_folders(args: argparse.Namespace) -> tuple[Path, Path] | None:
    """Validate the input folder and work out where output should go.

    Returns ``(input_dir, output_dir)``, or None after reporting the problem.
    """
    input_dir = args.input_dir.expanduser()

    if not input_dir.exists():
        print(f"error: input folder does not exist: {input_dir}", file=sys.stderr)
        return None
    if not input_dir.is_dir():
        print(f"error: input is not a folder: {input_dir}", file=sys.stderr)
        return None

    input_dir = input_dir.resolve()
    if args.output_dir is None:
        return input_dir, input_dir

    output_dir = args.output_dir.expanduser()
    if output_dir.exists() and not output_dir.is_dir():
        print(f"error: output is not a folder: {output_dir}", file=sys.stderr)
        return None

    # Resolve without requiring existence -- the folder is created on demand.
    return input_dir, output_dir.absolute().resolve()


def _example_command(input_dir: Path, output_dir: Path) -> str:
    """A concrete, runnable suggestion for a read-only source."""
    suggested = output_dir if output_dir != input_dir else Path.home() / "Pictures" / "sorted"
    return f"    python main.py -i {input_dir} -o {suggested} --copy"


def check_filesystems(
    input_dir: Path, output_dir: Path, copy_mode: bool
) -> list[str]:
    """Report anything that would make this run fail on every single file.

    Catching these up front matters most on external drives: macOS mounts NTFS
    read-only, so a whole EXIF scan would otherwise complete before the first
    write revealed the problem.
    """
    problems: list[str] = []

    output_state = check_writable(output_dir)
    if not output_state:
        lines = [
            f"cannot write to the output folder: {output_dir}",
            f"  reason: {output_state.reason}",
        ]
        if output_state.read_only_mount:
            lines.append(
                "  macOS mounts NTFS volumes read-only unless a third-party "
                "driver is installed."
            )
        lines += [
            "  Pick an output folder on a writable disk:",
            _example_command(input_dir, output_dir),
        ]
        problems.append("\n".join(lines))

    # Moving unlinks the original, so the *source* has to be writable too.
    if not copy_mode:
        input_state = check_writable(input_dir)
        if not input_state:
            lines = [
                f"cannot move files out of: {input_dir}",
                f"  reason: {input_state.reason}",
                "  Moving deletes the original, which this volume does not allow.",
                "  Use --copy to leave the source untouched:",
                _example_command(input_dir, output_dir),
            ]
            problems.append("\n".join(lines))

    return problems


def run(args: argparse.Namespace) -> int:
    folders = resolve_folders(args)
    if folders is None:
        return EXIT_FAILURES
    input_dir, output_dir = folders

    policy = FallbackPolicy(
        use_filename=args.fallback_filename,
        use_mtime=args.fallback_mtime,
    )

    print(f"Input:  {input_dir}{' (recursive)' if args.recursive else ''}")
    print(f"Output: {output_dir}{' (same as input)' if output_dir == input_dir else ''}")
    if not exiftool_available():
        logger.debug("exiftool not found; using built-in readers only")

    # Check before the scan: on a large external drive, reading EXIF from every
    # file only to fail on the first write wastes a great deal of time.
    problems = check_filesystems(input_dir, output_dir, copy_mode=args.copy)
    if problems:
        # stdout is block-buffered when piped while stderr is not, so without
        # this the errors would surface above the report they belong under.
        sys.stdout.flush()
        label = "warning" if args.dry_run else "error"
        for problem in problems:
            print(f"{label}: {problem}", file=sys.stderr)
        if not args.dry_run:
            return EXIT_FAILURES
        print(
            "Continuing anyway -- a dry run writes nothing.\n", file=sys.stderr
        )

    files = find_images(input_dir, recursive=args.recursive, output_root=output_dir)
    print(f"Found {len(files)} image file(s).")
    if not files:
        return EXIT_OK

    # A redrawing bar and debug log lines both want stderr; the logs win.
    show_bars = not args.debug

    print("Reading EXIF metadata ...")
    plan = build_plan(
        files,
        output_dir,
        policy=policy,
        copy=args.copy,
        progress=progress_factory("Reading EXIF", enabled=show_bars),
    )

    _emit(format_plan_summary(plan))
    _emit(format_date_sources(plan))
    _emit(
        format_undated_hint(
            plan, fallbacks_enabled=args.fallback_filename or args.fallback_mtime
        )
    )

    pending = count_moves(plan)
    if pending and not args.dry_run and not args.yes:
        verb = "Copy" if args.copy else "Move"
        if not _confirm(f"\n{verb} {pending} file(s) into {output_dir}?"):
            print("Aborted -- nothing was changed.")
            return EXIT_ABORTED

    report = execute_plan(
        plan,
        dry_run=args.dry_run,
        progress=progress_factory(
            "Copying" if args.copy else "Moving",
            # Nothing is written during a dry run, so there is nothing to watch.
            enabled=show_bars and not args.dry_run,
        ),
    )

    if args.verbose:
        print()
        _emit(format_verbose_lines(report, input_dir, output_dir))
    _emit(format_execution_summary(report))

    return EXIT_FAILURES if report.failed else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.debug)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ABORTED


if __name__ == "__main__":
    raise SystemExit(main())
