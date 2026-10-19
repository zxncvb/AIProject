import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import func, select

from ..config import get_settings
from ..db import AdminSessionLocal
from ..models import Agent, ComputeUsage, EvaluationJob, GpuLease, ModelProvider, Plugin, SandboxRun, Skill, TenantPolicy, Workflow, WorkflowRun, WorkflowSchedule, WorkflowVersion
from .knowledge import search_chunks
from .llm import call_chat
from .observability import new_trace_id, run_failures, runs_total, tool_calls
from .safety import inspect_text
from .sandbox import build_job_manifest


QUEUE = "ai_platform:workflow_runs"
INDEX_QUEUE = "ai_platform:knowledge_index"
EVALUATION_QUEUE = "ai_platform:evaluation_jobs"
SANDBOX_QUEUE = "ai_platform:sandbox_runs"


def now() -> datetime:
    return datetime.now(timezone.utc)


def resolve(value: Any, context: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    exact = re.fullmatch(r"\{\{\s*([^}]+?)\s*\}\}", value)
    if exact:
        return _lookup(exact.group(1), context)
    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", lambda m: str(_lookup(m.group(1), context)), value)


def _lookup(path: str, context: dict[str, Any]) -> Any:
    current: Any = context
    for part in path.strip().split("."):
        if isinstance(current, dict):
            current = current.get(part, "")
        else:
            return ""
    return current


def ordered_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = {str(n["id"]): n for n in graph.get("nodes", []) if n.get("id")}
    edges = graph.get("edges", [])
    outgoing: dict[str, list[str]] = {key: [] for key in nodes}
    incoming: dict[str, int] = {key: 0 for key in nodes}
    for edge in edges:
        source, target = str(edge.get("source", "")), str(edge.get("target", ""))
        if source in nodes and target in nodes:
            outgoing[source].append(target)
            incoming[target] += 1
    ready = [key for key, degree in incoming.items() if degree == 0]
    ordered: list[str] = []
    while ready:
        key = ready.pop(0)
        ordered.append(key)
        for target in outgoing[key]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if len(ordered) != len(nodes):
        raise ValueError("工作流图存在环或孤立节点无法排序")
    return [nodes[key] for key in ordered]


async def enqueue_run(run_id: str) -> None:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await redis.rpush(QUEUE, run_id)
    except Exception:
        asyncio.create_task(execute_run(run_id))
    finally:
        await redis.aclose()


async def enqueue_index(document_id: str) -> None:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await redis.rpush(INDEX_QUEUE, document_id)
    finally:
        await redis.aclose()


async def execute_index(document_id: str) -> None:
    from ..models import Document, DocumentChunk
    from .vector import upsert_chunks

    async with AdminSessionLocal() as db:
        document = await db.scalar(select(Document).where(Document.id == document_id))
        if not document:
            return
        provider = await db.scalar(select(ModelProvider).where(ModelProvider.tenant_id == document.tenant_id, ModelProvider.enabled.is_(True)).order_by(ModelProvider.created_at))
        if not provider:
            document.status = "ready"
            await db.commit()
            return
        chunks = (await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == document.id).order_by(DocumentChunk.chunk_index))).scalars().all()
        try:
            await upsert_chunks(provider, document.tenant_id, document.kb_id, [{"id": chunk.id, "document_id": chunk.document_id, "content": chunk.content} for chunk in chunks])
            document.status = "ready"
        except Exception as exc:
            document.status = "index_failed"
            logging.getLogger("enterprise_ai_platform").exception("knowledge index failed: %s", exc)
        await db.commit()


async def _provider(db, tenant_id: str, node_config: dict[str, Any]) -> ModelProvider:
    provider_id = node_config.get("provider_id")
    stmt = select(ModelProvider).where(ModelProvider.tenant_id == tenant_id, ModelProvider.enabled.is_(True))
    if provider_id:
        stmt = stmt.where(ModelProvider.id == provider_id)
    result = await db.execute(stmt)
    provider = result.scalars().first()
    if not provider:
        raise RuntimeError("未找到可用模型提供商，请先在模型管理中配置")
    return provider


