"""Runtime for tenant-scoped Agent tools and multi-turn execution."""

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import AgentConfig, AuditEvent, MCPServer, Plugin, Skill
from ..security import decrypt_secret
from .llm import call_routed_chat, stream_routed_chat
from .observability import tool_calls


MAX_TOOL_RESULT_CHARS = 12000


@dataclass(frozen=True)
class BoundTool:
    name: str
    original_name: str
    kind: str
    resource_id: str
    resource_name: str
    endpoint: str = ""
    secret_encrypted: str = ""
    transport: str = ""
    instructions: str = ""
    input_schema: dict[str, Any] | None = None


def _safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_") or "tool"
    return value[:40]


def _tool_schema(tool: BoundTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": f"{tool.resource_name}: {tool.original_name}"[:1000],
            "parameters": tool.input_schema or {"type": "object", "properties": {}, "additionalProperties": True},
        },
    }


def _manifest_tools(manifest: dict[str, Any], fallback_name: str) -> list[dict[str, Any]]:
    entries = manifest.get("tools") or manifest.get("functions") or []
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list) or not entries:
        entries = [{"name": fallback_name, "description": manifest.get("description", "")}]
    result = []
    for item in entries:
        if isinstance(item, str):
            result.append({"name": item, "description": "", "schema": {"type": "object", "properties": {}, "additionalProperties": True}})
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or fallback_name).strip()
        schema = item.get("input_schema") or item.get("inputSchema") or item.get("parameters") or item.get("schema")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}, "additionalProperties": True}
        result.append({"name": name, "description": str(item.get("description") or ""), "schema": schema})
    return result or [{"name": fallback_name, "schema": {"type": "object", "properties": {}, "additionalProperties": True}}]


def _selectors(capabilities: dict[str, Any], key: str) -> list[str]:
    values = capabilities.get(key) or []
    if not isinstance(values, list):
        values = [values]
    selected: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            selected.append(value.strip())
        elif isinstance(value, dict):
            for field in (f"{key[:-1]}_id", "id", "resource_id"):
                item = value.get(field)
                if item:
                    selected.append(str(item))
                    break
    return selected


