#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run ONNX inference and emit smartpi edge payload JSON")
    parser.add_argument("--weights", type=Path, required=True, help="Path to exported ONNX model")
    parser.add_argument("--source", type=Path, required=True, help="Path to source image")
    parser.add_argument("--class-map", type=Path, default=repo_root / "training" / "config" / "class_map.json")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--project", type=Path, default=repo_root / "training" / "runs")
    parser.add_argument("--name", type=str, default="onnx_predict")
    parser.add_argument("--output-json", type=Path, default=None)
    return parser


def load_class_map(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    return {item["remapped_id"]: item["canonical_label"] for item in data["classes"]}


def main() -> None:
    from ultralytics import YOLO

    args = build_parser().parse_args()
    class_map = load_class_map(args.class_map.resolve())

    model = YOLO(str(args.weights.resolve()), task="detect")
    results = model.predict(
        source=str(args.source.resolve()),
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        save=args.save,
        project=str(args.project.resolve()),
        name=args.name,
        exist_ok=True,
        verbose=False,
    )
    if not results:
        raise RuntimeError("No inference result returned from ONNX model")

    result = results[0]
    boxes = result.boxes
    label_conf = OrderedDict()
    if boxes is not None:
        for class_id_tensor, conf_tensor in zip(boxes.cls, boxes.conf):
            class_id = int(class_id_tensor.item())
            canonical = class_map.get(class_id, str(result.names.get(class_id, class_id)))
            confidence = round(float(conf_tensor.item()), 4)
            previous = label_conf.get(canonical, 0.0)
            if confidence > previous:
                label_conf[canonical] = confidence

    tongue_labels = list(label_conf.keys())
    payload = {
        "tongueLabels": tongue_labels,
        "tongueDescription": "Detected tongue labels: " + ", ".join(tongue_labels) if tongue_labels else "No tongue labels detected",
        "tongueConfidences": label_conf,
        "tongueImagePath": str(args.source.resolve()),
    }

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
