from fastapi import APIRouter, Depends

from app.api.crud import make_crud_router
from app.api.deps import require_admin
from app.models.cancellation_policy import CancellationPolicy
from app.schemas.cancellation_policy import CancellationPolicyCreate

router: APIRouter = make_crud_router(
    model=CancellationPolicy,
    create_schema=CancellationPolicyCreate,
    prefix="/cancellation-policies",
    noun="Cancellation policy",
    id_param="policy_id",
    tags=["cancellation-policies"],
    dependencies=[Depends(require_admin)],
)
