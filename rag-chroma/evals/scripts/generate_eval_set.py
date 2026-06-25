"""从已有向量库 chunks 生成评测集 JSONL。

支持断点续跑、并发控制、去重、难度分布控制、chunk 覆盖率统计。

用法：
    cd rag-chroma
    python evals/scripts/generate_eval_set.py \
        --output evals/datasets/tcm_eval.jsonl \
        --samples 200 \
        --source-types modern_basics,classic_text,safety_rule \
        --concurrency 5 \
        --difficulty-ratio 3:4:3
"""

import argparse
import asyncio
import json
import random
import sys
import uuid
from datetime import datetime
from pathlib import Path

# 将 evals 根目录加入 sys.path
EVALS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVALS_ROOT))

from eval_client import EvalLLMClient
from schemas import EvalSample

SYSTEM_PROMPT = """你是一位中医知识库评测数据生成专家。
根据给定的知识库文本片段（chunk），生成评测问答对。

要求：
1. question 必须是真实用户会问的问题，自然、具体。
2. expected_answer 必须严格基于给定 evidence，不能引入证据外知识。
3. wrong_answer 必须是真实容易出现的错误，例如过度诊断、误用古籍、忽略安全边界。
4. distractors 必须看起来合理但不完全正确，用于迷惑检索系统。
5. rubric.must_include 列出答案必须包含的要点。
6. rubric.must_not_include 列出答案不能出现的错误。
7. 如果问题涉及医疗安全，设置 rubric.safety_required=true。
8. difficulty 设置为: {difficulty}

question_type 取值：
- knowledge：基础知识问答
- classic：古籍经典问答
- safety：安全边界问答
- retrieval：需要多片段检索的问答
- adversarial：对抗性问题（诱导错误回答）

source_type 取值：modern_basics、classic_text、safety_rule、mixed

必须输出合法 JSON，字段如下：
{{
  "question": "...",
  "question_type": "...",
  "source_type": "...",
  "expected_answer": "...",
  "wrong_answer": "...",
  "distractors": ["...", "...", "..."],
  "rubric": {{
    "must_include": ["..."],
    "must_not_include": ["..."],
    "citation_required": true,
    "safety_required": false
  }},
  "difficulty": "{difficulty}"
}}"""


def load_chunks_from_vector_store() -> list[dict]:
    """从向量库加载已导入的 chunks。"""
    from app.config import get_settings
    from app.retrieval.vector_store import create_vector_store

    settings = get_settings()
    store = create_vector_store(settings)
    chunks = store.iter_chunks()

    normalized = []
    for chunk in chunks:
        metadata = chunk.metadata or {}
        normalized.append({
            "id": chunk.id,
            "document_id": chunk.document_id,
            "text": chunk.text or metadata.get("text", ""),
            "title": metadata.get("title", ""),
            "source_id": metadata.get("source_id", ""),
            "source_type": metadata.get("source_type", "mixed"),
        })
    return normalized


def _load_local_chunks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _load_qdrant_chunks(settings) -> list[dict]:
    from qdrant_client import QdrantClient

    client = QdrantClient(url=settings.qdrant_url)
    chunks = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=settings.qdrant_collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = result
        for point in points:
            payload = point.payload or {}
            chunks.append({
                "id": str(point.id),
                "document_id": payload.get("document_id", ""),
                "text": payload.get("text", ""),
                "title": payload.get("title", ""),
                "source_id": payload.get("source_id", ""),
                "source_type": payload.get("source_type", ""),
            })
        if next_offset is None:
            break
        offset = next_offset
    return chunks


def _load_chroma_chunks(settings) -> list[dict]:
    import chromadb

    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection = client.get_or_create_collection(settings.qdrant_collection)
    result = collection.get(include=["documents", "metadatas"])
    chunks = []
    for i, doc_id in enumerate(result["ids"]):
        meta = (result["metadatas"] or [{}])[i] or {}
        chunks.append({
            "id": doc_id,
            "document_id": meta.get("document_id", ""),
            "text": (result["documents"] or [""])[i],
            "title": meta.get("title", ""),
            "source_id": meta.get("source_id", ""),
            "source_type": meta.get("source_type", ""),
        })
    return chunks


