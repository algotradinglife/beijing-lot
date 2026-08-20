# Issue #209 Gate-A handoff to Issue #210 (forward prospective boundary)

Emitted 2026-08-20 as part of the Gate-A exploration delivery. This handoff
preserves the reserved post-development outcomes and the prospective-validation
boundary (REQ-209-12) and grants no automatic production claim.

## Frozen Gate-A identity

- Candidate: **MARKET_ONLY_CELL** probability on the frozen #238 M×3 tensor
  (learned logistic/MLP did not beat the market control on 2022 tune).
- Ticket layer: **dynamic N ∈ [3,8], K ∈ [1,16]** policy surface; delivered
  dry-run used N7/K8 for the matched 2023 reference.
- Payout economics: **0.65 applied exactly once** per winning N-fold ticket's
  SP product (never 0.65^N) — REQ-209-06.

## Reserved / sealed

- **2024+ (issue codes 24xxx and later): sealed.** No 2024 label was opened in
  Gate A. `TERMINAL_2024_*` are all `None` / `NOT_OPENED_GATE_B_SEALED`.
- Gate B (one-shot 2024 terminal) requires an **independent PI authorization**
  after the Gate-A freeze review; it is a separate authorization, not automatic.

## Boundary for #210

- #210 (held-out/forward validation) must receive the Gate-A frozen identity
  and the reserved outcome boundary; no post-development outcome is consumed by
  the Gate-A fit/tune/calibration path.
- Prospective `initial/10h/1h` channels are `RETROSPECTIVE_RELATIVE_PROXY` and
  are not strict-forward claims; #210 proceedings must keep studying causal
  forward accumulation separately (#248).

## Evidence location

- Reusable code: `src/issue209/`
- Executed notebook: `notebooks/research/issue-209/bj209_gate_a.ipynb`
- Immutable results + manifest: `results/issue-209/` (`SHA256SUMS.txt`,
  `decision.json`, `census.csv`, parquet artifacts, capital path)
- Tests: `tests/issue209/` (golden metrics + REQ-E06 tamper)
- Protocol: `method.yaml` (preflight PASS)
