# Beijing-lot Research Roadmap v1.0

## Project Positioning

Beijing-lot is a research system for studying:

- market information efficiency;
- decision chains;
- portfolio construction;
- long-term forward validation.

The objective is not to find a guaranteed prediction method, but to establish an auditable evidence chain.

```
Market Information
        ↓
Decision Information
        ↓
Portfolio Decision
        ↓
Forward Validation
```

## Integrated planning control plane

The historical Phase 0–5 record below remains the narrative research history.
GitHub planning uses a complementary cross-Project maturity roadmap:

| Layer | Responsibility |
| --- | --- |
| Project | The one durable functional home of an Issue; membership determines the responsible role |
| Milestone | The one PI-owned cross-Project maturity stage advanced by an Issue |
| Native Issue Graph | `blockedBy` / `blocking` dependencies and `parent` / `subIssues` decomposition |
| Issue Type | The authoritative kind of work |
| Project Status | The authoritative lifecycle state |
| Labels | Non-authoritative domain and work-type taxonomy only |
| Local Research OS | Derived cache or execution notes; never the planning source of truth |

The three Projects are:

- **BJ Data Platform** — sources, provenance, immutable datasets, freezes, and
  settlement truth;
- **BJ Prediction & Betting** — probability, models, decision chains,
  portfolios, and paper-only betting research;
- **BJ Product & Operations** — product workflows, runtime operations,
  observability, reliability, and the Research OS control plane.

The integrated maturity stages are:

| Milestone | Lifecycle | Stage question or goal |
| --- | --- | --- |
| M0 — Controlled Research Foundation | Completed | Is the auditable control plane needed to conduct research in place? |
| M1 — Research Data Readiness | Active | Which historical and forward assets support which claims under which provenance, time, and quality boundaries? |
| M2 — Probability and Model Evidence | Planned | Do market information and timestamp-safe football context add calibrated, reproducible probability information? |
| M3 — Decision and Portfolio Paper Evaluation | Planned | Do decision-chain and portfolio layers add separately measurable paper-only value? |
| M4 — Forward Operational Validation | Planned | Can frozen candidates operate prospectively and repeatedly under real collection, timing, and settlement conditions? |
| M5 — Release Readiness and Continuous Research | Planned | Has any candidate earned a separate controlled release review? |

Only PI may define, activate, close, rename, or change the lifecycle of a
Milestone. `Active` does not make every Issue in a stage executable, and
`Planned` is not dispatch or release authority. Each Issue still requires its
own contract and routing state. No Milestone authorizes execution, frontend
selectability, ROI claims, or automatic promotion to a later stage.

See
[`github_milestone_governance.md`](github_milestone_governance.md)
for the operating contract and
[`github_milestone_governance_receipt.md`](github_milestone_governance_receipt.md)
for the initial live mapping.

## Current unified-model roadmap

