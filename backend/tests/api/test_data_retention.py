"""Guest personal data has an expiry date — see app.services.data_retention.

What these cover is the rule itself: when the month starts running, what stops
it running at all, and that a wipe leaves the financial record standing. The
job wrapper around it is tests/api/test_purge_guest_data_job.py.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from beanie import PydanticObjectId

from app.core.config import settings
from app.models.booking import Booking, BookingCancellationPolicy, BookingCharge, BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.models.guest import Guest
from app.core.security import hash_otp_code
from app.models.otp_challenge import OtpChallenge
from app.models.payment_event import PaymentEvent
from app.services.data_retention import (
    REDACTED,
    purge_expired_guest_data,
    redacted_email_for,
    redacted_phone_for,
    retention_cutoff,
)

pytestmark = pytest.mark.anyio

TODAY = date(2026, 8, 30)


async def _booking(guest, begin: str, end: str, *, status: str = "Active", cancelled_at=None) -> Booking:
    booking = Booking(
        guest=guest,
        status=status,
        date_ranges=[
            BookingDateRange(
                begin_date=date.fromisoformat(begin), end_date=date.fromisoformat(end), price=100
            )
        ],
        cancellation_policy=BookingCancellationPolicy(
            name="Flexible", rules=[CancellationRule(days_before_checkin=1, refund_percentage=1.0)]
        ),
        cancelled_at=cancelled_at,
    )
    await booking.insert()
    return booking


class TestRetentionCutoff:
    async def test_counts_back_the_configured_number_of_days(self):
        assert retention_cutoff(date(2026, 8, 30)) == date(2026, 7, 31)
        assert retention_cutoff(date(2026, 3, 15)) == date(2026, 2, 13)

    async def test_the_window_is_the_same_length_in_every_month(self):
        # The point of days over calendar months: February and August give a
        # guest exactly as long, rather than 28 days in one and 31 in another.
        for day in (date(2026, 3, 1), date(2026, 9, 1), date(2027, 1, 1)):
            assert (day - retention_cutoff(day)).days == 30

    async def test_crosses_the_year_boundary(self):
        assert retention_cutoff(date(2026, 1, 15)) == date(2025, 12, 16)

    async def test_handles_a_leap_day_in_the_window(self):
        assert retention_cutoff(date(2028, 3, 20)) == date(2028, 2, 19)

    async def test_honours_a_longer_configured_window(self, monkeypatch):
        monkeypatch.setattr(settings, "guest_data_retention_days", 180)
        assert retention_cutoff(date(2026, 8, 30)) == date(2026, 3, 3)


class TestWipesGuestsPastTheWindow:
    async def test_wipes_a_guest_a_month_after_their_last_checkout(self, client, guest):
        await _booking(guest, "2026-07-20", "2026-07-25")

        assert await purge_expired_guest_data(TODAY) == 1

        wiped = await Guest.get(guest.id)
        assert wiped.family_name == REDACTED
        assert wiped.first_name == REDACTED
        assert wiped.email == redacted_email_for(guest.id)
        assert wiped.phone_number == redacted_phone_for(guest.id)
        assert wiped.residence_address.street_address == REDACTED
        assert wiped.residence_address.zip == REDACTED
        assert wiped.residence_address.city == REDACTED
        assert wiped.residence_address.state is None
        assert wiped.residence_address.country == REDACTED
        assert wiped.stripe_customer_id is None
        assert wiped.redacted_at is not None
        assert wiped.is_redacted

    async def test_keeps_a_guest_whose_month_has_not_run_out(self, client, guest):
        # Checked out five days ago.
        await _booking(guest, "2026-08-20", "2026-08-25")

        assert await purge_expired_guest_data(TODAY) == 0
        assert (await Guest.get(guest.id)).family_name == "Guestson"

    async def test_the_month_runs_from_the_latest_checkout(self, client, guest):
        # An old stay is not what the clock runs on if there was a later one.
        await _booking(guest, "2025-01-01", "2025-01-05")
        await _booking(guest, "2026-08-20", "2026-08-25")

        assert await purge_expired_guest_data(TODAY) == 0
        assert not (await Guest.get(guest.id)).is_redacted

    async def test_wipes_on_the_day_the_window_closes(self, client, guest):
        # Checkout exactly 30 days before TODAY — the cutoff is inclusive.
        await _booking(guest, "2026-07-26", "2026-07-31")

        assert await purge_expired_guest_data(TODAY) == 1
        assert (await Guest.get(guest.id)).is_redacted

    async def test_keeps_a_guest_one_day_short_of_the_window(self, client, guest):
        # The other side of the same boundary: 29 days is not yet 30.
        await _booking(guest, "2026-07-27", "2026-08-01")

        assert await purge_expired_guest_data(TODAY) == 0
        assert not (await Guest.get(guest.id)).is_redacted

    async def test_leaves_a_guest_who_never_booked(self, client, guest):
        # No booking, no anchor: registrations that never became a stay are
        # outside this sweep entirely.
        assert await purge_expired_guest_data(TODAY) == 0
        assert not (await Guest.get(guest.id)).is_redacted

    async def test_wipes_only_the_guests_past_the_window(self, client, guest, other_guest):
        await _booking(guest, "2026-07-20", "2026-07-25")
        await _booking(other_guest, "2026-08-20", "2026-08-25")

        assert await purge_expired_guest_data(TODAY) == 1
        assert (await Guest.get(guest.id)).is_redacted
        assert not (await Guest.get(other_guest.id)).is_redacted

    async def test_two_wiped_guests_do_not_collide_on_the_unique_indexes(
        self, client, guest, other_guest
    ):
        # email and phone_number are unique — a shared "[redacted]" would mean
        # only one guest in the database could ever be wiped.
        await _booking(guest, "2026-07-20", "2026-07-25")
        await _booking(other_guest, "2026-06-01", "2026-06-05")

        assert await purge_expired_guest_data(TODAY) == 2
        first, second = await Guest.get(guest.id), await Guest.get(other_guest.id)
        assert first.email != second.email
        assert first.phone_number != second.phone_number


class TestLiveBookingsHoldTheWipeOff:
    async def test_an_upcoming_stay_protects_the_whole_history(self, client, guest):
        await _booking(guest, "2025-01-01", "2025-01-05")
        await _booking(guest, "2026-12-01", "2026-12-05")

        assert await purge_expired_guest_data(TODAY) == 0
        assert not (await Guest.get(guest.id)).is_redacted

    async def test_a_stay_in_progress_protects_the_guest(self, client, guest):
        # Checked in, not yet checked out.
        await _booking(guest, "2026-08-28", "2026-09-02")
        await _booking(guest, "2025-01-01", "2025-01-05")

        assert await purge_expired_guest_data(TODAY) == 0

    async def test_a_pending_checkout_protects_the_guest(self, client, guest):
        await _booking(guest, "2025-01-01", "2025-01-05")
        await _booking(guest, "2026-12-01", "2026-12-05", status="Pending")

        assert await purge_expired_guest_data(TODAY) == 0

    async def test_a_stay_that_ended_today_is_not_upcoming_but_is_still_recent(self, client, guest):
        # end_date is the exclusive checkout day, so this guest left today —
        # not "upcoming", but nowhere near a month old either.
        await _booking(guest, "2026-08-25", "2026-08-30")

        assert await purge_expired_guest_data(TODAY) == 0


class TestCancellationsRestartTheClock:
    async def test_the_month_runs_from_the_cancellation_not_the_dates(self, client, guest):
        # Cancelled last week, for a stay that would have been next year.
        # Counting from the dates would hold this guest's data until 2028.
        await _booking(
            guest,
            "2027-07-01",
            "2027-07-05",
            status="Cancelled",
            cancelled_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

        assert await purge_expired_guest_data(TODAY) == 0
        assert not (await Guest.get(guest.id)).is_redacted

    async def test_wipes_a_month_after_the_cancellation(self, client, guest):
        await _booking(
            guest,
            "2027-07-01",
            "2027-07-05",
            status="Cancelled",
            cancelled_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

        assert await purge_expired_guest_data(TODAY) == 1
        assert (await Guest.get(guest.id)).is_redacted

    async def test_a_cancellation_is_the_latest_event_not_the_largest_date(self, client, guest):
        # A stay that happened, then a later cancellation of a future booking.
        # Both are over; the cancellation is the more recent of the two.
        await _booking(guest, "2026-05-01", "2026-05-05")
        await _booking(
            guest,
            "2027-01-01",
            "2027-01-05",
            status="Cancelled",
            cancelled_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )

        assert await purge_expired_guest_data(TODAY) == 0

    async def test_a_legacy_cancellation_falls_back_to_its_checkout_date(self, client, guest):
        # Cancelled before cancelled_at existed. Nothing records when, so the
        # stay's dates are used — the same clock these bookings ran on until
        # now, and never earlier than it would have wiped them.
        await _booking(guest, "2026-07-20", "2026-07-25", status="Cancelled")

        assert await purge_expired_guest_data(TODAY) == 1

    async def test_a_legacy_cancellation_of_a_future_stay_is_still_protected(self, client, guest):
        await _booking(guest, "2027-07-01", "2027-07-05", status="Cancelled")

        # No cancellation timestamp and dates in the future: falls back to the
        # checkout, which is nowhere near a month past.
        assert await purge_expired_guest_data(TODAY) == 0


class TestWhatSurvivesTheWipe:
    async def test_the_booking_record_is_left_standing(self, client, guest):
        booking = await _booking(guest, "2026-07-20", "2026-07-25")

        await purge_expired_guest_data(TODAY)

        kept = await Booking.get(booking.id, fetch_links=True)
        assert kept is not None
        assert kept.total_price == Decimal("100.00")
        # The link still resolves — the guest document is redacted, not gone,
        # so nothing that reads a booking's guest breaks on it.
        assert kept.guest.id == guest.id
        assert kept.guest.family_name == REDACTED

    async def test_stripe_payloads_are_emptied_but_the_dedupe_ledger_survives(self, client, guest):
        booking = await _booking(guest, "2026-07-20", "2026-07-25")
        booking.charges = [
            BookingCharge(
                stripe_payment_intent_id="pi_123",
                amount=Decimal("100.00"),
                currency="CHF",
                reason="initial_charge",
                status="succeeded",
            )
        ]
        await booking.save()
        event = PaymentEvent(
            stripe_event_id="evt_123",
            event_type="payment_intent.succeeded",
            processed_at=datetime.now(timezone.utc),
            booking_id=booking.id,
            data={"receipt_email": "guest@example.com", "billing_details": {"name": "Gary Guestson"}},
        )
        await event.insert()

        await purge_expired_guest_data(TODAY)

        kept = await PaymentEvent.get(event.id)
        assert kept.data == {}
        assert kept.stripe_event_id == "evt_123"
        assert kept.event_type == "payment_intent.succeeded"
        assert kept.booking_id == booking.id
        # The charge itself is the financial record and stays untouched.
        assert (await Booking.get(booking.id)).charges[0].stripe_payment_intent_id == "pi_123"

    async def test_another_guests_payment_events_are_left_alone(self, client, guest, other_guest):
        await _booking(guest, "2026-07-20", "2026-07-25")
        theirs = await _booking(other_guest, "2026-08-20", "2026-08-25")
        event = PaymentEvent(
            stripe_event_id="evt_other",
            event_type="payment_intent.succeeded",
            processed_at=datetime.now(timezone.utc),
            booking_id=theirs.id,
            data={"receipt_email": "other-guest@example.com"},
        )
        await event.insert()

        await purge_expired_guest_data(TODAY)

        assert (await PaymentEvent.get(event.id)).data == {"receipt_email": "other-guest@example.com"}


class TestIdempotence:
    async def test_a_second_pass_wipes_nothing_and_keeps_the_first_timestamp(self, client, guest):
        await _booking(guest, "2026-07-20", "2026-07-25")

        assert await purge_expired_guest_data(TODAY) == 1
        first = (await Guest.get(guest.id)).redacted_at

        assert await purge_expired_guest_data(TODAY) == 0
        assert (await Guest.get(guest.id)).redacted_at == first

    async def test_a_new_booking_after_a_wipe_does_not_re_wipe(self, client, guest):
        await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        # A month later, still nothing to do: redacted_at is what says so.
        assert await purge_expired_guest_data(TODAY + timedelta(days=60)) == 0


class TestCancellationStampsTheTimestamp:
    async def test_cancelling_a_booking_records_when(self, client, guest, guest_headers):
        booking = await _booking(guest, "2026-12-01", "2026-12-05", status="Pending")

        response = await client.post(f"/bookings/{booking.id}/cancel", headers=guest_headers)

        assert response.status_code == 200
        cancelled = await Booking.get(booking.id)
        assert cancelled.status == "Cancelled"
        assert cancelled.cancelled_at is not None
        assert (datetime.now(timezone.utc) - cancelled.cancelled_at).total_seconds() < 60


class TestAWipedGuestComingBack:
    """A returning guest must be a *new* guest.

    Nothing of the old record may be reachable, reusable or pre-filled: they
    register from scratch, onto a new document. The bookings they made before
    stay behind on the redacted one, which is now an anonymous financial
    record and nobody's account.
    """

    async def test_their_existing_session_stops_working(self, client, guest, guest_headers):
        # A token minted before the sweep. jwt_expire_minutes is a day, so
        # this is an ordinary session, not a contrived one.
        assert (await client.get("/auth/token/verify", headers=guest_headers)).status_code == 200

        await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        # 401, exactly as if the guest had been deleted — which is what the
        # frontend needs to see to clear the stored session and start over.
        assert (await client.get("/auth/token/verify", headers=guest_headers)).status_code == 401

    async def test_they_cannot_read_the_redacted_record_with_the_old_token(
        self, client, guest, guest_headers
    ):
        await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        # The booking form pre-fills from this endpoint; a 401 is what stops
        # "[redacted]" ever reaching it.
        response = await client.get(f"/guests/{guest.id}", headers=guest_headers)
        assert response.status_code == 401

    async def test_logging_in_again_does_not_find_the_old_guest(self, client, guest):
        original_email = guest.email
        await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        await OtpChallenge(
            identifier=original_email,
            channel="email",
            code_hash=hash_otp_code(original_email, "123456"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
        ).insert()
        response = await client.post(
            "/auth/otp/verify", json={"identifier": original_email, "code": "123456"}
        )

        assert response.status_code == 200
        body = response.json()
        # Not "guest": their address no longer belongs to any guest record, so
        # this is a first-time registration.
        assert body["subject_type"] == "pending_guest"
        assert body["subject_id"] == original_email

    async def test_registering_again_creates_a_separate_guest(self, client, guest):
        original_email, original_phone = guest.email, guest.phone_number
        booking = await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        await OtpChallenge(
            identifier=original_email,
            channel="email",
            code_hash=hash_otp_code(original_email, "123456"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
        ).insert()
        verify = await client.post(
            "/auth/otp/verify", json={"identifier": original_email, "code": "123456"}
        )
        pending_token = verify.json()["access_token"]

        # They fill the form in again from scratch — including a new address,
        # which is the point: nothing was carried over for them to correct.
        response = await client.post(
            "/guests/self",
            headers={"Authorization": f"Bearer {pending_token}"},
            json={
                "family_name": "Guestson",
                "first_name": "Gary",
                "phone_number": original_phone,
                "residence_address": {
                    "street_address": "9 New Road",
                    "zip": "99999",
                    "city": "Newtown",
                    "country": "US",
                },
            },
        )

        assert response.status_code == 201
        new_guest = response.json()["guest"]
        assert new_guest["_id"] != str(guest.id)
        assert new_guest["email"] == original_email
        assert new_guest["redacted_at"] is None
        assert new_guest["residence_address"]["city"] == "Newtown"

        # The old record keeps its redaction and keeps the old booking. The
        # new guest starts with none.
        old = await Guest.get(guest.id)
        assert old.is_redacted
        assert (await Booking.get(booking.id)).guest.ref.id == guest.id
        mine = await Booking.find({"guest.$id": PydanticObjectId(new_guest["_id"])}).to_list()
        assert mine == []

    async def test_the_old_phone_number_is_free_to_register_again(self, client, guest):
        # The redacted placeholders have to be unique per guest, but they must
        # also not squat on the real address/number the person will reuse.
        original_phone = guest.phone_number
        await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        conflict = await Guest.find_one({"phone_number": original_phone})
        assert conflict is None


class TestARedactedGuestCannotBeReused:
    async def test_an_admin_cannot_edit_the_retired_record(
        self, client, guest, admin_headers
    ):
        await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        response = await client.put(
            f"/guests/{guest.id}",
            headers=admin_headers,
            json={
                "family_name": "Guestson",
                "first_name": "Gary",
                "email": "guest@example.com",
                "phone_number": "+15550000002",
                "residence_address": {
                    "street_address": "1 Main St",
                    "zip": "12345",
                    "city": "Springfield",
                    "country": "US",
                },
            },
        )

        assert response.status_code == 409
        assert "retired" in response.json()["detail"]
        assert (await Guest.get(guest.id)).family_name == REDACTED

    async def test_no_new_booking_can_be_made_for_a_retired_guest(
        self, client, guest, admin_headers, price, plan
    ):
        await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        response = await client.post(
            "/bookings",
            headers=admin_headers,
            json={
                "guest_id": str(guest.id),
                "currency": "CHF",
                "plan_id": str(plan.id),
                "date_ranges": [{"begin_date": "2026-10-01", "end_date": "2026-10-05"}],
            },
        )

        assert response.status_code == 409
        assert "retired" in response.json()["detail"]

    async def test_an_admin_can_still_read_the_retired_record(self, client, guest, admin_headers):
        # Readable on purpose: the old bookings link to it, and an admin
        # looking at one has to be able to resolve the guest at all.
        await _booking(guest, "2026-07-20", "2026-07-25")
        await purge_expired_guest_data(TODAY)

        response = await client.get(f"/guests/{guest.id}", headers=admin_headers)

        assert response.status_code == 200
        assert response.json()["family_name"] == REDACTED
