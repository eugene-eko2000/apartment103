import pytest

pytestmark = pytest.mark.anyio


def _guest_payload(**overrides):
    payload = {
        "family_name": "Doe",
        "first_name": "Jane",
        "residence_address": {
            "street_address": "10 Elm St",
            "zip": "99999",
            "city": "Metropolis",
            "country": "US",
        },
        "phone_number": "+15557778888",
        "email": "jane@example.com",
    }
    payload.update(overrides)
    return payload


class TestCreateGuest:
    async def test_creates_guest(self, client, admin_headers):
        response = await client.post("/guests", json=_guest_payload(), headers=admin_headers)
        assert response.status_code == 201
        assert response.json()["email"] == "jane@example.com"

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post("/guests", json=_guest_payload(), headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post("/guests", json=_guest_payload())
        assert response.status_code == 401


class TestListGuests:
    async def test_lists_all_guests_for_admin(self, client, guest, admin_headers):
        response = await client.get("/guests", headers=admin_headers)
        assert response.status_code == 200
        emails = {g["email"] for g in response.json()}
        assert emails == {guest.email}

    async def test_requires_admin(self, client, guest_headers):
        response = await client.get("/guests", headers=guest_headers)
        assert response.status_code == 403


class TestGetGuest:
    async def test_admin_can_access_any_guest(self, client, guest, admin_headers):
        response = await client.get(f"/guests/{guest.id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["email"] == guest.email

    async def test_guest_can_access_own_record(self, client, guest, guest_headers):
        response = await client.get(f"/guests/{guest.id}", headers=guest_headers)
        assert response.status_code == 200
        assert response.json()["email"] == guest.email

    async def test_guest_cannot_access_other_guest_record(self, client, other_guest, guest_headers):
        response = await client.get(f"/guests/{other_guest.id}", headers=guest_headers)
        assert response.status_code == 403

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.get("/guests/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_authentication(self, client, guest):
        response = await client.get(f"/guests/{guest.id}")
        assert response.status_code == 401


class TestUpdateGuest:
    async def test_guest_can_update_own_record(self, client, guest, guest_headers):
        response = await client.put(
            f"/guests/{guest.id}",
            json=_guest_payload(first_name="Updated"),
            headers=guest_headers,
        )
        assert response.status_code == 200
        assert response.json()["first_name"] == "Updated"

    async def test_guest_cannot_update_other_guest_record(self, client, other_guest, guest_headers):
        response = await client.put(
            f"/guests/{other_guest.id}",
            json=_guest_payload(),
            headers=guest_headers,
        )
        assert response.status_code == 403

    async def test_admin_can_update_any_guest(self, client, guest, admin_headers):
        response = await client.put(
            f"/guests/{guest.id}",
            json=_guest_payload(first_name="ByAdmin"),
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["first_name"] == "ByAdmin"

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.put(
            "/guests/000000000000000000000000",
            json=_guest_payload(),
            headers=admin_headers,
        )
        assert response.status_code == 404


class TestDeleteGuest:
    async def test_admin_can_delete_guest(self, client, guest, admin_headers):
        response = await client.delete(f"/guests/{guest.id}", headers=admin_headers)
        assert response.status_code == 204

        follow_up = await client.get(f"/guests/{guest.id}", headers=admin_headers)
        assert follow_up.status_code == 404

    async def test_requires_admin(self, client, guest, guest_headers):
        response = await client.delete(f"/guests/{guest.id}", headers=guest_headers)
        assert response.status_code == 403

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete("/guests/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404
