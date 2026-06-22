#!/bin/bash
set -euo pipefail

CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-/home/pi/.openclaw/openclaw.json}"
PROVIDER_ID="${OPENCLAW_PROVIDER_ID:-alibaba-cloud}"
MODEL_ID="${OPENCLAW_MODEL_ID:-qwen3-max-2026-01-23}"
MODEL_NAME="${OPENCLAW_MODEL_NAME:-${MODEL_ID}}"
MODEL_BASE_URL="${OPENCLAW_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}"
MODEL_API_KEY="${OPENCLAW_API_KEY:-}"
MODEL_API="${OPENCLAW_MODEL_API:-openai-completions}"
MODEL_CONTEXT_WINDOW="${OPENCLAW_CONTEXT_WINDOW:-262144}"
MODEL_MAX_TOKENS="${OPENCLAW_MAX_TOKENS:-8192}"
RESET_SESSIONS="${OPENCLAW_RESET_SESSIONS:-1}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "OpenClaw 配置不存在：$CONFIG_PATH" >&2
  exit 1
fi

python3 - "$CONFIG_PATH" "$PROVIDER_ID" "$MODEL_ID" "$MODEL_NAME" "$MODEL_BASE_URL" "$MODEL_API_KEY" "$MODEL_API" "$MODEL_CONTEXT_WINDOW" "$MODEL_MAX_TOKENS" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
provider_id = sys.argv[2]
model_id = sys.argv[3]
model_name = sys.argv[4]
base_url = sys.argv[5]
api_key = sys.argv[6]
model_api = sys.argv[7]
context_window = int(sys.argv[8])
max_tokens = int(sys.argv[9])

config = json.loads(config_path.read_text(encoding="utf-8"))
models = config.setdefault("models", {}).setdefault("providers", {})
provider = models.setdefault(provider_id, {})
provider["baseUrl"] = base_url
provider["api"] = model_api
if api_key:
    provider["apiKey"] = api_key
provider["models"] = [{
    "id": model_id,
    "name": model_name,
    "reasoning": False,
    "input": ["text"],
    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
    "contextWindow": context_window,
    "maxTokens": max_tokens,
    "api": model_api,
}]
config.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})["primary"] = f"{provider_id}/{model_id}"
config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ "$RESET_SESSIONS" == "1" ]]; then
  sessions_dir="/home/pi/.openclaw/agents/main/sessions"
  if [[ -d "$sessions_dir" ]]; then
    backup_dir="${sessions_dir}.bak.$(date +%Y%m%d%H%M%S)"
    mv "$sessions_dir" "$backup_dir"
    mkdir -p "$sessions_dir"
    echo '{"sessions":[]}' > "$sessions_dir/sessions.json"
    echo "已备份旧会话到：$backup_dir"
  fi
fi

echo "OpenClaw 模型已更新为 ${PROVIDER_ID}/${MODEL_ID}"
