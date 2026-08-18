# #252 decision input (candidate)

This package profiles fixture/cell coverage and staleness across 1/6/12/24h common issue cutoffs and a deterministic local-date segment fallback. It does **not** select a final lead or crawler cadence. Historical proxy consists of three aggregate horizon summaries, not a row-level panel, and remains physically separate from observed-at evidence.

Timezone convention: Asia/Shanghai scheduled kickoff values are explicitly localized then converted to UTC. Without schedule history these curves are descriptive against the current schedule reference. `NO_OBSERVATION_BY_CUTOFF` is separate from `OBSERVATION_UNAVAILABLE_OR_INCOMPLETE`.

Internal checksums establish package integrity, not external authenticity after arbitrary re-signing. The source receipt proves only that SQLite main/WAL/SHM bytes were stable across this build interval.
