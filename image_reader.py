"""Reading images: is it an image, is it corrupted, and when was it taken."""

import os
from datetime import datetime

from PIL import Image

# Optional: lets Pillow open HEIC photos (some Samsung phones save these).
# Install with `pip install pillow-heif` if your DCIM folder has .heic files.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass


class ImageReader:
    IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")

    # EXIF tag numbers, checked in this order.
    EXIF_IFD = 0x8769            # sub-section of EXIF where the camera tags live
    DATE_TIME_ORIGINAL = 36867   # when the photo was taken (best)
    DATE_TIME_DIGITIZED = 36868  # when it was saved
    DATE_TIME = 306              # last modified (fallback)

    def is_image(self, path):
        return path.lower().endswith(self.IMAGE_EXTENSIONS)

    def is_corrupted(self, path):
        try:
            with Image.open(path) as img:
                img.verify()
            return False
        except Exception:
            return True

    def get_year_month(self, path):
        """Return the capture date as "YYYY-MM", or None if there is no usable date."""
        try:
            with Image.open(path) as img:
                exif = img.getexif()
        except Exception:
            return None

        camera_tags = exif.get_ifd(self.EXIF_IFD)
        candidates = [
            camera_tags.get(self.DATE_TIME_ORIGINAL),
            camera_tags.get(self.DATE_TIME_DIGITIZED),
            exif.get(self.DATE_TIME),
        ]

        for value in candidates:
            if not value:
                continue
            # EXIF dates look like "2023:05:14 12:30:45"
            try:
                date = datetime.strptime(str(value)[:10], "%Y:%m:%d")
            except ValueError:
                continue
            return date.strftime("%Y-%m")

        return None
