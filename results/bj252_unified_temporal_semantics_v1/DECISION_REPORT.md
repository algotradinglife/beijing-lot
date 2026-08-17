# #252 decision input (candidate)

This package profiles coverage and staleness across 1/6/12/24h common issue cutoffs and a deterministic local-date segment fallback. It does **not** select a final lead, cadence, or claim boundary: PI/user must decide those policy choices. Historical proxy and strict-forward namespaces are physically separate tables and the verifier refuses pooled semantics.

Timezone convention: Asia/Shanghai scheduled kickoff values are explicitly localized then converted to UTC. Reschedules must be represented by a new sealed fixture schedule before rebuilding; missing strict timestamps drop with `NO_OBSERVATION_BY_CUTOFF`.
