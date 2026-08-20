"""GET /payment-events/{stripe_event_id}.

A booking's `webhook_events` entries are references, not copies (see
app.models.booking.BookingWebhookEvent) — this is how the admin panel
resolves one back to its raw Stripe payload.
"""

from datetime import datetime, timezone

import pytest

from app.models.payment_event import PaymentEvent

pytestmark = pytest.mark.anyio


@pytest.fixture
async def payment_event(client) -> PaymentEvent:
    event = PaymentEvent(
        stripe_event_id="evt_lookup_1",
        event_type="payment_intent.succeeded",
        processed_at=datetime.now(timezone.utc),
        data={"id": "pi_lookup_1", "amount": 12345},
    )
    await event.insert()
    return event


class TestGetPaymentEvent:
    async def test_returns_raw_payload(self, client, payment_event, admin_headers):
        response = await client.get(f"/payment-events/{payment_event.stripe_event_id}", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["event_type"] == "payment_intent.succeeded"
        assert body["data"] == {"id": "pi_lookup_1", "amount": 12345}

    async def test_returns_404_for_unknown_event(self, client, admin_headers):
        response = await client.get("/payment-events/evt_does_not_exist", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_admin(self, client, payment_event, guest_headers):
        response = await client.get(f"/payment-events/{payment_event.stripe_event_id}", headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client, payment_event):
        response = await client.get(f"/payment-events/{payment_event.stripe_event_id}")
        assert response.status_code == 401
