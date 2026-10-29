#!/usr/bin/env bash
set -euo pipefail
session="${FLASHVSR_PLUS_TMUX_SESSION:-flashvsr-plus-api}"
if tmux has-session -t "$session" 2>/dev/null; then
  echo "running: $session"
  tmux list-windows -t "$session"
  curl -fsS "http://${FLASHVSR_PLUS_HOST:-127.0.0.1}:${FLASHVSR_PLUS_PORT:-18303}/readyz" || true
  echo
else
  echo "stopped: $session"
  exit 1
fi
