from pathlib import Path

import pytest
from fastapi import HTTPException

from app.config import Settings, validate_runtime_settings
from app import main
from app.main import bind_database_parameters, finops_costs, validate_extension_manifest, validate_knowledge_asset
from app.services import startup_guard


def test_kubernetes_secret_example_documents_production_guard_inputs():
    example = (Path(__file__).parents[2] / "deploy" / "k8s" / "secrets.example.yaml").read_text(encoding="utf-8")
    for field in (
        "APP_ENV",
        "APP_SECRET_KEY",
        "CONTROLLER_DATABASE_URL",
        "BOOTSTRAP_ADMIN_PASSWORD",
        "TRUSTED_HOSTS",
        "ALLOWED_HTTP_HOSTS",
        "PUBLICATION_SIGNING_SECRET",
        "APPLICATION_BUILDKIT_IMAGE",
        "SANDBOX_NODE_IMAGE",
        "SANDBOX_PYTHON_IMAGE",
        "SANDBOX_GO_IMAGE",
        "SANDBOX_JAVA_IMAGE",
    ):
        assert f"{field}:" in example
    assert "@sha256:replace-with-64-hex-digest" in example


def test_all_production_process_entrypoints_use_shared_startup_guard():
    root = Path(__file__).parents[1] / "app"
    for filename in ("main.py", "worker.py", "application_controller.py", "sandbox_controller.py"):
        source = (root / filename).read_text(encoding="utf-8")
        assert "validate_startup" in source or "validate_controller_startup" in source


def test_backup_delivery_contract_is_wired_to_kubernetes_secret():
    cronjob = (Path(__file__).parents[2] / "deploy" / "k8s" / "backup-cronjob.yaml").read_text(encoding="utf-8")
    assert "BACKUP_S3_URI" in cronjob
    assert "optional: true" in cronjob
    assert "DR_BACKUP_IMAGE" in (Path(__file__).parents[2] / "deploy" / "backup" / "dr-test.sh").read_text(encoding="utf-8")


def test_controller_database_identity_is_separate_from_migration_owner():
    provision = (Path(__file__).parents[2] / "deploy" / "postgres" / "provision-runtime.sh").read_text(encoding="utf-8")
    compose = (Path(__file__).parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    assert "platform_controller" in provision
    assert "BYPASSRLS" in provision
    assert "CONTROLLER_DATABASE_URL" in compose
    assert "POSTGRES_CONTROLLER_PASSWORD" in compose


def test_public_callback_outbox_has_operational_metrics_and_alerts():
    source = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    rules = (Path(__file__).parents[2] / "deploy" / "observability" / "rules" / "public-callback.yml").read_text(encoding="utf-8")
    assert "public_callback_pending" in source
    assert "public_callback_failed" in source
    assert "EnterpriseAIPublicCallbackBacklog" in rules
    assert "EnterpriseAIPublicCallbackFailed" in rules


def test_production_defaults_fail_fast_and_safe_settings_pass():
    with pytest.raises(RuntimeError, match="APP_SECRET_KEY"):
        validate_runtime_settings(Settings(
            app_env="production",
            app_secret_key="change-me-in-production",
            bootstrap_admin_password="ChangeMe_123456",
            database_url="sqlite+aiosqlite:///./data/platform.db",
            trusted_hosts="*",
        ))
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


@pytest.mark.asyncio
async def test_production_runtime_database_role_rejects_superuser(monkeypatch):
    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def scalar(self, _statement):
            return True

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(startup_guard, "engine", Engine())
    monkeypatch.setattr(startup_guard, "get_settings", lambda: Settings(app_env="production"))
    with pytest.raises(RuntimeError, match="must not be a PostgreSQL superuser"):
        await startup_guard.validate_database_runtime_role()


@pytest.mark.asyncio
async def test_production_controller_role_requires_non_superuser_bypassrls(monkeypatch):
    class Result:
        def first(self):
            return (False, True)

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _statement):
            return Result()

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(startup_guard, "controller_engine", Engine())
    monkeypatch.setattr(startup_guard, "get_settings", lambda: Settings(
        app_env="production",
        controller_database_url="postgresql+asyncpg://platform_controller:secret@db/platform",
    ))

    await startup_guard.validate_database_controller_role()

    class SuperuserResult:
        def first(self):
            return (True, True)

    class SuperuserConnection(Connection):
        async def execute(self, _statement):
            return SuperuserResult()

    class SuperuserEngine:
        def connect(self):
            return SuperuserConnection()

    monkeypatch.setattr(startup_guard, "controller_engine", SuperuserEngine())
    with pytest.raises(RuntimeError, match="controller database role must not be a PostgreSQL superuser"):
        await startup_guard.validate_database_controller_role()
