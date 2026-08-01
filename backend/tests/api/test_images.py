import io

import pytest
from PIL import Image as PILImage

pytestmark = pytest.mark.anyio


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_files() -> dict:
    return {"file": ("photo.png", _png_bytes(), "image/png")}


class TestUploadImage:
    async def test_rejects_unknown_category(self, client, admin_headers):
        response = await client.post(
            "/images",
            data={"category": "does-not-exist", "alt": ""},
            files=_upload_files(),
            headers=admin_headers,
        )
        assert response.status_code == 422

    async def test_uploads_into_known_category(self, client, category, admin_headers):
        response = await client.post(
            "/images",
            data={"category": category.slug, "alt": "A photo"},
            files=_upload_files(),
            headers=admin_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["category"] == category.slug
        assert body["sort_order"] == 0

    async def test_auto_appends_sort_order_when_omitted(self, client, category, image, admin_headers):
        response = await client.post(
            "/images",
            data={"category": category.slug, "alt": "Second photo"},
            files=_upload_files(),
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["sort_order"] == image.sort_order + 1


class TestReorderImages:
    async def test_updates_category_and_sort_order_in_bulk(self, client, category, image, admin_headers):
        other_category = await client.post(
            "/categories", json={"slug": "hero", "name": "Hero"}, headers=admin_headers
        )
        other_slug = other_category.json()["slug"]

        response = await client.post(
            "/images/reorder",
            json={"updates": [{"id": str(image.id), "category": other_slug, "sort_order": 5}]},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["category"] == other_slug
        assert body[0]["sort_order"] == 5

    async def test_empty_updates_returns_empty_list(self, client, admin_headers):
        response = await client.post("/images/reorder", json={"updates": []}, headers=admin_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_requires_admin(self, client, image, guest_headers):
        response = await client.post(
            "/images/reorder",
            json={"updates": [{"id": str(image.id), "category": image.category, "sort_order": 1}]},
            headers=guest_headers,
        )
        assert response.status_code == 403
