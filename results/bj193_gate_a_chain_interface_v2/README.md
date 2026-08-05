# #193 Gate-A v2 — chained per-issue interface amendment

This package amends, but does not replace or mutate, the accepted
`bj193_gate_a_preoutcome_v1` lineage.  It freezes three separately parameterized decisions:
match selection, outcome direction, and ticket construction.  No target
outcome or Gate-B settlement payload is opened.

Stage 2 actions are explicitly derived Stage-1-conditional adapters; they are
not renamed #190 B0-only actions. Stage 3 actions bind accepted #167 parameters
to the exact Stage-2 mask/weight-to-ordinal builder and byte-bound #145 engine.
The complete #137 match-vector registry supplies hash-bound pre-event weights
for every supported #127/#134 N7. A normalized Stage1×Stage3 registry screens
all 2,377,647 action pairs before learning: incompatible
#190/non-NA pairs are explicit zero-flow and never fall back to partial, unit,
or fabricated weights. The allocator replay signature is derived internally
from the issue and complete upstream/action digests.
The stagewise learner registry fixes projection columns, encoding, per-action
topology, screening and every validation/action tie.

Catalog census:

- Stage 1 selection actions: 2,469
- Stage 2 direction actions: 2,425
- Stage 3 seed-agnostic allocator/M actions: 963
- Complete pre-event Stage-3 match-weight rows: 47,819
- Normalized Stage1×Stage3 coverage rows/classes: 17,283/7
- stage-specific model configurations: 90
- required matched attribution controls: 4

Downstream stages consume immutable upstream outputs and digests.  Their
training inputs are chronologically honest upstream predictions, not in-sample
or realized-best choices.  Seed remains a nuisance replicate and M remains an
output from the accepted grid, not a budget gate.

`SHA256SUMS.json` binds exact committed transport bytes and the recorded
runtime. `PORTABLE_SHA256SUMS.json` plus `CONTENT_IDENTITY.json` bind canonical
decompressed gzip content, so semantic replay is portable across compliant
gzip implementations even when compressed bytes differ.

Status: ready for PI review, no Gate-B, betting, production, or #192 authority.
