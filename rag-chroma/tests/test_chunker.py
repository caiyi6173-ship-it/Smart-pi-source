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


def test_chunk_classic_text_by_heading_and_articles():
    text = """
<篇名>伤寒论
书名：伤寒论
作者：张仲景

<目录>

<篇名>辨太阳病脉证并治上

属性：1．太阳之为病，脉浮、头项强痛而恶寒。
2．太阳病，发热、汗出、恶风、脉缓者，名为中风。
3．太阳病，或已发热，或未发热，必恶寒，体痛，呕逆，脉阴阳俱紧者，名为伤寒。

<篇名>辨阳明病脉证并治

180．阳明之为病，胃家实是也。
""".strip()

    chunks = chunk_text(text, chunk_size=60, overlap=12, source_type="classic_text")

    assert len(chunks) >= 3
    assert chunks[0].section == "辨太阳病脉证并治上"
    assert "书名：伤寒论" not in chunks[0].text
    assert "1．太阳之为病" in chunks[0].text
    assert any(chunk.section == "辨阳明病脉证并治" for chunk in chunks)
    assert any("180．阳明之为病" in chunk.text for chunk in chunks)
