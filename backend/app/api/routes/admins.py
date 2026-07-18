from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_admin
from app.core.identifiers import normalize_phone_number
from app.models.admin import Admin
from app.schemas.admin import AdminCreate

router = APIRouter(prefix="/admins", tags=["admins"], dependencies=[Depends(require_admin)])


def _normalize_phone(raw: str) -> str:
    try:
        return normalize_phone_number(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("", response_model=Admin, status_code=status.HTTP_201_CREATED)
async def create_admin(payload: AdminCreate) -> Admin:
    data = payload.model_dump()
    data["phone_number"] = _normalize_phone(data["phone_number"])
    admin = Admin(**data)
    await admin.insert()
    return admin


@router.get("", response_model=list[Admin])
async def list_admins() -> list[Admin]:
    return await Admin.find_all().to_list()


@router.get("/{admin_id}", response_model=Admin)
async def get_admin(admin_id: PydanticObjectId) -> Admin:
    admin = await Admin.get(admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")
    return admin


@router.put("/{admin_id}", response_model=Admin)
async def update_admin(admin_id: PydanticObjectId, payload: AdminCreate) -> Admin:
    admin = await Admin.get(admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")
    admin.family_name = payload.family_name
    admin.first_name = payload.first_name
    admin.phone_number = _normalize_phone(payload.phone_number)
    admin.email = payload.email
    await admin.save()
    return admin


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(admin_id: PydanticObjectId) -> None:
    admin = await Admin.get(admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")
    await admin.delete()
