from fastapi import APIRouter, Depends

from app.api.common import get_or_404
from app.api.crud import make_crud_router
from app.api.deps import require_admin
from app.models.cancellation_policy import CancellationPolicy
from app.models.plan import Plan
from app.schemas.plan import PlanCreate


async def _with_resolved_policy(payload: PlanCreate) -> dict:
    """Swaps the incoming cancellation_policy_id for the linked document."""
    policy = await get_or_404(CancellationPolicy, payload.cancellation_policy_id, "Cancellation policy")
    return {
        "name": payload.name,
        "cancellation_policy": policy,
        "price_ratio": payload.price_ratio,
    }


router: APIRouter = make_crud_router(
    model=Plan,
    create_schema=PlanCreate,
    prefix="/plans",
    noun="Plan",
    id_param="plan_id",
    tags=["plans"],
    dependencies=[Depends(require_admin)],
    fetch_links=True,
    transform_payload=_with_resolved_policy,
)

# Unauthenticated: lets the booking widget look up pricing and the
# applicable cancellation policy without an admin session. Mounted ahead of
# `router` in main.py so "/plans/public" is matched before "/plans/{plan_id}".
public_router = APIRouter(prefix="/plans", tags=["plans"])


@public_router.get("/public", response_model=list[Plan])
async def list_public_plans() -> list[Plan]:
    return await Plan.find_all(fetch_links=True).to_list()
