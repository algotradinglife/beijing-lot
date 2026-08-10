# Issue #205 decision report — M×3 value matrix and joint N7 payoff calibration

## Decision

`INHERIT_EXACT_MARKET_BASELINE`. The preregistered metric is joint log loss (lower is better). The CV-selected challenger was `SIMPLE_REGIME_DEPENDENCE`. Locked matched joint log loss was 8.111346 versus 8.175457 for the exact market-independence baseline. The inherited scorer is `MARKET_INDEPENDENCE`.

The challenger did not advance despite its better locked log loss. On chronological CV, `SIMPLE_REGIME_DEPENDENCE` scored 8.107767 versus 8.107558 for `MODEL_INDEPENDENCE` (+0.000208, lower is better). On locked data its Brier score was also worse than market by +0.000176, although locked log loss and payout MAE improved. This is promising retrospective dependence evidence, not a validated edge and not evidence that dependence has no value.

## Absolute and matched evidence

See `metrics.csv` for absolute joint log loss, Brier, payout error and predicted/realized net, plus matched lifts versus the same locked market rows. Covered-case and fallback counts are reported separately. The locked challenger covered 75 issues and fell back on 0.

## Challenger analysis and risks

- Sparse payouts: each issue contributes all 2,187 possible N7 outcome identities and exactly one realized hit; proper joint log loss is primary, while payout MAE is diagnostic.
- One-issue concentration: each issue contributes one deterministic first-seven panel and equal issue weight.
- Final-SP leakage: official final SP is retained only as a label channel; scoring uses the frozen #204 pre-event SP-head prediction. It is never an inference feature in the dependence layer.
- Support shift: source/feature context outside frozen development support uses the exact market baseline; issues with fewer than seven valid matches emit `NO_BET_LT7`.
- Proxy boundary: this is retrospective proxy evidence and grants no production, betting or #210 authority.

## Value representation inherited by ticket learning

Ticket learning inherits only the schema's safe-control lane: `control_probability` (`MARKET_ONLY`, `FROZEN_SAFE_BASELINE`, promoted) plus the frozen pre-event SP head and `MARKET_INDEPENDENCE`. The logistic-residual probability, residual, gross/net and displayed utility are explicitly named `experimental_*`, graded `RETROSPECTIVE_PROXY_METHOD_CORRECTION`, `promoted=false`, dependent on #210 confirmation, and allowed only as ablation features. Neither displayed scalar replaces its underlying channels.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Exact zero-correction baseline | Exhaustive product `MARKET_INDEPENDENCE`; fallback copies it byte-for-byte | PASS |
| Fixed N=7, no sampling/portfolio optimization | Deterministic first-seven roster plus exhaustive 3^7 identities | PASS |
| Chronological calibration and ablations | CV_2022/CV_2023 then locked test; market, model independence, simple and latent-set controls | PASS |
| Fallback-mixed no worse and dependence lift | `decision.json`, `metrics.csv` | FAIL — baseline inherited |
| Notebook/code/artifact layers | issue notebook, `src/unified_value/joint_n7.py`, this package | PASS |

Decision input: accept `MARKET_INDEPENDENCE` and only the safe-control columns as the #206 controlling interface; keep `experimental_*` columns behind an explicitly source-graded ablation boundary. Known risks: retrospective proxy grade, one fixed N7 roster per issue, sparse realized configurations and frozen #204 SP-head error. Explicit review request: verify control/experimental lane provenance, absence of unlabeled accepted “true probability”, unchanged identity/no-leak/matched-lift/fallback mechanics, and the conservative advancement decision. Do not merge or close until independent EV and PI review.
