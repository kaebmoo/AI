#!/bin/bash

# Store the current directory
PROJECT_ROOT=$(pwd)

# Function to run a command in a new Terminal window
run_in_new_terminal() {
    local title="$1"
    local cmd="$2"
    
    # Run the command in a new Terminal window
    # We use -e to avoid heredoc complexity and potential syntax errors
    osascript -e "tell application \"Terminal\" to do script \"echo '$title'; $cmd\"" > /dev/null
}

echo "Starting NT AI Assistant Services..."

# 1. Backend API
echo "🚀 Launching Backend API..."
run_in_new_terminal "Backend API" "cd '$PROJECT_ROOT' && source venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

# 2. Celery Worker
echo "🚀 Launching Celery Worker..."
run_in_new_terminal "Celery Worker" "cd '$PROJECT_ROOT' && source venv/bin/activate && celery -A app.celery worker -Q email-queue,celery --loglevel=info"

# 3. User Frontend (Expo)
echo "🚀 Launching User Frontend..."
run_in_new_terminal "User Frontend" "cd '$PROJECT_ROOT'/frontend && npm run web"

# 4. Admin Web UI
echo "🚀 Launching Admin Web UI..."
run_in_new_terminal "Admin Web UI" "cd '$PROJECT_ROOT'/frontend-admin && npm run dev"

echo "✅ All services requested. Check the new Terminal windows."
