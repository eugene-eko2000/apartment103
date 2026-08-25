from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.core.config import settings
from app.models.admin import Admin
from app.models.booking import Booking
from app.models.cancellation_policy import CancellationPolicy
from app.models.category import Category
from app.models.closure import Closure
from app.models.external_calendar import ExternalCalendar
from app.models.guest import Guest
from app.models.image import Image
from app.models.otp_challenge import OtpChallenge
from app.models.payment_event import PaymentEvent
from app.models.plan import Plan
from app.models.price import Price
from app.models.promotion import Promotion


async def init_mongo() -> None:
    # tz_aware=True is required so datetimes read back from MongoDB are
    # timezone-aware (UTC), matching datetime.now(timezone.utc) elsewhere in
    # the app (e.g. OTP expiry/cooldown comparisons in app/api/routes/auth.py).
    client = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
    await init_beanie(
        database=client[settings.mongo_db],
        document_models=[
            CancellationPolicy,
            Plan,
            Price,
            Guest,
            Admin,
            Booking,
            OtpChallenge,
            Closure,
            PaymentEvent,
            Image,
            Category,
            ExternalCalendar,
            Promotion,
        ],
    )
