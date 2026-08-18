# #252 decision input (candidate)

This package profiles fixture/cell coverage and poll-start age across 1/6/12/24h common issue cutoffs and a deterministic local-date segment fallback. It does **not** select a final lead or crawler cadence. Historical proxy is stratified by horizon, market and field role rather than pooled into an M×3 denominator.

Timezone convention: Asia/Shanghai scheduled kickoff values are explicitly localized then converted to UTC. The collector timestamp is poll-start, not data-received time; merged rows do not retain upstream per-cell lineage. Without schedule history these curves are descriptive against the current schedule reference. Missing snapshots, incomplete storage and invalid SP values are separate drop causes.

Internal checksums establish package integrity, not external authenticity after arbitrary re-signing. The source receipt proves only that SQLite main/WAL/SHM bytes were stable across this build interval.
