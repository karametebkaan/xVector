#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "================================================================="
echo "   xMatch Studio: Multi-Layer Identity Resolution Frontend POC   "
echo "================================================================="

# 1. Verify Virtualenv and Node Dependencies
if [ ! -d ".venv" ] || [ ! -d "frontend/node_modules" ]; then
    echo "[!] Environment or dependencies missing. Bootstrapping with ./setup.sh..."
    ./setup.sh
fi

# 2. Check FalkorDB Docker container
echo "[*] Checking FalkorDB connection on localhost:6379..."
if ! .venv/bin/python -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('localhost', 6379))" 2>/dev/null; then
    echo "[!] FalkorDB is not reachable on localhost:6379."
    echo "[*] Attempting to start FalkorDB container..."
    docker run -d --name falkordb -p 6379:6379 falkordb/falkordb:latest 2>/dev/null || docker start falkordb 2>/dev/null || true
    sleep 2
fi

# 3. Clean up any existing listeners on ports 8002 and 5173
fuser -k 8002/tcp 2>/dev/null || true
fuser -k 5173/tcp 2>/dev/null || true

# 4. Launch FastAPI Backend
echo "[*] Starting FastAPI Backend on http://localhost:8002..."
.venv/bin/uvicorn xmatch.api:app --host 0.0.0.0 --port 8002 --log-level warning &
BACKEND_PID=$!

# Trap termination to kill backend and frontend
cleanup() {
    echo ""
    echo "[*] Shutting down xMatch Studio..."
    kill $BACKEND_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Wait for backend to be healthy
echo "[*] Waiting for API readiness..."
for i in {1..15}; do
    if curl -s http://localhost:8002/api/status >/dev/null 2>&1; then
        echo "[+] API is live at http://localhost:8002"
        echo "[+] API Documentation (Swagger): http://localhost:8002/docs"
        break
    fi
    sleep 0.5
done

# 5. Launch React Vite Frontend
echo "[*] Launching React Vite Frontend on http://localhost:5173..."
echo "-----------------------------------------------------------------"
echo "  -> Open Browser: http://localhost:5173"
echo "-----------------------------------------------------------------"
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