Updated: **2026-08-12 (Issue #207 producer evidence)**

The active program is [#202], which turns each issue's match × outcome tensor
into a four-stage decision path: probability/value representation, constrained
ticket construction, bankroll policy, and forward validation. Native GitHub
Issue Graph edges below are the execution authority; this section records the
PI interpretation and does not replace those edges or Project states.

```text
#203 causal M×3 tensor (Done)
             |
             v
#204 market-anchored probability/SP PoC (Done; market baseline retained)
             |
             v
#205 M×3 value matrix + fixed-N7 calibration (Done; market baseline retained)
             |
             v
#206 fixed-N7 ticket learning (Done; learned policy rejected, baseline unresolved)
             |
             v
#207 ¥100k active bankroll + separate NO_BET safety lane (EV Review pending)
             |
             v
#208 dynamic-N risk-conditioned frontier
             |
             v
#209 full-cycle historical ablation and baseline ladder
             |
             v
#210 held-out/prospective validation  <--- #218 causal support accumulation
             |
             v
#211 timestamped message overlay     <--- #182 message evidence
```

| Order | Issue | Live state | Milestone | Native dependency | Accepted or intended output |
| --- | --- | --- | --- | --- | --- |
| 1 | [#203] causal issue tensor | Closed / Done | M1 | #192 closed | Versioned issue × match × outcome data contract |
| 2 | [#204] residual probability and SP heads | Closed / Done | M2 | No open blocker | `MARKET_ONLY` retained as the safe baseline; residual model remains retrospective |
| 3 | [#205] M×3 value matrix and joint N7 calibration | Closed / Done | M2 | #204 closed | `MARKET_INDEPENDENCE` plus frozen pre-event SP is the safe #206 interface |
| 4 | [#206] fixed-N7 ticket generator | Closed / Done | M3 | #205 closed | Learned challenger rejected; no comparable accepted ticket baseline is bound, so all locked issues route to `NO_BET` |
| 5 | [#207] active bankroll + separate NO_BET safety lane | In Progress; producer evidence complete | M3 | #206 closed | Engine valid; one matched MARKET_WOR/K8 simple-controller signal; deployable policy remains false |
| 6 | [#208] dynamic-N frontier | Open | M3 | Blocked by #207 | Risk-conditioned N and parlay policy comparison |
| 7 | [#209] full-cycle historical evaluation | Open | M3 | Blocked by #208 | Chronological ablations and accepted baseline ladder |
| 8 | [#210] held-out/forward validation | Open | M4 | Blocked by #209 and #218 | Model-unseen audit plus frozen prospective evidence |
| 9 | [#211] message overlay | Open | M4 | Blocked by #210 and #182 | Incremental timestamped message evidence on the frozen policy |

### #205 terminal decision and downstream contract

- The dependence challenger improved locked joint log loss and payout MAE, but
  it was slightly worse than model independence on chronological CV and worse
  than market on locked Brier. It is promising retrospective evidence, not a
  validated edge.
- The controlling disposition is `INHERIT_EXACT_MARKET_BASELINE`. #206 may use
  only `control_probability` (`MARKET_ONLY`, `FROZEN_SAFE_BASELINE`) with the
  frozen pre-event SP head and `MARKET_INDEPENDENCE` as its safe lane.
- All `LOGISTIC_RESIDUAL` values are explicitly `experimental_*`,
  `RETROSPECTIVE_PROXY_METHOD_CORRECTION`, `promoted=false`, and ablation-only
  until #210 confirmation. They cannot silently replace the safe control.
- Closing #205 removes the native blocker from #206, but does not itself
  authorize execution. PI/user review must place #206 into an executable
  Project state.

The baseline ladder remains mandatory: every downstream model reports both
absolute performance and matched lift against its inherited frozen control.
No improvement is accepted when it arises only from lower stake, cash
retention, fewer tickets, post-outcome parameter choice, or an ungraded
retrospective feature.

### #206 research decision and Stage-3 handoff

- Every requested identity has exactly seven distinct matches, while each
  ticket selects its own subset from the complete issue pool. The #205
  first-seven calibration roster is not reused as the action universe.
- Chronology is CV-2021 train, CV-2022 policy/K selection and CV-2023 final
  historical evaluation. LOCKED_TEST 2025/2026 labels remain embargoed; its
  output is a label-blind requested-ticket ledger only.
- The best local matched comparator was MARKET_WR at K=8, but #205 accepted a
  probability scorer rather than a comparable Stage-3 ticket policy. MARKET_WR
  is therefore diagnostic and is not inherited as a deployable frozen baseline.
- The same-K LEARNED_MLP challenger had CV-2022 point matched realized lift
  +0.875233, but its Bonferroni-adjusted one-sided lower bound was -2.403563.
  Raw independence × predicted-SP expected utility is diagnostic only. The
  controlling disposition is `LEARNED_POLICY_REJECTED_BASELINE_UNRESOLVED`.
- Every locked issue deterministically routes to `NO_BET` with zero requested
  tickets/stake until PI binds a comparable accepted ticket baseline. This is a
  Stage-3 request decision, not final bankroll or position-sizing authority.
- The exploratory LOGISTIC_BASELINE/K16 row returned +67.88% realized pre-tax
  net on CV-2023 after -68.70% on CV-2022. It uses K16 turnover rather than the
  selected K8 matched budget and is consistent with one sparse payout, so it is
  a non-promotable follow-up clue rather than stable edge evidence.
- The negative result is scoped to the bounded 55,042-candidate generator and
  current feature/calibration contract; it does not reject ticket-subset learning
  generally. Closing #206 clears its native blocker, but #207 is not activated
  until PI adjusts its contract so the zero-request handoff does not collapse
  Stage 4 into a cash-only tautology or silently promote the local comparator.
- Evidence: [`issue_206_fixed_n7_ticket_policy.md`](issue_206_fixed_n7_ticket_policy.md).

### #207 active Stage-4 bankroll decision

- Lane A reconstructs 68,880 exact #206 research-only requests for the frozen
  five-policy K8 controlling panel plus K16/K32 sensitivities. Lane B retains
  #206 NO_BET and cash separately as `LOWER_EXPOSURE_ONLY`.
- CV-2021 fits the simple logistic controller before the bounded neural
  ablation; CV-2022 freezes both learned risk fractions at 1%; CV-2023 is the
  sole terminal historical evaluation. LOCKED_TEST labels remain embargoed.
- The strongest absolute K8 path is MARKET_WOR/native ¥2: ending capital
  ¥99,245.38 (-0.7546%), turnover ¥880 and maximum drawdown 0.7546%.
- On the exact MARKET_WOR/K8 simple-controller yuan schedule, equal weights end
  ¥4,012.10 lower and have 4.0121 percentage points more maximum drawdown; the
  matched score-weighted component ends ¥4,137.48 lower. This yields one
  hypothesis-generating `ACTIVE_OVERLAY_EVIDENCE=true` row.
- `ENGINE_VALID=true`, but `DEPLOYABLE_POLICY=false`: the accepted comparable
  Stage-3 baseline is unresolved and no strict confirmation exists. Cash does
  not answer the active question, and #208 remains blocked pending PI terminal
  review and explicit activation.
- Evidence: [`issue_207_fixed_n7_bankroll.md`](issue_207_fixed_n7_bankroll.md).

[#182]: https://github.com/algotradinglife/beijing-lot/issues/182
[#192]: https://github.com/algotradinglife/beijing-lot/issues/192
[#202]: https://github.com/algotradinglife/beijing-lot/issues/202
[#203]: https://github.com/algotradinglife/beijing-lot/issues/203
[#204]: https://github.com/algotradinglife/beijing-lot/issues/204
[#205]: https://github.com/algotradinglife/beijing-lot/issues/205
[#206]: https://github.com/algotradinglife/beijing-lot/issues/206
[#207]: https://github.com/algotradinglife/beijing-lot/issues/207
[#208]: https://github.com/algotradinglife/beijing-lot/issues/208
[#209]: https://github.com/algotradinglife/beijing-lot/issues/209
[#210]: https://github.com/algotradinglife/beijing-lot/issues/210
[#211]: https://github.com/algotradinglife/beijing-lot/issues/211
[#218]: https://github.com/algotradinglife/beijing-lot/issues/218

---

## Historical Phase 0–5 record

# Phase 0: Research Infrastructure (Completed)

## Data Foundation

- Beijing-lot live database
- SP snapshots
- settlement data
- as-of information boundary

## Strategy Archaeology

- Historical strategy audit
- Evidence classification
- Failed direction archive

## Freeze System

Completed:

- Freeze Protocol v1
- Freeze Automation v1
- Forward Dataset Pipeline

Purpose:

Create reproducible and auditable forward research samples.

---

# Phase 1: Market Information Research

Research question:

> How much information is contained in Beijing-lot market prices?

## SP-EFF-001 (Completed)

Question:

Does SP contain calibrated probability information?

Conclusion:

SP contains directional probability information. This does not prove exploitable betting advantage.

## Multi-Market Data Audit

Goal:

Determine research readiness of different markets:

- Handicap 3/1/0
- Correct Score
- Total Goals
- Half/Full Time

Check:

- data availability;
- pre-event snapshot;
- freeze support;
- settlement support.

## SP-CONSISTENCY-001

Study whether different markets represent a consistent probability space.

Example:

Correct Score distribution → win/draw/loss probability → compare with handicap market.

## SP-MOVEMENT-001

Study whether SP movement contains incremental information.

---

# Phase 2: Decision Chain Research

Research question:

> Can structured football reasoning improve decisions beyond market information?

Decision Chain is not a pure prediction model. It converts information into a structured decision process.

Inputs:

- market information;
- match context;
- risk assessment.

Outputs:

- primary decision;
- confidence;
- reasoning chain;
- protection requirements.

## Decision Chain Framework

Versions:

- v3.3.3
- v4.2

Research goal:

Compare:

SP only

vs

SP + Decision Chain

---

# Phase 3: Portfolio Construction Research

Research question:

> Given a decision, how should selections be combined into N-leg structures?

Focus:

- N-leg construction;
- protection legs;
- risk management;
- stake allocation.

Protection legs are studied as failure-risk reduction mechanisms, not as independent predictions.

Metrics:

- failure rate;
- survival rate;
- drawdown;
- risk-adjusted performance.

---

# Phase 4: Forward Validation

Use Freeze Automation to accumulate:

- 100 issues;
- 500 issues;
- 1000 issues.

Validate:

- market findings;
- decision chains;
- portfolio methods.

---

# Phase 5: Advanced Modeling

Potential directions:

- football probability models;
- Bayesian models;
- multi-market fusion;
- advanced portfolio optimization.

---

# Research Principles

1. Observation is not a law.
2. Backtest is not forward validation.
3. Single-period profit is not evidence.
4. All experiments require freeze, registry and review.
5. Probability information, decision quality and portfolio construction must be evaluated separately.
