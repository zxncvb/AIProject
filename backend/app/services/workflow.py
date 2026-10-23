import asyncio
import json
import logging
import os
import re
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import func, or_, select

from ..config import get_settings
from ..db import AdminSessionLocal
from ..models import Agent, ApprovalRequest, ComputeUsage, Document, EvaluationJob, GpuLease, ModelProvider, Plugin, Project, PublishDelivery, SandboxRun, Skill, TenantPolicy, Workflow, WorkflowRun, WorkflowSchedule, WorkflowVersion
from .knowledge import search_chunks
from .llm import call_chat, call_routed_chat
from .evaluation import judge_answer
from .observability import new_trace_id, run_failures, runs_total, tool_calls
from .safety import inspect_text
from .sandbox import build_job_manifest
from .publication import deliver as deliver_publication


QUEUE = "ai_platform:workflow_runs"
INDEX_QUEUE = "ai_platform:knowledge_index"
EVALUATION_QUEUE = "ai_platform:evaluation_jobs"
SANDBOX_QUEUE = "ai_platform:sandbox_runs"
JOB_KINDS = {"workflow", "knowledge_index", "evaluation", "sandbox", "publication_delivery"}


class WorkflowCancelled(Exception):
    pass


async def is_run_cancelled(run_id: str) -> bool:
    async with AdminSessionLocal() as check_db:
        status = await check_db.scalar(select(WorkflowRun.status).where(WorkflowRun.id == run_id))
        return status == "cancelled"


def now() -> datetime:
    return datetime.now(timezone.utc)


def _cron_field(value: str, minimum: int, maximum: int) -> set[int]:
    selected: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            raise ValueError("cron 字段不能为空")
        base, _, step_text = part.partition("/")
        try:
            step = int(step_text) if step_text else 1
        except ValueError as exc:
            raise ValueError("cron 步长无效") from exc
        if step <= 0:
            raise ValueError("cron 步长必须大于 0")
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            pieces = base.split("-", 1)
            try:
                start, end = int(pieces[0]), int(pieces[1])
            except ValueError as exc:
                raise ValueError("cron 范围无效") from exc
        else:
            try:
                start = end = int(base)
            except ValueError as exc:
                raise ValueError("cron 值无效") from exc
        if start < minimum or end > maximum or start > end:
            raise ValueError(f"cron 值必须在 {minimum}-{maximum} 范围内")
        selected.update(range(start, end + 1, step))
    return selected


def next_cron_occurrence(expression: str, timezone_name: str, after: datetime) -> datetime:
    """Return the next UTC occurrence for a standard five-field cron expression."""
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("cron 表达式必须包含 5 个字段：分 时 日 月 周")
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"不支持的时区: {timezone_name}") from exc
    minutes = _cron_field(fields[0], 0, 59)
    hours = _cron_field(fields[1], 0, 23)
    days = _cron_field(fields[2], 1, 31)
    months = _cron_field(fields[3], 1, 12)
    weekdays = _cron_field(fields[4], 0, 6)
    local = after.astimezone(tz).replace(second=0, microsecond=0, tzinfo=None) + timedelta(minutes=1)
    day_restricted = fields[2] != "*"
    weekday_restricted = fields[4] != "*"
    for _ in range(366 * 24 * 60):
        weekday = (local.weekday() + 1) % 7
        month_matches = local.month in months
        day_matches = local.day in days
        weekday_matches = weekday in weekdays
        if not month_matches:
            calendar_matches = False
        elif day_restricted and weekday_restricted:
            calendar_matches = day_matches or weekday_matches
        elif day_restricted:
            calendar_matches = day_matches
        elif weekday_restricted:
            calendar_matches = weekday_matches
        else:
            calendar_matches = True
        if local.minute in minutes and local.hour in hours and calendar_matches:
            candidate = local.replace(tzinfo=tz)
            utc_candidate = candidate.astimezone(timezone.utc)
            # Skip nonexistent local times during a DST spring-forward gap.
            if utc_candidate.astimezone(tz).replace(tzinfo=None) == local:
                return utc_candidate
        local += timedelta(minutes=1)
    raise ValueError("cron 表达式在一年内没有可执行时间")


def next_schedule_time(cron_expression: str, timezone_name: str, interval_seconds: int | None, base: datetime) -> datetime:
    if cron_expression.strip():
        return next_cron_occurrence(cron_expression.strip(), timezone_name or "UTC", base)
    if not interval_seconds:
        raise ValueError("调度必须配置 interval_seconds 或 cron_expression")
    return base + timedelta(seconds=max(10, interval_seconds))


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


