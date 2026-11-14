#!/bin/bash
# Quant Copilot — one-command startup.
# Usage: ./start.sh          (start everything)
#        ./start.sh backend  (API + Celery only)
#        ./start.sh frontend (Next.js only)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
LOGDIR="$BACKEND_DIR/logs"
mkdir -p "$LOGDIR"
source "$ROOT/scripts/service-lock.sh"
quant_lock_acquire "$LOGDIR/stack-start.lock"

# ---- helpers ----
running() { lsof -i ":$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

start_component() { echo "  [$(date +%H:%M:%S)] $1"; }

# ---- infrastructure ----
start_infra() {
    echo "=== Infrastructure ==="
    if ! pgrep -x postgres >/dev/null 2>&1; then
        start_component "starting postgresql@16"
        brew services start postgresql@16 >/dev/null 2>&1
        sleep 2
    else
        echo "  postgresql already running"
    fi
    if ! pgrep -x redis-server >/dev/null 2>&1; then
        start_component "starting redis"
        brew services start redis >/dev/null 2>&1
        sleep 1
    else
        echo "  redis already running"
    fi
}

# ---- backend ----
start_backend() {
    echo "=== Backend (port 8000) ==="
    cd "$BACKEND_DIR"
    if [ ! -d ".venv" ]; then
        start_component "creating venv + installing deps"
        python3 -m venv .venv
        .venv/bin/pip install -e ".[dev]" -q
    fi
    if running 8000; then
        echo "  API端口已监听，核验数据库与Redis就绪状态"
    elif launchctl print "gui/$(id -u)/com.quantcopilot.resident" >/dev/null 2>&1; then
        # 已注册驻留服务时只唤起同一实例，避免与launchd同时启动第二个后端。
        start_component "等待既有后台服务恢复"
        launchctl kickstart "gui/$(id -u)/com.quantcopilot.resident" || true
    else
        start_component "starting uvicorn"
        nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$LOGDIR/uvicorn.log" 2>&1 < /dev/null &
    fi
    if ! .venv/bin/python "$ROOT/scripts/wait-api.py" --timeout 60; then
        echo "  后台未就绪，停止启动流程；请检查 $LOGDIR/" >&2
        return 1
    fi
    echo "  API与依赖已就绪"

    # Celery worker
    if pgrep -f "celery.*worker" >/dev/null 2>&1; then
        echo "  celery worker already running — skip"
    else
        start_component "starting celery worker"
        .venv/bin/celery -A app.tasks.celery_app worker --loglevel=info > "$LOGDIR/celery.log" 2>&1 &
        echo "  celery worker started (pid $!)"
    fi

    # Celery beat (scheduled tasks, e.g. the earnings pipeline)
    if pgrep -f "celery.*beat" >/dev/null 2>&1; then
        echo "  celery beat already running — skip"
    else
        start_component "starting celery beat"
        .venv/bin/celery -A app.tasks.celery_app beat --loglevel=info > "$LOGDIR/celery-beat.log" 2>&1 &
        echo "  celery beat started (pid $!)"
    fi
}

# ---- frontend ----
start_frontend() {
    echo "=== Frontend (port 3000) ==="
    cd "$FRONTEND_DIR"
    if [ ! -d "node_modules" ]; then
        start_component "installing npm deps"
        npm install --silent
    fi
    bash "$ROOT/scripts/frontend-service.sh"

}

# ---- summary ----
summary() {
    echo ""
    echo "=============================="
    echo " Quant Copilot services ready"
    echo "=============================="
    echo "  Frontend : http://localhost:3000"
    echo "  Backend  : http://localhost:8000/docs"
    echo "  Logs     : $LOGDIR/"
    echo ""
    if running 8000 && running 3000; then
        "$BACKEND_DIR/.venv/bin/python" "$ROOT/scripts/wait-api.py" --timeout 2 >/dev/null 2>&1 \
            && echo "  Health   : OK" \
            || echo "  Health   : backend not healthy"
    fi
}

# ---- main ----
MODE="${1:-all}"
case "$MODE" in
    all)
        start_infra
        start_backend
        start_frontend
        summary
        ;;
    backend)
        start_infra
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    *)
        echo "Usage: ./start.sh [all|backend|frontend]"
        exit 1
        ;;
esac
