from types import SimpleNamespace

import httpx
import pytest

from app import main
from app.db import get_admin_db
from app.services import public_callback


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


def test_public_callback_is_allowlisted_and_signed_payload_is_stable(monkeypatch):
    monkeypatch.setattr(
        public_callback,
        "get_settings",
        lambda: SimpleNamespace(app_env="test", allowed_hosts={"hooks.example.com"}, app_secret_key="secret", publication_signing_secret=""),
    )
    assert public_callback.validate_public_callback_url("https://hooks.example.com/result") == "https://hooks.example.com/result"
    with pytest.raises(ValueError, match="允许的出站主机"):
        public_callback.validate_public_callback_url("https://169.254.169.254/latest/meta-data")
    payload = public_callback.public_callback_payload(
        kind="workflow", run_id="run-1", tenant_id="tenant-1", status="succeeded", output={"answer": "ok"}
    )
    assert payload["event"] == "public_application.run.completed"
    assert payload["output"] == {"answer": "ok"}
    assert payload["error"] is None


@pytest.mark.asyncio
async def test_public_result_rate_limit_uses_tenant_and_run_scope(monkeypatch):
    calls = []

    class LimitedRedis(FakeRedis):
        @classmethod
        def from_url(cls, *_args, **_kwargs):
            return cls()

        async def incr(self, key):
            calls.append(key)
            return 1

    monkeypatch.setattr(main, "Redis", LimitedRedis)
    request = SimpleNamespace(client=SimpleNamespace(host="198.51.100.10"))
    await main.enforce_public_result_rate_limit("tenant-1", "run-1", request)
    assert calls and "ai_platform:public_result:tenant-1:" in calls[0]
    assert "198.51.100.10" in calls[0]
