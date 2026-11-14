#!/bin/bash
# 显式重启同一后台服务；重建launchd任务以清除本次手动重启的30秒节流。
set -euo pipefail
project="$(cd "$(dirname "$0")/.." && pwd)"
service="gui/$(id -u)/com.quantcopilot.resident"
launchctl print "$service" >/dev/null
mkdir -p "$project/backend/logs"
checkpoint="$project/backend/logs/account-restart-checkpoint.json"
"$project/backend/.venv/bin/python" "$project/scripts/account-checkpoint.py" capture --database "$project/backend/data/cycle/events.sqlite" --checkpoint "$checkpoint"
previous="$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"
origin="$("$project/backend/.venv/bin/python" -c 'import time;print(time.monotonic())')"
phase(){ "$project/backend/.venv/bin/python" -c 'import time,sys,json;print(json.dumps({"phase":sys.argv[1],"seconds":round(time.monotonic()-float(sys.argv[2]),3)},ensure_ascii=False))' "$1" "$origin"; }
echo '正在重启后台，账户和历史数据保留…'
phase request
plist="$HOME/Library/LaunchAgents/com.quantcopilot.resident.plist"
[ -f "$plist" ] || { echo "找不到既有后台服务配置" >&2;exit 1; }
# 原配置不改动，崩溃自动恢复仍保留原节流；仅本次显式部署重新注册。
launchctl bootout "$service"
phase unregistered
restore(){ launchctl bootstrap "gui/$(id -u)" "$plist" >/dev/null 2>&1 || true; }
trap restore EXIT
for n in {1..40}; do
    [ -z "$previous" ] || ! kill -0 "$previous" 2>/dev/null && break
    sleep .25
done
if [ -n "$previous" ] && kill -0 "$previous" 2>/dev/null; then
    trap - EXIT
    echo "旧后台尚未退出，停止切换以避免两个执行者；退出后可重试注册" >&2;exit 1
fi
phase old_process_exited
launchctl bootstrap "gui/$(id -u)" "$plist"
phase registered
trap - EXIT
mkdir -p "$project/backend/logs"
"$project/backend/.venv/bin/python" "$project/scripts/wait-api.py" --timeout 60 --previous-pid "$previous" --elapsed-origin "$origin" | tee "$project/backend/logs/restart-latest.json"

"$project/backend/.venv/bin/python" "$project/scripts/account-checkpoint.py" check --database "$project/backend/data/cycle/events.sqlite" --checkpoint "$checkpoint"
