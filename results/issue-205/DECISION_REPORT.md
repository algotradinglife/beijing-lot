# Issue #205 decision report — M×3 value matrix and joint N7 payoff calibration

## Decision

`INHERIT_EXACT_MARKET_BASELINE`. The preregistered metric is joint log loss (lower is better). The CV-selected challenger was `SIMPLE_REGIME_DEPENDENCE`. Locked matched joint log loss was 8.111346 versus 8.175457 for the exact market-independence baseline. The inherited scorer is `MARKET_INDEPENDENCE`.

## Absolute and matched evidence

See `metrics.csv` for absolute joint log loss, Brier, payout error and predicted/realized net, plus matched lifts versus the same locked market rows. Covered-case and fallback counts are reported separately. The locked challenger covered 75 issues and fell back on 0.

## Challenger analysis and risks

- Sparse payouts: each issue contributes all 2,187 possible N7 outcome identities and exactly one realized hit; proper joint log loss is primary, while payout MAE is diagnostic.
- One-issue concentration: each issue contributes one deterministic first-seven panel and equal issue weight.
- Final-SP leakage: official final SP is retained only as a label channel; scoring uses the frozen #204 pre-event SP-head prediction. It is never an inference feature in the dependence layer.
- Support shift: source/feature context outside frozen development support uses the exact market baseline; issues with fewer than seven valid matches emit `NO_BET_LT7`.
- Proxy boundary: this is retrospective proxy evidence and grants no production, betting or #210 authority.

## Value representation inherited by ticket learning

Ticket learning inherits the versioned long-form J×3 schema in `value_matrix_schema.json`: calibrated probability, SP prediction, uncertainty, residual, gross and pre-tax-net remain separate. `displayed_scalar_utility` is only the documented projection `0.65*p*SP-1`, not a replacement for those channels.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Exact zero-correction baseline | Exhaustive product `MARKET_INDEPENDENCE`; fallback copies it byte-for-byte | PASS |
| Fixed N=7, no sampling/portfolio optimization | Deterministic first-seven roster plus exhaustive 3^7 identities | PASS |
| Chronological calibration and ablations | CV_2022/CV_2023 then locked test; market, model independence, simple and latent-set controls | PASS |
| Fallback-mixed no worse and dependence lift | `decision.json`, `metrics.csv` | FAIL — baseline inherited |
| Notebook/code/artifact layers | issue notebook, `src/unified_value/joint_n7.py`, this package | PASS |

Decision input: accept `MARKET_INDEPENDENCE` as the #206 interface. Known risks: retrospective proxy grade, one fixed N7 roster per issue, sparse realized configurations and frozen #204 SP-head error. Explicit review request: verify identity construction, no-leak SP channel, matched-lift arithmetic, OOD fallback identity, and the conservative advancement decision. Do not merge or close until independent EV and PI review.