async def execute_run(run_id: str) -> None:
    async with AdminSessionLocal() as db:
        result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run = result.scalar_one_or_none()
        if not run or run.status not in {"queued", "running"}:
            return
        version = await db.scalar(
            select(WorkflowVersion).where(WorkflowVersion.workflow_id == run.workflow_id, WorkflowVersion.version == run.workflow_version)
        )
        workflow = await db.scalar(select(Workflow).where(Workflow.id == run.workflow_id))
        if not version or not workflow:
            run.status, run.error, run.finished_at = "failed", "工作流版本不存在", now()
            await db.commit()
            return
        run.status = "running"
        run.started_at = run.started_at or now()
        run.trace_id = run.trace_id or new_trace_id()
        await db.commit()
        started_clock = time.perf_counter()
        try:
            completed, state = await execute_graph(db, run, version)
            last_node_id = state.get("last_node_id")
            run.output_json = completed.get(last_node_id, completed) if last_node_id else completed
            run.status, run.finished_at = "succeeded", now()
            run.state_json = state
            db.add(ComputeUsage(tenant_id=run.tenant_id, run_id=run.id, cost_center=run.cost_center or "unassigned", cpu_milliseconds=int((time.perf_counter() - started_clock) * 1000), tokens=sum(int((value or {}).get("usage", {}).get("total_tokens", 0)) for value in completed.values() if isinstance(value, dict))))
            await db.commit()
            runs_total.labels(run.tenant_id, "succeeded").inc()
        except Exception as exc:
            run.status, run.error, run.finished_at = "failed", str(exc), now()
            db.add(ComputeUsage(tenant_id=run.tenant_id, run_id=run.id, cost_center=run.cost_center or "unassigned", cpu_milliseconds=int((time.perf_counter() - started_clock) * 1000)))
            await db.commit()
            run_failures.labels(run.tenant_id).inc()
            runs_total.labels(run.tenant_id, "failed").inc()


async def execute_evaluation(job_id: str) -> None:
    async with AdminSessionLocal() as db:
        job = await db.scalar(select(EvaluationJob).where(EvaluationJob.id == job_id))
        if not job or job.status not in {"queued", "running"}:
            return
        agent = await db.scalar(select(Agent).where(Agent.id == job.agent_id, Agent.tenant_id == job.tenant_id, Agent.enabled.is_(True)))
        provider_stmt = select(ModelProvider).where(ModelProvider.tenant_id == job.tenant_id, ModelProvider.enabled.is_(True))
        if agent and agent.provider_id:
            provider_stmt = provider_stmt.where(ModelProvider.id == agent.provider_id)
        provider = (await db.execute(provider_stmt)).scalars().first()
        if not agent or not provider:
            job.status, job.error, job.finished_at = "failed", "评测智能体或模型不可用", now()
            await db.commit()
            return
        job.status, job.started_at = "running", now()
        await db.commit()
        try:
            policy = await db.scalar(select(TenantPolicy).where(TenantPolicy.tenant_id == job.tenant_id))
            safety_policy = (policy.safety_json if policy else {}) or {}
            results: list[dict[str, Any]] = []
            total_tokens = 0
            for case in (job.request_json or {}).get("cases", []):
                message = str(case.get("message") or "")
                safety = inspect_text(message, safety_policy)
                if safety["blocked"]:
                    results.append({"message": message, "passed": False, "score": 0, "error": "安全策略拦截", "reasons": safety["reasons"]})
                    continue
                response = await call_chat(db, provider, [{"role": "system", "content": agent.system_prompt}, {"role": "user", "content": safety["text"]}], tenant_id=job.tenant_id)
                answer = response.get("text", "")
                usage = response.get("usage") or {}
                total_tokens += int(usage.get("total_tokens", 0))
                expected = [str(value) for value in case.get("expected_contains", [])]
                missing = [value for value in expected if value.lower() not in answer.lower()]
                results.append({"message": message, "answer": answer, "passed": not missing, "score": 1 if not missing else 0, "missing": missing, "usage": usage})
            passed = sum(1 for item in results if item["passed"])
            job.results_json = {"agent_id": agent.id, "total": len(results), "passed": passed, "score": round(passed / len(results), 4) if results else 0, "results": results}
            job.status, job.finished_at = "succeeded", now()
            db.add(ComputeUsage(tenant_id=job.tenant_id, tokens=total_tokens))
            await db.commit()
        except Exception as exc:
            job.status, job.error, job.finished_at = "failed", str(exc), now()
            await db.commit()


