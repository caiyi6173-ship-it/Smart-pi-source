#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import mimetypes
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import cv2
import requests


@dataclass
class MediaUploadResult:
    storage: str
    object_key: str | None = None
    url: str | None = None
    bucket: str | None = None


class MediaUploader:
    def upload_media(self, image_path: Path) -> MediaUploadResult:
        raise NotImplementedError


class LocalOnlyMediaUploader(MediaUploader):
    def upload_media(self, image_path: Path) -> MediaUploadResult:
        return MediaUploadResult(storage="local")


class AliyunOssMediaUploader(MediaUploader):
    def __init__(
        self,
        endpoint: str | None,
        bucket: str | None,
        prefix: str,
        region: str | None,
        auth_mode: str,
        public_base_url: str | None,
        presigned_url: str | None,
    ) -> None:
        self.endpoint = (endpoint or "").strip() or None
        self.bucket = (bucket or "").strip() or None
        self.prefix = prefix.strip().strip("/")
        self.region = (region or "").strip() or None
        self.auth_mode = auth_mode
        self.public_base_url = (public_base_url or "").strip() or None
        self.presigned_url = (presigned_url or "").strip() or None

    def upload_media(self, image_path: Path) -> MediaUploadResult:
        object_key = self._build_object_key(image_path)
        if self.auth_mode == "presigned":
            self._upload_with_presigned_url(image_path)
        elif self.auth_mode == "sts":
            raise RuntimeError("Aliyun OSS STS upload is reserved but not implemented in this phase")
        else:
            raise RuntimeError(f"Unsupported OSS auth mode: {self.auth_mode}")

        return MediaUploadResult(
            storage="aliyun-oss",
            object_key=object_key,
            url=self._resolve_public_url(object_key),
            bucket=self.bucket,
        )

    def _build_object_key(self, image_path: Path) -> str:
        date_path = datetime.now().strftime("%Y/%m/%d")
        parts = [part for part in [self.prefix, date_path, image_path.name] if part]
        return "/".join(parts)

    def _upload_with_presigned_url(self, image_path: Path) -> None:
        if not self.presigned_url:
            raise RuntimeError("Aliyun OSS presigned upload URL is required in presigned mode")

        content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        with image_path.open("rb") as fh:
            response = requests.put(
                self.presigned_url,
                data=fh,
                headers={"Content-Type": content_type},
                timeout=120,
            )
        response.raise_for_status()

    def _resolve_public_url(self, object_key: str) -> str | None:
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}/{object_key}"
        if not self.endpoint or not self.bucket:
            return None

        endpoint = self.endpoint
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            parsed = urlparse(endpoint)
            base = f"{parsed.scheme}://{self.bucket}.{parsed.netloc}".rstrip("/")
            return f"{base}/{object_key}"
        return f"https://{self.bucket}.{endpoint.strip('/')}/{object_key}"


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Capture one frame from a Raspberry Pi USB camera, run tongue inference, and optionally upload to SmartTCM backend."
    )
    parser.add_argument("--weights", type=Path, required=True, help="Path to .pt or .onnx detector")
    parser.add_argument("--source", type=str, default="0", help="Camera index (e.g. 0) or image path")
    parser.add_argument("--class-map", type=Path, default=repo_root / "config" / "class_map.json", help="Path to class_map.json")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--backend-url", type=str, default="http://192.168.137.1:8080/api/v1/analysis")
    parser.add_argument("--user-id", type=str, default="pi_usb_cam_001")
    parser.add_argument("--device-id", type=str, default="raspberrypi-usb-cam")
    parser.add_argument("--heart-rate", type=int, default=75)
    parser.add_argument("--spo2", type=int, default=98)
    parser.add_argument("--capture-dir", type=Path, default=repo_root / "data" / "captures")
    parser.add_argument("--media-failure-dir", type=Path, default=repo_root / "data" / "pending_media_uploads")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--repeat", type=int, default=1, help="Repeat inference N times for simple benchmark")
    parser.add_argument("--upload-image", action="store_true", help="Upload captured image to backend as tongueImage")
    parser.add_argument("--skip-upload", action="store_true", help="Only run capture/inference locally")
    parser.add_argument("--sensor-reading", action="append", default=[], help="Extra sensor reading, key=value")
    parser.add_argument("--media-upload-mode", choices=["none", "aliyun-oss"], default="none", help="Optional cloud media upload mode")
    parser.add_argument("--oss-endpoint", type=str, default=None, help="Aliyun OSS endpoint host or full URL")
    parser.add_argument("--oss-bucket", type=str, default=None, help="Aliyun OSS bucket name")
    parser.add_argument("--oss-prefix", type=str, default="smarttcm/edge", help="Object key prefix under bucket")
    parser.add_argument("--oss-region", type=str, default=None, help="Aliyun OSS region")
    parser.add_argument("--oss-auth-mode", choices=["presigned", "sts"], default="presigned", help="Aliyun OSS upload auth mode")
    parser.add_argument("--media-public-base-url", type=str, default=None, help="Optional public URL base for uploaded cloud images")
    parser.add_argument("--oss-presigned-url", type=str, default=None, help="Reserved presigned upload URL for current phase")
    return parser


