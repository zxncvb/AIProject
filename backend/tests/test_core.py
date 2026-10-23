from app.services.crypto import chunk_text
from app.services.evaluation import parse_judge_result
from app.services.identity import claim_values, mapped_role, parse_role_mapping
from app.services.knowledge import rerank_candidates
from app.services.rate_limit import allow_local, clear_local
from app.services.storage import object_key
from app.services.workflow import fair_order_messages, ordered_nodes, resolve


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


def test_rag_reranker_prefers_term_coverage_and_keeps_explanation():
    rows = rerank_candidates(
        [
            {"chunk_id": "a", "content": "设备轴承出现高频声音，需要检查润滑。", "score": 0.7},
            {"chunk_id": "b", "content": "设备运行维护手册。", "score": 0.9},
        ],
        "轴承 高频声音",
        2,
    )
    assert rows[0]["chunk_id"] == "a"
    assert rows[0]["rerank"]["term_coverage"] > 0


def test_worker_fair_order_round_robins_tenants_and_respects_priority():
    rows = fair_order_messages([
        ("1-0", {"tenant_id": "a", "priority": "5"}),
        ("2-0", {"tenant_id": "a", "priority": "1"}),
        ("3-0", {"tenant_id": "b", "priority": "1"}),
    ])
    assert [fields["tenant_id"] for _, fields in rows] == ["a", "b", "a"]
    assert rows[0][1]["priority"] == "1"


def test_storage_key_is_tenant_scoped_and_filename_safe():
    key = object_key("tenant-1", "abc123", "../../secret report.pdf")
    assert key == "tenants/tenant-1/documents/abc123/secret_report.pdf"
    assert ".." not in key


def test_judge_parser_accepts_json_wrapped_in_model_text():
    result = parse_judge_result('```json\n{"score": 0.8, "passed": true, "reason": "充分"}\n```')
    assert result["score"] == 0.8
    assert result["passed"] is True


def test_local_rate_limit_fallback_blocks_after_limit():
    import asyncio

    clear_local()
    async def run():
        assert await allow_local("test-rate", 2, 60)
        assert await allow_local("test-rate", 2, 60)
        assert not await allow_local("test-rate", 2, 60)
    asyncio.run(run())
    clear_local()

