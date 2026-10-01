"""Storing uploaded images: validate, recompress, write to disk, record an
Image document. Shared by the Photos admin (app.api.routes.images) and the
images attached to automated guest messages
(app.api.routes.message_templates), so both get the same size limit, format
handling and on-disk layout.
"""

import re
import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.image import Image
from app.schemas.image import ALLOWED_CONTENT_TYPES, OUTPUT_CONTENT_TYPES
from app.services.image_processing import compress_image

# Raw upload cap, ahead of compression — generous enough for an
# uncompressed phone/DSLR photo. The file actually written to disk is the
# recompressed, downsized output from compress_image(), which lands far
# below this.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Fallback for browser/OS combinations that don't set a Content-Type for
# HEIC/HEIF (most commonly Windows without the HEIF extension pack
# installed) — the file is still a real HEIC, just mislabeled as generic
# octet-stream or left blank.
_EXTENSION_CONTENT_TYPES = {".heic": "image/heic", ".heif": "image/heif"}


def _resolve_content_type(file: UploadFile) -> str | None:
    if file.content_type in ALLOWED_CONTENT_TYPES:
        return file.content_type
    return _EXTENSION_CONTENT_TYPES.get(Path(file.filename or "").suffix.lower())


def _slugify(filename: str) -> str:
    stem = Path(filename).stem.lower()
    slug = _SLUG_RE.sub("-", stem).strip("-")[:40]
    return slug or "image"


def storage_dir() -> Path:
    """The image directory. Created once at startup (see
    app.main.lifespan) rather than here — this is called on every upload,
    delete and, in local dev, every image read, and mkdir is a blocking
    syscall."""
    return Path(settings.image_storage_path)


def stored_path(key: str) -> Path | None:
    """The file behind `key`, or None when it is missing or `key` is not a
    plain filename."""
    path = storage_dir() / key
    # `key` is flat by construction (see save_upload), so a key carrying any
    # "/" or ".." can only be a traversal attempt — comparing the resolved
    # name back to the key rejects it without touching the filesystem layout.
    if path.name != key or not path.is_file():
        return None
    return path


async def save_upload(file: UploadFile, *, category: str, alt: str = "", sort_order: int = 0) -> Image:
    resolved_content_type = _resolve_content_type(file)
    ext = ALLOWED_CONTENT_TYPES.get(resolved_content_type or "")
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"content type must be one of {sorted(ALLOWED_CONTENT_TYPES)}",
        )

    body = await file.read()
    if not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="File is empty")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )

    compressed, width, height = compress_image(body, ext)

    # Flat filename (no "/"), so `key` can never escape the storage dir.
    key = f"{category}-{_slugify(file.filename or '')}-{secrets.token_hex(8)}.{ext}"
    (storage_dir() / key).write_bytes(compressed)

    image = Image(
        key=key,
        category=category,
        # The output format (OUTPUT_CONTENT_TYPES[ext]), not the client's
        # original claim — for HEIC/HEIF input these differ, since
        # compress_image() always converts them to JPEG.
        content_type=OUTPUT_CONTENT_TYPES[ext],
        size_bytes=len(compressed),
        width=width,
        height=height,
        alt=alt,
        sort_order=sort_order,
    )
    await image.insert()
    return image


async def delete_stored(image: Image) -> None:
    (storage_dir() / image.key).unlink(missing_ok=True)
    await image.delete()
