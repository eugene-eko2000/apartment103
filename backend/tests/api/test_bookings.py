from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from beanie import PydanticObjectId

from app.core.config import settings
from app.models.booking import Booking, BookingCharge
from app.models.cancellation_policy import CancellationPolicy, CancellationRule
from app.models.plan import Plan

pytestmark = pytest.mark.anyio


# The admin shape: a cancellation policy by id and a hand-set price, which
# is stored verbatim. Admin-only — see _plan_payload for the guest shape.
def _booking_payload(guest_id, cancellation_policy_id, **overrides):
    payload = {
        "guest_id": str(guest_id),
        "cancellation_policy_id": str(cancellation_policy_id),
        "currency": "CHF",
        "date_ranges": [
            {"begin_date": "2026-07-01", "end_date": "2026-07-05", "price": 400.0}
        ],
    }
    payload.update(overrides)
    return payload


# The guest shape: names the chosen plan and carries no amount at all. With
# the `price`/`plan` fixtures (200.00 CHF a night, ratio 0.5) these four
# nights come to 400.00 CHF — the same total _booking_payload states by
# hand, so assertions hold across both shapes.
def _plan_payload(guest_id, plan_name, **overrides):
    payload = {
        "guest_id": str(guest_id),
        "plan_name": plan_name,
        "currency": "CHF",
        "date_ranges": [{"begin_date": "2026-07-01", "end_date": "2026-07-05"}],
    }
    payload.update(overrides)
    return payload


