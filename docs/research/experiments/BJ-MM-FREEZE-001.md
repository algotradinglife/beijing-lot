# BJ-MM-FREEZE-001 — p40/p42 strict segment freeze gate

Status: `reviewed`; capability task, not a predictive experiment.

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

## Read-only operational evidence audit

Audit cutoff: `2026-07-26T06:26:42Z`.

The immutable coordinator ledger binds the first two eligible events after
activation to Segment 1 and Segment 2 of issue `26078`. Both bindings and both
packages pass their recursive verifiers. No package was regenerated, replaced,
or backfilled during this audit.

### Checkpoint 1

- Event ID:
  `d43d4bac00024c4556c66b03baf38d1da243694ed76bad07f5e6170aa0d22317`
- Immutable package:
  `results/research/multimarket_segment_freeze_v1/26078/segment_01/d43d4bac00024c4556c66b03baf38d1da243694ed76bad07f5e6170aa0d22317/`
- Effective freeze: `2026-07-24T17:55:00+08:00`
- Package manifest SHA-256:
  `88f4d8ec54f3f878662d5f000ded138c8230e6a0689bd00bd189bd5d5a7465a8`
- Package `SHA256SUMS` SHA-256:
  `06cdb0bbd11f77b3023e84ba31bc7db7e61ab9ff1e20a3a85ffbd9230421f1c0`
- Binding manifest SHA-256:
  `f89abf5563a076c070addbca75382b7fe5d144b8ba7ab7ef43d56dbe16c873c2`
- Binding `SHA256SUMS` SHA-256:
  `e6d0da826f72944ae3f2b03ab4453a6b45356e31bbdfd430a5a334a38c9fee3a`
- Recursive package verifier: `valid`
- Denominator: 63 matches × 2 markets = 126 match-markets
- Included: 81 match-markets (p40 50; p42 31), 1,175 outcome rows
- Rejected: 45 match-markets (p40 13; p42 32), all `invalid_sp`
- Paired p40/p42 overlap: 31 matches
- Skipped candidate observations: 891 (`post_freeze_clock` 126;
  `invalid_sp` 765)
- Source clock range:
  `2026-07-24T17:53:39+08:00` to
  `2026-07-24T17:53:41+08:00`
- Fetch clock range:
  `2026-07-24T09:54:03Z` to `2026-07-24T09:54:04Z`
- Included match-market timing, min / p50 / p95 / max minutes:
  kickoff `35 / 545 / 1745 / 1805`; source staleness
  `1.316667 / 1.316667 / 1.35 / 1.35`; capture age
  `0.933333 / 0.95 / 0.95 / 0.95`
- Coordinator history at cutoff: 203 receipts, all `complete`, with no
  retry reason or failure. First receipt
  `2026-07-24T10:09:16.932099Z`; latest receipt
  `2026-07-26T06:26:11.126734Z`.

### Checkpoint 2

- Event ID:
  `4b2da70d1e5e6cf083daf50d661627e917f820190b4e177e1c900c11790435cd`
- Immutable package:
  `results/research/multimarket_segment_freeze_v1/26078/segment_02/4b2da70d1e5e6cf083daf50d661627e917f820190b4e177e1c900c11790435cd/`
- Effective freeze: `2026-07-26T00:55:00+08:00`
- Package manifest SHA-256:
  `4a07f723ce6d1551fefb5658541357bad26962a6034d8c96fe64de3f01ad2ba4`
- Package `SHA256SUMS` SHA-256:
  `6245e7e11e0d5cad7c26d6028e6b419519e6428f8f63b716a4e7bb85c2e358fc`
- Binding manifest SHA-256:
  `a4ed9ead59ae42d0d06c7aae8f57813f5234b38e11833b69229b753faf9e74fc`
- Binding `SHA256SUMS` SHA-256:
  `382143c6262cc3fb3a63f472a85ab92d059e1c222553f4e3308b0cbf76fd84e0`
- Recursive package verifier: `valid`
- Denominator: 72 matches × 2 markets = 144 match-markets
- Included: 110 match-markets (p40 70; p42 40), 1,560 outcome rows
- Rejected: 34 match-markets (p40 2; p42 32), all `invalid_sp`
- Paired p40/p42 overlap: 40 matches
- Skipped candidate observations: 5,383 (`post_freeze_clock` 144;
  `invalid_sp` 5,239)
- Source clock range:
  `2026-07-24T20:37:49+08:00` to
  `2026-07-26T00:40:22+08:00`
- Fetch clock range:
  `2026-07-24T12:39:03Z` to `2026-07-25T16:40:51Z`
- Included match-market timing, min / p50 / p95 / max minutes:
  kickoff `50 / 485 / 1325 / 1385` over 108 rows with a kickoff clock;
  source staleness
  `14.633333 / 14.633333 / 14.65 / 1697.183333`; capture age
  `14.15 / 14.166667 / 14.166667 / 1695.95`
- Match 79 has no published kickoff clock, so its two included market rows have
  no `minutes_to_kickoff`; this is disclosed rather than imputed. Both rows
  still satisfy the package's verified dual-clock, sale-state, completeness,
  and pre-freeze rules.
- Coordinator history at cutoff: 55 receipts, all `complete`, with no retry
  reason or failure. First receipt `2026-07-25T16:56:12.617077Z`; latest
  receipt `2026-07-26T06:26:11.169277Z`.

Both packages fix `execution_enabled=false`, `frontend_selectable=false`, and
`roi_authorized=false`. The preregistered mechanical predicate—two
automatically selected post-activation segment events, each with verified
immutable provenance, genuine pre-cutoff observations, and non-zero paired
p40/p42 overlap—is satisfied by the published ledger state.

## PI G4/G5 classification

- `G4 segment_asof_freeze_capability = READY_STRICT` for the declared
  prospective scope and rows that pass the frozen eligibility rules.
- `G5 immutable_publication_and_reproducibility = READY_STRICT` for the
  declared two-event operational scope.
- `market_coverage = PARTIAL`: paired coverage is 31/63 and 40/72; p42 rejects
  32 matches in each checkpoint as `invalid_sp`; checkpoint 2 contains two
  included market rows without a published kickoff clock; and maximum
  source/capture staleness is about 1,697 minutes.

This passes the preregistered operational capability gate. It does not
establish full-market availability, freshness sufficiency, market consistency,
calibration, predictive quality, statistical sample sufficiency, or ROI.
Issue #17 may close after this report is merged, but no downstream statistical
experiment is automatically authorized. A later consistency experiment may
consume only explicitly eligible overlap rows under its own preregistered
data-quality rules.

## Reproduction

```bash
.venv/bin/python -m pytest -q tests/scripts/test_multimarket_p0.py
.venv/bin/python scripts/manage_multimarket_p0.py freeze-segment --issue ISSUE --segment-idx SEGMENT_IDX --output-dir OUTPUT_ROOT
```

The fixture test reruns the same event, verifies byte-identical package content,
and rejects a tampered nested raw file and post-freeze candidate.
