#!/bin/bash
set -euo pipefail

MESSAGE="${1:-}"
if [[ -z "$MESSAGE" ]]; then
  echo "Please provide the user utterance for OpenClaw." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_WORKSPACE="/home/pi/smartpi/openclaw"
if [[ -d "$OPENCLAW_WORKSPACE" ]]; then
  cd "$OPENCLAW_WORKSPACE"
else
  cd "$SCRIPT_DIR"
fi

PROMPT=$(cat <<EOF
You are smartpi's conversational edge assistant.
Prefer using the installed skill smartpi-edge-control.
When an edge action is needed, append one marker line at the end:
[[SMARTPI_ACTION:camera.start]]
For chat requests, respond naturally without marker.
Return plain text only.

User utterance:
$MESSAGE
EOF
)

exec openclaw agent --local --agent main --message "$PROMPT" --timeout "${OPENCLAW_TIMEOUT_SECONDS:-18}"
