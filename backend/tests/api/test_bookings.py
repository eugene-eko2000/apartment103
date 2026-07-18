import pytest

pytestmark = pytest.mark.anyio


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

    async def test_guest_can_create_booking_for_self(
        self, client, guest, cancellation_policy, guest_headers
    ):
        response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=guest_headers,
        )
        assert response.status_code == 201

    async def test_guest_cannot_create_booking_for_other_guest(
        self, client, other_guest, cancellation_policy, guest_headers
    ):
        response = await client.post(
            "/bookings",
            json=_booking_payload(other_guest.id, cancellation_policy.id),
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


class TestListPublicBookedDateRanges:
    async def test_lists_date_ranges_without_authentication(
        self, client, guest, cancellation_policy, admin_headers
    ):
        await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )

        response = await client.get("/bookings/public/date-ranges")
        assert response.status_code == 200
        body = response.json()
        assert body == [{"begin_date": "2026-07-01", "end_date": "2026-07-05"}]


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
        self, client, guest, cancellation_policy, guest_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
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
        self, client, guest, cancellation_policy, guest_headers, admin_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
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
        self, client, guest, cancellation_policy, guest_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(guest.id, cancellation_policy.id, currency="USD"),
            headers=guest_headers,
        )
        assert response.status_code == 200
        assert response.json()["currency"] == "USD"

    async def test_guest_cannot_update_other_guest_booking(
        self, client, guest, other_guest, cancellation_policy, admin_headers, other_guest_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=admin_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(guest.id, cancellation_policy.id, currency="USD"),
            headers=other_guest_headers,
        )
        assert response.status_code == 403

    async def test_guest_cannot_reassign_booking_to_other_guest(
        self, client, guest, other_guest, cancellation_policy, guest_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
            headers=guest_headers,
        )
        booking_id = create_response.json()["_id"]

        response = await client.put(
            f"/bookings/{booking_id}",
            json=_booking_payload(other_guest.id, cancellation_policy.id),
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


class TestDeleteBooking:
    async def test_guest_can_delete_own_booking(
        self, client, guest, cancellation_policy, guest_headers
    ):
        create_response = await client.post(
            "/bookings",
            json=_booking_payload(guest.id, cancellation_policy.id),
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
