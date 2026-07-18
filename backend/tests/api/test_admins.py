import pytest

pytestmark = pytest.mark.anyio


class TestCreateAdmin:
    async def test_creates_admin(self, client, admin_headers):
        response = await client.post(
            "/admins",
            json={
                "family_name": "Smith",
                "first_name": "Sam",
                "phone_number": "+15551112222",
                "email": "sam@example.com",
            },
            headers=admin_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "sam@example.com"
        assert "_id" in body

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post(
            "/admins",
            json={
                "family_name": "Smith",
                "first_name": "Sam",
                "phone_number": "+15551112222",
                "email": "sam@example.com",
            },
            headers=guest_headers,
        )
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post(
            "/admins",
            json={
                "family_name": "Smith",
                "first_name": "Sam",
                "phone_number": "+15551112222",
                "email": "sam@example.com",
            },
        )
        assert response.status_code == 401

    async def test_normalizes_phone_number_formatting_before_storing(self, client, admin_headers):
        response = await client.post(
            "/admins",
            json={
                "family_name": "Smith",
                "first_name": "Sam",
                "phone_number": "+1 (555) 111-2222",
                "email": "sam@example.com",
            },
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["phone_number"] == "+15551112222"

    async def test_rejects_invalid_phone_number(self, client, admin_headers):
        response = await client.post(
            "/admins",
            json={
                "family_name": "Smith",
                "first_name": "Sam",
                "phone_number": "not-a-phone",
                "email": "sam@example.com",
            },
            headers=admin_headers,
        )
        assert response.status_code == 400


class TestListAdmins:
    async def test_lists_all_admins(self, client, admin, admin_headers):
        response = await client.get("/admins", headers=admin_headers)
        assert response.status_code == 200
        emails = {a["email"] for a in response.json()}
        assert emails == {admin.email}

    async def test_requires_admin(self, client, guest_headers):
        response = await client.get("/admins", headers=guest_headers)
        assert response.status_code == 403


class TestGetAdmin:
    async def test_returns_admin(self, client, admin, admin_headers):
        response = await client.get(f"/admins/{admin.id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["email"] == admin.email

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.get("/admins/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_admin(self, client, admin, guest_headers):
        response = await client.get(f"/admins/{admin.id}", headers=guest_headers)
        assert response.status_code == 403


class TestUpdateAdmin:
    async def test_updates_admin_fields(self, client, admin, admin_headers):
        response = await client.put(
            f"/admins/{admin.id}",
            json={
                "family_name": "Updated",
                "first_name": "Name",
                "phone_number": "+15559998888",
                "email": "updated@example.com",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["family_name"] == "Updated"
        assert body["email"] == "updated@example.com"

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.put(
            "/admins/000000000000000000000000",
            json={
                "family_name": "Updated",
                "first_name": "Name",
                "phone_number": "+15559998888",
                "email": "updated@example.com",
            },
            headers=admin_headers,
        )
        assert response.status_code == 404

    async def test_normalizes_phone_number_formatting_before_storing(self, client, admin, admin_headers):
        response = await client.put(
            f"/admins/{admin.id}",
            json={
                "family_name": "Updated",
                "first_name": "Name",
                "phone_number": "+1 (555) 999-8888",
                "email": "updated@example.com",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["phone_number"] == "+15559998888"


class TestDeleteAdmin:
    async def test_deletes_admin(self, client, admin, admin_headers, other_admin_headers):
        response = await client.delete(f"/admins/{admin.id}", headers=admin_headers)
        assert response.status_code == 204

        follow_up = await client.get(f"/admins/{admin.id}", headers=other_admin_headers)
        assert follow_up.status_code == 404

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete("/admins/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_admin(self, client, admin, guest_headers):
        response = await client.delete(f"/admins/{admin.id}", headers=guest_headers)
        assert response.status_code == 403
