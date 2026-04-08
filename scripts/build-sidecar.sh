#!/usr/bin/env bash
# Build the Python sidecar binary and place it where Tauri expects it.
# Run from the repo root: ./scripts/build-sidecar.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$REPO_ROOT/aibutler-core"
BIN_DIR="$CORE_DIR/bin"
TAURI_BIN_DIR="$REPO_ROOT/desktop/src-tauri"

echo "→ Building aiButler runtime sidecar..."
cd "$CORE_DIR"

# Ensure pyinstaller is available
if ! command -v pyinstaller &>/dev/null; then
  echo "Installing pyinstaller..."
  pip install pyinstaller
fi

# Build
pyinstaller \
  --onefile \
  --name aibutler-runtime \
  --add-data "runtime:runtime" \
  --add-data "tools:tools" \
  --hidden-import "runtime.engine" \
  --hidden-import "runtime.agentic" \
  --hidden-import "runtime.rag_memory" \
  --hidden-import "runtime.plugins" \
  --hidden-import "tools.file_ops" \
  --hidden-import "tools.computer_use" \
  --hidden-import "tools.secrets" \
  --hidden-import "tools.life_data" \
  runtime/__main__.py

# Copy to bin/ (for direct use)
mkdir -p "$BIN_DIR"
cp dist/aibutler-runtime "$BIN_DIR/aibutler-runtime"
chmod +x "$BIN_DIR/aibutler-runtime"

# Copy into Tauri resources for local desktop use / future bundling
cp dist/aibutler-runtime "$TAURI_BIN_DIR/aibutler-runtime"
chmod +x "$TAURI_BIN_DIR/aibutler-runtime"

echo "✅ Sidecar built: $BIN_DIR/aibutler-runtime"
echo "✅ Copied to Tauri: $TAURI_BIN_DIR/aibutler-runtime"
