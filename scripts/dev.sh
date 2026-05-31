#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"

ensure_port_available() {
  local label="$1"
  local port="$2"

  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Error: ${label} port ${port} is already in use." >&2
    echo "Stop the process below, or rerun with a different ${label} port." >&2
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >&2 || true
    exit 1
  fi
}

terminate_process_tree() {
  local pid="$1"
  local child

  for child in $(pgrep -P "${pid}" 2>/dev/null || true); do
    terminate_process_tree "${child}"
  done
  kill "${pid}" 2>/dev/null || true
}

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    terminate_process_tree "${BACKEND_PID}"
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    terminate_process_tree "${FRONTEND_PID}"
  fi
}

trap cleanup EXIT INT TERM

ensure_port_available "backend" "${BACKEND_PORT}"
ensure_port_available "frontend" "${FRONTEND_PORT}"

echo "Starting backend on ${BACKEND_URL}"
(
  cd "${ROOT_DIR}"
  PYTHONPATH=backend python -m uvicorn \
    texas_holdem_trainer.api.app:app \
    --reload \
    --reload-dir backend \
    --port "${BACKEND_PORT}"
) &
BACKEND_PID=$!

echo "Starting frontend on http://127.0.0.1:${FRONTEND_PORT}"
(
  cd "${ROOT_DIR}/frontend"
  VITE_PROXY_TARGET="${BACKEND_URL}" npm run dev -- --port "${FRONTEND_PORT}" --strictPort
) &
FRONTEND_PID=$!

while true; do
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    wait "${BACKEND_PID}"
    exit $?
  fi
  if ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    wait "${FRONTEND_PID}"
    exit $?
  fi
  sleep 1
done
