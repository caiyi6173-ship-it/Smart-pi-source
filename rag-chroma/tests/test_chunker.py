from app.ingest.chunker import chunk_text


def test_chunk_text_with_overlap():
    chunks = chunk_text("一" * 1000, chunk_size=300, overlap=50)
    assert len(chunks) == 4
    assert chunks[0].index == 0
    assert len(chunks[0].text) == 300


def test_chunk_text_empty():
    assert chunk_text("\n\n") == []


def test_chunk_structured_modern_basics_by_paragraph_and_section():
    text = """
# 阴阳五行基础

阴阳是中医认识人体生命活动和病理变化的重要概念。

中医所说的阴阳平衡，通常指人体功能活动和物质基础保持相对协调，也包括寒热偏向、升降出入等方面维持动态稳定。

五行是用木火土金水五类属性来解释系统关联的理论工具，也常用于帮助理解脏腑、时令、颜色、味道等对应关系。
""".strip()
    chunks = chunk_text(text, chunk_size=140, overlap=40, source_type="modern_basics")

    assert len(chunks) == 2
    assert chunks[0].section == "阴阳五行基础"
    assert "阴阳五行基础" in chunks[0].text
    assert "阴阳平衡" in chunks[0].text
    assert "五行是用木火土金水" in chunks[1].text
