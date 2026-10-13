"""Automated guest messages: rendering, the due-date rule, and sending
exactly once (app.services.guest_messages, app.jobs.send_guest_messages)."""

from datetime import date, datetime, timedelta, timezone

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.jobs import send_guest_messages as job
from app.models.booking import Booking, BookingCancellationPolicy, BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.models.message_delivery import MessageDelivery
from app.models.message_template import MessageTemplate, MessageTemplateVersion
from app.services import guest_messages

pytestmark = pytest.mark.anyio

TODAY = date(2026, 11, 2)
# Templates exist well before TODAY unless a test says otherwise, so the
# created_at bound doesn't interfere with the rule under test.
LONG_AGO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _version(language="en", subject="Hello {{guest_first_name}}", body="See you on {{checkin_date}}."):
    return MessageTemplateVersion(language=language, subject=subject, body_markdown=body)


async def _template(anchor="booking_date", direction="after", offset_days=1, versions=None, **kwargs):
    template = MessageTemplate(
        name="Test",
        anchor=anchor,
        direction=direction,
        offset_days=offset_days,
        versions=versions or [_version()],
        created_at=kwargs.pop("created_at", LONG_AGO),
        **kwargs,
    )
    await template.insert()
    return template


async def _booking(guest, checkin, checkout, booked_on, status="Active", adults=2, children_ages=None):
    booking = Booking(
        guest=guest,
        status=status,
        booking_date=booked_on,
        adults=adults,
        children_ages=children_ages or [],
        date_ranges=[BookingDateRange(begin_date=checkin, end_date=checkout, price=400)],
        cancellation_policy=BookingCancellationPolicy(
            name="Flexible", rules=[CancellationRule(days_before_checkin=1, refund_percentage=1.0)]
        ),
    )
    await booking.insert()
    return booking


def outbox_email(sent):
    async def fake_email(to, subject, html, attachments=None):
        sent["email"].append({"to": to, "subject": subject, "html": html})

    return fake_email


@pytest.fixture
def outbox(monkeypatch):
    sent = {"email": [], "sms": []}

    async def fake_email(to, subject, html, attachments=None):
        sent["email"].append({"to": to, "subject": subject, "html": html})

    async def fake_sms(to, body):
        sent["sms"].append({"to": to, "body": body})

    monkeypatch.setattr(guest_messages, "send_html_email", fake_email)
    monkeypatch.setattr(guest_messages, "send_sms", fake_sms)
    return sent


class TestPlaceholders:
    async def test_values_come_from_the_booking_and_guest(self, client, guest):
        booking = await _booking(
            guest, date(2026, 11, 12), date(2026, 11, 16), date(2026, 11, 1), adults=2, children_ages=[3, 6, 12]
        )
        values = guest_messages.placeholder_values(booking, guest)
        assert values == {
            "guest_first_name": "Gary",
            "guest_last_name": "Guestson",
            "checkin_date": "12.11.2026",
            "checkout_date": "16.11.2026",
            "stay_days": "4",
            "adults_number": "2",
            "children_older_6yo_number": "2",
            "children_below_6yo_number": "1",
        }

    async def test_multi_range_stay_spans_first_checkin_to_last_checkout(self, client, guest):
        booking = await _booking(guest, date(2026, 11, 12), date(2026, 11, 14), date(2026, 11, 1))
        booking.date_ranges.append(BookingDateRange(begin_date=date(2026, 11, 14), end_date=date(2026, 11, 20), price=1))
        values = guest_messages.placeholder_values(booking, guest)
        assert (values["checkin_date"], values["checkout_date"], values["stay_days"]) == ("12.11.2026", "20.11.2026", "8")

    async def test_counts_are_blank_on_a_booking_that_never_recorded_them(self, client, guest):
        booking = await _booking(guest, date(2026, 11, 12), date(2026, 11, 16), date(2026, 11, 1), adults=None)
        values = guest_messages.placeholder_values(booking, guest)
        assert values["adults_number"] == values["children_older_6yo_number"] == values["children_below_6yo_number"] == ""


