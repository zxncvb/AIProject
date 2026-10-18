from typing import Any


RUNTIME_IMAGES = {
    "nodejs": "node:22-bookworm-slim",
    "python": "python:3.12-slim",
    "go": "golang:1.23-bookworm",
    "java": "eclipse-temurin:21-jre",
}


def build_job_manifest(run_id: str, runtime: str, source: dict[str, Any], timeout_seconds: int, cpu_millicores: int, memory_mb: int) -> dict[str, Any]:
    if runtime not in RUNTIME_IMAGES:
        raise ValueError("unsupported sandbox runtime")
    command = source.get("command") or ["sh", "-c", "echo sandbox runtime; sleep 1"]
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        raise ValueError("source.command must be a non-empty string array")
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
                "spec": {
                    "automountServiceAccountToken": False,
                    "restartPolicy": "Never",
                    "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [{
                        "name": "runner", "image": RUNTIME_IMAGES[runtime], "command": command,
                        "resources": {"requests": {"cpu": f"{cpu_millicores}m", "memory": f"{memory_mb}Mi"}, "limits": {"cpu": f"{cpu_millicores}m", "memory": f"{memory_mb}Mi"}},
                        "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                        "env": [{"name": "AI_SANDBOX_RUN_ID", "value": run_id}],
                    }],
                },
            },
        },
    }
