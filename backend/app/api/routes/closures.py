from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_admin
from app.models.closure import Closure
from app.schemas.closure import ClosedDateRange, ClosureCreate

router = APIRouter(
    prefix="/closures",
    tags=["closures"],
    dependencies=[Depends(require_admin)],
)

# Unauthenticated: lets the guest calendar disable dates blocked on other
# platforms without an admin session. Mounted ahead of `router` in main.py,
# matching the pattern used for "/bookings/public/...".
public_router = APIRouter(prefix="/closures", tags=["closures"])


@public_router.get("/public/date-ranges", response_model=list[ClosedDateRange])
async def list_public_closed_date_ranges() -> list[ClosedDateRange]:
    closures = await Closure.find_all().to_list()
    return [ClosedDateRange(begin_date=c.begin_date, end_date=c.end_date) for c in closures]


@router.post("", response_model=Closure, status_code=status.HTTP_201_CREATED)
async def create_closure(payload: ClosureCreate) -> Closure:
    closure = Closure(**payload.model_dump())
    await closure.insert()
    return closure


@router.get("", response_model=list[Closure])
async def list_closures() -> list[Closure]:
    return await Closure.find_all().to_list()


@router.get("/{closure_id}", response_model=Closure)
async def get_closure(closure_id: PydanticObjectId) -> Closure:
    closure = await Closure.get(closure_id)
    if closure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Closure not found")
    return closure


@router.put("/{closure_id}", response_model=Closure)
async def update_closure(closure_id: PydanticObjectId, payload: ClosureCreate) -> Closure:
    closure = await Closure.get(closure_id)
    if closure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Closure not found")
    closure.platform = payload.platform
    closure.begin_date = payload.begin_date
    closure.end_date = payload.end_date
    await closure.save()
    return closure


@router.delete("/{closure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_closure(closure_id: PydanticObjectId) -> None:
    closure = await Closure.get(closure_id)
    if closure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Closure not found")
    await closure.delete()