async def _job_tenant_id(kind: str, resource_id: str) -> str:
    model_by_kind = {
        "workflow": WorkflowRun,
        "knowledge_index": Document,
        "evaluation": EvaluationJob,
        "sandbox": SandboxRun,
        "publication_delivery": PublishDelivery,
    }
    model = model_by_kind.get(kind)
    if not model:
        return ""
    async with AdminSessionLocal() as db:
        return str(await db.scalar(select(model.tenant_id).where(model.id == resource_id)) or "")


async def enqueue_job(kind: str, resource_id: str, redis: Redis | None = None, *, tenant_id: str | None = None, priority: int = 5) -> str:
    if kind not in JOB_KINDS:
        raise ValueError(f"unsupported job kind: {kind}")
    owned = redis is None
    redis = redis or Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        tenant_id = tenant_id or await _job_tenant_id(kind, resource_id)
        fields = {"kind": kind, "resource_id": resource_id, "tenant_id": tenant_id or "unknown", "priority": str(max(0, min(int(priority), 9))), "queued_at": now().isoformat()}
        return await redis.xadd(get_settings().job_stream, fields, maxlen=100000, approximate=True)
    finally:
        if owned:
            await redis.aclose()


async def enqueue_run(run_id: str) -> None:
    try:
        await enqueue_job("workflow", run_id)
    except Exception:
        asyncio.create_task(execute_run(run_id))


async def enqueue_index(document_id: str) -> None:
    await enqueue_job("knowledge_index", document_id)


async def enqueue_evaluation(job_id: str) -> None:
    await enqueue_job("evaluation", job_id)


