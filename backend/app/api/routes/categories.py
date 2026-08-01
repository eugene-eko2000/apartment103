from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_admin
from app.models.category import Category
from app.models.image import Image
from app.schemas.category import CategoryCreate, CategoryUpdate

# Categories are only ever read/written from the admin Photos panel — the
# public site resolves photos by stable label (see app/api/routes/images.py),
# never by category — so this router is admin-only, no public counterpart.
router = APIRouter(prefix="/categories", tags=["categories"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[Category])
async def list_categories() -> list[Category]:
    return await Category.find_all().sort(+Category.sort_order).to_list()


@router.post("", response_model=Category, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryCreate) -> Category:
    if await Category.find_one(Category.slug == payload.slug):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A category with this slug already exists"
        )
    last = await Category.find_all().sort(-Category.sort_order).first_or_none()
    category = Category(slug=payload.slug, name=payload.name, sort_order=(last.sort_order + 1) if last else 0)
    await category.insert()
    return category


@router.patch("/{category_id}", response_model=Category)
async def update_category(category_id: PydanticObjectId, payload: CategoryUpdate) -> Category:
    category = await Category.get(category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    category.name = payload.name
    await category.save()
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: PydanticObjectId) -> None:
    category = await Category.get(category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    in_use = await Image.find(Image.category == category.slug).count()
    if in_use > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category still has photos; move or delete them first",
        )
    await category.delete()
