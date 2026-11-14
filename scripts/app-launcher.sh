#!/bin/bash
set -e
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
project="$HOME/quant-copilot"
dashboard="http://localhost:3000/invest"
health="http://localhost:8000/health"
logs="$HOME/Library/Logs"
log="$logs/Quant Copilot Launcher.log"

mkdir -p "$logs"
ready() {
  "$project/backend/.venv/bin/python" "$project/scripts/wait-api.py" --timeout 3 >/dev/null 2>&1 &&
    /usr/bin/curl -fsS --max-time 15 "$dashboard" >/dev/null 2>&1
}

if [ ! -x "$project/start.sh" ]; then
  printf '找不到启动脚本：%s/start.sh\n' "$project" >&2
  exit 1
fi

if ! ready; then
  if ! "$project/start.sh" >>"$log" 2>&1; then
    printf '启动脚本运行失败。日志：%s\n' "$log" >&2
    exit 1
  fi
  for attempt in {1..10}; do
    ready && break
    sleep 2
  done
fi

if ! ready; then
  printf '前端或后端未就绪。启动日志：%s\n服务日志：%s/backend/logs/\n' "$log" "$project" >&2
  exit 1
fi

/usr/bin/open "$dashboard"
printf '[%s] 驾驶舱已交给默认浏览器打开。\n' "$(date '+%F %T')" >>"$log"
