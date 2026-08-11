# Issue #206 decision report — fixed-N7 ticket policy learning

## Decision

`INHERIT_MATCHED_MARKET_CONTROL`. The prior-only CV_2022 selection chose `LOGIT_Q_WOR` with K=64. Its issue-block bootstrap 95% realized-ROI lift interval versus the matched `MARKET_Q_WOR` was [-0.6908, +1.7170]. The deterministic learned gate was disabled, so unsupported issues route byte-exactly to the matched market control.

On held-out CV_2023 (the last label-eligible fold), fallback-mixed realized ROI was -0.7105 versus -0.7105; matched lift was +0.0000. Distinct-ticket coverage lift was +0.0000. The policy therefore does not meet the preregistered no-worse-plus-gain rule.

## Absolute and matched evidence

`policy_surface.csv` reports absolute expected/realized ROI, issue hit coverage, ticket coverage, match overlap, ticket-stake HHI, gross HHI, repeats and turnover. It also reports matched lifts against the same issue/K/stake `MARKET_Q_WOR`. `BEST_FULL_FULL` is reported separately at 2,187 tickets (¥4,374) and is never presented as capital-matched to smaller K.

## Controls and ablations

- Safe controls: accepted `BEST_FULL_FULL` and full-pool `MARKET_Q_WOR` on the promoted #205 market/SP interface.
- Simple controls: market temperature 0.75/1.25, market WR, deterministic bounded top mass and Hamilton residual integer allocation.
- Risk-preference controls: the same market proposal family with a tunable 5/7 overlap cap or 0.5 overlap penalty, always compared at matched K/stake; neither is treated as a universal rule.
- Learned controls: package-backed multinomial logistic regression and scikit-learn MLP. The residual-channel MLP is explicitly retrospective, non-promoted and ablation-only.
- Every ticket selects its own seven-match subset from the complete issue pool. There is no inherited first-seven roster.

## Failure regimes and risks

Sparse seven-leg hits make realized utility noisy; CV_2022 selection is separated from held-out CV_2023 evaluation. The OOD gate uses standardized feature support and falls back above 20% issue-level OOD. 2025/2026 label and official-SP fields are nulled before inference, so locked rows provide requested tickets only. Top-mass search is intentionally bounded to the eight highest issue match weights; it is a control, not proof of global combinatorial optimality. `joblib` artifacts are version-bound to the frozen environment.

## Stage-3 handoff

`ticket_ledger.parquet` preserves ticket identity, selected match subset, outcomes, source probability product, predicted-SP product, expected utility, repeat rows, fallback reason and requested ¥2 stake. It grants no Stage-4 bankroll or final-capital authority.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Exact N=7 and per-ticket independent subset | `policy_contract.json`, verifier, ticket ledger | PASS |
| K/WR/WOR/repeat/overlap and fallback trace | `policy_surface.csv`, `fallback_trace.csv` | PASS |
| Absolute plus matched same-stake lift | `policy_surface.csv` | PASS |
| Chronology; no 2025-04+ label read | fold models, nulled locked labels, verifier/tests | PASS |
| Simple/package baseline before neural | logistic/market controls then sklearn MLP | PASS |
| Fallback-mixed no worse plus preregistered gain | `decision.json` | FAIL — inherit matched market control |
| Notebook/code/artifact layers | issue notebook, `src/ticket_policy`, this package | PASS |

Decision input: inherit the matched market-weighted control at the selected K; retain BEST_FULL/FULL as the unequal-capital absolute control. Known risks: sparse payouts, bounded top-mass search, historical support shift and version-bound model serialization. Explicit review request: independently replay the notebook/package; mutate all 2025+ labels; verify exact ticket constraints, matched stake, control-copy fallback bytes, model chronology, overlap/repeat accounting and the conservative disposition. No merge, issue closure, betting or capital sizing is requested.
