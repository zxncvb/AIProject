from types import SimpleNamespace

import httpx
import pytest

from app import main
from app.db import get_db
from app.deps import get_context


class AgentDatabase:
    def __init__(self, agent, provider):
        self.values = iter((agent, provider))
        self.added = []
        self.commits = 0

    async def scalar(self, _statement):
        return next(self.values)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        for value in self.added:
            if hasattr(value, "id") and getattr(value, "id", None) is None:
                value.id = "generated-id"


class FakeRateRedis:
    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return cls()

    async def incr(self, _key):
        return 1

    async def expire(self, *_args):
        return True

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_agent_stream_endpoint_emits_tool_trace_and_persists_completion(monkeypatch):
    agent = SimpleNamespace(
        id="agent-1",
        tenant_id="tenant-1",
        project_id="project-1",
        provider_id="provider-1",
        enabled=True,
        knowledge_base_id=None,
        system_prompt="You are helpful.",
    )
    provider = SimpleNamespace(id="provider-1", enabled=True)
    database = AgentDatabase(agent, provider)
    context = SimpleNamespace(
        user_id="user-1",
        tenant_id="tenant-1",
        role="operator",
        custom_permissions=("api:agent:invoke",),
    )
    config = SimpleNamespace(agent_type="chat", memory_json={"enabled": False})

    async def override_db():
        yield database

    async def override_context():
        return context

    async def no_op(*_args, **_kwargs):
        return None

    async def fake_tenant_policy(*_args, **_kwargs):
        return SimpleNamespace(safety_json={})

    async def fake_agent_config(*_args, **_kwargs):
        return config

    async def fake_stream(*_args, **_kwargs):
        yield {"type": "token", "text": "Hello"}
        yield {"type": "tool_call", "id": "call-1", "name": "plugin_lookup"}
        yield {"type": "tool_result", "name": "plugin_lookup", "status": "success"}
        yield {
            "type": "final",
            "text": "Hello from tool",
            "usage": {"total_tokens": 7},
            "provider_id": "provider-1",
            "model": "test-model",
            "tool_trace": [{"id": "call-1", "name": "plugin_lookup", "status": "success"}],
            "tool_rounds": 1,
        }

    monkeypatch.setattr(main, "enforce_monthly_budget", no_op)
    monkeypatch.setattr(main, "require_project_access", no_op)
    monkeypatch.setattr(main, "tenant_policy", fake_tenant_policy)
    monkeypatch.setattr(main, "inspect_text", lambda text, _policy: {"blocked": False, "text": text, "reasons": []})
    monkeypatch.setattr(main, "get_or_create_agent_config", fake_agent_config)
    monkeypatch.setattr(main, "load_agent_memories", no_op)
    monkeypatch.setattr(main, "stream_agent_loop", fake_stream)
    monkeypatch.setattr(main, "audit", no_op)
    monkeypatch.setattr(main, "Redis", FakeRateRedis)

    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[get_context] = override_context
    try:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/agents/agent-1/chat/stream",
                json={"message": "find my order", "cost_center": "agent"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "event: token" in response.text
        assert "event: tool_call" in response.text
        assert "event: tool_result" in response.text
        assert "event: done" in response.text
        assert '"text": "Hello from tool"' in response.text
        assert any(getattr(item, "event_type", "") == "message" for item in database.added)
        assert any(getattr(item, "tokens", None) == 7 for item in database.added)
        assert database.commits == 1
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        main.app.dependency_overrides.pop(get_context, None)
