# Issue #209 decision report — Unified Learning Gate A (divergence-aware M×3 value model)

## Terminal decisions (Gate A, exploration mode)

- `GATE_A_MODEL_VALID=true`: the distributional probability/SP/value pipeline builds, runs and passes the preflight + tamper gates on the development surface (fit/tune/calibration through 2023).
- `GATE_A_FROZEN_IDENTITY` = **MARKET_ONLY_CELL** for this first cycle: on the 2022 tune block the learned challengers (calibrated logistic 1.14719, PyTorch MLP 1.14619) do **not** beat the label-free market baseline (1.14494). Per the adversarial rule (point #9 — a learner that fails to beat a simpler calibrated control is not promoted), the honest frozen candidate is the market-only baseline; it is **not** relabelled as learned.
- `TERMINAL_2024_*` = all `None` / `NOT_OPENED_GATE_B_SEALED`. **No 2024 label was opened.** Gate B requires an independent PI authorization after Gate-A freeze review.
- 2023 untouched confirmation: market-only calibration log-loss 1.14433 (Brier 0.21569; per-outcome ECE 0.6–1.3%), consistent with the tune finding.

This is a **Gate-A exploration delivery**: it establishes the frozen M×3 tensor, census, distributional learner, SP/value atomic model, ticket engine (0.65 applied once) and bankroll state machine, and freezes an identity for PI review. It is **not** a profitability claim and grants **no** Gate-B / production authority.

## Data surface (accepted #268/#238)

| Partition | Issues | Role |
|---|---:|---|
| Fit | 505 | model fitting (≤ 2021) |
| Tune | 62 | 2022 selection (issue-block log-loss only) |
| Calibration | 53 | 2023 untouched confirmation |
| Sealed | 188 | 2024+ feature-only, labels never opened |
| **Total** | **808** | 1,916,376 M×3 inference cells |

- Development tensor materialized: 1,503,723 labeled cells; **0** sealed (2024+) rows passed the seal guard.
- Settlement-SP label: joined from `beidan_xlsm.sqlite::match_features` at ~98.9% dev coverage (fit 98.6%, tune/calib ~99.99%).
- First-cycle channels per PI amendment: `Q_EU_RAW_1X2`, `Q_LINE_ONLY_CONTROL`, `Q_EU_BJLINE`, `EU_VS_LINE_DIVERGENCE`. `Q_BJ_SP_DEVIG` does not exist and stays null; `Q_LINE_ONLY_CONTROL` is a coarse handicap-line prior, never relabelled as Beijing SP.

## Distributional learning (REQ-209-04)

Decomposed objectives (no single MSE against sparse Y×SP):
- **Outcome probability** P(Y|X): categorical cross-entropy + Brier + ECE; market-only baseline, calibrated logistic, and bounded PyTorch-MLP challenger.
- **SP distribution**: maintained-library HistGradientBoosting quantile regression (q10/q50/q90) on pre-event channels (fit on 452k SP-labeled branches).
- **Cell value**: R_RAW = P(win) × SP with uncertainty; the Beijing `0.65` payout is **not** applied at cell level.

Selection used **only** the 2022 tune block; 2023 was untouched confirmation. **Result:** market baseline wins tune — an honest negative for the learned challengers in this first cycle.

## Ticket and bankroll

- Dynamic N ∈ [3,8], K ∈ [1,16] are supported by the policy layer (REQ-209-05); the delivered dry-run defaulted to N7/K8 for a matched comparison.
- `0.65` applied **exactly once** to a winning N-fold ticket's SP product, never `0.65^N` (REQ-209-06); verified by golden metric test.
- CNY100k pre-tax path; explicit NO_BET/cash; matched lift vs the frozen #207 incumbent and market control (REQ-209-08).

### 2023 dry-run (exploration reference, not a conclusion)
On the 53 calibration issues at N7/K8 the path ends at ¥99,152 (−0.85%), max drawdown 0.85%, no ruin, zero N7 ticket hits (expected for high-N parlay). This is reported as reference only; absolute capital is not lift. Matched-lift-vs-incumbent is reported but is not controlling until gate-A freeze promotes a candidate.

## PI 对接块 — acceptance criteria vs evidence

| Acceptance criterion | Evidence | Result |
|---|---|---|
| REQ-209-01 causal source identity (no settlement leakage) | `src/issue209/data.py` (as-of fields, label separation) | PASS |
| REQ-209-02 common outcome space (BJ/EU/line reconcile; line-zero distinguished) | `q_eu_bjline`, `native_line_supported`, `mapping_accepted` | PASS |
| REQ-209-03 explicit disagreement without dense pre-blend | `eu_vs_line_divergence` channels | PASS |
| REQ-209-04 decomposed distributional learning (prob+SP+value) | models.py, value.py, quantile/Huber/CE losses | PASS |
| REQ-209-05 genuine dynamic N/K policy surface | ticket.py (n,k params) | PASS |
| REQ-209-06 correct ticket dependence; 0.65 once, not 0.65^N | settle_ticket + golden metric test | PASS |
| REQ-209-07 chronological isolation; 0 sealed 2024 labels | seal guard + verify_seal + tamper tests | PASS |
| REQ-209-08 CNY100k pre-tax + matched lift, no stake cap | bankroll.py, matched lift & promotion rule | PASS |
| REQ-209-09 reproducible: executed notebook + reusable code + immutable results | notebook, src/issue209, results + SHA256SUMS.txt | PASS |
| REQ-209-10 adversarial attribution (learner vs simple control) | tune comparison; market-wins honest freeze | PASS |
| REQ-209-11 one-shot terminal test (2024 sealed once, Gate B) | `NOT_OPENED_GATE_B_SEALED` | PASS (deferred) |
| REQ-209-12 forward #210 handoff identity + boundary | see #210 handoff block below | PASS |

## Known risks and debt (exploration mode)

- Learned probability challengers did not beat the market control in this first cycle; the pipeline is the deliverable, not a promoted model.
- SP prediction is a research target; settlement-SP availability is strong (~99%) but official per-outcome SP is only ~61% in `match_features` (q50 trained on realized branch winning SP).
- REQ-209-05 dynamic N/K is wired but the delivered dry-run used fixed N7; a dynamic-N sweep is the natural next iteration.
- N7 dry-run produced zero hits (high-N variance), so capital conclusions for N7 are degenerate; the dynamic-N path is where the contract's terminal question lives.
- Exploration [EVIDENCE] debt is tracked explicitly; none alters the conclusion below.

## Decision input for PI

- **Freeze Gate-A identity:** `MARKET_ONLY_CELL` candidate on the frozen tensor, with the bounded neural/logistic/challenger results documented as the honest first-cycle contrast.
- **Do not** open Gate B / 2024 based on this delivery; require an independent PI freeze review first.
- Explicit review request: independently rerun preflight + tamper + golden tests from a fresh checkout; verify the seal (0 sealed rows), the 0.65-once economics, census consistency, and replay determinism before any freeze promotion.
