from types import SimpleNamespace

import pytest

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
