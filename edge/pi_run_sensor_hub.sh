#!/bin/bash
set -euo pipefail

ARGS=()
if [[ "${MOCK_SENSORS:-}" == "1" ]]; then
  ARGS+=(--mock)
fi

exec /home/pi/SmartTCM/venv/bin/python /home/pi/SmartTCM/edge/smarttcm_sensor_hub.py \
  --device-id "${DEVICE_ID:-raspberrypi5-edge}" \
  --backend-url "${BACKEND_URL:-http://192.168.137.1:18080/api/v1/edge/telemetry}" \
  --sample-interval "${SAMPLE_INTERVAL:-1.0}" \
  --upload-interval "${UPLOAD_INTERVAL:-2.0}" \
  --port "${PORT:-8091}" \
  "${ARGS[@]}"
