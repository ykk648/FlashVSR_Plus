#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
session="${FLASHVSR_PLUS_TMUX_SESSION:-flashvsr-plus-api}"
source scripts/configure_china_mirrors.sh >/dev/null
if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session"
  echo "attach with: tmux attach -t $session"
  exit 0
fi
mkdir -p runtime/api
tmux new-session -d -s "$session" "cd '$repo_root' && set -a && . ./.env 2>/dev/null || true; set +a; exec uv run flashvsr-plus-api --host \"\${FLASHVSR_PLUS_HOST:-0.0.0.0}\" --port \"\${FLASHVSR_PLUS_PORT:-18303}\" --device \"\${FLASHVSR_PLUS_DEVICE:-cuda:0}\" 2>&1 | tee -a runtime/api/server.log"
echo "started tmux session: $session"
echo "attach with: tmux attach -t $session"
