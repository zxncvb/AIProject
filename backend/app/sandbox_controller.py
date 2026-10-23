"""Kubernetes controller for submitted full-code sandbox jobs.

Run this as a separate service in a cluster. The API/worker only creates a
restricted Job manifest; this controller is the component allowed to submit
and observe Jobs in Kubernetes.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from sqlalchemy import select

from .db import AdminSessionLocal
from .models import SandboxRun
from .services.public_callback import deliver_public_callback, public_callback_payload


NAMESPACE = os.getenv("SANDBOX_NAMESPACE", "ai-platform")
logger = logging.getLogger(__name__)


def load_cluster_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def job_name(row: SandboxRun) -> str:
    return str((row.manifest_json.get("metadata") or {}).get("name") or "")


def delete_job(api: client.BatchV1Api, name: str) -> None:
    if not name:
        return
    try:
        api.delete_namespaced_job(name, NAMESPACE, propagation_policy="Background")
    except ApiException as exc:
        if exc.status != 404:
            raise


def job_logs(core_api: client.CoreV1Api | None, run_id: str) -> str:
    if core_api is None:
        return ""
    pods = core_api.list_namespaced_pod(NAMESPACE, label_selector=f"ai.platform/run-id={run_id}", limit=5)
    parts = []
    for pod in pods.items:
        try:
            parts.append(core_api.read_namespaced_pod_log(pod.metadata.name, NAMESPACE, tail_lines=300, timestamps=True)[:65536])
        except ApiException as exc:
            logger.warning("sandbox log collection failed for %s: %s", run_id, exc.status)
    return "\n".join(parts)[:65536]


async def notify_public_callback(row: SandboxRun) -> None:
    callback_url = str((row.source_json or {}).get("callback_url") or "").strip()
    if not callback_url:
        return
    try:
        result = await deliver_public_callback(
            callback_url,
            public_callback_payload(
                kind="sandbox",
                run_id=row.id,
                tenant_id=row.tenant_id,
                status=row.status,
                output=row.output_json,
                error=row.error,
                finished_at=row.finished_at,
            ),
        )
        if not result.get("delivered"):
            logger.warning("public sandbox callback was not delivered run_id=%s", row.id)
    except Exception:
        logger.exception("public sandbox callback failed run_id=%s", row.id)


async def reconcile_once(api: client.BatchV1Api, core_api: client.CoreV1Api | None = None) -> None:
    async with AdminSessionLocal() as db:
        submitted = (await db.execute(select(SandboxRun).where(SandboxRun.status == "submitted").limit(20))).scalars().all()
        for row in submitted:
            try:
                api.create_namespaced_job(namespace=NAMESPACE, body=row.manifest_json)
                await db.refresh(row)
                if row.status == "cancelled":
                    delete_job(api, job_name(row))
                    continue
                row.status = "running"
                await db.commit()
            except ApiException as exc:
                if exc.status == 409:
                    await db.refresh(row)
                    if row.status == "cancelled":
                        delete_job(api, job_name(row))
                        continue
                    row.status = "running"
                    await db.commit()
                else:
                    row.status, row.error = "failed", f"kubernetes submit failed: {exc.reason}"
                    row.finished_at = datetime.now(timezone.utc)
                    await db.commit()
                    await notify_public_callback(row)
        active = (await db.execute(select(SandboxRun).where(SandboxRun.status == "running").limit(50))).scalars().all()
        for row in active:
            name = job_name(row)
            if not name:
                continue
            try:
                job = api.read_namespaced_job_status(name, NAMESPACE)
            except ApiException as exc:
                if exc.status == 404:
                    row.status, row.error, row.finished_at = "failed", "Kubernetes Job 不存在", datetime.now(timezone.utc)
                    await db.commit()
                    await notify_public_callback(row)
                    continue
                raise
            status = job.status
            if status.succeeded or status.failed:
                logs = job_logs(core_api, row.id)
                await db.refresh(row)
                if row.status == "cancelled":
                    delete_job(api, name)
                    continue
                row.status = "succeeded" if status.succeeded else "failed"
                row.error = "" if status.succeeded else f"sandbox job failed: {status.failed}"
                row.finished_at = datetime.now(timezone.utc)
                row.output_json = {"job_name": name, "succeeded": bool(status.succeeded), "logs": logs}
                await db.commit()
                await notify_public_callback(row)
                delete_job(api, name)
        cancelled = (await db.execute(select(SandboxRun).where(SandboxRun.status == "cancelled").limit(50))).scalars().all()
        for row in cancelled:
            if not (row.output_json or {}).get("job_cleaned"):
                delete_job(api, job_name(row))
                row.output_json = {**(row.output_json or {}), "job_cleaned": True}
                await db.commit()
                await notify_public_callback(row)


async def main() -> None:
    load_cluster_config()
    api = client.BatchV1Api()
    core_api = client.CoreV1Api()
    while True:
        try:
            await reconcile_once(api, core_api)
        except Exception:
            logger.exception("sandbox reconciliation failed")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
