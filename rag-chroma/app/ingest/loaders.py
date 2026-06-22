from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx", ".html", ".htm"}


def load_path(path: Path) -> tuple[str, dict]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type: {suffix}")

    if suffix in {".txt"}:
        return _read_text_with_fallback(path), {}
    if suffix in {".md", ".markdown"}:
        return _load_markdown(path)
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix == ".docx":
        return _load_docx(path), {}
    if suffix in {".html", ".htm"}:
        return _load_html(path), {}
    raise ValueError(f"unsupported file type: {suffix}")


def iter_supported_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_EXTENSIONS else []
    return sorted(file for file in path.rglob("*") if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS)


def _read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    candidates = ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5")
    best_text = ""
    best_score = -1
    for encoding in candidates:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        score = _chinese_text_score(text)
        if score > best_score:
            best_text = text
            best_score = score
    if best_text:
        return best_text
    return raw.decode("utf-8", errors="replace")


def _load_markdown(path: Path) -> tuple[str, dict]:
    raw_text = _read_text_with_fallback(path)
    front_matter, body = _split_front_matter(raw_text)
    return body, front_matter


def _chinese_text_score(text: str) -> int:
    replacement_penalty = text.count("\ufffd") * 20
    cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    common_hits = sum(text.count(word) for word in ("卷", "篇", "病", "脉", "舌", "黄帝", "伤寒", "本草"))
    return cjk_count + common_hits * 10 - replacement_penalty


def _split_front_matter(text: str) -> tuple[dict, str]:
    stripped = text.lstrip()
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_index = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = idx
            break
    if end_index is None:
        return {}, text

    metadata_lines = lines[1:end_index]
    body = "\n".join(lines[end_index + 1 :]).strip()
    return _parse_simple_front_matter(metadata_lines), body


def _parse_simple_front_matter(lines: list[str]) -> dict:
    metadata: dict[str, object] = {}
    current_key: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current_key:
            metadata.setdefault(current_key, [])
            value = stripped[2:].strip()
            if value:
                metadata[current_key].append(value)
            continue
        if ":" not in stripped:
            current_key = None
            continue
        key, value = stripped.split(":", 1)
        current_key = key.strip()
        parsed_value = value.strip()
        if not parsed_value:
            metadata[current_key] = []
            continue
        if parsed_value.startswith("[") and parsed_value.endswith("]"):
            inner = parsed_value[1:-1].strip()
            metadata[current_key] = [item.strip() for item in inner.split(",") if item.strip()] if inner else []
            continue
        metadata[current_key] = parsed_value

    return metadata


def _load_pdf(path: Path) -> tuple[str, dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to read PDF files. Run pip install pypdf.") from exc

    reader = PdfReader(str(path))
    page_texts: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            page_texts.append(f"\n\n[page:{idx}]\n{text}")
    return "\n".join(page_texts), {"page_count": len(reader.pages)}


def _load_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("python-docx is required to read DOCX files. Run pip install python-docx.") from exc

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _load_html(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("beautifulsoup4 is required to read HTML files. Run pip install beautifulsoup4.") from exc

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)
