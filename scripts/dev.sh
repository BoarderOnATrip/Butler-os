#!/usr/bin/env bash
# Start all aiButler services in parallel (dev mode).
# Run from repo root: ./scripts/dev.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Kill on Ctrl+C
cleanup() {
  echo ""
  echo "Stopping all services..."
  kill 0
}
trap cleanup SIGINT SIGTERM

echo ""
echo "  Starting aiButler dev stack..."
echo "  Ctrl+C to stop all"
echo ""

# Bridge
echo "→ Starting bridge on :8765"
cd "$REPO_ROOT/bridge" && python server.py &
BRIDGE_PID=$!

# Desktop
echo "→ Starting desktop (Tauri dev)"
cd "$REPO_ROOT/desktop" && cargo tauri dev &
DESKTOP_PID=$!

wait
