from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.core.config import settings
from app.models.cancellation_policy import CancellationPolicy
from app.models.plan import Plan


async def init_mongo() -> None:
    client = AsyncMongoClient(settings.mongo_uri)
    await init_beanie(
        database=client[settings.mongo_db],
        document_models=[CancellationPolicy, Plan],
    )
