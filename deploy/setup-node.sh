#!/bin/bash
# One-shot setup for cc-boss on MI300X node
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== cc-boss node setup ==="

# 1. Install cc-boss
echo "[1/3] Installing cc-boss..."
pip install -e "$SCRIPT_DIR"

# 2. Install cloudflared if not present
if ! command -v cloudflared &>/dev/null; then
    echo "[2/3] Installing cloudflared..."
    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
        -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
else
    echo "[2/3] cloudflared already installed"
fi

echo "[3/3] Done. Start with:"
echo ""
echo "  cc-boss start --port 8080 --workers 5 --repo /path/to/project &"
echo "  cloudflared tunnel --url http://localhost:8080"
echo ""
echo "Then open the generated https://xxx.trycloudflare.com URL on your phone."
