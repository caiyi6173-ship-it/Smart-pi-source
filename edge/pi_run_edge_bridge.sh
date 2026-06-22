#!/bin/bash
set -euo pipefail

exec /home/pi/SmartTCM/venv/bin/python /home/pi/SmartTCM/edge/smarttcm_edge_bridge.py \
  --backend-base-url "${BACKEND_BASE_URL:-http://192.168.137.1:18080}" \
  --stream-base-url "${STREAM_BASE_URL:-http://127.0.0.1:8081}" \
  --sensor-base-url "${SENSOR_BASE_URL:-http://127.0.0.1:8091}" \
  --voice-base-url "${VOICE_BASE_URL:-http://127.0.0.1:8093}" \
  --device-id "${DEVICE_ID:-raspberrypi5-edge}" \
  --user-id "${USER_ID:-front_dashboard_user}" \
  --port "${PORT:-8092}"