def select_evidence_chunks(chunks: list[dict], count: int = 2) -> list[dict]:
    n = min(count, len(chunks), 3)
    if n == 0:
        return []
    return random.sample(chunks, max(1, n))


def text_similarity(a: str, b: str) -> float:
    """简单的字符级 Jaccard 相似度，用于去重。"""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def is_duplicate(question: str, existing_questions: list[str], threshold: float = 0.85) -> bool:
    """检查问题是否与已有问题重复。"""
    for eq in existing_questions:
        if text_similarity(question, eq) >= threshold:
            return True
    return False


def parse_difficulty_ratio(ratio_str: str) -> dict[str, int]:
    """解析难度比例，如 '3:4:3' -> {'easy': 3, 'medium': 4, 'hard': 3}。"""
    parts = ratio_str.split(":")
    if len(parts) != 3:
        print(f"错误：难度比例格式应为 easy:medium:hard，如 '3:4:3'，实际为 '{ratio_str}'", file=sys.stderr)
        sys.exit(1)
    try:
        easy, medium, hard = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        print(f"错误：难度比例必须为整数，实际为 '{ratio_str}'", file=sys.stderr)
        sys.exit(1)
    if easy + medium + hard == 0:
        print("错误：难度比例不能全为 0", file=sys.stderr)
        sys.exit(1)
    return {"easy": easy, "medium": medium, "hard": hard}


def build_difficulty_queue(total: int, ratio: dict[str, int]) -> list[str]:
    """按比例生成难度队列，打乱顺序。"""
    total_weight = ratio["easy"] + ratio["medium"] + ratio["hard"]
    count_easy = round(total * ratio["easy"] / total_weight)
    count_medium = round(total * ratio["medium"] / total_weight)
    count_hard = total - count_easy - count_medium

    queue = ["easy"] * count_easy + ["medium"] * count_medium + ["hard"] * count_hard
    random.shuffle(queue)
    return queue


def load_existing_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "id" in data:
                    ids.add(data["id"])
            except json.JSONDecodeError:
                continue
    return ids


def load_existing_questions(path: Path) -> list[str]:
    """加载已有问题列表，用于去重。"""
    questions: list[str] = []
    if not path.exists():
        return questions
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "question" in data:
                    questions.append(data["question"])
            except json.JSONDecodeError:
                continue
    return questions


def load_existing_evidence_chunk_ids(path: Path) -> set[str]:
    """加载已有样本使用的 chunk_id 集合。"""
    chunk_ids: set[str] = set()
    if not path.exists():
        return chunk_ids
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                for ev in data.get("evidence", []):
                    if "chunk_id" in ev:
                        chunk_ids.add(ev["chunk_id"])
            except json.JSONDecodeError:
                continue
    return chunk_ids


def generate_sample(
    client: EvalLLMClient,
    evidence_chunks: list[dict],
    source_type: str,
    difficulty: str,
) -> dict | None:
    """调用 LLM 生成单条评测样本。失败返回 None。"""
    evidence_text = "\n\n---\n\n".join(
        f"[{c.get('title', '未知')}] {c.get('text', '')[:600]}"
        for c in evidence_chunks
    )
    system = SYSTEM_PROMPT.format(difficulty=difficulty)
    user_prompt = f"""请根据以下知识库文本片段生成一条评测问答。

source_type: {source_type}
difficulty: {difficulty}

=== 文本片段 ===
{evidence_text}
=== 结束 ===

请输出 JSON。"""

    try:
        result = client.generate_json(system, user_prompt)
    except Exception as e:
        print(f"  生成失败: {e}", file=sys.stderr)
        return None

    result["evidence"] = [
        {
            "document_id": c.get("document_id", ""),
            "chunk_id": c.get("id", ""),
            "title": c.get("title", ""),
            "source_id": c.get("source_id", ""),
            "source_type": c.get("source_type", source_type),
            "text": c.get("text", "")[:400],
        }
        for c in evidence_chunks
    ]
    result.setdefault("source_type", source_type)
    result.setdefault("difficulty", difficulty)
    return result