class TestCreateBooking:
    async def test_admin_can_create_booking_for_any_guest(
        self, client, guest, cancellation_policy, admin_headers
    ):
        response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["currency"] == "CHF"
        assert body["cancellation_policy"]["name"] == cancellation_policy.name
        assert body["status"] == "Pending"

    async def test_guest_can_create_booking_for_self(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        assert response.status_code == 201

    async def test_guest_cannot_create_booking_for_other_guest(
        self, client, other_guest, cancellation_policy, guest_headers, plan, price):
        response = await client.post(
            "/bookings",
            json=_plan_payload(other_guest.id, plan.name),
            headers=guest_headers,
        )
        assert response.status_code == 403

    async def test_returns_404_for_unknown_guest(self, client, cancellation_policy, admin_headers):
        response = await client.post(
            "/bookings",
            json=_booking_payload("000000000000000000000000", cancellation_policy.id),
            headers=admin_headers,
        )
        assert response.status_code == 404

    async def test_returns_404_for_unknown_cancellation_policy(self, client, guest, admin_headers):
        response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, "000000000000000000000000"),
            headers=admin_headers,
        )
        assert response.status_code == 404

    async def test_requires_authentication(self, client, guest, cancellation_policy):
        response = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id)
        )
        assert response.status_code == 401

    async def test_rejects_second_pending_booking_for_same_guest(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        first = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        assert first.status_code == 201

        second = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        assert second.status_code == 409

    async def test_allows_new_pending_booking_once_previous_is_cancelled(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        first = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = first.json()["_id"]
        await client.post(f"/bookings/{booking_id}/cancel", headers=guest_headers)

        second = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        assert second.status_code == 201

    async def test_claims_its_nights_and_starts_a_hold(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # The whole point of creating the booking up front: from this moment
        # the dates are held, and the hold has a deadline.
        before = datetime.now(timezone.utc)
        created = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        assert created.status_code == 201

        stored = await Booking.get(PydanticObjectId(created.json()["_id"]))
        assert stored.status == "Pending"
        assert stored.booked_nights == [date(2026, 7, d) for d in (1, 2, 3, 4)]
        assert stored.pending_expires_at is not None
        expires_at = stored.pending_expires_at.replace(tzinfo=timezone.utc)
        assert expires_at >= before + timedelta(minutes=settings.pending_booking_ttl_minutes - 1)
        assert expires_at <= datetime.now(timezone.utc) + timedelta(
            minutes=settings.pending_booking_ttl_minutes
        )

    async def test_rejects_dates_another_guest_is_in_checkout_for(
        self, client, guest, other_guest, cancellation_policy, admin_headers
    ):
        first = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        assert first.status_code == 201

        second = await client.post(
            "/bookings",
            json=_booking_payload(
                other_guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-07-03", "end_date": "2026-07-08", "price": 500.0}],
            ),
            headers=admin_headers,
        )
        assert second.status_code == 409
        # The same wording the guest gets when a payment arrives too late,
        # naming the dates that are spoken for.
        assert "2026-07-01 to 2026-07-05" in second.json()["detail"]

    async def test_rejects_dates_an_active_booking_holds(
        self, client, guest, other_guest, cancellation_policy, admin_headers
    ):
        first = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking = await Booking.get(PydanticObjectId(first.json()["_id"]))
        booking.status = "Active"
        booking.pending_expires_at = None
        await booking.save()

        second = await client.post(
            "/bookings",
            json=_booking_payload(other_guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        assert second.status_code == 409

    async def test_rejects_dates_a_closure_covers(
        self, client, guest, cancellation_policy, closure, admin_headers
    ):
        # A closure claims no nights of its own (it isn't a booking), so this
        # is the overlap query doing the work, not the unique index.
        response = await client.post(
            "/bookings",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-08-02", "end_date": "2026-08-06", "price": 400.0}],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 409

    async def test_accepts_dates_freed_by_an_expired_hold(
        self, client, guest, other_guest, cancellation_policy, admin_headers
    ):
        first = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        abandoned_id = PydanticObjectId(first.json()["_id"])
        abandoned = await Booking.get(abandoned_id)
        await abandoned.set(
            {Booking.pending_expires_at: datetime.now(timezone.utc) - timedelta(minutes=1)}
        )

        second = await client.post(
            "/bookings",
            json=_booking_payload(other_guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        assert second.status_code == 201
        assert await Booking.get(abandoned_id) is None

    async def test_checkout_day_may_be_another_stays_checkin(
        self, client, guest, other_guest, cancellation_policy, admin_headers
    ):
        # end_date is the exclusive checkout day, so back-to-back stays hold
        # disjoint nights and both go through.
        first = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        assert first.status_code == 201

        second = await client.post(
            "/bookings",
            json=_booking_payload(
                other_guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-07-05", "end_date": "2026-07-09", "price": 400.0}],
            ),
            headers=admin_headers,
        )
        assert second.status_code == 201


class TestListPublicBookedDateRanges:
    async def test_includes_pending_bookings(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # A guest in checkout holds their nights, so the calendar has to show
        # those days as taken — offering them would only walk the next guest
        # into a conflict they can't get past.
        await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )

        response = await client.get("/bookings/public/date-ranges")
        assert response.status_code == 200
        assert response.json() == [{"begin_date": "2026-07-01", "end_date": "2026-07-05"}]

    async def test_excludes_expired_pending_bookings(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # A checkout that ran out of time holds nothing: the endpoint sweeps
        # it away rather than greying out dates that are in fact free.
        created = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = PydanticObjectId(created.json()["_id"])
        booking = await Booking.get(booking_id)
        await booking.set(
            {Booking.pending_expires_at: datetime.now(timezone.utc) - timedelta(minutes=1)}
        )

        response = await client.get("/bookings/public/date-ranges")
        assert response.status_code == 200
        assert response.json() == []
        assert await Booking.get(booking_id) is None

    async def test_lists_date_ranges_for_active_bookings(
        self, client, guest, cancellation_policy, admin_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking = await Booking.get(PydanticObjectId(create_response.json()["_id"]))
        booking.status = "Active"
        await booking.save()

        response = await client.get("/bookings/public/date-ranges")
        assert response.status_code == 200
        body = response.json()
        assert body == [{"begin_date": "2026-07-01", "end_date": "2026-07-05"}]

    async def test_excludes_cancelled_bookings(
        self, client, guest, cancellation_policy, admin_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = create_response.json()["_id"]
        await client.post(f"/bookings/{booking_id}/cancel", headers=admin_headers)

        response = await client.get("/bookings/public/date-ranges")
        assert response.status_code == 200
        assert response.json() == []


class TestListBookings:
    async def test_admin_sees_all_bookings(
        self, client, guest, other_guest, cancellation_policy, admin_headers
    ):
        # Different dates for the two guests: bookings hold their nights from
        # creation now, so two stays on the same nights can't both exist.
        await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        await client.post(
            "/bookings",
            json=_booking_payload(
                other_guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-08-01", "end_date": "2026-08-05", "price": 400.0}],
            ),
            headers=admin_headers,
        )

        response = await client.get("/bookings", headers=admin_headers)
        assert response.status_code == 200
        assert len(response.json()) == 2

    async def test_guest_only_sees_own_bookings(
        self, client, guest, other_guest, cancellation_policy, admin_headers, guest_headers
    ):
        await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        await client.post(
            "/bookings",
            json=_booking_payload(other_guest.id, cancellation_policy.id),
            headers=admin_headers,
        )

        response = await client.get("/bookings", headers=guest_headers)
        assert response.status_code == 200
        bookings = response.json()
        assert len(bookings) == 1
        assert bookings[0]["guest"]["id"] == str(guest.id)

    async def test_requires_authentication(self, client):
        response = await client.get("/bookings")
        assert response.status_code == 401


class TestGetBooking:
    async def test_guest_can_access_own_booking(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.get(f"/bookings/{booking_id}", headers=guest_headers)
        assert response.status_code == 200

    async def test_guest_cannot_access_other_guest_booking(
        self, client, guest, other_guest, cancellation_policy, admin_headers, other_guest_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.get(f"/bookings/{booking_id}", headers=other_guest_headers)
        assert response.status_code == 403

    async def test_admin_can_access_any_booking(
        self, client, guest, cancellation_policy, guest_headers, admin_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.get(f"/bookings/{booking_id}", headers=admin_headers)
        assert response.status_code == 200

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.get("/bookings/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404


class TestUpdateBooking:
    async def test_guest_can_update_own_booking(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_plan_payload(guest.id, plan.name, currency="USD"),
            headers=guest_headers,
        )
        assert response.status_code == 200
        assert response.json()["currency"] == "USD"

    async def test_guest_cannot_update_other_guest_booking(
        self, client, guest, other_guest, cancellation_policy, admin_headers, other_guest_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_plan_payload(guest.id, plan.name, currency="USD"),
            headers=other_guest_headers,
        )
        assert response.status_code == 403

    async def test_guest_cannot_reassign_booking_to_other_guest(
        self, client, guest, other_guest, cancellation_policy, guest_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_plan_payload(other_guest.id, plan.name),
            headers=guest_headers,
        )
        assert response.status_code == 403

    async def test_returns_404_for_unknown_booking_id(
        self, client, guest, cancellation_policy, admin_headers
    ):
        response = await client.put(
            "/bookings/000000000000000000000000",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        assert response.status_code == 404

    async def test_cannot_edit_a_charged_booking(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # An already-charged booking carries money state (amount_charged,
        # charges) that a date/price rewrite would invalidate: the schedule
        # would be rebuilt while the ledger stayed untouched, leaving
        # amount_charged > total_price and charges that no longer match.
        created = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        booking_id = created.json()["_id"]
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.status = "Active"
        booking.amount_charged = Decimal("200.00")
        booking.charges = [
            BookingCharge(
                stripe_payment_intent_id="pi_test_charged",
                amount=Decimal("200.00"),
                currency="CHF",
                reason="initial_charge",
                status="succeeded",
            )
        ]
        await booking.save()

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-07-01", "end_date": "2026-07-03", "price": 50.0}],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 400

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.amount_charged == Decimal("200.00")
        assert [charge.amount for charge in stored.charges] == [Decimal("200.00")]
        assert [date_range.price for date_range in stored.date_ranges] == [Decimal("400.00")]

    async def test_cannot_edit_a_cancelled_booking(
        self, client, guest, cancellation_policy, admin_headers
    ):
        created = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        booking_id = created.json()["_id"]
        await client.post(f"/bookings/{booking_id}/cancel", headers=admin_headers)

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        assert response.status_code == 400

    async def test_edit_rechecks_availability_against_an_active_booking(
        self, client, guest, other_guest, cancellation_policy, admin_headers
    ):
        pending = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        pending_id = pending.json()["_id"]

        active = await client.post(
            "/bookings",
            json=_booking_payload(
                other_guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-08-01", "end_date": "2026-08-04", "price": 300.0}],
            ),
            headers=admin_headers,
        )
        active_booking = await Booking.get(PydanticObjectId(active.json()["_id"]))
        active_booking.status = "Active"
        await active_booking.save()

        response = await client.put(
            f"/bookings/{pending_id}",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-08-01", "end_date": "2026-08-04", "price": 300.0}],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 409

    async def test_edit_rechecks_availability_against_a_closure(
        self, client, guest, cancellation_policy, admin_headers, closure
    ):
        pending = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        pending_id = pending.json()["_id"]

        response = await client.put(
            f"/bookings/{pending_id}",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-08-02", "end_date": "2026-08-06", "price": 300.0}],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 409


class TestCancelBooking:
    async def test_guest_can_cancel_own_booking(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.post(f"/bookings/{booking_id}/cancel", headers=guest_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "Cancelled"

    async def test_admin_can_cancel_any_booking(
        self, client, guest, cancellation_policy, guest_headers, admin_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.post(f"/bookings/{booking_id}/cancel", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "Cancelled"

    async def test_guest_cannot_cancel_other_guest_booking(
        self, client, guest, other_guest, cancellation_policy, admin_headers, other_guest_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.post(f"/bookings/{booking_id}/cancel", headers=other_guest_headers)
        assert response.status_code == 403

    async def test_cannot_cancel_already_cancelled_booking(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]
        await client.post(f"/bookings/{booking_id}/cancel", headers=guest_headers)

        response = await client.post(f"/bookings/{booking_id}/cancel", headers=guest_headers)
        assert response.status_code == 400

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.post("/bookings/000000000000000000000000/cancel", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_authentication(self, client, guest, cancellation_policy, admin_headers):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.post(f"/bookings/{booking_id}/cancel")
        assert response.status_code == 401


class TestDeleteBooking:
    async def test_guest_can_delete_own_booking(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.delete(f"/bookings/{booking_id}", headers=guest_headers)
        assert response.status_code == 204

        follow_up = await client.get(f"/bookings/{booking_id}", headers=guest_headers)
        assert follow_up.status_code == 404

    async def test_guest_cannot_delete_other_guest_booking(
        self, client, guest, other_guest, cancellation_policy, admin_headers, other_guest_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.delete(f"/bookings/{booking_id}", headers=other_guest_headers)
        assert response.status_code == 403

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete("/bookings/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_guest_cannot_delete_active_booking_directly(
        self, client, guest, cancellation_policy, guest_headers, plan, price):
        create_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.status = "Active"
        await booking.save()

        response = await client.delete(f"/bookings/{booking_id}", headers=guest_headers)
        assert response.status_code == 400

    async def test_admin_can_delete_active_booking(
        self, client, guest, cancellation_policy, admin_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = create_response.json()["_id"]
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.status = "Active"
        await booking.save()

        response = await client.delete(f"/bookings/{booking_id}", headers=admin_headers)
        assert response.status_code == 204


class TestBookedNightsAreInternal:
    """booked_nights backs the unique index that prevents double-booking. It
    is derived entirely from date_ranges and of no use to any client, so it
    must never appear in a Booking response — while still being persisted."""

    async def test_absent_from_single_booking_responses(
        self, client, guest, cancellation_policy, admin_headers
    ):
        created = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        assert created.status_code == 201
        assert "booked_nights" not in created.json()

        booking_id = created.json()["_id"]
        fetched = await client.get(f"/bookings/{booking_id}", headers=admin_headers)
        assert fetched.status_code == 200
        assert "booked_nights" not in fetched.json()

        cancelled = await client.post(f"/bookings/{booking_id}/cancel", headers=admin_headers)
        assert cancelled.status_code == 200
        assert "booked_nights" not in cancelled.json()

    async def test_absent_from_the_list_response(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # Regression guard for the "__all__" exclude form: on a list response
        # model a plain {"booked_nights"} key set is read as sequence indices
        # and silently excludes nothing.
        await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        listed = await client.get("/bookings", headers=admin_headers)
        assert listed.status_code == 200
        assert listed.json()
        assert all("booked_nights" not in item for item in listed.json())

    async def test_update_moves_the_claimed_nights(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # Moving a stay gives up the old nights and takes the new ones.
        # Excluding booked_nights from responses is a wire-format choice
        # only — the field is still what backs the claim in storage.
        created = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        booking_id = created.json()["_id"]

        updated = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-08-01", "end_date": "2026-08-04", "price": 300.0}],
            ),
            headers=admin_headers,
        )
        assert updated.status_code == 200
        assert "booked_nights" not in updated.json()

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.booked_nights == [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]


class TestPricesAreServerSide:
    """A booking's price is derived from stored rates and the chosen plan —
    never from the request. These are the regression guards for the hole
    that let a guest post their own `price` and be charged it."""

    async def test_guest_supplied_price_is_ignored(
        self, client, guest, plan, price, guest_headers
    ):
        response = await client.post(
            "/bookings",
            json=_plan_payload(
                guest.id,
                plan.name,
                date_ranges=[
                    # 4 nights at 200.00 with the plan's 0.5 ratio = 400.00,
                    # whatever the request claims.
                    {"begin_date": "2026-07-01", "end_date": "2026-07-05", "price": 1.0}
                ],
            ),
            headers=guest_headers,
        )
        assert response.status_code == 201
        assert response.json()["date_ranges"][0]["price"] == 400.0

    async def test_guest_cannot_set_a_price_without_a_plan(
        self, client, guest, price, cancellation_policy, guest_headers
    ):
        # The admin manual-override shape, posted by a guest: refused
        # outright rather than quietly repriced, since there is no plan to
        # price it from.
        response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=guest_headers,
        )
        assert response.status_code == 403

    async def test_price_follows_the_plan_ratio(self, client, guest, price, plan, guest_headers):
        full_price_plan = await Plan(
            name="Full Price", cancellation_policy=plan.cancellation_policy, price_ratio=1.0
        ).insert()

        response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, full_price_plan.name),
            headers=guest_headers,
        )
        assert response.status_code == 201
        assert response.json()["date_ranges"][0]["price"] == 800.0

    async def test_price_is_converted_into_the_booking_currency(
        self, client, guest, plan, price, guest_headers
    ):
        response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name, currency="USD"),
            headers=guest_headers,
        )
        assert response.status_code == 201
        # 400.00 CHF, +6% commission on the CHF figure, at the fixture's
        # 4 USD/CHF rate.
        assert response.json()["date_ranges"][0]["price"] == 1696.0

    async def test_cancellation_policy_comes_from_the_plan(
        self, client, guest, plan, price, cancellation_policy, guest_headers
    ):
        # A crafted request naming the cheap plan while pointing at another,
        # more lenient policy: the policy is taken from the plan regardless.
        strict = await CancellationPolicy(
            name="Strict",
            rules=[CancellationRule(days_before_checkin=0, refund_percentage=0.0)],
        ).insert()
        strict_plan = await Plan(name="Strict Plan", cancellation_policy=strict, price_ratio=0.5).insert()

        response = await client.post(
            "/bookings",
            json=_plan_payload(
                guest.id, strict_plan.name, cancellation_policy_id=str(cancellation_policy.id)
            ),
            headers=guest_headers,
        )
        assert response.status_code == 201
        assert response.json()["cancellation_policy"]["name"] == "Strict"

    async def test_update_reprices_from_the_server_too(
        self, client, guest, plan, price, guest_headers
    ):
        # PUT shares the create path's resolver; a tampered price must not
        # slip in through the edit a guest makes on the way back from
        # checkout.
        created = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        booking_id = created.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_plan_payload(
                guest.id,
                plan.name,
                date_ranges=[{"begin_date": "2026-07-01", "end_date": "2026-07-03", "price": 1.0}],
            ),
            headers=guest_headers,
        )
        assert response.status_code == 200
        assert response.json()["date_ranges"][0]["price"] == 200.0

    async def test_returns_404_for_unknown_plan(self, client, guest, price, guest_headers):
        response = await client.post(
            "/bookings", json=_plan_payload(guest.id, "No Such Plan"), headers=guest_headers
        )
        assert response.status_code == 404

    async def test_returns_400_for_dates_with_no_configured_rate(
        self, client, guest, plan, price, guest_headers
    ):
        response = await client.post(
            "/bookings",
            json=_plan_payload(
                guest.id,
                plan.name,
                date_ranges=[{"begin_date": "2031-07-01", "end_date": "2031-07-05"}],
            ),
            headers=guest_headers,
        )
        assert response.status_code == 400

    async def test_rejects_a_stay_that_ends_before_it_begins(
        self, client, guest, plan, price, guest_headers
    ):
        response = await client.post(
            "/bookings",
            json=_plan_payload(
                guest.id,
                plan.name,
                date_ranges=[{"begin_date": "2026-07-05", "end_date": "2026-07-01"}],
            ),
            headers=guest_headers,
        )
        assert response.status_code == 422

    async def test_admin_manual_price_is_still_honoured(
        self, client, guest, price, cancellation_policy, admin_headers
    ):
        response = await client.post(
            "/bookings",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[
                    {"begin_date": "2026-07-01", "end_date": "2026-07-05", "price": 42.0}
                ],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["date_ranges"][0]["price"] == 42.0


class TestPromotionsAreSnapshotted:
    """A promotion's effect on a booking is frozen at booking time.

    The stored `applied_promotions` are a by-value copy, exactly like the
    cancellation policy snapshot: what the guest agreed to pay cannot be
    changed afterwards by an admin editing — or deleting — the offer.
    """

    async def test_booking_stores_the_discounted_and_regular_prices(
        self, client, guest, plan, price, promotion, guest_headers
    ):
        response = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        assert response.status_code == 201
        stored = response.json()["date_ranges"][0]
        # Three of the four nights fall inside the promotion: 20% off a
        # 100.00 nightly price, three times.
        assert stored["price"] == 340.0
        assert stored["regular_price"] == 400.0

    async def test_booking_stores_the_applied_promotion(
        self, client, guest, plan, price, promotion, guest_headers
    ):
        response = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        applied = response.json()["date_ranges"][0]["applied_promotions"]
        assert len(applied) == 1
        assert applied[0]["promotion_id"] == str(promotion.id)
        assert applied[0]["name"] == "Summer escape"
        assert applied[0]["nights"] == 3
        assert applied[0]["discount_total"] == 60.0
        assert applied[0]["discount_type"] == "percent"
        assert applied[0]["discount_ratio"] == 0.2

    async def test_editing_the_promotion_does_not_change_an_existing_booking(
        self, client, guest, plan, price, promotion, guest_headers, admin_headers
    ):
        created = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        booking_id = created.json()["_id"]

        await client.put(
            f"/promotions/{promotion.id}",
            json={
                "name": "Renamed and halved",
                "begin_date": promotion.begin_date.isoformat(),
                "end_date": promotion.end_date.isoformat(),
                "discount_type": "percent",
                "discount_ratio": 0.5,
                "min_stay_days": 1,
            },
            headers=admin_headers,
        )

        response = await client.get(f"/bookings/{booking_id}", headers=guest_headers)
        stored = response.json()["date_ranges"][0]
        assert stored["price"] == 340.0
        assert stored["applied_promotions"][0]["name"] == "Summer escape"
        assert stored["applied_promotions"][0]["discount_ratio"] == 0.2

    async def test_deleting_the_promotion_does_not_change_an_existing_booking(
        self, client, guest, plan, price, promotion, guest_headers, admin_headers
    ):
        created = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        booking_id = created.json()["_id"]

        await client.delete(f"/promotions/{promotion.id}", headers=admin_headers)

        response = await client.get(f"/bookings/{booking_id}", headers=guest_headers)
        stored = response.json()["date_ranges"][0]
        assert stored["price"] == 340.0
        assert stored["regular_price"] == 400.0
        assert stored["applied_promotions"][0]["name"] == "Summer escape"

    async def test_display_reports_the_discount(
        self, client, guest, plan, price, promotion, guest_headers
    ):
        created = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        booking_id = created.json()["_id"]

        response = await client.get(
            f"/bookings/{booking_id}/display?currency=CHF", headers=guest_headers
        )
        body = response.json()
        assert body["total_price"] == 340.0
        assert body["total_regular_price"] == 400.0
        assert body["total_discount"] == 60.0
        assert body["date_ranges"][0]["regular_price"] == 400.0
        assert body["date_ranges"][0]["discount"] == 60.0

    async def test_admin_manual_price_records_no_discount(
        self, client, guest, price, cancellation_policy, promotion, admin_headers
    ):
        # An admin typing a final amount is stating the actual figure,
        # promotions included — so nothing is struck through.
        response = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        stored = response.json()["date_ranges"][0]
        assert stored["price"] == 400.0
        assert stored["regular_price"] == 400.0
        assert stored["applied_promotions"] == []
