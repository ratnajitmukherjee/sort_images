# sort-images

Sort photos into `YYYY-MM` folders by the date the picture was actually taken.

The capture date is read from the **EXIF metadata inside each file**, not from
its name. That is the whole point: a folder of `IMG_0001.JPG`, `DSC_1180.NEF`
and `PXL_20240119_154500123.jpg` carries no useful ordering in the filenames,
but every one of those files knows when its shutter fired. JPEG, HEIC, DNG,
NEF, CR2, ARW and the other raw formats are all read the same way.

```
before/                          after/
├── IMG_0001.JPG                 ├── 2023-05/
├── IMG_0002.JPG                 │   ├── IMG_0001.JPG
├── DSC_1180.NEF                 │   └── IMG_0002.JPG
├── PXL_20240119_154500.jpg      ├── 2023-06/
└── screenshot.png               │   └── DSC_1180.NEF
                                 ├── 2024-01/
                                 │   └── PXL_20240119_154500.jpg
                                 └── undated/
                                     └── screenshot.png
```

Nothing is guessed. A file with no readable capture date goes to `undated/`
rather than being filed under a month it may not belong to.

## Install

Requires Python 3.10 or newer.

```bash
git clone https://github.com/ratnajitmukherjee/sort_images.git
cd sort_images
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

That installs a `sort-images` command. You can equally run it straight from a
checkout without installing, which is also the easiest way to attach a
debugger:

```bash
python main.py -i ~/Pictures/holiday --dry-run
```

### Optional: exiftool

If [`exiftool`](https://exiftool.org) is on your `PATH` it is used as a last
resort for exotic formats the Python libraries cannot decode. It is entirely
optional — the tool works without it and silently skips that backend.

```bash
brew install exiftool          # macOS
sudo apt install libimage-exiftool-perl   # Debian/Ubuntu
```

## Usage

```bash
# Look first, change nothing. Always worth doing.
sort-images -i ~/Pictures/holiday --dry-run

# Sort in place — YYYY-MM folders are created inside the input folder.
sort-images -i ~/Pictures/holiday

# Sort into a separate folder, leaving the originals untouched.
sort-images -i /Volumes/CARD/DCIM -o ~/Pictures/library --recursive --copy

# Place files that carry no EXIF date at all.
sort-images -i ~/Pictures/scans --fallback-filename --fallback-mtime
```

A dry run over five files looks like this:

```
$ sort-images -i ~/Pictures/holiday --dry-run
Input:  /Users/you/Pictures/holiday
Output: /Users/you/Pictures/holiday (same as input)
Found 5 image file(s).
Reading EXIF metadata ...

Destination folders:
  2023-05      2 file(s)
  2023-06      1 file(s)
  undated      2 file(s)

Dates came from:
  exif               3 file(s)
  no date found      2 file(s)

2 file(s) had no EXIF capture date and went to 'undated'.
  Try --fallback-filename and/or --fallback-mtime to place them.

Summary:
  moved           5

Dry run -- nothing was changed. Re-run without --dry-run to apply.
```

Adding `--fallback-filename --fallback-mtime -v` places those two stragglers
and shows the reasoning per file:

```
  moved     DSC_1180.JPG   ->  2023-06/DSC_1180.JPG   [DateTimeOriginal via pillow]
  moved     IMG_0001.JPG   ->  2023-05/IMG_0001.JPG   [DateTimeOriginal via pillow]
  moved     PXL_2024...jpg ->  2024-01/PXL_2024...jpg [parsed from filename]
  moved     screenshot.jpg ->  2026-09/screenshot.jpg [filesystem modification time]
