#!/bin/bash
# Job Search System — start everything
# Usage: ./start.sh       # local only (localhost:8000)
#        ./start.sh --mobile  # + permanent Cloudflare tunnel (jobsearch.aidatasolutions.co)

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

# Kill previous instances
pkill -f "uvicorn app.main" 2>/dev/null || true
pkill -f "cloudflared tunnel run" 2>/dev/null || true
sleep 1

echo "▶ Starting backend (port 8000)..."
cd "$DIR"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload \
  >/tmp/jobsearch-backend.log 2>&1 &
BACKEND_PID=$!

sleep 3

if [[ "$1" == "--mobile" ]]; then
  echo "▶ Starting Cloudflare tunnel..."
  cloudflared tunnel run jobsearch \
    >/tmp/jobsearch-tunnel.log 2>&1 &
  TUNNEL_PID=$!
  sleep 3

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  App URL: https://jobsearch.aidatasolutions.co"
  echo "  (open on Mac or iPhone)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

echo ""
echo "✓ Local:   http://localhost:8000"
echo "✓ API:     http://localhost:8000/api"
echo ""
echo "Logs: /tmp/jobsearch-backend.log"
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID ${TUNNEL_PID:-} 2>/dev/null" EXIT
wait
