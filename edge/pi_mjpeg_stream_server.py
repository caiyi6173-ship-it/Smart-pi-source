#!/usr/bin/env python
from __future__ import annotations

import argparse
import base64
import cgi
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run continuous tongue detection on Raspberry Pi camera and serve MJPEG stream over HTTP."
    )
    parser.add_argument("--weights", type=Path, required=True, help="Path to .pt or .onnx detector")
    parser.add_argument("--source", type=str, default="0", help="Camera index or video/image path")
    parser.add_argument("--class-map", type=Path, default=repo_root / "config" / "class_map.json", help="Path to class_map.json")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--jpeg-quality", type=int, default=65)
    parser.add_argument("--frame-interval-ms", type=int, default=40)
    parser.add_argument("--inference-interval-ms", type=int, default=450)
    parser.add_argument("--camera-width", type=int, default=640)
    parser.add_argument("--camera-height", type=int, default=480)
    parser.add_argument("--camera-buffer-size", type=int, default=1)
    parser.add_argument("--title", type=str, default="smartpi Live Detection")
    return parser


def load_class_map(path: Path) -> dict[int, str]:
    with path.open("r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    return {item["remapped_id"]: item["canonical_label"] for item in data["classes"]}


@dataclass
class StreamState:
    jpeg_bytes: bytes | None = None
    cached_hit_jpeg: bytes | None = None
    last_error: str | None = None
    frame_count: int = 0
    last_labels: list[str] | None = None
    last_updated_at: float | None = None
    fps: float = 0.0
    inference_fps: float = 0.0
    hit_updated_at: float | None = None
    hit_labels: list[str] | None = None


class MjpegDetectionServer:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.state = StreamState()
        self.class_map = load_class_map(args.class_map.resolve())
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.server: ThreadingHTTPServer | None = None
        self.last_frame_monotonic: float | None = None
        self.last_inference_monotonic: float | None = None
        self.last_hit_cache_monotonic: float | None = None
        self.latest_frame: Any | None = None
        self.last_detections: list[dict[str, Any]] = []
        self.last_labels: list[str] = []
        self.model = None
        self.inference_lock = threading.Lock()

    def start(self) -> None:
        from ultralytics import YOLO

        task = "detect" if self.args.weights.suffix.lower() == ".onnx" else None
        self.model = YOLO(str(self.args.weights.resolve()), task=task) if task else YOLO(str(self.args.weights.resolve()))

        capture_worker = threading.Thread(target=self._capture_loop, name="capture-loop", daemon=True)
        infer_worker = threading.Thread(target=self._inference_loop, name="inference-loop", daemon=True)
        capture_worker.start()
        infer_worker.start()

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path in ("/", "/index.html"):
                    self._serve_index()
                    return
                if self.path.startswith("/health"):
                    self._serve_health()
                    return
                if self.path.startswith("/snapshot"):
                    self._serve_snapshot()
                    return
                if self.path.startswith("/hit-snapshot"):
                    self._serve_hit_snapshot()
                    return
                if self.path.startswith("/stream"):
                    self._serve_stream()
                    return
                if self.path.startswith("/detect"):
                    self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "Use POST for detect")
                    return
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

            def do_POST(self) -> None:
                if self.path.startswith("/detect"):
                    self._serve_detect()
                    return
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _serve_index(self) -> None:
                html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{outer.args.title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f4ee; color: #1d1b18; }}
    .card {{ background: white; border-radius: 16px; padding: 16px; box-shadow: 0 10px 24px rgba(0,0,0,0.08); max-width: 980px; }}
    img {{ width: 100%; max-width: 920px; border-radius: 12px; border: 1px solid #ddd; }}
    .meta {{ margin-top: 12px; color: #555; }}
    code {{ background: #f1efe9; padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{outer.args.title}</h1>
    <p>Open <code>/stream</code> for MJPEG, <code>/snapshot</code> for one frame, <code>/health</code> for status, and <code>/detect</code> for one-shot image detection.</p>
    <img src="/stream" alt="smartpi live detection stream">
  </div>
</body>
</html>"""
                data = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _serve_health(self) -> None:
                with outer.lock:
                    payload = {
                        "status": "UP" if outer.state.jpeg_bytes else "STARTING",
                        "frameCount": outer.state.frame_count,
                        "fps": round(outer.state.fps, 2),
                        "inferenceFps": round(outer.state.inference_fps, 2),
                        "lastLabels": outer.state.last_labels or [],
                        "hitFrameReady": bool(outer.state.cached_hit_jpeg),
                        "hitUpdatedAt": outer.state.hit_updated_at,
                        "hitLabels": outer.state.hit_labels or [],
                        "lastError": outer.state.last_error,
                        "lastUpdatedAt": outer.state.last_updated_at,
                    }
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _serve_snapshot(self) -> None:
                with outer.lock:
                    jpeg = outer.state.jpeg_bytes
                if not jpeg:
                    self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "No frame ready")
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                self.wfile.write(jpeg)

            def _serve_hit_snapshot(self) -> None:
                with outer.lock:
                    jpeg = outer.state.cached_hit_jpeg
                if not jpeg:
                    self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "No recognized frame cached")
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                self.wfile.write(jpeg)

            def _serve_stream(self) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()

                last_seen = -1
                try:
                    while not outer.stop_event.is_set():
                        with outer.lock:
                            frame_count = outer.state.frame_count
                            jpeg = outer.state.jpeg_bytes
                        if jpeg and frame_count != last_seen:
                            self.wfile.write(b"--frame\r\n")
                            self.wfile.write(b"Content-Type: image/jpeg\r\n")
                            self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                            self.wfile.write(jpeg)
                            self.wfile.write(b"\r\n")
                            last_seen = frame_count
                        time.sleep(0.03)
                except (BrokenPipeError, ConnectionResetError):
                    return

            def _serve_detect(self) -> None:
                try:
                    content_type = self.headers.get("Content-Type", "")
                    if "multipart/form-data" not in content_type:
                        self.send_error(HTTPStatus.BAD_REQUEST, "multipart/form-data expected")
                        return

                    form = cgi.FieldStorage(
                        fp=self.rfile,
                        headers=self.headers,
                        environ={
                            "REQUEST_METHOD": "POST",
                            "CONTENT_TYPE": content_type,
                        },
                    )

                    field_name = "image" if "image" in form else "file" if "file" in form else None
                    if not field_name:
                        self.send_error(HTTPStatus.BAD_REQUEST, "image file is required")
                        return

                    file_item = form[field_name]
                    image_bytes = file_item.file.read()
                    result = outer.detect_image_bytes(image_bytes)
                    data = json.dumps(result, ensure_ascii=False).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as ex:
                    payload = json.dumps({"error": str(ex)}, ensure_ascii=False).encode("utf-8")
                    self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

        self.server = ThreadingHTTPServer((self.args.host, self.args.port), Handler)
        print(f"smartpi MJPEG stream running on http://{self.args.host}:{self.args.port}", flush=True)
        self.server.serve_forever()

    def _capture_loop(self) -> None:
        source = int(self.args.source) if self.args.source.isdigit() else self.args.source
        cap = cv2.VideoCapture(source)
        if self.args.source.isdigit():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.args.camera_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.args.camera_height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, self.args.camera_buffer_size)
        if not cap.isOpened():
            with self.lock:
                self.state.last_error = f"Failed to open source: {self.args.source}"
            return

        try:
            while not self.stop_event.is_set():
                ok, frame = self._read_latest_frame(cap)
                if not ok or frame is None:
                    with self.lock:
                        self.state.last_error = "Camera read failed"
                    time.sleep(0.05)
                    continue

                with self.lock:
                    self.latest_frame = frame.copy()
                    detections = [dict(item) for item in self.last_detections]
                    labels = list(self.last_labels)
                    inference_fps = self.state.inference_fps

                annotated = frame.copy()
                try:
                    for detection in detections:
                        x1, y1, x2, y2 = detection["xyxy"]
                        label = detection["label"]
                        confidence = float(detection["confidence"])
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (16, 118, 110), 2)
                        text = f"{label} {confidence:.2f}"
                        cv2.putText(annotated, text, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (16, 118, 110), 2, cv2.LINE_AA)
                    if not labels:
                        cv2.putText(annotated, "No tongue label", (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 83, 9), 2, cv2.LINE_AA)
                    cv2.putText(
                        annotated,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        (18, annotated.shape[0] - 18),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                    cv2.putText(
                        annotated,
                        f"FPS {self._update_fps():.1f}",
                        (18, 62),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                    cv2.putText(
                        annotated,
                        f"INF {inference_fps:.1f} every {max(1, int(self.args.inference_interval_ms))}ms",
                        (18, 90),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (220, 220, 220),
                        2,
                        cv2.LINE_AA,
                    )
                    ok_encode, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), self.args.jpeg_quality])
                    if not ok_encode:
                        raise RuntimeError("JPEG encode failed")
                    jpeg_bytes = buf.tobytes()
                    now_wall = time.time()
                    should_cache_hit = bool(labels) and self._should_refresh_hit_cache()
                    with self.lock:
                        self.state.jpeg_bytes = jpeg_bytes
                        self.state.frame_count += 1
                        self.state.last_labels = labels
                        self.state.last_updated_at = now_wall
                        self.state.last_error = None
                        if should_cache_hit:
                            self.state.cached_hit_jpeg = jpeg_bytes
                            self.state.hit_updated_at = now_wall
                            self.state.hit_labels = list(labels)
                except Exception as ex:
                    with self.lock:
                        self.state.last_error = str(ex)
                time.sleep(max(self.args.frame_interval_ms, 1) / 1000.0)
        finally:
            cap.release()

    def _inference_loop(self) -> None:
        interval_seconds = max(1, int(self.args.inference_interval_ms)) / 1000.0
        while not self.stop_event.is_set():
            with self.lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()

            if frame is None:
                time.sleep(0.05)
                continue

            try:
                labels, detections, _ = self._infer_frame(frame)
                with self.lock:
                    self.last_detections = detections
                    self.last_labels = labels
            except Exception as ex:
                with self.lock:
                    self.state.last_error = str(ex)

            time.sleep(interval_seconds)

    def detect_image_bytes(self, image_bytes: bytes) -> dict[str, Any]:
        if not image_bytes:
            raise ValueError("Empty image payload")
        frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Failed to decode image")

        labels, detections, confidences = self._infer_frame(frame)
        annotated = frame.copy()
        for detection in detections:
            x1, y1, x2, y2 = detection["xyxy"]
            label = detection["label"]
            confidence = float(detection["confidence"])
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (16, 118, 110), 2)
            text = f"{label} {confidence:.2f}"
            cv2.putText(annotated, text, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (16, 118, 110), 2, cv2.LINE_AA)
        if not labels:
            cv2.putText(annotated, "No tongue label", (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 83, 9), 2, cv2.LINE_AA)
        cv2.putText(
            annotated,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            (18, annotated.shape[0] - 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        ok_encode, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), self.args.jpeg_quality])
        if not ok_encode:
            raise RuntimeError("Annotated JPEG encode failed")

        return {
            "tongueLabels": labels,
            "tongueDescription": f"边缘端识别标签：{'、'.join(labels)}" if labels else "未识别到舌象标签",
            "tongueConfidences": confidences,
            "annotatedImageBase64": base64.b64encode(buf.tobytes()).decode("ascii"),
            "annotatedImageFileName": f"edge_detect_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
        }

    def _infer_frame(self, frame: Any) -> tuple[list[str], list[dict[str, Any]], dict[str, float]]:
        if self.model is None:
            raise RuntimeError("Model is not initialized")

        labels: list[str] = []
        detections: list[dict[str, Any]] = []
        confidences: dict[str, float] = {}
        with self.inference_lock:
            results = self.model.predict(
                source=frame,
                conf=self.args.conf,
                imgsz=self.args.imgsz,
                device=self.args.device,
                verbose=False,
                save=False,
                exist_ok=True,
            )

        result = results[0]
        boxes = result.boxes
        if boxes is not None:
            for xyxy, cls_tensor, conf_tensor in zip(boxes.xyxy, boxes.cls, boxes.conf):
                class_id = int(cls_tensor.item())
                confidence = float(conf_tensor.item())
                label = self.class_map.get(class_id, str(result.names.get(class_id, class_id)))
                labels.append(label)
                previous = confidences.get(label, 0.0)
                if confidence > previous:
                    confidences[label] = round(confidence, 4)
                detections.append(
                    {
                        "label": label,
                        "confidence": confidence,
                        "xyxy": [int(v) for v in xyxy.tolist()],
                    }
                )

        with self.lock:
            self._update_inference_fps()
            self.state.last_error = None

        return labels, detections, confidences

    def _read_latest_frame(self, cap: cv2.VideoCapture) -> tuple[bool, Any]:
        latest_ok = False
        latest_frame = None
        if self.args.source.isdigit():
            for _ in range(2):
                cap.grab()
        ok, frame = cap.read()
        if ok and frame is not None:
            latest_ok = True
            latest_frame = frame
        return latest_ok, latest_frame

    def _update_fps(self) -> float:
        now = time.perf_counter()
        if self.last_frame_monotonic is None:
            self.last_frame_monotonic = now
            return self.state.fps

        delta = now - self.last_frame_monotonic
        self.last_frame_monotonic = now
        if delta <= 0:
            return self.state.fps

        instant_fps = 1.0 / delta
        smoothed = instant_fps if self.state.fps <= 0 else (self.state.fps * 0.8 + instant_fps * 0.2)
        self.state.fps = smoothed
        return smoothed

    def _update_inference_fps(self) -> float:
        now = time.perf_counter()
        if self.last_inference_monotonic is None:
            self.last_inference_monotonic = now
            return self.state.inference_fps

        delta = now - self.last_inference_monotonic
        self.last_inference_monotonic = now
        if delta <= 0:
            return self.state.inference_fps

        instant_fps = 1.0 / delta
        smoothed = instant_fps if self.state.inference_fps <= 0 else (self.state.inference_fps * 0.8 + instant_fps * 0.2)
        self.state.inference_fps = smoothed
        return smoothed

    def _should_refresh_hit_cache(self) -> bool:
        now = time.perf_counter()
        with self.lock:
            last_cache = self.last_hit_cache_monotonic
            if last_cache is None or now - last_cache >= 3.0:
                self.last_hit_cache_monotonic = now
                return True
        return False


def main() -> None:
    args = build_parser().parse_args()
    server = MjpegDetectionServer(args)
    server.start()


if __name__ == "__main__":
    main()
