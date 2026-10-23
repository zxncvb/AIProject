from types import SimpleNamespace

import pytest

from app.main import apply_database_column_policy, public_application_runtime, public_runtime_manifest
from app.services.llm import rank_providers
from app.services.sandbox import build_job_manifest
from app.services.workflow import enqueue_job


def test_sandbox_requires_real_command_and_hardens_pod():
    with pytest.raises(ValueError, match="source.command"):
        build_job_manifest("run-1", "python", {}, 60, 500, 512)
    manifest = build_job_manifest("run-1", "python", {"command": ["python", "-c", "print('ok')"], "input": {"question": "你好"}}, 60, 500, 512)
    pod = manifest["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert any(item["name"] == "AI_APP_INPUT" and "你好" in item["value"] for item in container["env"])


def test_database_column_policy_hides_and_masks_columns():
    columns, rows = apply_database_column_policy(
        ["name", "email", "api_token", "salary"],
        [{"name": "张三", "email": "person@example.com", "api_token": "very-secret", "salary": 8000}],
        {"column_policies": {"salary": {"allowed_roles": ["admin"]}}},
        "viewer",
    )
    assert columns == ["name", "email", "api_token"]
    assert rows[0]["name"] == "张三"
    assert rows[0]["email"].startswith("***")
    assert rows[0]["api_token"].startswith("***")
    assert "salary" not in rows[0]


def test_model_router_prioritizes_healthy_provider():
    providers = [
        SimpleNamespace(id="a", config_json={"priority": 1}),
        SimpleNamespace(id="b", config_json={"priority": 10}),
    ]
    health = {"a": SimpleNamespace(ok=False, latency_ms=10), "b": SimpleNamespace(ok=True, latency_ms=100)}
    assert [item.id for item in rank_providers(providers, health)] == ["b", "a"]


@pytest.mark.asyncio
async def test_public_application_details_do_not_expose_source_or_keys():
    class Database:
        def __init__(self):
            self.values = iter([
                SimpleNamespace(id="tenant-1"),
                SimpleNamespace(id="app-1", name="测试应用", slug="test", app_type="full_code"),
                SimpleNamespace(version=1, manifest_json={"public": True, "runtime": "python", "app_key": "secret-value"}, source_json={"command": ["python", "run.py"]}),
            ])

        async def scalar(self, _query):
            return next(self.values)

    result = await public_application_runtime("tenant", "test", Database())
    assert result["authentication_required"] is True
    assert "runtime" not in result
    assert "source" not in result
    assert "secret-value" not in str(result)


def test_public_runtime_manifest_strips_sensitive_ui_metadata():
    result = public_runtime_manifest({
        "ui": {"title": "工单", "secret": "do-not-return", "nested": {"api_key": "also-private", "label": "保留"}},
        "input_schema": {"properties": {"password": {"type": "string"}}},
        "actions": [{"type": "response", "output": {"token": "private", "value": "ok"}}],
    })
    rendered = str(result)
    assert "do-not-return" not in rendered
    assert "also-private" not in rendered
    assert "private" not in rendered
    assert result["ui"]["nested"]["label"] == "保留"
    assert "password" in result["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_reliable_queue_writes_typed_stream_message():
    class FakeRedis:
        def __init__(self):
            self.call = None

        async def xadd(self, stream, fields, **options):
            self.call = (stream, fields, options)
            return "1-0"

    redis = FakeRedis()
    message_id = await enqueue_job("knowledge_index", "document-1", redis)
    assert message_id == "1-0"
    assert redis.call[1]["kind"] == "knowledge_index"
    assert redis.call[1]["resource_id"] == "document-1"
    assert redis.call[2]["maxlen"] == 100000


@pytest.mark.asyncio
async def test_reliable_queue_rejects_unknown_job_kind():
    with pytest.raises(ValueError, match="unsupported job kind"):
        await enqueue_job("unknown", "resource-1", SimpleNamespace())
