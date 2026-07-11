from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, status

from app.models.cancellation_policy import CancellationPolicy
from app.schemas.cancellation_policy import CancellationPolicyCreate

router = APIRouter(prefix="/cancellation-policies", tags=["cancellation-policies"])


@router.post("", response_model=CancellationPolicy, status_code=status.HTTP_201_CREATED)
async def create_cancellation_policy(payload: CancellationPolicyCreate) -> CancellationPolicy:
    policy = CancellationPolicy(**payload.model_dump())
    await policy.insert()
    return policy


@router.get("", response_model=list[CancellationPolicy])
async def list_cancellation_policies() -> list[CancellationPolicy]:
    return await CancellationPolicy.find_all().to_list()


@router.get("/{policy_id}", response_model=CancellationPolicy)
async def get_cancellation_policy(policy_id: PydanticObjectId) -> CancellationPolicy:
    policy = await CancellationPolicy.get(policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cancellation policy not found")
    return policy


@router.put("/{policy_id}", response_model=CancellationPolicy)
async def update_cancellation_policy(
    policy_id: PydanticObjectId, payload: CancellationPolicyCreate
) -> CancellationPolicy:
    policy = await CancellationPolicy.get(policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cancellation policy not found")
    policy.name = payload.name
    policy.rules = payload.rules
    await policy.save()
    return policy


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cancellation_policy(policy_id: PydanticObjectId) -> None:
    policy = await CancellationPolicy.get(policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cancellation policy not found")
    await policy.delete()
