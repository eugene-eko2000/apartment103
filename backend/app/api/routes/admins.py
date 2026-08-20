from fastapi import APIRouter, Depends

from app.api.crud import make_crud_router
from app.api.deps import require_admin
from app.core.identifiers import normalize_identifier
from app.api.common import normalize_phone_or_400
from app.models.admin import Admin
from app.schemas.admin import AdminCreate


async def _normalized(payload: AdminCreate) -> dict:
    """Phone to E.164, email lowercased.

    Both matter for login, which resolves an identifier to an Admin with an
    exact match on the stored value (see
    app.api.routes.auth._find_principal) — an address stored with capitals,
    or a number stored as typed, would simply never resolve.
    """
    return {
        **payload.model_dump(),
        "phone_number": normalize_phone_or_400(payload.phone_number),
        "email": normalize_identifier(payload.email, "email"),
    }


router: APIRouter = make_crud_router(
    model=Admin,
    create_schema=AdminCreate,
    prefix="/admins",
    noun="Admin",
    id_param="admin_id",
    tags=["admins"],
    dependencies=[Depends(require_admin)],
    transform_payload=_normalized,
)
