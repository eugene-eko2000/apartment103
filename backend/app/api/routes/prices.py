from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_admin
from app.models.price import Price
from app.schemas.price import PriceCreate

router = APIRouter(prefix="/prices", tags=["prices"], dependencies=[Depends(require_admin)])

# Unauthenticated: lets the booking widget look up nightly rates without an
# admin session. Mounted ahead of `router` in main.py so "/prices/public" is
# matched before "/prices/{price_id}".
public_router = APIRouter(prefix="/prices", tags=["prices"])


@public_router.get("/public", response_model=list[Price])
async def list_public_prices() -> list[Price]:
    return await Price.find_all().to_list()


@router.post("", response_model=Price, status_code=status.HTTP_201_CREATED)
async def create_price(payload: PriceCreate) -> Price:
    price = Price(period=payload.period)
    await price.insert()
    return price


@router.get("", response_model=list[Price])
async def list_prices() -> list[Price]:
    return await Price.find_all().to_list()


@router.get("/{price_id}", response_model=Price)
async def get_price(price_id: PydanticObjectId) -> Price:
    price = await Price.get(price_id)
    if price is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price not found")
    return price


@router.put("/{price_id}", response_model=Price)
async def update_price(price_id: PydanticObjectId, payload: PriceCreate) -> Price:
    price = await Price.get(price_id)
    if price is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price not found")
    price.period = payload.period
    await price.save()
    return price


@router.delete("/{price_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_price(price_id: PydanticObjectId) -> None:
    price = await Price.get(price_id)
    if price is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price not found")
    await price.delete()
