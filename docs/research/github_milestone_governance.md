# GitHub milestone governance

Capability: `BJ-MILESTONE-CONTROL-001`

This document defines the PI-owned integrated roadmap across the three broad
GitHub Projects. It changes planning metadata only. It does not change data,
collectors, models, strategies, portfolios, tickets, runtime, APIs, frontend,
deployment, release authority, or Research OS evidence state.

## Planning semantics

| Layer | Sole responsibility |
| --- | --- |
| GitHub Project | The durable functional home of an Issue |
| Milestone | The cross-Project research maturity stage advanced by an Issue |
| Labels | Fine domain, work type, owner, and dispatch state |
| Issue | The executable contract |
| Pull request | Implementation and review evidence |
| `.research/graph.yaml` | Scientific and evidence dependencies |
| `docs/research/roadmap.md` | Narrative research direction and historical record |

An Issue has exactly one primary Project and at most one Milestone. A Milestone
does not replace Project ownership, routing labels, Issue dependencies, or
Research OS gates. Cross-Project dependencies remain linked Issues.

## Authority and lifecycle

PI alone may define, create, open, close, rename, or change the lifecycle of a
Milestone. Engineer may configure a Milestone or mapping only from an explicit
PI Issue or comment. Strategist and Engineer request moves with `[TO: PI]`; they
do not move Issues themselves.

Lifecycle is stated in each Milestone description:

- `COMPLETED` means PI has accepted the exit gate and the Milestone is closed;
- `ACTIVE` means the stage is the current integrated maturity focus;
- `PLANNED` means the stage is defined but not activated.

GitHub exposes only open/closed Milestone state, so `ACTIVE` and `PLANNED` remain
explicit description-level semantics. A due date is optional and may be added
only by PI. Completion depends on exit gates, not dates, Issue counts, merged
code, or historical profit.

## Milestone contracts

### M0 — Controlled Research Foundation

Lifecycle: `COMPLETED`.

Goal: establish the auditable control plane required to conduct research
without conflating implementation, evidence, and execution.

Cross-Project outcomes:

- Data Platform: source/data inventory baseline, settlement/freeze foundations,
  and multi-market readiness baseline;
- Prediction & Betting: strategy archaeology, experiment registry, and
  research-evidence boundaries;
- Product & Operations: Research OS bootstrap, GitHub governance, runtime
  status baseline, and review workflow.

Exit gate:

- the Research OS control plane exists;
- Freeze Protocol and the experiment registry exist;
- the three broad Projects and routing taxonomy are accepted;
- baseline operations observability exists.

Exclusion: completion does not claim that data or strategies are effective and
does not authorize execution, selectability, or ROI.

### M1 — Research Data Readiness

Lifecycle: `ACTIVE`.

Question: which historical and forward assets support which kinds of research,
under what provenance, time, and quality boundaries?

Goal: build a versioned, auditable research data foundation while preserving
principled claim boundaries and flexible use of imperfect but informative
history.

Cross-Project outcomes:

- Data Platform: source census, field dictionary,
  coverage/provenance/timestamp grades, strict/proxy/label/settlement
  separation, target-market freeze and settlement capability, and integration
  recommendations;
- Prediction & Betting: per-play `label_ready`, `feature_ready`, `price_ready`,
  chronological-split, coarse-baseline, and ROI-readiness contracts;
- Product & Operations: truthful readiness, coverage, staleness, and blocker
  observability with auditable evidence links.

Exit gate:

1. discoverable sources have inventory entries or deterministic missing
   reasons;
2. relevant fields and markets have admissible-use and integration
   classifications;
3. p34/p40/p42 strict, proxy, and coverage boundaries are reproducible;
4. p51 and other plays have continue, defer, or stop dispositions;
5. strict, historical-proxy, and settlement truth layers cannot be silently
   mixed;
6. the per-play model-readiness matrix is accepted;
7. product surfaces expose readiness and blockers truthfully;
8. execution, selectability, and ROI authority remain disabled.

Exclusion: M1 does not require perfect historical sources or full market
coverage and does not authorize a profitability or release claim.

### M2 — Probability and Model Evidence

Lifecycle: `PLANNED`.

Question: do market information and timestamp-safe football context provide
calibrated, reproducible incremental probability information?

Cross-Project outcomes:

- Data Platform: frozen dataset versions and reproducible chronological panels
  consumed from accepted M1 contracts;
- Prediction & Betting: SP efficiency, multi-market consistency, score
  distributions, rankings/form, and preregistered ablations against suitable
  baselines;
- Product & Operations: read-only experiment/evidence views without strategy
  selectability.

Exit gate:

- every formal experiment cites an accepted dataset version and
  preregistration;
- baselines and incremental variants are evaluated separately;
- primary metrics include Log Loss, Brier, and calibration under chronological
  or forward boundaries;
- multiple-comparison, leakage, and sample-size limitations are explicit.

Exclusion: prediction quality is not assumed to imply betting advantage,
selectability, execution authority, or ROI.

### M3 — Decision and Portfolio Paper Evaluation

