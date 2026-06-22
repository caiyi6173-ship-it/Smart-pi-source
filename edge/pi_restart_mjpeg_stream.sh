#!/bin/bash
set -euo pipefail

PROFILE="${1:-low-latency}"
SERVICE_NAME="smartpi-edge-stream.service"
START_SCRIPT="/home/pi/smartpi/edge/pi_start_mjpeg_stream.sh"

echo "Restarting ${SERVICE_NAME} with profile: ${PROFILE}"

bash "${START_SCRIPT}" "${PROFILE}"

echo
echo "Health check:"
curl -s --max-time 8 http://127.0.0.1:8081/health || true
