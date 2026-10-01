"""Admin API for automated guest messages (app.api.routes.message_templates)."""

from datetime import date

import pytest

from app.models.message_delivery import MessageDelivery
from app.services import guest_messages

pytestmark = pytest.mark.anyio


def _payload(**overrides):
    payload = {
        "name": "Welcome",
        "anchor": "checkin",
        "direction": "before",
        "offset_days": 2,
        "versions": [
            {"language": "en", "subject": "See you soon, {{guest_first_name}}", "body_markdown": "**Hi** {{guest_first_name}}"},
            {"language": "de", "subject": "Bis bald", "body_markdown": "Hallo {{ guest_first_name }}"},
        ],
    }
    payload.update(overrides)
    return payload


class TestMessageTemplateCrud:
    async def test_create_list_update_delete(self, client, admin_headers):
        created = await client.post("/message-templates", json=_payload(), headers=admin_headers)
        assert created.status_code == 201
        body = created.json()
        assert body["active"] is True
        assert [v["language"] for v in body["versions"]] == ["en", "de"]
        template_id = body["_id"]

        listed = await client.get("/message-templates", headers=admin_headers)
        assert [t["_id"] for t in listed.json()] == [template_id]
        stored_created_at = listed.json()[0]["created_at"]

        updated = await client.put(
            f"/message-templates/{template_id}", json=_payload(name="Renamed", offset_days=3), headers=admin_headers
        )
        assert updated.status_code == 200
        assert (updated.json()["name"], updated.json()["offset_days"]) == ("Renamed", 3)
        # An edit must not move the bound the send job looks back to.
        assert updated.json()["created_at"] == stored_created_at

        deleted = await client.delete(f"/message-templates/{template_id}", headers=admin_headers)
        assert deleted.status_code == 204
        assert (await client.get("/message-templates", headers=admin_headers)).json() == []

    async def test_admin_only(self, client, guest_headers):
        assert (await client.get("/message-templates", headers=guest_headers)).status_code == 403
        assert (await client.post("/message-templates", json=_payload())).status_code == 401

    @pytest.mark.parametrize(
        "overrides, message",
        [
            ({"anchor": "booking_date", "direction": "before"}, "before the booking date"),
            ({"versions": []}, "at least one language"),
            (
                {
                    "versions": [
                        {"language": "en", "subject": "a", "body_markdown": "b"},
                        {"language": "en", "subject": "c", "body_markdown": "d"},
                    ]
                },
                "only one version",
            ),
            (
                {"versions": [{"language": "en", "subject": "Hi {{guest_firstname}}", "body_markdown": "b"}]},
                "{{guest_firstname}}",
            ),
            ({"offset_days": -1}, "greater than or equal to 0"),
        ],
    )
    async def test_rejects_invalid_templates(self, client, admin_headers, overrides, message):
        response = await client.post("/message-templates", json=_payload(**overrides), headers=admin_headers)
        assert response.status_code == 422
        assert message in str(response.json()["detail"])

    async def test_deleting_a_template_drops_its_delivery_log(self, client, admin_headers):
        template_id = (await client.post("/message-templates", json=_payload(), headers=admin_headers)).json()["_id"]
        await MessageDelivery(
            template_id=template_id, booking_id="000000000000000000000001", scheduled_for=date(2026, 11, 1)
        ).insert()

        await client.delete(f"/message-templates/{template_id}", headers=admin_headers)
        assert await MessageDelivery.find_all().count() == 0


class TestTestSendAndStats:
    async def test_sends_the_chosen_version_with_sample_values_to_the_admin(
        self, client, admin, admin_headers, monkeypatch
    ):
        sent = []

        async def fake_email(to, subject, html, attachments=None):
            sent.append((to, subject, html))

        monkeypatch.setattr(guest_messages, "send_html_email", fake_email)
        template_id = (await client.post("/message-templates", json=_payload(), headers=admin_headers)).json()["_id"]

        response = await client.post(
            f"/message-templates/{template_id}/test-send", json={"language": "en"}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json() == {"to": admin.email, "subject": "See you soon, Anna"}
        assert sent[0][0] == admin.email
        assert "<strong>Hi</strong> Anna" in sent[0][2]

        missing = await client.post(
            f"/message-templates/{template_id}/test-send", json={"language": "fr"}, headers=admin_headers
        )
        assert missing.status_code == 400

    async def test_stats_count_deliveries_per_template(self, client, admin_headers):
        template_id = (await client.post("/message-templates", json=_payload(), headers=admin_headers)).json()["_id"]
        for n, status in enumerate(["sent", "sent", "failed"]):
            await MessageDelivery(
                template_id=template_id,
                booking_id=f"00000000000000000000000{n}",
                scheduled_for=date(2026, 11, 1),
                email_status=status,
            ).insert()

        response = await client.get("/message-templates/stats", headers=admin_headers)
        assert response.status_code == 200
        assert response.json() == [{"template_id": template_id, "sent": 2, "failed": 1, "skipped": 0}]

        deliveries = await client.get(f"/message-templates/{template_id}/deliveries", headers=admin_headers)
        assert len(deliveries.json()) == 3
