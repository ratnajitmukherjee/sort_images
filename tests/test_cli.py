"""End-to-end tests driving the command line interface."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sort_images import cli
from sort_images.cli import EXIT_FAILURES, EXIT_OK, main


def test_sorts_a_mixed_folder_end_to_end(
    photo_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["-i", str(photo_folder), "--yes"])

    assert exit_code == EXIT_OK
    assert (photo_folder / "2023-05" / "IMG_0001.JPG").is_file()
    assert (photo_folder / "2023-05" / "DSC_9987.jpg").is_file()
    assert (photo_folder / "2023-06" / "holiday-beach.jpeg").is_file()
    assert (photo_folder / "2021-12" / "_MG_4410.jpg").is_file()
    assert (photo_folder / "undated" / "no_exif_at_all.jpg").is_file()

    # Non-image files are never touched.
    assert (photo_folder / "notes.txt").is_file()

    output = capsys.readouterr().out
    assert "2023-05" in output
    assert "Summary:" in output


def test_input_flag_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])

    assert excinfo.value.code == 2
    assert "--input" in capsys.readouterr().err


def test_long_form_input_flag_works(photo_folder: Path) -> None:
    assert main(["--input", str(photo_folder), "--yes"]) == EXIT_OK
    assert (photo_folder / "2023-05" / "IMG_0001.JPG").is_file()


def test_output_defaults_to_input(
    photo_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["-i", str(photo_folder), "--dry-run"])

    assert "same as input" in capsys.readouterr().out


def test_sorts_into_a_separate_output_folder(
    tmp_path: Path, jpeg_factory
) -> None:
    source_dir = tmp_path / "card"
    dest_dir = tmp_path / "library"
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=source_dir)

    exit_code = main(["-i", str(source_dir), "-o", str(dest_dir), "--yes"])

    assert exit_code == EXIT_OK
    assert (dest_dir / "2023-05" / "IMG_0001.jpg").is_file()
    assert not (source_dir / "2023-05").exists()
    assert not (source_dir / "IMG_0001.jpg").exists()      # moved out


def test_long_form_output_flag_works(tmp_path: Path, jpeg_factory) -> None:
    source_dir = tmp_path / "card"
    dest_dir = tmp_path / "library"
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=source_dir)

    assert main(
        ["--input", str(source_dir), "--output", str(dest_dir), "--yes"]
    ) == EXIT_OK
    assert (dest_dir / "2023-05" / "IMG_0001.jpg").is_file()


def test_output_folder_is_created_if_missing(tmp_path: Path, jpeg_factory) -> None:
    source_dir = tmp_path / "card"
    dest_dir = tmp_path / "does" / "not" / "exist" / "yet"
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=source_dir)

    assert main(["-i", str(source_dir), "-o", str(dest_dir), "--yes"]) == EXIT_OK
    assert (dest_dir / "2023-05" / "IMG_0001.jpg").is_file()


def test_copy_into_separate_output_keeps_originals(
    tmp_path: Path, jpeg_factory
) -> None:
    """The archival workflow: card stays untouched, library gets a copy."""
    source_dir = tmp_path / "card"
    dest_dir = tmp_path / "library"
    source = jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=source_dir)

    exit_code = main(
        ["-i", str(source_dir), "-o", str(dest_dir), "--copy", "--yes"]
    )

    assert exit_code == EXIT_OK
    assert source.is_file()
    assert (dest_dir / "2023-05" / "IMG_0001.jpg").is_file()


def test_output_nested_inside_input_is_not_rescanned(
    tmp_path: Path, jpeg_factory
) -> None:
    """`-o` inside `-i` must not re-process what the run just wrote."""
    dest_dir = tmp_path / "sorted"
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    first = main(["-i", str(tmp_path), "-o", str(dest_dir), "--yes", "-r"])
    second = main(["-i", str(tmp_path), "-o", str(dest_dir), "--yes", "-r"])

    assert first == second == EXIT_OK
    assert (dest_dir / "2023-05" / "IMG_0001.jpg").is_file()
    assert not (dest_dir / "2023-05" / "IMG_0001_1.jpg").exists()
    assert not (dest_dir / "sorted").exists()


def test_dry_run_reports_but_changes_nothing(
    photo_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = sorted(p.name for p in photo_folder.iterdir())

    exit_code = main(["-i", str(photo_folder), "--dry-run"])

    assert exit_code == EXIT_OK
    assert sorted(p.name for p in photo_folder.iterdir()) == before
    assert "Dry run" in capsys.readouterr().out


def test_dry_run_does_not_create_the_output_folder(
    tmp_path: Path, jpeg_factory
) -> None:
    source_dir = tmp_path / "card"
    dest_dir = tmp_path / "library"
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=source_dir)

    main(["-i", str(source_dir), "-o", str(dest_dir), "--dry-run"])

    assert not dest_dir.exists()


def test_camera_names_are_sorted_by_metadata_not_by_name(
    tmp_path: Path, jpeg_factory
) -> None:
    """The core requirement: unrelated naming schemes still sort correctly.

    Three files with three different naming conventions -- one of which carries
    a *misleading* date in its name -- must all be placed from EXIF alone.
    """
    jpeg_factory("DSC_9987.NEF.jpg", datetime(2023, 5, 1, 9, 0))
    jpeg_factory("2019-01-01_wrong_name.jpg", datetime(2023, 5, 2, 9, 0))
    jpeg_factory("P1000123.jpg", datetime(2023, 5, 3, 9, 0))

    assert main(["-i", str(tmp_path), "--yes"]) == EXIT_OK

    sorted_names = {p.name for p in (tmp_path / "2023-05").iterdir()}
    assert sorted_names == {
        "DSC_9987.NEF.jpg",
        "2019-01-01_wrong_name.jpg",
        "P1000123.jpg",
    }
    assert not (tmp_path / "2019-01").exists()


def test_rerunning_in_place_is_idempotent(photo_folder: Path) -> None:
    main(["-i", str(photo_folder), "--yes"])
    first = {p.name for p in (photo_folder / "2023-05").iterdir()}

    exit_code = main(["-i", str(photo_folder), "--yes", "--recursive"])

    assert exit_code == EXIT_OK
    assert {p.name for p in (photo_folder / "2023-05").iterdir()} == first


def test_recursive_flattens_nested_folders(tmp_path: Path, jpeg_factory) -> None:
    jpeg_factory("top.jpg", datetime(2023, 5, 14))
    jpeg_factory("deep.jpg", datetime(2023, 6, 1), root=tmp_path / "card" / "dcim")

    assert main(["-i", str(tmp_path), "--yes", "--recursive"]) == EXIT_OK
    assert (tmp_path / "2023-05" / "top.jpg").is_file()
    assert (tmp_path / "2023-06" / "deep.jpg").is_file()


def test_already_sorted_input_is_refiled_into_a_new_output(
    tmp_path: Path, jpeg_factory
) -> None:
    """A sorted library can be re-filed elsewhere.

    YYYY-MM folders are only ignored when they belong to the output, so
    pointing -o somewhere new picks them up rather than skipping them.
    """
    source_dir = tmp_path / "old_library"
    dest_dir = tmp_path / "new_library"
    jpeg_factory("a.jpg", datetime(2023, 5, 14), root=source_dir / "2023-05")

    assert main(
        ["-i", str(source_dir), "-o", str(dest_dir), "--yes", "-r"]
    ) == EXIT_OK
    assert (dest_dir / "2023-05" / "a.jpg").is_file()


def test_copy_mode_keeps_originals(tmp_path: Path, jpeg_factory) -> None:
    source = jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    assert main(["-i", str(tmp_path), "--yes", "--copy"]) == EXIT_OK
    assert source.is_file()
    assert (tmp_path / "2023-05" / "IMG_0001.jpg").is_file()


def test_filename_fallback_places_undated_files(
    tmp_path: Path, jpeg_factory
) -> None:
    jpeg_factory("20230514_123045.jpg", None)

    assert main(["-i", str(tmp_path), "--yes", "--fallback-filename"]) == EXIT_OK
    assert (tmp_path / "2023-05" / "20230514_123045.jpg").is_file()


def test_undated_hint_is_shown_without_fallbacks(
    tmp_path: Path, jpeg_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    jpeg_factory("mystery.jpg", None)

    main(["-i", str(tmp_path), "--dry-run"])

    assert "--fallback-filename" in capsys.readouterr().out


def test_verbose_lists_each_file(
    photo_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["-i", str(photo_folder), "--dry-run", "--verbose"])

    output = capsys.readouterr().out
    assert "IMG_0001.JPG" in output
    assert "DateTimeOriginal" in output


def test_debug_flag_reports_backend_decisions(
    tmp_path: Path, jpeg_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    """--debug must say which backend read the file, on stderr."""
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    main(["-i", str(tmp_path), "--dry-run", "--debug"])

    captured = capsys.readouterr()
    assert "exifread" in captured.err
    assert "IMG_0001.jpg" in captured.err
    # Diagnostics must not contaminate the report on stdout.
    assert "DEBUG" not in captured.out
    # Third-party chatter must not drown out our own decisions.
    assert "TiffImagePlugin" not in captured.err


def test_write_phase_is_watched_on_a_real_run(
    tmp_path: Path, jpeg_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real run must draw a bar over the write phase, not just the read."""
    descriptions: list[str] = []
    real_factory = cli.progress_factory

    def _spy(description: str, enabled: bool = True, stream=None):
        if enabled:
            descriptions.append(description)
        return real_factory(description, enabled=enabled, stream=stream)

    monkeypatch.setattr(cli, "progress_factory", _spy)
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    assert main(["-i", str(tmp_path), "--yes"]) == EXIT_OK
    assert descriptions == ["Reading EXIF", "Moving"]


