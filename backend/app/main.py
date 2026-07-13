from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import (
    admins,
    bookings,
    cancellation_policies,
    guests,
    health,
    plans,
)
from app.core.config import settings
from app.db.mongo import init_mongo


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongo()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router)
app.include_router(plans.router)
app.include_router(cancellation_policies.router)
app.include_router(guests.router)
app.include_router(admins.router)
app.include_router(bookings.router)
