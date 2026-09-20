import pytest

from app.core.config import settings

pytestmark = pytest.mark.anyio


class TestHealth:
    async def test_returns_ok_status(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_reports_which_environment_answered(self, client):
        """preprod and prod share a host behind one edge proxy, so a misrouted
        request still returns a healthy-looking response. This field is what
        makes that detectable."""
        response = await client.get("/health")
        assert response.json()["environment"] == settings.environment
