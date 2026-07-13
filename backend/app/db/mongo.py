from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.core.config import settings
from app.models.admin import Admin
from app.models.booking import Booking
from app.models.cancellation_policy import CancellationPolicy
from app.models.guest import Guest
from app.models.otp_challenge import OtpChallenge
from app.models.plan import Plan


async def init_mongo() -> None:
    client = AsyncMongoClient(settings.mongo_uri)
    await init_beanie(
        database=client[settings.mongo_db],
        document_models=[CancellationPolicy, Plan, Guest, Admin, Booking, OtpChallenge],
    )
