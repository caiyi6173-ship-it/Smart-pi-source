from dataclasses import dataclass

from app.retrieval.text import normalize_text


MODERN_BASICS_INTENT_TERMS = (
    "是什么",
    "什么意思",
    "基础",
    "科普",
    "入门",
    "怎么理解",
    "阴阳",
    "五行",
    "气血",
    "津液",
    "脏腑",
    "四诊",
    "望闻问切",
    "体质",
    "经络",
    "腧穴",
    "穴位",
    "药食同源",
    "食疗",
    "食养",
    "养生",
    "情志",
    "起居",
    "八段锦",
    "太极拳",
)

MODERN_EXPLAINER_TERMS = (
    "是什么",
    "什么意思",
    "怎么理解",
    "科普",
    "入门",
    "基础",
)

SAFETY_INTENT_TERMS = (
    "安全吗",
    "能不能",
    "禁忌",
    "副作用",
    "不良反应",
    "用药",
    "孕妇",
    "儿童",
    "老人",
    "老年",
    "慢病",
    "急症",
    "就医",
    "危险",
    "胸痛",
    "呼吸困难",
    "高热",
)

CLASSIC_BOOK_TERMS = (
    "黄帝内经",
    "素问",
    "灵枢",
    "伤寒论",
    "金匮要略",
    "神农本草经",
    "本草经",
    "八十一难经",
    "难经",
    "温病条辨",
    "脾胃论",
    "丹溪心法",
    "濒湖脉学",
    "望诊遵经",
    "临症验舌法",
    "察舌辨症新法",
)

CLASSIC_STRUCTURE_TERMS = (
    "原文",
    "条文",
    "篇",
    "卷",
    "章",
    "节",
    "记载",
    "记曰",
    "所云",
    "出自",
    "载于",
)

CLASSIC_TOPIC_TERMS = (
    "太阳病",
    "阳明病",
    "少阳病",
    "太阴病",
    "少阴病",
    "厥阴病",
    "辨太阳病",
    "辨阳明病",
    "辨少阳病",
    "辨太阴病",
    "辨少阴病",
    "辨厥阴病",
)

CLASSIC_SUFFIX_TERMS = ("经", "论", "方论", "要略", "本草", "条辨", "脉学")


@dataclass(frozen=True)
class RouteProfile:
    label: str = "general"
    hard_source_type: str | None = None
    supplemental_source_types: tuple[str, ...] = ()
    rerank_source_boosts: tuple[tuple[str, float], ...] = ()
    rerank_preferred_source_types: tuple[str, ...] = ()
    rerank_penalized_source_types: tuple[str, ...] = ()


def build_route_profile(question: str, filters: dict | None = None) -> RouteProfile:
    filters = filters or {}
    if _has_explicit_source_filter(filters.get("source_type")):
        return RouteProfile(label="explicit_filter")

    normalized = normalize_text(question)
    classic_book_intent = any(term in normalized for term in CLASSIC_BOOK_TERMS)
    classic_topic_intent = any(term in normalized for term in CLASSIC_TOPIC_TERMS)
    classic_structure_intent = any(term in normalized for term in CLASSIC_STRUCTURE_TERMS)
    classic_suffix_intent = any(term in normalized for term in CLASSIC_SUFFIX_TERMS)
    classic_quote_intent = classic_structure_intent and (classic_suffix_intent or classic_topic_intent)
    safety_intent = any(term in normalized for term in SAFETY_INTENT_TERMS)
    modern_intent = any(term in normalized for term in MODERN_BASICS_INTENT_TERMS)
    modern_explainer_intent = any(term in normalized for term in MODERN_EXPLAINER_TERMS)

    if classic_book_intent or classic_quote_intent:
        return RouteProfile(
            label="classic_text_primary",
            hard_source_type="classic_text",
            rerank_source_boosts=(
                ("classic_text", 1.0),
                ("modern_basics", -0.35),
                ("safety_rule", -0.25),
            ),
            rerank_preferred_source_types=("classic_text",),
            rerank_penalized_source_types=("modern_basics", "safety_rule"),
        )

    if classic_topic_intent and modern_explainer_intent:
        return RouteProfile(
            label="modern_basics_with_classic_support",
            supplemental_source_types=("modern_basics", "classic_text"),
            rerank_source_boosts=(
                ("modern_basics", 1.0),
                ("classic_text", 0.35),
                ("safety_rule", -0.2),
            ),
            rerank_preferred_source_types=("modern_basics", "classic_text"),
            rerank_penalized_source_types=("safety_rule",),
        )

    if classic_topic_intent:
        return RouteProfile(
            label="classic_text_primary",
            hard_source_type="classic_text",
            rerank_source_boosts=(
                ("classic_text", 1.0),
                ("modern_basics", -0.2),
            ),
            rerank_preferred_source_types=("classic_text",),
            rerank_penalized_source_types=("modern_basics",),
        )

    if safety_intent:
        return RouteProfile(
            label="safety_primary",
            supplemental_source_types=("safety_rule", "modern_basics"),
            rerank_source_boosts=(
                ("safety_rule", 1.0),
                ("modern_basics", 0.6),
                ("classic_text", -0.35),
            ),
            rerank_preferred_source_types=("safety_rule", "modern_basics"),
            rerank_penalized_source_types=("classic_text",),
        )

    if modern_intent:
        return RouteProfile(
            label="modern_basics_primary",
            supplemental_source_types=("modern_basics",),
            rerank_source_boosts=(
                ("modern_basics", 1.0),
                ("classic_text", -0.25),
            ),
            rerank_preferred_source_types=("modern_basics",),
            rerank_penalized_source_types=("classic_text",),
        )

    return RouteProfile()


def route_metadata_boost(question: str, source_type: str) -> float:
    profile = build_route_profile(question)
    boost_map = dict(profile.rerank_source_boosts)
    if source_type in boost_map:
        return boost_map[source_type]
    if source_type in profile.rerank_preferred_source_types:
        return 1.0
    if source_type in profile.rerank_penalized_source_types:
        return -0.35
    return 0.0


def _is_classic_text_intent(normalized_question: str) -> bool:
    classic_book_intent = any(term in normalized_question for term in CLASSIC_BOOK_TERMS)
    classic_topic_intent = any(term in normalized_question for term in CLASSIC_TOPIC_TERMS)
    classic_structure_intent = any(term in normalized_question for term in CLASSIC_STRUCTURE_TERMS)
    classic_suffix_intent = any(term in normalized_question for term in CLASSIC_SUFFIX_TERMS)
    modern_explainer_intent = any(term in normalized_question for term in MODERN_EXPLAINER_TERMS)

    if classic_book_intent:
        return True
    if classic_structure_intent and (classic_suffix_intent or classic_topic_intent):
        return True
    if classic_topic_intent and not modern_explainer_intent:
        return True
    return False


def _has_explicit_source_filter(source_type: object) -> bool:
    if source_type is None:
        return False
    if isinstance(source_type, str):
        return bool(source_type.strip())
    if isinstance(source_type, (list, tuple, set)):
        return any(isinstance(item, str) and item.strip() for item in source_type)
    return True
