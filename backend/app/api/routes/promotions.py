from datetime import date

from fastapi import APIRouter, Depends

from app.api.crud import make_crud_router
from app.api.deps import require_admin
from app.models.guest import Currency
from app.models.promotion import Promotion
from app.schemas.promotion import PromotionCreate, PublicPromotion
from app.services.currency_service import convert_amount_with_rates, rates_for

router: APIRouter = make_crud_router(
    model=Promotion,
    create_schema=PromotionCreate,
    prefix="/promotions",
    noun="Promotion",
    id_param="promotion_id",
    tags=["promotions"],
    dependencies=[Depends(require_admin)],
    sort="begin_date",
)

# Unauthenticated: lets the guest calendar highlight promoted days (and show
# what the offer is) without a session. Mounted ahead of `router` in main.py
# so "/promotions/public" is matched before "/promotions/{promotion_id}".
public_router = APIRouter(prefix="/promotions", tags=["promotions"])


@public_router.get("/public", response_model=list[PublicPromotion])
async def list_public_promotions(currency: Currency = "CHF") -> list[PublicPromotion]:
    # Inactive offers are parked by the admin and expired ones can no longer
    # apply to any bookable stay, so neither belongs in the calendar.
    promotions = (
        await Promotion.find(Promotion.active == True, Promotion.end_date >= date.today())  # noqa: E712
        .sort("begin_date")
        .to_list()
    )
    # One rate lookup for the whole response rather than two awaits per
    # promotion — and none at all when nothing needs converting (see
    # app.services.currency_service.rates_for).
    rates = await rates_for({promotion.currency for promotion in promotions}, currency, "CHF")
    return [
        PublicPromotion(
            id=promotion.id,
            name=promotion.name,
            begin_date=promotion.begin_date,
            end_date=promotion.end_date,
            discount_type=promotion.discount_type,
            discount_ratio=promotion.discount_ratio,
            discount_amount=convert_amount_with_rates(
                promotion.discount_amount, promotion.currency, currency, rates
            ),
            discount_amount_chf=convert_amount_with_rates(
                promotion.discount_amount, promotion.currency, "CHF", rates
            ),
            min_stay_days=promotion.min_stay_days,
        )
        for promotion in promotions
    ]
