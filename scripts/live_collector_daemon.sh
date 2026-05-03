#!/usr/bin/env bash
# Live Collector daemon control script.
# Usage: scripts/live_collector_daemon.sh {start|stop|restart|status|logs|tail}

set -euo pipefail

LABEL="com.beidanlot.live_collector"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
STDOUT_LOG="/Volumes/Data Drive/workspace/trading/beijing-lot/data/logs/live_collector.stdout.log"
STDERR_LOG="/Volumes/Data Drive/workspace/trading/beijing-lot/data/logs/live_collector.stderr.log"

cmd="${1:-status}"

case "$cmd" in
    start)
        if launchctl list | grep -q "$LABEL"; then
            echo "Already running. PID:"
            launchctl list | grep "$LABEL" | awk '{print $1}'
        else
            launchctl load "$PLIST"
            sleep 1
            echo "Loaded. Status:"
            launchctl list | grep "$LABEL" || echo "(not yet visible — wait a few seconds)"
        fi
        ;;
    stop)
        launchctl unload "$PLIST" 2>/dev/null || echo "(was not loaded)"
        echo "Stopped."
        ;;
    restart)
        "$0" stop
        sleep 1
        "$0" start
        ;;
    status)
        if launchctl list | grep -q "$LABEL"; then
            echo "[RUNNING]"
            launchctl list | grep "$LABEL"
            if [[ -f "$STDOUT_LOG" ]]; then
                echo
                echo "Last 5 stdout lines:"
                tail -5 "$STDOUT_LOG"
            fi
        else
            echo "[NOT RUNNING]"
            echo "Start with: $0 start"
        fi
        ;;
    logs)
        echo "=== STDOUT ($STDOUT_LOG) ==="
        tail -50 "$STDOUT_LOG" 2>/dev/null || echo "(no stdout log yet)"
        echo
        echo "=== STDERR ($STDERR_LOG) ==="
        tail -50 "$STDERR_LOG" 2>/dev/null || echo "(no stderr log yet)"
        ;;
    tail)
        echo "Tailing logs (Ctrl-C to exit)..."
        tail -f "$STDOUT_LOG" "$STDERR_LOG" 2>/dev/null
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|tail}"
        exit 1
        ;;
esac
