# HANDOFF — Issue #207

[SESSION] 20260812_080952_e25efb

Current branch: `analyst/bj207-issue`

Current HEAD: the evidence commit containing this document; resolve with `git rev-parse HEAD` after checkout.

## Completed

- Implemented the active fixed-N7 Stage-4 bankroll engine in `src/bankroll_policy/fixed_n7.py`.
- Reconstructed 68,880 exact source-bound #206 research requests for all five policies at K=8/16/32; K=8 controls and K=16/32 are sensitivity-only.
- Kept #206 NO_BET and cash in a separate SAFE lane as `LOWER_EXPOSURE_ONLY`.
- Added native ¥2, equal 1/5/25/100%, score-weighted 5%, simple logistic and bounded neural paths with exact integer ¥2 projection and no top-up.
- Bound chronology to CV-2021 fit, CV-2022 freeze, CV-2023 terminal historical evaluation; LOCKED_TEST outcomes remain unused.
- Added executable notebook, reusable CLI, focused tests, immutable 18-payload evidence package, decision report, three plots, Research Wiki entry and roadmap update.

## Decisions and rationale

- `ENGINE_VALID=true`: manifest, #206 source binding, exact K8 identity/source-cell reconstruction, capital conservation, integer projection, split boundary and semantic checks pass.
- `ACTIVE_OVERLAY_EVIDENCE=true`: one preregistered controlling row qualifies. `MARKET_WOR/K8/SIMPLE_LOGISTIC` beats equal weights by ¥4,012.10 ending capital and 4.0121 percentage points maximum drawdown on the exact same executable funding schedule; it beats score-weighted allocation by ¥4,137.48 on the same schedule.
- `DEPLOYABLE_POLICY=false`: the accepted comparable Stage-3 ticket baseline remains unresolved, this is retrospective CV-2023 evidence, and there is no strict independent confirmation. The result is hypothesis-generating only.
- Simple logistic was fitted before the bounded neural ablation to comply with package-first/minimal-controller discipline. Cash is never used to establish active lift.

## Known risks

Sparse N7 payouts dominate economics; only one learned K8 row qualifies. Results remain sensitive to candidate recall, ticket overlap, predicted SP, integer allocation and retrospective CV-2022 risk calibration. MARKET_WOR/native ¥2 remains the strongest absolute K8 path but still loses 0.7546%. No issue closure, merge, release, frontend selectability or downstream activation is authorized.

## Verification

- `PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py verify --output results/issue-207`
- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_bj207_bankroll.py`
- `PYTHONPATH=src .venv/bin/python scripts/execute_bj207_notebook.py --kernel python3`
- Full-suite result is recorded in the PR/issue handoff comment.

## Next state

Next state must be `EV Review`. EV should independently recompute exact K8 identities, common executable schedule matching, capital/payout accounting, holding metrics, SAFE lower-exposure attribution, chronology/LOCKED boundary, notebook clean-run and immutable replay. #208 must remain blocked until PI terminal review and explicit activation.
