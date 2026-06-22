#!/bin/bash
set -euo pipefail

VENV_PYTHON="/home/pi/smartpi/venv/bin/python"
MODEL_NAME="${PIPER_VOICE_NAME:-zh_CN-huayan-medium}"
MODEL_DIR="${PIPER_MODEL_DIR:-/home/pi/smartpi/models/piper}"
CACHE_DIR="${TTS_CACHE_DIR:-/home/pi/smartpi/cache/tts}"
WHISPER_MODEL="${FASTER_WHISPER_MODEL:-tiny}"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
HF_HOME="${HF_HOME:-/home/pi/smartpi/cache/huggingface}"
PIPER_BASE_URL="${PIPER_DOWNLOAD_BASE_URL:-$HF_ENDPOINT/rhasspy/piper-voices/resolve/main}"
KWS_MODEL_NAME="${SHERPA_KWS_MODEL_NAME:-sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01}"
KWS_MODEL_PARENT="${SHERPA_KWS_MODEL_PARENT:-/home/pi/smartpi/models/kws}"
KWS_MODEL_DIR="${SHERPA_KWS_MODEL_DIR:-$KWS_MODEL_PARENT/$KWS_MODEL_NAME}"
KWS_DOWNLOAD_URL="${SHERPA_KWS_DOWNLOAD_URL:-https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/${KWS_MODEL_NAME}.tar.bz2}"

mkdir -p "$MODEL_DIR" "$CACHE_DIR" "$HF_HOME" "$KWS_MODEL_PARENT"

if ! command -v ffmpeg >/dev/null 2>&1; then
  sudo apt update
  sudo apt install -y ffmpeg
fi

if ! command -v ffplay >/dev/null 2>&1; then
  sudo apt update
  sudo apt install -y ffmpeg
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip uninstall -y piper-tts piper >/dev/null 2>&1 || true
"$VENV_PYTHON" -m pip install faster-whisper webrtcvad-wheels piper-tts pathvalidate sentencepiece pypinyin sherpa-onnx sherpa-onnx-bin

if [[ ! -f "$MODEL_DIR/${MODEL_NAME}.onnx" ]]; then
  lang_family="${MODEL_NAME%%_*}"
  rest="${MODEL_NAME#*_}"
  lang_region="${rest%%-*}"
  voice_and_quality="${MODEL_NAME#${lang_family}_${lang_region}-}"
  voice_name="${voice_and_quality%-*}"
  voice_quality="${voice_and_quality##*-}"
  voice_code="${lang_family}_${lang_region}-${voice_name}-${voice_quality}"
  base_url="${PIPER_BASE_URL}/${lang_family}/${lang_family}_${lang_region}/${voice_name}/${voice_quality}"
  curl -L "${base_url}/${voice_code}.onnx?download=true" -o "$MODEL_DIR/${voice_code}.onnx"
  curl -L "${base_url}/${voice_code}.onnx.json?download=true" -o "$MODEL_DIR/${voice_code}.onnx.json"
fi

export HF_ENDPOINT
export HF_HOME
export FASTER_WHISPER_MODEL="$WHISPER_MODEL"
export FASTER_WHISPER_COMPUTE_TYPE="${FASTER_WHISPER_COMPUTE_TYPE:-int8}"
if [[ ! -d "$HF_HOME/models--Systran--faster-whisper-${WHISPER_MODEL}" ]]; then
  "$VENV_PYTHON" - <<'PY'
import os
from faster_whisper import WhisperModel

model_name = os.environ.get("FASTER_WHISPER_MODEL", "base")
compute_type = os.environ.get("FASTER_WHISPER_COMPUTE_TYPE", "int8")
hf_home = os.environ.get("HF_HOME", "/home/pi/smartpi/cache/huggingface")
WhisperModel(model_name, device="cpu", compute_type=compute_type, download_root=hf_home)
print(f"Downloaded faster-whisper model: {model_name}")
PY
fi

if [[ ! -f "$KWS_MODEL_DIR/tokens.txt" ]]; then
  archive_path="/tmp/${KWS_MODEL_NAME}.tar.bz2"
  curl -L "$KWS_DOWNLOAD_URL" -o "$archive_path"
  tar -xjf "$archive_path" -C "$KWS_MODEL_PARENT"
  rm -f "$archive_path"
fi

cat <<EOF
Local voice stack installation completed.
Recommended values in /home/pi/smartpi/config/voice_agent.env:
ENABLE_LOCAL_STT=1
ENABLE_LOCAL_TTS=1
ENABLE_WEBRTCVAD=1
HF_ENDPOINT=$HF_ENDPOINT
HF_HOME=$HF_HOME
PIPER_COMMAND=/home/pi/smartpi/venv/bin/python -m piper
PIPER_MODEL_PATH=$MODEL_DIR/${MODEL_NAME}.onnx
PIPER_CONFIG_PATH=$MODEL_DIR/${MODEL_NAME}.onnx.json
TTS_CACHE_DIR=$CACHE_DIR
ENABLE_KEYWORD_SPOTTER=1
SHERPA_KWS_COMMAND=/home/pi/smartpi/venv/bin/sherpa-onnx-keyword-spotter
SHERPA_KWS_CLI=/home/pi/smartpi/venv/bin/sherpa-onnx-cli
SHERPA_KWS_MODEL_DIR=$KWS_MODEL_DIR
SHERPA_KWS_TOKENS_TYPE=${SHERPA_KWS_TOKENS_TYPE:-}
SHERPA_KWS_KEYWORDS_THRESHOLD=${SHERPA_KWS_KEYWORDS_THRESHOLD:-0.35}
SHERPA_KWS_KEYWORDS_SCORE=${SHERPA_KWS_KEYWORDS_SCORE:-1.8}
SHERPA_KWS_NUM_THREADS=${SHERPA_KWS_NUM_THREADS:-2}

Then restart:
sudo systemctl restart smartpi-voice-agent.service
EOF