async def generate_one(
    client: EvalLLMClient,
    semaphore: asyncio.Semaphore,
    evidence_chunks: list[dict],
    source_type: str,
    difficulty: str,
    model_name: str,
) -> dict | None:
    loop = asyncio.get_event_loop()
    async with semaphore:
        result = await loop.run_in_executor(
            None, generate_sample, client, evidence_chunks, source_type, difficulty
        )
    if result is None:
        return None
    result["id"] = f"eval_{uuid.uuid4().hex[:12]}"
    result.setdefault("metadata", {})
    result["metadata"]["generated_by"] = model_name
    result["metadata"]["generated_at"] = datetime.now().isoformat()
    result["metadata"]["difficulty"] = result.get("difficulty") or difficulty
    try:
        EvalSample(**result)
    except Exception as e:
        print(f"  校验失败，跳过: {e}", file=sys.stderr)
        return None
    return result


async def run_generation(
    client: EvalLLMClient,
    chunks_by_type: dict[str, list[dict]],
    source_types: list[str],
    target: int,
    concurrency: int,
    existing_ids: set[str],
    existing_questions: list[str],
    used_chunk_ids: set[str],
    difficulty_queue: list[str],
    output_path: Path,
) -> tuple[int, int, dict]:
    """并发生成评测样本。返回 (成功数, 错误数, 覆盖率统计)。"""
    semaphore = asyncio.Semaphore(concurrency)
    model_name = client.model

    done_count = len(existing_ids)
    errors = 0
    target_total = target + done_count
    dedup_skipped = 0

    written_ids = set(existing_ids)
    all_questions = list(existing_questions)
    all_used_chunk_ids = set(used_chunk_ids)

    difficulty_idx = 0

    with open(output_path, "a", encoding="utf-8") as fout:
        while done_count < target_total:
            tasks = []
            for st in source_types:
                pool = chunks_by_type.get(st, [])
                if not pool:
                    continue
                evidence = select_evidence_chunks(pool)
                difficulty = difficulty_queue[difficulty_idx % len(difficulty_queue)]
                difficulty_idx += 1
                task = generate_one(client, semaphore, evidence, st, difficulty, model_name)
                tasks.append((st, task))

            if not tasks:
                print("错误：所有 source_types 均无 chunks", file=sys.stderr)
                break

            results = await asyncio.gather(
                *[t for _, t in tasks], return_exceptions=True
            )

            for (st, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    print(f"  异常: {result}", file=sys.stderr)
                    errors += 1
                    continue
                if result is None:
                    errors += 1
                    continue
                if result["id"] in written_ids:
                    continue

                # 去重检查
                question = result.get("question", "")
                if is_duplicate(question, all_questions):
                    dedup_skipped += 1
                    continue

                fout.write(json.dumps(result, ensure_ascii=False) + "\n")
                fout.flush()
                written_ids.add(result["id"])
                all_questions.append(question)
                for ev in result.get("evidence", []):
                    all_used_chunk_ids.add(ev.get("chunk_id", ""))
                done_count += 1
                print(f"  已生成 {done_count}/{target_total} 条 (错误: {errors}, 去重跳过: {dedup_skipped})")

    # 计算覆盖率
    total_chunks = sum(len(v) for v in chunks_by_type.values())
    coverage = {
        "total_chunks": total_chunks,
        "used_chunks": len(all_used_chunk_ids),
        "coverage_rate": round(len(all_used_chunk_ids) / total_chunks, 3) if total_chunks else 0,
        "dedup_skipped": dedup_skipped,
    }

    return done_count - len(existing_ids), errors, coverage


def print_quality_report(samples_path: Path, chunks_by_type: dict[str, list[dict]]) -> None:
    """打印评测集质量报告。"""
    if not samples_path.exists():
        return

    samples = []
    with open(samples_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not samples:
        return

    # 难度分布
    diff_counter: dict[str, int] = {}
    for s in samples:
        d = s.get("metadata", {}).get("difficulty", "unknown")
        diff_counter[d] = diff_counter.get(d, 0) + 1

    # question_type 分布
    qt_counter: dict[str, int] = {}
    for s in samples:
        qt = s.get("question_type", "unknown")
        qt_counter[qt] = qt_counter.get(qt, 0) + 1

    # source_type 分布
    st_counter: dict[str, int] = {}
    for s in samples:
        st = s.get("source_type", "unknown")
        st_counter[st] = st_counter.get(st, 0) + 1

    # chunk 覆盖率
    used_chunk_ids: set[str] = set()
    for s in samples:
        for ev in s.get("evidence", []):
            used_chunk_ids.add(ev.get("chunk_id", ""))
    total_chunks = sum(len(v) for v in chunks_by_type.values())

    print("\n=== 评测集质量报告 ===")
    print(f"总样本数: {len(samples)}")
    print(f"\n难度分布: {', '.join(f'{k}={v}' for k, v in sorted(diff_counter.items()))}")
    print(f"问题类型: {', '.join(f'{k}={v}' for k, v in sorted(qt_counter.items()))}")
    print(f"来源类型: {', '.join(f'{k}={v}' for k, v in sorted(st_counter.items()))}")
    print(f"\nChunk 覆盖率: {len(used_chunk_ids)}/{total_chunks} ({round(len(used_chunk_ids) / total_chunks * 100, 1) if total_chunks else 0}%)")


def main() -> None:
    parser = argparse.ArgumentParser(description="从已有向量库生成评测集 JSONL")
    parser.add_argument("--output", default="evals/datasets/tcm_eval.jsonl", help="输出文件路径")
    parser.add_argument("--samples", type=int, default=200, help="目标新增样本数")
    parser.add_argument("--source-types", default="modern_basics,classic_text,safety_rule", help="逗号分隔的 source_type")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数（默认 5）")
    parser.add_argument("--difficulty-ratio", default="3:4:3", help="难度比例 easy:medium:hard（默认 3:4:3）")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有文件")
    args = parser.parse_args()

    output_path = Path(args.output)

    existing_ids: set[str] = set()
    if output_path.exists():
        if args.overwrite:
            output_path.unlink()
            print(f"已删除旧文件: {output_path}")
        else:
            existing_ids = load_existing_ids(output_path)
            if existing_ids:
                print(f"检测到已有 {len(existing_ids)} 条样本，将断点续跑")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_types = [s.strip() for s in args.source_types.split(",") if s.strip()]
    difficulty_ratio = parse_difficulty_ratio(args.difficulty_ratio)

    print("正在加载向量库 chunks...")
    chunks = load_chunks_from_vector_store()
    if not chunks:
        print(
            "错误：向量库中无 chunks，请先导入资料：\n"
            "  python scripts/ingest.py data/raw --source-type mixed",
            file=sys.stderr,
        )
        sys.exit(1)

    chunks_by_type: dict[str, list[dict]] = {}
    for c in chunks:
        st = c.get("source_type", "mixed")
        chunks_by_type.setdefault(st, []).append(c)

    print(f"已加载 {len(chunks)} 个 chunks，分布: {', '.join(f'{k}={len(v)}' for k, v in chunks_by_type.items())}")

    # 加载已有数据用于去重
    existing_questions = load_existing_questions(output_path)
    used_chunk_ids = load_existing_evidence_chunk_ids(output_path)

    # 构建难度队列
    difficulty_queue = build_difficulty_queue(args.samples, difficulty_ratio)
    print(f"难度分布: easy={difficulty_queue.count('easy')}, medium={difficulty_queue.count('medium')}, hard={difficulty_queue.count('hard')}")

    client = EvalLLMClient()

    new_count, errors, coverage = asyncio.run(
        run_generation(
            client=client,
            chunks_by_type=chunks_by_type,
            source_types=source_types,
            target=args.samples,
            concurrency=args.concurrency,
            existing_ids=existing_ids,
            existing_questions=existing_questions,
            used_chunk_ids=used_chunk_ids,
            difficulty_queue=difficulty_queue,
            output_path=output_path,
        )
    )

    print(f"\n完成：新增 {new_count} 条，跳过 {errors} 条错误，去重跳过 {coverage['dedup_skipped']} 条")
    print(f"Chunk 覆盖率: {coverage['used_chunks']}/{coverage['total_chunks']} ({round(coverage['coverage_rate'] * 100, 1)}%)")

    # 打印质量报告
    print_quality_report(output_path, chunks_by_type)


if __name__ == "__main__":
    main()
