from pathlib import Path

import pytest
from fastapi import HTTPException

from app.config import Settings, validate_runtime_settings
from app.main import bind_database_parameters, finops_costs, validate_extension_manifest, validate_knowledge_asset


def test_kubernetes_secret_example_documents_production_guard_inputs():
    example = (Path(__file__).parents[2] / "deploy" / "k8s" / "secrets.example.yaml").read_text(encoding="utf-8")
    for field in (
        "APP_ENV",
        "APP_SECRET_KEY",
        "BOOTSTRAP_ADMIN_PASSWORD",
        "TRUSTED_HOSTS",
        "APPLICATION_BUILDKIT_IMAGE",
        "SANDBOX_NODE_IMAGE",
        "SANDBOX_PYTHON_IMAGE",
        "SANDBOX_GO_IMAGE",
        "SANDBOX_JAVA_IMAGE",
    ):
        assert f"{field}:" in example
    assert "@sha256:replace-with-64-hex-digest" in example


def test_backup_delivery_contract_is_wired_to_kubernetes_secret():
    cronjob = (Path(__file__).parents[2] / "deploy" / "k8s" / "backup-cronjob.yaml").read_text(encoding="utf-8")
    assert "BACKUP_S3_URI" in cronjob
    assert "optional: true" in cronjob
    assert "DR_BACKUP_IMAGE" in (Path(__file__).parents[2] / "deploy" / "backup" / "dr-test.sh").read_text(encoding="utf-8")


def test_production_defaults_fail_fast_and_safe_settings_pass():
    with pytest.raises(RuntimeError, match="APP_SECRET_KEY"):
        validate_runtime_settings(Settings(app_env="production"))
    validate_runtime_settings(Settings(app_env="test"))


def test_production_requires_immutable_runtime_images():
    settings = Settings(
        app_env="production",
        app_secret_key="a-real-secret",
        bootstrap_admin_password="a-real-password",
        database_url="postgresql+asyncpg://platform:password@db/platform",
        database_admin_url="postgresql+asyncpg://platform:password@db/platform",
        trusted_hosts="platform.example.com",
    )
    with pytest.raises(RuntimeError, match="SANDBOX_NODE_IMAGE"):
        validate_runtime_settings(settings)
    digest = "registry.example/image@sha256:" + "a" * 64
    settings.application_buildkit_image = digest
    settings.sandbox_node_image = digest
    settings.sandbox_python_image = digest
    settings.sandbox_go_image = digest
    settings.sandbox_java_image = digest
    validate_runtime_settings(settings)


def test_extension_manifest_rejects_capability_outside_allowlist():
    with pytest.raises(HTTPException) as exc:
        validate_extension_manifest({"capabilities": ["shell.exec"]})
    assert exc.value.status_code == 422


def test_knowledge_asset_requires_typed_content():
    with pytest.raises(HTTPException) as exc:
        validate_knowledge_asset("qa", {"question": "only question"})
    assert exc.value.status_code == 422


def test_knowledge_asset_accepts_graph_shape():
    validate_knowledge_asset("graph", {"nodes": [], "edges": []})


def test_database_parameters_are_bound_for_each_driver_style():
    sql, params = bind_database_parameters("SELECT * FROM orders WHERE id = :order_id", "postgresql", {"order_id": 7})
    assert sql.endswith("id = $1")
    assert params == (7,)
    sql, params = bind_database_parameters("SELECT * FROM orders WHERE id = :order_id", "oracle", {"order_id": 7})
    assert sql.endswith("id = :order_id")
    assert params == {"order_id": 7}


def test_finops_costs_are_calculated_from_usage_and_pricing():
    class Usage:
        tokens = 2000
        cpu_milliseconds = 3000
        gpu_seconds = 4

    costs = finops_costs(Usage(), {"token_price_per_1k": 0.1, "cpu_price_per_second": 0.2, "gpu_price_per_second": 0.5})
    assert costs == {"tokens": 0.2, "gpu": 2.0, "cpu": 0.6, "total": 2.8}
