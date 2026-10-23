from types import SimpleNamespace
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from fastapi import HTTPException

from app import main


class FakeResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return list(self.values)


class FakeDatabase:
    def __init__(self, migration_versions):
        self.migration_versions = migration_versions

    async def execute(self, statement):
        if "alembic_version" in str(statement):
            return FakeResult(self.migration_versions)
        return FakeResult(())


class HealthyRedis:
    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return cls()

    async def ping(self):
        return True

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_healthz_is_liveness_probe_without_database(monkeypatch):
    result = await main.healthz()

    assert result["ok"] is True


def test_readiness_head_matches_alembic_migrations():
    backend_root = Path(__file__).parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))

    assert ScriptDirectory.from_config(config).get_heads() == [main.EXPECTED_ALEMBIC_HEAD]


@pytest.mark.asyncio
async def test_readyz_requires_current_migration_head_and_redis(monkeypatch):
    monkeypatch.setattr(main, "Redis", HealthyRedis)
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(redis_url="redis://test/0"))

    result = await main.readyz(FakeDatabase([main.EXPECTED_ALEMBIC_HEAD]))

    assert result["ok"] is True
    assert result["dependencies"]["migrations"] == main.EXPECTED_ALEMBIC_HEAD


@pytest.mark.asyncio
async def test_readyz_returns_503_when_schema_is_not_at_head(monkeypatch):
    monkeypatch.setattr(main, "Redis", HealthyRedis)

    with pytest.raises(HTTPException) as exc:
        await main.readyz(FakeDatabase(["older_revision"]))

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "postgres_not_ready"


@pytest.mark.asyncio
async def test_readyz_returns_503_when_redis_is_unavailable(monkeypatch):
    class BrokenRedis(HealthyRedis):
        async def ping(self):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(main, "Redis", BrokenRedis)
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(redis_url="redis://test/0"))

    with pytest.raises(HTTPException) as exc:
        await main.readyz(FakeDatabase([main.EXPECTED_ALEMBIC_HEAD]))

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "redis_not_ready"
