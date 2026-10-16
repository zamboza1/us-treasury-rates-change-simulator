#!/bin/bash
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
BACKEND_PORT="${BACKEND_PORT:-8081}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"

"$PYTHON" -c 'import fastapi, uvicorn, requests, pydantic' || {
    echo 'Install requirements.txt in your Python environment first.' >&2
    exit 1
}
# Refuse occupied ports. Never terminate unrelated services.
"$PYTHON" - "$BACKEND_PORT" "$FRONTEND_PORT" <<'PY'
import socket, sys
sockets = []
try:
    for value in sys.argv[1:]:
        port = int(value)
        if not 1 <= port <= 65535:
            raise ValueError('Ports must be between 1 and 65535.')
        server = socket.socket()
        sockets.append(server)
        server.bind(('127.0.0.1', port))
except (OSError, ValueError) as exc:
    sys.exit(f'Cannot start servers: {exc}')
finally:
    for server in sockets:
        server.close()
PY

BACKEND_PID=''
FRONTEND_PID=''
cleanup() {
    [ -z "$BACKEND_PID" ] || kill "$BACKEND_PID" 2>/dev/null || true
    [ -z "$FRONTEND_PID" ] || kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM

"$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!
"$PYTHON" -m http.server "$FRONTEND_PORT" --bind 127.0.0.1 --directory frontend &
FRONTEND_PID=$!
echo "Simulator: http://127.0.0.1:$FRONTEND_PORT/?apiPort=$BACKEND_PORT"
# Stop our companion server if either process exits.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
    sleep 1
done
exit 1
