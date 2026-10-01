"""Images attached to automated guest messages: upload, validation, inline
rendering and the orphan sweep."""

import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image as PILImage

from app.core.config import settings
from app.models.image import MESSAGE_IMAGE_CATEGORY, Image
from app.models.message_template import MessageTemplate, MessageTemplateVersion
from app.services import guest_messages

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def image_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "image_storage_path", str(tmp_path))
    return tmp_path


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


async def _upload(client, admin_headers) -> dict:
    response = await client.post(
        "/message-templates/images", files={"file": ("Lake View.png", _png_bytes(), "image/png")}, headers=admin_headers
    )
    assert response.status_code == 201
    return response.json()


def _payload(image_ids, body):
    return {
        "name": "Welcome",
        "anchor": "checkin",
        "direction": "before",
        "offset_days": 2,
        "image_ids": image_ids,
        "versions": [{"language": "en", "subject": "Hi", "body_markdown": body}],
    }


class TestUpload:
    async def test_stores_the_image_like_photos_do(self, client, admin_headers, image_dir):
        image = await _upload(client, admin_headers)
        assert image["category"] == MESSAGE_IMAGE_CATEGORY
        assert image["key"].startswith("guest-messages-lake-view-")
        assert (image_dir / image["key"]).is_file()

        listed = await client.get("/message-templates/images", headers=admin_headers)
        assert [i["_id"] for i in listed.json()] == [image["_id"]]

    async def test_admin_only(self, client, guest_headers):
        response = await client.post(
            "/message-templates/images", files={"file": ("a.png", _png_bytes(), "image/png")}, headers=guest_headers
        )
        assert response.status_code == 403

    async def test_rejects_non_images(self, client, admin_headers):
        response = await client.post(
            "/message-templates/images", files={"file": ("a.txt", b"hello", "text/plain")}, headers=admin_headers
        )
        assert response.status_code == 422

    async def test_kept_out_of_the_photo_library(self, client, admin_headers, category):
        await _upload(client, admin_headers)
        assert (await client.get("/images")).json() == []

    async def test_the_category_slug_is_reserved(self, client, admin_headers):
        response = await client.post(
            "/categories", json={"slug": MESSAGE_IMAGE_CATEGORY, "name": "Mine"}, headers=admin_headers
        )
        assert response.status_code == 409


class TestTemplateValidation:
    async def test_saves_attached_and_placed_images(self, client, admin_headers):
        image = await _upload(client, admin_headers)
        response = await client.post(
            "/message-templates",
            json=_payload([image["_id"]], f"Look:\n\n{{{{image:{image['_id']}}}}}"),
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["image_ids"] == [image["_id"]]

    async def test_rejects_placing_an_image_that_is_not_attached(self, client, admin_headers):
        image = await _upload(client, admin_headers)
        response = await client.post(
            "/message-templates", json=_payload([], f"{{{{image:{image['_id']}}}}}"), headers=admin_headers
        )
        assert response.status_code == 422
        assert "not attached" in str(response.json()["detail"])

    async def test_rejects_an_image_in_the_subject(self, client, admin_headers):
        image = await _upload(client, admin_headers)
        payload = _payload([image["_id"]], "Body")
        payload["versions"][0]["subject"] = f"Hi {{{{image:{image['_id']}}}}}"
        response = await client.post("/message-templates", json=payload, headers=admin_headers)
        assert response.status_code == 422

    async def test_rejects_ids_that_are_not_message_images(self, client, admin_headers):
        response = await client.post(
            "/message-templates", json=_payload(["000000000000000000000001"], "Body"), headers=admin_headers
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "Unknown image attached to the message"


class TestRendering:
    async def test_images_travel_inline_with_the_email(self, client, admin_headers):
        image = await _upload(client, admin_headers)
        template = MessageTemplate.model_validate(
            _payload([image["_id"]], f"Hello {{{{guest_first_name}}}}\n\n{{{{image:{image['_id']}}}}}")
        )
        images = await guest_messages.attached_images(template)
        message = guest_messages.render_message(template.versions[0], {"guest_first_name": "Anna"}, images)

        content_id = f"image-{image['_id']}@guest-message"
        assert f'src="cid:{content_id}"' in message.html
        assert 'style="max-width:100%;height:auto;"' in message.html
        assert [(a.content_id, a.mime_type) for a in message.attachments] == [(content_id, "image/png")]
        assert message.attachments[0].content.startswith(b"\x89PNG")

    async def test_unplaced_images_are_not_attached(self, client, admin_headers):
        image = await _upload(client, admin_headers)
        template = MessageTemplate.model_validate(_payload([image["_id"]], "No pictures here"))
        message = guest_messages.render_message(
            template.versions[0], {}, await guest_messages.attached_images(template)
        )
        assert message.attachments == []

    async def test_a_missing_image_file_is_dropped_rather_than_left_as_braces(self, client, admin_headers, image_dir):
        image = await _upload(client, admin_headers)
        (image_dir / image["key"]).unlink()
        template = MessageTemplate.model_validate(_payload([image["_id"]], f"A{{{{image:{image['_id']}}}}}B"))
        message = guest_messages.render_message(
            template.versions[0], {}, await guest_messages.attached_images(template)
        )
        assert "<p>AB</p>" in message.html
        assert message.attachments == []

    async def test_test_send_carries_the_images(self, client, admin, admin_headers, monkeypatch):
        sent = []

        async def fake_email(to, subject, html, attachments=None):
            sent.append(attachments)

        monkeypatch.setattr(guest_messages, "send_html_email", fake_email)
        image = await _upload(client, admin_headers)
        template_id = (
            await client.post(
                "/message-templates",
                json=_payload([image["_id"]], f"{{{{image:{image['_id']}}}}}"),
                headers=admin_headers,
            )
        ).json()["_id"]

        response = await client.post(
            f"/message-templates/{template_id}/test-send", json={"language": "en"}, headers=admin_headers
        )
        assert response.status_code == 200
        assert len(sent[0]) == 1


class TestPurgeOrphanImages:
    async def _image(self, image_dir, uploaded_at, name):
        (image_dir / name).write_bytes(b"x")
        image = Image(
            key=name, category=MESSAGE_IMAGE_CATEGORY, content_type="image/png", size_bytes=1, uploaded_at=uploaded_at
        )
        await image.insert()
        return image

    async def test_deletes_only_old_images_no_message_uses(self, client, image_dir):
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        old = now - timedelta(days=2)
        used = await self._image(image_dir, old, "used.png")
        orphan = await self._image(image_dir, old, "orphan.png")
        fresh = await self._image(image_dir, now - timedelta(hours=1), "fresh.png")
        await MessageTemplate(
            name="t",
            anchor="checkin",
            direction="before",
            offset_days=1,
            image_ids=[used.id],
            versions=[MessageTemplateVersion(language="en", subject="s", body_markdown="b")],
        ).insert()

        assert await guest_messages.purge_orphan_images(now) == 1
        assert {i.key for i in await Image.find_all().to_list()} == {"used.png", "fresh.png"}
        assert not (image_dir / "orphan.png").exists()
        assert (image_dir / "used.png").exists() and (image_dir / "fresh.png").exists()
        assert orphan.id not in {i.id for i in await Image.find_all().to_list()}
        assert fresh.id is not None
