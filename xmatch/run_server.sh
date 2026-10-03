#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "================================================================="
echo "   xMatch: FastAPI Backend Server                                "
echo "================================================================="

# 1. Bootstrap environment if needed
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/uvicorn" ]; then
    echo "[!] Virtualenv or uvicorn not found. Running ./setup.sh..."
    ./setup.sh
fi

# 2. Check FalkorDB Docker container
echo "[*] Checking FalkorDB connection on localhost:6379..."
if ! .venv/bin/python -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('localhost', 6379))" 2>/dev/null; then
    echo "[!] FalkorDB is not reachable on localhost:6379."
    if command -v docker >/dev/null 2>&1; then
        echo "[*] Attempting to start FalkorDB container..."
        docker run -d --name falkordb -p 6379:6379 falkordb/falkordb:latest 2>/dev/null || docker start falkordb 2>/dev/null || true
        sleep 2
    fi
fi

# 3. Clean up existing port 8002 if needed
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8002/tcp 2>/dev/null || true
fi

PORT="${PORT:-8002}"
HOST="${HOST:-0.0.0.0}"

echo "[*] Starting FastAPI Backend on http://${HOST}:${PORT}..."
echo "[+] Swagger Documentation: http://${HOST}:${PORT}/docs"
echo "-----------------------------------------------------------------"

exec "$DIR/.venv/bin/uvicorn" xmatch.api:app --host "$HOST" --port "$PORT" --reload "$@"
