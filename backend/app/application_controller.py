"""Reconcile application image builds and long-running hosted deployments."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from sqlalchemy import select

from .config import get_settings
from .db import AdminSessionLocal
from .models import ApplicationBuild, ApplicationDeployment


logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_cluster_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _job_logs(core: client.CoreV1Api, build_id: str) -> str:
    namespace = get_settings().application_runtime_namespace
    pods = core.list_namespaced_pod(namespace, label_selector=f"ai.platform/build-id={build_id}", limit=3)
    output: list[str] = []
    for pod in pods.items:
        try:
            output.append(core.read_namespaced_pod_log(pod.metadata.name, namespace, tail_lines=500, timestamps=True)[:131072])
        except ApiException as exc:
            logger.warning("application build log read failed: %s", exc.status)
    return "\n".join(output)[:131072]


def _apply_service(api: client.CoreV1Api, manifest: dict) -> None:
    namespace, name = manifest["metadata"]["namespace"], manifest["metadata"]["name"]
    try:
        api.patch_namespaced_service(name, namespace, manifest)
    except ApiException as exc:
        if exc.status != 404:
            raise
        api.create_namespaced_service(namespace, manifest)


def _apply_deployment(api: client.AppsV1Api, manifest: dict) -> None:
    namespace, name = manifest["metadata"]["namespace"], manifest["metadata"]["name"]
    try:
        api.patch_namespaced_deployment(name, namespace, manifest)
    except ApiException as exc:
        if exc.status != 404:
            raise
        api.create_namespaced_deployment(namespace, manifest)


def _apply_ingress(api: client.NetworkingV1Api, manifest: dict) -> None:
    namespace, name = manifest["metadata"]["namespace"], manifest["metadata"]["name"]
    try:
        api.patch_namespaced_ingress(name, namespace, manifest)
    except ApiException as exc:
        if exc.status != 404:
            raise
        api.create_namespaced_ingress(namespace, manifest)


async def reconcile_once(
    batch: client.BatchV1Api,
    apps: client.AppsV1Api,
    core: client.CoreV1Api,
    networking: client.NetworkingV1Api,
) -> None:
    namespace = get_settings().application_runtime_namespace
    async with AdminSessionLocal() as db:
        queued_builds = (await db.execute(select(ApplicationBuild).where(ApplicationBuild.status == "queued").limit(10))).scalars().all()
        for row in queued_builds:
            try:
                batch.create_namespaced_job(namespace, row.manifest_json)
                row.status, row.started_at = "building", utcnow()
            except ApiException as exc:
                if exc.status == 409:
                    row.status, row.started_at = "building", row.started_at or utcnow()
                else:
                    row.status, row.error, row.finished_at = "failed", f"构建任务提交失败: {exc.reason}", utcnow()
            await db.commit()

        active_builds = (await db.execute(select(ApplicationBuild).where(ApplicationBuild.status == "building").limit(20))).scalars().all()
        for row in active_builds:
            name = str((row.manifest_json.get("metadata") or {}).get("name") or "")
            try:
                job = batch.read_namespaced_job_status(name, namespace)
            except ApiException as exc:
                if exc.status == 404:
                    row.status, row.error, row.finished_at = "failed", "Kubernetes 构建 Job 不存在", utcnow()
                    await db.commit()
                    continue
                raise
            if job.status.succeeded or job.status.failed:
                logs = _job_logs(core, row.id)
                row.status = "succeeded" if job.status.succeeded else "failed"
                row.error = "" if job.status.succeeded else "镜像构建失败"
                row.output_json = {"image": row.image, "logs": logs}
                row.finished_at = utcnow()
                await db.commit()

        queued_deployments = (await db.execute(select(ApplicationDeployment).where(ApplicationDeployment.status == "queued").limit(10))).scalars().all()
        for row in queued_deployments:
            try:
                _apply_deployment(apps, row.manifest_json["deployment"])
                _apply_service(core, row.manifest_json["service"])
                if row.manifest_json.get("ingress"):
                    _apply_ingress(networking, row.manifest_json["ingress"])
                row.status = "deploying"
                row.error = ""
            except Exception as exc:
                row.status, row.error = "failed", f"部署提交失败: {exc}"[:2000]
            await db.commit()

        deploying = (await db.execute(select(ApplicationDeployment).where(ApplicationDeployment.status == "deploying").limit(30))).scalars().all()
        for row in deploying:
            manifest = row.manifest_json.get("deployment") or {}
            name = str((manifest.get("metadata") or {}).get("name") or "")
            try:
                workload = apps.read_namespaced_deployment_status(name, namespace)
            except ApiException as exc:
                if exc.status == 404:
                    row.status, row.error = "failed", "应用 Deployment 不存在"
                    await db.commit()
                    continue
                raise
            desired = workload.spec.replicas or 0
            available = workload.status.available_replicas or 0
            if desired > 0 and available >= desired:
                previous = (await db.execute(select(ApplicationDeployment).where(ApplicationDeployment.application_id == row.application_id, ApplicationDeployment.environment == row.environment, ApplicationDeployment.status == "active", ApplicationDeployment.id != row.id))).scalars().all()
                for item in previous:
                    item.status = "superseded"
                row.status = "active"
                await db.commit()

        stopping = (await db.execute(select(ApplicationDeployment).where(ApplicationDeployment.status == "stopping").limit(20))).scalars().all()
        for row in stopping:
            manifest = row.manifest_json.get("deployment") or {}
            name = str((manifest.get("metadata") or {}).get("name") or "")
            try:
                apps.patch_namespaced_deployment_scale(name, namespace, {"spec": {"replicas": 0}})
                row.status = "stopped"
                row.error = ""
            except ApiException as exc:
                if exc.status == 404:
                    row.status = "stopped"
                else:
                    row.error = f"下线失败: {exc.reason}"[:2000]
            await db.commit()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_cluster_config()
    batch = client.BatchV1Api()
    apps = client.AppsV1Api()
    core = client.CoreV1Api()
    networking = client.NetworkingV1Api()
    while True:
        try:
            await reconcile_once(batch, apps, core, networking)
        except Exception:
            logger.exception("application runtime reconciliation failed")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
