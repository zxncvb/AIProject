import httpx
import pytest

from app import main


@pytest.mark.asyncio
async def test_metrics_response_has_security_headers_and_request_id():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/metrics", headers={"X-Request-ID": "api-contract-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "api-contract-1"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")


def test_production_api_documentation_is_not_registered():
    assert main.app.openapi_url is None
    assert main.app.docs_url is None
    assert main.app.redoc_url is None
