from datetime import date
from decimal import Decimal

import pytest
from beanie import PydanticObjectId

from app.models.booking import Booking, nights_of_ranges
from app.models.cancellation_policy import CancellationPolicy, CancellationRule
from app.models.plan import Plan
from app.services.charge_schedule import outstanding_amount

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


class TestListPublicBookedDateRanges:
    async def test_excludes_pending_bookings(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # A booking that's stored but not yet paid/verified (Pending) must
        # not block the calendar, so a second guest can still reach checkout
        # for the same dates — see app.services.availability for how that
        # race is then resolved.
        await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )

        response = await client.get("/bookings/public/date-ranges")
        assert response.status_code == 200
        assert response.json() == []

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


class TestUpdateBookingKeepsTheMoneyStraight:
    """A booking's charges, its stored charge schedule and its total price
    have to keep describing the same stay. PUT replaces the terms wholesale —
    dates, prices, cancellation policy — so anything it recomputes must be
    reconciled against money that has already moved, and anything that can't
    be reconciled must be refused.
    """

    async def _charged_booking(self, client, guest, cancellation_policy, admin_headers, amount="400.00"):
        """An Active booking, fully charged for its 400.00 CHF stay — the
        state the daily accrual job leaves a paid booking in."""
        created = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        booking = await Booking.get(PydanticObjectId(created.json()["_id"]))
        await booking.set(
            {
                Booking.status: "Active",
                Booking.amount_charged: Decimal(amount),
                Booking.payment_status: "fully_charged",
            }
        )
        return created.json()["_id"]

    async def test_guest_cannot_edit_a_booking_that_has_been_paid_for(
        self, client, guest, cancellation_policy, guest_headers, admin_headers, plan, price
    ):
        booking_id = await self._charged_booking(client, guest, cancellation_policy, admin_headers)

        response = await client.put(
            f"/bookings/{booking_id}", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        assert response.status_code == 400

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.total_price == Decimal("400.00")

    async def test_a_cancelled_booking_cannot_be_edited(
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

    async def test_total_cannot_be_dropped_below_what_was_already_charged(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # The overpayment this would strand has nowhere to go: nothing in the
        # app refunds, so the edit is refused instead of stored.
        booking_id = await self._charged_booking(client, guest, cancellation_policy, admin_headers)

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-07-01", "end_date": "2026-07-03", "price": 150.0}],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 400

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.total_price == Decimal("400.00")
        assert stored.amount_charged == Decimal("400.00")
        assert stored.payment_status == "fully_charged"

    async def test_currency_cannot_be_changed_once_money_has_moved(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # amount_charged carries no currency of its own — it is denominated in
        # booking.currency, so re-denominating the stay would leave the two
        # sides of the invariant in different currencies.
        booking_id = await self._charged_booking(client, guest, cancellation_policy, admin_headers)

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(guest.id, cancellation_policy.id, currency="USD"),
            headers=admin_headers,
        )
        assert response.status_code == 400

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.currency == "CHF"

    async def test_raising_the_total_reopens_the_booking_for_accrual(
        self, client, guest, cancellation_policy, admin_headers
    ):
        booking_id = await self._charged_booking(client, guest, cancellation_policy, admin_headers)

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-07-01", "end_date": "2026-07-06", "price": 600.0}],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 200

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.total_price == Decimal("600.00")
        # The 400.00 already captured no longer covers the stay, so the
        # booking goes back to partially charged and the rebuilt schedule
        # entry is pending again for the accrual job to pick up.
        assert stored.payment_status == "partially_charged"
        assert [entry.status for entry in stored.charge_schedule] == ["pending"]
        assert outstanding_amount(stored, date(2026, 7, 1)) == Decimal("200.00")

    async def test_an_edit_that_still_covers_the_charges_stays_settled(
        self, client, guest, cancellation_policy, admin_headers
    ):
        booking_id = await self._charged_booking(client, guest, cancellation_policy, admin_headers)

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                # Same total, later dates: the rebuilt schedule moves with the
                # stay but is still fully covered by what was charged.
                date_ranges=[{"begin_date": "2026-07-20", "end_date": "2026-07-24", "price": 400.0}],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 200

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.payment_status == "fully_charged"
        assert [entry.status for entry in stored.charge_schedule] == ["done"]
        assert outstanding_amount(stored, date(2026, 7, 24)) == Decimal("0.00")

    async def test_an_unpaid_booking_keeps_its_card_verified_status(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # A free-cancellation booking is Active with a verified card and
        # nothing charged; re-deriving payment_status from a zero
        # amount_charged would wrongly read as partially charged.
        created = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        booking_id = created.json()["_id"]
        booking = await Booking.get(PydanticObjectId(booking_id))
        await booking.set({Booking.status: "Active", Booking.payment_status: "card_verified"})

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(
                guest.id,
                cancellation_policy.id,
                date_ranges=[{"begin_date": "2026-07-01", "end_date": "2026-07-06", "price": 500.0}],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 200

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.payment_status == "card_verified"
        assert [entry.status for entry in stored.charge_schedule] == ["pending"]


class TestUpdateBookingRechecksAvailability:
    """A Pending booking blocks nothing, so its dates can go stale while it
    sits in checkout. Moving it has to be checked against what is actually
    booked or closed — the unique index on booked_nights only catches Active
    bookings clashing with each other."""

    async def _active_booking(self, client, guest, cancellation_policy, admin_headers, date_ranges):
        created = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id, date_ranges=date_ranges),
            headers=admin_headers,
        )
        booking = await Booking.get(PydanticObjectId(created.json()["_id"]))
        await booking.set(
            {Booking.status: "Active", Booking.booked_nights: nights_of_ranges(booking.date_ranges)}
        )
        return booking

    async def test_moving_a_pending_booking_onto_taken_nights_is_refused(
        self, client, guest, other_guest, cancellation_policy, admin_headers, other_guest_headers, plan, price
    ):
        await self._active_booking(
            client,
            guest,
            cancellation_policy,
            admin_headers,
            [{"begin_date": "2026-07-10", "end_date": "2026-07-15", "price": 500.0}],
        )
        created = await client.post(
            "/bookings", json=_plan_payload(other_guest.id, plan.name), headers=other_guest_headers
        )
        booking_id = created.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_plan_payload(
                other_guest.id,
                plan.name,
                date_ranges=[{"begin_date": "2026-07-12", "end_date": "2026-07-14"}],
            ),
            headers=other_guest_headers,
        )
        assert response.status_code == 409

        stored = await Booking.get(PydanticObjectId(booking_id))
        assert stored.date_ranges[0].begin_date == date(2026, 7, 1)

    async def test_moving_a_pending_booking_onto_a_closure_is_refused(
        self, client, guest, cancellation_policy, guest_headers, closure, plan, price
    ):
        created = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        booking_id = created.json()["_id"]

        # The closure fixture blocks 2026-08-01 to 2026-08-05.
        response = await client.put(
            f"/bookings/{booking_id}",
            json=_plan_payload(
                guest.id,
                plan.name,
                date_ranges=[{"begin_date": "2026-08-02", "end_date": "2026-08-04"}],
            ),
            headers=guest_headers,
        )
        assert response.status_code == 409

    async def test_free_dates_are_still_accepted(
        self, client, guest, other_guest, cancellation_policy, admin_headers, guest_headers, plan, price
    ):
        await self._active_booking(
            client,
            other_guest,
            cancellation_policy,
            admin_headers,
            [{"begin_date": "2026-07-10", "end_date": "2026-07-15", "price": 500.0}],
        )
        created = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        booking_id = created.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_plan_payload(
                guest.id,
                plan.name,
                # Checkout on the other booking's check-in day: end_date is
                # exclusive, so these do not overlap.
                date_ranges=[{"begin_date": "2026-07-06", "end_date": "2026-07-10"}],
            ),
            headers=guest_headers,
        )
        assert response.status_code == 200
        assert response.json()["date_ranges"][0]["end_date"] == "2026-07-10"


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

    async def test_still_persisted_for_an_active_booking(
        self, client, guest, cancellation_policy, admin_headers
    ):
        # Excluding it from responses must not mean excluding it from writes:
        # an update on an Active booking still has to keep the index in sync.
        created = await client.post(
            "/bookings", json=_booking_payload(guest.id, cancellation_policy.id), headers=admin_headers
        )
        booking_id = created.json()["_id"]
        booking = await Booking.get(PydanticObjectId(booking_id))
        await booking.set({Booking.status: "Active"})

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
        assert [night.isoformat() for night in stored.booked_nights] == [
            "2026-08-01",
            "2026-08-02",
            "2026-08-03",
        ]


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
