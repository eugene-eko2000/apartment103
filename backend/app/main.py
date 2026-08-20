import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admins,
    auth,
    bookings,
    cancellation_policies,
    categories,
    closures,
    guests,
    health,
    images,
    payment_events,
    payments,
    plans,
    prices,
)
from app.core.config import settings
from app.db.mongo import init_mongo
from app.jobs.reconcile_payments import scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongo()
    # Once, here, rather than on every upload/delete/read — see
    # app.api.routes.images._storage_dir.
    Path(settings.image_storage_path).mkdir(parents=True, exist_ok=True)
    start_scheduler()
    yield
    scheduler.shutdown(wait=False)


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
app.include_router(categories.router)
app.include_router(guests.router)
app.include_router(admins.router)
app.include_router(bookings.public_router)
app.include_router(bookings.router)
app.include_router(closures.public_router)
app.include_router(closures.router)
app.include_router(payments.router)
app.include_router(payments.webhook_router)
app.include_router(payment_events.router)
app.include_router(images.public_router)
app.include_router(images.router)
