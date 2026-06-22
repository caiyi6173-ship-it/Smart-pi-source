#!/bin/bash
set -euo pipefail

sudo apt update
sudo apt install -y git curl build-essential

if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
  sudo apt install -y nodejs
fi

if ! command -v openclaw >/dev/null 2>&1; then
  curl -fsSL https://openclaw.ai/install.sh | bash
fi

cat <<EOF
OpenClaw 已安装完成（如上方未报错）。
下一步建议执行：
1. openclaw onboard --install-daemon
2. 完成 Gateway 初始化
3. 安装 smartpi skill：
   /home/pi/smartpi/edge/pi_install_smartpi_openclaw_skill.sh
4. 如需切换到百炼模型，可执行：
   /home/pi/smartpi/edge/pi_configure_openclaw_model.sh
EOF
