import re
import secrets
from pathlib import Path

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pymongo import UpdateOne

from app.api.deps import require_admin
from app.core.config import settings
from app.models.category import Category
from app.models.image import Image
from app.schemas.image import (
    ALLOWED_CONTENT_TYPES,
    OUTPUT_CONTENT_TYPES,
    LabelInput,
    ReorderRequest,
)
from app.services.image_processing import compress_image

router = APIRouter(prefix="/images", tags=["images"], dependencies=[Depends(require_admin)])

# Unauthenticated: the frontend fetches image metadata (key/alt/category) to
# render galleries without an admin session, matching the pattern used for
# "/closures/public/...".
public_router = APIRouter(prefix="/images", tags=["images"])

# Raw upload cap, ahead of compression — generous enough for an
# uncompressed phone/DSLR photo. The file actually written to disk is the
# recompressed, downsized output from compress_image(), which lands far
# below this.
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
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


def _storage_dir() -> Path:
    path = Path(settings.image_storage_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


@public_router.get("", response_model=list[Image])
async def list_images(category: str | None = None) -> list[Image]:
    query = Image.find(Image.category == category) if category else Image.find_all()
    return await query.sort(+Image.sort_order).to_list()


# Registered ahead of GET "/{key}" below: without a label segment this would
# be a single path segment too ("/images/labels" vs "/images/{key}"), so
# it's kept two-segment-only ("/images/labels/{label}") to never collide —
# see the routing note on get_image_file.
@public_router.get("/labels/{label}", response_model=list[Image])
async def list_images_by_label(label: str) -> list[Image]:
    normalized = label.strip().lower()
    return await Image.find(Image.labels == normalized).sort(+Image.sort_order).to_list()


@public_router.get("/{key}")
async def get_image_file(key: str) -> FileResponse:
    # In production nginx serves /images/<key> directly from the shared
    # volume (see deploy/nginx/templates/default.conf.template) and this
    # route is never reached. It exists so the same URL works in local dev,
    # where the frontend talks to uvicorn directly with no nginx in front.
    #
    # This single-segment pattern matches anything, including "/images/labels"
    # — that's exactly why list_images_by_label above requires a label
    # segment (`/images/labels/{label}`, never a bare `/images/labels`): a
    # bare route would be a coin flip depending on router registration order
    # in main.py. Keep it that way if you add more label routes.
    path = _storage_dir() / key
    if path.name != key or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.post("", response_model=Image, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    category: str = Form(...),
    alt: str = Form(""),
    sort_order: int | None = Form(None),
) -> Image:
    if not await Category.find_one(Category.slug == category):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown category",
        )
    if sort_order is None:
        last = await Image.find(Image.category == category).sort(-Image.sort_order).first_or_none()
        sort_order = (last.sort_order + 1) if last else 0
    resolved_content_type = _resolve_content_type(file)
    ext = ALLOWED_CONTENT_TYPES.get(resolved_content_type or "")
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"content type must be one of {sorted(ALLOWED_CONTENT_TYPES)}",
        )

    body = await file.read()
    if not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File is empty")
    if len(body) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )

    compressed, width, height = compress_image(body, ext)

    # Flat filename (no "/"), so `key` can never escape the storage dir.
    key = f"{category}-{_slugify(file.filename or '')}-{secrets.token_hex(8)}.{ext}"
    (_storage_dir() / key).write_bytes(compressed)

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


@router.post("/reorder", response_model=list[Image])
async def reorder_images(payload: ReorderRequest) -> list[Image]:
    """Bulk-persist an arrangement: same-category drag reorder and
    cross-category moves both just resend every affected image's
    (category, sort_order) in one shot, so this single endpoint covers both.
    """
    if not payload.updates:
        return []
    ops = [
        UpdateOne({"_id": update.id}, {"$set": {"category": update.category, "sort_order": update.sort_order}})
        for update in payload.updates
    ]
    await Image.get_pymongo_collection().bulk_write(ops)
    ids = [update.id for update in payload.updates]
    return await Image.find({"_id": {"$in": ids}}).sort(+Image.sort_order).to_list()


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(image_id: PydanticObjectId) -> None:
    image = await Image.get(image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    (_storage_dir() / image.key).unlink(missing_ok=True)
    await image.delete()


@router.post("/{image_id}/labels", response_model=Image)
async def add_image_label(image_id: PydanticObjectId, payload: LabelInput) -> Image:
    image = await Image.get(image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    if payload.label not in image.labels:
        image.labels.append(payload.label)
        await image.save()
    return image


@router.delete("/{image_id}/labels/{label}", response_model=Image)
async def remove_image_label(image_id: PydanticObjectId, label: str) -> Image:
    image = await Image.get(image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    normalized = label.strip().lower()
    if normalized in image.labels:
        image.labels.remove(normalized)
        await image.save()
    return image
