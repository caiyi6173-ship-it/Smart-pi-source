#!/bin/bash
set -euo pipefail

PROFILE="${1:-low-latency}"
ENV_FILE="/home/pi/smartpi/config/mjpeg_stream.env"
SERVICE_NAME="smartpi-edge-stream.service"

case "$PROFILE" in
  high-accuracy|low-latency)
    ;;
  *)
    echo "Unknown profile: $PROFILE" >&2
    exit 1
    ;;
esac

mkdir -p /home/pi/smartpi/config /home/pi/smartpi/data/results

cat > "$ENV_FILE" <<EOF
PROFILE=$PROFILE
EOF

sudo systemctl restart "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME"
