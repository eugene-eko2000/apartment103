from datetime import date, timedelta

from app.models.booking import BookingCharge
from app.models.cancellation_policy import CancellationRule
from app.services.invoice import build_charge_invoice_pdf, invoice_number_for
from tests.booking_factories import booking, guest


def _charge(**overrides) -> BookingCharge:
    defaults = dict(
        stripe_payment_intent_id="pi_test123",
        amount=250.0,
        currency="CHF",
        reason="initial_charge",
        status="succeeded",
    )
    defaults.update(overrides)
    return BookingCharge(**defaults)


def test_invoice_number_is_derived_from_payment_intent_id():
    assert invoice_number_for(_charge(stripe_payment_intent_id="pi_abc")) == "INV-pi_abc"


def test_build_charge_invoice_pdf_produces_valid_pdf_bytes():
    b = booking(
        rules=[CancellationRule(days_before_checkin=0, refund_percentage=1.0)],
        begin_date=date.today() + timedelta(days=10),
    )
    pdf_bytes = build_charge_invoice_pdf(booking=b, guest=guest(), charge=_charge())

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500
