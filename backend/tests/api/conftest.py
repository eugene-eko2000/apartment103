from datetime import date
from decimal import Decimal

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
from app.models.category import Category  # noqa: E402
from app.models.closure import Closure  # noqa: E402
from app.models.external_calendar import ExternalCalendar  # noqa: E402
from app.models.guest import Guest, ResidenceAddress  # noqa: E402
from app.models.image import Image  # noqa: E402
from app.models.plan import Plan  # noqa: E402
from app.models.price import DateRangeRate, Period, Price  # noqa: E402
from app.services import currency_service  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def _reset_database():
    """Empty every collection between tests, rather than dropping the whole
    database.

    Same isolation, but the collections — and therefore the indexes
    init_beanie creates from each model's Settings.indexes — survive. That
    matters twice over: dropping the database made every test pay to rebuild
    the full index set (roughly 4x the suite's runtime), and it meant tests
    ran against a database with no unique constraints at all, so a
    duplicate-key path could never be exercised.
    """
    mongo_client = AsyncMongoClient(settings.mongo_uri)
    database = mongo_client[settings.mongo_db]
    for name in await database.list_collection_names():
        await database[name].delete_many({})
    await mongo_client.close()
    yield


@pytest.fixture(autouse=True)
def fixed_currency_conversion(monkeypatch):
    """Make every currency conversion in a route test deterministic.

    Booking prices are derived server-side now (see
    app.services.booking_pricing), so any non-CHF booking performs a real
    conversion — which without this would mean a live Stripe FX Quotes call
    from the suite. The rates are deliberately round rather than realistic,
    so a converted amount can be verified by hand; they mirror the table in
    tests/test_currency_service.py.

    commission_rate is pinned alongside them because it is a deployment
    setting read from .env, and a converted amount asserted in a test would
    otherwise depend on whatever the machine running it happens to have
    configured.
    """

    async def fake_get_exchange_rates():
        return {
            "CHF": Decimal("1"),
            "EUR": Decimal("2"),
            "USD": Decimal("4"),
            "GBP": Decimal("0.8"),
        }

    monkeypatch.setattr(currency_service, "get_exchange_rates", fake_get_exchange_rates)
    monkeypatch.setattr(settings, "commission_rate", Decimal("0.06"))


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
async def price(client) -> Price:
    """A nightly rate covering the dates the booking tests use. This is the
    server's authority for what a stay costs (see
    app.services.booking_pricing), so any test creating a booking through
    the guest/plan path needs it in place."""
    price = Price(
        period=Period(
            begin_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            currency="CHF",
            date_ranges=[
                DateRangeRate(
                    begin_date=date(2026, 1, 1),
                    end_date=date(2026, 12, 31),
                    daily_rate=Decimal("200.00"),
                    min_stay_days=1,
                )
            ],
        )
    )
    await price.insert()
    return price


@pytest.fixture
async def plan(client, cancellation_policy) -> Plan:
    """A plan at half the nightly rate — deliberately not 1.0, so a test
    asserting a computed price can tell "the ratio was applied" apart from
    "the raw rate was used"."""
    plan = Plan(name="Half Price", cancellation_policy=cancellation_policy, price_ratio=0.5)
    await plan.insert()
    return plan


@pytest.fixture
async def closure(client) -> Closure:
    closure = Closure(platform="airbnb", begin_date=date(2026, 8, 1), end_date=date(2026, 8, 5))
    await closure.insert()
    return closure


@pytest.fixture
async def external_calendar(client) -> ExternalCalendar:
    calendar = ExternalCalendar(
        name="Airbnb",
        url="https://www.airbnb.com/calendar/ical/12345.ics?s=secret",
        export_token="test-export-token-airbnb",
    )
    await calendar.insert()
    return calendar


@pytest.fixture
async def other_external_calendar(client) -> ExternalCalendar:
    calendar = ExternalCalendar(
        name="Booking.com",
        url="https://admin.booking.com/hotel/hoteladmin/ical.html?t=secret",
        export_token="test-export-token-booking",
    )
    await calendar.insert()
    return calendar


@pytest.fixture
async def category(client) -> Category:
    category = Category(slug="gallery", name="Gallery", sort_order=0)
    await category.insert()
    return category


@pytest.fixture
async def image(client, category) -> Image:
    image = Image(
        key="gallery-test-photo-abc123.jpg",
        category=category.slug,
        content_type="image/jpeg",
        size_bytes=1024,
        alt="Test photo",
        sort_order=0,
    )
    await image.insert()
    return image


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