```

### Options

| Flag | Meaning |
| --- | --- |
| `-i`, `--input INPUT_DIR` | Folder containing the images to sort. **Required.** |
| `-o`, `--output OUTPUT_DIR` | Where the `YYYY-MM` folders are created. Defaults to the input folder. |
| `-n`, `--dry-run` | Show what would happen without changing anything. |
| `-r`, `--recursive` | Also scan subfolders of the input folder. |
| `--copy` | Copy files into place instead of moving them. |
| `--fallback-filename` | If a file has no EXIF date, try to read a `YYYYMMDD` date from its name. |
| `--fallback-mtime` | If a file has no EXIF date, fall back to its modification time. |
| `-v`, `--verbose` | List every file and where it goes. |
| `-y`, `--yes` | Do not ask for confirmation before moving files. |
| `--debug` | Print diagnostics: which backend read which file, and why a file was skipped. |
| `--version` | Print the version and exit. |

Exit codes: `0` success, `1` one or more files failed, `3` aborted at the
confirmation prompt or by `Ctrl-C`.

## How the date is decided

EXIF is always the authority. Three backends are tried in turn and the first
to produce a usable timestamp wins:

1. **exifread** — JPEG and every TIFF-derived raw (DNG, NEF, CR2, ARW, ORF, PEF, SRW…).
2. **Pillow** — HEIC/HEIF/AVIF via `pillow-heif`, plus PNG, WebP and TIFF.
3. **exiftool** — optional external binary, for whatever the first two cannot read.

Within a file, tags are consulted in order of trustworthiness:
`DateTimeOriginal` (the moment the shutter fired), then `DateTimeDigitized`
(written to card), then `DateTime` (a plain modification stamp that editing
software rewrites). Malformed placeholders such as `0000:00:00 00:00:00`, which
cameras emit when the clock was never set, are rejected rather than bucketed.

Two fallbacks exist for files that carry no EXIF at all — screenshots, exports
stripped by messaging apps, scans — and **both are off by default**, because a
wrong date silently files a photo under the wrong month:

- `--fallback-filename` parses an unambiguous ISO-ordered `YYYYMMDD` run from the
  name. Day-first names like `14-05-2023` are ambiguous and deliberately left
  unmatched.
- `--fallback-mtime` trusts the filesystem modification time.

Whichever source was used is always reported, so a run stays auditable.

## Safety

This tool moves your photographs, so it is built to refuse to lose one.

- **Nothing is ever overwritten.** A name clash is resolved by suffixing
  `_1`, `_2`, … rather than replacing the file already there.
- **Duplicates are detected, not re-copied.** If the destination already holds a
  byte-identical file (size check, then SHA-256), the source is left alone and
  reported as a duplicate.
- **Re-runs are idempotent.** A file already sitting in its correct `YYYY-MM`
  folder is skipped, and sorted folders belonging to the output are not
  re-scanned.
- **One bad file never aborts the batch.** Failures are recorded per file and
  listed in the summary; the run continues.
- **Dry run means dry run.** Planning and execution are separate, and `--dry-run`
  walks the identical code path but stops before touching the filesystem — so
  what it prints is what a real run would do.
- **Writability is checked up front.** macOS mounts NTFS volumes read-only, so
  an unwritable source or destination is caught before a long EXIF scan rather
  than after it, with a concrete suggested command.
- **Non-image files are never touched**, and you are asked to confirm before
  anything moves unless you pass `-y`.

## Supported formats

Recognised by extension across the common bitmap formats (JPEG, PNG, GIF, BMP,
WebP, TIFF, JPEG 2000), Apple/ISO-BMFF (HEIC, HEIF, AVIF), and raw formats from
Adobe, Nikon, Canon, Sony, Fujifilm, Olympus, Panasonic, Pentax, Samsung,
Sigma, Epson, Minolta, Hasselblad, Phase One, Mamiya, Leaf, Leica, Kodak and
GoPro.

Extensions are only a hint. Every candidate whose suffix is unfamiliar is also
sniffed by magic bytes, so a raw file named `DSC_0001` with no extension at all
is still recognised and sorted.

## Development

```bash
pip install -e ".[dev]"
pytest              # 251 passed, 1 skipped
pytest --cov        # currently 97% line + branch coverage
```

### Project layout

The package is small and each module has one job. `main.py` only wires things
up; the work lives in `sort_images/`:

| Module | Responsibility |
| --- | --- |
| `cli.py` | Argument parsing and orchestration — **start here** |
| `discovery.py` | Which files are candidates |
| `filetypes.py` | Is this an image, by extension or by content signature |
| `exif_reader.py` | Pulling the timestamp out of a file |
| `date_source.py` | Deciding which date to trust, and recording why |
| `planner.py` | Working out destinations — performs no writes |
| `executor.py` | Actually moving or copying files |
| `report.py` | Rendering the human-readable output |
| `filesystem.py` | Writability and read-only mount checks |
| `progress.py` | Progress bars |

The planner/executor split is what makes `--dry-run` trustworthy: the same plan
is built either way, and a dry run simply stops before the executor runs.

## License

[MIT](LICENSE) — do what you like with it, no warranty.
