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
        echo "  uvicorn already running on :8000 — skip"
    else
        start_component "starting uvicorn"
        .venv/bin/uvicorn app.main:app --port 8000 > "$LOGDIR/uvicorn.log" 2>&1 &
        for i in $(seq 1 15); do
            running 8000 && break
            sleep 1
        done
        running 8000 && echo "  uvicorn ready" || echo "  !! uvicorn failed to start — check $LOGDIR/uvicorn.log"
    fi

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
    echo " Quant Copilot is running"
    echo "=============================="
    echo "  Frontend : http://localhost:3000"
    echo "  Backend  : http://localhost:8000/docs"
    echo "  Logs     : $LOGDIR/"
    echo ""
    if running 8000 && running 3000; then
        curl -sf http://localhost:8000/health >/dev/null 2>&1 \
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
