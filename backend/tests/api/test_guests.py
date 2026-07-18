import pytest

from app.core.security import create_access_token
from app.models.guest import Guest

pytestmark = pytest.mark.anyio


def _pending_guest_headers(identifier: str) -> dict[str, str]:
    token, _ = create_access_token(identifier, "pending_guest")
    return {"Authorization": f"Bearer {token}"}


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
        body = response.json()
        assert body["guest"]["email"] == "jane@example.com"
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post("/guests", json=_guest_payload(), headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post("/guests", json=_guest_payload())
        assert response.status_code == 401

    async def test_normalizes_phone_number_formatting_before_storing(self, client, admin_headers):
        payload = _guest_payload(phone_number="+1 (555) 777-8888")
        response = await client.post("/guests", json=payload, headers=admin_headers)
        assert response.status_code == 201
        assert response.json()["guest"]["phone_number"] == "+15557778888"

    async def test_rejects_invalid_phone_number(self, client, admin_headers):
        response = await client.post("/guests", json=_guest_payload(phone_number="not-a-phone"), headers=admin_headers)
        assert response.status_code == 400


class TestRegisterGuestSelf:
    async def test_registers_guest_using_verified_email(self, client):
        headers = _pending_guest_headers("newperson@example.com")
        payload = _guest_payload(phone_number="+15559990000")
        del payload["email"]

        response = await client.post("/guests/self", json=payload, headers=headers)
        assert response.status_code == 201
        body = response.json()
        assert body["guest"]["email"] == "newperson@example.com"
        assert body["guest"]["phone_number"] == "+15559990000"
        assert body["token_type"] == "bearer"
        assert "access_token" in body

        stored = await Guest.find_one(Guest.email == "newperson@example.com")
        assert stored is not None

    async def test_registers_guest_using_verified_phone(self, client):
        headers = _pending_guest_headers("+15559990000")
        payload = _guest_payload(email="newperson@example.com")
        del payload["phone_number"]

        response = await client.post("/guests/self", json=payload, headers=headers)
        assert response.status_code == 201
        assert response.json()["guest"]["phone_number"] == "+15559990000"

    async def test_ignores_client_supplied_email_for_verified_field(self, client):
        headers = _pending_guest_headers("newperson@example.com")
        payload = _guest_payload(email="attacker@example.com", phone_number="+15559990000")

        response = await client.post("/guests/self", json=payload, headers=headers)
        assert response.status_code == 201
        assert response.json()["guest"]["email"] == "newperson@example.com"

    async def test_rejects_when_guest_already_exists(self, client, guest):
        headers = _pending_guest_headers(guest.email)
        payload = _guest_payload(phone_number="+15559990000")
        del payload["email"]

        response = await client.post("/guests/self", json=payload, headers=headers)
        assert response.status_code == 409

    async def test_requires_pending_guest_token(self, client, guest_headers):
        payload = _guest_payload(phone_number="+15559990000")
        del payload["email"]

        response = await client.post("/guests/self", json=payload, headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        payload = _guest_payload(phone_number="+15559990000")
        del payload["email"]

        response = await client.post("/guests/self", json=payload)
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

    async def test_normalizes_phone_number_formatting_before_storing(self, client, guest, guest_headers):
        response = await client.put(
            f"/guests/{guest.id}",
            json=_guest_payload(phone_number="+1 (555) 777-8888"),
            headers=guest_headers,
        )
        assert response.status_code == 200
        assert response.json()["phone_number"] == "+15557778888"


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
