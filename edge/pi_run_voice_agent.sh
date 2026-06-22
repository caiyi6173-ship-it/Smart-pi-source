#!/bin/bash
set -euo pipefail

resolve_record_device() {
  if [[ -n "${RECORD_DEVICE:-}" && "${RECORD_DEVICE}" != "default" ]]; then
    printf '%s\n' "${RECORD_DEVICE}"
    return
  fi

  if arecord -L 2>/dev/null | grep -qx 'plughw:CARD=WebCamera,DEV=0'; then
    printf '%s\n' 'plughw:CARD=WebCamera,DEV=0'
    return
  fi

  if arecord -L 2>/dev/null | grep -qx 'sysdefault:CARD=WebCamera'; then
    printf '%s\n' 'sysdefault:CARD=WebCamera'
    return
  fi

  printf '%s\n' 'default'
}

resolve_playback_device() {
  if [[ -n "${PLAYBACK_DEVICE:-}" && "${PLAYBACK_DEVICE}" != "default" ]]; then
    printf '%s\n' "${PLAYBACK_DEVICE}"
    return
  fi

  if aplay -L 2>/dev/null | grep -qx 'plughw:CARD=MAX98357A,DEV=0'; then
    printf '%s\n' 'plughw:CARD=MAX98357A,DEV=0'
    return
  fi

  if aplay -L 2>/dev/null | grep -qx 'sysdefault:CARD=MAX98357A'; then
    printf '%s\n' 'sysdefault:CARD=MAX98357A'
    return
  fi

  printf '%s\n' 'default'
}

piper_command_path() {
  if [[ -n "${PIPER_COMMAND:-}" ]]; then
    printf '%s\n' "${PIPER_COMMAND}"
    return
  fi

  if [[ -x "/home/pi/SmartTCM/venv/bin/python" ]]; then
    printf '%s\n' '/home/pi/SmartTCM/venv/bin/python -m piper'
    return
  fi

  printf '%s\n' 'piper'
}

RECORD_DEVICE_RESOLVED="$(resolve_record_device)"
PLAYBACK_DEVICE_RESOLVED="$(resolve_playback_device)"
PIPER_COMMAND_RESOLVED="$(piper_command_path)"

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HOME="${HF_HOME:-/home/pi/SmartTCM/cache/huggingface}"
mkdir -p "${HF_HOME}" "${TTS_CACHE_DIR:-/home/pi/SmartTCM/cache/tts}"

