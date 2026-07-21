from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.core.config import settings

# Route tests exercise the app against a real MongoDB instance (see
# docker-compose.yml) rather than a mock, since beanie's query builders and
# aggregation-based `fetch_links` behavior are not worth re-implementing in a
# fake. Point at a dedicated database so tests never touch dev data.
settings.mongo_db = "apartment103_test"

# 32+ bytes so PyJWT doesn't emit InsecureKeyLengthWarning for HS256 (RFC 7518 3.2).
settings.jwt_secret_key = "test-only-secret-key-please-do-not-use-in-prod"

from app.core.security import create_access_token  # noqa: E402
from app.db.mongo import init_mongo  # noqa: E402
from app.main import app  # noqa: E402
from app.models.admin import Admin  # noqa: E402
from app.models.cancellation_policy import CancellationPolicy, CancellationRule  # noqa: E402
from app.models.closure import Closure  # noqa: E402
from app.models.guest import Guest, ResidenceAddress  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def _reset_database():
    mongo_client = AsyncMongoClient(settings.mongo_uri)
    await mongo_client.drop_database(settings.mongo_db)
    await mongo_client.close()
    yield


@pytest.fixture
async def client():
    await init_mongo()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
async def admin(client) -> Admin:
    admin = Admin(
        family_name="Adminson",
        first_name="Ada",
        phone_number="+15550000001",
        email="admin@example.com",
    )
    await admin.insert()
    return admin


@pytest.fixture
async def other_admin(client) -> Admin:
    admin = Admin(
        family_name="Otherson",
        first_name="Otto",
        phone_number="+15550000099",
        email="other-admin@example.com",
    )
    await admin.insert()
    return admin


@pytest.fixture
async def guest(client) -> Guest:
    guest = Guest(
        family_name="Guestson",
        first_name="Gary",
        residence_address=ResidenceAddress(
            street_address="1 Main St",
            zip="12345",
            city="Springfield",
            country="US",
        ),
        phone_number="+15550000002",
        email="guest@example.com",
    )
    await guest.insert()
    return guest


@pytest.fixture
async def other_guest(client) -> Guest:
    guest = Guest(
        family_name="Bystander",
        first_name="Barb",
        residence_address=ResidenceAddress(
            street_address="2 Side St",
            zip="54321",
            city="Shelbyville",
            country="US",
        ),
        phone_number="+15550000003",
        email="other-guest@example.com",
    )
    await guest.insert()
    return guest


@pytest.fixture
async def cancellation_policy(client) -> CancellationPolicy:
    policy = CancellationPolicy(
        name="Flexible",
        rules=[CancellationRule(days_before_checkin=1, refund_percentage=1.0)],
    )
    await policy.insert()
    return policy


@pytest.fixture
async def closure(client) -> Closure:
    closure = Closure(platform="airbnb", begin_date=date(2026, 8, 1), end_date=date(2026, 8, 5))
    await closure.insert()
    return closure


def _auth_headers(subject_id: str, subject_type: str) -> dict[str, str]:
    token, _ = create_access_token(subject_id, subject_type)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin) -> dict[str, str]:
    return _auth_headers(str(admin.id), "admin")


@pytest.fixture
def other_admin_headers(other_admin) -> dict[str, str]:
    return _auth_headers(str(other_admin.id), "admin")


@pytest.fixture
def guest_headers(guest) -> dict[str, str]:
    return _auth_headers(str(guest.id), "guest")


@pytest.fixture
def other_guest_headers(other_guest) -> dict[str, str]:
    return _auth_headers(str(other_guest.id), "guest")
