from types import SimpleNamespace

import httpx
import pytest

from app import main
from app.db import get_admin_db


class FakeRedis:
    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return cls()

    async def incr(self, _key):
        return 1

    async def expire(self, *_args):
        return True

    async def aclose(self):
        return None


class FakeDatabase:
    def __init__(self, *values):
        self.values = iter(values)
        self.added = []

    async def scalar(self, _statement):
        return next(self.values)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        return None


def public_fixture():
    tenant = SimpleNamespace(id="tenant-1", slug="acme", is_active=True)
    application = SimpleNamespace(id="app-1", slug="helpdesk", name="Helpdesk", app_type="low_code", status="deployed", created_by="user-1")
    version = SimpleNamespace(
        version=3,
        status="deployed",
        manifest_json={
            "public": True,
            "input_schema": {
                "type": "object",
                "required": ["question"],
                "properties": {"question": {"type": "string", "maxLength": 200}},
            },
            "actions": [{"type": "response", "output": {"answer": "{{input.question}}"}}],
        },
        source_json={},
    )
    return tenant, application, version


@pytest.mark.asyncio
async def test_public_runtime_and_invoke_are_exposed_through_http(monkeypatch):
    tenant, application, version = public_fixture()
    database = FakeDatabase(tenant, application, version, tenant, application, version)

    async def override_db():
        yield database

    monkeypatch.setattr(main, "Redis", FakeRedis)
    main.app.dependency_overrides[get_admin_db] = override_db
    try:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            runtime_response = await client.get("/api/v1/public/apps/acme/helpdesk")
            assert runtime_response.status_code == 200
            assert runtime_response.json()["runtime"]["input_schema"]["required"] == ["question"]
            assert runtime_response.headers["x-content-type-options"] == "nosniff"

            invoke_response = await client.post(
                "/api/v1/public/apps/acme/helpdesk/invoke",
                json={"input": {"question": "reset password"}},
            )
            assert invoke_response.status_code == 200
            assert invoke_response.json()["output"] == {"answer": "reset password"}
    finally:
        main.app.dependency_overrides.pop(get_admin_db, None)


@pytest.mark.asyncio
async def test_public_invoke_rejects_invalid_input_over_http(monkeypatch):
    tenant, application, version = public_fixture()
    database = FakeDatabase(tenant, application, version)

    async def override_db():
        yield database

    monkeypatch.setattr(main, "Redis", FakeRedis)
    main.app.dependency_overrides[get_admin_db] = override_db
    try:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/public/apps/acme/helpdesk/invoke", json={"input": {}})
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "invalid_input"
    finally:
        main.app.dependency_overrides.pop(get_admin_db, None)
