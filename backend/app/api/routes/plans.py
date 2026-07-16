from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_admin
from app.models.cancellation_policy import CancellationPolicy
from app.models.plan import Plan
from app.schemas.plan import PlanCreate

router = APIRouter(prefix="/plans", tags=["plans"], dependencies=[Depends(require_admin)])

# Unauthenticated: lets the booking widget look up pricing and the
# applicable cancellation policy without an admin session. Mounted ahead of
# `router` in main.py so "/plans/public" is matched before "/plans/{plan_id}".
public_router = APIRouter(prefix="/plans", tags=["plans"])


async def _get_cancellation_policy_or_404(policy_id: PydanticObjectId) -> CancellationPolicy:
    policy = await CancellationPolicy.get(policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cancellation policy not found")
    return policy


@public_router.get("/public", response_model=list[Plan])
async def list_public_plans() -> list[Plan]:
    return await Plan.find_all(fetch_links=True).to_list()


@router.post("", response_model=Plan, status_code=status.HTTP_201_CREATED)
async def create_plan(payload: PlanCreate) -> Plan:
    cancellation_policy = await _get_cancellation_policy_or_404(payload.cancellation_policy_id)
    plan = Plan(
        name=payload.name,
        cancellation_policy=cancellation_policy,
        price_ratio=payload.price_ratio,
    )
    await plan.insert()
    return plan


@router.get("", response_model=list[Plan])
async def list_plans() -> list[Plan]:
    return await Plan.find_all(fetch_links=True).to_list()


@router.get("/{plan_id}", response_model=Plan)
async def get_plan(plan_id: PydanticObjectId) -> Plan:
    plan = await Plan.get(plan_id, fetch_links=True)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


@router.put("/{plan_id}", response_model=Plan)
async def update_plan(plan_id: PydanticObjectId, payload: PlanCreate) -> Plan:
    plan = await Plan.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    cancellation_policy = await _get_cancellation_policy_or_404(payload.cancellation_policy_id)
    plan.name = payload.name
    plan.cancellation_policy = cancellation_policy
    plan.price_ratio = payload.price_ratio
    await plan.save()
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(plan_id: PydanticObjectId) -> None:
    plan = await Plan.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    await plan.delete()
