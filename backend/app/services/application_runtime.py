"""Kubernetes build and hosting manifests for full-code applications."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ..config import get_settings


DNS_LABEL = re.compile(r"[^a-z0-9-]+")
HOSTNAME = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
SECRET_NAME = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")


def resource_name(prefix: str, identifier: str) -> str:
    value = DNS_LABEL.sub("-", f"{prefix}-{identifier}".lower()).strip("-")
    return value[:63].rstrip("-")


def validate_application_domain(domain: str, tls_secret_name: str = "") -> tuple[str, str]:
    """Validate a customer hostname and its Kubernetes TLS secret name."""
    normalized = domain.strip().lower().rstrip(".")
    if normalized and not HOSTNAME.fullmatch(normalized):
        raise ValueError("custom_domain 必须是完整的 DNS 域名")
    secret = tls_secret_name.strip()
    if normalized and not secret:
        raise ValueError("配置 custom_domain 时必须同时提供 tls_secret_name")
    if secret and not SECRET_NAME.fullmatch(secret):
        raise ValueError("tls_secret_name 不是有效的 Kubernetes Secret 名称")
    return normalized, secret


def validate_build_source(source: dict[str, Any]) -> dict[str, str]:
    git_url = str(source.get("git_url") or "").strip()
    parsed = urlparse(git_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("全代码构建要求 source.git_url 为 HTTPS Git 仓库")
    git_ref = str(source.get("git_ref") or "main").strip()
    dockerfile = str(source.get("dockerfile") or "Dockerfile").strip()
    context = str(source.get("context") or ".").strip()
    for label, value in {"git_ref": git_ref, "dockerfile": dockerfile, "context": context}.items():
        if not value or ".." in value or any(char in value for char in "\r\n\0"):
            raise ValueError(f"source.{label} 无效")
    return {"git_url": git_url, "git_ref": git_ref, "dockerfile": dockerfile, "context": context}


def build_image_name(app_slug: str, version: int, build_id: str, requested: str | None = None) -> str:
    if requested:
        image = requested.strip()
    else:
        registry = get_settings().application_registry.rstrip("/")
        if not registry:
            raise ValueError("未配置 APPLICATION_REGISTRY，无法推送构建镜像")
        image = f"{registry}/{app_slug}:v{version}-{build_id[:8]}"
    if len(image) > 500 or any(char.isspace() for char in image) or image.startswith(("http://", "https://")):
        raise ValueError("镜像地址无效")
    return image


def build_buildkit_manifest(build_id: str, source: dict[str, Any], image: str) -> dict[str, Any]:
    settings = get_settings()
    build = validate_build_source(source)
    name = resource_name("ai-build", build_id[:20])
    git_context = f"{build['git_url']}#{build['git_ref']}:{build['context']}"
    args = [
        "buildctl-daemonless.sh", "build",
        "--frontend", "dockerfile.v0",
        "--opt", f"context={git_context}",
        "--opt", f"filename={build['dockerfile']}",
        "--output", f"type=image,name={image},push=true",
    ]
    pod_spec: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "restartPolicy": "Never",
        "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [{
            "name": "buildkit",
            "image": settings.application_buildkit_image,
            "args": args,
            "env": [{"name": "BUILDKITD_FLAGS", "value": "--oci-worker-no-process-sandbox"}],
            "resources": {"requests": {"cpu": "500m", "memory": "1Gi"}, "limits": {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "10Gi"}},
            "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": False, "capabilities": {"drop": ["ALL"]}},
            "volumeMounts": [{"name": "buildkit-state", "mountPath": "/home/user/.local/share/buildkit"}, {"name": "registry-auth", "mountPath": "/home/user/.docker", "readOnly": True}],
        }],
        "volumes": [
            {"name": "buildkit-state", "emptyDir": {"sizeLimit": "10Gi"}},
            {"name": "registry-auth", "secret": {"secretName": "application-registry-auth", "optional": True}},
        ],
    }
    if settings.application_runtime_class:
        pod_spec["runtimeClassName"] = settings.application_runtime_class
    return {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": name, "namespace": settings.application_runtime_namespace, "labels": {"ai.platform/component": "application-build", "ai.platform/build-id": build_id}},
        "spec": {"backoffLimit": 1, "activeDeadlineSeconds": 1800, "ttlSecondsAfterFinished": 3600, "template": {"metadata": {"labels": {"ai.platform/component": "application-build", "ai.platform/build-id": build_id}}, "spec": pod_spec}},
    }


def build_application_manifests(
    deployment_id: str,
    app_slug: str,
    image: str,
    replicas: int,
    container_port: int,
    health_path: str,
    env: dict[str, str],
    secret_refs: dict[str, str],
    host: str | None = None,
    tls_secret_name: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    name = resource_name("ai-app", app_slug)
    labels = {"app.kubernetes.io/name": name, "ai.platform/component": "full-code-application", "ai.platform/deployment-id": deployment_id}
    env_items = [{"name": key, "value": value} for key, value in sorted(env.items()) if re.fullmatch(r"[A-Z_][A-Z0-9_]*", key)]
    for key, reference in sorted(secret_refs.items()):
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or "/" not in reference:
            raise ValueError("secret_refs 必须使用 ENV_NAME=secret-name/key 格式")
        secret_name, secret_key = reference.split("/", 1)
        env_items.append({"name": key, "valueFrom": {"secretKeyRef": {"name": secret_name, "key": secret_key}}})
    container: dict[str, Any] = {
        "name": "application", "image": image, "imagePullPolicy": "IfNotPresent",
        "ports": [{"name": "http", "containerPort": container_port}], "env": env_items,
        "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "1", "memory": "1Gi"}},
        "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "runAsNonRoot": True, "capabilities": {"drop": ["ALL"]}},
        "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
        "readinessProbe": {"httpGet": {"path": health_path, "port": "http"}, "initialDelaySeconds": 5, "periodSeconds": 10},
        "livenessProbe": {"httpGet": {"path": health_path, "port": "http"}, "initialDelaySeconds": 20, "periodSeconds": 20},
    }
    pod_spec: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [container], "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": "256Mi"}}],
    }
    if settings.application_runtime_class:
        pod_spec["runtimeClassName"] = settings.application_runtime_class
    deployment = {
        "apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name, "namespace": settings.application_runtime_namespace, "labels": labels},
        "spec": {"replicas": replicas, "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}}, "selector": {"matchLabels": {"app.kubernetes.io/name": name}}, "template": {"metadata": {"labels": labels}, "spec": pod_spec}},
    }
    service = {
        "apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "namespace": settings.application_runtime_namespace, "labels": labels},
        "spec": {"selector": {"app.kubernetes.io/name": name}, "ports": [{"name": "http", "port": 80, "targetPort": "http"}]},
    }
    manifests: dict[str, Any] = {"deployment": deployment, "service": service}
    ingress_host = (host or (f"{app_slug}.{settings.application_base_domain}" if settings.application_base_domain else "")).lower()
    if ingress_host:
        ingress_host, ingress_tls_secret = validate_application_domain(ingress_host, tls_secret_name or "application-wildcard-tls")
        manifests["ingress"] = {
            "apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": name, "namespace": settings.application_runtime_namespace, "annotations": {"nginx.ingress.kubernetes.io/proxy-body-size": "25m"}},
            "spec": {"tls": [{"hosts": [ingress_host], "secretName": ingress_tls_secret}], "rules": [{"host": ingress_host, "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {"service": {"name": name, "port": {"number": 80}}}}]}}]},
        }
    return manifests
