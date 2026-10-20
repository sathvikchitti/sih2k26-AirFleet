#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PORT="${DEMO_BACKEND_PORT:-8000}"
FRONTEND_PORT="${DEMO_FRONTEND_PORT:-5173}"
MODEL_PATH="$BACKEND_DIR/models/cmapss_fd001_rf_v1.joblib"
DATA_DIR="$ROOT_DIR/CMAPSSData"
VITE_ENTRY="$FRONTEND_DIR/node_modules/vite/bin/vite.js"
BACKEND_PID=""
FRONTEND_PID=""
RUN_ID="$$"
BACKEND_LOG="$BACKEND_DIR/run_demo_backend_${RUN_ID}.log"
FRONTEND_LOG="$BACKEND_DIR/run_demo_frontend_${RUN_ID}.log"

fail() { printf 'run_demo: %s\n' "$*" >&2; exit 1; }

check_port() {
  local port="$1"
  python -c 'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.close()' "$port" \
    || fail "port $port is already in use or unavailable; no process was stopped. Set DEMO_BACKEND_PORT and DEMO_FRONTEND_PORT to unused ports."
}

wait_http() {
  local url="$1" pid="$2" label="$3"
  for _ in $(seq 1 60); do
    kill -0 "$pid" 2>/dev/null || fail "$label exited during startup; see $BACKEND_LOG or $FRONTEND_LOG"
    if python -c 'from urllib.request import urlopen; import sys; r=urlopen(sys.argv[1], timeout=2); sys.exit(0 if r.status == 200 else 1)' "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "$label did not become ready at $url within 60 seconds; see $BACKEND_LOG or $FRONTEND_LOG"
}

cleanup() {
  local pid
  for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] && (( BACKEND_PORT >= 1024 && BACKEND_PORT <= 65535 )) \
  || fail "DEMO_BACKEND_PORT must be an integer between 1024 and 65535"
[[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] && (( FRONTEND_PORT >= 1024 && FRONTEND_PORT <= 65535 )) \
  || fail "DEMO_FRONTEND_PORT must be an integer between 1024 and 65535"
[[ -s "$MODEL_PATH" ]] || fail "FD001 model artifact is missing: $MODEL_PATH; see README.md for training instructions"
[[ -s "$DATA_DIR/test_FD001.txt" ]] || fail "FD001 test history is missing under $DATA_DIR; see README.md for the local dataset files"
[[ -f "$VITE_ENTRY" ]] || fail "frontend dependencies are missing; run npm ci from $FRONTEND_DIR first"
python -c 'import fastapi,joblib,numpy,sklearn,uvicorn' \
  || fail "backend dependencies are missing; run python -m pip install -r backend/requirements.txt first"
command -v node >/dev/null || fail "node is required to launch Vite"
check_port "$BACKEND_PORT"
check_port "$FRONTEND_PORT"
[[ "$BACKEND_PORT" != "$FRONTEND_PORT" ]] || fail "backend and frontend ports must differ; no process was started"

export ML_PROVIDER=fd001
export DEMO_SCENARIO=fd001_operations
[[ "${DEMO_ACCESS_MODE:-local}" == "local" ]] || fail "run_demo.sh is local-only; use the restricted deployment instructions for hosting"
export DEMO_ACCESS_MODE=local
export DEMO_RESET_ENABLED="${DEMO_RESET_ENABLED:-false}"
export DEMO_PERMISSION_MODE=hardened
export DEMO_BACKEND_PORT="$BACKEND_PORT"
export DEMO_FRONTEND_PORT="$FRONTEND_PORT"
export FRONTEND_ORIGINS="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
export FD001_MODEL_PATH="$MODEL_PATH"
export FD001_DATA_DIR="$DATA_DIR"
export API_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}"
# Process-level empty value takes precedence over a developer-local dotenv file.
export VITE_API_BASE=

(cd "$BACKEND_DIR" && exec python -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT") >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
wait_http "http://127.0.0.1:${BACKEND_PORT}/api/health" "$BACKEND_PID" "FD001 backend"

(cd "$FRONTEND_DIR" && exec node "$VITE_ENTRY" --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort) >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
wait_http "http://127.0.0.1:${FRONTEND_PORT}/" "$FRONTEND_PID" "Vite frontend"

printf 'FD001 operations demo ready: http://localhost:%s/ (API on http://127.0.0.1:%s).\n' "$FRONTEND_PORT" "$BACKEND_PORT"
printf 'Provider: fd001; scenario: fd001_operations; reset=%s. Press Ctrl+C to stop only launcher-owned processes.\n' "$DEMO_RESET_ENABLED"
printf 'Logs: %s ; %s\n' "$BACKEND_LOG" "$FRONTEND_LOG"

while :; do
  kill -0 "$BACKEND_PID" 2>/dev/null || fail "backend exited; see $BACKEND_LOG"
  kill -0 "$FRONTEND_PID" 2>/dev/null || fail "frontend exited; see $FRONTEND_LOG"
  sleep 1
done
