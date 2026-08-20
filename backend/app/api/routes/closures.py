from fastapi import APIRouter, Depends

from app.api.crud import make_crud_router
from app.api.deps import require_admin
from app.models.closure import Closure
from app.schemas.closure import ClosedDateRange, ClosureCreate

router: APIRouter = make_crud_router(
    model=Closure,
    create_schema=ClosureCreate,
    prefix="/closures",
    noun="Closure",
    id_param="closure_id",
    tags=["closures"],
    dependencies=[Depends(require_admin)],
)

# Unauthenticated: lets the guest calendar disable dates blocked on other
# platforms without an admin session. Mounted ahead of `router` in main.py,
# matching the pattern used for "/bookings/public/...".
public_router = APIRouter(prefix="/closures", tags=["closures"])


@public_router.get("/public/date-ranges", response_model=list[ClosedDateRange])
async def list_public_closed_date_ranges() -> list[ClosedDateRange]:
    # ClosedDateRange doubles as the projection model, so `platform` never
    # leaves the database for this anonymous endpoint.
    return await Closure.find_all(projection_model=ClosedDateRange).to_list()