Lifecycle: `PLANNED`.

Question: given accepted probability information, do decision-chain and
portfolio layers add separately measurable value under paper-only constraints?

Cross-Project outcomes:

- Data Platform: versioned frozen decisions, portfolio inputs, and settlement
  joins;
- Prediction & Betting: v3.3.3/v4.2 incremental comparisons,
  primary/protection/stop behavior, exact-N, concentration, diversification,
  and budget scenarios;
- Product & Operations: paper-only plan review, human-readable verification,
  download, and settlement replay.

Exit gate:

- probability, decision chain, and portfolio construction remain separate
  experiments;
- fixed baselines and decision rules are preregistered;
- protection depth, failure/survival, concentration, and drawdown are reported.

Exclusion: no paper candidate becomes frontend-selectable, execution-enabled,
or ROI-authorized without a later PI review.

### M4 — Forward Operational Validation

Lifecycle: `PLANNED`.

Question: can frozen candidates and data contracts operate prospectively and
repeatedly under real collection, timing, and settlement conditions?

Cross-Project outcomes:

- Data Platform: collection SLA, immutable prospective snapshots, recovery,
  settlement, and drift monitoring;
- Prediction & Betting: preregistered forward candidates and periodic evidence
  accumulation without retrospective replacement;
- Product & Operations: scheduled research freeze and user adhoc generation
  remain distinct, with monitoring, alerts, manual controls, and truthful
  failure states.

Exit gate:

- repeated prospective events are selected without cherry-picking;
- missed, late, or incomplete events remain fail-closed;
- operational reliability and statistical evidence are reported separately;
- sample thresholds and review checkpoints are preregistered.

Exclusion: planned forward validation is not active dispatch and cannot
automatically promote a candidate to release.

### M5 — Release Readiness and Continuous Research

Lifecycle: `PLANNED`.

Question: has any candidate accumulated enough reproducible, prospective, and
operational evidence for a controlled release review?

Cross-Project outcomes:

- Data Platform: retained/versioned evidence, reproducibility, and long-term
  quality monitoring;
- Prediction & Betting: formal release review, scope limits, failure
  conditions, and periodic revalidation;
- Product & Operations: explicit execution/selectability gates, rollback,
  audit trail, and post-release monitoring.

Exit gate:

- release review is a separate PI-approved contract;
- candidate identity, deterministic/randomization policy, and evidence are
  frozen;
- risk, rollback, monitoring, and deauthorization are defined;
- negative and insufficient-evidence decisions remain acceptable.

Exclusion: historical profit alone never authorizes release, execution,
selectability, or ROI claims.

## Initial mapping

Only these anchors are assigned during initial configuration:

| Issue | Milestone | Rationale |
| --- | --- | --- |
| #14 Research OS bootstrap | M0 | Control-plane foundation anchor |
| #30 Operations observability | M0 | Product/operations foundation anchor |
| #38 Project governance | M0 | Accepted three-Project planning control plane |
| #11 MM-DATA-AUDIT-001 | M1 | Accepted multi-market readiness baseline |
| #17 BJ-MM-FREEZE-001 | M1 | Strict p40/p42 freeze and coverage evidence |
| #37 SCORE-PRICE-HIST-AUDIT-001 | M1 | Historical score-price provenance classification |
| #40 HIST-DATA-CENSUS-001 | M1 | Long-horizon census and admissible-use matrix |
| #31 SP-CONSISTENCY-001A | M2 | Completed probability-space coverage anchor |
| #35 SCORE-HCAP-HIST-001 | M2 | Historical model evidence awaiting reproducibility correction |
| #20 BJ-BET-FREEZE-001 | M3 | Exact-N/portfolio and paper correct-score freeze capability |

M4 and M5 start empty. Closed history is not mass-migrated to make future stages
appear complete.

## Operating procedure

1. PI creates or updates the stage contract and explicitly authorizes a mapping.
2. Engineer confirms the Issue's existing primary Project and routing labels.
3. Engineer assigns at most one Milestone without changing Project or routing
   metadata.
4. Engineer verifies the Milestone description, lifecycle, due date, mapping,
   and Project/routing invariants from GitHub.
5. A fresh independent Codex reviewer validates the exact repository HEAD and
   live configuration.
6. PI performs planning-control acceptance and alone authorizes merge or
   lifecycle change.

New Issues receive `state/ready` only when their dependencies and the active
roadmap permit execution. Milestone assignment alone never dispatches work.

## Verification and safety

Verification must confirm:

- exactly the six governed Milestone titles;
- M0 closed, M1–M5 open, and every due date unset;
- exact Issue membership with M4/M5 empty;
- no Issue assigned to more than one Milestone;
- unchanged Project fields, views, memberships, and non-task routing labels;
- `.research/graph.yaml` absent from the diff;
- no domain code, runtime, schema, strategy, model, API, frontend, deployment,
  or release changes.

Public descriptions and receipts must contain no credentials, tokens, cookies,
local filesystem paths, private service URLs, environment dumps, proprietary
payloads, personal data, betting account details, or sensitive diagnostics.
