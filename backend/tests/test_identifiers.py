import pytest

from app.core.identifiers import classify_identifier, normalize_identifier


class TestClassifyIdentifier:
    @pytest.mark.parametrize(
        "identifier",
        [
            "user@example.com",
            "USER@EXAMPLE.COM",
            "first.last+tag@sub.example.co",
            "  user@example.com  ",
        ],
    )
    def test_classifies_valid_emails(self, identifier):
        assert classify_identifier(identifier) == "email"

    @pytest.mark.parametrize(
        "identifier",
        [
            "user@",
            "user@example",
            "@example.com",
            "us er@example.com",
            "user@ example.com",
        ],
    )
    def test_rejects_invalid_emails(self, identifier):
        with pytest.raises(ValueError, match="Invalid email address"):
            classify_identifier(identifier)

    @pytest.mark.parametrize(
        "identifier",
        [
            "1234567",
            "+1 234 567 8901",
            "(555) 123-4567",
            "555-123-4567",
        ],
    )
    def test_classifies_valid_phone_numbers(self, identifier):
        assert classify_identifier(identifier) == "phone"

    @pytest.mark.parametrize(
        "identifier",
        [
            "12345",  # too short
            "1" * 21,  # too long
            "abcdefg",
            "555-abc-defg",
        ],
    )
    def test_rejects_invalid_phone_numbers(self, identifier):
        with pytest.raises(ValueError, match="Invalid phone number"):
            classify_identifier(identifier)

    def test_strips_surrounding_whitespace_before_classifying(self):
        assert classify_identifier("   +15551234567   ") == "phone"


class TestNormalizeIdentifier:
    def test_normalizes_email_to_lowercase_and_strips(self):
        assert normalize_identifier("  USER@Example.COM  ", "email") == "user@example.com"

    def test_normalizes_phone_by_removing_formatting_characters(self):
        assert normalize_identifier("+1 (555) 123-4567", "phone") == "+15551234567"

    def test_normalizes_phone_preserves_leading_plus(self):
        assert normalize_identifier("+1 (555) 123-4567", "phone") == "+15551234567"

    def test_normalizes_phone_strips_surrounding_whitespace(self):
        assert normalize_identifier("  +15551234567  ", "phone") == "+15551234567"

    def test_assumes_default_region_for_numbers_without_country_code(self):
        assert normalize_identifier("078 123 45 67", "phone") == "+41781234567"

    def test_different_formats_of_the_same_number_normalize_identically(self):
        """A returning guest who types their number differently than before
        (spacing, missing country code, ...) must still be matched to their
        existing account at login."""
        variants = ["078 123 45 67", "0781234567", "+41781234567", "0041 78 123 45 67"]
        normalized = {normalize_identifier(v, "phone") for v in variants}
        assert normalized == {"+41781234567"}
