from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import hash_otp_code
from app.models.otp_challenge import OtpChallenge

pytestmark = pytest.mark.anyio


async def _create_challenge(identifier: str, code: str, **overrides) -> OtpChallenge:
    now = datetime.now(timezone.utc)
    challenge = OtpChallenge(
        identifier=identifier,
        channel="email" if "@" in identifier else "sms",
        code_hash=hash_otp_code(identifier, code),
        expires_at=overrides.pop("expires_at", now + timedelta(seconds=300)),
        attempts=overrides.pop("attempts", 0),
        consumed_at=overrides.pop("consumed_at", None),
        created_at=overrides.pop("created_at", now),
    )
    await challenge.insert()
    return challenge


class TestVerifyToken:
    async def test_accepts_valid_guest_token(self, client, guest_headers):
        response = await client.get("/auth/token/verify", headers=guest_headers)
        assert response.status_code == 200
        assert response.json() == {"status": "OK"}

    async def test_accepts_valid_admin_token(self, client, admin_headers):
        response = await client.get("/auth/token/verify", headers=admin_headers)
        assert response.status_code == 200
        assert response.json() == {"status": "OK"}

    async def test_rejects_missing_token(self, client):
        response = await client.get("/auth/token/verify")
        assert response.status_code == 401

    async def test_rejects_malformed_token(self, client):
        response = await client.get(
            "/auth/token/verify", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401

    async def test_rejects_token_for_deleted_guest(self, client, guest):
        from app.core.security import create_access_token

        token, _ = create_access_token(str(guest.id), "guest")
        await guest.delete()

        response = await client.get(
            "/auth/token/verify", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


class TestRequestOtp:
    async def test_accepts_known_guest_email_and_creates_challenge(self, client, guest):
        response = await client.post("/auth/otp/request", json={"identifier": guest.email})
        assert response.status_code == 202

        challenges = await OtpChallenge.find(OtpChallenge.identifier == guest.email).to_list()
        assert len(challenges) == 1
        assert challenges[0].channel == "email"

    async def test_accepts_known_admin_email_and_creates_challenge(self, client, admin):
        response = await client.post("/auth/otp/request", json={"identifier": admin.email})
        assert response.status_code == 202

        challenges = await OtpChallenge.find(OtpChallenge.identifier == admin.email).to_list()
        assert len(challenges) == 1

    async def test_accepts_known_guest_phone_and_creates_sms_challenge(self, client, guest):
        response = await client.post("/auth/otp/request", json={"identifier": guest.phone_number})
        assert response.status_code == 202

        challenges = await OtpChallenge.find(
            OtpChallenge.identifier == guest.phone_number
        ).to_list()
        assert len(challenges) == 1
        assert challenges[0].channel == "sms"

    async def test_sends_otp_for_unknown_identifier(self, client):
        """Unknown identifiers also get a challenge: verifying it is how a
        first-time guest registers, so there's no known/unknown to hide."""
        response = await client.post(
            "/auth/otp/request", json={"identifier": "nobody@example.com"}
        )
        assert response.status_code == 202

        challenges = await OtpChallenge.find(
            OtpChallenge.identifier == "nobody@example.com"
        ).to_list()
        assert len(challenges) == 1

    async def test_rejects_malformed_identifier(self, client):
        response = await client.post("/auth/otp/request", json={"identifier": "not-an-identifier"})
        assert response.status_code == 400

    async def test_second_request_within_cooldown_does_not_create_new_challenge(
        self, client, guest
    ):
        first = await client.post("/auth/otp/request", json={"identifier": guest.email})
        second = await client.post("/auth/otp/request", json={"identifier": guest.email})
        assert first.status_code == 202
        assert second.status_code == 202

        challenges = await OtpChallenge.find(OtpChallenge.identifier == guest.email).to_list()
        assert len(challenges) == 1

    async def test_request_after_cooldown_creates_new_challenge(self, client, guest, monkeypatch):
        from app.api.routes import auth as auth_module

        monkeypatch.setattr(auth_module.settings, "otp_resend_cooldown_seconds", 0)

        await client.post("/auth/otp/request", json={"identifier": guest.email})
        await client.post("/auth/otp/request", json={"identifier": guest.email})

        challenges = await OtpChallenge.find(OtpChallenge.identifier == guest.email).to_list()
        assert len(challenges) == 2


class TestVerifyOtp:
    async def test_verifies_valid_code_for_guest(self, client, guest):
        await _create_challenge(guest.email, "123456")

        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.email, "code": "123456"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject_type"] == "guest"
        assert body["subject_id"] == str(guest.id)
        assert body["token_type"] == "bearer"
        assert "access_token" in body

    async def test_verifies_valid_code_for_admin(self, client, admin):
        await _create_challenge(admin.email, "654321")

        response = await client.post(
            "/auth/otp/verify", json={"identifier": admin.email, "code": "654321"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject_type"] == "admin"
        assert body["subject_id"] == str(admin.id)

    async def test_default_audience_resolves_to_guest_when_identifier_is_also_an_admin(
        self, client, admin, guest
    ):
        """Same person can hold both roles (e.g. staff booking for themselves).
        The default ("guest") audience — used by the booking flow and the
        header login — resolves to guest so the booking form identifies and
        pre-fills them."""
        admin.phone_number = guest.phone_number
        await admin.save()

        await _create_challenge(guest.phone_number, "111222")
        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.phone_number, "code": "111222"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject_type"] == "guest"
        assert body["subject_id"] == str(guest.id)

    async def test_admin_audience_resolves_to_admin_when_identifier_is_also_a_guest(
        self, client, admin, guest
    ):
        """The admin-dashboard login (audience="admin") must still resolve to
        admin for someone who holds both roles, or they'd be locked out of
        /admin once they also have a guest profile."""
        admin.phone_number = guest.phone_number
        await admin.save()

        await _create_challenge(guest.phone_number, "333444")
        response = await client.post(
            "/auth/otp/verify",
            json={"identifier": guest.phone_number, "code": "333444", "audience": "admin"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject_type"] == "admin"
        assert body["subject_id"] == str(admin.id)

    async def test_marks_challenge_consumed_after_verification(self, client, guest):
        challenge = await _create_challenge(guest.email, "123456")

        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.email, "code": "123456"}
        )
        assert response.status_code == 200

        refreshed = await OtpChallenge.get(challenge.id)
        assert refreshed.consumed_at is not None

    async def test_rejects_wrong_code_and_increments_attempts(self, client, guest):
        challenge = await _create_challenge(guest.email, "123456")

        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.email, "code": "000000"}
        )
        assert response.status_code == 401

        refreshed = await OtpChallenge.get(challenge.id)
        assert refreshed.attempts == 1
        assert refreshed.consumed_at is None

    async def test_rejects_malformed_identifier(self, client):
        response = await client.post(
            "/auth/otp/verify", json={"identifier": "not-an-identifier", "code": "123456"}
        )
        assert response.status_code == 400

    async def test_rejects_when_no_challenge_exists(self, client, guest):
        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.email, "code": "123456"}
        )
        assert response.status_code == 401

    async def test_rejects_expired_challenge(self, client, guest):
        now = datetime.now(timezone.utc)
        await _create_challenge(
            guest.email,
            "123456",
            expires_at=now - timedelta(seconds=1),
            created_at=now - timedelta(seconds=600),
        )

        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.email, "code": "123456"}
        )
        assert response.status_code == 401

    async def test_rejects_after_max_attempts_reached(self, client, guest):
        await _create_challenge(guest.email, "123456", attempts=5)

        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.email, "code": "123456"}
        )
        assert response.status_code == 401

    async def test_rejects_already_consumed_challenge(self, client, guest):
        now = datetime.now(timezone.utc)
        await _create_challenge(guest.email, "123456", consumed_at=now)

        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.email, "code": "123456"}
        )
        assert response.status_code == 401

    async def test_uses_most_recent_unconsumed_challenge(self, client, guest):
        now = datetime.now(timezone.utc)
        await _create_challenge(
            guest.email, "111111", created_at=now - timedelta(seconds=60)
        )
        await _create_challenge(guest.email, "222222", created_at=now)

        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.email, "code": "222222"}
        )
        assert response.status_code == 200

    async def test_verifies_phone_identifier(self, client, guest):
        await _create_challenge(guest.phone_number, "123456")

        response = await client.post(
            "/auth/otp/verify", json={"identifier": guest.phone_number, "code": "123456"}
        )
        assert response.status_code == 200
        assert response.json()["subject_id"] == str(guest.id)

    async def test_matches_returning_guest_who_types_phone_in_a_different_format(self, client):
        """A guest stored with an E.164 number must still be recognized when
        they log in typing the equivalent local/differently-punctuated form,
        so the booking form gets pre-filled instead of treating them as new."""
        from app.models.guest import Guest, ResidenceAddress

        returning_guest = Guest(
            family_name="Meier",
            first_name="Anna",
            residence_address=ResidenceAddress(
                street_address="1 Bahnhofstrasse", zip="8001", city="Zurich", country="CH"
            ),
            phone_number="+41781234567",
            email="anna@example.com",
        )
        await returning_guest.insert()

        # The challenge is keyed by the normalized identifier, same as
        # POST /auth/otp/request would store it.
        await _create_challenge("+41781234567", "123456")
        response = await client.post(
            "/auth/otp/verify", json={"identifier": "078 123 45 67", "code": "123456"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject_type"] == "guest"
        assert body["subject_id"] == str(returning_guest.id)

    async def test_issues_pending_guest_token_for_unregistered_identifier(self, client):
        await _create_challenge("newperson@example.com", "123456")

        response = await client.post(
            "/auth/otp/verify", json={"identifier": "newperson@example.com", "code": "123456"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject_type"] == "pending_guest"
        assert body["subject_id"] == "newperson@example.com"
        assert "access_token" in body
