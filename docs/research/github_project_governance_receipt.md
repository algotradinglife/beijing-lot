# BJ-PROJECT-CONTROL-001 verification receipt

Validation timestamp: `2026-07-26T05:47:09Z`

This receipt contains only GitHub planning metadata. It contains no token,
credential, local path, environment dump, private service URL, or sensitive
operational payload.

## Governed Projects

| Project | Node ID | GitHub URL | Repository link |
| --- | --- | --- | --- |
| BJ Data Platform | `PVT_kwDOCnDY5c4Bed77` | https://github.com/orgs/algotradinglife/projects/1 | `algotradinglife/beijing-lot` |
| BJ Prediction & Betting | `PVT_kwDOCnDY5c4Bed79` | https://github.com/orgs/algotradinglife/projects/2 | `algotradinglife/beijing-lot` |
| BJ Product & Operations | `PVT_kwDOCnDY5c4Bed7_` | https://github.com/orgs/algotradinglife/projects/3 | `algotradinglife/beijing-lot` |

Exactly these three governed Projects are linked to the repository. No narrower
Research Lab, Market Probability, Football Modeling, Decision Chain, or
Portfolio Project was created.

## Fields and views

All three Projects have the same minimal governed field contract:

| Field | Options |
| --- | --- |
| Status | Inbox, Ready, In Progress, Review, Waiting, Done, Cancelled |
| Owner Role | PI, Strategist, Engineer |
| Priority | P0, P1, P2, P3 |
| Review Gate | None, EV, PI, EV+PI |

GitHub's built-in `Title`, `Assignees`, `Labels`, `Linked pull requests`,
`Milestone`, `Repository`, `Reviewers`, `Parent issue`,
`Sub-issues progress`, `Created`, `Updated`, and `Closed` fields remain
available. No Phase, Subdomain, Evidence Level, market, model, or
execution-mode custom field was created.

| View | Layout | Filter |
| --- | --- | --- |
| Current | table | `-status:Done -status:Cancelled` |
| Ready | table | `status:Ready label:"state/ready"` |
| In Progress | table | `status:"In Progress"` |
| Review | table | `status:Review` |
| Waiting | table | `status:Waiting` |
| Completed | table | `status:Done,Cancelled` |

Each Project also retains GitHub's built-in unfiltered `View 1`. GitHub's
2026-03-10 public Project-view API creates views but does not expose rename or
delete operations for that platform default. `View 1` is not part of the
governed view contract; the six named rows above are.

## Labels

Created by this capability:

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
- `type/research`
- `type/audit`
- `type/capability`
- `type/product`
- `type/operations`

Reused without renaming or deleting:

- `owner/strategist`
- `owner/engineer`
- `state/ready`
- `state/executing`
- `state/review`
- `state/completed`
- `state/cancelled`
- all legacy unprefixed and task-specific labels

No routing label description, color, or name was changed.

## Open-Issue inventory

| Issue | Primary Project | Project Status | Owner Role | Priority | Review Gate | Fine labels | Deterministic rationale |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #17 `BJ-MM-FREEZE-001` | BJ Data Platform | Done | Engineer | P0 | EV+PI | `domain/data-collection`, `domain/data-provenance`, `domain/freeze-execution`, `type/capability` | Its primary deliverable is a strict collector/input-freeze and provenance capability; cross-domain freeze use remains a label. |
| #20 `BJ-BET-FREEZE-001` | BJ Prediction & Betting | Done | Engineer | P0 | EV+PI | `domain/portfolio`, `domain/freeze-execution`, `type/capability` | Its primary deliverable is exact-N and budget betting alternatives plus their immutable freeze. |
| #35 `SCORE-HCAP-HIST-001` | BJ Prediction & Betting | Ready | Strategist | P1 | EV+PI | `domain/football-modeling`, `type/research` | Its executable contract is a historical score-distribution model comparison. |
| #37 `SCORE-PRICE-HIST-AUDIT-001` | BJ Data Platform | Ready | Strategist | P1 | EV+PI | `domain/data-provenance`, `type/audit` | Its primary deliverable is existence, lineage, timestamp, and eligibility classification for a historical data asset. |
| #38 `BJ-PROJECT-CONTROL-001` | BJ Product & Operations | Review | Engineer | P1 | EV+PI | `domain/operations`, `domain/research-os`, `type/capability` | Its primary deliverable is the GitHub/Research OS planning control plane. |
| #40 `HIST-DATA-CENSUS-001` | BJ Data Platform | Waiting | Strategist | P1 | EV+PI | `domain/data-provenance`, `type/audit` | Its contract explicitly assigns the Data Platform and blocks dispatch on #37 acceptance, so it remains a non-ready waiting item. |

Every open Issue is mapped exactly once. There are no unmapped or ambiguous
open Issues at this validation timestamp.

## Completed foundation anchors

Only one key completed anchor was seeded per Project:

| Issue | Primary Project | Status | Fine labels | Rationale |
| --- | --- | --- | --- | --- |
| #11 `MM-DATA-AUDIT-001` | BJ Data Platform | Done | `domain/data-provenance`, `type/audit` | Establishes the accepted multi-market data-readiness baseline. |
| #31 `SP-CONSISTENCY-001A` | BJ Prediction & Betting | Done | `domain/market-probability`, `domain/football-modeling`, `type/research` | Establishes the accepted probability-space consistency gate and boundary. |
| #30 `BJ-OPS-OBS-001` | BJ Product & Operations | Done | `domain/product`, `domain/operations`, `type/capability` | Establishes the existing operations status surface and control-plane boundary. |

Closed historical Issues were not mass-migrated.

## Milestone, routing, and Research OS invariants

- The six open Issues and three completed anchors have no Milestone changes.
- `owner/*` and `state/*` labels remain the Hermes dispatch source of truth.
- Project Status is a human planning field and does not mutate routing labels.
- `.research/graph.yaml`, `.research/tasks/`, and
  `docs/research/roadmap.md` were not modified by this capability.
- No strategy, model, backtest, data, collector, ticket, API, frontend, runtime,
  deployment, or release file was modified.

## Exact verification commands

Run with an authenticated GitHub CLI token that has organization Projects read
permission:

```bash
gh project list --owner algotradinglife --format json

gh project field-list PROJECT_NUMBER \
  --owner algotradinglife --format json

gh api graphql \
  -f query='query($org:String!,$number:Int!){organization(login:$org){projectV2(number:$number){repositories(first:10){nodes{nameWithOwner}} views(first:20){nodes{number name filter layout}}}}}' \
  -F org=algotradinglife -F number=PROJECT_NUMBER

gh project item-list PROJECT_NUMBER \
  --owner algotradinglife --format json

gh label list --repo algotradinglife/beijing-lot \
  --limit 200 --json name,color,description

gh issue list --repo algotradinglife/beijing-lot \
  --state open --limit 200 \
  --json number,title,labels,milestone,projectItems,url

git diff --name-only 0783a59090598f551de6af9a6db139fece53bdb5...HEAD

git diff --exit-code \
  0783a59090598f551de6af9a6db139fece53bdb5...HEAD \
  -- .research/graph.yaml .research/tasks docs/research/roadmap.md \
     apps config ops schemas scripts src tests
```

For each governed Project, substitute its numeric `PROJECT_NUMBER`. Verification
passes only when Project names/links, exact custom fields/options, six
views/filters, item uniqueness, label taxonomy, open-Issue coverage, Milestone
invariance, routing invariance, and the documentation-only diff all agree.