class TestRendering:
    async def test_markdown_is_rendered_and_placeholders_substituted(self):
        message = guest_messages.render_message(
            _version(subject="Hi {{ guest_first_name }}", body="**Welcome**, {{guest_first_name}}!"),
            {"guest_first_name": "Anna"},
        )
        assert message.subject == "Hi Anna"
        assert "<strong>Welcome</strong>, Anna!" in message.html
        assert settings.business_name in message.html

    async def test_guest_values_cannot_inject_markup_or_markdown(self):
        message = guest_messages.render_message(
            _version(body="Dear {{guest_first_name}}"), {"guest_first_name": "<b>*Evil*</b>"}
        )
        assert "<b>" not in message.html
        assert "<em>" not in message.html
        assert "&lt;b&gt;*Evil*&lt;/b&gt;" in message.html

    async def test_raw_html_in_the_template_is_not_passed_through(self):
        message = guest_messages.render_message(_version(body="<script>x()</script>"), {})
        assert "<script>" not in message.html

    async def test_sms_is_in_the_guests_language(self):
        assert guest_messages.render_sms("de", "Willkommen") == (
            f"Sie haben eine Nachricht von {settings.business_name} erhalten: Willkommen. "
            "Bitte lesen Sie die Nachricht in Ihrem E-Mail-Postfach."
        )
        assert guest_messages.render_sms(None, "Welcome") == (
            f"You got a message from {settings.business_name}: Welcome. Check your email to read the message."
        )

    async def test_sms_does_not_double_the_subjects_own_punctuation(self):
        assert guest_messages.render_sms("en", "Thank you, John!") == (
            f"You got a message from {settings.business_name}: Thank you, John! Check your email to read the message."
        )


class TestPickVersion:
    def _template(self, *languages):
        return MessageTemplate.model_construct(versions=[_version(language=lang) for lang in languages])

    async def test_prefers_the_guests_language(self):
        assert guest_messages.pick_version(self._template("en", "de"), "de").language == "de"

    async def test_falls_back_to_english_without_a_preferred_language(self):
        assert guest_messages.pick_version(self._template("de", "en"), None).language == "en"

    async def test_falls_back_to_english_when_the_guests_language_is_missing(self):
        assert guest_messages.pick_version(self._template("de", "en"), "fr").language == "en"

    async def test_none_without_english_or_the_guests_language(self):
        assert guest_messages.pick_version(self._template("de"), "fr") is None


class TestDueBookings:
    async def test_one_day_after_booking(self, client, guest):
        template = await _template("booking_date", "after", 1)
        due = await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1))
        await _booking(guest, date(2026, 12, 10), date(2026, 12, 12), date(2026, 11, 2))  # booked today

        result = await guest_messages.due_bookings(template, TODAY)
        assert [(b.id, day) for b, day in result] == [(due.id, TODAY)]

    async def test_two_days_before_checkin(self, client, guest):
        template = await _template("checkin", "before", 2)
        due = await _booking(guest, date(2026, 11, 4), date(2026, 11, 6), date(2026, 10, 1))
        await _booking(guest, date(2026, 11, 5), date(2026, 11, 7), date(2026, 10, 1))

        assert [b.id for b, _ in await guest_messages.due_bookings(template, TODAY)] == [due.id]

    async def test_one_day_before_checkout_across_a_month_boundary(self, client, guest):
        template = await _template("checkout", "before", 1)
        due = await _booking(guest, date(2026, 11, 28), date(2026, 12, 1), date(2026, 10, 1))
        assert [b.id for b, _ in await guest_messages.due_bookings(template, date(2026, 11, 30))] == [due.id]

    async def test_only_active_bookings(self, client, guest):
        template = await _template("booking_date", "after", 1)
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1), status="Pending")
        await _booking(guest, date(2026, 12, 6), date(2026, 12, 8), date(2026, 11, 1), status="Cancelled")
        assert await guest_messages.due_bookings(template, TODAY) == []

    async def test_a_missed_send_day_is_made_up_however_late(self, client, guest):
        # Due Oct 2 — a month of runs missed it; it still goes out today.
        template = await _template("booking_date", "after", 1)
        missed = await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 10, 1))

        result = await guest_messages.due_bookings(template, TODAY)
        assert [(b.id, day) for b, day in result] == [(missed.id, date(2026, 10, 2))]

    async def test_a_booking_made_after_its_send_day_gets_the_message_late(self, client, guest):
        # "3 days before check-in" fell on Oct 31 — before this booking
        # existed. The guest still gets it, on the first run after booking.
        template = await _template("checkin", "before", 3)
        late = await _booking(guest, date(2026, 11, 3), date(2026, 11, 5), date(2026, 11, 1))

        result = await guest_messages.due_bookings(template, TODAY)
        assert [(b.id, day) for b, day in result] == [(late.id, date(2026, 10, 31))]

    async def test_a_same_day_booking_gets_every_pre_arrival_message(self, client, guest):
        # Booked today for a stay starting today.
        week_before = await _template("checkin", "before", 7)
        day_before = await _template("checkin", "before", 1)
        on_booking = await _template("booking_date", "after", 0)
        booking = await _booking(guest, TODAY, date(2026, 11, 4), TODAY)

        for template in (week_before, day_before, on_booking):
            assert [b.id for b, _ in await guest_messages.due_bookings(template, TODAY)] == [booking.id]

    async def test_never_backfills_from_before_the_template_existed(self, client, guest):
        template = await _template("booking_date", "after", 1, created_at=datetime(2026, 11, 2, 9, tzinfo=timezone.utc))
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 10, 20))  # due Oct 21
        due_today = await _booking(guest, date(2026, 12, 6), date(2026, 12, 8), date(2026, 11, 1))

        assert [b.id for b, _ in await guest_messages.due_bookings(template, TODAY)] == [due_today.id]

    async def test_a_booking_made_after_the_template_is_owed_even_past_messages(self, client, guest):
        # Template created Nov 1; booked Nov 2 for a stay starting Nov 3, so
        # "7 days before check-in" (Oct 27) predates the template but not the
        # booking — the booking is what made it owed.
        template = await _template("checkin", "before", 7, created_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
        booking = await _booking(guest, date(2026, 11, 3), date(2026, 11, 5), TODAY)
        assert [b.id for b, _ in await guest_messages.due_bookings(template, TODAY)] == [booking.id]

    async def test_pre_departure_messages_are_dropped_once_the_guest_has_left(self, client, guest):
        before_checkin = await _template("checkin", "before", 2)
        after_checkout = await _template("checkout", "after", 0)
        # Stay ended Nov 1; the booking was made long before, but the job
        # never got to it (e.g. the template was paused until now).
        booking = await _booking(guest, date(2026, 10, 25), date(2026, 11, 1), date(2026, 10, 1))

        assert await guest_messages.due_bookings(before_checkin, TODAY) == []
        assert [b.id for b, _ in await guest_messages.due_bookings(after_checkout, TODAY)] == [booking.id]

    async def test_on_checkout_day_a_pre_departure_message_still_goes(self, client, guest):
        template = await _template("checkout", "before", 1)
        booking = await _booking(guest, date(2026, 10, 30), TODAY, date(2026, 10, 1))
        assert [b.id for b, _ in await guest_messages.due_bookings(template, TODAY)] == [booking.id]

    async def test_already_sent_bookings_are_not_candidates(self, client, guest, outbox):
        template = await _template("booking_date", "after", 1)
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 10, 1))
        assert await guest_messages.send_due_messages(TODAY) == 1
        assert await guest_messages.due_bookings(template, TODAY + timedelta(days=5)) == []