async def execute_sandbox(run_id: str) -> None:
    async with AdminSessionLocal() as db:
        row = await db.scalar(select(SandboxRun).where(SandboxRun.id == run_id))
        if not row or row.status not in {"queued", "running"}:
            return
        row.status, row.started_at = "running", now()
        await db.commit()
        try:
            source = row.source_json or {}
            manifest = build_job_manifest(row.id, row.runtime, source, int(source.get("timeout_seconds", 300)), int(source.get("cpu_millicores", 500)), int(source.get("memory_mb", 512)))
            row.manifest_json = manifest
            row.output_json = {"dispatch": "kubernetes_job", "job_name": manifest["metadata"]["name"], "message": "已生成受限 Job，等待集群沙箱控制器提交"}
            row.status, row.finished_at = "submitted", now()
            await db.commit()
        except Exception as exc:
            row.status, row.error, row.finished_at = "failed", str(exc), now()
            await db.commit()


async def reconcile_gpu_leases() -> None:
    async with AdminSessionLocal() as db:
        current = now()
        rows = (await db.execute(select(GpuLease).where(GpuLease.status.in_(["allocated", "queued"]), GpuLease.expires_at <= current))).scalars().all()
        for row in rows:
            row.status, row.released_at = "expired", current
        settings = get_settings()
        allocated = await db.scalar(select(func.coalesce(func.sum(GpuLease.requested_count), 0)).where(GpuLease.status == "allocated", GpuLease.expires_at > current)) or 0
        queued = (await db.execute(select(GpuLease).where(GpuLease.status == "queued", GpuLease.expires_at > current).order_by(GpuLease.created_at).with_for_update(skip_locked=True))).scalars().all()
        node_names = settings.gpu_node_name_list
        for row in queued:
            if int(allocated) + row.requested_count > settings.gpu_total_count:
                break
            row.status = "allocated"
            row.node_name = node_names[int(allocated) % len(node_names)] if node_names else "unassigned"
            allocated += row.requested_count
        if rows or queued:
            await db.commit()


async def dispatch_schedules(redis: Redis) -> None:
    """Create queued runs for due interval schedules with an atomic next-run advance."""
    current = now()
    async with AdminSessionLocal() as db:
        schedules = (await db.execute(select(WorkflowSchedule).where(WorkflowSchedule.active.is_(True), WorkflowSchedule.next_run_at <= current).order_by(WorkflowSchedule.next_run_at).limit(50).with_for_update(skip_locked=True))).scalars().all()
        queued_ids: list[str] = []
        for schedule in schedules:
            workflow = await db.scalar(select(Workflow).where(Workflow.id == schedule.workflow_id, Workflow.tenant_id == schedule.tenant_id, Workflow.status == "published"))
            if not workflow or not workflow.published_version:
                schedule.next_run_at = current + timedelta(seconds=max(10, schedule.interval_seconds))
                continue
            run = WorkflowRun(tenant_id=schedule.tenant_id, project_id=workflow.project_id, workflow_id=workflow.id, workflow_version=workflow.published_version, input_json=schedule.input_json, trace_id="", created_by=schedule.created_by)
            db.add(run)
            await db.flush()
            queued_ids.append(run.id)
            schedule.last_run_at = current
            schedule.next_run_at = current + timedelta(seconds=max(10, schedule.interval_seconds))
        await db.commit()
    if queued_ids:
        await redis.rpush(QUEUE, *queued_ids)


def next_graph_nodes(graph: dict[str, Any], node: dict[str, Any], output: dict[str, Any]) -> list[str]:
    """Resolve outgoing edges, including true/false condition handles."""
    node_id = str(node.get("id", ""))
    edges = [edge for edge in graph.get("edges", []) if str(edge.get("source", "")) == node_id]
    node_type = str((node.get("data") or {}).get("kind") or node.get("type", "")).lower()
    if node_type in {"condition", "if", "switch"}:
        branch = "true" if bool(output.get("result")) else "false"
        labeled = [edge for edge in edges if edge.get("sourceHandle") or edge.get("condition")]
        if labeled:
            edges = [edge for edge in labeled if str(edge.get("sourceHandle") or edge.get("condition")).lower() in {branch, "default"}]
    return [str(edge["target"]) for edge in edges if edge.get("target")]


