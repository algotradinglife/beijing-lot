#!/usr/bin/env bash
set -euo pipefail
if (( $# != 2 )); then echo "Usage: monitor_market_capture.sh CAPTURE_ROOT REPORT_ROOT" >&2; exit 2; fi
capture_root=$1
report_root=$2
[[ -d "$capture_root" ]] || { echo "Capture directory missing: $capture_root" >&2; exit 1; }
mkdir -p "$report_root"
exec 9>"$report_root/monitor.lock"
flock -n 9
worker_pid=0
if [[ -e "$capture_root/progress.json" ]]; then
  snapshot=$(cat "$capture_root/progress.json")
  worker_pid=$(jq -er '.pid | select(type == "number" and . > 0)' <<<"$snapshot")
else
  snapshot='{"state":"NO_PROGRESS_RECORD"}'
fi
alive=false
supervisor_pid=0
if [[ -f "$capture_root/supervisor.json" ]]; then supervisor_pid=$(jq -er '.pid' "$capture_root/supervisor.json"); fi
for candidate_pid in "$worker_pid" "$supervisor_pid"; do
  if [[ "$candidate_pid" =~ ^[0-9]+$ && -r /proc/$candidate_pid/cmdline ]]; then
    cmdline=$(tr '\0' '\n' < "/proc/$candidate_pid/cmdline")
    if [[ ( "$cmdline" == *collect_market_history.py* || "$cmdline" == *supervise_market_history.py* ) && "$cmdline" == *"$capture_root"* ]]; then alive=true; fi
  fi
done
recovery=null
if [[ -f "$capture_root/recovery.json" ]]; then recovery=$(cat "$capture_root/recovery.json"); fi
previous=null
if [[ -f "$report_root/latest.json" ]]; then previous=$(cat "$report_root/latest.json"); fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)
temp=$(mktemp "$report_root/.snapshot.XXXXXX")
jq --arg capture_root "$capture_root" --argjson alive "$alive" --argjson recovery "$recovery" --argjson previous "$previous" --arg checked_at "$(date -u +%FT%TZ)" '
 {capture_root:$capture_root,checked_at_utc:$checked_at,process_alive:$alive,worker_state:.state,
 current_issue:.active_issue,completed_issues:.completed_issues,new_responses:.new_responses,
 blocked_streak:.blocked_streak,worker_updated_at:.updated_at_utc,
 recovery_state:$recovery.state,recovery_reason:$recovery.reason,
 next_probe_at:$recovery.next_probe_at,recovery_attempt:$recovery.attempt,
 response_delta:(if $previous == null or $previous.capture_root != $capture_root or .new_responses == null or $previous.new_responses == null then null else .new_responses-$previous.new_responses end),
 issue_delta:(if $previous == null or $previous.capture_root != $capture_root or .completed_issues == null or $previous.completed_issues == null then null else .completed_issues-$previous.completed_issues end),
 status:(if .state == "NO_PROGRESS_RECORD" then "NO_PROGRESS_RECORD"
 elif .state == "OBSERVED_INVENTORY_ATTEMPTED" then "FINISHED"
 elif $alive == false then "PROCESS_EXITED"
 elif .state == "CIRCUIT_OPEN" and $recovery != null then $recovery.state
 elif .state != "RUNNING" then .state
 elif $previous != null and $previous.capture_root == $capture_root and .new_responses == $previous.new_responses and .completed_issues == $previous.completed_issues then "NO_PROGRESS_SINCE_PREVIOUS_CHECK"
 else "RUNNING" end)}' <<<"$snapshot" > "$temp"
cp "$temp" "$report_root/$stamp.json"
mv "$temp" "$report_root/latest.json"
cat "$report_root/latest.json"
