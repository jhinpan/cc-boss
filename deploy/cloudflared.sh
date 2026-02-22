#!/bin/bash
# Start Cloudflare Tunnel pointing at cc-boss
set -euo pipefail

PORT="${1:-8080}"

echo "Starting Cloudflare Tunnel -> http://localhost:${PORT}"
echo "The generated URL will work on iPhone Safari (HTTPS, no config needed)"
echo ""

cloudflared tunnel --url "http://localhost:${PORT}"
