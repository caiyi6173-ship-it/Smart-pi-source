import math
import re
from collections import Counter


TCM_SYNONYMS = {
    "舌苔黄腻": ["黄腻苔", "苔黄腻", "湿热", "痰热"],
    "齿痕舌": ["齿印舌", "脾虚", "湿盛"],
    "红舌": ["舌红", "热象", "阴虚内热", "实热"],
    "白苔": ["舌苔白", "寒湿", "表证"],
    "紫舌": ["舌紫", "血瘀", "瘀血"],
    "阴阳": ["阴阳平衡", "寒热", "虚实"],
    "五行": ["木火土金水", "生克制化"],
    "气血津液": ["气血", "津液", "精气血津液"],
    "脏腑": ["五脏六腑", "肝心脾肺肾"],
    "四诊": ["望闻问切", "望诊", "闻诊", "问诊", "切诊"],
    "体质": ["中医体质", "偏颇体质", "平和体质"],
    "经络": ["经脉", "络脉", "腧穴", "穴位"],
    "药食同源": ["食疗", "食养", "中药安全"],
    "养生": ["起居", "饮食", "情志", "运动"],
    "用药安全": ["中药安全", "不良反应", "配伍禁忌", "就医"],
}

TCM_PHRASES = (
    "中医药",
    "健康素养",
    "阴阳",
    "五行",
    "阴阳平衡",
    "气血",
    "津液",
    "气血津液",
    "脏腑",
    "五脏六腑",
    "四诊",
    "望闻问切",
    "望诊",
    "闻诊",
    "问诊",
    "切诊",
    "病因",
    "病机",
    "体质",
    "平和体质",
    "偏颇体质",
    "经络",
    "腧穴",
    "穴位",
    "药食同源",
    "食疗",
    "食养",
    "情志",
    "起居",
    "运动",
    "八段锦",
    "太极拳",
    "儿童",
    "孕产",
    "老年",
    "慢病",
    "用药安全",
    "不良反应",
    "就医",
    "急症",
)


def rewrite_queries(question: str) -> list[str]:
    normalized = normalize_text(question)
    queries = [question.strip()]
    for key, synonyms in TCM_SYNONYMS.items():
        if key in normalized:
            queries.extend(synonyms)
        for synonym in synonyms:
            if synonym in normalized:
                queries.append(key)
                queries.extend(item for item in synonyms if item != synonym)
    compact = []
    seen = set()
    for query in queries:
        value = query.strip()
        if value and value not in seen:
            compact.append(value)
            seen.add(value)
    return compact[:6]


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{1,4}", normalized)
    expanded: list[str] = [phrase for phrase in TCM_PHRASES if phrase in normalized]
    for token in tokens:
        expanded.append(token)
        if _is_cjk(token) and len(token) > 2:
            expanded.extend(token[idx : idx + 2] for idx in range(0, len(token) - 1))
    return expanded


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def keyword_overlap_score(query: str, text: str) -> float:
    query_terms = set(tokenize(query))
    if not query_terms:
        return 0.0
    text_terms = set(tokenize(text))
    return len(query_terms & text_terms) / len(query_terms)


def bm25_rank(query: str, candidates, top_k: int):
    tokenized_docs = [tokenize(chunk.text) for chunk in candidates]
    if not tokenized_docs:
        return []
    doc_freq: Counter[str] = Counter()
    for tokens in tokenized_docs:
        doc_freq.update(set(tokens))
    avgdl = sum(len(tokens) for tokens in tokenized_docs) / len(tokenized_docs)
    query_terms = tokenize(query)
    scored = []
    for chunk, doc_tokens in zip(candidates, tokenized_docs, strict=True):
        score = _bm25_score(query_terms, doc_tokens, doc_freq, len(tokenized_docs), avgdl)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return []
    max_score = scored[0][0] or 1.0
    results = []
    for score, chunk in scored[:top_k]:
        updated = chunk.model_copy(deep=True)
        updated.lexical_score = score / max_score
        updated.score = updated.lexical_score
        updated.retrieval_source = "bm25"
        results.append(updated)
    return results


def _bm25_score(query_terms: list[str], doc_tokens: list[str], doc_freq: Counter[str], doc_count: int, avgdl: float) -> float:
    if not query_terms or not doc_tokens:
        return 0.0
    k1 = 1.5
    b = 0.75
    term_freq = Counter(doc_tokens)
    score = 0.0
    doc_len = len(doc_tokens)
    for term in query_terms:
        tf = term_freq.get(term, 0)
        if tf == 0:
            continue
        df = doc_freq.get(term, 0)
        idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
        denom = tf + k1 * (1 - b + b * doc_len / (avgdl or 1.0))
        score += idf * (tf * (k1 + 1)) / denom
    return score


def _is_cjk(text: str) -> bool:
    return all("\u4e00" <= char <= "\u9fff" for char in text)
