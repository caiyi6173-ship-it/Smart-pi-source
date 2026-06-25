from dataclasses import dataclass
import re


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
    if source_type == "classic_text":
        structured = _chunk_classic_text(text, min(chunk_size, 480), min(overlap, 80))
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


def _chunk_classic_text(text: str, target_size: int, overlap: int) -> list[TextChunk]:
    units = _extract_classic_units(text)
    if not units:
        return []

    chunks: list[TextChunk] = []
    buffer_texts: list[str] = []
    buffer_section: str | None = None
    index = 0

    def flush_buffer() -> None:
        nonlocal buffer_texts, buffer_section, index
        if not buffer_texts:
            return
        chunks.append(TextChunk(text="\n".join(buffer_texts).strip(), index=index, section=buffer_section))
        index += 1
        buffer_texts = []
        buffer_section = None

    for section, unit_text in units:
        unit_text = unit_text.strip()
        if not unit_text:
            continue
        if len(unit_text) > target_size:
            flush_buffer()
            for piece in _sliding_window_chunks(unit_text, target_size, overlap):
                chunks.append(TextChunk(text=piece.text, index=index, section=section))
                index += 1
            continue

        if not buffer_texts:
            buffer_texts = [unit_text]
            buffer_section = section
            continue

        candidate = "\n".join([*buffer_texts, unit_text])
        same_section = section == buffer_section
        if len(candidate) <= target_size and same_section:
            buffer_texts.append(unit_text)
            continue

        flush_buffer()
        buffer_texts = [unit_text]
        buffer_section = section

    flush_buffer()
    return chunks


def _extract_classic_units(text: str) -> list[tuple[str | None, str]]:
    units: list[tuple[str | None, str]] = []
    current_section: str | None = None
    current_lines: list[str] = []

    def flush_unit() -> None:
        nonlocal current_lines
        if not current_lines:
            return
        unit = "\n".join(current_lines).strip()
        if unit:
            units.append((current_section, unit))
        current_lines = []

    for raw_line in text.splitlines():
        line = _clean_classic_line(raw_line)
        if not line:
            continue

        heading = _classic_heading(line)
        if heading is not None:
            flush_unit()
            if heading != "目录":
                current_section = heading
            continue

        if _is_classic_book_metadata(line):
            continue

        if _starts_classic_article(line):
            flush_unit()
            current_lines = [line]
            continue

        if not current_lines:
            current_lines = [line]
        else:
            current_lines.append(line)

    flush_unit()
    return units


def _clean_classic_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip()).strip()


def _classic_heading(line: str) -> str | None:
    tag_match = re.fullmatch(r"<([^<>]+)>\s*(.*)", line)
    if tag_match:
        tag = tag_match.group(1).strip()
        value = tag_match.group(2).strip()
        if tag == "目录":
            return "目录"
        if tag in {"篇名", "卷", "章", "节"} and value:
            return value
    if re.fullmatch(r"卷[一二三四五六七八九十百千万\d]+.*", line):
        return line
    return None


def _is_classic_book_metadata(line: str) -> bool:
    return bool(re.match(r"^(书名|作者|朝代|年份|底本|校注|版本)[：:]", line))


def _starts_classic_article(line: str) -> bool:
    return bool(re.match(r"^(属性[:：]\s*)?([0-9０-９]+|[一二三四五六七八九十百千万]+)[\.．、]", line))
