#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

mkdir -p logs

# Bootstrap environment if needed
if [ ! -d ".venv" ] || [ ! -d "frontend/node_modules" ]; then
    echo "[!] Environment or dependencies missing. Bootstrapping with ./setup.sh..."
    ./setup.sh
fi

# Clean up any existing listeners on ports 8002 and 5173
fuser -k 8002/tcp 2>/dev/null || true
fuser -k 5173/tcp 2>/dev/null || true

# Start FastAPI backend detached
echo "[*] Starting FastAPI Backend on http://localhost:8002..."
setsid .venv/bin/uvicorn xmatch.api:app --host 0.0.0.0 --port 8002 </dev/null >logs/backend.log 2>&1 &

# Start Vite React frontend detached
echo "[*] Starting Vite React Frontend on http://localhost:5173..."
setsid npm run dev --prefix frontend -- --host 0.0.0.0 --port 5173 </dev/null >logs/frontend.log 2>&1 &

sleep 2

# Verify
if curl -s http://localhost:8002/api/status >/dev/null 2>&1; then
    echo "[+] Backend is LIVE at http://localhost:8002"
    echo "[+] Swagger Docs: http://localhost:8002/docs"
fi

if curl -s http://localhost:5173 >/dev/null 2>&1; then
    echo "[+] Frontend is LIVE at http://localhost:5173"
    echo "================================================================="
    echo "  👉 Open your browser at: http://localhost:5173"
    echo "================================================================="
fi
