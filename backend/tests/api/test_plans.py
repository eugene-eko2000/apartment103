import pytest

pytestmark = pytest.mark.anyio


def _plan_payload(cancellation_policy_id, **overrides):
    payload = {
        "name": "Summer Plan",
        "cancellation_policy_id": str(cancellation_policy_id),
        "currency": "CHF",
        "default_price": 100.0,
        "date_ranges": [
            {"begin_date": "2026-07-01", "end_date": "2026-08-01", "daily_rate": 120.0}
        ],
    }
    payload.update(overrides)
    return payload


class TestCreatePlan:
    async def test_creates_plan(self, client, cancellation_policy, admin_headers):
        response = await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=admin_headers
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Summer Plan"
        assert body["default_price"] == 100.0

    async def test_returns_404_for_unknown_cancellation_policy(self, client, admin_headers):
        response = await client.post(
            "/plans",
            json=_plan_payload("000000000000000000000000"),
            headers=admin_headers,
        )
        assert response.status_code == 404

    async def test_requires_admin(self, client, cancellation_policy, guest_headers):
        response = await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=guest_headers
        )
        assert response.status_code == 403

    async def test_requires_authentication(self, client, cancellation_policy):
        response = await client.post("/plans", json=_plan_payload(cancellation_policy.id))
        assert response.status_code == 401


class TestListPublicPlans:
    async def test_lists_plans_without_authentication(
        self, client, cancellation_policy, admin_headers
    ):
        await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=admin_headers
        )

        response = await client.get("/plans/public")
        assert response.status_code == 200
        names = {p["name"] for p in response.json()}
        assert names == {"Summer Plan"}
        assert response.json()[0]["cancellation_policy"]["name"] == cancellation_policy.name


class TestListPlans:
    async def test_lists_all_plans(self, client, cancellation_policy, admin_headers):
        await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=admin_headers
        )
        response = await client.get("/plans", headers=admin_headers)
        assert response.status_code == 200
        names = {p["name"] for p in response.json()}
        assert names == {"Summer Plan"}

    async def test_requires_admin(self, client, guest_headers):
        response = await client.get("/plans", headers=guest_headers)
        assert response.status_code == 403


class TestGetPlan:
    async def test_returns_plan(self, client, cancellation_policy, admin_headers):
        create_response = await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=admin_headers
        )
        plan_id = create_response.json()["_id"]

        response = await client.get(f"/plans/{plan_id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Summer Plan"

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.get("/plans/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404


class TestUpdatePlan:
    async def test_updates_plan_fields(self, client, cancellation_policy, admin_headers):
        create_response = await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=admin_headers
        )
        plan_id = create_response.json()["_id"]

        response = await client.put(
            f"/plans/{plan_id}",
            json=_plan_payload(cancellation_policy.id, name="Winter Plan"),
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Winter Plan"

    async def test_returns_404_for_unknown_plan_id(self, client, cancellation_policy, admin_headers):
        response = await client.put(
            "/plans/000000000000000000000000",
            json=_plan_payload(cancellation_policy.id),
            headers=admin_headers,
        )
        assert response.status_code == 404

    async def test_returns_404_for_unknown_cancellation_policy(
        self, client, cancellation_policy, admin_headers
    ):
        create_response = await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=admin_headers
        )
        plan_id = create_response.json()["_id"]

        response = await client.put(
            f"/plans/{plan_id}",
            json=_plan_payload("000000000000000000000000"),
            headers=admin_headers,
        )
        assert response.status_code == 404


class TestDeletePlan:
    async def test_deletes_plan(self, client, cancellation_policy, admin_headers):
        create_response = await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=admin_headers
        )
        plan_id = create_response.json()["_id"]

        response = await client.delete(f"/plans/{plan_id}", headers=admin_headers)
        assert response.status_code == 204

        follow_up = await client.get(f"/plans/{plan_id}", headers=admin_headers)
        assert follow_up.status_code == 404

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete("/plans/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_admin(self, client, cancellation_policy, admin_headers, guest_headers):
        create_response = await client.post(
            "/plans", json=_plan_payload(cancellation_policy.id), headers=admin_headers
        )
        plan_id = create_response.json()["_id"]

        response = await client.delete(f"/plans/{plan_id}", headers=guest_headers)
        assert response.status_code == 403
