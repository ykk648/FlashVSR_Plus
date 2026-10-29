#!/usr/bin/env bash
set -euo pipefail
session="${FLASHVSR_PLUS_TMUX_SESSION:-flashvsr-plus-api}"
if tmux has-session -t "$session" 2>/dev/null; then
  tmux send-keys -t "$session" C-c
  sleep 1
  tmux kill-session -t "$session" 2>/dev/null || true
  echo "stopped tmux session: $session"
else
  echo "tmux session is not running: $session"
fi
