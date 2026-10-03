#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "================================================================="
echo "   xMatch: Setting Up Development Environment                    "
echo "================================================================="

# 1. Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] Error: python3 is not installed or not in PATH."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[*] Found Python $PYTHON_VERSION"

# 2. Setup Virtual Environment
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment in .venv..."
    python3 -m venv .venv
else
    echo "[+] Virtual environment .venv already exists."
fi

# 3. Install Python Dependencies
echo "[*] Installing Python dependencies in editable mode (with tests)..."
.venv/bin/pip install --upgrade pip setuptools wheel >/dev/null
.venv/bin/pip install -e ".[test]"

echo "[+] Python environment ready."

# 4. Setup Frontend Node Dependencies
if [ -f "frontend/package.json" ]; then
    if [ ! -d "frontend/node_modules" ]; then
        if command -v npm >/dev/null 2>&1; then
            echo "[*] Installing frontend dependencies in frontend/node_modules..."
            npm install --prefix frontend
            echo "[+] Frontend dependencies installed."
        else
            echo "[!] Warning: npm is not installed. Frontend dependencies skipped."
        fi
    else
        echo "[+] Frontend node_modules already installed."
    fi
fi

# 5. Check FalkorDB Container
echo "[*] Checking FalkorDB connection on localhost:6379..."
if ! .venv/bin/python -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('localhost', 6379))" 2>/dev/null; then
    echo "[!] FalkorDB is not reachable on localhost:6379."
    if command -v docker >/dev/null 2>&1; then
        echo "[*] Attempting to start FalkorDB via Docker..."
        docker run -d --name falkordb -p 6379:6379 falkordb/falkordb:latest 2>/dev/null || docker start falkordb 2>/dev/null || true
        sleep 2
    else
        echo "[!] Docker not detected. Please ensure FalkorDB is running on port 6379."
    fi
else
    echo "[+] FalkorDB is active on localhost:6379."
fi

echo "================================================================="
echo "   xMatch Setup Complete!                                        "
echo "   • Run CLI demo:           ./run.sh                            "
echo "   • Run FastAPI server:     ./run_server.sh                     "
echo "   • Run interactive Studio: ./start_ui.sh                       "
echo "   • Run unit tests:         .venv/bin/pytest                    "
echo "================================================================="
