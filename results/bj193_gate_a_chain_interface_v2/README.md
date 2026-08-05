# #193 Gate-A v2 — chained per-issue interface amendment

This package amends, but does not replace or mutate, the accepted
`bj193_gate_a_preoutcome_v1` lineage.  It freezes three separately parameterized decisions:
match selection, outcome direction, and ticket construction.  No target
outcome or Gate-B settlement payload is opened.

Catalog census:

- Stage 1 selection actions: 2,469
- Stage 2 direction actions: 2,425
- Stage 3 seed-agnostic allocator/M actions: 963
- stage-specific model configurations: 90
- required matched attribution controls: 4

Downstream stages consume immutable upstream outputs and digests.  Their
training inputs are chronologically honest upstream predictions, not in-sample
or realized-best choices.  Seed remains a nuisance replicate and M remains an
output from the accepted grid, not a budget gate.

Status: ready for PI review, no Gate-B, betting, production, or #192 authority.
