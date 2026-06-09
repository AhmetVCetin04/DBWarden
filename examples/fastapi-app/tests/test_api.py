import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


# These tests verify the FastAPI routes work correctly without
# a live database (they test the endpoint wiring, not the DB).
# In production you'd test against an actual database using
# dbwarden's sandbox or a testcontainers-backed instance.

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health_root():
    """Verify /health/ endpoint returns status JSON."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.anyio
async def test_db_status():
    """Verify /db/status endpoint returns migration state."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/db/status")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_root():
    """Verify root endpoint returns welcome message."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
