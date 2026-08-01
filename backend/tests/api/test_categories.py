import pytest

pytestmark = pytest.mark.anyio


class TestCreateCategory:
    async def test_creates_category(self, client, admin_headers):
        response = await client.post(
            "/categories", json={"slug": "hero", "name": "Hero"}, headers=admin_headers
        )
        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "hero"
        assert body["name"] == "Hero"
        assert body["sort_order"] == 0

    async def test_appends_sort_order_after_existing_categories(self, client, category, admin_headers):
        response = await client.post(
            "/categories", json={"slug": "hero", "name": "Hero"}, headers=admin_headers
        )
        assert response.status_code == 201
        assert response.json()["sort_order"] == category.sort_order + 1

    async def test_rejects_duplicate_slug(self, client, category, admin_headers):
        response = await client.post(
            "/categories", json={"slug": category.slug, "name": "Another name"}, headers=admin_headers
        )
        assert response.status_code == 409

    async def test_rejects_invalid_slug(self, client, admin_headers):
        response = await client.post(
            "/categories", json={"slug": "Not Valid!", "name": "Bad"}, headers=admin_headers
        )
        assert response.status_code == 422

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post(
            "/categories", json={"slug": "hero", "name": "Hero"}, headers=guest_headers
        )
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post("/categories", json={"slug": "hero", "name": "Hero"})
        assert response.status_code == 401


class TestListCategories:
    async def test_lists_categories_sorted(self, client, admin_headers):
        await client.post("/categories", json={"slug": "b", "name": "B"}, headers=admin_headers)
        await client.post("/categories", json={"slug": "a", "name": "A"}, headers=admin_headers)
        response = await client.get("/categories", headers=admin_headers)
        assert response.status_code == 200
        slugs = [c["slug"] for c in response.json()]
        assert slugs == ["b", "a"]

    async def test_requires_admin(self, client, guest_headers):
        response = await client.get("/categories", headers=guest_headers)
        assert response.status_code == 403


class TestUpdateCategory:
    async def test_renames_category(self, client, category, admin_headers):
        response = await client.patch(
            f"/categories/{category.id}", json={"name": "Renamed"}, headers=admin_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed"
        assert body["slug"] == category.slug

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.patch(
            "/categories/000000000000000000000000", json={"name": "X"}, headers=admin_headers
        )
        assert response.status_code == 404


class TestDeleteCategory:
    async def test_deletes_empty_category(self, client, category, admin_headers):
        response = await client.delete(f"/categories/{category.id}", headers=admin_headers)
        assert response.status_code == 204

        follow_up = await client.get("/categories", headers=admin_headers)
        assert follow_up.json() == []

    async def test_rejects_delete_when_category_has_photos(self, client, category, image, admin_headers):
        response = await client.delete(f"/categories/{category.id}", headers=admin_headers)
        assert response.status_code == 409

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete("/categories/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_admin(self, client, category, guest_headers):
        response = await client.delete(f"/categories/{category.id}", headers=guest_headers)
        assert response.status_code == 403
