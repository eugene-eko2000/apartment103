import pytest

from app.services import email_templates

_CONFIRMATION_CONTEXT = {
    "business_name": "Berg See Home",
    "guest_first_name": "Alex",
    "booking_id": "abc123",
    "currency": "CHF",
    "check_in": "2026-09-01",
    "check_out": "2026-09-04",
    "total_price": 300.0,
    # Undiscounted by default: total_regular_price == total_price, so the
    # "you save" block stays out of the way.
    "total_regular_price": 300.0,
    "total_discount": 0.0,
    "nightly_rates": [{"date": "2026-09-01", "rate": 100.0}],
    "cancellation_policy_name": "Standard",
    "cancellation_rules": [{"days_before_checkin": 14, "refund_percentage": 1.0}],
    "amount_charged": 0.0,
    "pending_schedule": [{"date": "2026-08-18", "amount": 300.0}],
}

_PAYMENT_CONTEXT = {
    **_CONFIRMATION_CONTEXT,
    "amount_charged": 50.0,
    "pending_schedule": [],
    "charge_reason": "scheduled_accrual",
    "charge_amount": 50.0,
    "charge_currency": "CHF",
    "charge_date": "2026-08-18",
    "charge_reference": "pi_test",
}


def test_resolve_language_falls_back_to_default_for_unset_or_unsupported():
    assert email_templates.resolve_language(None) == "en"
    assert email_templates.resolve_language("de") == "de"
    assert email_templates.resolve_language("xx") == "en"


@pytest.mark.parametrize("language", ["en", "de", "fr", "it"])
def test_booking_confirmation_renders_for_every_supported_language(language):
    subject, body = email_templates.render_email(
        language=language, name="booking_confirmation.html", context=_CONFIRMATION_CONTEXT
    )
    assert "Berg See Home" in subject
    assert "abc123" in body
    assert "100.00 CHF" in body


@pytest.mark.parametrize("language", ["en", "de", "fr", "it"])
def test_scheduled_payment_renders_for_every_supported_language(language):
    subject, body = email_templates.render_email(
        language=language, name="scheduled_payment.html", context=_PAYMENT_CONTEXT
    )
    assert "Berg See Home" in subject
    assert "pi_test" in body
    assert "50.00 CHF" in body


@pytest.mark.parametrize("language", ["en", "de", "fr", "it"])
def test_booking_confirmation_omits_the_saving_when_nothing_was_discounted(language):
    _, body = email_templates.render_email(
        language=language, name="booking_confirmation.html", context=_CONFIRMATION_CONTEXT
    )
    assert "line-through" not in body


@pytest.mark.parametrize("language", ["en", "de", "fr", "it"])
def test_booking_confirmation_shows_the_saving_for_a_discounted_booking(language):
    _, body = email_templates.render_email(
        language=language,
        name="booking_confirmation.html",
        context={**_CONFIRMATION_CONTEXT, "total_regular_price": 400.0, "total_discount": 100.0},
    )
    # The struck-through regular price and the saving, alongside the
    # unchanged payable total.
    assert "line-through" in body
    assert "400.00 CHF" in body
    assert "100.00 CHF" in body
    assert "300.00 CHF" in body