async def execute_graph(db, run: WorkflowRun, version: WorkflowVersion) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = version.graph_json or {}
    nodes = {str(node["id"]): node for node in graph.get("nodes", []) if node.get("id")}
    incoming = {node_id: 0 for node_id in nodes}
    for edge in graph.get("edges", []):
        target = str(edge.get("target", ""))
        if target in incoming:
            incoming[target] += 1
    state = dict(run.state_json or {})
    completed = dict(state.get("nodes", {}))
    pending = list(state.get("pending_nodes", []))
    if not pending:
        pending = [node_id for node_id, count in incoming.items() if count == 0]
    context = {"input": dict(run.input_json or {}), "nodes": completed, "run": {"id": run.id}}
    while pending:
        node_id = pending.pop(0)
        if node_id not in nodes or node_id in completed:
            continue
        node = nodes[node_id]
        node_type = str((node.get("data") or {}).get("kind") or node.get("type", "")).lower()
        config = node.get("data") or node.get("config") or {}
        retry_limit = max(0, min(int(config.get("retry", 0)), 5))
        timeout_seconds = max(1, min(int(config.get("timeout_seconds", 120)), 900))
        output: dict[str, Any] | None = None
        for attempt in range(retry_limit + 1):
            try:
                output = await asyncio.wait_for(execute_node(db, run, node_type, node_id, config, context), timeout=timeout_seconds)
                break
            except Exception:
                if attempt >= retry_limit:
                    raise
                await asyncio.sleep(min(2 ** attempt, 8))
        output = output or {}
        context["nodes"][node_id] = output
        state["nodes"] = context["nodes"]
        state["last_node_id"] = node_id
        next_nodes = next_graph_nodes(graph, node, output)
        pending.extend(item for item in next_nodes if item not in completed and item not in pending)
        state["pending_nodes"] = pending
        run.state_json = state
        await db.commit()
        if node_type in {"approval", "human_approval"} and not output.get("approved", False):
            run.status = "waiting_approval"
            state["waiting_node_id"] = node_id
            await db.commit()
            runs_total.labels(run.tenant_id, "waiting_approval").inc()
            return context["nodes"], state
    return context["nodes"], state


