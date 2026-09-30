# sort_images

Sorts a folder of phone photos (e.g. an Android `DCIM` dump) into `YYYY-MM`
folders using the date stored in each photo's EXIF data.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
# Copy (default). Output goes to <input>/sorted_images
python main.py -i /media/drive/DCIM

# Move into a folder of your choice
python main.py -i /media/drive/DCIM -o /media/drive/Sorted --mode move
```

| Argument           | Meaning                                                   |
|--------------------|-----------------------------------------------------------|
| `-i, --input-dir`  | Folder with the photos. Sub-folders are included.         |
| `-o, --output-dir` | Where the `YYYY-MM` folders go. Created if missing.       |
| `-m, --mode`       | `copy` (default) or `move`.                               |

Supported images: `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`, `.heif`
(HEIC/HEIF via `pillow-heif`). Videos and other files are ignored.

Images that are corrupted or have no EXIF date are left where they are and
listed in the report. The report is printed at the end and saved as
`report_<timestamp>.txt` in the output folder.

## Code layout

| File              | What it does                                            |
|-------------------|---------------------------------------------------------|
| `main.py`         | Arguments, checks the folders, starts the sorter.       |
| `executor.py`     | `ImageSorter`: finds images, copies/moves them.         |
| `image_reader.py` | `ImageReader`: is it an image, is it corrupted, its date. |
| `report.py`       | `Report`: the summary printed and saved at the end.     |
| `test_sorter.py`  | Tests. Run with `pytest test_sorter.py`.                |
