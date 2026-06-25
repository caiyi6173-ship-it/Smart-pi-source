from app.retrieval.hybrid import local_rerank
from app.retrieval.routing import build_route_profile
from app.schemas import Chunk


def test_classic_query_routes_to_classic_text():
    profile = build_route_profile("伤寒论中太阳病是什么")

    assert profile.label == "classic_text_primary"
    assert profile.hard_source_type == "classic_text"


def test_modern_query_routes_to_modern_basics():
    profile = build_route_profile("阴阳是什么意思")

    assert profile.label == "modern_basics_primary"
    assert profile.supplemental_source_types == ("modern_basics",)


def test_safety_query_routes_to_safety_and_modern():
    profile = build_route_profile("孕妇能不能用药食同源")

    assert profile.label == "safety_primary"
    assert profile.supplemental_source_types == ("safety_rule", "modern_basics")


def test_classic_topic_explainer_routes_to_modern_with_classic_support():
    profile = build_route_profile("太阳病是什么意思")

    assert profile.label == "modern_basics_with_classic_support"
    assert profile.supplemental_source_types == ("modern_basics", "classic_text")


def test_explicit_source_filter_bypasses_auto_routing():
    profile = build_route_profile("阴阳是什么意思", {"source_type": "classic_text"})

    assert profile.label == "explicit_filter"


def test_local_rerank_prefers_classic_source_for_classic_query():
    modern_chunk = Chunk(
        id="modern",
        document_id="modern-doc",
        text="太阳病是中医里常见的古典病机概念。",
        score=0.8,
        lexical_score=0.8,
        metadata={"source_type": "modern_basics", "title": "中医基础科普"},
    )
    classic_chunk = Chunk(
        id="classic",
        document_id="classic-doc",
        text="太阳病，发热汗出，恶风，脉缓者，名为中风。",
        score=0.8,
        lexical_score=0.8,
        metadata={"source_type": "classic_text", "title": "伤寒论"},
    )

    ranked = local_rerank("伤寒论中太阳病是什么", [modern_chunk, classic_chunk], top_k=2)

    assert ranked[0].id == "classic"


def test_local_rerank_prefers_exact_classic_book_title():
    other_classic = Chunk(
        id="other-classic",
        document_id="other-doc",
        text="伤寒一日，太阳受之。太阳主表，其证头项痛，腰脊强。",
        score=0.95,
        lexical_score=0.95,
        metadata={"source_type": "classic_text", "title": "望诊遵经"},
    )
    target_classic = Chunk(
        id="target-classic",
        document_id="target-doc",
        text="属性：1．太阳之为病，脉浮、头项强痛而恶寒。",
        score=0.92,
        lexical_score=0.92,
        metadata={"source_type": "classic_text", "title": "457-伤寒论"},
    )

    ranked = local_rerank("伤寒论中太阳病是什么？", [other_classic, target_classic], top_k=2)

    assert ranked[0].id == "target-classic"


def test_local_rerank_prefers_modern_source_for_explainer_query():
    modern_chunk = Chunk(
        id="modern",
        document_id="modern-doc",
        text="太阳病通常指外感初起、病位偏表的证候阶段，可先从概念上理解。",
        score=0.8,
        lexical_score=0.8,
        metadata={"source_type": "modern_basics", "title": "中医基础科普"},
    )
    classic_chunk = Chunk(
        id="classic",
        document_id="classic-doc",
        text="太阳病，发热汗出，恶风，脉缓者，名为中风。",
        score=0.8,
        lexical_score=0.8,
        metadata={"source_type": "classic_text", "title": "伤寒论"},
    )

    ranked = local_rerank("太阳病是什么意思", [classic_chunk, modern_chunk], top_k=2)

    assert ranked[0].id == "modern"
