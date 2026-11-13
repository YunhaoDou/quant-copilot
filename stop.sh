#!/bin/bash
# Quant Copilot — stop all services started by start.sh.
set -e

echo "=== Stopping Quant Copilot ==="

# Celery worker
if pkill -f "celery.*worker" 2>/dev/null; then
    echo "  celery worker stopped"
else
    echo "  celery worker not running"
fi

# Uvicorn (backend)
if pkill -f "uvicorn app.main:app" 2>/dev/null; then
    echo "  uvicorn stopped"
else
    echo "  uvicorn not running"
fi

# Next.js生产服务（只移除本项目托管的服务）
launchctl remove com.quantcopilot.frontend >/dev/null 2>&1 || true

# Next.js dev server
if pkill -f "next dev" 2>/dev/null; then
    echo "  next.js stopped"
else
    echo "  next.js not running"
fi

# Infrastructure (leave running by default — comment out to stop everything)
# brew services stop postgresql@16
# brew services stop redis

echo "Done."
