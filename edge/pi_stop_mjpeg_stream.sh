#!/bin/bash
set -euo pipefail

sudo systemctl stop smarttcm-edge-stream.service
sudo systemctl --no-pager --full status smarttcm-edge-stream.service || true
