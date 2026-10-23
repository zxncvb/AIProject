from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import MCPServer
from app.services import agent_runtime


def test_agent_tool_manifest_is_normalized_to_openai_schema():
    tools = agent_runtime._manifest_tools(
        {"tools": [{"name": "lookup_order", "description": "Find an order", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}}}]},
        "orders",
    )
    assert tools[0]["name"] == "lookup_order"
    assert tools[0]["schema"]["properties"]["id"]["type"] == "string"


def test_capability_selectors_support_explicit_resource_prefixes():
    plugins, mcp_servers, skills = agent_runtime._tool_selectors({"tools": ["plugin:p1", "mcp:m1", "skill:s1"]})
    assert plugins == ["p1"]
    assert mcp_servers == ["m1"]
    assert skills == ["s1"]


def test_tool_calls_are_normalized_and_missing_ids_are_stable():
    calls = agent_runtime._normal_tool_calls([{"function": {"name": "lookup", "arguments": "{}"}}])
    assert calls == [{"id": "tool_call_0", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]


def test_tool_retry_policy_only_retries_transient_statuses():
    assert agent_runtime._retryable_tool_status(429)
    assert agent_runtime._retryable_tool_status(503)
    assert not agent_runtime._retryable_tool_status(400)
    assert not agent_runtime._retryable_tool_status(404)


def test_tool_rate_limit_key_is_scoped_to_tenant_actor_and_tool():
    assert agent_runtime.tool_rate_limit_key("tenant-a", "user-1", "lookup") != agent_runtime.tool_rate_limit_key("tenant-b", "user-1", "lookup")
    assert agent_runtime.tool_rate_limit_key("tenant-a", "user-1", "lookup") != agent_runtime.tool_rate_limit_key("tenant-a", "user-2", "lookup")


def test_agent_type_contract_rejects_legacy_execution_labels():
    assert agent_runtime.validate_agent_type("chat") == "chat"
    assert agent_runtime.validate_agent_type("chatflow") == "chatflow"
    with pytest.raises(ValueError, match="workflow"):
        agent_runtime.validate_agent_type("workflow")
    with pytest.raises(ValueError, match="a2a"):
        agent_runtime.validate_agent_type("a2a")


def test_mcp_resource_model_exposes_approval_contract():
    assert hasattr(agent_runtime.MCPServer, "approval_status")
    assert hasattr(agent_runtime.MCPServer, "approved_by")
    assert hasattr(agent_runtime.MCPServer, "approved_at")


@pytest.mark.asyncio
async def test_agent_tools_only_load_approved_enabled_mcp_servers():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(MCPServer.__table__.create)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            db.add_all([
                MCPServer(
                    id="approved-1",
                    tenant_id="tenant-1",
                    name="approved",
                    endpoint="http://localhost:1",
                    transport="streamable_http",
                    manifest_json={"tools": ["lookup"]},
                    approval_status="approved",
                    enabled=True,
                    created_by="user-1",
                ),
                MCPServer(
                    id="pending-1",
                    tenant_id="tenant-1",
                    name="pending",
                    endpoint="http://localhost:2",
                    transport="streamable_http",
                    manifest_json={"tools": ["must_not_load"]},
                    approval_status="pending",
                    enabled=True,
                    created_by="user-1",
                ),
                MCPServer(
                    id="disabled-1",
                    tenant_id="tenant-1",
                    name="disabled",
                    endpoint="http://localhost:3",
                    transport="streamable_http",
                    manifest_json={"tools": ["must_not_load"]},
                    approval_status="approved",
                    enabled=False,
                    created_by="user-1",
                ),
            ])
            await db.commit()
            tools = await agent_runtime.load_agent_tools(
                db,
                "tenant-1",
                SimpleNamespace(capabilities_json={"mcp_servers": ["approved-1", "pending-1", "disabled-1"]}),
            )
        assert [(tool.kind, tool.original_name) for tool in tools.values()] == [("mcp", "lookup")]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_agent_loop_executes_tool_then_sends_tool_result_back(monkeypatch):
    bound = agent_runtime.BoundTool("plugin_p1_lookup", "lookup", "plugin", "p1", "Orders")
    responses = iter([
        {"text": "", "tool_calls": [{"id": "call-1", "function": {"name": "plugin_p1_lookup", "arguments": "{\"id\": \"42\"}"}}], "usage": {"total_tokens": 2}, "provider_id": "provider-1", "model": "model-1"},
        {"text": "订单已找到", "tool_calls": [], "usage": {"total_tokens": 3}, "provider_id": "provider-1", "model": "model-1"},
    ])
    sent_messages = []

    async def fake_load(*_args, **_kwargs):
        return {bound.name: bound}

    async def fake_call(_db, messages, **_kwargs):
        sent_messages.append(messages)
        return next(responses)

    async def fake_execute(*_args, **_kwargs):
        return ([{"role": "tool", "tool_call_id": "call-1", "name": bound.name, "content": "{\"status\": \"ok\"}"}], [{"id": "call-1", "name": bound.name, "kind": "plugin", "status": "success"}])

    monkeypatch.setattr(agent_runtime, "load_agent_tools", fake_load)
    monkeypatch.setattr(agent_runtime, "call_routed_chat", fake_call)
    monkeypatch.setattr(agent_runtime, "_execute_tool_calls", fake_execute)

    result = await agent_runtime.run_agent_loop(SimpleNamespace(), [{"role": "user", "content": "查订单"}], tenant_id="tenant-1", actor_id="user-1", config=None)
    assert result["text"] == "订单已找到"
    assert result["tool_rounds"] == 1
    assert result["tool_trace"][0]["status"] == "success"
    assert sent_messages[1][-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_stream_agent_loop_forwards_usage_for_disconnect_accounting(monkeypatch):
    async def fake_load(*_args, **_kwargs):
        return {}

    async def fake_stream(*_args, **_kwargs):
        yield {"type": "usage", "usage": {"total_tokens": 7}}
        yield {"type": "text", "text": "部分答案"}
        yield {"type": "done"}

    monkeypatch.setattr(agent_runtime, "load_agent_tools", fake_load)
    monkeypatch.setattr(agent_runtime, "stream_routed_chat", fake_stream)
    events = [item async for item in agent_runtime.stream_agent_loop(SimpleNamespace(), [{"role": "user", "content": "问题"}], tenant_id="tenant-1", actor_id="user-1", config=None)]
    assert {item["type"] for item in events} == {"usage", "token", "final"}
    assert next(item for item in events if item["type"] == "usage")["usage"]["total_tokens"] == 7


@pytest.mark.asyncio
async def test_stream_agent_loop_reassembles_tool_call_deltas_and_emits_trace(monkeypatch):
    bound = agent_runtime.BoundTool("plugin_p1_lookup", "lookup", "plugin", "p1", "Orders")
    streams = iter([
        [
            {"type": "tool_call_delta", "tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "plugin_p1_", "arguments": '{"id":'}}]},
            {"type": "tool_call_delta", "tool_calls": [{"index": 0, "function": {"name": "lookup", "arguments": ' "42"}'}}]},
            {"type": "done"},
        ],
        [{"type": "text", "text": "订单已找到"}, {"type": "usage", "usage": {"total_tokens": 4}}, {"type": "done"}],
    ])

    async def fake_load(*_args, **_kwargs):
        return {bound.name: bound}

    async def fake_stream(*_args, **_kwargs):
        for item in next(streams):
            yield item

    async def fake_execute(*_args, **_kwargs):
        return ([{"role": "tool", "tool_call_id": "call-1", "name": bound.name, "content": "{\"status\":\"ok\"}"}], [{"id": "call-1", "name": bound.name, "kind": "plugin", "status": "success"}])

    monkeypatch.setattr(agent_runtime, "load_agent_tools", fake_load)
    monkeypatch.setattr(agent_runtime, "stream_routed_chat", fake_stream)
    monkeypatch.setattr(agent_runtime, "_execute_tool_calls", fake_execute)
    events = [item async for item in agent_runtime.stream_agent_loop(SimpleNamespace(), [{"role": "user", "content": "查询"}], tenant_id="tenant-1", actor_id="user-1", config=None)]
    assert next(item for item in events if item["type"] == "tool_call")["name"] == bound.name
    assert next(item for item in events if item["type"] == "tool_result")["status"] == "success"
    final = next(item for item in events if item["type"] == "final")
    assert final["text"] == "订单已找到"
    assert final["tool_trace"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_stream_agent_loop_does_not_concatenate_repeated_tool_call_ids(monkeypatch):
    bound = agent_runtime.BoundTool("plugin_p1_lookup", "lookup", "plugin", "p1", "Orders")
    streams = iter([
        [
            {"type": "tool_call_delta", "tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "plugin_p1_", "arguments": "{"}}]},
            {"type": "tool_call_delta", "tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "lookup", "arguments": "}"}}]},
            {"type": "done"},
        ],
        [{"type": "text", "text": "done"}, {"type": "done"}],
    ])

    async def fake_load(*_args, **_kwargs):
        return {bound.name: bound}

    async def fake_stream(*_args, **_kwargs):
        for item in next(streams):
            yield item

    executed = []

    async def fake_execute(_db, _tools, calls, **_kwargs):
        executed.extend(calls)
        return ([{"role": "tool", "tool_call_id": calls[0]["id"], "name": bound.name, "content": "ok"}], [{"id": calls[0]["id"], "name": bound.name, "kind": "plugin", "status": "success"}])

    monkeypatch.setattr(agent_runtime, "load_agent_tools", fake_load)
    monkeypatch.setattr(agent_runtime, "stream_routed_chat", fake_stream)
    monkeypatch.setattr(agent_runtime, "_execute_tool_calls", fake_execute)

    events = [item async for item in agent_runtime.stream_agent_loop(SimpleNamespace(), [{"role": "user", "content": "lookup"}], tenant_id="tenant-1", actor_id="user-1", config=None)]
    assert executed[0]["id"] == "call-1"
    assert next(item for item in events if item["type"] == "tool_call")["id"] == "call-1"
