"""Tests for extension and magic-byte based image detection."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sort_images.filetypes import (
    has_image_extension,
    looks_like_image,
    read_header,
    sniff_image_header,
)


@pytest.mark.parametrize(
    "header",
    [
        b"\xff\xd8\xff\xe0" + b"\x00" * 12,          # JPEG
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 12,         # PNG
        b"II*\x00" + b"\x00" * 16,                   # TIFF LE (DNG/NEF/CR2/ARW)
        b"MM\x00*" + b"\x00" * 16,                   # TIFF BE
        b"IIU\x00" + b"\x00" * 16,                   # Panasonic RW2
        b"IIRO" + b"\x00" * 16,                      # Olympus ORF
        b"FUJIFILMCCD-RAW" + b"\x00" * 8,            # Fujifilm RAF
        b"FOVb" + b"\x00" * 16,                      # Sigma X3F
        b"GIF89a" + b"\x00" * 12,                    # GIF
        b"\x00\x00\x00\x18ftypheic" + b"\x00" * 8,   # HEIC
        b"\x00\x00\x00\x18ftypavif" + b"\x00" * 8,   # AVIF
        b"\x00\x00\x00\x18ftypcrx " + b"\x00" * 8,   # Canon CR3
        b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8,   # WebP
    ],
)
def test_sniff_recognises_image_signatures(header: bytes) -> None:
    assert sniff_image_header(header) is True


@pytest.mark.parametrize(
    "header",
    [
        b"",                                          # empty
        b"just some plain text in a file",            # text
        b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8,    # MP4 video, not an image
        b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 8,    # WAV audio
        b"PK\x03\x04" + b"\x00" * 16,                 # zip
        b"%PDF-1.7" + b"\x00" * 12,                   # pdf
    ],
)
def test_sniff_rejects_non_images(header: bytes) -> None:
    assert sniff_image_header(header) is False


@pytest.mark.parametrize(
    "name",
    ["a.jpg", "a.JPG", "a.HEIC", "a.dng", "a.NEF", "a.cr2", "a.CR3", "a.arw", "a.raf"],
)
def test_known_extensions_are_recognised(name: str) -> None:
    assert has_image_extension(Path(name)) is True


@pytest.mark.parametrize("name", ["a.txt", "a.pdf", "a.mp4", "a", "a.doc"])
def test_unknown_extensions_are_not_recognised(name: str) -> None:
    assert has_image_extension(Path(name)) is False


def test_extensionless_camera_file_is_detected_by_content(
    tmp_path: Path, jpeg_factory
) -> None:
    """A raw file stripped of its extension must still be recognised."""
    original = jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))
    renamed = tmp_path / "DSC_0001"
    original.rename(renamed)

    assert has_image_extension(renamed) is False
    assert looks_like_image(renamed) is True


def test_text_file_is_not_an_image(tmp_path: Path) -> None:
    note = tmp_path / "notes.txt"
    note.write_text("hello")
    assert looks_like_image(note) is False


def test_read_header_on_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_header(tmp_path / "nope.jpg") == b""
