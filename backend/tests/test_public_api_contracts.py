from types import SimpleNamespace
import time

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app import main
from app.db import get_controller_db, get_db
from app.deps import get_context
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

    async def exists(self, _key):
        return 0


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
    application = SimpleNamespace(id="app-1", slug="helpdesk", name="Helpdesk", app_type="low_code", status="deployed", created_by="user-1", public_rate_limit_per_minute=120)
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
    main.app.dependency_overrides[get_controller_db] = override_db
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
        main.app.dependency_overrides.pop(get_controller_db, None)


@pytest.mark.asyncio
async def test_public_invoke_rejects_invalid_input_over_http(monkeypatch):
    tenant, application, version = public_fixture()
    database = FakeDatabase(tenant, application, version)

    async def override_db():
        yield database

    monkeypatch.setattr(main, "Redis", FakeRedis)
    main.app.dependency_overrides[get_controller_db] = override_db
    try:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/public/apps/acme/helpdesk/invoke", json={"input": {}})
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "invalid_input"
    finally:
        main.app.dependency_overrides.pop(get_controller_db, None)


@pytest.mark.asyncio
async def test_public_result_token_is_bound_to_tenant_application_and_run(monkeypatch):
    row = SimpleNamespace(
        id="run-1",
        tenant_id="tenant-1",
        workflow_id="workflow-1",
        status="succeeded",
        output_json={"answer": "async-ok"},
        error=None,
        created_at=None,
        started_at=None,
        finished_at=None,
    )
    application = SimpleNamespace(id="app-1", tenant_id="tenant-1", status="deployed")
    version = SimpleNamespace(version=2, manifest_json={"workflow_id": "workflow-1"})
    database = FakeDatabase(row, application, version)

    async def override_db():
        yield database

    monkeypatch.setattr(main, "Redis", FakeRedis)
    main.app.dependency_overrides[get_controller_db] = override_db
    try:
        token = main.create_public_result_token("workflow", "run-1", "tenant-1", "app-1")
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(f"/api/v1/public/runs/{token}")
            assert response.status_code == 200
            assert response.json()["output"] == {"answer": "async-ok"}

        mismatched_token = main.create_public_result_token("workflow", "run-1", "tenant-1", "other-app")
        database.values = iter([row, application, version])
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(f"/api/v1/public/runs/{mismatched_token}")
            assert response.status_code == 404
    finally:
        main.app.dependency_overrides.pop(get_controller_db, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,error", [("failed", "workflow failed"), ("cancelled", "cancelled by user")])
async def test_public_result_http_contract_hides_output_for_non_success_terminal_states(monkeypatch, status, error):
    row = SimpleNamespace(
        id="run-1",
        tenant_id="tenant-1",
        workflow_id="workflow-1",
        status=status,
        output_json={"sensitive": "must-not-be-returned"},
        error=error,
        created_at=None,
        started_at=None,
        finished_at=None,
    )
    application = SimpleNamespace(id="app-1", tenant_id="tenant-1", status="deployed")
    version = SimpleNamespace(version=2, manifest_json={"workflow_id": "workflow-1"})
    database = FakeDatabase(row, application, version)

    async def override_db():
        yield database

    monkeypatch.setattr(main, "Redis", FakeRedis)
    main.app.dependency_overrides[get_controller_db] = override_db
    try:
        token = main.create_public_result_token("workflow", "run-1", "tenant-1", "app-1")
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(f"/api/v1/public/runs/{token}")

        assert response.status_code == 200
        assert response.json()["status"] == status
        assert response.json()["output"] is None
        assert response.json()["error"] == error
    finally:
        main.app.dependency_overrides.pop(get_controller_db, None)


def test_public_result_token_expiry_is_rejected(monkeypatch):
    token = main.create_public_result_token("workflow", "run-1", "tenant-1", "app-1")
    current_time = time.time()
    monkeypatch.setattr(main.time, "time", lambda: current_time + main.PUBLIC_RESULT_TOKEN_TTL_SECONDS + 1)

    with pytest.raises(main.HTTPException) as exc:
        main.decode_public_result_token(token)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_public_result_token_revocation_closes_the_http_loop(monkeypatch):
    class RevocationRedis(FakeRedis):
        revoked = set()

        async def setex(self, key, _ttl, _value):
            self.revoked.add(key)

        async def exists(self, key):
            return int(key in self.revoked)

    database = FakeDatabase()
    context = SimpleNamespace(tenant_id="tenant-1", user_id="admin-1", role="admin", custom_permissions=())

    async def override_db():
        yield database

    async def override_context():
        return context

    async def no_op_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(main, "Redis", RevocationRedis)
    monkeypatch.setattr(main, "audit", no_op_audit)
    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[get_controller_db] = override_db
    main.app.dependency_overrides[get_context] = override_context
    try:
        token = main.create_public_result_token("workflow", "run-1", "tenant-1", "app-1")
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            revoked = await client.post("/api/public/result-tokens/revoke", json={"result_token": token})
            assert revoked.status_code == 200
            assert revoked.json()["revoked"] is True

            result = await client.get(f"/api/v1/public/runs/{token}")
            assert result.status_code == 410
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        main.app.dependency_overrides.pop(get_controller_db, None)
        main.app.dependency_overrides.pop(get_context, None)


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
async def test_public_callback_delivery_id_is_sent_for_idempotency(monkeypatch):
    captured = {}

    class Response:
        status_code = 202

        def raise_for_status(self):
            return None

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **kwargs):
            captured.update(kwargs)
            return Response()

    monkeypatch.setattr(public_callback.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(public_callback, "validate_public_callback_url", lambda value: value)
    monkeypatch.setattr(public_callback, "get_settings", lambda: SimpleNamespace(publication_signing_secret="secret", app_secret_key="fallback"))
    result = await public_callback.deliver_public_callback("https://hooks.example.com/result", {"run_id": "run-1"}, delivery_id="delivery-1")

    assert result["delivered"] is True
    assert captured["headers"]["X-Enterprise-AI-Delivery-ID"] == "delivery-1"


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


@pytest.mark.asyncio
async def test_public_callback_outbox_requeues_failed_delivery(monkeypatch):
    row = SimpleNamespace(
        id="delivery-1",
        callback_url="https://hooks.example.com/result",
        payload_json={"run_id": "run-1"},
        status="queued",
        attempts=0,
        next_attempt_at=public_callback.utcnow(),
        lease_until=None,
        last_error="",
        response_status=0,
        delivered_at=None,
    )

    class Session:
        def __init__(self):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalar(self, _statement):
            self.calls += 1
            return row

        async def commit(self):
            return None

    sessions = iter([Session(), Session()])
    monkeypatch.setattr(public_callback, "ControllerSessionLocal", lambda: next(sessions))

    async def failed_delivery(_url, _payload, **_kwargs):
        return {"delivered": False, "status_code": 503, "error": "temporary outage"}

    monkeypatch.setattr(public_callback, "deliver_public_callback", failed_delivery)
    result = await public_callback.deliver_public_callback_delivery("delivery-1")

    assert result["delivered"] is False
    assert row.status == "queued"
    assert row.attempts == 1
    assert row.response_status == 503
    assert row.last_error == "temporary outage"


@pytest.mark.asyncio
async def test_public_callback_outbox_reuses_row_after_concurrent_unique_conflict(monkeypatch):
    existing = SimpleNamespace(id="delivery-existing", status="queued")
    delivered = []

    class Session:
        def __init__(self):
            self.values = iter([None, existing])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalar(self, _statement):
            return next(self.values)

        def add(self, _value):
            return None

        async def flush(self):
            raise IntegrityError("insert", {}, RuntimeError("duplicate"))

        async def rollback(self):
            return None

        async def commit(self):
            return None

    async def fake_deliver(delivery_id):
        delivered.append(delivery_id)
        return {"delivered": False}

    monkeypatch.setattr(public_callback, "ControllerSessionLocal", lambda: Session())
    monkeypatch.setattr(public_callback, "validate_public_callback_url", lambda value: value)
    monkeypatch.setattr(public_callback, "deliver_public_callback_delivery", fake_deliver)
    result = await public_callback.enqueue_public_callback_delivery(
        kind="workflow",
        run_id="run-1",
        tenant_id="tenant-1",
        callback_url="https://hooks.example.com/result",
        payload={"run_id": "run-1"},
    )

    assert result == "delivery-existing"
    assert delivered == ["delivery-existing"]
