#!/bin/bash
set -euo pipefail

sudo systemctl stop smartpi-edge-stream.service
sudo systemctl --no-pager --full status smartpi-edge-stream.service || true
