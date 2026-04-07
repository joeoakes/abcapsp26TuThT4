#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
BACKEND_MODULE="src.backend.maze_server"
DASHBOARD_URL="${DASHBOARD_URL:-https://127.0.0.1:8447/dashboard}"

echo "Starting backend: ${BACKEND_MODULE}"
MTLS_REQUIRE_CLIENT="${MTLS_REQUIRE_CLIENT:-0}" "${PYTHON_BIN}" -m "${BACKEND_MODULE}" &
BACKEND_PID=$!

cleanup() {
  if kill -0 "${BACKEND_PID}" 2>/dev/null; then
    echo "Stopping backend (${BACKEND_PID})"
    kill "${BACKEND_PID}" || true
  fi
}
trap cleanup EXIT INT TERM

sleep 2
echo "Dashboard available at: ${DASHBOARD_URL}"
echo "Press Ctrl+C to stop."
wait "${BACKEND_PID}"
