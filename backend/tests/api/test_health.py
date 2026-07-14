import pytest

pytestmark = pytest.mark.anyio


class TestHealth:
    async def test_returns_ok_status(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