async def enqueue_sandbox(run_id: str) -> None:
    await enqueue_job("sandbox", run_id)


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
            if run.status == "waiting_approval":
                return
            if await is_run_cancelled(run.id):
                raise WorkflowCancelled()
            last_node_id = state.get("last_node_id")
            run.output_json = completed.get(last_node_id, completed) if last_node_id else completed
            run.status, run.finished_at = "succeeded", now()
            run.state_json = state
            db.add(ComputeUsage(tenant_id=run.tenant_id, run_id=run.id, cost_center=run.cost_center or "unassigned", cpu_milliseconds=int((time.perf_counter() - started_clock) * 1000), tokens=sum(int((value or {}).get("usage", {}).get("total_tokens", 0)) for value in completed.values() if isinstance(value, dict))))
            await db.commit()
            runs_total.labels(run.tenant_id, "succeeded").inc()
        except WorkflowCancelled:
            run.status, run.error, run.finished_at = "cancelled", "已由用户取消", now()
            db.add(ComputeUsage(tenant_id=run.tenant_id, run_id=run.id, cost_center=run.cost_center or "unassigned", cpu_milliseconds=int((time.perf_counter() - started_clock) * 1000)))
            await db.commit()
            runs_total.labels(run.tenant_id, "cancelled").inc()
        except Exception as exc:
            run.error = str(exc)
            compensation_errors: list[str] = []
            try:
                compensation_errors = await execute_compensations(db, run, version)
            except Exception as compensation_exc:
                compensation_errors.append(f"补偿调度失败: {compensation_exc}")
            suffix = f"；补偿异常: {' | '.join(compensation_errors)}" if compensation_errors else ""
            run.status, run.error, run.finished_at = "failed", f"{exc}{suffix}", now()
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
            judge_tokens = 0
            request = job.request_json or {}
            judge_enabled = bool(request.get("judge_enabled"))
            judge_provider_id = str(request.get("judge_provider_id") or "") or None
            for case in (job.request_json or {}).get("cases", []):
                message = str(case.get("message") or "")
                safety = inspect_text(message, safety_policy)
                if safety["blocked"]:
                    results.append({"message": message, "passed": False, "score": 0, "error": "安全策略拦截", "reasons": safety["reasons"]})
                    continue
                response = await call_routed_chat(db, [{"role": "system", "content": agent.system_prompt}, {"role": "user", "content": safety["text"]}], tenant_id=job.tenant_id, preferred_provider_id=agent.provider_id)
                answer = response.get("text", "")
                usage = response.get("usage") or {}
                total_tokens += int(usage.get("total_tokens", 0))
                expected = [str(value) for value in case.get("expected_contains", [])]
                missing = [value for value in expected if value.lower() not in answer.lower()]
                item = {"message": message, "answer": answer, "passed": not missing, "score": 1 if not missing else 0, "missing": missing, "usage": usage}
                if judge_enabled:
                    judge = await judge_answer(db, tenant_id=job.tenant_id, answer=answer, expected_contains=expected, provider_id=judge_provider_id)
                    item["judge"] = judge
                    item["passed"] = bool(item["passed"] and judge["passed"])
                    item["score"] = round((float(item["score"]) + float(judge["score"])) / 2, 4)
                    judge_tokens += int((judge.get("usage") or {}).get("total_tokens", 0))
                results.append(item)
            passed = sum(1 for item in results if item["passed"])
            score = round(passed / len(results), 4) if results else 0
            threshold = max(0.0, min(1.0, float(request.get("regression_threshold") or 0)))
            gate_passed = not threshold or score >= threshold
            job.results_json = {"agent_id": agent.id, "dataset_version": request.get("dataset_version", "v1"), "total": len(results), "passed": passed, "score": score, "regression_threshold": threshold, "regression_gate": "passed" if gate_passed else "failed", "judge_enabled": judge_enabled, "results": results}
            job.status, job.finished_at = ("succeeded" if gate_passed else "regression_failed"), now()
            db.add(ComputeUsage(tenant_id=job.tenant_id, tokens=total_tokens + judge_tokens))
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
            request = row.source_json or {}
            source = request.get("source", request)
            manifest = build_job_manifest(row.id, row.runtime, source, int(request.get("timeout_seconds", 300)), int(request.get("cpu_millicores", 500)), int(request.get("memory_mb", 512)))
            row.manifest_json = manifest
            row.output_json = {"dispatch": "kubernetes_job", "job_name": manifest["metadata"]["name"], "message": "已生成受限 Job，等待集群沙箱控制器提交"}
            row.status, row.finished_at = "submitted", None
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
    """Create queued runs for due schedules with an atomic next-run advance."""
    current = now()
    async with AdminSessionLocal() as db:
        schedules = (await db.execute(select(WorkflowSchedule).where(WorkflowSchedule.active.is_(True), WorkflowSchedule.next_run_at <= current).order_by(WorkflowSchedule.next_run_at).limit(50).with_for_update(skip_locked=True))).scalars().all()
        queued_ids: list[str] = []
        for schedule in schedules:
            workflow = await db.scalar(select(Workflow).where(Workflow.id == schedule.workflow_id, Workflow.tenant_id == schedule.tenant_id, Workflow.status == "published"))
            try:
                next_run_after_due = next_schedule_time(schedule.cron_expression, schedule.timezone, schedule.interval_seconds, schedule.next_run_at)
                next_run_at = next_schedule_time(schedule.cron_expression, schedule.timezone, schedule.interval_seconds, current)
            except ValueError:
                schedule.active = False
                continue
            misfired = next_run_after_due <= current
            if misfired and schedule.misfire_policy == "skip":
                # The schedule missed one or more occurrences while the worker
                # was down; advance to the next future occurrence without
                # creating a catch-up run.
                schedule.next_run_at = next_run_at
                continue
            if not workflow or not workflow.published_version:
                schedule.next_run_at = next_run_at
                continue
            project = await db.scalar(select(Project).where(Project.id == workflow.project_id, Project.tenant_id == workflow.tenant_id))
            cost_center = f"project:{project.slug}"[:120] if project and project.slug else "workflow"
            run = WorkflowRun(tenant_id=schedule.tenant_id, project_id=workflow.project_id, workflow_id=workflow.id, workflow_version=workflow.published_version, cost_center=cost_center, input_json=schedule.input_json, trace_id="", created_by=schedule.created_by)
            db.add(run)
            await db.flush()
            queued_ids.append(run.id)
            schedule.last_run_at = current
            schedule.next_run_at = next_run_at
        await db.commit()
    for run_id in queued_ids:
        await enqueue_job("workflow", run_id, redis)