def load_class_map(path: Path) -> dict[int, str]:
    with path.open("r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    return {item["remapped_id"]: item["canonical_label"] for item in data["classes"]}


def parse_sensor_readings(items: list[str]) -> dict[str, float]:
    readings: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid sensor reading '{item}', expected key=value")
        key, value = item.split("=", 1)
        readings[key.strip()] = float(value.strip())
    return readings


def capture_frame(source: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if source.isdigit():
        cap = cv2.VideoCapture(int(source))
        try:
            if not cap.isOpened():
                raise RuntimeError(f"Failed to open camera index {source}")
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Camera read failed")
            cv2.imwrite(str(output_path), frame)
        finally:
            cap.release()
        return output_path

    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source image not found: {source_path}")
    return source_path


def predict_labels(weights: Path, source_path: Path, class_map: dict[int, str], imgsz: int, conf: float, device: str) -> tuple[dict[str, Any], list[float]]:
    from ultralytics import YOLO

    task = "detect" if weights.suffix.lower() == ".onnx" else None
    model = YOLO(str(weights), task=task) if task else YOLO(str(weights))

    timings_ms: list[float] = []
    label_conf: OrderedDict[str, float] = OrderedDict()
    repeats = getattr(predict_labels, "_repeat_count", 1)
    last_result = None
    for _ in range(repeats):
        start = time.perf_counter()
        results = model.predict(
            source=str(source_path),
            conf=conf,
            imgsz=imgsz,
            device=device,
            verbose=False,
            save=False,
            exist_ok=True,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings_ms.append(round(elapsed_ms, 2))
        if not results:
            raise RuntimeError("No inference result returned")
        last_result = results[0]

    assert last_result is not None
    boxes = last_result.boxes
    if boxes is not None:
        for class_id_tensor, conf_tensor in zip(boxes.cls, boxes.conf):
            class_id = int(class_id_tensor.item())
            canonical = class_map.get(class_id, str(last_result.names.get(class_id, class_id)))
            confidence = round(float(conf_tensor.item()), 4)
            previous = label_conf.get(canonical, 0.0)
            if confidence > previous:
                label_conf[canonical] = confidence

    speed = dict(last_result.speed or {})
    speed["wallInferenceMs"] = round(sum(timings_ms) / len(timings_ms), 2)
    speed["benchmarkRuns"] = len(timings_ms)
    return {
        "tongueLabels": list(label_conf.keys()),
        "tongueDescription": "Detected tongue labels: " + ", ".join(label_conf.keys()) if label_conf else "No tongue labels detected",
        "tongueConfidences": label_conf,
        "speed": speed,
    }, timings_ms


def create_media_uploader(args: argparse.Namespace) -> MediaUploader:
    if args.media_upload_mode == "aliyun-oss":
        return AliyunOssMediaUploader(
            endpoint=args.oss_endpoint,
            bucket=args.oss_bucket,
            prefix=args.oss_prefix,
            region=args.oss_region,
            auth_mode=args.oss_auth_mode,
            public_base_url=args.media_public_base_url,
            presigned_url=args.oss_presigned_url,
        )
    return LocalOnlyMediaUploader()


def upload_result(backend_url: str, payload: dict[str, Any], image_path: Path | None) -> dict[str, Any]:
    data = {"payload": json.dumps(payload, ensure_ascii=False)}
    files = None
    if image_path is not None:
        files = {"tongueImage": (image_path.name, image_path.open("rb"), "image/jpeg")}
    try:
        response = requests.post(backend_url, data=data, files=files, timeout=120)
        response.raise_for_status()
        return response.json()
    finally:
        if files is not None:
            files["tongueImage"][1].close()


def queue_failed_media_upload(queue_dir: Path, image_path: Path, metadata: dict[str, Any]) -> Path:
    queue_dir.mkdir(parents=True, exist_ok=True)
    queue_name = f"media_upload_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    queue_path = queue_dir / queue_name
    payload = {
        "imagePath": str(image_path),
        "createdAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "metadata": metadata,
    }
    queue_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return queue_path


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    class_map = load_class_map(args.class_map.resolve())
    sensor_readings = parse_sensor_readings(args.sensor_reading)
    media_uploader = create_media_uploader(args)

    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    capture_name = datetime.now().strftime("usb_cam_%Y%m%d_%H%M%S.jpg")
    capture_path = (args.capture_dir / capture_name).resolve()
    source_path = capture_frame(args.source, capture_path)

    predict_labels._repeat_count = max(1, args.repeat)
    inference_payload, timings_ms = predict_labels(
        weights=args.weights.resolve(),
        source_path=source_path,
        class_map=class_map,
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
    )

    media_result = MediaUploadResult(storage="local")
    media_upload_error = None
    queued_media_upload = None
    if args.media_upload_mode != "none":
        try:
            media_result = media_uploader.upload_media(source_path)
        except Exception as ex:
            media_upload_error = str(ex)
            queued_path = queue_failed_media_upload(
                args.media_failure_dir,
                source_path,
                {
                    "mode": args.media_upload_mode,
                    "ossEndpoint": args.oss_endpoint,
                    "ossBucket": args.oss_bucket,
                    "ossPrefix": args.oss_prefix,
                    "ossRegion": args.oss_region,
                    "ossAuthMode": args.oss_auth_mode,
                    "mediaPublicBaseUrl": args.media_public_base_url,
                    "error": media_upload_error,
                },
            )
            queued_media_upload = str(queued_path)

    payload: dict[str, Any] = {
        "userId": args.user_id,
        "source": "device",
        "deviceId": args.device_id,
        "capturedAt": ts,
        "heartRate": args.heart_rate,
        "spo2": args.spo2,
        "tongueLabels": inference_payload["tongueLabels"],
        "tongueDescription": inference_payload["tongueDescription"],
        "sensorReadings": sensor_readings,
        "tongueImagePath": str(source_path),
        "notes": json.dumps(
            {
                "weights": str(args.weights.resolve()),
                "sourceImage": str(source_path),
                "speed": inference_payload["speed"],
                "timingsMs": timings_ms,
                "mediaUploadMode": args.media_upload_mode,
                "mediaUploadError": media_upload_error,
                "queuedMediaUpload": queued_media_upload,
            },
            ensure_ascii=False,
        ),
    }
    if inference_payload["tongueConfidences"]:
        payload["tongueConfidences"] = dict(inference_payload["tongueConfidences"])

    if media_result.storage != "local":
        payload["mediaStorage"] = media_result.storage
    if media_result.url:
        payload["cloudImageUrl"] = media_result.url
    if media_result.object_key:
        payload["cloudImageObjectKey"] = media_result.object_key
    if media_result.bucket:
        payload["cloudImageBucket"] = media_result.bucket

    result = {
        "capturePath": str(source_path),
        "inference": inference_payload,
        "payload": payload,
        "mediaUpload": {
            "mode": args.media_upload_mode,
            "storage": media_result.storage,
            "url": media_result.url,
            "objectKey": media_result.object_key,
            "bucket": media_result.bucket,
            "error": media_upload_error,
            "queuedPath": queued_media_upload,
        },
        "backendResponse": None,
    }

    if not args.skip_upload:
        result["backendResponse"] = upload_result(
            backend_url=args.backend_url,
            payload=payload,
            image_path=source_path if args.upload_image else None,
        )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
