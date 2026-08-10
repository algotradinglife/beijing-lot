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

Updated: **2026-08-11 01:22 HKT (UTC+08:00)**

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
#206 fixed-N7 ticket learning (awaiting PI/user activation)
             |
             v
#207 ¥100k bankroll + NO_BET policy
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
| 4 | [#206] fixed-N7 ticket generator | Open; activation pending | M3 | #205 closed | Constraint-valid ticket policy with exact safe-control fallback |
| 5 | [#207] bankroll/NO_BET integration | Open | M3 | Blocked by #206 | ¥100k capital path and safe abstention policy |
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
