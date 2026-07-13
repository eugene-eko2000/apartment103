from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, status

from app.models.admin import Admin
from app.schemas.admin import AdminCreate

router = APIRouter(prefix="/admins", tags=["admins"])


@router.post("", response_model=Admin, status_code=status.HTTP_201_CREATED)
async def create_admin(payload: AdminCreate) -> Admin:
    admin = Admin(**payload.model_dump())
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
    admin.phone_number = payload.phone_number
    admin.email = payload.email
    await admin.save()
    return admin


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(admin_id: PydanticObjectId) -> None:
    admin = await Admin.get(admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")
    await admin.delete()
