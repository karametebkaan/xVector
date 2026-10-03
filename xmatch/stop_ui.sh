#!/usr/bin/env bash
echo "[*] Stopping xMatch Studio services..."
fuser -k 8002/tcp 2>/dev/null || true
fuser -k 5173/tcp 2>/dev/null || true
echo "[+] Successfully stopped services on ports 8002 and 5173."
