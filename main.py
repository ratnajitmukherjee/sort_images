#!/usr/bin/env python3
"""Entry point for sort-images. Run or debug this file directly.

    python main.py -i ~/Pictures/holiday --dry-run
    python main.py -i ~/Pictures/holiday -o ~/Pictures/sorted

In PyCharm: right-click this file -> Run / Debug, then set the arguments under
Run > Edit Configurations. Breakpoints anywhere in ``sort_images/`` will hit.

The real work lives in ``sort_images/``; this file only wires it up:

    cli.py         argument parsing, orchestration   <- start here
    discovery.py   which files are candidates
    exif_reader.py pulling the timestamp out of a file
    date_source.py deciding which date to trust
    planner.py     working out destinations (no writes)
    executor.py    actually moving files
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file straight from a checkout, without `pip install -e .`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sort_images.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
