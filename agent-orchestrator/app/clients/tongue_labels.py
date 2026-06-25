import json
from pathlib import Path
from typing import Any


class TongueLabelResolver:
    def __init__(self, class_map_path: Path) -> None:
        self.class_map_path = class_map_path
        self._index = self._load_index(class_map_path)

    def resolve_many(
        self,
        labels: list[str],
        confidences: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        confidences = confidences or {}
        resolved = []
        for label in labels:
            item = self.resolve(label)
            item["input_label"] = label
            item["confidence"] = confidences.get(label)
            resolved.append(item)
        return resolved

    def resolve(self, label: str) -> dict[str, Any]:
        key = str(label).strip()
        if not key:
            return self._unknown(label)
        return self._index.get(key.lower()) or self._unknown(label)

    def _load_index(self, path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        index: dict[str, dict[str, Any]] = {}
        for item in data.get("classes", []):
            normalized = {
                "canonical_label": item.get("canonical_label", ""),
                "display_name_zh": item.get("display_name_zh", ""),
                "verified": bool(item.get("verified", False)),
                "original_id": item.get("original_id"),
                "remapped_id": item.get("remapped_id"),
                "aliases": item.get("aliases", []),
            }
            keys = [
                item.get("canonical_label"),
                item.get("display_name_zh"),
                item.get("original_id"),
                item.get("remapped_id"),
                *item.get("aliases", []),
            ]
            for key in keys:
                if key is not None and str(key).strip():
                    index[str(key).strip().lower()] = dict(normalized)
        return index

    def _unknown(self, label: str) -> dict[str, Any]:
        return {
            "canonical_label": str(label),
            "display_name_zh": str(label),
            "verified": False,
            "original_id": None,
            "remapped_id": None,
            "aliases": [],
        }
