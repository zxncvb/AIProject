import pytest
from pydantic import ValidationError

from app.schemas import MemberCreate
from app.services.application_runtime import build_application_manifests, build_buildkit_manifest, validate_build_source
from app.services.content_security import inspect_dlp, inspect_upload, validate_file_signature
from app.services.publication import channel_payload, signed_headers


def test_upload_security_rejects_executable_content_and_detects_dlp():
    with pytest.raises(ValueError, match="可执行程序"):
        validate_file_signature("report.pdf", b"MZ-not-a-document")
    findings = inspect_dlp("联系人 13800138000，api_key=abcdefghijklmnop")
    assert {item["category"] for item in findings} == {"mobile_cn", "access_token"}


@pytest.mark.asyncio
async def test_upload_security_blocks_eicar_fragment():
    with pytest.raises(ValueError, match="安全扫描未通过"):
        await inspect_upload("scan.txt", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE")


def test_full_code_build_and_runtime_manifests_are_hardened():
    source = validate_build_source({"git_url": "https://github.com/example/app.git", "git_ref": "main", "context": "."})
    build = build_buildkit_manifest("build-123", source, "registry.example/app:v1")
    pod = build["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["containers"][0]["securityContext"]["capabilities"]["drop"] == ["ALL"]
    manifests = build_application_manifests("deploy-123", "customer-service", "registry.example/app:v1", 2, 8080, "/healthz", {"APP_ENV": "production"}, {"API_KEY": "app-secrets/api-key"})
    runtime_pod = manifests["deployment"]["spec"]["template"]["spec"]
    container = runtime_pod["containers"][0]
    assert runtime_pod["automountServiceAccountToken"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert any(item["name"] == "API_KEY" and "valueFrom" in item for item in container["env"])


def test_publication_payload_and_signature_are_channel_compatible():
    event = {"resource_type": "agent", "version": 3, "resource_id": "agent-1"}
    assert channel_payload("dingtalk", event)["msgtype"] == "text"
    assert channel_payload("feishu", event)["msg_type"] == "text"
    first = signed_headers(event, "secret", "1700000000")
    second = signed_headers(event, "secret", "1700000000")
    assert first == second
    assert first["X-AI-Signature"].startswith("sha256=")


def test_build_source_blocks_non_https_and_path_traversal():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_build_source({"git_url": "ssh://git@example/app.git"})
    with pytest.raises(ValueError, match="无效"):
        validate_build_source({"git_url": "https://github.com/example/app.git", "dockerfile": "../Dockerfile"})


def test_member_name_rejects_corrupted_client_text():
    with pytest.raises(ValidationError, match="乱码"):
        MemberCreate(email="user@example.com", password="long-password-123", display_name="SCIM ???", role="viewer")
