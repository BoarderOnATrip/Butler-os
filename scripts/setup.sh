#!/usr/bin/env bash
# First-time aiButler development setup.
# Run from repo root: ./scripts/setup.sh
set -euo pipefail

echo ""
echo "  aiButler.me — Development Setup"
echo "  ================================"
echo ""

# 1. Homebrew deps
if command -v brew &>/dev/null; then
  echo "→ Installing Homebrew dependencies..."
  brew bundle --file=Brewfile || true
else
  echo "⚠  Homebrew not found. Install from https://brew.sh"
fi

# 2. Python deps for core
echo "→ Installing Python dependencies..."
cd aibutler-core
pip install \
  elevenlabs \
  pillow \
  rembg \
  fastapi \
  uvicorn \
  pydantic \
  chromadb \
  pyinstaller \
  2>/dev/null || pip3 install elevenlabs pillow rembg fastapi uvicorn pydantic chromadb pyinstaller
cd ..

# 3. Python deps for bridge
echo "→ Installing bridge dependencies..."
pip install -r bridge/requirements.txt 2>/dev/null || pip3 install -r bridge/requirements.txt

# 4. Node deps for desktop
echo "→ Installing desktop dependencies..."
cd desktop && npm install && cd ..

# 5. Node deps for mobile
echo "→ Installing mobile dependencies..."
cd mobile && npm install && cd ..

# 6. Build sidecar
echo "→ Building Python sidecar..."
./scripts/build-sidecar.sh

echo ""
echo "  ✅ Setup complete! Next steps:"
echo ""
echo "  1. Run the desktop shell:  cd desktop && cargo tauri dev"
echo "     The onboarding flow will store your ElevenLabs API key in Keychain"
echo "     and persist your agent ID in ~/.aibutler/config.json."
echo ""
echo "  2. Run mobile when needed: cd mobile && npx expo start"
echo ""
echo "  3. Run the bridge locally: cd bridge && python server.py"
echo "     For phone pairing on LAN: AIBUTLER_BRIDGE_ALLOW_LAN=1 python server.py"
echo "     Pairing token path: ~/.aibutler/bridge.json"
echo ""
echo "  4. Optional direct voice loop: cd aibutler-core && python voice.py"
echo ""
