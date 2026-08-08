# #204 Gate A v4 — market-anchored probability/SP data build

Status: Draft PR #219 candidate. This is the single canonical, immutable
outcome-unexposed Gate-A package for `BJ-UNIFIED-PROB-SP-POC-001`:
`results/bj204_gate_a_preoutcome_v4`.

The frozen chronology contains 344 development issues through `25042` and a
locked 75-issue retrospective test window (`25043–25125`, `26011–26049`).
Issues `26051+` remain reserved for #210. Development uses the official
identity bridge to the p_close market proxy; the test side uses normalized
average-EU. Both are materialized through one source-graded M×3 feature/mask
adapter, rather than treated as identical feeds.

The package records 102,245 development matches (101,029 complete p_close
triplets), 16,990 locked-test matches (16,968 complete average-EU triplets),
and the identifier-only `25041/25042` development census (1,021 available
official 3SP identities from 1,024 source identities). Official final 3SP is
target-only and remains unopened in Gate A; `predicted_final_sp_input` is a
pre-event input proxy, not a target.

The executable notebook
`notebooks/research/issue-204/bj204_track_a_gate_a.ipynb` visibly constructs a
bounded common panel from committed fixtures and audits the full immutable
panel: source identities, chronology, duplicate/unmatched identities,
per-field/outcome coverage, representative M×3 tensors, and reconciliation
figures. A full rebuild requires explicit read-only source paths; it never
searches a parent worktree for private archives.

Gate B is not authorized. This historical data-contract freeze does not
authorize model training, outcome evaluation, tickets, ROI analysis, betting,
or promotion.
