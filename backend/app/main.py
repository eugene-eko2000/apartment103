import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admins,
    auth,
    bookings,
    cancellation_policies,
    guests,
    health,
    plans,
    prices,
)
from app.core.config import settings
from app.db.mongo import init_mongo

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongo()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(plans.public_router)
app.include_router(plans.router)
app.include_router(prices.public_router)
app.include_router(prices.router)
app.include_router(cancellation_policies.router)
app.include_router(guests.router)
app.include_router(admins.router)
app.include_router(bookings.router)
