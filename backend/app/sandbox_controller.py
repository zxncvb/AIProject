"""Kubernetes controller for submitted full-code sandbox jobs.

Run this as a separate service in a cluster. The API/worker only creates a
restricted Job manifest; this controller is the component allowed to submit
and observe Jobs in Kubernetes.
"""
import asyncio
import os
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from sqlalchemy import select

from .db import AdminSessionLocal
from .models import SandboxRun


NAMESPACE = os.getenv("SANDBOX_NAMESPACE", "ai-platform")


def load_cluster_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


async def reconcile_once(api: client.BatchV1Api) -> None:
    async with AdminSessionLocal() as db:
        submitted = (await db.execute(select(SandboxRun).where(SandboxRun.status == "submitted").limit(20))).scalars().all()
        for row in submitted:
            try:
                api.create_namespaced_job(namespace=NAMESPACE, body=row.manifest_json)
                row.status = "running"
                await db.commit()
            except ApiException as exc:
                if exc.status == 409:
                    row.status = "running"
                    await db.commit()
                else:
                    row.status, row.error = "failed", f"kubernetes submit failed: {exc.reason}"
                    await db.commit()
        active = (await db.execute(select(SandboxRun).where(SandboxRun.status == "running").limit(50))).scalars().all()
        for row in active:
            job_name = (row.manifest_json.get("metadata") or {}).get("name")
            if not job_name:
                continue
            job = api.read_namespaced_job_status(job_name, NAMESPACE)
            status = job.status
            if status.succeeded:
                row.status, row.finished_at = "succeeded", row.finished_at or datetime.now(timezone.utc)
                row.output_json = {"job_name": job_name, "succeeded": True}
                await db.commit()
            elif status.failed:
                row.status, row.error = "failed", f"sandbox job failed: {status.failed}"
                await db.commit()


async def main() -> None:
    load_cluster_config()
    api = client.BatchV1Api()
    while True:
        try:
            await reconcile_once(api)
        except Exception:
            pass
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
