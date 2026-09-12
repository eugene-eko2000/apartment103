"""Suite-wide guards against a test escaping into a real vendor account, or
asserting against a machine-specific deployment setting.

`backend/.env` carries working SendGrid and Twilio credentials and pytest
loads it, so without the first fixture below every test that walks a
notification path really sends — app.core.notifications only falls back to
"log it instead" when the credential is *unset*. Blanking the credentials
covers every caller at once, including the modules that did
`from app.core.notifications import send_sms` and so can't be neutralised by
patching a single name on `app.core.notifications` itself. Tests that assert
*that* a notification went out still patch `send_sms`/`send_html_email` on
the service module under test; this fixture is only the backstop for the
paths they don't care about.

`commission_rate` is pinned for the same class of reason: it's read from
.env, so any converted amount a test asserts would otherwise depend on
whatever the machine running the suite happens to have configured. The
pinned value is the model default, and tests that care about the rate itself
(tests/test_currency_service.py) override it per case.
"""

from decimal import Decimal

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def no_live_vendor_sends(monkeypatch):
    monkeypatch.setattr(settings, "sendgrid_api_key", None)
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    monkeypatch.setattr(settings, "twilio_messaging_service_sid", None)


@pytest.fixture(autouse=True)
def pinned_commission_rate(monkeypatch):
    monkeypatch.setattr(settings, "commission_rate", Decimal("0.06"))
