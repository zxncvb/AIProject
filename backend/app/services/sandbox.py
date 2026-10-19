from typing import Any
import json

from ..config import get_settings


RUNTIME_IMAGES = {
    "nodejs": "node:22-bookworm-slim",
    "python": "python:3.12-slim",
    "go": "golang:1.23-bookworm",
    "java": "eclipse-temurin:21-jre",
}


def build_job_manifest(run_id: str, runtime: str, source: dict[str, Any], timeout_seconds: int, cpu_millicores: int, memory_mb: int) -> dict[str, Any]:
    if runtime not in RUNTIME_IMAGES:
        raise ValueError("unsupported sandbox runtime")
    command = source.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        raise ValueError("source.command must be a non-empty string array")
    if any(len(item) > 4096 for item in command):
        raise ValueError("source.command entry is too long")
    settings = get_settings()
    app_input = source.get("input")
    input_json = json.dumps(app_input, ensure_ascii=False, separators=(",", ":")) if app_input is not None else ""
    if len(input_json.encode("utf-8")) > 16384:
        raise ValueError("sandbox input exceeds 16 KiB")
    runtime_class = settings.sandbox_runtime_class.strip()
    if runtime_class and not all(part.isalnum() or part in "-." for part in runtime_class):
        raise ValueError("invalid sandbox runtime class")
    pod_spec: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "restartPolicy": "Never",
        "securityContext": {"runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532, "seccompProfile": {"type": "RuntimeDefault"}},
        "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": f"{max(64, min(settings.sandbox_ephemeral_storage_mb, 1024))}Mi"}}],
        "containers": [{
            "name": "runner", "image": RUNTIME_IMAGES[runtime], "command": command,
            "resources": {
                "requests": {"cpu": f"{cpu_millicores}m", "memory": f"{memory_mb}Mi"},
                "limits": {"cpu": f"{cpu_millicores}m", "memory": f"{memory_mb}Mi", "ephemeral-storage": f"{max(64, min(settings.sandbox_ephemeral_storage_mb, 1024))}Mi"},
            },
            "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
            "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
            "env": [{"name": "AI_SANDBOX_RUN_ID", "value": run_id}, {"name": "TMPDIR", "value": "/tmp"}],
        }],
    }
    if runtime_class:
        pod_spec["runtimeClassName"] = runtime_class
    if input_json:
        pod_spec["containers"][0]["env"].append({"name": "AI_APP_INPUT", "value": input_json})
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": f"ai-sandbox-{run_id[:20]}", "labels": {"ai.platform/sandbox": "true", "ai.platform/run-id": run_id}},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": timeout_seconds,
            "ttlSecondsAfterFinished": 3600,
            "template": {
                "metadata": {"labels": {"ai.platform/sandbox": "true", "ai.platform/run-id": run_id}},
                "spec": pod_spec,
            },
        },
    }
