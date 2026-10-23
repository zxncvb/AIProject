import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_pitr_override_enables_wal_archiving():
    text = (ROOT / "docker-compose.pitr.yml").read_text(encoding="utf-8")

    assert "wal_level=replica" in text
    assert "archive_mode=on" in text
    assert "archive_timeout=60s" in text
    assert "archive_command=/usr/local/bin/wal-archive.sh" in text
    assert "platform-postgres-wal" in text


def test_wal_archive_command_rejects_path_traversal_and_supports_durable_targets():
    text = (ROOT / "deploy" / "backup" / "wal-archive.sh").read_text(encoding="utf-8")

    assert "s3://" in text
    assert "file://" in text
    assert "unsafe WAL file name" in text
    assert "command -v aws" in text


def test_cloudnativepg_example_declares_object_store_wal_archive():
    text = (ROOT / "deploy" / "k8s" / "stateful-ha.example.yaml").read_text(encoding="utf-8")

    assert "barmanObjectStore:" in text
    assert "destinationPath: s3://REPLACE_WITH_DURABLE_BUCKET/" in text
    assert "wal:" in text
    assert "compression: gzip" in text


def test_pitr_smoke_test_switches_wal_and_checks_archiver_progress():
    text = (ROOT / "deploy" / "ci" / "pitr-smoke.sh").read_text(encoding="utf-8")

    assert "docker-compose.pitr.yml" in text
    assert "pg_switch_wal" in text
    assert "pg_stat_archiver" in text
    assert "archived_count > 0" in text
    assert "down -v --remove-orphans" in text


def test_alembic_migrations_have_one_deployable_head():
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in (ROOT / "backend" / "migrations" / "versions").glob("*.py"):
        values: dict[str, object] = {}
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.Assign) or not node.targets:
                continue
            name = getattr(node.targets[0], "id", "")
            if name not in {"revision", "down_revision"}:
                continue
            if isinstance(node.value, ast.Constant):
                values[name] = node.value.value
            elif isinstance(node.value, (ast.Tuple, ast.List)):
                values[name] = tuple(item.value for item in node.value.elts if isinstance(item, ast.Constant))
        revision = str(values["revision"])
        revisions.add(revision)
        parent = values.get("down_revision")
        parents.update(parent if isinstance(parent, tuple) else ({parent} if parent else set()))

    assert revisions - parents == {"20261024_email_verification"}


def test_audit_events_are_append_only_after_hash_chain_migration():
    text = (ROOT / "backend" / "migrations" / "versions" / "20261023_audit_append_only.py").read_text(encoding="utf-8")

    assert "BEFORE UPDATE OR DELETE ON audit_events" in text
    assert "audit_events is append-only" in text
    assert "reject_audit_event_mutation" in text
