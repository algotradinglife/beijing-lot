# HANDOFF — Issue #208 REWORK v2 (fresh)

[SESSION] 20260814_233747_be422d

## Current state

- Branch: `analyst/bj208-rework-r1` (worktree `/home/drwho1985/workspace/soccer/beijing-lot-bj208-r1`)
- Upstream base: 53f67ec (old PR #228 head, contains tracked results/issue-205 + issue-207)
- This PR supersedes PR #228 (EV REJECT 53f67ec, REWORK_TYPE=method)

## What was done (fresh rework, EV D1-D6 + REQ-E09)

1. **D1 evidence chain**: `results/issue-208/` fully committed (61 files in
   manifest incl. models/*.joblib, schema.json, provenance.json, receipt.sha256,
   COMPLETED.json). `.gitignore` now allows issue-208. Fresh checkout can
   re-verify without worker-local files.
2. **D2 capital semantics**: SIMPLE_ACTIVE = exact #207 EQUAL_1PCT
   (requested=pre*1%, integer ¥2-unit projection over K tickets).
   `capital_change_identical` binds frozen CONTROLLING identities — verified
   to match the #207 EQUAL_1PCT ledger to 7 decimals (¥64,659.136… on CV_2023).
3. **D3 leakage/serialization**: sklearn early_stopping disabled everywhere;
   chronological issue-block validation (last 15% train issues); Ridge +
   best-fixed controls evaluated per fold with full paths + ablation;
   model weights + scaler serialized to models/fold*.joblib (handoff
   label-blind replayable).
4. **D4 verifier**: manifest full coverage (relative paths + unlisted check),
   provenance trusted-hash validation, capital accounting (start ¥100,000,
   ¥2 units, requested/funded/K, continuity), N/K semantics with K, outcome
   triple validation, REAL 2024-mutation invariance test. Tamper suite attacks
   the production verify_package on full package copies — 4/4 detected.
5. **D5 metrics**: max drawdown = running peak (golden test [100,80,200]→0.2);
   golden tests bound to production functions; added time-under-water,
   recovery, max consecutive losses, rolling 5/10/20 loss + worst windows.
6. **D6 atomicity**: staging dir + fsync + COMPLETED before final manifest +
   atomic rename; NO_BET explicit for infeasible/OOD/incumbent-infeasible.

## Key decisions

- Selection rule wording superseded (#208-3): "positive on ALL constructible
  folds (2 of 2)" — fold 0 remains non-constructible (DELTA #208-1).
- Protocol/contract versions bumped to v2 (PROTOCOL-LOG rows #208-2..#208-6).
- Terminal result unchanged in direction: safety-gated learned path ≡ frozen
  incumbent (matched lift 0.0 on both folds) → freeze N7/K8/MARKET_WOR/
  native-¥2 incumbent for #209. But the corrected capital semantics changed
  the control evidence materially: capital_change_identical (EQUAL_1PCT)
  ends ¥64,659 (not ¥101,425), static_n8k8 ends ¥100,810, best_fixed(N4K32)
  ¥88,604.

## Known issues

- MLP ConvergenceWarning (max_iter=500) on both folds — benign, early_stopping
  off, loss curve decreasing; validation RMSE (1,555) < fit RMSE (1,976).
- 731/68,417 matches have zero realized True (unlabeled matches) — loader
  treats ≤1 realized True as valid (duplicates still fail).
- 6 LOCKED_TEST rows have official SP = 0.0 — treated as void sentinel;
  negative SP still fails.

## Next step

- EV independent audit at this PR's HEAD: fresh checkout, re-run
  notebook/verify/preflight/pytest, tamper probes, REQ-208-01..09 evidence.
- If REJECT: follow REWORK_TYPE branch (method → fresh / minor → resume).

## Replay

```
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py verify --output results/issue-208
PYTHONPATH=src .venv/bin/python -m pytest tests/test_bj208_metrics.py tests/test_bj208_tamper.py
```
