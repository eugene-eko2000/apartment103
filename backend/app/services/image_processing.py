"""Downsize and recompress uploaded photos before they're written to disk.

Property photos come off phones/DSLRs at 4000px+ and several MB each, far
past what any web/mobile layout renders at. 2000px on the longest side
comfortably covers a full-bleed hero image on a 2x (retina) display at
normal viewport widths, and per-format quality settings below strike a
standard web-compression balance (small file, no visible artifacting).
Anything larger than that is wasted bandwidth for every guest who loads the
site, so this always runs before a file reaches IMAGE_STORAGE_PATH.
"""

import io

import pillow_heif
from fastapi import HTTPException, status
from PIL import Image, ImageOps

# Pillow has no built-in HEIC/HEIF support (the default format for iPhone
# photos); this registers a plugin so Image.open() can decode it like any
# other format. Global and import-time by design — it's a one-time process
# registration, not per-request state.
pillow_heif.register_heif_opener()

_MAX_DIMENSION = 2000

_SAVE_KWARGS: dict[str, dict] = {
    "jpg": {"format": "JPEG", "quality": 82, "optimize": True, "progressive": True},
    "png": {"format": "PNG", "optimize": True},
    "webp": {"format": "WEBP", "quality": 82, "method": 6},
}


def compress_image(body: bytes, ext: str) -> tuple[bytes, int, int]:
    """Returns (recompressed_bytes, width, height). Raises 422 on unopenable input."""
    try:
        image = Image.open(io.BytesIO(body))
        image.load()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File is not a valid image"
        ) from exc

    # Bakes EXIF rotation into the pixels and drops the (now redundant) EXIF
    # block entirely, which also strips any location/device metadata.
    image = ImageOps.exif_transpose(image)

    if ext == "jpg":
        has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
        if has_alpha:
            # JPEG has no alpha channel; flatten onto white rather than
            # dropping transparency straight to black.
            rgba = image.convert("RGBA")
            flattened = Image.new("RGB", rgba.size, (255, 255, 255))
            flattened.paste(rgba, mask=rgba.split()[-1])
            image = flattened
        elif image.mode != "RGB":
            image = image.convert("RGB")

    # In-place, aspect-preserving, and a no-op if the image is already
    # within bounds — never upscales a smaller source image.
    image.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, **_SAVE_KWARGS[ext])
    return buffer.getvalue(), image.width, image.height
