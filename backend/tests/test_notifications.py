"""Preprod test-marking in app.core.notifications.

Asserts on what is actually handed to SendGrid/Twilio: the vendor clients are
replaced with recorders and fake credentials are set, so the real send path
runs end to end without leaving the process.
"""

import pytest

from app.core import notifications
from app.core.config import settings
from app.services import email_templates

pytestmark = pytest.mark.anyio

BANNER_HTML = '<p style="color:#d00000; font-weight:bold; margin:0 0 16px 0;"><strong>[THIS IS A TEST MESSAGE]</strong></p>'


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def sent(monkeypatch):
    """Configure fake credentials and record every outbound message."""
    records: dict[str, list] = {"mail": [], "sms": []}

    class FakeSendGrid:
        def __init__(self, api_key):
            pass

        def send(self, message):
            records["mail"].append(message.get())

    class FakeMessages:
        def create(self, **kwargs):
            records["sms"].append(kwargs)

    class FakeTwilio:
        def __init__(self, sid, token):
            self.messages = FakeMessages()

    monkeypatch.setattr(settings, "sendgrid_api_key", "SG.fake")
    monkeypatch.setattr(settings, "twilio_account_sid", "AC.fake")
    monkeypatch.setattr(settings, "twilio_auth_token", "fake")
    monkeypatch.setattr(settings, "twilio_messaging_service_sid", "MG.fake")
    monkeypatch.setattr(notifications, "SendGridAPIClient", FakeSendGrid)
    monkeypatch.setattr(notifications, "TwilioClient", FakeTwilio)
    return records


@pytest.fixture(params=["production", "local"])
def non_test_environment(request, monkeypatch):
    monkeypatch.setattr(settings, "environment", request.param)


@pytest.fixture
def preprod(monkeypatch):
    monkeypatch.setattr(settings, "environment", "preprod")


def _rendered_booking_email() -> tuple[str, str]:
    """The real booking-confirmation markup (unrendered, which is enough for
    where the banner lands)."""
    raw = (email_templates.DATA_DIR / "en" / "booking_confirmation.html").read_text(encoding="utf-8")
    subject_line, _, html_content = raw.partition("\n\n")
    return subject_line.removeprefix("Subject: "), html_content


class TestPreprod:
    async def test_sms_is_prefixed(self, sent, preprod):
        await notifications.send_sms("+41790000000", "Your code is 123456")
        assert sent["sms"][0]["body"] == "[TEST MESSAGE] Your code is 123456"

    async def test_text_email_subject_and_body_are_marked(self, sent, preprod):
        await notifications.send_text_email("a@example.com", "Your code", "Code: 123456")
        mail = sent["mail"][0]
        assert mail["subject"] == "[TEST MESSAGE] Your code"
        assert mail["content"][0]["value"] == "[THIS IS A TEST MESSAGE]\n\nCode: 123456"

    async def test_html_email_gets_red_bold_banner_first_in_body(self, sent, preprod):
        subject, html_content = _rendered_booking_email()
        await notifications.send_html_email("a@example.com", subject, html_content)
        mail = sent["mail"][0]
        assert mail["subject"] == f"[TEST MESSAGE] {subject}"
        body = mail["content"][0]["value"]
        body_open_end = body.index(">", body.index("<body")) + 1
        assert body[body_open_end:].startswith(BANNER_HTML)
        # Nothing else in the rendered email moved.
        assert body.replace(BANNER_HTML, "", 1) == html_content

    async def test_html_without_body_tag_gets_banner_at_start(self, sent, preprod):
        await notifications.send_html_email("a@example.com", "S", "<p>Hello</p>")
        assert sent["mail"][0]["content"][0]["value"] == BANNER_HTML + "<p>Hello</p>"

    async def test_logged_fallback_is_marked_too(self, monkeypatch, preprod, caplog):
        caplog.set_level("INFO", logger="app.notifications")
        await notifications.send_sms("+41790000000", "hi")
        await notifications.send_text_email("a@example.com", "Subj", "body")
        assert "body=[TEST MESSAGE] hi" in caplog.text
        assert "subject=[TEST MESSAGE] Subj" in caplog.text


class TestNotPreprod:
    async def test_sms_unchanged(self, sent, non_test_environment):
        await notifications.send_sms("+41790000000", "Your code is 123456")
        assert sent["sms"][0]["body"] == "Your code is 123456"

    async def test_text_email_unchanged(self, sent, non_test_environment):
        await notifications.send_text_email("a@example.com", "Your code", "Code: 123456")
        mail = sent["mail"][0]
        assert mail["subject"] == "Your code"
        assert mail["content"][0]["value"] == "Code: 123456"

    async def test_html_email_unchanged(self, sent, non_test_environment):
        subject, html_content = _rendered_booking_email()
        await notifications.send_html_email("a@example.com", subject, html_content)
        mail = sent["mail"][0]
        assert mail["subject"] == subject
        assert mail["content"][0]["value"] == html_content
