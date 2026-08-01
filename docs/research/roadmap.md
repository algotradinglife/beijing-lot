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

## Current strategy evidence roadmap

Updated: **2026-08-01 20:42 CST (UTC+08:00)**

The current bottleneck is evidence of durable outcome-level price value, not
another unconstrained portfolio search. Accepted work already provides rolling
out-of-sample calibrated probabilities ([#89]) and outcome-safe predicted BJDC
SP vectors ([#90]). Later N-leg, pruning, and sampling studies ([#91], [#95],
[#98], and [#101]) showed that stake reduction or isolated positive cells do
not by themselves overcome the 0.65 factor, tax, and payout concentration.

The active sequence therefore separates source of edge, entry selection, and
portfolio packaging:

```text
#89 calibrated probability + #90 predicted SP (Done)
                         |
                         v
#106 outcome-level q = p x SP value atlas (Ready)
                /                    \
               v                      v
#107 issue-level value gate       #105 joint N7 construction
             (Inbox)                    (Blocked)
                \                    /
                         v
#108 tax-aware dynamic-N and path frontier (Inbox)
```

| Order | Issue | Project status | Milestone | Native dependency | Intended output |
| --- | --- | --- | --- | --- | --- |
| 1 | [#106] outcome-level probability-SP value atlas | Ready | M2 | #89 and #90 (closed) | At most two robust value pockets, or `NO_PROMOTION` |
| 2A | [#107] issue-level value-density/no-bet gate | Inbox | M3 | Blocked by #106 | One deterministic issue-entry gate, or `NO_PROMOTION` |
| 2B | [#105] joint match selection, pruning and GM-SP gate | Blocked | M3 | Blocked by #106 | Fixed-N7 joint construction result |
| 3 | [#108] tax-aware dynamic-N asymmetric path frontier | Inbox | M3 | Blocked by #105 and #107 | Tax-adjusted dynamic-N comparison |

Only #106 is executable now. #90 is reused rather than duplicated: it already
produced an accepted historical predicted-SP candidate. Downstream issues may
consume accepted immutable artifacts, but may not refit upstream models after
outcome access. A relative improvement from a still-negative baseline, lower
stake, or higher hit rate is not promotion evidence; positive tax-adjusted OOS
EV/ROI and robustness remain required.

[#89]: https://github.com/algotradinglife/beijing-lot/issues/89
[#90]: https://github.com/algotradinglife/beijing-lot/issues/90
[#91]: https://github.com/algotradinglife/beijing-lot/issues/91
[#95]: https://github.com/algotradinglife/beijing-lot/issues/95
[#98]: https://github.com/algotradinglife/beijing-lot/issues/98
[#101]: https://github.com/algotradinglife/beijing-lot/issues/101
[#105]: https://github.com/algotradinglife/beijing-lot/issues/105
[#106]: https://github.com/algotradinglife/beijing-lot/issues/106
[#107]: https://github.com/algotradinglife/beijing-lot/issues/107
[#108]: https://github.com/algotradinglife/beijing-lot/issues/108

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
