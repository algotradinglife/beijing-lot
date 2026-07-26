# GitHub project governance

Capability: `BJ-PROJECT-CONTROL-001`

This document defines the repository planning control plane. It does not change
the scientific roadmap, Research OS authority, Hermes dispatch, milestones, or
any product/runtime behavior.

## Planning layers

| Layer | Sole responsibility |
| --- | --- |
| GitHub Project | Broad, durable functional domain |
| Labels | Fine-grained domain, work type, routing, and dispatch |
| Milestone | Time dimension; intentionally not configured by this capability |
| Issue | Executable contract |
| Pull request | Implementation and review evidence |
| `.research/graph.yaml` | Scientific and evidence dependencies, not daily workflow state |
| `docs/research/roadmap.md` | Narrative research direction |

Every Issue has exactly one primary Project. An Issue may carry several domain
labels inside that Project. Work that crosses Project boundaries is split into
linked Issues with an explicit dependency instead of adding one Issue to
multiple Projects.

## Broad Project boundaries

### BJ Data Platform

Owns collectors and source adapters, historical data assets, match/provider
mapping, immutable snapshots and manifests, data quality and provenance, freeze
input assets, settlement truth, schemas, and dataset maintenance.

The program owner is Engineer. PI retains authority over research eligibility
decisions that depend on these assets.

### BJ Prediction & Betting

Owns market probability and calibration, football models and features, score
distributions, decision chains, primary/protection/stop policies, portfolio and
concentration work, exact-N and budget alternatives, scheduled and adhoc betting
freezes, and strategy-level settlement evaluation.

Strategist owns research execution, Engineer owns engineering implementation,
and PI owns research design and acceptance. Sharing this Project does not merge
scientific questions: probability quality, model incremental value,
decision-chain value, portfolio performance, and execution readiness remain
separate Issues with separate metrics.

### BJ Product & Operations

Owns dashboards and user workflows, review/download/manual-operation surfaces,
collector and runtime status UI, services, scheduling, recovery, deployment,
monitoring, operational reliability, Research OS, and GitHub control-plane
capabilities.

The program owner is Engineer.

No narrower Project named Research Lab, Market Probability, Football Modeling,
Decision Chain, Portfolio, or similar may replace these label-level domains.

## Common Project fields

Each Project's governed planning contract uses only these fields:

| Field | Options |
| --- | --- |
| `Status` | Inbox, Ready, In Progress, Review, Waiting, Done, Cancelled |
| `Owner Role` | PI, Strategist, Engineer |
| `Priority` | P0, P1, P2, P3 |
| `Review Gate` | None, EV, PI, EV+PI |

Phase, Subdomain, Evidence Level, market, model, and execution mode are not
Project fields. They belong in labels, Issue contracts, or immutable experiment
artifacts.

Each Project provides the same saved views:

| View | Filter |
| --- | --- |
| `Current` | `-status:Done -status:Cancelled` |
| `Ready` | `status:Ready label:"state/ready"` |
| `In Progress` | `status:"In Progress"` |
| `Review` | `status:Review` |
| `Waiting` | `status:Waiting` |
| `Completed` | `status:Done,Cancelled` |

GitHub also creates an unfiltered built-in `View 1` when a Project is created.
The public API can create views but cannot rename or delete that platform-owned
default. It is retained as an unmanaged convenience view; the six views above
are the governed contract.

Project Status is the human planning view. It must not add, remove, or infer
Hermes routing labels.

## Label taxonomy

Domain labels are additive within the one primary Project:

- `domain/data-collection`
- `domain/data-provenance`
- `domain/market-probability`
- `domain/football-modeling`
- `domain/decision-chain`
- `domain/portfolio`
- `domain/freeze-execution`
- `domain/product`
- `domain/operations`
- `domain/research-os`

Every mapped Issue has exactly one primary work-type label:

- `type/research`
- `type/audit`
- `type/capability`
- `type/product`
- `type/operations`

Routing labels remain the dispatch interface:

- `owner/strategist`
- `owner/engineer`
- `state/ready`
- existing lifecycle labels including `state/executing`, `state/review`,
  `state/completed`, and `state/cancelled`

Legacy labels are retained. The unprefixed `research`, `capability`,
`research-os`, `infrastructure`, `phase-1`, `research-pi`, and task-specific
labels are compatibility metadata, not aliases that this capability removes or
renames. A later cleanup Issue may propose deprecations only after Hermes and PI
approve the migration.

## Classification workflow

When PI creates an Issue:

1. Read the Issue goal, permitted inputs, deliverables, and acceptance owner.
2. Select the one Project whose boundary owns the primary deliverable.
3. Add all applicable `domain/*` labels.
4. Add exactly one `type/*` label.
5. Preserve PI-provided owner and state routing labels unchanged.
6. Set Project Status from explicit lifecycle evidence; never use Project Status
   to synthesize a routing label.
7. Set Owner Role to the routed execution owner, Priority from the Issue
   contract, and Review Gate from its required EV/PI workflow.
8. If the primary deliverable is genuinely ambiguous, leave the Issue unmapped,
   record the alternatives and rationale in the receipt, and request a PI
   decision rather than assigning multiple Projects.

For cross-project work, create a dependent Issue in the downstream Project and
link the two contracts. The upstream Issue produces its own evidence; the
downstream Issue consumes only the accepted interface or immutable artifact.

Milestones will later provide dates, release windows, or planning periods. This
capability creates, edits, and assigns no Milestones.

## Status verification

Planning configuration is verified from GitHub, not inferred from local files:

1. list the organization Projects and confirm exactly the three governed names;
2. inspect every Project's fields, options, views, filters, and repository link;
3. list Project items and confirm an Issue URL occurs in at most one governed
   Project;
4. list every open repository Issue and compare it with the receipt mapping or
   ambiguity table;
5. verify every mapped Issue has one `type/*` label and its declared
   `domain/*` labels;
6. verify routing labels and all Milestone assignments before and after the
   change;
7. verify `.research/graph.yaml` and all runtime/domain paths are absent from
   the implementation diff.

The committed verification receipt records the exact read-only commands and the
validation timestamp.

## Public planning metadata safety

Project titles, descriptions, fields, views, Issue labels, mapping rationales,
and receipts must contain no credentials, tokens, cookies, local filesystem
paths, environment dumps, private service URLs, proprietary source payloads,
personal data, betting account details, or sensitive operational diagnostics.
Use repository-relative identifiers, GitHub Issue URLs, redacted hashes, and
public capability IDs only.
