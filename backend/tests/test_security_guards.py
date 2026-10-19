import pytest
from fastapi import HTTPException

from app.main import validate_extension_manifest, validate_knowledge_asset


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
