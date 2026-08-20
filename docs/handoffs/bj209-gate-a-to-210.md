# Issue #209 Gate-A handoff to Issue #210 (forward prospective boundary)

Emitted 2026-08-20 as part of the Gate-A exploration delivery. This handoff
preserves the reserved post-development outcomes and the prospective-validation
boundary (REQ-209-12) and grants no automatic production claim.

## Frozen Gate-A identity

- Candidate: **MARKET_ONLY_CELL** probability on the frozen #238 M×3 tensor
  (learned logistic/MLP did not beat the market control on 2022 tune).
- Ticket layer tested a learned action-conditioned surface over
  N={3,5,7,8}, K={8,32,128,512}, TOP_VALUE/WR/WOR and NO_BET.  The frozen
  2023 mapping selected six configurations, but ended at CNY98,838.66 versus
  CNY99,152.00 for fixed N7/K8 TOP_VALUE (matched lift -0.316pp).
- Disposition: **RETAIN_FIXED_CONTROL_NO_PROMOTION**.  The dynamic interface is
  valid, but the candidate failed out-of-time generalization and is not the
  frozen #210 policy.
- Payout economics: **0.65 applied exactly once** per winning N-fold ticket's
  SP product (never 0.65^N) — REQ-209-06.

## Reserved / sealed

- **2024+ (issue codes 24xxx and later): sealed.** No 2024 label was opened in
  Gate A. `TERMINAL_2024_*` are all `None` / `NOT_OPENED_GATE_B_SEALED`.
- Gate B (one-shot 2024 terminal) remains unauthorized.  The failed 2023
  candidate does not spend the terminal holdout.

## Boundary for #210

- #210 may start only after a future candidate beats the frozen control on an
  untouched pre-2024 block.  It must receive that exact identity and the
  reserved outcome boundary; #209 itself supplies no promoted dynamic policy.
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
