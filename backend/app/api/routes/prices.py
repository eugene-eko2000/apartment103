from fastapi import APIRouter, Depends

from app.api.crud import make_crud_router
from app.api.deps import require_admin
from app.models.guest import Currency
from app.models.price import Price
from app.schemas.price import PriceCreate, PublicDateRangeRate, PublicPeriod, PublicPrice
from app.services.currency_service import convert_amount_with_rates, rates_for

router: APIRouter = make_crud_router(
    model=Price,
    create_schema=PriceCreate,
    prefix="/prices",
    noun="Price",
    id_param="price_id",
    tags=["prices"],
    dependencies=[Depends(require_admin)],
    sort="period.begin_date",
)

# Unauthenticated: lets the booking widget look up nightly rates without an
# admin session. Mounted ahead of `router` in main.py so "/prices/public" is
# matched before "/prices/{price_id}".
public_router = APIRouter(prefix="/prices", tags=["prices"])


@public_router.get("/public", response_model=list[PublicPrice])
async def list_public_prices(currency: Currency = "CHF") -> list[PublicPrice]:
    prices = await Price.find_all().sort("period.begin_date").to_list()
    # One rate lookup for the whole response rather than two awaits per
    # date range — and none at all when nothing needs converting (see
    # app.services.currency_service.rates_for).
    rates = await rates_for({price.period.currency for price in prices}, currency, "CHF")
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
                        daily_rate=convert_amount_with_rates(
                            date_range.daily_rate, price.period.currency, currency, rates
                        ),
                        daily_rate_chf=convert_amount_with_rates(
                            date_range.daily_rate, price.period.currency, "CHF", rates
                        ),
                    )
                    for date_range in price.period.date_ranges
                ],
            ),
        )
        for price in prices
    ]
