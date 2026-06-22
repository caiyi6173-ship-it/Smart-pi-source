#!/bin/bash
set -euo pipefail

SOURCE_SKILL_DIR="/home/pi/smartpi/openclaw/skills/smartpi-edge-control"
WORKSPACE_SKILL_ROOT="/home/pi/smartpi/openclaw/skills/smartpi-edge-control"
GLOBAL_SKILL_ROOT="${HOME}/.openclaw/skills/smartpi-edge-control"

mkdir -p "$WORKSPACE_SKILL_ROOT"
mkdir -p "$GLOBAL_SKILL_ROOT"
if [[ "$SOURCE_SKILL_DIR" != "$WORKSPACE_SKILL_ROOT" ]]; then
  cp -f "$SOURCE_SKILL_DIR/SKILL.md" "$WORKSPACE_SKILL_ROOT/SKILL.md"
fi
cp -f "$SOURCE_SKILL_DIR/SKILL.md" "$GLOBAL_SKILL_ROOT/SKILL.md"

cat <<EOF
smartpi OpenClaw skill 已安装到：
1) Workspace skills (优先):
   $WORKSPACE_SKILL_ROOT
2) Global skills:
   $GLOBAL_SKILL_ROOT

如果 OpenClaw 已在运行，建议执行：
1. openclaw gateway restart
2. openclaw status
3. 在 /home/pi/smartpi/openclaw 目录运行一次测试：
   /home/pi/smartpi/openclaw/run_openclaw_message.sh "打开摄像头识别"
EOF
