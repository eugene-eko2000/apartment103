from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_admin
from app.models.guest import Currency
from app.models.price import Price
from app.schemas.price import PriceCreate, PublicDateRangeRate, PublicPeriod, PublicPrice
from app.services.currency_service import convert_amount

router = APIRouter(prefix="/prices", tags=["prices"], dependencies=[Depends(require_admin)])

# Unauthenticated: lets the booking widget look up nightly rates without an
# admin session. Mounted ahead of `router` in main.py so "/prices/public" is
# matched before "/prices/{price_id}".
public_router = APIRouter(prefix="/prices", tags=["prices"])


@public_router.get("/public", response_model=list[PublicPrice])
async def list_public_prices(currency: Currency = "CHF") -> list[PublicPrice]:
    prices = await Price.find_all().sort("period.begin_date").to_list()
    return [
        PublicPrice(
            id=price.id,
            period=PublicPeriod(
                begin_date=price.period.begin_date,
                end_date=price.period.end_date,
                currency=currency,
                date_ranges=[
                    PublicDateRangeRate(
                        begin_date=date_range.begin_date,
                        end_date=date_range.end_date,
                        min_stay_days=date_range.min_stay_days,
                        daily_rate=await convert_amount(date_range.daily_rate, price.period.currency, currency),
                        daily_rate_chf=await convert_amount(date_range.daily_rate, price.period.currency, "CHF"),
                    )
                    for date_range in price.period.date_ranges
                ],
            ),
        )
        for price in prices
    ]


@router.post("", response_model=Price, status_code=status.HTTP_201_CREATED)
async def create_price(payload: PriceCreate) -> Price:
    price = Price(period=payload.period)
    await price.insert()
    return price


@router.get("", response_model=list[Price])
async def list_prices() -> list[Price]:
    return await Price.find_all().sort("period.begin_date").to_list()


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
