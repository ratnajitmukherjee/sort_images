"""Run with: pytest test_sorter.py"""

import os
import subprocess
import sys

from PIL import Image

from executor import ImageSorter

HERE = os.path.dirname(os.path.abspath(__file__))


def make_image(path, date=None):
    """Create a small JPEG at `path`, with an EXIF DateTimeOriginal if `date` is given."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    exif = Image.Exif()
    if date:
        exif.get_ifd(0x8769)[36867] = date
    Image.new("RGB", (10, 10), "red").save(path, exif=exif)


def run_sorter(input_dir, output_dir, mode="copy"):
    os.makedirs(output_dir, exist_ok=True)  # main.py does this before calling the sorter
    sorter = ImageSorter(input_dir, output_dir, mode)
    sorter.run()
    return sorter


def test_copies_into_year_month_folders(tmp_path):
    input_dir = str(tmp_path / "in")
    output_dir = str(tmp_path / "out")
    make_image(os.path.join(input_dir, "a.jpg"), "2023:05:14 10:00:00")
    make_image(os.path.join(input_dir, "Camera", "sub", "b.jpg"), "2024:12:01 08:30:00")

    sorter = run_sorter(input_dir, output_dir)

    assert sorter.success_count == 2
    assert os.path.isfile(os.path.join(output_dir, "2023-05", "a.jpg"))
    assert os.path.isfile(os.path.join(output_dir, "2024-12", "b.jpg"))
    assert os.path.isfile(os.path.join(input_dir, "a.jpg"))  # copy keeps the original


def test_move_removes_original(tmp_path):
    input_dir = str(tmp_path / "in")
    output_dir = str(tmp_path / "out")
    make_image(os.path.join(input_dir, "a.jpg"), "2023:05:14 10:00:00")

    run_sorter(input_dir, output_dir, mode="move")

    assert os.path.isfile(os.path.join(output_dir, "2023-05", "a.jpg"))
    assert not os.path.exists(os.path.join(input_dir, "a.jpg"))


def test_corrupted_and_dateless_images_go_to_dead_letter_queue(tmp_path):
    input_dir = str(tmp_path / "in")
    output_dir = str(tmp_path / "out")
    broken = os.path.join(input_dir, "broken.jpg")
    no_date = os.path.join(input_dir, "no_date.jpg")
    os.makedirs(input_dir)
    with open(broken, "wb") as f:
        f.write(b"this is not an image")
    make_image(no_date)

    sorter = run_sorter(input_dir, output_dir)

    assert sorter.success_count == 0
    assert (broken, "corrupted") in sorter.dead_letter_queue
    assert (no_date, "no EXIF date") in sorter.dead_letter_queue


def test_non_images_are_ignored(tmp_path):
    input_dir = str(tmp_path / "in")
    os.makedirs(input_dir)
    with open(os.path.join(input_dir, "video.mp4"), "wb") as f:
        f.write(b"x")

    sorter = run_sorter(input_dir, str(tmp_path / "out"))

    assert sorter.success_count == 0
    assert sorter.dead_letter_queue == []


def test_same_filename_does_not_overwrite(tmp_path):
    input_dir = str(tmp_path / "in")
    output_dir = str(tmp_path / "out")
    make_image(os.path.join(input_dir, "one", "IMG.jpg"), "2023:05:14 10:00:00")
    make_image(os.path.join(input_dir, "two", "IMG.jpg"), "2023:05:20 10:00:00")

    run_sorter(input_dir, output_dir)

    assert sorted(os.listdir(os.path.join(output_dir, "2023-05"))) == ["IMG.jpg", "IMG_1.jpg"]


def test_output_folder_inside_input_is_not_rescanned(tmp_path):
    input_dir = str(tmp_path / "in")
    output_dir = os.path.join(input_dir, "sorted_images")
    make_image(os.path.join(input_dir, "a.jpg"), "2023:05:14 10:00:00")
    make_image(os.path.join(output_dir, "2020-01", "old.jpg"), "2020:01:01 10:00:00")

    sorter = run_sorter(input_dir, output_dir)

    assert sorter.find_images() == [os.path.join(input_dir, "a.jpg")]
    assert sorter.success_count == 1


def test_report_file_is_written(tmp_path):
    input_dir = str(tmp_path / "in")
    output_dir = str(tmp_path / "out")
    make_image(os.path.join(input_dir, "no_date.jpg"))

    run_sorter(input_dir, output_dir)

    reports = [f for f in os.listdir(output_dir) if f.startswith("report_")]
    assert len(reports) == 1
    with open(os.path.join(output_dir, reports[0])) as f:
        text = f.read()
    assert "Failed:      1" in text
    assert "no_date.jpg" in text


def test_main_rejects_missing_input_dir(tmp_path):
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "main.py"), "-i", str(tmp_path / "missing")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_main_uses_default_output_folder(tmp_path):
    input_dir = str(tmp_path / "in")
    make_image(os.path.join(input_dir, "a.jpg"), "2023:05:14 10:00:00")

    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "main.py"), "-i", input_dir],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert os.path.isfile(os.path.join(input_dir, "sorted_images", "2023-05", "a.jpg"))
