#!/usr/bin/env bash
set -euo pipefail
if (( $# != 2 )); then echo "Usage: monitor_market_capture.sh CAPTURE_ROOT REPORT_ROOT" >&2; exit 2; fi
capture_root=$1
report_root=$2
mkdir -p "$report_root"
exec 9>"$report_root/monitor.lock"
flock -n 9
snapshot=$(cat "$capture_root/progress.json")
worker_pid=$(jq -er '.pid | select(type == "number" and . > 0)' <<<"$snapshot")
alive=false
if [[ -r /proc/$worker_pid/cmdline ]]; then
  cmdline=$(tr '\0' '\n' < "/proc/$worker_pid/cmdline")
  if [[ "$cmdline" == *collect_market_history.py* && "$cmdline" == *"$capture_root"* ]]; then alive=true; fi
fi
previous=null
if [[ -f "$report_root/latest.json" ]]; then previous=$(cat "$report_root/latest.json"); fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)
temp=$(mktemp "$report_root/.snapshot.XXXXXX")
jq --argjson alive "$alive" --argjson previous "$previous" --arg checked_at "$(date -u +%FT%TZ)" '
 {checked_at_utc:$checked_at,process_alive:$alive,worker_state:.state,
 current_issue:.active_issue,completed_issues:.completed_issues,new_responses:.new_responses,
 blocked_streak:.blocked_streak,worker_updated_at:.updated_at_utc,
 response_delta:(if $previous == null then null else .new_responses-$previous.new_responses end),
 issue_delta:(if $previous == null then null else .completed_issues-$previous.completed_issues end),
 status:(if .state == "OBSERVED_INVENTORY_ATTEMPTED" then "FINISHED"
 elif $alive == false then "PROCESS_EXITED"
 elif .state != "RUNNING" then .state
 elif $previous != null and .new_responses == $previous.new_responses and .completed_issues == $previous.completed_issues then "NO_PROGRESS_SINCE_PREVIOUS_CHECK"
 else "RUNNING" end)}' <<<"$snapshot" > "$temp"
cp "$temp" "$report_root/$stamp.json"
mv "$temp" "$report_root/latest.json"
cat "$report_root/latest.json"
