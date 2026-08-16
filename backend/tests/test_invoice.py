from datetime import date, timedelta

import pytest

from app.models.booking import BookingCharge
from app.models.cancellation_policy import CancellationRule
from app.services.email_templates import _SUPPORTED_LANGUAGES
from app.services.invoice import _invoice_labels, build_charge_invoice_pdf, invoice_number_for
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


@pytest.mark.parametrize("language", _SUPPORTED_LANGUAGES)
def test_build_charge_invoice_pdf_renders_in_every_supported_language(language):
    b = booking(
        rules=[CancellationRule(days_before_checkin=0, refund_percentage=1.0)],
        begin_date=date.today() + timedelta(days=10),
    )
    pdf_bytes = build_charge_invoice_pdf(booking=b, guest=guest(preferred_language=language), charge=_charge())

    assert pdf_bytes.startswith(b"%PDF")


def test_build_charge_invoice_pdf_falls_back_to_default_language_when_unset():
    b = booking(
        rules=[CancellationRule(days_before_checkin=0, refund_percentage=1.0)],
        begin_date=date.today() + timedelta(days=10),
    )
    pdf_bytes = build_charge_invoice_pdf(booking=b, guest=guest(preferred_language=None), charge=_charge())

    assert pdf_bytes.startswith(b"%PDF")


@pytest.mark.parametrize("language", _SUPPORTED_LANGUAGES)
def test_invoice_labels_are_complete_for_every_supported_language(language):
    labels = _invoice_labels(language)

    for key in ("invoice", "date", "booking_reference", "billed_to", "stay", "description", "amount", "payment_reference"):
        assert labels[key]

    for reason in ("initial_charge", "scheduled_accrual", "cancellation_settlement"):
        assert labels["charge_reasons"][reason]
