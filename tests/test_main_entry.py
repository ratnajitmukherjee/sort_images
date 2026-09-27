"""Tests for main.py, the project's runnable entry point.

These run it as a real subprocess, which is what proves it works when launched
straight from a checkout (or from PyCharm's Run/Debug) rather than only through
the installed console script.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = PROJECT_ROOT / "main.py"


def run_main(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MAIN_PY), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or PROJECT_ROOT),
        timeout=120,
    )


def test_main_py_exists_at_the_project_root() -> None:
    assert MAIN_PY.is_file()


def test_main_py_reports_version() -> None:
    result = run_main("--version")

    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_main_py_shows_help_with_input_and_output_flags() -> None:
    result = run_main("--help")

    assert result.returncode == 0
    assert "-i INPUT_DIR" in result.stdout or "--input" in result.stdout
    assert "--output" in result.stdout


def test_main_py_sorts_a_folder(tmp_path: Path, jpeg_factory) -> None:
    source_dir = tmp_path / "card"
    dest_dir = tmp_path / "library"
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=source_dir)

    result = run_main(
        "-i", str(source_dir), "-o", str(dest_dir), "--yes"
    )

    assert result.returncode == 0, result.stderr
    assert (dest_dir / "2023-05" / "IMG_0001.jpg").is_file()


def test_main_py_runs_from_any_working_directory(
    tmp_path: Path, jpeg_factory
) -> None:
    """The sys.path shim must work regardless of where it is launched from."""
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    result = run_main("-i", str(tmp_path), "--dry-run", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "2023-05" in result.stdout
