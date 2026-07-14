from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest

from app.core import security
from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_otp_code,
    hash_otp_code,
    verify_otp_code,
)

# 32+ bytes so PyJWT doesn't emit InsecureKeyLengthWarning for HS256 (RFC 7518 3.2).
TEST_JWT_SECRET_KEY = "test-only-secret-key-please-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _secure_jwt_secret(monkeypatch):
    monkeypatch.setattr(security.settings, "jwt_secret_key", TEST_JWT_SECRET_KEY)


class TestGenerateOtpCode:
    def test_returns_string_of_configured_length(self):
        code = generate_otp_code()
        assert len(code) == settings.otp_length
        assert code.isdigit()

    def test_respects_custom_otp_length(self, monkeypatch):
        monkeypatch.setattr(security.settings, "otp_length", 4)
        code = generate_otp_code()
        assert len(code) == 4
        assert code.isdigit()

    def test_zero_pads_small_values(self, monkeypatch):
        monkeypatch.setattr(security.settings, "otp_length", 6)
        with patch("app.core.security.secrets.randbelow", return_value=42):
            code = generate_otp_code()
        assert code == "000042"

    def test_uses_full_width_when_value_fills_length(self, monkeypatch):
        monkeypatch.setattr(security.settings, "otp_length", 6)
        with patch("app.core.security.secrets.randbelow", return_value=999999):
            code = generate_otp_code()
        assert code == "999999"


class TestHashOtpCode:
    def test_is_deterministic_for_same_inputs(self):
        assert hash_otp_code("user@example.com", "123456") == hash_otp_code(
            "user@example.com", "123456"
        )

    def test_differs_when_identifier_differs(self):
        assert hash_otp_code("a@example.com", "123456") != hash_otp_code(
            "b@example.com", "123456"
        )

    def test_differs_when_code_differs(self):
        assert hash_otp_code("user@example.com", "123456") != hash_otp_code(
            "user@example.com", "654321"
        )

    def test_returns_hex_sha256_digest(self):
        digest = hash_otp_code("user@example.com", "123456")
        assert len(digest) == 64
        int(digest, 16)  # raises ValueError if not valid hex


class TestVerifyOtpCode:
    def test_returns_true_for_matching_code(self):
        code_hash = hash_otp_code("user@example.com", "123456")
        assert verify_otp_code("user@example.com", "123456", code_hash) is True

    def test_returns_false_for_wrong_code(self):
        code_hash = hash_otp_code("user@example.com", "123456")
        assert verify_otp_code("user@example.com", "000000", code_hash) is False

    def test_returns_false_for_wrong_identifier(self):
        code_hash = hash_otp_code("user@example.com", "123456")
        assert verify_otp_code("other@example.com", "123456", code_hash) is False

    def test_returns_false_for_garbage_hash(self):
        assert verify_otp_code("user@example.com", "123456", "not-a-real-hash") is False


class TestCreateAccessToken:
    def test_returns_token_and_expiry_seconds(self):
        token, expires_in = create_access_token("user-id-1", "guest")
        assert isinstance(token, str)
        assert expires_in == settings.jwt_expire_minutes * 60

    def test_token_payload_contains_subject_and_type(self):
        token, _ = create_access_token("user-id-1", "admin")
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sub"] == "user-id-1"
        assert payload["type"] == "admin"

    def test_token_expiry_matches_configured_delta(self, monkeypatch):
        monkeypatch.setattr(security.settings, "jwt_expire_minutes", 30)
        before = datetime.now(timezone.utc)
        token, expires_in = create_access_token("user-id-1", "guest")
        after = datetime.now(timezone.utc)

        assert expires_in == 30 * 60
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        # PyJWT truncates the "exp" claim to whole seconds, so allow a
        # one-second tolerance on the lower bound.
        assert before + timedelta(minutes=30) - timedelta(seconds=1) <= exp
        assert exp <= after + timedelta(minutes=30)


class TestDecodeAccessToken:
    def test_decodes_valid_token(self):
        token, _ = create_access_token("user-id-1", "guest")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-id-1"
        assert payload["type"] == "guest"

    def test_raises_on_expired_token(self, monkeypatch):
        monkeypatch.setattr(security.settings, "jwt_expire_minutes", -1)
        token, _ = create_access_token("user-id-1", "guest")
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_raises_on_tampered_signature(self):
        token, _ = create_access_token("user-id-1", "guest")
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(tampered)

    def test_raises_on_wrong_secret(self, monkeypatch):
        token, _ = create_access_token("user-id-1", "guest")
        monkeypatch.setattr(
            security.settings, "jwt_secret_key", "a-completely-different-32-byte-secret"
        )
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_raises_on_malformed_token(self):
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token("not-a-jwt")