ARGS=(
  --bridge-base-url "${BRIDGE_BASE_URL:-http://127.0.0.1:8092}"
  --wake-word "${WAKE_WORD:-小中医}"
  --assistant-name "${ASSISTANT_NAME:-SmartTCM Voice}"
  --record-device "${RECORD_DEVICE_RESOLVED}"
  --playback-device "${PLAYBACK_DEVICE_RESOLVED}"
  --record-seconds "${RECORD_SECONDS:-3}"
  --record-sample-rate "${RECORD_SAMPLE_RATE:-16000}"
  --whisper-model "${FASTER_WHISPER_MODEL:-tiny}"
  --whisper-device "${FASTER_WHISPER_DEVICE:-cpu}"
  --whisper-compute-type "${FASTER_WHISPER_COMPUTE_TYPE:-int8}"
  --whisper-language "${FASTER_WHISPER_LANGUAGE:-zh}"
  --whisper-initial-prompt "${FASTER_WHISPER_INITIAL_PROMPT:-SmartTCM 舌象分析、摄像头识别、心率、血氧、皮肤温度、读取分析结果、重新分析。}"
  --wake-whisper-model "${FASTER_WHISPER_WAKE_MODEL:-tiny}"
  --wake-whisper-compute-type "${FASTER_WHISPER_WAKE_COMPUTE_TYPE:-int8}"
  --wake-whisper-initial-prompt "${FASTER_WHISPER_WAKE_INITIAL_PROMPT:-}"
  --wake-listen-window-seconds "${WAKE_LISTEN_WINDOW_SECONDS:-1.8}"
  --wake-listen-command-seconds "${WAKE_LISTEN_COMMAND_SECONDS:-${COMMAND_MAX_RECORD_SECONDS:-${RECORD_SECONDS:-3}}}"
  --command-max-record-seconds "${COMMAND_MAX_RECORD_SECONDS:-3}"
  --command-silence-stop-ms "${COMMAND_SILENCE_STOP_MS:-700}"
  --command-min-speech-ms "${COMMAND_MIN_SPEECH_MS:-300}"
  --command-rms-threshold "${COMMAND_RMS_THRESHOLD:-220}"
  --wake-rms-threshold "${WAKE_RMS_THRESHOLD:-160}"
  --vad-mode "${VAD_MODE:-1}"
  --vad-frame-ms "${VAD_FRAME_MS:-30}"
  --wake-listen-cooldown-seconds "${WAKE_LISTEN_COOLDOWN_SECONDS:-0.25}"
  --wake-word-aliases "${WAKE_WORD_ALIASES:-}"
  --wake-fuzzy-max-distance "${WAKE_FUZZY_MAX_DISTANCE:-1}"
  --wake-fuzzy-prefix-window-chars "${WAKE_FUZZY_PREFIX_WINDOW_CHARS:-8}"
  --wake-ack-text "${WAKE_ACK_TEXT:-}"
  --dashscope-api-key "${DASHSCOPE_API_KEY:-}"
  --asr-model "${DASHSCOPE_ASR_MODEL:-paraformer-realtime-v2}"
  --tts-model "${DASHSCOPE_TTS_MODEL:-cosyvoice-v2}"
  --tts-voice "${DASHSCOPE_TTS_VOICE:-longxiaochun_v2}"
  --remote-tts-base-url "${REMOTE_TTS_BASE_URL:-}"
  --remote-tts-model "${REMOTE_TTS_MODEL:-tts-1}"
  --remote-tts-voice "${REMOTE_TTS_VOICE:-smarttcm}"
  --remote-tts-timeout-seconds "${REMOTE_TTS_TIMEOUT_SECONDS:-30}"
  --llm-base-url "${DIRECT_LLM_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions}"
  --llm-api-key "${DIRECT_LLM_API_KEY:-${DASHSCOPE_API_KEY:-}}"
  --llm-model "${DIRECT_LLM_MODEL:-qwen3.6-flash-2026-04-16}"
  --llm-timeout-seconds "${DIRECT_LLM_TIMEOUT_SECONDS:-20}"
  --llm-temperature "${DIRECT_LLM_TEMPERATURE:-0.2}"
  --llm-system-prompt "${DIRECT_LLM_SYSTEM_PROMPT:-}"
  --piper-command "${PIPER_COMMAND_RESOLVED}"
  --piper-model-path "${PIPER_MODEL_PATH:-}"
  --piper-config-path "${PIPER_CONFIG_PATH:-}"
  --tts-cache-dir "${TTS_CACHE_DIR:-/home/pi/SmartTCM/cache/tts}"
  --keyword-spotter-command "${SHERPA_KWS_COMMAND:-sherpa-onnx-keyword-spotter}"
  --keyword-spotter-cli-command "${SHERPA_KWS_CLI:-sherpa-onnx-cli}"
  --kws-model-dir "${SHERPA_KWS_MODEL_DIR:-}"
  --kws-tokens-type "${SHERPA_KWS_TOKENS_TYPE:-}"
  --kws-keywords-threshold "${SHERPA_KWS_KEYWORDS_THRESHOLD:-0.35}"
  --kws-keywords-score "${SHERPA_KWS_KEYWORDS_SCORE:-1.8}"
  --kws-num-threads "${SHERPA_KWS_NUM_THREADS:-2}"
  --openclaw-command "${OPENCLAW_COMMAND:-}"
  --openclaw-timeout-seconds "${OPENCLAW_TIMEOUT_SECONDS:-12}"
  --port "${PORT:-8093}"
)

if [[ "${ENABLE_LOCAL_STT:-1}" == "1" ]]; then
  ARGS+=(--enable-local-stt)
fi

if [[ "${ENABLE_LOCAL_TTS:-1}" == "1" ]]; then
  ARGS+=(--enable-local-tts)
fi

if [[ "${ENABLE_CLOUD_SPEECH:-0}" == "1" ]]; then
  ARGS+=(--enable-cloud-speech)
fi

if [[ "${ENABLE_REMOTE_TTS:-0}" == "1" ]]; then
  ARGS+=(--enable-remote-tts)
fi

if [[ "${ENABLE_DIRECT_LLM:-0}" == "1" ]]; then
  ARGS+=(--enable-direct-llm)
fi

if [[ "${ENABLE_WEBRTCVAD:-1}" == "1" ]]; then
  ARGS+=(--enable-webrtcvad)
fi

if [[ "${ENABLE_WAKE_LISTEN:-1}" == "1" ]]; then
  ARGS+=(--enable-wake-listen)
fi

if [[ "${ENABLE_KEYWORD_SPOTTER:-0}" == "1" ]]; then
  ARGS+=(--enable-keyword-spotter)
fi

if [[ "${ENABLE_OPENCLAW:-0}" == "1" ]]; then
  ARGS+=(--enable-openclaw)
fi

exec /home/pi/SmartTCM/venv/bin/python /home/pi/SmartTCM/edge/smarttcm_voice_agent.py "${ARGS[@]}"
