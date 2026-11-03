#!/usr/bin/env bash
# One-click launcher: starts the PO Token provider (if built) + the Flask app,
# and stops the provider automatically on Ctrl+C.
#
#   ./start.sh            # default port 5050
#   PORT=8000 ./start.sh  # custom port
set -uo pipefail
cd "$(dirname "$0")"

PY="./venv/bin/python"
PORT="${PORT:-5050}"
POT_DIR="pot-provider/server"
PROVIDER_PID=""

if [ ! -x "$PY" ]; then
  echo "❌ venv belum ada. Jalankan dulu:"
  echo "   python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
  exit 1
fi

cleanup() {
  if [ -n "$PROVIDER_PID" ] && kill -0 "$PROVIDER_PID" 2>/dev/null; then
    echo
    echo "⏹  Menghentikan server PO Token (pid $PROVIDER_PID)…"
    kill "$PROVIDER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [ -f "$POT_DIR/build/main.js" ]; then
  if lsof -iTCP:4416 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "✅ Server PO Token sudah jalan di :4416"
  else
    echo "▶ Menjalankan server PO Token…"
    ( cd "$POT_DIR" && node build/main.js ) >/tmp/pot-provider.log 2>&1 &
    PROVIDER_PID=$!
    for _ in $(seq 1 20); do
      lsof -iTCP:4416 -sTCP:LISTEN >/dev/null 2>&1 && break
      sleep 0.5
    done
    echo "   server PO Token pid $PROVIDER_PID (log: /tmp/pot-provider.log)"
  fi
else
  echo "⚠  pot-provider belum di-build — video membership tak akan jalan."
  echo "   Lihat README bagian 'Setup server PO Token pertama kali'."
fi

echo "▶ Aplikasi: http://127.0.0.1:$PORT   (tekan Ctrl+C untuk berhenti)"
PORT="$PORT" "$PY" app.py