def test_copy_run_labels_the_write_phase_copying(
    tmp_path: Path, jpeg_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptions: list[str] = []
    real_factory = cli.progress_factory

    def _spy(description: str, enabled: bool = True, stream=None):
        if enabled:
            descriptions.append(description)
        return real_factory(description, enabled=enabled, stream=stream)

    monkeypatch.setattr(cli, "progress_factory", _spy)
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    assert main(["-i", str(tmp_path), "--yes", "--copy"]) == EXIT_OK
    assert descriptions == ["Reading EXIF", "Copying"]


def test_dry_run_does_not_watch_a_write_that_never_happens(
    tmp_path: Path, jpeg_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptions: list[str] = []
    real_factory = cli.progress_factory

    def _spy(description: str, enabled: bool = True, stream=None):
        if enabled:
            descriptions.append(description)
        return real_factory(description, enabled=enabled, stream=stream)

    monkeypatch.setattr(cli, "progress_factory", _spy)
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    main(["-i", str(tmp_path), "--dry-run"])

    assert descriptions == ["Reading EXIF"]


def test_debug_disables_both_bars(
    tmp_path: Path, jpeg_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Log lines and a redrawing bar would fight over stderr."""
    enabled_flags: list[bool] = []
    real_factory = cli.progress_factory

    def _spy(description: str, enabled: bool = True, stream=None):
        enabled_flags.append(enabled)
        return real_factory(description, enabled=enabled, stream=stream)

    monkeypatch.setattr(cli, "progress_factory", _spy)
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    main(["-i", str(tmp_path), "--yes", "--debug"])

    assert enabled_flags == [False, False]


def test_debug_is_off_by_default(
    tmp_path: Path, jpeg_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))

    main(["-i", str(tmp_path), "--dry-run"])

    assert "DEBUG" not in capsys.readouterr().err


def test_missing_input_folder_exits_with_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["-i", str(tmp_path / "does_not_exist")])

    assert exit_code == EXIT_FAILURES
    assert "does not exist" in capsys.readouterr().err


def test_input_that_is_a_file_exits_with_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "a.txt"
    target.write_text("hi")

    assert main(["-i", str(target)]) == EXIT_FAILURES
    assert "input is not a folder" in capsys.readouterr().err


def test_output_that_is_a_file_exits_with_error(
    tmp_path: Path, jpeg_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("in the way")

    assert main(["-i", str(tmp_path), "-o", str(blocker)]) == EXIT_FAILURES
    assert "output is not a folder" in capsys.readouterr().err


def test_empty_folder_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["-i", str(tmp_path)]) == EXIT_OK
    assert "Found 0 image file(s)." in capsys.readouterr().out


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    assert "0.1.0" in capsys.readouterr().out
