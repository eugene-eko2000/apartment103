from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pymongo import UpdateOne

from app.api.deps import require_admin
from app.models.category import Category
from app.models.image import MESSAGE_IMAGE_CATEGORY, Image
from app.schemas.image import LabelInput, ReorderRequest
from app.services.image_storage import delete_stored, save_upload, stored_path

router = APIRouter(prefix="/images", tags=["images"], dependencies=[Depends(require_admin)])

# Unauthenticated: the frontend fetches image metadata (key/alt/category) to
# render galleries without an admin session, matching the pattern used for
# "/closures/public/...".
public_router = APIRouter(prefix="/images", tags=["images"])


@public_router.get("", response_model=list[Image])
async def list_images(category: str | None = None) -> list[Image]:
    # Images attached to guest messages live in the same collection but are
    # not part of the photo library, so an unfiltered listing leaves them out.
    query = (
        Image.find(Image.category == category)
        if category
        else Image.find(Image.category != MESSAGE_IMAGE_CATEGORY)
    )
    return await query.sort(+Image.sort_order).to_list()


# Registered ahead of GET "/{key}" below: without a label segment this would
# be a single path segment too ("/images/labels" vs "/images/{key}"), so
# it's kept two-segment-only ("/images/labels/{label}") to never collide —
# see the routing note on get_image_file.
@public_router.get("/labels/{label}", response_model=list[Image])
async def list_images_by_label(label: str) -> list[Image]:
    normalized = label.strip().lower()
    return await Image.find(Image.labels == normalized).sort(+Image.sort_order).to_list()


def _stored_file(key: str):
    path = stored_path(key)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return path


# Two segments, so it never collides with GET "/{key}" below. It is public for
# the same reason that route is: the bytes it returns are already served
# unauthenticated at "/images/<key>" — the only thing added here is the
# Content-Disposition that makes a browser save the file instead of showing
# it. (Kept out of reach of a plain navigation's inability to send the admin
# bearer token, which is what the admin panel's bulk download relies on.)
@public_router.get("/{key}/download")
async def download_image_file(key: str) -> FileResponse:
    return FileResponse(
        _stored_file(key),
        # The stored key is already a unique, extension-carrying filename, so
        # a bulk download of many photos never collides in the browser's
        # download folder.
        filename=key,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@public_router.get("/{key}")
async def get_image_file(key: str) -> FileResponse:
    # In production nginx serves /images/<key> directly from the shared
    # volume (see deploy/nginx/templates/default.conf.template) and this
    # route is never reached. It exists so the same URL works in local dev,
    # where the frontend talks to uvicorn directly with no nginx in front.
    # The "/download" variant above is two segments, so nginx's
    # single-segment image regex does not match it and it always reaches
    # FastAPI, in dev and in production alike.
    #
    # This single-segment pattern matches anything, including "/images/labels"
    # — that's exactly why list_images_by_label above requires a label
    # segment (`/images/labels/{label}`, never a bare `/images/labels`): a
    # bare route would be a coin flip depending on router registration order
    # in main.py. Keep it that way if you add more label routes.
    return FileResponse(
        _stored_file(key), headers={"Cache-Control": "public, max-age=31536000, immutable"}
    )


@router.post("", response_model=Image, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    category: str = Form(...),
    alt: str = Form(""),
    sort_order: int | None = Form(None),
) -> Image:
    if not await Category.find_one(Category.slug == category):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unknown category",
        )
    if sort_order is None:
        last = await Image.find(Image.category == category).sort(-Image.sort_order).first_or_none()
        sort_order = (last.sort_order + 1) if last else 0
    return await save_upload(file, category=category, alt=alt, sort_order=sort_order)


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
    await delete_stored(image)


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
