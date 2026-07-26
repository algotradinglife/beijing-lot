# GitHub milestone governance verification receipt

Capability: `BJ-MILESTONE-CONTROL-001`

Implementation verification timestamp: `2026-07-26T08:24:19Z`.

This is a redacted planning-control receipt. It records public repository
metadata only and contains no credentials, local paths, environment dumps,
private URLs, source payloads, personal data, account data, or operational
diagnostics.

## Milestone inventory

Exactly six repository Milestones exist:

| No. | Stable title | GitHub state | Lifecycle | Due date | URL |
| ---: | --- | --- | --- | --- | --- |
| 1 | M0 — Controlled Research Foundation | closed | COMPLETED | none | https://github.com/algotradinglife/beijing-lot/milestone/1 |
| 2 | M1 — Research Data Readiness | open | ACTIVE | none | https://github.com/algotradinglife/beijing-lot/milestone/2 |
| 3 | M2 — Probability and Model Evidence | open | PLANNED | none | https://github.com/algotradinglife/beijing-lot/milestone/3 |
| 4 | M3 — Decision and Portfolio Paper Evaluation | open | PLANNED | none | https://github.com/algotradinglife/beijing-lot/milestone/4 |
| 5 | M4 — Forward Operational Validation | open | PLANNED | none | https://github.com/algotradinglife/beijing-lot/milestone/5 |
| 6 | M5 — Release Readiness and Continuous Research | open | PLANNED | none | https://github.com/algotradinglife/beijing-lot/milestone/6 |

## Live descriptions

### Milestone 1 — M0

- Lifecycle: `COMPLETED`; closed after initial mapping verification.
- Goal: establish the auditable control plane required to conduct research
  without conflating implementation, evidence, and execution.
- Cross-Project outcomes: data/freeze foundations; strategy archaeology and
  experiment boundaries; Research OS, GitHub governance, runtime status, and
  review workflow.
- Exit gate: Research OS, Freeze Protocol, experiment registry, three broad
  Projects, routing taxonomy, and baseline operations observability exist.
- Exclusion: completion does not claim effective data or strategies and does
  not authorize execution, selectability, ROI, or replacement of Research OS
  evidence state.

### Milestone 2 — M1

- Lifecycle: `ACTIVE`; no due date.
- Question: which historical and forward assets support which research under
  which provenance, time, and quality boundaries?
- Goal: build a versioned, auditable data foundation with principled claim
  boundaries and usable imperfect history.
- Cross-Project outcomes: source/field/coverage/admissibility contracts;
  per-play label, feature, price, split, baseline, and ROI-readiness contracts;
  truthful readiness, coverage, staleness, blocker, and evidence-link views.
- Exit gate: inventories or deterministic missing reasons; admissible-use
  classifications; reproducible p34/p40/p42 boundaries; dispositions for p51
  and other plays; non-mixing of strict/proxy/settlement layers; accepted
  model-readiness matrix; truthful product surfaces; no execution authority.
- Exclusion: does not require perfect history or full coverage and does not
  authorize profitability or release claims.

### Milestone 3 — M2

- Lifecycle: `PLANNED`; no due date.
- Question: do market information and timestamp-safe context add calibrated,
  reproducible incremental probability information?
- Goal and outcomes: consume accepted M1 frozen panels; evaluate SP efficiency,
  multi-market consistency, score distributions, context, and preregistered
  ablations; expose read-only evidence views.
- Exit gate: accepted dataset/preregistration identity, separated baselines and
  increments, Log Loss/Brier/calibration, chronological boundaries, and explicit
  multiple-comparison/leakage/sample limitations.
- Exclusion: prediction quality does not imply betting advantage, execution,
  selectability, or ROI.

### Milestone 4 — M3

- Lifecycle: `PLANNED`; no due date.
- Question: do decision-chain and portfolio layers add separately measurable
  value under paper-only constraints?
- Goal and outcomes: versioned frozen decisions and settlement joins;
  v3.3.3/v4.2, primary/protection/stop, exact-N, concentration,
  diversification, and budget evaluations; paper-only review/download/replay.
- Exit gate: probability, decision, and portfolio remain separate; fixed
  baselines/rules are preregistered; protection, failure/survival,
  concentration, and drawdown are reported.
- Exclusion: no paper candidate is execution-enabled, frontend-selectable, or
  ROI-authorized without later PI review.

### Milestone 5 — M4

- Lifecycle: `PLANNED`; no due date.
- Question: can frozen candidates operate prospectively and repeatedly under
  real collection, timing, and settlement conditions?
- Goal and outcomes: collection SLA, immutable snapshots, recovery, settlement,
  drift monitoring, preregistered forward evidence, and distinct scheduled
  research versus adhoc product flows.
- Exit gate: no cherry-picking; missed/late/incomplete events fail closed;
  reliability and statistics stay separate; thresholds and reviews are
  preregistered.
