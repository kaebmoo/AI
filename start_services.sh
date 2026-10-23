#!/bin/bash
# start_services.sh — run everything NT AI Assistant needs on a dev machine (macOS)
#
#   ./start_services.sh            start all (backend, celery, user frontend, admin UI)
#   ./start_services.sh stop       stop all
#   ./start_services.sh status     show which ports are up
#   ./start_services.sh setup      first-time install: venv + pip + npm + init_db
#
# Redis is shared across projects → start it yourself (brew services start redis); this only checks it.
# Each service opens in its own Terminal window so logs stay visible.
# ponytail: macOS Terminal via osascript only; use the VS Code tasks (.vscode/tasks.json) elsewhere.

cd "$(dirname "$0")" || exit 1
ROOT=$(pwd)
CELERY_QUEUES="email-queue,reports-queue,celery"   # must match app/celery.py task_routes

term() {  # term <title> <command> — run in a new Terminal window
    osascript -e "tell application \"Terminal\" to do script \"cd '$ROOT' && echo '== $1 =='; $2\"" >/dev/null
}

port_up() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

preflight() {
    local ok=1
    [ -f .env ]                        || { echo "❌ .env missing            → cp .env.example .env"; ok=0; }
    [ -x venv/bin/uvicorn ]            || { echo "❌ venv missing            → ./start_services.sh setup"; ok=0; }
    [ -d frontend/node_modules ]       || { echo "❌ frontend deps missing   → ./start_services.sh setup"; ok=0; }
    [ -d frontend-admin/node_modules ] || { echo "❌ admin UI deps missing   → ./start_services.sh setup"; ok=0; }
    redis-cli ping >/dev/null 2>&1    || { echo "❌ Redis not running       → brew services start redis"; ok=0; }
    [ $ok = 1 ] || exit 1
}

case "${1:-start}" in
start)
    preflight
    echo "🚀 Backend API";        term "Backend API :8000"    "venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    echo "🚀 Celery Worker";       term "Celery Worker"        "venv/bin/celery -A app.celery worker -Q $CELERY_QUEUES --loglevel=info"
    echo "🚀 User Frontend";       term "User Frontend :8081"  "cd frontend && npm run web"
    echo "🚀 Admin Web UI";        term "Admin UI :5173"       "cd frontend-admin && npm run dev"
    echo "✅ Requested. Backend http://localhost:8000 · User http://localhost:8081 · Admin http://localhost:5173"
    ;;
stop)
    pkill -f "uvicorn app.main:app"               && echo "stopped backend"
    pkill -f "celery -A app.celery"               && echo "stopped celery"
    pkill -f "frontend/node_modules/.bin/expo"    && echo "stopped user frontend"
    pkill -f "frontend-admin/node_modules/.bin/vite" && echo "stopped admin UI"
    echo "done"
    ;;
status)
    for svc in "Redis:6379" "Backend:8000" "User Frontend:8081" "Admin UI:5173"; do
        name=${svc%%:*}; port=${svc##*:}
        port_up "$port" && echo "✓ $name :$port" || echo "✗ $name :$port"
    done
    pgrep -fl "celery -A app.celery worker" >/dev/null && echo "✓ Celery worker" || echo "✗ Celery worker"
    ;;
setup)
    set -e
    [ -f .env ] || { cp .env.example .env; echo "created .env — edit SECRET_KEY / API keys"; }
    [ -d venv ] || python3 -m venv venv
    venv/bin/pip install -r requirements.txt
    (cd frontend && npm install)
    (cd frontend-admin && npm install)
    venv/bin/python scripts/init_db.py
    echo "✅ setup done → ./start_services.sh"
    ;;
*)
    sed -n 2,8p "$0"; exit 1 ;;
esac
