#!/bin/bash
set -euo pipefail

MESSAGE="${1:-}"
if [[ -z "$MESSAGE" ]]; then
  echo "我还没有听到你的问题，请再说一次。"
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${SCRIPT_DIR}}"
cd "$WORKSPACE_DIR"

PROMPT=$(cat <<EOF
你是 smartpi 的语音助手。请优先结合已经安装的 smartpi-edge-control skill，自主判断是否需要触发 smartpi 动作。
规则：
1. 正常回复请保持自然中文，不要 Markdown，不要代码块。
2. 如果判断需要执行 smartpi 动作，请在回复末尾单独追加一行动作标记，例如：[[SMARTPI_ACTION:camera.start]]
3. 动作名只能从以下白名单中选择：
camera.start
camera.stop
sensor.temperature.start
sensor.temperature.stop
sensor.pulseox.start
sensor.pulseox.stop
telemetry.temperature.read
telemetry.pulseox.read
analysis.latest
analysis.trigger
4. 如果是闲聊、解释、安抚或不需要设备动作，就不要追加动作标记。
用户原话：$MESSAGE
EOF
)

exec openclaw agent --local --agent main --message "$PROMPT" --timeout "${OPENCLAW_TIMEOUT_SECONDS:-12}"
