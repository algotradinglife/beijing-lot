# BJ-MM-FREEZE-001 — p40/p42 strict segment freeze gate

Status: `engineering_validation`; capability task, not a predictive experiment.

## Preregistration

Activation identity is `research/bj-mm-freeze-001` at git revision
`63f09bef1c1a0399192444d79814a988bddede80` (2026-07-23T17:38:56Z).
The first two eligible segment windows after this activation are consumed in
database order by the research-only coordinator. Target playids are `[40, 42]`;
selection is `segment_freeze`. All packages fix
`execution_enabled=false`, `frontend_selectable=false`, and
`roi_authorized=false`.

## Evidence procedure

Packages are append-only at
`results/research/multimarket_segment_freeze_v1/<issue>/segment_<NN>/<event_id>/`.
`event_id` is a SHA-256 identity over schema, issue, segment, effective decision
time, and sorted playids. The coordinator records retry status for failures and
only considers an existing event complete after recursive verification.

For every segment, the denominator is all segment matches × two markets. Each
candidate must have both clocks at or before the same effective decision time,
an open sale whose cutoff is later than that time, a complete finite >1 outcome
vector, stable mapping, and a verified immutable source bundle. The reportable
package contains denominators, rejections, skipped candidates, timings,
staleness, frozen outcomes, and mechanical paired p40/p42 overlap. No terminal
value is substituted.

No prospective event package exists at this commit, so G4/G5 remain `PARTIAL`
pending the first two automatically selected events. Operational repeatability
is not statistical sample sufficiency or evidence of market consistency.

## Reproduction

```bash
.venv/bin/python -m pytest -q tests/scripts/test_multimarket_p0.py
.venv/bin/python scripts/manage_multimarket_p0.py freeze-segment --issue ISSUE --segment-idx SEGMENT_IDX --output-dir OUTPUT_ROOT
```

The fixture test reruns the same event, verifies byte-identical package content,
and rejects a tampered nested raw file and post-freeze candidate.
