"""Identify image files by extension *and* by content signature.

Extensions are only a hint: camera and phone exports arrive with names we cannot
predict, and some are renamed or stripped entirely. Every candidate is therefore
also sniffed by magic bytes, so a RAW file called ``DSC_0001`` with no extension
is still recognised.
"""

from __future__ import annotations

from pathlib import Path

# Read enough to cover the longest signature we check (RAF needs 15 bytes,
# ISO-BMFF brand codes live at offsets 8-12).
HEADER_SIZE = 32

#: Extensions we treat as images on sight. Deliberately broad -- this is the
#: fast path, not the authority. Unknown extensions fall through to sniffing.
IMAGE_EXTENSIONS = frozenset(
    {
        # Common bitmap / consumer formats
        ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".gif", ".bmp", ".webp",
        ".tif", ".tiff", ".jp2", ".j2k", ".jpf", ".jpx",
        # Apple / ISO-BMFF
        ".heic", ".heif", ".hif", ".avif",
        # Raw formats, by vendor
        ".dng",                                  # Adobe / Google / Leica
        ".nef", ".nrw",                          # Nikon
        ".cr2", ".cr3", ".crw",                  # Canon
        ".arw", ".srf", ".sr2",                  # Sony
        ".raf",                                  # Fujifilm
        ".orf",                                  # Olympus / OM System
        ".rw2", ".raw",                          # Panasonic
        ".pef", ".ptx",                          # Pentax
        ".srw",                                  # Samsung
        ".x3f",                                  # Sigma
        ".erf",                                  # Epson
        ".mrw",                                  # Minolta
        ".3fr", ".fff",                          # Hasselblad
        ".iiq",                                  # Phase One
        ".mef",                                  # Mamiya
        ".mos",                                  # Leaf
        ".rwl",                                  # Leica
        ".dcr", ".kdc",                          # Kodak
        ".gpr",                                  # GoPro
    }
)

#: Signatures matched against the very start of the file.
_MAGIC_PREFIXES: tuple[bytes, ...] = (
    b"\xff\xd8\xff",                 # JPEG
    b"\x89PNG\r\n\x1a\n",            # PNG
    b"II*\x00",                      # TIFF little-endian: DNG, NEF, CR2, ARW, ...
    b"MM\x00*",                      # TIFF big-endian
    b"II+\x00",                      # BigTIFF little-endian
    b"MM\x00+",                      # BigTIFF big-endian
    b"IIU\x00",                      # Panasonic RW2/RAW
    b"IIRO",                         # Olympus ORF
    b"MMOR",                         # Olympus ORF
    b"IIRS",                         # Olympus ORF
    b"FUJIFILMCCD-RAW",              # Fujifilm RAF
    b"FOVb",                         # Sigma X3F
    b"\x00MRM",                      # Minolta MRW
    b"GIF87a",                       # GIF
    b"GIF89a",                       # GIF
    b"BM",                           # BMP
    b"\x00\x00\x00\x0cjP  ",         # JPEG 2000
)

#: ISO base-media brands that denote a still image container. The brand sits at
#: bytes 8-12, immediately after the ``ftyp`` box marker.
_FTYP_IMAGE_BRANDS = frozenset(
    {
        b"heic", b"heix", b"heim", b"heis",   # HEIC stills
        b"hevc", b"hevx",                     # HEVC image sequences
        b"mif1", b"msf1",                     # generic HEIF
        b"avif", b"avis",                     # AVIF
        b"crx ",                              # Canon CR3
    }
)


def has_image_extension(path: Path) -> bool:
    """Return True when the suffix is one we recognise as an image."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def sniff_image_header(header: bytes) -> bool:
    """Return True when ``header`` starts with a known image signature.

    Pure function over bytes so it can be exercised without touching disk.
    """
    if not header:
        return False

    if header.startswith(_MAGIC_PREFIXES):
        return True

    # ISO base-media container (HEIC / AVIF / CR3): "....ftyp<brand>"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return header[8:12] in _FTYP_IMAGE_BRANDS

    # RIFF container -- only WEBP is an image.
    if len(header) >= 12 and header[0:4] == b"RIFF":
        return header[8:12] == b"WEBP"

    return False


def read_header(path: Path, size: int = HEADER_SIZE) -> bytes:
    """Read the leading bytes of ``path``, returning b"" if it cannot be read."""
    try:
        with path.open("rb") as handle:
            return handle.read(size)
    except OSError:
        return b""


def looks_like_image(path: Path) -> bool:
    """Return True when ``path`` is an image by extension or by content.

    A known extension short-circuits the read. Anything else is sniffed, which
    is what lets extension-less or oddly named camera files still be sorted.
    """
    if has_image_extension(path):
        return True
    return sniff_image_header(read_header(path))