def _tool_selectors(capabilities: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    plugins = _selectors(capabilities, "plugins")
    mcp_servers = _selectors(capabilities, "mcp_servers")
    skills = _selectors(capabilities, "skills")
    tool_values = capabilities.get("tools") or []
    if not isinstance(tool_values, list):
        tool_values = [tool_values]
    for value in tool_values:
        if isinstance(value, dict):
            kind = str(value.get("kind") or value.get("type") or "").lower()
            resource_id = str(value.get("id") or value.get("resource_id") or value.get("plugin_id") or value.get("mcp_server_id") or value.get("skill_id") or "")
            if resource_id and kind in {"plugin", "plugins"}:
                plugins.append(resource_id)
            elif resource_id and kind in {"mcp", "mcp_server", "mcp_servers"}:
                mcp_servers.append(resource_id)
            elif resource_id and kind in {"skill", "skills"}:
                skills.append(resource_id)
        elif isinstance(value, str):
            if value.startswith("plugin:"):
                plugins.append(value.split(":", 2)[1])
            elif value.startswith("mcp:"):
                mcp_servers.append(value.split(":", 2)[1])
            elif value.startswith("skill:"):
                skills.append(value.split(":", 2)[1])
            elif value.strip():
                # The UI historically stored resource IDs directly in tools.
                # Matching all three tables remains tenant-scoped and selects
                # only the table that actually owns the ID.
                plugins.append(value.strip())
                mcp_servers.append(value.strip())
                skills.append(value.strip())
    return list(dict.fromkeys(plugins)), list(dict.fromkeys(mcp_servers)), list(dict.fromkeys(skills))


async def load_agent_tools(db: AsyncSession, tenant_id: str, config: AgentConfig | None) -> dict[str, BoundTool]:
    """Load only resources explicitly granted in the Agent capability config."""
    capabilities = (config.capabilities_json if config else {}) or {}
    plugin_ids, mcp_ids, skill_ids = _tool_selectors(capabilities)
    tools: dict[str, BoundTool] = {}

    plugins = []
    if plugin_ids:
        plugins = (await db.execute(select(Plugin).where(Plugin.tenant_id == tenant_id, Plugin.id.in_(plugin_ids), Plugin.enabled.is_(True), Plugin.approval_status == "approved"))).scalars().all()
    for plugin in plugins:
        manifest = plugin.manifest_json or {}
        for index, item in enumerate(_manifest_tools(manifest, plugin.name)):
            original_name = item["name"]
            name = f"plugin_{plugin.id[:8]}_{_safe_name(original_name)}"[:64]
            if name in tools:
                name = f"{name}_{index}"[:64]
            tools[name] = BoundTool(name, original_name, "plugin", plugin.id, plugin.name, plugin.endpoint, plugin.secret_encrypted, input_schema=item["schema"])

    mcp_servers = []
    if mcp_ids:
        mcp_servers = (await db.execute(select(MCPServer).where(MCPServer.tenant_id == tenant_id, MCPServer.id.in_(mcp_ids), MCPServer.enabled.is_(True)))).scalars().all()
    for server in mcp_servers:
        manifest = server.manifest_json or {}
        for index, item in enumerate(_manifest_tools(manifest, server.name)):
            original_name = item["name"]
            name = f"mcp_{server.id[:8]}_{_safe_name(original_name)}"[:64]
            if name in tools:
                name = f"{name}_{index}"[:64]
            tools[name] = BoundTool(name, original_name, "mcp", server.id, server.name, server.endpoint, server.secret_encrypted, server.transport, input_schema=item["schema"])

    skill_rows = []
    if skill_ids:
        skill_rows = (await db.execute(select(Skill).where(Skill.tenant_id == tenant_id, Skill.id.in_(skill_ids), Skill.enabled.is_(True)))).scalars().all()
    for skill in skill_rows:
        name = f"skill_{skill.id[:8]}_{_safe_name(skill.name)}"[:64]
        tools[name] = BoundTool(name, skill.name, "skill", skill.id, skill.name, instructions=skill.instructions, input_schema={"type": "object", "properties": {"input": {"type": "object"}}, "additionalProperties": True})
    return tools


def _json_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {"value": value}
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


def _check_allowed_http_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.hostname.lower() not in get_settings().allowed_hosts:
        raise RuntimeError("工具地址不在租户允许的主机列表中")


async def execute_bound_tool(tool: BoundTool, arguments: dict[str, Any], *, tenant_id: str) -> Any:
    if tool.kind == "skill":
        return {"skill": tool.resource_name, "instructions": tool.instructions, "input": arguments}
    _check_allowed_http_endpoint(tool.endpoint)
    headers = {"X-AI-Tenant-ID": tenant_id}
    secret = decrypt_secret(tool.secret_encrypted)
    if secret:
        headers["X-AI-Plugin-Secret"] = secret if tool.kind == "plugin" else ""
        if tool.kind == "mcp":
            headers["Authorization"] = f"Bearer {secret}"
            headers.pop("X-AI-Plugin-Secret", None)
    timeout = httpx.Timeout(30.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if tool.kind == "plugin":
            response = await client.post(tool.endpoint, json={"tool": tool.original_name, "arguments": arguments}, headers=headers)
        else:
            if tool.transport == "stdio":
                raise RuntimeError("MCP stdio 服务需要由受控 sidecar 执行")
            response = await client.post(
                tool.endpoint,
                json={"jsonrpc": "2.0", "id": tool.name, "method": "tools/call", "params": {"name": tool.original_name, "arguments": arguments}},
                headers=headers,
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            payload = {"text": response.text}
    if tool.kind == "mcp" and isinstance(payload, dict):
        if payload.get("error"):
            raise RuntimeError(str(payload["error"])[:1000])
        return payload.get("result", payload)
    return payload


def _compact_result(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text[:MAX_TOOL_RESULT_CHARS]


def _merge_usage(total: dict[str, int], usage: dict[str, Any] | None) -> None:
    usage = usage or {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if usage.get(key) is not None:
            total[key] = total.get(key, 0) + int(usage[key] or 0)
    if "total_tokens" not in total:
        total["total_tokens"] = total.get("prompt_tokens", 0) + total.get("completion_tokens", 0)


def _normal_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, call in enumerate(calls):
        function = call.get("function") or {}
        name = str(function.get("name") or call.get("name") or "")
        if not name:
            continue
        result.append({"id": str(call.get("id") or f"tool_call_{index}"), "type": "function", "function": {"name": name, "arguments": function.get("arguments") or "{}"}})
    return result


async def _execute_tool_calls(db: AsyncSession, tools: dict[str, BoundTool], calls: list[dict[str, Any]], *, tenant_id: str, actor_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    messages: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    for call in _normal_tool_calls(calls):
        name = call["function"]["name"]
        bound = tools.get(name)
        status = "success"
        try:
            if not bound:
                raise RuntimeError("工具未在 Agent 能力白名单中")
            output = await execute_bound_tool(bound, _json_arguments(call["function"]["arguments"]), tenant_id=tenant_id)
            content = _compact_result(output)
            tool_calls.labels(tenant_id, bound.kind, "success").inc()
            resource_id = bound.resource_id
            kind = bound.kind
        except Exception as exc:
            status = "error"
            content = _compact_result({"error": str(exc)[:1000]})
            tool_calls.labels(tenant_id, bound.kind if bound else "unknown", "error").inc()
            resource_id = bound.resource_id if bound else ""
            kind = bound.kind if bound else "unknown"
        trace.append({"id": call["id"], "name": name, "kind": kind, "status": status})
        db.add(AuditEvent(tenant_id=tenant_id, actor_id=actor_id, action="agent.tool_call", resource_type=kind, resource_id=resource_id, detail_json={"tool": name, "status": status}))
        messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": content})
    if trace:
        await db.commit()
    return messages, trace


async def run_agent_loop(db: AsyncSession, messages: list[dict[str, Any]], *, tenant_id: str, actor_id: str | None, config: AgentConfig | None, preferred_provider_id: str | None = None, max_rounds: int = 3) -> dict[str, Any]:
    bound_tools = await load_agent_tools(db, tenant_id, config)
    tool_schemas = [_tool_schema(item) for item in bound_tools.values()]
    current = list(messages)
    usage: dict[str, int] = {}
    trace: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    for round_index in range(max(1, min(max_rounds, 3))):
        result = await call_routed_chat(db, current, tenant_id=tenant_id, preferred_provider_id=preferred_provider_id, tools=tool_schemas or None)
        _merge_usage(usage, result.get("usage"))
        calls = _normal_tool_calls(result.get("tool_calls") or [])
        if not calls:
            return {**result, "usage": usage, "tool_trace": trace, "tool_rounds": round_index}
        assistant = {"role": "assistant", "content": result.get("text") or None, "tool_calls": calls}
        current.append(assistant)
        tool_messages, round_trace = await _execute_tool_calls(db, bound_tools, calls, tenant_id=tenant_id, actor_id=actor_id)
        current.extend(tool_messages)
        trace.extend(round_trace)
    return {**result, "text": result.get("text") or "工具调用已达到最大轮次，请稍后重试。", "usage": usage, "tool_trace": trace, "tool_rounds": max_rounds}


async def stream_agent_loop(db: AsyncSession, messages: list[dict[str, Any]], *, tenant_id: str, actor_id: str | None, config: AgentConfig | None, preferred_provider_id: str | None = None, max_rounds: int = 3):
    """Yield text/tool/final events while preserving the same tool loop semantics."""
    bound_tools = await load_agent_tools(db, tenant_id, config)
    tool_schemas = [_tool_schema(item) for item in bound_tools.values()]
    current = list(messages)
    usage: dict[str, int] = {}
    trace: list[dict[str, Any]] = []
    final_text = ""
    provider_id = model = None
    for round_index in range(max(1, min(max_rounds, 3))):
        round_text = ""
        deltas: dict[int, dict[str, Any]] = {}
        async for event in stream_routed_chat(db, current, tenant_id=tenant_id, preferred_provider_id=preferred_provider_id, tools=tool_schemas or None):
            provider_id = event.get("provider_id") or provider_id
            model = event.get("model") or model
            if event["type"] == "text":
                round_text += event["text"]
                final_text += event["text"]
                yield {"type": "token", "text": event["text"]}
            elif event["type"] == "usage":
                _merge_usage(usage, event.get("usage"))
            elif event["type"] == "tool_call_delta":
                for delta in event.get("tool_calls") or []:
                    index = int(delta.get("index", 0))
                    target = deltas.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    target["id"] += str(delta.get("id") or "")
                    fn = delta.get("function") or {}
                    target["function"]["name"] += str(fn.get("name") or "")
                    target["function"]["arguments"] += str(fn.get("arguments") or "")
        calls = _normal_tool_calls(list(deltas.values()))
        if not calls:
            yield {"type": "final", "text": final_text, "usage": usage, "provider_id": provider_id, "model": model, "tool_trace": trace, "tool_rounds": round_index}
            return
        current.append({"role": "assistant", "content": round_text or None, "tool_calls": calls})
        for call in calls:
            yield {"type": "tool_call", "name": call["function"]["name"], "id": call["id"]}
        tool_messages, round_trace = await _execute_tool_calls(db, bound_tools, calls, tenant_id=tenant_id, actor_id=actor_id)
        current.extend(tool_messages)
        trace.extend(round_trace)
        for item in round_trace:
            yield {"type": "tool_result", "name": item["name"], "status": item["status"]}
    yield {"type": "final", "text": final_text or "工具调用已达到最大轮次，请稍后重试。", "usage": usage, "provider_id": provider_id, "model": model, "tool_trace": trace, "tool_rounds": max_rounds}