async def execute_node(db, run: WorkflowRun, node_type: str, node_id: str, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if node_type in {"input", "start"}:
        return context["input"]
    if node_type in {"output", "end"}:
        value = resolve(config.get("value", "{{previous}}"), {**context, "previous": list(context["nodes"].values())[-1] if context["nodes"] else context["input"]})
        return {"value": value}
    if node_type in {"approval", "human_approval"}:
        approved = (context["nodes"].get(node_id) or {}).get("approved", False)
        return {"approved": approved, "comment": (context["nodes"].get(node_id) or {}).get("comment", "")}
    if node_type == "condition":
        expr = str(resolve(config.get("expression", ""), context)).strip().lower()
        return {"result": expr not in {"", "false", "0", "none", "null"}}
    if node_type in {"loop", "foreach"}:
        items = resolve(config.get("items", "{{input.items}}"), context)
        if not isinstance(items, list):
            items = [] if items is None or items == "" else [items]
        body = config.get("body") or {"kind": "output", "value": "{{item}}"}
        body_type = str(body.get("kind") or body.get("type", "output")).lower()
        results = []
        for index, item in enumerate(items):
            local = {**context, "item": item, "index": index}
            body_config = body.get("data") or body.get("config") or body
            results.append(await execute_node(db, run, body_type, f"{node_id}:{index}", body_config, local))
        return {"items": results, "count": len(results)}
    if node_type == "parallel":
        branches = config.get("branches") or []
        async def run_branch(index: int, branch: dict[str, Any]) -> dict[str, Any]:
            branch_type = str(branch.get("kind") or branch.get("type", "output")).lower()
            branch_config = branch.get("data") or branch.get("config") or branch
            return await execute_node(db, run, branch_type, f"{node_id}:{index}", branch_config, {**context, "branch_index": index})
        results = await asyncio.gather(*(run_branch(index, branch) for index, branch in enumerate(branches)))
        return {"branches": results, "count": len(results)}
    if node_type == "knowledge":
        kb_id = str(config.get("kb_id", ""))
        query = str(resolve(config.get("query", "{{input.question}}"), context))
        rows = await search_chunks(db, run.tenant_id, kb_id, query, int(config.get("limit", 5)))
        return {"query": query, "results": rows, "context": "\n\n".join(row["content"] for row in rows)}
    if node_type == "llm":
        provider = await _provider(db, run.tenant_id, config)
        system = str(resolve(config.get("system", "You are an enterprise assistant."), context))
        prompt = str(resolve(config.get("prompt", "{{input.question}}"), context))
        result = await call_chat(db, provider, [{"role": "system", "content": system}, {"role": "user", "content": prompt}], tenant_id=run.tenant_id, model=config.get("model"), temperature=float(config.get("temperature", 0.2)), max_tokens=config.get("max_tokens"))
        return result
    if node_type == "agent":
        agent_id = str(config.get("agent_id", ""))
        agent = await db.scalar(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == run.tenant_id, Agent.enabled.is_(True)))
        if not agent:
            raise RuntimeError("Agent 不存在或已禁用")
        provider = await _provider(db, run.tenant_id, {"provider_id": agent.provider_id})
        prompt = str(resolve(config.get("prompt", "{{input.question}}"), context))
        knowledge_context = ""
        if agent.knowledge_base_id:
            rows = await search_chunks(db, run.tenant_id, agent.knowledge_base_id, prompt, 5)
            knowledge_context = "\n\n".join(row["content"] for row in rows)
        system = agent.system_prompt + (f"\n\nEnterprise knowledge context:\n{knowledge_context}" if knowledge_context else "")
        return await call_chat(db, provider, [{"role": "system", "content": system}, {"role": "user", "content": prompt}], tenant_id=run.tenant_id)
    if node_type in {"http", "request"}:
        url = str(resolve(config.get("url", ""), context))
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        allowed = get_settings().allowed_hosts
        if not host or host not in allowed:
            raise RuntimeError("HTTP 节点目标不在允许的主机列表中")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(str(config.get("method", "POST")).upper(), url, json=resolve(config.get("body", {}), context))
            response.raise_for_status()
            tool_calls.labels(run.tenant_id, "http", "success").inc()
            try:
                return response.json()
            except ValueError:
                return {"text": response.text}
    if node_type == "plugin":
        plugin_id = str(config.get("plugin_id", ""))
        plugin = await db.scalar(select(Plugin).where(Plugin.id == plugin_id, Plugin.tenant_id == run.tenant_id, Plugin.enabled.is_(True)))
        if not plugin:
            raise RuntimeError("插件不存在或已禁用")
        if plugin.approval_status != "approved":
            raise RuntimeError("插件尚未通过审批")
        from urllib.parse import urlparse
        plugin_host = (urlparse(plugin.endpoint).hostname or "").lower()
        if not plugin_host or plugin_host not in get_settings().allowed_hosts:
            raise RuntimeError("插件地址不在允许的主机列表中")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(plugin.endpoint, json=resolve(config.get("input", context), context), headers={"X-AI-Tenant-ID": run.tenant_id})
            response.raise_for_status()
            tool_calls.labels(run.tenant_id, "plugin", "success").inc()
            return response.json()
    if node_type == "skill":
        skill_id = str(config.get("skill_id", ""))
        skill = await db.scalar(select(Skill).where(Skill.id == skill_id, Skill.tenant_id == run.tenant_id, Skill.enabled.is_(True)))
        if not skill:
            raise RuntimeError("Skill 不存在或已禁用")
        return {"name": skill.name, "version": skill.version, "instructions": skill.instructions}
    raise RuntimeError(f"不支持的工作流节点类型: {node_type}")


async def worker_loop() -> None:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    while True:
        await dispatch_schedules(redis)
        await reconcile_gpu_leases()
        item = await redis.blpop([QUEUE, INDEX_QUEUE, get_settings().evaluation_queue, get_settings().sandbox_queue], timeout=5)
        if item:
            if item[0] == INDEX_QUEUE:
                await execute_index(item[1])
            elif item[0] == get_settings().evaluation_queue:
                await execute_evaluation(item[1])
            elif item[0] == get_settings().sandbox_queue:
                await execute_sandbox(item[1])
            else:
                await execute_run(item[1])
