#!/usr/bin/env bash
set -euo pipefail

# Start the proton-vpn-manager daemon (assumes capabilities already set on the python binary).

DAEMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.. && pwd)"
PIDFILE="/tmp/proton-vpn-manager-demo.pid"
LOGFILE="/tmp/proton-vpn-manager-demo.log"

echo "Starting proton-vpn-manager daemon..."

# If already running, stop it first
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping existing daemon (PID $OLD_PID)"
        kill "$OLD_PID" || true
        sleep 1
    fi
    rm -f "$PIDFILE"
fi

# Start daemon
cd "$DAEMON_DIR"
nohup .venv/bin/python -m daemon.daemon > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "Daemon started (PID $!), logging to $LOGFILE"
echo ""
echo "Now run: ${DAEMON_DIR}/.venv/bin/python ${DAEMON_DIR}/examples/demo_dummy_adapter.py"
