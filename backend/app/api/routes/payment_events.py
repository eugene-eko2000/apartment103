from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_admin
from app.models.payment_event import PaymentEvent

# Admin-only: raw Stripe payloads are an operational audit trail, never
# guest-facing.
router = APIRouter(prefix="/payment-events", tags=["payment-events"], dependencies=[Depends(require_admin)])


@router.get("/{stripe_event_id}", response_model=PaymentEvent)
async def get_payment_event(stripe_event_id: str) -> PaymentEvent:
    """Fetch one webhook event by its Stripe id.

    A booking's own `webhook_events` list holds only references (id, type,
    timestamp) — see app.models.booking.BookingWebhookEvent — so the admin
    panel resolves the raw payload through here when an entry is expanded,
    rather than every booking carrying a copy of every payload it ever saw.
    """
    event = await PaymentEvent.find_one(PaymentEvent.stripe_event_id == stripe_event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment event not found")
    return event