- Exclusion: no active dispatch or automatic release promotion.

### Milestone 6 — M5

- Lifecycle: `PLANNED`; no due date.
- Question: has a candidate accumulated enough reproducible, prospective, and
  operational evidence for a controlled release review?
- Goal and outcomes: retained evidence and quality monitoring; formal release
  scope/failure/revalidation; explicit gates, rollback, audit, and monitoring.
- Exit gate: a separate PI contract; frozen identity/policy/evidence; defined
  risk, rollback, monitoring, and deauthorization; negative decisions allowed.
- Exclusion: historical profit alone never authorizes release, execution,
  selectability, or ROI.

The full live description bodies are reproducible with the Milestone commands
below. Each contains its lifecycle, goal, cross-Project outcomes, exit gate, and
exclusions.

## Exact Issue mapping

| Issue | State at verification | Milestone | Existing primary Project |
| ---: | --- | --- | --- |
| #14 | closed | M0 | none; preserved completed-history state |
| #30 | closed | M0 | BJ Product & Operations |
| #38 | closed | M0 | BJ Product & Operations |
| #11 | closed | M1 | BJ Data Platform |
| #17 | closed | M1 | BJ Data Platform |
| #37 | closed | M1 | BJ Data Platform |
| #40 | open | M1 | BJ Data Platform |
| #31 | closed | M2 | BJ Prediction & Betting |
| #35 | open | M2 | BJ Prediction & Betting |
| #20 | open | M3 | BJ Prediction & Betting |

M4 and M5 contain no Issues. No other closed Issue was migrated.

## Unmapped open Issues

| Issue | PI disposition |
| ---: | --- |
| #44 `BJ-MILESTONE-CONTROL-001` | Configuration capability; intentionally absent from the declared initial Milestone table. It remains unmapped unless PI explicitly assigns it. |

All other open Issues at the timestamp (#20, #35, and #40) have the declared
mapping above.

## Before/after invariants

- The three organization Projects, their field definitions, saved views, and
  existing item membership were unchanged. The only Project addition was the
  current #44 capability to its declared primary Project, BJ Product &
  Operations.
- The ten mapped Issues retained their existing Project membership. The
  completed historical #14 anchor had no Project item before this task and
  remains unchanged; it was not mass-migrated.
- Routing labels for the ten mapped Issues were unchanged. #44 alone moved from
  `state/ready` to `state/executing` when PI dispatched this task.
- The pre-existing closed #37 routing/Project lifecycle mismatch was observed
  and deliberately left unchanged because this task authorizes Milestone
  mapping, not unrelated lifecycle repair.
- `.research/graph.yaml` SHA-256 before documentation changes:
  `859c4eabb7d933086ef99ff27b78737c6d175bf020b6940aa1c5ecbd0a7da5c9`.
  It remains the scientific/evidence dependency graph and is not modified.
- No Project field/view, domain code, data, collector, model, strategy,
  portfolio, ticket, runtime, schema, API, frontend, deployment, or release
  artifact is modified.

## Verification commands

```bash
gh api 'repos/algotradinglife/beijing-lot/milestones?state=all&per_page=100'
gh api repos/algotradinglife/beijing-lot/milestones/MILESTONE_NUMBER
gh api 'repos/algotradinglife/beijing-lot/issues?milestone=MILESTONE_NUMBER&state=all&per_page=100'
gh issue view ISSUE --repo algotradinglife/beijing-lot \
  --json number,state,title,milestone,labels,projectItems
gh issue list --repo algotradinglife/beijing-lot --state open --limit 100 \
  --json number,title,milestone,labels,projectItems
gh project list --owner algotradinglife --format json
gh project field-list PROJECT_NUMBER --owner algotradinglife --format json
gh project item-list PROJECT_NUMBER --owner algotradinglife \
  --format json --limit 100
sha256sum .research/graph.yaml
git diff --check
git diff --name-status BASE...HEAD
```

Verification criteria:

1. the Milestone list contains exactly numbers 1–6 and the six stable titles;
2. Milestone 1 is closed, 2–6 are open, and every `due_on` is `null`;
3. membership is exactly `M0={14,30,38}`, `M1={11,17,37,40}`,
   `M2={31,35}`, `M3={20}`, `M4={}`, `M5={}`;
4. every other open Issue is listed above with PI disposition;
5. Project/routing invariants and `.research/graph.yaml` remain unchanged;
6. repository diff is documentation-only and passes redaction inspection.

## Redaction result

PASS. The receipt contains repository-relative documentation paths, public
GitHub URLs, public Issue numbers, public capability identifiers, and the
Research OS graph digest only. It contains no token, credential, cookie, local
absolute path, environment dump, private URL, proprietary payload, personal
data, betting account detail, or sensitive runtime diagnostic.
