# HANDOFF — Issue #378 (BJ-UNIFIED-N6-N7-PORTFOLIO-001/v2)

[SESSION] 20260824_224756_4cf93f

## Current HEAD
- Branch: `analyst/bj378-n6-n7-portfolio` (from `origin/main` 4509c9b)
- Worktree: `/home/drwho1985/workspace/soccer/beijing-lot-bj378`
- Rebuild: `python3 scripts/run_n6_n7_portfolio.py --force`
- Verify:  `python3 scripts/verify_n6_n7_portfolio.py` (deterministic byte-replay)
- Tests:  `python3 -m pytest tests/test_n6_n7_portfolio.py -q` (15 passed)

## Completed
- Claimed #378 (In Progress) via claim.py; session above.
- Identified the complete corrected N6 R0-R6 surface from #381
  (`results/n6_corrected_all_r`), plus #377
  (`results/n6_support_transfer_grid`) and #373
  (`results/n7_support_transfer_grid`).
- Full diagnostic package delivered under `results/n6_n7_portfolio/`:
  - shared corrected calendar (152 issues union; exact-common 151; exclusion 23032
    NO_BET zero flow; 20/21 UNTRUSTED_SELECTED_LEG exclusions disclosed)
  - correlation/association/losing-dependence/tail-overlap diagnostics (151 issues)
  - standalone + preregistered 50/50 portfolio + N7-halved dilution counterfactual +
    parallel 1:1 scale diagnostic + mechanical weighted-average identity
  - matched contrasts with circular moving-block bootstrap (block 10, 5000 draws)
  - async-contribution bootstrap (portfolio vs N7_HALVED risk deltas)
  - return-dilution attribution; decision.json; source_receipt.json; MANIFEST.json
- Executed notebook (12/12 cells), report, figure committed under docs/notebooks.

## Key decisions and rationale
1. N6 side of the pool = #381 canonical controls R0/R3 after confirming every
   R0-R6 arm is standalone-negative. #377 retained no grid cell (its
   decision.json verdict is HISTORICAL_MECHANISM_FRONTIER_NO_GATE_PASS,
   expert_admitted_cells=[]), so no N6 support-transfer arm enters the pool.
2. N7 side = #373 corrected R3 CONTROL C0E0 (positive standalone +32,689);
   C1E2/C1E3 exposed only as mechanism hypotheses (per #373 decision.json), never
   portfolio members.
3. Portfolio = preregistered 50/50: sleeve pnl = 0.5 x standalone pnl; NO_BET
   zero flow where an expert is inactive; capital CNY100,000. Mechanical
   weighted average IDENTICAL to the portfolio by construction (verified).
   N7_HALVED (0.5 x N7) is the pure stake-reduction counterfactual that makes
   dilution attribution crisp; PARALLEL_1_1 (both sleeves CNY1,024) is the
   transparent scale diagnostic, not a tuned weight.
4. Metric definitions mirror the frozen upstream protocol exactly
   (_path_metrics, _run_summary, _payout_concentration, circular moving-block
   with block=10/draws=5000, rolling 20/30/50). Golden tests pin N6-R3 and
   N7-C0E0 risk values to #381/#373 risk_diagnostics.csv.
5. Bootstrap seeds: 378_001 (contrasts), 378_002 (async deltas) — the upstream
   convention `{issue}_00K` per stream.
6. Verifier is source-bound: recomputes from upstream bundles/performance.csv,
   checks N6-R3 vs N6-C0E0 cross-package parity (exact), financial invariants
   (CNY1,024 / 512 units), aggregation parity, portfolio/mechanical identity,
   MANIFEST hashes, and byte-exact deterministic replay into a temp dir.
   Replay is the check INDEPENDENT of MANIFEST (attacker who rewrites MANIFEST
   still fails byte-replay against the frozen upstream sources).

## Findings (honest negative result)
- No positive standalone N6 payoff source: R0 -33,511 / R3 -12,300; no retained
  grid cell. So no N6 arm enters the expert pool (contract #6).
- Payoffs are SYNCHRONIZED, not asynchronous: Pearson r=0.754 (pool pair),
  both-losing on 76.2% of 151 shared issues, both-underwater 96.7%, top-10 gross
  sets overlap 5/10, largest payout of BOTH experts on the same issue (23021).
- Portfolio dilutes: 50/50 PnL CNY10,195 = N7_half (16,345) + N6-half (-6,150);
  max DD 32.3% vs N7_HALVED 16.6%; async DD delta bootstrap CI [+0.051,+0.351]
  entirely positive — the N6 sleeve never reduces drawdown vs pure stake
  reduction. Risk-adjusted return/DD ~0.32 vs N7 full ~0.99.
- Verdict: NO_N6_POSITIVE_STANDALONE_PORTFOLIO_DILUTIVE; portfolio NOT
  PROMOTABLE; #210/#218 untouched; no prospective evidence consumed.

## Known issues
- Pyright LSP warnings on optional imports (matplotlib/nbformat/nbclient) and
  bool ndarray attribute inference — environment analysis artifacts, not
  runtime defects; pytest + verify + replay all green.
- results/n6_n7_portfolio/ is force-tracked (repo .gitignore ignores results/*
  by default); upstream packages are tracked the same way.

## Next
- Codex self-check (EV lens): PASS after 3 rounds. Findings fixed: (1) _path_metrics
  public contract trimmed to the frozen 3 keys (internal _path_state extracted);
  (2) verify_package now enforces exact artifact-set equality vs MANIFEST and
  FAILS on missing MANIFEST; (3) replay loop is symmetric (stored vs replay
  file-set equality + byte compare) so coordinated artifact+manifest-entry
  deletion is caught. 17/17 tests pass.
- Commit all; push analyst/bj378-n6-n7-portfolio; open PR with Closes #378;
  post_handoff; finalize_delivery (In Progress -> PI Review per deployed
  tooling; EV is optional post-merge advisory per d0fc7fc).
