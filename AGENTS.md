# Repository Agent Governance

## GitHub Issue Graph Is the Control-Plane Source of Truth

All planning, routing, dependency resolution, dispatch, review, and completion
decisions must be derived from the live GitHub Issue Graph.

The authoritative fields are:

- `blockedBy` / `blocking` for execution dependencies;
- `parent` / `subIssues` for work decomposition;
- `issueType` for the kind of work;
- GitHub Project `Status` for lifecycle state;
- GitHub Project membership for functional ownership. The Project determines
  the responsible role.

Issue bodies and comments may explain intent, methods, evidence, and decisions,
but they are not authoritative for dependency or lifecycle state. Text such as
`Depends on #...`, labels that imitate state, local task files, and chat history
must not be used to reconstruct or override the Issue Graph.

Before planning or dispatching work, read the relevant graph fields with
`gh issue view` or `gh issue list` JSON output. Before declaring work blocked,
ready, reviewable, or complete, read them again. When a relationship changes,
update the native GitHub relationship first and verify both directions
(`blockedBy` and `blocking`) by reading it back.

If GitHub cannot be read or updated, fail closed: report that the control-plane
state is unavailable. Do not manufacture a substitute graph from prose or local
files.

The PI owns issue contracts, graph edges, Project routing, final review, issue
closure, and PR merges. Executors may report evidence and propose graph changes,
but must not silently redefine the graph.

## Local Research OS Files

`.research/graph.yaml` and `.research/tasks/*.yaml` are derived caches or
execution notes only. They may mirror GitHub for local tooling, but they must
never lead, contradict, or replace the live GitHub Issue Graph. Any mismatch is
resolved in favor of GitHub, then the local mirror is refreshed.

## Engineering principles (owner-mandated)

1. **No backward-compat tax.** Delete obsolete code outright. No compat layers,
   no migrations, no fallbacks for old behavior — if it's outdated, remove it.
2. **Simplest implementation that satisfies the current need.** No speculative
   abstraction, no gratuitous config layers.
3. **Layered system — build thin first.** Get a minimal end-to-end version
   running, then add on top. Never rip out working code for unimplemented
   complexity.
4. **Modular components, separation of concerns.** Keep pieces decoupled and
   single-purpose.
5. **Prefer mature, maintained libraries.** No reinventing the wheel without a
   clear reason.
6. **Check existing dependencies first.** Before adding a package or writing
   your own, see what the project already has and what it can do. Don't assume
   the library is missing.
7. **Architecture decisions are made long-term.** No "ship it now, fix later"
   stopgaps — an accepted design is expected to persist.
8. **Learn from mature products.** See how established products solve the same
   problem and use proven patterns; don't invent from scratch.

## Cutoff-driven historical learning (owner-mandated)

Every decision-facing operation that learns, calibrates, tunes, selects, ranks,
gates, or optimizes from historical data must be behind a function that accepts
an explicit cutoff object. This includes learned preprocessing, thresholds,
support depth, hyperparameters, seeds, expert admission, routing, allocation,
bankroll gates, league/team effects, regimes, embeddings, priors, shrinkage,
imputation, normalization, and historically derived availability gates.

The function must filter on actual data and label availability strictly before
the cutoff, derive every internal fit/tune/calibration partition inside that
prior window, fail closed on missing chronology or insufficient history, and
return the learned artifact together with a machine-readable receipt. The
receipt must bind cutoff identity/time, maximum source and label-availability
time, partitions, selected parameters, metrics, gate predicates, source hashes,
transitive implementation hashes, model identity, and a cutoff-bound cache key.
Independent replay is mandatory. A cache from another cutoff, source, or
implementation may never be reused.

Hidden temporal globals such as `FIT_END`, `TUNE_YEAR`, and
`CALIBRATION_YEAR`, or a detached persisted acceptance boolean, must not control
a new target period. Historical packages that predate this rule may remain only
as explicitly inventoried historical evidence; they are not clean reusable
interfaces. Business constants such as fixed N, CNY1,024, CNY2 units, and one
ticket-level 0.65 payout factor are explicit contract inputs rather than learned
parameters.

Every research contract and PI/adversarial review must inventory the transitive
historical-learning functions and answer: cutoff received, maximum admitted
source/label time, partition derivation, cross-cutoff cache exclusion,
post-cutoff mutation invariance through selection/support/tickets/routing, and
receipt binding of imported helpers. A label-free final artifact is not by
itself evidence of causality.

The primary adaptive mode is issue-level walk-forward. For a target issue, the
cutoff is its fixture-relative decision epoch; prior-year history and only those
current-year issues whose labels were actually available strictly before that
epoch may be admitted. The target issue, future issues, and unsettled labels are
excluded by both timestamp and exact target-issue identity. Timestamp filtering
alone is insufficient even when a bad source claims the target settled early.
Each target issue gets an immutable cutoff-keyed artifact before its
settlement is opened; later labels must never rewrite it.

Every availability claim must name its evidence class. Observed availability
and a documented conservative safe boundary may authorize prospective use;
historical timestamp proxies may support diagnostics only and must never be
promoted into a prospective availability claim.

Recency weighting is itself historical learning. Equal expansion, explicit
time/issue decay, bounded recent-state blends, change detectors, refit cadence,
half-life, window, blend, threshold, and effective-sample-size floors must be
passed explicitly and selected only inside a prior cutoff window. Receipts must
bind the full weight ledger, effective sample size, long-history shrinkage, and
policy parameters. Sparse recent evidence must fail closed or shrink to the
frozen long-history prior. A later issue model/cache may never serve an earlier
issue.

A recent-state blend is a convex mixture of two normalized distributions:
`(1-alpha) * long_history + alpha * recent_state`. The receipt must reconcile
both component masses separately; multiplying only recent rows inside one
global normalization is not an accepted blend implementation.

All of this chronology machinery must come from the shared
`src/temporal_learning` library. Research modules are clients: they supply only
domain-specific fit/predict/select callbacks and must not copy cutoff,
availability, partition, weighting, ESS, cache, receipt, runner, or replay
utilities. New direct historical fitting outside a shared learning context and
duplicated temporal helpers fail repository governance checks. Migrations delete
or replace obsolete implementations; they do not add compatibility wrappers.
Static enforcement scans both `src/` and `scripts/` and permits legacy debt only
by exact AST occurrence fingerprint and count, never by exempting a whole file.
