#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/pi/smartpi/rag}"
SERVICE_NAME="smartpi-rag.service"
SERVICE_SRC="$APP_DIR/deploy/$SERVICE_NAME"
SERVICE_DST="/etc/systemd/system/$SERVICE_NAME"

mkdir -p "$APP_DIR/data/raw" "$APP_DIR/data/processed" "$APP_DIR/data/chroma" "$APP_DIR/data/qdrant"
mkdir -p /home/pi/smartpi/data/results

cd "$APP_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
if ! python -m pip install -r requirements.txt; then
  echo "Full requirements install failed, falling back to core runtime dependencies."
  python -m pip install \
    fastapi \
    "uvicorn[standard]" \
    pydantic \
    pydantic-settings \
    python-dotenv \
    openai \
    qdrant-client \
    python-docx \
    pypdf \
    beautifulsoup4 \
    httpx
fi

sudo cp "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo "Bootstrap complete for $APP_DIR"
