#!/usr/bin/env python3
"""Sort photos into YYYY-MM folders using the date stored in their EXIF data.

Usage:
    python main.py -i /media/drive/DCIM
    python main.py -i /media/drive/DCIM -o /media/drive/Sorted --mode move
"""

import argparse
import os
import sys

from executor import ImageSorter


def main():
    parser = argparse.ArgumentParser(description="Sort images into YYYY-MM folders by EXIF date.")
    parser.add_argument("-i", "--input-dir", required=True,
                        help="Folder containing the images (sub-folders are included).")
    parser.add_argument("-o", "--output-dir",
                        help="Where the YYYY-MM folders go. Default: <input-dir>/sorted_images")
    parser.add_argument("-m", "--mode", choices=["copy", "move"], default="copy",
                        help="Copy the images (safe, default) or move them.")
    args = parser.parse_args()

    input_dir = os.path.abspath(args.input_dir)
    if not os.path.isdir(input_dir):
        print(f"Error: input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)

    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        output_dir = os.path.join(input_dir, "sorted_images")

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    sorter = ImageSorter(input_dir, output_dir, args.mode)
    sorter.run()


if __name__ == "__main__":
    main()
