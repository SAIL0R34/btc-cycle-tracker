#!/usr/bin/env bash

set -euo pipefail

UNIT_NAME="btc-swing-cycle-tracker.service"

is_running() {
  systemctl --user is-active --quiet "$UNIT_NAME"
}

start() {
  if is_running; then
    echo "streamlit service already running"
    return 0
  fi

  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT_NAME"

  if is_running; then
    echo "started streamlit on http://localhost:8501"
  else
    echo "failed to start streamlit" >&2
    exit 1
  fi
}

stop() {
  if ! is_running; then
    echo "streamlit is not running"
    return 0
  fi

  systemctl --user stop "$UNIT_NAME"
  echo "stopped streamlit service"
}

status() {
  if is_running; then
    systemctl --user --no-pager --full status "$UNIT_NAME"
  else
    echo "not running"
  fi
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop || true; start ;;
  status) status ;;
  *)
    echo "usage: $0 {start|stop|restart|status}" >&2
    exit 1
    ;;
esac
