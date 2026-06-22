from pathlib import Path

from app.ingest.loaders import load_path


def test_markdown_loader_strips_front_matter_and_extracts_metadata(tmp_path: Path):
    sample = tmp_path / "sample.md"
    sample.write_text(
        """---
title: 阴阳五行基础
source_type: modern_basics
source_urls:
  - https://example.com/a
  - https://example.com/b
tags: [中医基础, 阴阳]
---

# 阴阳五行基础

阴阳用于解释相互关联、相互制约的两类属性。
""",
        encoding="utf-8",
    )

    text, extra = load_path(sample)

    assert "source_urls" not in text
    assert text.startswith("# 阴阳五行基础")
    assert extra["title"] == "阴阳五行基础"
    assert extra["source_type"] == "modern_basics"
    assert extra["source_urls"] == ["https://example.com/a", "https://example.com/b"]
    assert extra["tags"] == ["中医基础", "阴阳"]
