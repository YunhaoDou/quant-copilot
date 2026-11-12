#!/bin/bash
# 登录后启动策略后端，失败时由 launchd 重试。
set -e
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
project="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$project/backend"

if ! /opt/homebrew/opt/postgresql@16/bin/pg_isready -q; then
    /opt/homebrew/bin/brew services start postgresql@16
fi
if ! /opt/homebrew/bin/redis-cli ping >/dev/null 2>&1; then
    /opt/homebrew/bin/brew services start redis
fi
for attempt in {1..20}; do
    if /opt/homebrew/opt/postgresql@16/bin/pg_isready -q && /opt/homebrew/bin/redis-cli ping >/dev/null 2>&1; then
        # caffeinate 随后端生命周期保持空闲唤醒，允许显示器正常关闭。
        exec /usr/bin/caffeinate -i "$project/backend/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    fi
    sleep 1
done
echo "本地数据库或Redis未就绪，等待launchd重试。" >&2
exit 1
