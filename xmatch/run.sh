#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

if [ ! -d "$DIR/.venv" ]; then
    echo "[!] Virtualenv .venv not found. Bootstrapping with ./setup.sh..."
    "$DIR/setup.sh"
fi

"$DIR/.venv/bin/python" "$DIR/run_demo.py" "$@"