class TestSending:
    async def test_sends_email_then_sms_once(self, client, guest, outbox):
        guest.preferred_language = "de"
        await guest.save()
        await _template(
            "booking_date",
            "after",
            1,
            versions=[_version("en"), _version("de", subject="Hallo {{guest_first_name}}", body="Bis {{checkin_date}}")],
        )
        booking = await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1))

        assert await guest_messages.send_due_messages(TODAY) == 1
        assert await guest_messages.send_due_messages(TODAY) == 0

        assert [m["subject"] for m in outbox["email"]] == ["Hallo Gary"]
        assert outbox["email"][0]["to"] == guest.email
        assert "Bis 01.12.2026" in outbox["email"][0]["html"]
        assert len(outbox["sms"]) == 1
        assert outbox["sms"][0]["to"] == guest.phone_number
        assert "Hallo Gary" in outbox["sms"][0]["body"]

        delivery = await MessageDelivery.find_one(MessageDelivery.booking_id == booking.id)
        assert (delivery.email_status, delivery.sms_status, delivery.language) == ("sent", "sent", "de")

    async def test_inactive_templates_are_not_sent(self, client, guest, outbox):
        await _template("booking_date", "after", 1, active=False)
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1))
        assert await guest_messages.send_due_messages(TODAY) == 0

    async def test_skipped_without_a_usable_version(self, client, guest, outbox):
        guest.preferred_language = "fr"
        await guest.save()
        await _template("booking_date", "after", 1, versions=[_version("de")])
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1))

        assert await guest_messages.send_due_messages(TODAY) == 0
        assert outbox["email"] == outbox["sms"] == []
        delivery = await MessageDelivery.find_one()
        assert delivery.email_status == "skipped"

    async def test_a_failed_email_sends_no_sms_and_is_retried(self, client, guest, outbox, monkeypatch):
        await _template("booking_date", "after", 1)
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1))

        async def failing_email(*args, **kwargs):
            raise RuntimeError("SendGrid down")

        monkeypatch.setattr(guest_messages, "send_html_email", failing_email)
        assert await guest_messages.send_due_messages(TODAY) == 0
        assert outbox["sms"] == []
        delivery = await MessageDelivery.find_one()
        assert (delivery.email_status, delivery.email_error) == ("failed", "SendGrid down")

        # Next day: still inside the catch-up window, so it goes out.
        async def working_email(to, subject, html, attachments=None):
            outbox["email"].append({"to": to})

        monkeypatch.setattr(guest_messages, "send_html_email", working_email)
        assert await guest_messages.send_due_messages(TODAY + timedelta(days=1)) == 1
        assert len(outbox["sms"]) == 1
        delivery = await MessageDelivery.find_one()
        assert (delivery.email_status, delivery.attempts) == ("sent", 2)

    async def test_failed_emails_are_retried_on_later_runs_until_attempts_run_out(
        self, client, guest, outbox, monkeypatch
    ):
        await _template("booking_date", "after", 1)
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1))

        async def failing_email(*args, **kwargs):
            raise RuntimeError("SendGrid down")

        monkeypatch.setattr(guest_messages, "send_html_email", failing_email)
        for day in range(settings.guest_message_max_attempts):
            assert await guest_messages.send_due_messages(TODAY + timedelta(days=5 * day)) == 0
        delivery = await MessageDelivery.find_one()
        assert (delivery.email_status, delivery.attempts) == ("failed", settings.guest_message_max_attempts)

        monkeypatch.setattr(guest_messages, "send_html_email", outbox_email(outbox))
        assert await guest_messages.send_due_messages(TODAY + timedelta(days=30)) == 0

    async def test_each_sent_message_is_logged_against_its_booking(self, client, guest, outbox, caplog):
        template = await _template("checkin", "before", 3)
        booking = await _booking(guest, date(2026, 11, 3), date(2026, 11, 5), date(2026, 11, 1))

        with caplog.at_level("INFO", logger="app.services.guest_messages"):
            assert await guest_messages.send_due_messages(TODAY) == 1

        delivery = await MessageDelivery.find_one(MessageDelivery.booking_id == booking.id)
        assert delivery.template_id == template.id
        assert (delivery.guest_name, delivery.checkin_date, delivery.checkout_date) == (
            "Gary Guestson",
            date(2026, 11, 3),
            date(2026, 11, 5),
        )
        assert delivery.scheduled_for == date(2026, 10, 31)
        assert (delivery.email_status, delivery.sent_at is not None) == ("sent", True)
        assert delivery.recipient_email == guest.email
        line = next(r.getMessage() for r in caplog.records if "sent for booking" in r.getMessage())
        assert str(booking.id) in line and str(template.id) in line and "due 2026-10-31, 2 day(s) late" in line

    async def test_a_failed_sms_does_not_resend_the_email(self, client, guest, outbox, monkeypatch):
        await _template("booking_date", "after", 1)
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1))

        async def failing_sms(*args, **kwargs):
            raise RuntimeError("Twilio down")

        monkeypatch.setattr(guest_messages, "send_sms", failing_sms)
        assert await guest_messages.send_due_messages(TODAY) == 1
        assert await guest_messages.send_due_messages(TODAY) == 0
        assert len(outbox["email"]) == 1
        delivery = await MessageDelivery.find_one()
        assert (delivery.email_status, delivery.sms_status) == ("sent", "failed")

    async def test_redacted_guests_are_skipped(self, client, guest, outbox):
        guest.redacted_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
        await guest.save()
        await _template("booking_date", "after", 1)
        await _booking(guest, date(2026, 12, 1), date(2026, 12, 5), date(2026, 11, 1))

        assert await guest_messages.send_due_messages(TODAY) == 0
        assert outbox["email"] == []


class TestSendGuestMessagesJob:
    async def test_a_failing_pass_is_swallowed(self, monkeypatch):
        async def boom() -> int:
            raise RuntimeError("mongo is having a moment")

        monkeypatch.setattr(job, "send_due_messages", boom)
        assert await job.send_guest_messages() == 0

    async def test_registers_daily_at_noon_utc(self):
        scheduler = AsyncIOScheduler()
        job.register(scheduler)

        registered = scheduler.get_job(job.JOB_ID)
        fields = {field.name: str(field) for field in registered.trigger.fields}
        assert (fields["hour"], fields["minute"]) == ("12", "0")
        assert str(registered.trigger.timezone) == "UTC"
        assert registered.max_instances == 1
        assert registered.coalesce is True
