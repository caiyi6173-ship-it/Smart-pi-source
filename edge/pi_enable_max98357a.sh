#!/bin/bash
set -euo pipefail

CONFIG_FILE="/boot/firmware/config.txt"
BACKUP_FILE="${CONFIG_FILE}.bak_smarttcm_$(date +%Y%m%d%H%M%S)"
OVERLAY_LINE="${I2S_OVERLAY_LINE:-dtoverlay=max98357a,no-sdmode}"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "未找到 $CONFIG_FILE，请确认系统是 Raspberry Pi OS Bookworm/兼容布局。" >&2
  exit 1
fi

sudo cp "$CONFIG_FILE" "$BACKUP_FILE"

sudo python3 - <<'PY'
from pathlib import Path
import os

config_path = Path('/boot/firmware/config.txt')
lines = config_path.read_text(encoding='utf-8').splitlines()
overlay_line = os.environ.get('I2S_OVERLAY_LINE', 'dtoverlay=max98357a,no-sdmode')
new_lines = []
seen_i2s = False
seen_overlay = False
for line in lines:
    stripped = line.strip()
    if stripped == 'dtparam=audio=on':
        new_lines.append('#dtparam=audio=on')
        continue
    if stripped == 'dtparam=i2s=on':
        seen_i2s = True
        new_lines.append('dtparam=i2s=on')
        continue
    if stripped.startswith('dtoverlay=max98357a') or stripped == overlay_line:
        seen_overlay = True
        new_lines.append(overlay_line)
        continue
    new_lines.append(line)

if not seen_i2s:
    new_lines.append('dtparam=i2s=on')
if not seen_overlay:
    new_lines.append(overlay_line)

config_path.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
PY

cat <<EOF
MAX98357A I2S 配置已写入：
1. 备份文件：$BACKUP_FILE
2. 已确保存在：dtparam=i2s=on
3. 已确保存在：$OVERLAY_LINE
4. 已注释：dtparam=audio=on

下一步建议：
1. sudo reboot
2. 重启后执行 aplay -l
3. 再用 speaker-test -c 2 -t wav 或 aplay 测试输出
EOF