async def dispatch_publication_deliveries(redis: Redis) -> None:
    """Drain the database outbox while recovering expired enqueue reservations."""
    current = now()
    async with AdminSessionLocal() as db:
        rows = (await db.execute(
            select(PublishDelivery)
            .where(
                or_(
                    PublishDelivery.status == "queued",
                    (PublishDelivery.status == "failed") & (PublishDelivery.next_attempt_at <= current),
                    (PublishDelivery.status == "enqueued") & (PublishDelivery.next_attempt_at <= current),
                )
            )
            .order_by(PublishDelivery.created_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        )).scalars().all()
        delivery_ids = [row.id for row in rows]
        for row in rows:
            row.status = "enqueued"
            row.next_attempt_at = current + timedelta(minutes=2)
        await db.commit()
    for delivery_id in delivery_ids:
        try:
            await enqueue_job("publication_delivery", delivery_id, redis)
        except Exception as exc:
            async with AdminSessionLocal() as db:
                row = await db.scalar(select(PublishDelivery).where(PublishDelivery.id == delivery_id))
                if row and row.status == "enqueued":
                    row.status = "queued"
                    row.error = f"发布任务入队失败: {exc}"[:2000]
                    row.next_attempt_at = None
                    await db.commit()


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
        if await is_run_cancelled(run.id):
            raise WorkflowCancelled()
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
        completed_order = list(state.get("completed_order", []))
        if node_id not in completed_order:
            completed_order.append(node_id)
        state["completed_order"] = completed_order
        next_nodes = next_graph_nodes(graph, node, output)
        pending.extend(item for item in next_nodes if item not in completed and item not in pending)
        state["pending_nodes"] = pending
        run.state_json = state
        await db.commit()
        if node_type in {"approval", "human_approval"} and not output.get("approved", False):
            run.status = "waiting_approval"
            state["waiting_node_id"] = node_id
            existing = await db.scalar(select(ApprovalRequest).where(ApprovalRequest.tenant_id == run.tenant_id, ApprovalRequest.request_type == "workflow.node", ApprovalRequest.resource_id == run.id, ApprovalRequest.status == "pending"))
            if not existing:
                db.add(ApprovalRequest(
                    tenant_id=run.tenant_id,
                    applicant_id=run.created_by,
                    request_type="workflow.node",
                    resource_type="workflow_run",
                    resource_id=run.id,
                    title=str(config.get("title") or f"工作流节点审批：{node_id}"),
                    payload_json={"run_id": run.id, "node_id": node_id, "approver_roles": config.get("approver_roles", ["admin", "owner"]), "min_approvals": int(config.get("min_approvals", 1))},
                ))
            await db.commit()
            runs_total.labels(run.tenant_id, "waiting_approval").inc()
            return context["nodes"], state
    return context["nodes"], state


async def execute_compensations(db, run: WorkflowRun, version: WorkflowVersion) -> list[str]:
    """Execute configured node compensations in reverse completion order.

    A node opts in with ``data.compensation`` using the same shape as a normal
    node (for example an HTTP or plugin call). Results are persisted so a
    retried worker never repeats an already successful compensation.
    """
    graph = version.graph_json or {}
    nodes = {str(node["id"]): node for node in graph.get("nodes", []) if node.get("id")}
    state = dict(run.state_json or {})
    compensation_state = dict(state.get("compensations", {}))
    context = {"input": dict(run.input_json or {}), "nodes": dict(state.get("nodes", {})), "run": {"id": run.id, "error": run.error}}
    errors: list[str] = []
    for node_id in reversed(list(state.get("completed_order", []))):
        node = nodes.get(node_id) or {}
        config = node.get("data") or node.get("config") or {}
        compensation = config.get("compensation")
        if not isinstance(compensation, dict) or compensation_state.get(node_id, {}).get("status") == "succeeded":
            continue
        kind = str(compensation.get("kind") or compensation.get("type") or "").lower()
        compensation_config = compensation.get("data") or compensation.get("config") or compensation
        if not kind or kind in {"approval", "human_approval", "loop", "parallel"}:
            errors.append(f"{node_id}: 补偿节点类型无效")
            compensation_state[node_id] = {"status": "failed", "error": "补偿节点类型无效"}
            continue
        try:
            output = await asyncio.wait_for(execute_node(db, run, kind, f"compensate:{node_id}", compensation_config, context), timeout=max(1, min(int(compensation_config.get("timeout_seconds", 60)), 300)))
            compensation_state[node_id] = {"status": "succeeded", "output": output, "finished_at": now().isoformat()}
        except Exception as exc:
            compensation_state[node_id] = {"status": "failed", "error": str(exc)[:1000], "finished_at": now().isoformat()}
            errors.append(f"{node_id}: {exc}")
        state["compensations"] = compensation_state
        run.state_json = state
        await db.commit()
    return errors


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
        result = await call_routed_chat(db, [{"role": "system", "content": system}, {"role": "user", "content": prompt}], tenant_id=run.tenant_id, preferred_provider_id=config.get("provider_id"), model=config.get("model"), temperature=float(config.get("temperature", 0.2)), max_tokens=config.get("max_tokens"))
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
        return await call_routed_chat(db, [{"role": "system", "content": system}, {"role": "user", "content": prompt}], tenant_id=run.tenant_id, preferred_provider_id=agent.provider_id)
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


def fair_order_messages(messages: list[tuple[str, dict[str, str]]]) -> list[tuple[str, dict[str, str]]]:
    """Round-robin messages by tenant while keeping lower priority first."""
    buckets: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for message_id, fields in messages:
        tenant_id = fields.get("tenant_id") or "unknown"
        buckets.setdefault(tenant_id, []).append((message_id, fields))
    for bucket in buckets.values():
        bucket.sort(key=lambda item: (int(item[1].get("priority", "5") or 5), item[0]))
    ordered: list[tuple[str, dict[str, str]]] = []
    while buckets:
        for tenant_id in list(buckets):
            bucket = buckets[tenant_id]
            if bucket:
                ordered.append(bucket.pop(0))
            if not bucket:
                buckets.pop(tenant_id, None)
    return ordered


async def worker_loop() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    try:
        try:
            await redis.xgroup_create(settings.job_stream, settings.job_consumer_group, id="0-0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

        # Drain the queues used by earlier releases so upgrades do not lose queued work.
        legacy_queues = {
            QUEUE: "workflow",
            INDEX_QUEUE: "knowledge_index",
            settings.evaluation_queue: "evaluation",
            settings.sandbox_queue: "sandbox",
        }
        for queue, kind in legacy_queues.items():
            for _ in range(1000):
                resource_id = await redis.lpop(queue)
                if not resource_id:
                    break
                await enqueue_job(kind, resource_id, redis)

        while True:
            await dispatch_schedules(redis)
            await dispatch_publication_deliveries(redis)
            await reconcile_gpu_leases()

            claimed = await redis.xautoclaim(
                settings.job_stream,
                settings.job_consumer_group,
                consumer,
                settings.worker_claim_idle_ms,
                start_id="0-0",
                count=20,
            )
            messages = claimed[1] if len(claimed) > 1 else []
            if not messages:
                batches = await redis.xreadgroup(
                    settings.job_consumer_group,
                    consumer,
                    {settings.job_stream: ">"},
                    count=20,
                    block=5000,
                )
                messages = batches[0][1] if batches else []

            ordered_messages = fair_order_messages(messages)
            global_limit = asyncio.Semaphore(max(1, settings.worker_max_concurrency))
            tenant_limits: dict[str, asyncio.Semaphore] = {}

            async def process_message(message_id: str, fields: dict[str, str]) -> None:
                kind = fields.get("kind", "")
                resource_id = fields.get("resource_id", "")
                tenant_id = fields.get("tenant_id") or "unknown"
                attempts = int(fields.get("attempts", "0") or 0)
                tenant_limit = tenant_limits.setdefault(tenant_id, asyncio.Semaphore(max(1, settings.worker_per_tenant_concurrency)))
                try:
                    async with global_limit, tenant_limit:
                        async with asyncio.timeout(max(10, settings.worker_job_timeout_seconds)):
                            if kind == "workflow":
                                await execute_run(resource_id)
                            elif kind == "knowledge_index":
                                await execute_index(resource_id)
                            elif kind == "evaluation":
                                await execute_evaluation(resource_id)
                            elif kind == "sandbox":
                                await execute_sandbox(resource_id)
                            elif kind == "publication_delivery":
                                await deliver_publication(resource_id)
                            else:
                                raise ValueError(f"unsupported job kind: {kind}")
                except Exception as exc:
                    logging.getLogger("enterprise_ai_platform.worker").exception(
                        "job failed kind=%s resource_id=%s tenant_id=%s attempt=%s", kind, resource_id, tenant_id, attempts + 1
                    )
                    retry_fields = {
                        "kind": kind,
                        "resource_id": resource_id,
                        "tenant_id": tenant_id,
                        "priority": fields.get("priority", "5"),
                        "queued_at": fields.get("queued_at", now().isoformat()),
                        "attempts": str(attempts + 1),
                        "last_error": str(exc)[:1000],
                    }
                    target = settings.job_stream if attempts + 1 < settings.worker_max_attempts else f"{settings.job_stream}:dead"
                    await redis.xadd(target, retry_fields, maxlen=100000, approximate=True)
                finally:
                    await redis.xack(settings.job_stream, settings.job_consumer_group, message_id)
                    await redis.xdel(settings.job_stream, message_id)

            await asyncio.gather(*(process_message(message_id, fields) for message_id, fields in ordered_messages))
    finally:
        await redis.aclose()
