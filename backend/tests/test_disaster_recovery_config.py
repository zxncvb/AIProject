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
