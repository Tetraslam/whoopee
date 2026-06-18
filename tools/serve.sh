#!/usr/bin/env bash
# serve.sh — start/stop/status the dashboard as a real background daemon.
#
# Every subcommand returns immediately (no foreground blocking), so it's safe
# for both a human terminal and an agent's shell tool.
#
#   tools/serve.sh start [project]    # default project: dashboard
#   tools/serve.sh stop  [project]
#   tools/serve.sh restart [project]
#   tools/serve.sh status [project]
#   tools/serve.sh logs  [project]    # tail -n 40 of the log
#
# Secrets are injected via load-env.sh (global + the project's own .env.op).
# Each project defines how it runs in the `run_cmd` case below.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="${2:-dashboard}"
RUN_DIR="$REPO_ROOT/.run"
PID_FILE="$RUN_DIR/$PROJ.pid"
LOG_FILE="$RUN_DIR/$PROJ.log"
mkdir -p "$RUN_DIR"

run_cmd() {
  # How each project launches. Add a case when you add a new long-running project.
  case "$1" in
    dashboard)
      echo "uv run --directory projects/dashboard python -m dashboard.app"
      ;;
    *)
      echo ""
      ;;
  esac
}

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid; pid="$(cat "$PID_FILE")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

cmd_start() {
  if is_running; then
    echo "$PROJ already running (pid $(cat "$PID_FILE"))"; return 0
  fi
  local cmd; cmd="$(run_cmd "$PROJ")"
  if [[ -z "$cmd" ]]; then
    echo "no run command defined for project '$PROJ' (edit tools/serve.sh)"; exit 1
  fi
  # Fully detach: setsid + nohup, stdin from /dev/null, output to the log.
  # load-env.sh injects secrets; the inner command is the project's runner.
  setsid bash -c "cd '$REPO_ROOT' && exec tools/load-env.sh --dir 'projects/$PROJ' -- $cmd" \
    </dev/null >"$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  sleep 2
  if is_running; then
    echo "$PROJ started (pid $pid) — logs: tools/serve.sh logs $PROJ"
  else
    echo "$PROJ failed to start; recent log:"; tail -n 20 "$LOG_FILE"; exit 1
  fi
}

cmd_stop() {
  if ! is_running; then echo "$PROJ not running"; rm -f "$PID_FILE"; return 0; fi
  local pid; pid="$(cat "$PID_FILE")"
  # kill the whole process group (setsid made the pid a group leader)
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  sleep 1
  kill -KILL -- "-$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "$PROJ stopped"
}

cmd_status() {
  if is_running; then echo "$PROJ: running (pid $(cat "$PID_FILE"))";
  else echo "$PROJ: stopped"; fi
}

cmd_logs() { [[ -f "$LOG_FILE" ]] && tail -n 40 "$LOG_FILE" || echo "no log yet"; }

case "${1:-}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status)  cmd_status ;;
  logs)    cmd_logs ;;
  *) echo "usage: tools/serve.sh {start|stop|restart|status|logs} [project]"; exit 2 ;;
esac
