"""The main job: find images, sort them into YYYY-MM folders, write a report."""

import os
import shutil

from tqdm import tqdm

from image_reader import ImageReader
from report import Report


class ImageSorter:
    def __init__(self, input_dir, output_dir, mode):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.mode = mode                 # "copy" or "move"
        self.reader = ImageReader()
        self.dead_letter_queue = []      # list of (full_path, reason) for failed images
        self.success_count = 0

    def run(self):
        images = self.find_images()
        print(f"Found {len(images)} images in {self.input_dir}")

        for path in tqdm(images, desc=f"{self.mode.capitalize()} images", unit="img"):
            self.process_image(path)

        report = Report(self.mode, len(images), self.success_count, self.dead_letter_queue)
        report.save(self.output_dir)

    def find_images(self):
        """Walk the input folder (and all sub-folders) and return full paths of every image."""
        images = []
        for root, dirs, files in os.walk(self.input_dir):
            # Never walk into the output folder, it may live inside the input folder.
            dirs[:] = [d for d in dirs if os.path.join(root, d) != self.output_dir]

            for name in files:
                path = os.path.join(root, name)
                if self.reader.is_image(path):
                    images.append(path)
        images.sort()
        return images

    def process_image(self, path):
        if self.reader.is_corrupted(path):
            self.dead_letter_queue.append((path, "corrupted"))
            return

        year_month = self.reader.get_year_month(path)
        if year_month is None:
            self.dead_letter_queue.append((path, "no EXIF date"))
            return

        bin_dir = os.path.join(self.output_dir, year_month)
        if not os.path.isdir(bin_dir):
            os.makedirs(bin_dir)

        destination = self.get_free_path(bin_dir, os.path.basename(path))
        try:
            if self.mode == "move":
                shutil.move(path, destination)
            else:
                shutil.copy2(path, destination)
        except OSError as error:
            self.dead_letter_queue.append((path, f"{self.mode} failed: {error}"))
            return

        self.success_count += 1

    def get_free_path(self, folder, filename):
        """Return folder/filename, adding _1, _2, ... if a file with that name already exists."""
        destination = os.path.join(folder, filename)
        name, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(destination):
            destination = os.path.join(folder, f"{name}_{counter}{ext}")
            counter += 1
        return destination
