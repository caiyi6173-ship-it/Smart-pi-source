from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    index: int
    section: str | None = None


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120, source_type: str = "mixed") -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    if source_type in {"modern_basics", "safety_rule"}:
        structured = _chunk_structured_markdown(text, min(chunk_size, 360))
        if structured:
            return structured

    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return []
    return _sliding_window_chunks(normalized, chunk_size, overlap)


def _sliding_window_chunks(text: str, chunk_size: int, overlap: int) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(TextChunk(text=chunk, index=index))
            index += 1
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _chunk_structured_markdown(text: str, target_size: int) -> list[TextChunk]:
    blocks = _extract_structured_blocks(text)
    if not blocks:
        return []

    chunks: list[TextChunk] = []
    buffer_texts: list[str] = []
    buffer_section: str | None = None
    index = 0
    min_chunk_size = max(120, target_size // 2)

    for section, paragraph in blocks:
        block_text = paragraph if section is None else f"{section}\n{paragraph}"
        if len(block_text) > target_size:
            if buffer_texts:
                chunks.append(TextChunk(text="\n\n".join(buffer_texts), index=index, section=buffer_section))
                index += 1
                buffer_texts = []
                buffer_section = None
            for piece in _sliding_window_chunks(block_text, target_size, max(40, target_size // 5)):
                chunks.append(TextChunk(text=piece.text, index=index, section=section))
                index += 1
            continue

        if not buffer_texts:
            buffer_texts = [block_text]
            buffer_section = section
            continue

        candidate = "\n\n".join([*buffer_texts, block_text])
        same_section = section == buffer_section
        if len(candidate) <= target_size and (same_section or len("\n\n".join(buffer_texts)) < min_chunk_size):
            buffer_texts.append(block_text)
            continue

        chunks.append(TextChunk(text="\n\n".join(buffer_texts), index=index, section=buffer_section))
        index += 1
        buffer_texts = [block_text]
        buffer_section = section

    if buffer_texts:
        chunks.append(TextChunk(text="\n\n".join(buffer_texts), index=index, section=buffer_section))
    return chunks


def _extract_structured_blocks(text: str) -> list[tuple[str | None, str]]:
    blocks: list[tuple[str | None, str]] = []
    current_section: str | None = None
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        paragraph = " ".join(line.strip() for line in paragraph_lines if line.strip()).strip()
        if paragraph:
            blocks.append((current_section, paragraph))
        paragraph_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("#"):
            flush_paragraph()
            heading = line.lstrip("#").strip()
            if heading:
                current_section = heading
            continue
        paragraph_lines.append(line)
    flush_paragraph()
    return blocks
