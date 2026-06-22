#!/bin/bash
set -euo pipefail

PROFILE="${PROFILE:-low-latency}"
SOURCE="${SOURCE:-0}"
INFERENCE_INTERVAL_MS=450

case "$PROFILE" in
  high-accuracy)
    INFERENCE_INTERVAL_MS=180
    ;;
  low-latency)
    INFERENCE_INTERVAL_MS=450
    ;;
  *)
    echo "Unknown profile: $PROFILE" >&2
    exit 1
    ;;
esac

exec /home/pi/smartpi/venv/bin/python /home/pi/smartpi/edge/pi_mjpeg_stream_server.py \
  --weights /home/pi/smartpi/models/tongue_best.onnx \
  --source "${SOURCE}" \
  --class-map /home/pi/smartpi/config/class_map.json \
  --device cpu \
  --imgsz 640 \
  --jpeg-quality 65 \
  --frame-interval-ms 40 \
  --inference-interval-ms "${INFERENCE_INTERVAL_MS}" \
  --camera-width 640 \
  --camera-height 480 \
  --camera-buffer-size 1 \
  --port 8081
