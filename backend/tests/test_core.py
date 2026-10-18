from app.services.crypto import chunk_text
from app.services.identity import claim_values, mapped_role, parse_role_mapping
from app.services.workflow import ordered_nodes, resolve


def test_resolve_exact_and_embedded_templates():
    context = {"input": {"question": "你好"}, "nodes": {"answer": {"text": "完成"}}}
    assert resolve("{{input.question}}", context) == "你好"
    assert resolve("结果：{{nodes.answer.text}}", context) == "结果：完成"


def test_ordered_nodes_rejects_cycle():
    graph = {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]}
    try:
        ordered_nodes(graph)
    except ValueError as exc:
        assert "环" in str(exc)
    else:
        raise AssertionError("cycle should be rejected")


def test_chunk_text_has_overlap_and_clean_content():
    chunks = chunk_text("第一行\n\n第二行", size=5, overlap=1)
    assert chunks
    assert all("\n\n" not in item for item in chunks)


def test_oidc_group_mapping_supports_json_and_space_delimited_claims():
    mapping = parse_role_mapping('{"ai-admin": "admin", "ai-dev": "developer"}')
    claims = {"groups": ["engineering", "ai-dev"], "roles": "reader"}
    assert claim_values(claims, "roles") == ["reader"]
    assert mapped_role(claims, "groups", "roles", mapping, "viewer") == "developer"


def test_oidc_group_mapping_supports_env_pairs_and_default():
    mapping = parse_role_mapping("ai-admin=admin,ai-ops=operator")
    assert mapped_role({"groups": ["unknown"]}, "groups", "roles", mapping, "viewer") == "viewer"
    assert mapped_role({"groups": ["ai-admin"]}, "groups", "roles", mapping, "viewer") == "admin"

