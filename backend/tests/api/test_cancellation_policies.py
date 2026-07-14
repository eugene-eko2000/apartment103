import pytest

pytestmark = pytest.mark.anyio


def _policy_payload(**overrides):
    payload = {
        "name": "Strict",
        "rules": [{"days_before_checkin": 7, "refund_percentage": 0.5}],
    }
    payload.update(overrides)
    return payload


class TestCreateCancellationPolicy:
    async def test_creates_policy(self, client, admin_headers):
        response = await client.post(
            "/cancellation-policies", json=_policy_payload(), headers=admin_headers
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Strict"
        assert body["rules"] == [{"days_before_checkin": 7, "refund_percentage": 0.5}]

    async def test_defaults_rules_to_empty_list(self, client, admin_headers):
        response = await client.post(
            "/cancellation-policies", json={"name": "No rules"}, headers=admin_headers
        )
        assert response.status_code == 201
        assert response.json()["rules"] == []

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post(
            "/cancellation-policies", json=_policy_payload(), headers=guest_headers
        )
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post("/cancellation-policies", json=_policy_payload())
        assert response.status_code == 401


class TestListCancellationPolicies:
    async def test_lists_all_policies(self, client, cancellation_policy, admin_headers):
        response = await client.get("/cancellation-policies", headers=admin_headers)
        assert response.status_code == 200
        names = {p["name"] for p in response.json()}
        assert names == {cancellation_policy.name}

    async def test_requires_admin(self, client, guest_headers):
        response = await client.get("/cancellation-policies", headers=guest_headers)
        assert response.status_code == 403


class TestGetCancellationPolicy:
    async def test_returns_policy(self, client, cancellation_policy, admin_headers):
        response = await client.get(
            f"/cancellation-policies/{cancellation_policy.id}", headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["name"] == cancellation_policy.name

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.get(
            "/cancellation-policies/000000000000000000000000", headers=admin_headers
        )
        assert response.status_code == 404


class TestUpdateCancellationPolicy:
    async def test_updates_policy_fields(self, client, cancellation_policy, admin_headers):
        response = await client.put(
            f"/cancellation-policies/{cancellation_policy.id}",
            json=_policy_payload(name="Renamed"),
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.put(
            "/cancellation-policies/000000000000000000000000",
            json=_policy_payload(),
            headers=admin_headers,
        )
        assert response.status_code == 404


class TestDeleteCancellationPolicy:
    async def test_deletes_policy(self, client, cancellation_policy, admin_headers):
        response = await client.delete(
            f"/cancellation-policies/{cancellation_policy.id}", headers=admin_headers
        )
        assert response.status_code == 204

        follow_up = await client.get(
            f"/cancellation-policies/{cancellation_policy.id}", headers=admin_headers
        )
        assert follow_up.status_code == 404

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete(
            "/cancellation-policies/000000000000000000000000", headers=admin_headers
        )
        assert response.status_code == 404

    async def test_requires_admin(self, client, cancellation_policy, guest_headers):
        response = await client.delete(
            f"/cancellation-policies/{cancellation_policy.id}", headers=guest_headers
        )
        assert response.status_code == 403
