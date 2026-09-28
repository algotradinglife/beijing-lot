# #493 deliverable 2 — REUSE / PENDING / UNUSABLE matrix for prior N7 research

Issue: [#493](https://github.com/algotradinglife/beijing-lot/issues/493) (parent [#492](https://github.com/algotradinglife/beijing-lot/issues/492)).
Scope of this document: verify what #424 / #425 / #427 / #439 / #451 / #453 / #455 / #459 and the existing Dixon-Coles (DC) chain actually delivered and tested, and classify each component for #493's needs.

Audit performed: 2026-09-22 (UTC), read-only on the repository and on GitHub. No issue, PR, label or Project field was created or changed. No branch was checked out, stashed, reset or worktree-added; branch content was read with `git ls-tree` / `git show` / `git archive` into a temporary directory outside the repository.

## 1. Verdict in one paragraph

Every N7 research artifact from the eight issues lives **only on unmerged, stacked `codex/*` branches**. `main` contains none of the QMDs `quarto/134..159`, none of the `r/n7_sleeve_*` / `r/n7_capital_*` / `r/n7_prefix_*` / `r/n7_quality_*` / `r/n7_group_exchange_*` / `r/n7_expanded_*` / `r/n7_joint_*` modules and none of their Python modules. Where I could run the tests on the branch tree they **passed** (see §4–§11), which makes the *code* REUSE-grade; but as a deliverable available to #493 on `main` every one of them is **PENDING**. No component was found to silently consume post-cutoff information, so no component is UNUSABLE on look-ahead grounds. The single UNUSABLE row in the matrix is a **semantic** mismatch, not contamination: #459's `minimum_sp: 1.3` eligibility gate (the same gate used by #451/#453/#455) must not become #493's base candidate filter, because #493's confirmed contract forbids SP/difficulty preference as a base eligibility rule. The DC chain has the same shape plus a sharper problem: on `main` the three authoritative R modules named by #493 (`r/dixon_coles_grid.R`, `r/n7_market_projection.R`, `r/fundamentals_total_market.R`) exist **only as untracked working-tree files**, four of the R files their tests `source()` are missing entirely, and the DC tests therefore error on `main` while passing on branch `codex/258-dixon-coles-score-grid`.

Consequence for #493: the reuse decision is not "is the old research any good" — it is mostly **integration and re-binding work**, plus four genuinely new pieces (#493's own contract): the 20:00 Asia/Shanghai decision epoch with the 24 h bettable window, the (match, outcome) mask with legal-TopK-without-renormalisation, cross-day period-budget balance, and the SP>10 → 4.5 pre-decision estimate rule.

## 2. Classification rule used here

| Class | Meaning in this matrix |
|---|---|
| REUSE | Artifact exists, its tests were observed passing in this audit, it is component-ready for #493 and #493 can reach it (committed on `main`). |
| PENDING | Artifact exists (possibly tested) but is not reachable/complete for #493 — unmerged branch, untracked file, missing integration, or genuinely not built — or it does not exist yet. |
| UNUSABLE | Artifact exists but must not be used for a decision-facing #493 contract (look-ahead/chronology contamination, wrong semantics, or failing tests that indicate a defect rather than an environment gap). |

"Review status" is deliberately **not** treated as acceptance. A component can be tested-and-green and still be PENDING for #493.

## 3. Native Issue Graph and lifecycle state (read via `gh api graphql`, read-only)

| Issue | State | Project Status | issueType | parent | subIssues | blockedBy | blocking |
|---|---|---|---|---|---|---|---|
| #424 | CLOSED | Done | Task | #202 | — | — | — |
| #425 | OPEN | Review | — | — | — | — | — |
| #427 | OPEN | (none) | — | — | — | — | — |
| #439 | OPEN | Review | — | — | — | — | — |
| #451 | OPEN | Review | Task | — | — | — | — |
| #453 | OPEN | Review | Task | — | — | — | — |
| #455 | OPEN | Review | Task | — | — | — | — |
| #459 | OPEN | Review | Task | — | — | — | — |
| #492 | OPEN | Inbox | Feature | #202 | #493–#498 | — | — |
| #493 | OPEN | Ready | Task | #492 | — | — | #494 |

**Not accepted:** #425, #439, #451, #453, #455, #459 are OPEN and in Project `Review`; #427 is OPEN with no Project status at all. Only #424 is CLOSED/Done, and its own acceptance is explicitly limited to *retrospective research* (see §4). #492 itself states these are unverified historical evidence. None of these states is acceptance for #493.

## 4. #424 — N7 64-ticket sleeve coverage × return frontier and 8-sleeve portfolio (BJ-N7-SLEEVE-PORTFOLIO-001)

**Contract / acceptance.** CLOSED 2026-09-12, Project Done, parent #202, no blockedBy/blocking/subIssues. PI accepted it as **retrospective research**, verdict `COVERAGE_STRUCTURE_SIGNAL`, with accepted limitations written into the issue: exposed 2010-only data, finite 24-group candidate pool, unproven historical availability (`historical_admission=false`), synthetic 5-round risk stress, settled-before-next-issue accounting. No demonstrated capital superiority, no prospective admission. `docs/research/` decision report + roadmap are part of the delivery.

**Delivered artifacts (all on branches only).**

- Branches: `origin/codex/424-research-base` (staged integration base), `origin/codex/424-pi-review` @700d3fb9 (reviewed candidate), `origin/codex/424-joint-research` @c543069c (accepted joint research).
- PRs: #426 (merged into `codex/424-research-base`, 2026-09-12T13:31:27Z) and #428 (merged into `codex/424-research-base`, 2026-09-12T15:47:59Z). Both merge into the research branch, **not** `main`.
- QMD: `quarto/134_n7_sleeve_portfolio.qmd` … `quarto/139_n7_joint_sleeves.qmd`.
- R: `r/n7_sleeve_summary.R`, `r/n7_sleeve_tables.R`, `r/n7_sleeve_cap_report.R`, `r/n7_sleeve_expansion_report.R`, `r/n7_joint_sleeves.R`, `r/n7_joint_report.R`, `r/fundamentals_n7_reuse.R`.
- Python: `src/n7_sleeve_states.py`, `src/n7_sleeve_candidates.py`, `src/n7_sleeve_portfolio.py`, `src/n7_sleeve_probability_cap.py`, `src/n7_sleeve_cap_check.py`, `src/n7_sleeve_expansion.py`, `src/n7_sleeve_expansion_check.py`, `src/n7_joint_study.py`, `src/n7_joint_check.py`.
- Acceptance evidence: `docs/research/n7_joint_acceptance.md`, `n7_joint_acceptance_receipt.json`, `n7_joint_checks.json`, `n7_joint_codex_review.md`, `n7_joint_transitive_functions.csv` (branch only).

**Tests observed in this audit** (branch tree extracted to a temp dir; `R_LIBS_USER=<repo>/r_lib`, `FUNDAMENTALS_PYTHON=<repo>/.venv/bin/python`, `PYTHONPATH=<temp tree>`):

- `.venv/bin/python -m pytest tests/test_n7_sleeve_states.py tests/test_n7_sleeve_portfolio.py tests/test_n7_sleeve_runner.py tests/test_n7_sleeve_checker.py tests/test_n7_sleeve_expansion.py tests/test_n7_sleeve_expansion_runner.py tests/test_n7_sleeve_probability_cap.py tests/test_n7_sleeve_cap_runner.py tests/test_n7_joint_study.py tests/test_n7_joint_check.py -q` → **40 passed** (27.99 s).
- `test-n7-joint-report.R` 25 pass; `test-n7-sleeve-cap-report.R` 15 pass; `test-n7-sleeve-expansion-report.R` 10 pass; `test-n7-sleeve-summary.R` 16 pass; `test-n7-sleeve-tables.R` 31 pass.
- `test-n7-joint-sleeves.R`: **54 pass** with `FUNDAMENTALS_PYTHON` + `PYTHONPATH` set. Without them the same file gives 1 failure + 3 errors, all from `n7_joint_validate` rejecting an empty Python path / `reticulate::import("src.temporal_learning")` failing — an environment gap, not a code defect.

**Committed on `main`?** No. `git ls-tree -r HEAD -- quarto/ | grep -E '^quarto/13[4-9]_'` returns nothing; the branch is 94 commits ahead of and 88 behind `main`.

**Chronology / look-ahead.** The accepted contract keeps target settlement out of selection and uses shared issue-level outcome worlds rather than an independence product; `src/n7_union_inputs.py` (from #439, same lineage) refuses cross-snapshot source binding, and the #424 evidence records `historical_admission=false`. I found no silent post-cutoff input in the selection modules I inspected. Evidence grade is nonetheless **diagnostic-only**: the issue itself admits the exposure and the unproven availability.

**Classification for #493: PENDING.** Reason: component code is REUSE-grade and tested, but it is on an unmerged research branch; #424's own acceptance says main integration is a separate, unreviewed concern, and its evidence is retrospective-diagnostic only.

**What #493 still must build on top of it:** (match, outcome) hard/soft mask; legal TopK over the original combination probability **without renormalisation**; the 20:00 Asia/Shanghai decision epoch and 24 h bettable window; cross-day period-budget balance (balance = 1024 − period spend, not reset daily); the SP>10 → 4.5 pre-decision estimate rule; and binding the DC probability base into the sleeve surface instead of the #424 frozen bundle.

## 5. #425 — N7 capital scaling: sleeve breadth × state depth frontier (BJ-N7-CAPITAL-SCALING-001)

**Contract / acceptance.** OPEN, Project `Review`, no parent, no graph edges. Comment reports PI research verdict **NO_STABLE_FRONTIER** and delivery via PR #432; the issue explicitly stays open, no `main` merge. The comment also notes that three earlier storage commits on the branch were not covered by the research Codex review and require separate integration review.

**Delivered artifacts (branch only).**

- Branch: `origin/codex/425-capital-frontier` @977aeabb; PR #432, base `codex/424-research-base`, **OPEN**.
- QMD: `quarto/140_n7_capital_frontier.qmd` (plus `141_n7_candidate_hit_rank.qmd`, `142_n7_missed_candidates.qmd`).
- R: `r/n7_capital_depth.R`, `r/n7_capital_portfolio.R`, `r/n7_capital_compare.R`, `r/n7_capital_issue.R`, `r/n7_capital_report.R`, `r/n7_rank_diagnostic.R`, `r/n7_missed_candidates.R`.
- Python: `src/n7_capital_study.py`, `src/n7_capital_check.py`, `src/n7_capital_archive.py`, `src/n7_rank_diagnostic.py`.
- Evidence: `docs/research/n7_capital_acceptance.md`, `docs/research/n7_capital_contract.md` (branch only).

**Tests observed:** `.venv/bin/python -m pytest tests/test_n7_capital_archive.py tests/test_n7_capital_check.py tests/test_n7_capital_study.py -q` → **15 passed**; `tests/test_n7_rank_diagnostic.py tests/test_n7_single_ticket_sampling.py` → **9 passed**. R: `test-n7-capital-compare.R` 30, `test-n7-capital-depth.R` 24, `test-n7-capital-issue.R` 40, `test-n7-capital-portfolio.R` 42, `test-n7-capital-report.R` 38 — all pass.

**Committed on `main`?** No (113 ahead / 88 behind).

**Chronology.** Cutoffs are delegated to `src/temporal_learning` (`r/n7_joint_sleeves.R` imports `src.temporal_learning` for `Cutoff$decision_epoch`); the reported study is explicitly "100 exposed historical issues, not unseen validation". Diagnostic-only evidence, no contamination found.

**Classification for #493: PENDING.** Reason: branch-only, PR open, and the budget-preference frontier is a research answer table rather than a #493 decision component.

**What #493 still must build:** nothing new from #425 beyond integration — #493 only needs the depth/curve interface to express 4×128 / 8×64 / 4×96+4×32 structural controls at a fixed 1024 CNY ceiling, with cash retained and actual spend reported separately.

## 6. #427 — adaptive N7 capital router (BJ-N7-ADAPTIVE-ROUTER-001)

**Contract / acceptance.** OPEN, no Project status, no parent, no blockedBy/blocking/subIssues, **zero comments**.

**Delivered artifacts: none.** No branch matches `codex/427*`; no remote branch name, file name or commit message matches `router` / `realloc` / `adaptive` in the N7 lineage; `gh pr list --search 427` returns no PR that references this issue. The interfaces the contract asks for (`evaluate_reallocation`, `propose_reallocations`, extended `allocate_sleeve_budget`) do not exist anywhere in the repository or on any branch.

**Committed on `main`?** N/A — nothing exists.

**Classification for #493: PENDING.** Reason: not delivered at all; the issue is open and unstarted. It is also the one prior issue that #493 does **not** need for its own minimal replay (dynamic deepen/expand/transfer belongs to later stages, #496/#497).

**What #493 still must build:** nothing for the minimal replay. If later stages need reallocation, the whole component must be built; do not cite #427 as delivered.

## 7. #439 — joint coverage, adaptive depth and matched-budget sweet-region tests

**Contract / acceptance.** OPEN, Project `Review`, no graph edges. Comment: PR #440, commit `c40d7b9f`, "issue is verified in Review; no closure or merge performed"; evidence paths are quoted as `audits/issue439-union-v3/...` and `reports/issue439-union-v3/149_n7_sweet_joint_coverage.html` on the declared persistent root.

**Delivered artifacts (branch only).**

- Branch `origin/codex/439-joint-coverage` @c40d7b9f; PR #440, base `codex/437-sweet-region`, **OPEN**. Delta vs base: `quarto/149_n7_sweet_joint_coverage.qmd`, `r/n7_sweet_union.R`, `r/n7_sweet_union_summary.R`, `src/n7_union_inputs.py`, `docs/research/n7_sweet_union_439.md`, tests `tests/test_n7_union_inputs.py`, `tests/test_n7_union_empty_runner.py`, `tests/test_n7_sweet_union_replay.py`, `tests/testthat/test-n7-sweet-union.R`, `test-n7-sweet-union-summary.R`.
- `src/n7_union_inputs.py` is the freeze/binding component: it binds catalog bytes, rank receipt, source cutoffs and `src.temporal_learning` implementation closure, and refuses cross-snapshot or ambiguous source identity.

**Tests observed:** `tests/test_n7_union_inputs.py` + `tests/test_n7_union_empty_runner.py` → **4 failed / 5 passed** as invoked, all four failures being `KeyError: 'RSCRIPT'` at `tests/test_n7_union_empty_runner.py:48` (the test shells out with `os.environ['RSCRIPT']`); with `RSCRIPT=/usr/local/bin/Rscript` the same command gives **9 passed** (37.96 s). `tests/test_n7_sweet_union_replay.py` → **8 passed**. R: `test-n7-sweet-union.R` 12, `test-n7-sweet-union-summary.R` 12 (plus inherited `test-n7-sweet-region.R` 13, `test-n7-sweet-diagnostics.R` 11) — all pass.

**Evidence on the persistent root:** the HTML `reports/issue439-union-v3/149_n7_sweet_joint_coverage.html` and the figure set exist, but the cited **`audits/issue439-union-v3` directory does not exist** anywhere under `/run/media/drwho1985/Sandisk/data/beijing-lot` (a depth-5 search for `*issue439*` returns only `reports/issue439-union-v1` and `reports/issue439-union-v3`). The audit trail cited by the issue is therefore not independently verifiable from the workspace.

**Committed on `main`?** No.

**Classification for #493: PENDING.** Reason: branch-only and PR open; the cited audit evidence is missing; `n7_union_inputs` is the strongest freeze-binding candidate but is bound to #439's catalog, not to #493's snapshot/DC inputs.

**What #493 still must build:** re-point the binding at #493's Nowscore snapshot + DC probability base; add the missing mask/TopK semantics; re-create an evidence directory (the cited `audits/issue439-union-v3` is absent).

## 8. #451 — N7 prefix stopping and marginal ticket return

**Contract / acceptance.** OPEN, Project `Review`, Task, no graph edges. Comment: PR #452, code `71cc1e15`, delivery record `e0331014`; verdict **retain the original purchase depth**; the comment honestly records that the full R suite still has 6 pre-existing failures/errors and 2 skips, and that no full Python/CI green is claimed.

**Delivered artifacts (branch only).** Branch `origin/codex/451-prefix-stop` @e0331014; PR #452, base `codex/449-refill-conclusion`, **OPEN**. Delta vs base: `quarto/155_n7_prefix_stop.qmd`, `r/n7_prefix_stop.R`, `r/n7_prefix_settlement.R`, `src/n7_prefix_validation.py`, `docs/research/n7_prefix_stop_451.md`, `tests/test_n7_prefix_validation.py`, `tests/testthat/test-n7-prefix-stop.R`, `test-n7-prefix-settlement.R`.

**Tests observed:** `pytest tests/test_n7_prefix_validation.py -q` → **1 passed**. R: `test-n7-prefix-stop.R` 9 pass, `test-n7-prefix-settlement.R` 6 pass.

**Chronology.** The delivered design keeps selection on frozen pre-decision prefixes and uses actual SP only in a separate settlement module (`n7_prefix_settlement.R`); the comment states the 0.65 factor is applied once at ticket level. No contamination found.

**Committed on `main`?** No.

**Classification for #493: PENDING.** Reason: branch-only, PR open, and the result is a diagnostic "retain ORIGINAL" verdict rather than a reusable #493 component. #493 may reuse the depth/prefix arithmetic only after integration.

**What #493 still must build:** nothing new; #493's budget rule differs (period ceiling with cash retention and cross-day accumulation), so the fixed per-issue prefix arithmetic must be re-derived on top of #493's contract.

## 9. #453 — quality-gated N7 group selection and shared failure risk

**Contract / acceptance.** OPEN, Project `Review`, Task, no graph edges. Comment: PR #454, commit `d7063860`; verdict **retain the original JOINT marginal-union selection**; the PR is stacked on `codex/451-prefix-stop`; the comment repeats the 6 pre-existing full-suite failures and states no merge/closure.

**Delivered artifacts (branch only).** Branch `origin/codex/453-quality-diversification` @d7063860; PR #454, base `codex/451-prefix-stop`, **OPEN**. Delta vs base: `quarto/156_n7_quality_diversification.qmd`, `r/n7_quality_allocate.R`, `r/n7_quality_diagnostics.R`, `r/n7_quality_settlement.R`, `src/n7_quality_replay.py`, `docs/research/n7_quality_diversification_453.md`, `tests/test_n7_quality_replay.py`, `tests/testthat/test-n7-quality-*.R`.

**Tests observed:** `pytest tests/test_n7_quality_replay.py -q` → **4 passed**. R: `test-n7-quality-allocate.R` 14, `test-n7-quality-diagnostics.R` 14, `test-n7-quality-settlement.R` 7 — all pass.

**Committed on `main`?** No.

**Classification for #493: PENDING.** Reason: branch-only, PR open, stacked on an open PR; the verdict is a negative/diagnostic retention result.

**What #493 still must build:** the quality-band gate is not part of #493's confirmed contract (it does not filter by difficulty/SP preference); #493 needs the reuse/overlap accounting only, which #453 measures rather than provides as an interface.

## 10. #455 — budget-aware N7 group exchanges versus JOINT greedy selection

**Contract / acceptance.** OPEN, Project `Review`, Task, no graph edges. Comment: PR #456, commit `a5cd2f60`; recommends `EXCHANGE12` as the preferred variant **for the exposed historical study only**, explicitly not a drawdown or unseen-data claim; no merge/closure.

**Delivered artifacts (branch only).** Branch `origin/codex/455-budget-exchanges` @a5cd2f60; PR #456, base `codex/453-quality-diversification`, **OPEN**. Delta vs base: `quarto/157_n7_group_exchanges.qmd`, `r/n7_group_exchange.R`, `r/n7_frozen_scenarios.R`, `src/n7_exchange_replay.py`, `docs/research/n7_budget_exchanges_455.md`, `tests/test_n7_exchange_replay.py`, `tests/testthat/test-n7-group-exchange.R`, `test-n7-frozen-scenarios.R`.

**Tests observed:** `pytest tests/test_n7_exchange_replay.py -q` → **3 passed**. R: `test-n7-group-exchange.R` 18 pass, `test-n7-frozen-scenarios.R` 5 pass.

**Committed on `main`?** No.

**Classification for #493: PENDING.** Reason: branch-only, PR open, stacked; the exchange search is a later-stage capability (#496/#497) and its gains are explicitly seed/configurations-dependent, not independent evidence.

**What #493 still must build:** nothing for the minimal replay; later stages must rebuild the exchange search on top of #493's period/decision-epoch budget accounting.

## 11. #459 — fixed main N7 strategies on the expanded 495 accepted issues

**Contract / acceptance.** OPEN, Project `Review`, Task, no graph edges. Comment: PI/Codex research acceptance for PR #460, commit `2a60dd72`; retains SP1.30 JOINT as reference; states "this is exposed retrospective research, not prospective validation" and that added-period gain must not justify more budget. Delivery/evidence is quoted under `/run/media/drwho1985/Sandisk/data/beijing-lot/`.

**Delivered artifacts (branch only).** Branch `origin/codex/459-expanded-strategies` @2a60dd72; PR #460, base `codex/457-group-attribution`, **OPEN**. Delta vs base: `quarto/159_n7_expanded_strategies.qmd`, `r/n7_expanded_diagnostics.R`, `src/n7_expanded_replay.py`, `src/n7_expanded_pool_check.py`, `config/n7_expanded_459.json`, `docs/research/n7_expanded_strategies_459.md`, tests `tests/test_n7_expanded_{catalog,dispatch,inputs,pool_check,replay,worlds}.py`, `tests/testthat/test-n7-expanded-diagnostics.R`. This branch tip also contains every earlier artifact of the stack (`quarto/130..159`).

**Tests observed:** `pytest tests/test_n7_expanded_catalog.py tests/test_n7_expanded_dispatch.py tests/test_n7_expanded_inputs.py tests/test_n7_expanded_pool_check.py tests/test_n7_expanded_replay.py tests/test_n7_expanded_worlds.py -q` → **23 passed**. R: `test-n7-expanded-diagnostics.R` 13 pass, `test-n7-exchange-attribution.R` 23 pass (inherited from #457).

**Chronology.** The contract pins registry release `market-cleaning-120408-121002-v1` (SHA256 `629e07fc…`), keeps new allocations frozen before settlement reads, and states that labels already exposed during cleaning do not make the study prospective. Diagnostic-only evidence; no silent post-cutoff input found.

**Committed on `main`?** No (178 ahead / 88 behind).

**Classification for #493: PENDING.** Reason: branch-only, PR open; it evaluates strategies on 495 exposed issues, which is not #493's decision-epoch/availability contract.

**What #493 still must build:** #493 needs 20:00-Asia/Shanghai availability evidence and the DC probability base, neither of which #459 establishes; #459's 495-issue registry release may be reused only as a **historical diagnostic** input, not as the decision input.

## 12. Existing Dixon-Coles chain (#493 deliverable 3's subject)

**What exists where.**

- `r/dixon_coles_grid.R`, `src/dixon_coles_rho.py`, `r/n7_market_projection.R`, `r/fundamentals_total_market.R`, `r/fundamentals_market_comparison.R`, `r/ou_total_market.R` exist in the working tree but are **untracked** (`git status --porcelain` shows `??` for each; `git ls-tree HEAD` finds none of them).
- The committed home of the DC grid is branch `codex/258-dixon-coles-score-grid` @f1cc5485 (commit `6dcc6844`, "feat: Dixon-Coles low-score dependence for the score grid"), which is **not merged into `main`** (`git merge-base --is-ancestor` → NO).
- The untracked working-tree copies of `r/dixon_coles_grid.R`, `r/n7_market_projection.R`, `r/fundamentals_total_market.R`, `r/fundamentals_market_comparison.R` and their three R test files are byte-identical to the branch blobs (`diff` clean). `r/ou_total_market.R` and `tests/testthat/test-ou-total-market.R` are untracked and are **absent from that branch** (newer concurrent work).
- The four R files that the DC tests `source()` — `r/probability_exploration.R`, `r/strength_market_scenario.R`, `r/fundamentals_score_diagnostic.R`, `r/fundamentals_score_shape.R` — exist on `codex/258-dixon-coles-score-grid` and are **missing from the working tree entirely** (they are not even present as untracked files).

**Tests observed on `main` (working tree, `R_LIBS_USER=<repo>/r_lib`, run from `tests/testthat`):**

- `test-dixon-coles-grid.R`, `test-n7-market-projection.R`, `test-fundamentals-total-market.R` each → **1 error, 0 pass**: `Error in file(filename, "r"): 无法打开文件'../../r/probability_exploration.R'`.
- `test-ou-total-market.R` → **6 failed, 9 errors, 0 pass**: `没有"ou_devig"这个函数` / `没有"ou_p_over"这个函数` — the test file never `source()`s `r/ou_total_market.R` (unlike the other DC tests) and no helper loads it, so the functions are undefined.

**Tests observed on the branch tree (`git archive codex/258-dixon-coles-score-grid r tests src scripts config` into a temp dir):**

- `test-dixon-coles-grid.R` **32 pass**, `test-n7-market-projection.R` **34 pass**, `test-fundamentals-total-market.R` **28 pass**, `test-fundamentals-market-comparison.R` **24 pass**.
- `.venv/bin/python -m pytest tests/dixon_coles_rho/test_rho.py -q` → **34 passed** (1 pandas dateutil warning).

**Chronology.** `r/n7_market_projection.R` uses an explicit cutoff; the grid/rho modules are pure probability transforms. No post-cutoff input was found. The issue's own framing (deliverable 3) already anticipates the problems: inconsistent old rho documentation, a rho=0 configuration, and missing rebuild scripts.

**Classification for the DC chain: PENDING.** Reason: the authoritative modules are not committed to `main`; on `main` the DC R tests cannot even load their dependencies; the `ou` component's test does not run. The code itself is sound where it can be exercised (all four R files and the Python rho suite pass on the branch).

**What #493 still must build:** commit the DC chain (or an equivalent authoritative version) to `main` with its four dependency modules; fix `test-ou-total-market.R` to load its module; resolve the rho documentation/configuration inconsistency and pin one rho for #493 (default −0.14, sensitivity −0.2…−0.1 as an open question, not a proven optimum); bind the DC probability base to #493's Nowscore snapshot and `src/temporal_learning` cutoff receipt.

## 13. Shared infrastructure on `main` that #493 can actually reuse

These are committed on `main` (verified with `git ls-tree HEAD`) and their tests were run in this audit:

- `src/temporal_learning` (core, provenance, replay, issue_partitions, predictor_clock, diagnostic_labels) — the mandated chronology implementation; covered by `tests/test_bj252_temporal_semantics.py` and by every `tests/test_fundamentals_*` that imports it.
- `src/ticket_policy/fixed_n7.py` — N7 candidate generation on `main`; `tests/test_bj206_fixed_n7.py`.
- `src/nowscore_settlement.py` — Nowscore settlement parsing/DB build (no payout policy by its own docstring); `tests/test_nowscore_settlement.py`.
- `src/bj396_settlement` — settlement source-probe/quarantine pipeline; `tests/test_bj396_settlement.py`.
- `src/freeze_v0.py`, `src/research_freeze_protocol.py` — freeze/receipt machinery; `tests/test_freeze_v0.py`.
- `r/n7_fixture_portfolio.R` — committed R N7 fixture/ticket portfolio helper; `tests/testthat/test-n7-fixture-portfolio.R` **224 pass**.

Combined run: `.venv/bin/python -m pytest tests/test_freeze_v0.py tests/test_nowscore_settlement.py tests/test_bj396_settlement.py tests/test_bj206_fixed_n7.py tests/test_bj252_temporal_semantics.py -q` → **170 passed** (185.21 s).

Also observed: `r/joint_basket_sleeve_settle.R` (untracked on `main`) — `tests/testthat/test-joint-basket-sleeve-settle.R` **29 pass**; not committed, therefore PENDING.

**Concurrent in-progress work (not evidence):** `r/n7_experiment_contract.R` is present but **untracked** (531 lines, constants 1024 CNY / 2 CNY / 20:00 Asia/Shanghai / 24 h window). It is work in progress by another session; it is not committed, not tested in this audit, and is not counted as a #493 delivery here.

## 14. Consolidated matrix

The machine-readable form of this table is `results/n7_493_reuse_matrix_v1/matrix.csv`; the exact commands and observed outcomes are in `results/n7_493_reuse_matrix_v1/MANIFEST.json`.

| issue | artifact path | kind | committed? | tested? | test command | test result | class | reason | what #493 must still build |
|---|---|---|---|---|---|---|---|---|---|
| #424 | `quarto/134_n7_sleeve_portfolio.qmd .. quarto/139_n7_joint_sleeves.qmd` | QMD deliverable | no (origin/codex/424-joint-research @c543069c) | claimed only | `not run (no QMD re-render performed)` | not observed | **PENDING** | Branch-only. PRs #426/#428 merged into codex/424-research-base; main unchanged; #424 acceptance says main integration is separate and unreviewed. | Integrate to main, then re-render under #493 inputs (decision epoch, DC base, masks). |
| #424 | `r/n7_sleeve_summary.R, r/n7_sleeve_tables.R` | R module (depth curves, sleeve summary, long audit tables) | no (branch) | yes | `Rscript --vanilla -e "library(testthat); test_file('test-n7-sleeve-summary.R')" (and test-n7-sleeve-tables.R)` | 16 pass / 31 pass | **REUSE** | Component-ready C_s(m) depth curves and tibble sleeve/long audit tables; tests pass; no post-cutoff input found. | Add mask/TopK columns and integrate to main. |
| #424 | `r/n7_joint_sleeves.R, r/n7_joint_report.R` | R core (2187-state namespace, shared-scenario P(any hit), 8x64) | no (branch) | yes | `test_file('test-n7-joint-sleeves.R') with FUNDAMENTALS_PYTHON=<repo>/.venv/bin/python and PYTHONPATH=<tree>` | 54 pass (25 pass for joint-report); without env 1 fail + 3 error (empty python path / reticulate import src.temporal_learning) | **REUSE** | Canonical 3^7 namespace and shared issue-level outcome worlds are exactly the union base #493 needs; chronlogy delegated to src/temporal_learning. | Integrate; bind the DC probability base; add (match,outcome) masks and legal TopK. |
| #424 | `src/n7_sleeve_states.py, src/n7_sleeve_candidates.py, src/n7_sleeve_portfolio.py, src/n7_sleeve_probability_cap.py, src/n7_sleeve_cap_check.py, src/n7_sleeve_expansion.py, src/n7_sleeve_expansion_check.py, src/n7_joint_study.py, src/n7_joint_check.py` | Python core (state namespace, candidates, portfolio/scenario union, joint study) | no (branch) | yes | `.venv/bin/python -m pytest tests/test_n7_sleeve_states.py tests/test_n7_sleeve_portfolio.py tests/test_n7_sleeve_runner.py tests/test_n7_sleeve_checker.py tests/test_n7_sleeve_expansion.py tests/test_n7_sleeve_expansion_runner.py tests/test_n7_sleeve_probability_cap.py tests/test_n7_sleeve_cap_runner.py tests/test_n7_joint_study.py tests/test_n7_joint_check.py -q` | 40 passed in 27.99s | **REUSE** | Verified state enumeration and shared-scenario union implementation; note src/n7_sleeve_portfolio.py 'masks' are scenario bitmasks, not (match,outcome) ticket masks. | Integrate to main; add #493 mask semantics. |
| #424 | `docs/research/n7_joint_acceptance.md, n7_joint_acceptance_receipt.json, n7_joint_checks.json, n7_joint_codex_review.md` | acceptance evidence | no (branch) | n/a | `git ls-tree (existence only)` | exists on branch, absent on main | **PENDING** | Acceptance evidence is off-main and is retrospective-only (historical_admission=false, exposed 2010-only data, synthetic risk). | Carry into the #493 evidence chain or re-derive on #493 inputs. |
| #425 | `quarto/140_n7_capital_frontier.qmd (+141, 142)` | QMD deliverable | no (origin/codex/425-capital-frontier @977aeabb; PR #432 OPEN) | claimed only | `not run` | not observed | **PENDING** | Branch-only; PR open with base codex/424-research-base. | Integrate; re-render for #493 budget controls. |
| #425 | `r/n7_capital_depth.R, r/n7_capital_portfolio.R, r/n7_capital_compare.R, r/n7_capital_issue.R, r/n7_capital_report.R` | R module (depth/coverage threshold, allocation, portfolio compare) | no (branch) | yes | `test_file('test-n7-capital-compare.R' / '-depth.R' / '-issue.R' / '-portfolio.R' / '-report.R')` | 30 / 24 / 40 / 42 / 38 pass | **REUSE** | Depth resolution (TopN and cumulative-tau) and budget allocation interfaces are the #493 depth/ceiling primitives. | Integrate; re-derive on #493 period-budget/cash semantics. |
| #425 | `src/n7_capital_study.py, src/n7_capital_check.py, src/n7_capital_archive.py, src/n7_rank_diagnostic.py` | Python study/check/archive | no (branch) | yes | `pytest tests/test_n7_capital_archive.py tests/test_n7_capital_check.py tests/test_n7_capital_study.py -q ; pytest tests/test_n7_rank_diagnostic.py tests/test_n7_single_ticket_sampling.py -q` | 15 passed ; 9 passed | **REUSE** | Replay/checker pattern and archive hashing are reusable for independent replay. | Integrate to main. |
| #425 | `docs/research/n7_capital_acceptance.md, n7_capital_contract.md` | acceptance evidence | no (branch) | n/a | `git ls-tree (existence only)` | exists on branch only | **PENDING** | Verdict NO_STABLE_FRONTIER is a diagnostic research conclusion, not an accepted #493 component; issue stays OPEN/Review. | Cite as diagnostic reference only. |
| #427 | `(none)` | no artifact | no | no | `gh pr list --search 427 ; git branch -a \| grep 427 ; git log --all --grep=427 ; per-branch ls-tree grep 'router\|realloc\|adaptive'` | no branch, PR, file or commit found; issue OPEN with no Project status and zero comments | **PENDING** | Not delivered at all; the contract's evaluate_reallocation/propose_reallocations interfaces do not exist anywhere. | Not needed for the #493 minimal replay; build from scratch in a later stage if required. |
| #439 | `src/n7_union_inputs.py` | Python freeze/binding contract | no (origin/codex/439-joint-coverage @c40d7b9f; PR #440 OPEN) | yes | `pytest tests/test_n7_union_inputs.py -q` | 5 passed | **REUSE** | Binds catalog bytes, rank receipt, source cutoffs and src.temporal_learning implementation closure; rejects cross-snapshot/ambiguous sources; reads no labels. | Re-point binding at #493's Nowscore snapshot + DC probability base. |
| #439 | `r/n7_sweet_union.R, r/n7_sweet_union_summary.R` | R module (marginal joint-coverage allocation) | no (branch) | yes | `test_file('test-n7-sweet-union.R' / 'test-n7-sweet-union-summary.R')` | 12 pass / 12 pass | **REUSE** | Marginal union/CNY allocation with shared scenarios is the closest existing analogue of #493 group construction. | Integrate; accept explicit reuse/overlap cap parameters. |
| #439 | `quarto/149_n7_sweet_joint_coverage.qmd` | QMD deliverable | no (branch) | claimed only | `not run` | not observed | **PENDING** | Branch-only; the rendered HTML exists on the external persistent root but the QMD is not on main. | Re-render for #493. |
| #439 | `audits/issue439-union-v3/ (cited by the issue comment)` | evidence directory | no | n/a | `find /run/media/drwho1985/Sandisk/data/beijing-lot -maxdepth 5 -iname '*issue439*'` | only reports/issue439-union-v1 and reports/issue439-union-v3 found; audits/issue439-union-v3 absent | **PENDING** | Cited audit trail is not present on the persistent root, so the frozen plan grid cannot be independently replayed from this workspace. | Recreate an evidence directory under #493's own contract. |
| #451 | `r/n7_prefix_stop.R, r/n7_prefix_settlement.R` | R module (prefix stopping + separate settlement) | no (origin/codex/451-prefix-stop @e0331014; PR #452 OPEN) | yes | `test_file('test-n7-prefix-stop.R' / 'test-n7-prefix-settlement.R')` | 9 pass / 6 pass | **REUSE** | Clean separation of frozen prefix selection from settlement replay; 0.65 applied once at ticket level. | Integrate; re-derive on #493's cross-day period budget. |
| #451 | `src/n7_prefix_validation.py` | Python report-completeness contract | no (branch) | yes | `pytest tests/test_n7_prefix_validation.py -q` | 1 passed | **REUSE** | Deterministic completeness check over arm/seed grids; no fitting or selection. | Integrate to main. |
| #451 | `quarto/155_n7_prefix_stop.qmd` | QMD deliverable | no (branch) | claimed only | `not run` | not observed | **PENDING** | Branch-only; verdict is 'retain original depth', a diagnostic conclusion. | Re-render for #493 if used as a control. |
| #451 | `audits/issue451-prefix-comparison-v2/ (cited)` | evidence directory | no | n/a | `find /run/media/drwho1985/Sandisk/data/beijing-lot -maxdepth 5 -iname '*issue451*'` | only reports/issue451-prefix-v1 and -v2 found; the cited audits directory is absent | **PENDING** | Cited audit trail not present; independent replay not possible here. | Recreate under #493 if reused. |
| #453 | `r/n7_quality_allocate.R, r/n7_quality_diagnostics.R, r/n7_quality_settlement.R` | R module (quality gate, overlap/concentration diagnostics) | no (origin/codex/453-quality-diversification @d7063860; PR #454 OPEN, stacked on #451) | yes | `test_file('test-n7-quality-allocate.R' / '-diagnostics.R' / '-settlement.R')` | 14 / 14 / 7 pass | **REUSE** | Overlap and concentration diagnostics (pair overlap, HHI-style measures) are directly useful to #493's reuse/overlap control. | Integrate; do not import the quality gate as a #493 eligibility filter. |
| #453 | `src/n7_quality_replay.py` | Python replay | no (branch) | yes | `pytest tests/test_n7_quality_replay.py -q` | 4 passed | **REUSE** | Independent replay/accounting pattern. | Integrate to main. |
| #453 | `quarto/156_n7_quality_diversification.qmd` | QMD deliverable | no (branch) | claimed only | `not run` | not observed | **PENDING** | Branch-only; verdict is retention of the existing JOINT rule. | Re-render for #493 if reused as a control. |
| #453 | `audits/issue453-quality-v1/ (cited)` | evidence directory | no | n/a | `find /run/media/drwho1985/Sandisk/data/beijing-lot -maxdepth 5 -iname '*issue453*'` | only reports/issue453-quality-v1 found; audits directory absent | **PENDING** | Cited audit trail not present. | Recreate under #493 if reused. |
| #455 | `r/n7_group_exchange.R, r/n7_frozen_scenarios.R` | R module (1-to-1/1-to-2 exchanges, frozen scenarios) | no (origin/codex/455-budget-exchanges @a5cd2f60; PR #456 OPEN, stacked on #453) | yes | `test_file('test-n7-group-exchange.R' / 'test-n7-frozen-scenarios.R')` | 18 pass / 5 pass | **REUSE** | Deterministic exchange neighbourhood with strict-improvement termination and frozen scenario reuse. | Integrate; later-stage capability, not required by #493's minimal replay. |
| #455 | `src/n7_exchange_replay.py` | Python replay | no (branch) | yes | `pytest tests/test_n7_exchange_replay.py -q` | 3 passed | **REUSE** | Independent replay/accounting of exchanges. | Integrate to main. |
| #455 | `quarto/157_n7_group_exchanges.qmd` | QMD deliverable | no (branch) | claimed only | `not run` | not observed | **PENDING** | Branch-only; EXCHANGE12 recommendation is scoped to the exposed historical study. | Re-render for #493 if reused as a control. |
| #455 | `audits/issue455-exchange-v1/ (cited)` | evidence directory | no | n/a | `find /run/media/drwho1985/Sandisk/data/beijing-lot -maxdepth 5 -iname '*issue455*'` | only reports/issue455-exchange-v1 found; audits directory absent | **PENDING** | Cited audit trail not present. | Recreate under #493 if reused. |
| #459 | `r/n7_expanded_diagnostics.R` | R module (diagnostics for seven strategies) | no (origin/codex/459-expanded-strategies @2a60dd72; PR #460 OPEN, stacked on #457) | yes | `test_file('test-n7-expanded-diagnostics.R')` | 13 pass | **REUSE** | Reusable diagnostics/plotting helpers over frozen strategy ledgers. | Integrate to main. |
| #459 | `src/n7_expanded_replay.py, src/n7_expanded_pool_check.py, config/n7_expanded_459.json` | Python replay/pool-check + config | no (branch) | yes | `pytest tests/test_n7_expanded_catalog.py tests/test_n7_expanded_dispatch.py tests/test_n7_expanded_inputs.py tests/test_n7_expanded_pool_check.py tests/test_n7_expanded_replay.py tests/test_n7_expanded_worlds.py -q` | 23 passed | **REUSE** | Replay and pool validation with source/cutoff receipts; the seven strategy definitions are frozen and reproducible. | Integrate to main. |
| #459 | `config/n7_expanded_459.json minimum_sp=1.3 eligibility gate (same gate in #451/#453/#455)` | research eligibility gate | no (branch) | n/a | `grep -n 'minimum_sp' config/n7_expanded_459.json` | minimum_sp: 1.3 present on six arms | **UNUSABLE** | #493 forbids SP/difficulty preference as a base eligibility filter ('概率、SP、难易度偏好不自动成为基础资格过滤'). Importing this gate into #493's candidate pool would violate the confirmed contract. | Keep as a research control only; #493 builds its own unfiltered eligibility rule. |
| #459 | `quarto/159_n7_expanded_strategies.qmd` | QMD deliverable | no (branch) | claimed only | `not run` | not observed | **PENDING** | Branch-only; the 495-issue study is exposed retrospective research by its own acceptance. | Re-render for #493 if reused as a diagnostic. |
| #459 | `audits/issue459-expanded-v1/ (cited)` | evidence directory | no | n/a | `find /run/media/drwho1985/Sandisk/data/beijing-lot -maxdepth 5 -iname '*issue459*'` | only reports/issue459-expanded-v1 found; audits directory absent | **PENDING** | Cited audit trail not present. | Recreate under #493 if reused. |
| DC chain | `r/dixon_coles_grid.R` | R module (Dixon-Coles tau grid) | no (branch codex/258-dixon-coles-score-grid @f1cc5485 commit 6dcc6844; untracked copy on main) | yes | `branch tree: test_file('test-dixon-coles-grid.R'); main tree: same` | 32 pass on branch; on main 1 error (cannot open ../../r/probability_exploration.R) | **PENDING** | Authoritative module is not committed to main; on main its test cannot load four sourced dependencies that are absent from the working tree. | Commit to main with r/probability_exploration.R, r/strength_market_scenario.R, r/fundamentals_score_diagnostic.R, r/fundamentals_score_shape.R; bind to #493 snapshot. |
| DC chain | `src/dixon_coles_rho.py` | Python rho estimation/history | no (untracked on main; branch 258) | yes | `branch tree: .venv/bin/python -m pytest tests/dixon_coles_rho/test_rho.py -q` | 34 passed (1 pandas dateutil warning) | **PENDING** | Untracked on main; rho documentation/config inconsistency (rho=0 config, missing rebuild scripts) still to resolve per #493 deliverable 3. | Commit to main; pin one rho (default -0.14) and document the sensitivity range as open. |
| DC chain | `r/n7_market_projection.R` | R module (DC score grid -> N7 three-way probability) | no (untracked on main; branch 258) | yes | `branch tree: test_file('test-n7-market-projection.R'); main tree: same` | 34 pass on branch; on main 1 error (missing ../../r/probability_exploration.R) | **PENDING** | The probability-base module #493 needs is not committed; its test cannot run on main. | Commit to main; expose the DC->N7 interface for #493. |
| DC chain | `r/fundamentals_total_market.R` | R module (totals market -> probabilities) | no (untracked on main; branch 258) | yes | `branch tree: test_file('test-fundamentals-total-market.R'); main tree: same` | 28 pass on branch; on main 1 error (missing ../../r/probability_exploration.R) | **PENDING** | Same as above; also note #493 requires not mixing the Beidan totals market path with the DC path. | Commit to main; keep the totals/DC paths separated per #493 deliverable 3. |
| DC chain | `r/fundamentals_market_comparison.R` | R module (market comparison) | no (untracked on main; branch 258) | yes | `branch tree: test_file('test-fundamentals-market-comparison.R')` | 24 pass on branch | **PENDING** | Untracked on main; supporting module for the DC chain. | Commit to main with the rest of the chain. |
| DC chain | `r/ou_total_market.R + tests/testthat/test-ou-total-market.R` | R module + test (over/under totals) | no (untracked; absent from branch 258) | attempted, fails | `main tree: test_file('test-ou-total-market.R')` | 6 failed / 9 errors / 0 pass (no 'ou_devig' / 'ou_p_over' function: the test never sources r/ou_total_market.R and no helper loads it) | **PENDING** | Test file cannot load its module; the component is untracked and unverifiable as delivered. | Fix the test to source the module, commit both, then re-run before any reuse. |
| shared (main) | `src/temporal_learning (core, provenance, replay, issue_partitions, predictor_clock, diagnostic_labels)` | Python package (cutoff/receipt/replay) | yes (main) | yes | `pytest tests/test_bj252_temporal_semantics.py tests/test_freeze_v0.py tests/test_nowscore_settlement.py tests/test_bj396_settlement.py tests/test_bj206_fixed_n7.py -q` | 170 passed in 185.21s | **REUSE** | The owner-mandated chronology implementation; committed on main and green. | Use as-is for every #493 decision-facing cutoff; do not copy its helpers. |
| shared (main) | `src/ticket_policy/fixed_n7.py` | Python N7 candidate generation | yes (main) | yes | `pytest tests/test_bj206_fixed_n7.py -q` | part of the 170 passed run | **REUSE** | Committed N7 candidate generator with provenance/digest handling. | Evaluate against #493's unfiltered eligibility rule before adopting. |
| shared (main) | `src/nowscore_settlement.py` | Python settlement parsing/DB build | yes (main) | yes | `pytest tests/test_nowscore_settlement.py -q` | part of the 170 passed run | **REUSE** | Committed settlement source parser; declares no payout policy, so the 0.65 rule must be applied by the caller. | Wrap with the single ticket-level 0.65 payout application for #493. |
| shared (main) | `src/bj396_settlement` | Python settlement pipeline | yes (main) | yes | `pytest tests/test_bj396_settlement.py -q` | part of the 170 passed run | **REUSE** | Committed settlement/quarantine pipeline with source-probe receipts. | Reuse as the settlement authority for #493. |
| shared (main) | `src/freeze_v0.py, src/research_freeze_protocol.py` | Python freeze/receipt machinery | yes (main) | yes | `pytest tests/test_freeze_v0.py -q` | part of the 170 passed run | **REUSE** | Committed freeze/receipt tooling. | Bind #493's frozen ticket sets before opening settlement. |
| shared (main) | `r/n7_fixture_portfolio.R` | R module (N7 fixture/ticket portfolio) | yes (main) | yes | `Rscript --vanilla -e "library(testthat); test_file('test-n7-fixture-portfolio.R')"` | 224 pass | **REUSE** | Committed R N7 ticket-level portfolio helper with the strongest test coverage found in this audit. | Extend with #493's mask/TopK and period-budget parameters rather than duplicating it. |
| shared (untracked) | `r/joint_basket_sleeve_settle.R` | R module (sleeve settlement) | no (untracked) | yes | `test_file('test-joint-basket-sleeve-settle.R')` | 29 pass | **PENDING** | Passes but is not committed, so #493 cannot rely on it. | Commit to main or replace with the authoritative settlement path. |
| #493 (WIP) | `r/n7_experiment_contract.R` | R module (period/decision-epoch/availability/accounting) | no (untracked; concurrent work by another session) | no | `not run (not part of this audit)` | not observed | **PENDING** | 531-line untracked work in progress; not committed and not tested here, so it is not evidence of a #493 delivery. | Finish, test and commit under #493 itself. |

### Row counts

45 matrix rows: **REUSE 21, PENDING 23, UNUSABLE 1**. Per-issue verdict (the reuse question #493 actually asks): all eight issues are **PENDING** as deliverables — #424 and #425 have REUSE-grade, tested component code but no `main` commit; #427 has nothing; #439/#451/#453/#455/#459 are branch-only with open, stacked PRs and partly unverifiable audit evidence; the DC chain is uncommitted and its tests error on `main`. The 21 REUSE rows are either main-committed shared infrastructure or branch components that are component-ready once integrated.

## 15. What #493 must still build (aggregate gap list)

1. **Decision epoch / availability (new).** 20:00 Asia/Shanghai decision instant, fixtures kicking off inside the next 24 h and still bettable, with explicit window endpoints and a sell-stop boundary test. Nothing in #424–#459 implements this; `src/decision_epoch_tensor` and the Nowscore collectors are the candidate base.
2. **Masks (new).** (match, outcome) hard/soft masks with no renormalisation after application, and legal TopK over the original combination probability. The `masks` found in `src/n7_sleeve_portfolio.py` / `src/n7_incremental_coverage.py` are scenario bitmasks for union coverage — different semantics.
3. **Period budget (new).** Balance = 1024 − period cumulative actual spend, not reset per day, no top-up from returns, stop on exhaustion; unspent cash stays cash and must not be relabelled as alpha.
4. **SP estimate rule (new).** Store the actual pre-decision SP when available; for a single match/outcome use SP>10 → 4.5, SP≤10 unchanged, as a fixed rule applied to the estimate only, never to probability or settlement.
5. **DC probability base (PENDING).** Integrate the DC chain to `main`, fix its tests, pin rho, and bind it to the Nowscore snapshot with a `src/temporal_learning` receipt.
6. **Freeze / settlement / QMD (PENDING).** Reuse `src/temporal_learning`, `src/freeze_v0.py`, `src/nowscore_settlement.py`, `src/bj396_settlement`; the QMD acceptance entry point does not exist for #493 yet (the nearest artifacts are branch-only `quarto/140..159`).

## 16. Evidence limitations of this audit

- Branch tests were executed from `git archive` extractions of the branch trees into a temporary directory, because the hard rules forbid checkout/stash/worktree. The extracted tree contains `src/`, `r/`, `tests/`, `config/`, `scripts/` but **not** `results/` (6.3 GB on that branch), so tests that need the large frozen result trees were not exercised.
- Some tests require environment variables that the repository does not set by default (`FUNDAMENTALS_PYTHON`, `PYTHONPATH`, `RSCRIPT`). Where that caused failures I report both the as-invoked result and the result with the variables set; I never claim a pass I did not observe.
- I did not re-render any QMD. The issues claim clean renders; the rendered HTML files exist under the external persistent root for #439/#451/#453/#455/#459, but I verified only their existence, not their content.
- The `audits/issueNNN-*` directories cited by #439/#451/#453/#455/#459 comments were not found on the persistent root; only `reports/issueNNN-*` were. Independent replay of the frozen plan grids was therefore not possible in this session.
- The chronology check is a targeted code/contract inspection, not an exhaustive transitive audit. The issues' own statements (`historical_admission=false`, exposed 2010-only data, exposed 200-issue panels, repeated seeds not independent samples) mean all of their evidence is **retrospective-diagnostic**, which is the strongest limitation for #493's decision-facing contract.
