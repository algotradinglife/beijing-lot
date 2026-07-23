# Strategy Parallel Session Handoff

Date: 2026-07-12

## Sessions

- Production/integration session: `beijing-lot`
- Strategy research session: `beijing-lot-strategy`
- Strategy branch: `feature/strategy/beijing-lot-model-betting-20260712`
- Strategy worktree: `.worktrees/feature-strategy-beijing-lot-model-betting-20260712`
- Base commit: `d5fb5505d2ef4b9a5fef880de5953f3380de9653`

The strategy branch starts from the committed main baseline. Uncommitted production work in the main worktree is intentionally excluded.

## Ownership Boundary

The production session owns:

- live collection and scheduler reliability;
- decision API and dashboard behavior;
- segment refresh, manual/automatic freeze, operational artifact publication;
- the formal `active_v3.3.3` release and production manifests;
- settlement, monitoring, and promotion integration.

The strategy session owns:

- alternative probability models and calibration experiments;
- primary-pick optimization and league/tag diagnostics;
- protection trimming, rescue/cost attribution, and draw protection;
- ticket construction, concentration, exposure, bankroll, and portfolio experiments;
- leakage-safe historical replay, walk-forward validation, and paper candidates.

The strategy session must not edit or restart the live collector, API, dashboard, or production daemons. It must not change `active_release_id`, overwrite formal artifacts, or write to the shared SQLite databases.

## Shared Data And Output Isolation

The strategy worktree has read-only-by-contract links to the main worktree's `data/` and `.venv`.

- Treat every file under `data/` as immutable input.
- If an experiment needs database writes, first copy the database into the strategy worktree's temporary/output directory.
- Write experiment outputs only under `results/strategy_parallel/<experiment_id>/`.
- Write reports under `docs/strategy/` with a strategy-specific name and date.
- Do not write into current production directories such as `results/segment_betting_plan/`, `results/segment_decision_forward_artifacts/`, or formal structured artifact roots.

## Research Contract

Every candidate must preserve these controls:

1. Use only information available before the declared decision timestamp.
2. Fit calibration, league effects, and thresholds on strictly earlier issues.
3. Keep comparison budgets, segment boundaries, N, seeds, and settlement rules identical.
4. Report primary hit rate, coverage rate, average depth, cost, ROI/profit proxy, maximum drawdown, full-loss rate, and concentration.
5. Report per-issue results and sensitivity; do not promote a result driven by one issue, one season, or one high-SP hit.
6. Keep `v4.2` read-only and keep all new candidates paper/shadow until production review.
7. Record negative results as first-class outcomes.

## Initial Research Backlog

1. Diagnose ticket concentration using final stake-weighted exposure, not unscaled base-bundle counts.
2. Re-optimize Segment-style portfolios for effective independence: match exposure caps, outcome-code exposure caps, HHI/effective-ticket count, and operational bundle count.
3. Continue v3.3.3 primary-pick experiments with strict walk-forward splits and league/tag effects as soft diagnostics.
4. Evaluate protection marginal value by source: probability runner-up, q disagreement, handicap-fit, draw protection, and intelligence protection.
5. Build same-budget Baseline / Primary / Lean-cover / Combined comparisons for eventual Phase 4 review.

## Deliverable Contract

Each experiment handoff must include:

- hypothesis and exact candidate/version ID;
- input paths, issue range, cutoff policy, and leakage checks;
- reproducible command and machine-readable output paths;
- baseline versus candidate tables with the metrics above;
- failure cases, uncertainty, and a clear `reject`, `continue paper`, or `request promotion review` conclusion;
- code and tests limited to the strategy branch.

Use this document as the standing coordination note. The strategy session should append a dated entry to the log below whenever it completes a material experiment or needs production integration.

## Integration Protocol

1. Strategy commits one logically scoped experiment at a time.
2. Strategy updates this handoff log with commit hash and artifact/report paths.
3. Production reviews the commit and imports it selectively; do not merge the whole worktree by default.
4. Production reruns relevant tests and forward checks before exposing a candidate in the dashboard.
5. Only the production session may change formal release manifests or enable execution.

## Handoff Log

- 2026-07-12: worktree and Codex session created; no strategy experiment started yet.
