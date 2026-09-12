**Suitable for a scoped historical-only draft PR; the original #424 contract is not fulfilled.** No new critical correctness findings in the full **44-file, three-commit diff `2798b83a..b125a0d1`**.

Live graph, read before review and rechecked: **OPEN / PI Review**, Task, parent #202, no blockedBy/blocking/subIssues.

Unresolved acceptance concerns, all **high confidence**:

- **P1 — Causal probability admission remains unproven.** Cutoff validation checks identity and timestamps, but does not establish actual source availability. The reports explicitly retain exposed probabilities, historical clock proxies and `historical_admission=false`. Preserve that boundary; source hashes and this run’s freeze ordering cannot certify causality. [Validation](https://github.com/algotradinglife/beijing-lot/blob/b125a0d133fb1e96ecbe4debf8b28b52222fb4fa/src/fundamentals_n7_baseline.py#L82), [disclosure](https://github.com/algotradinglife/beijing-lot/blob/b125a0d133fb1e96ecbe4debf8b28b52222fb4fa/docs/research/n7_sleeve_portfolio.md#L10).

- **P2 — Prior-window development is not demonstrated.** Frontier thresholds, overlap penalties, pool sizes and probability caps are fixed retrospective sensitivities. Freezing them before this run reads settlement does not establish the issue’s required prior-development-window selection. Explicitly mark that requirement outstanding in PI evidence. [Frontier declaration](https://github.com/algotradinglife/beijing-lot/blob/b125a0d133fb1e96ecbe4debf8b28b52222fb4fa/docs/research/n7_sleeve_portfolio.md#L56), [expansion disclosure](https://github.com/algotradinglife/beijing-lot/blob/b125a0d133fb1e96ecbe4debf8b28b52222fb4fa/quarto/135_n7_sleeve_expansion.qmd#L37).

- **P2 — R implementation is a disclosed contract deviation.** Python/NumPy/SciPy performs numerical selection; R projects frozen arrays into matrices, rankings, long tables and depth curves. Those interfaces are delivered, but they do not literally fulfill “R-native vectorized” computational-core wording. Record the deviation without claiming contract equivalence. [Implementation distinction](https://github.com/algotradinglife/beijing-lot/blob/b125a0d133fb1e96ecbe4debf8b28b52222fb4fa/docs/research/n7_sleeve_portfolio.md#L98).

- **P2 — Optimization and validation remain bounded.** Portfolio construction uses greedy/local search and reported risk diagnostics, rather than the complete joint return/overlap/path-risk constrained problem. Solver timeouts affect exposure; cross-year and ex-largest-year evidence are unavailable. Keep these unresolved rather than treating numerical/accounting acceptance as scientific completion. [Search](https://github.com/algotradinglife/beijing-lot/blob/b125a0d133fb1e96ecbe4debf8b28b52222fb4fa/src/n7_sleeve_portfolio.py#L55), [limitations](https://github.com/algotradinglife/beijing-lot/blob/b125a0d133fb1e96ecbe4debf8b28b52222fb4fa/docs/research/n7_sleeve_portfolio.md#L250).

The transitive inventory covers inherited `draw_cells`/`fit_draw_foundation`/`predict_draw_foundation` calibration, probability-pool generation/ranking, state enumeration/subset optimization, sleeve candidate construction, shared-world portfolio selection, expansion sampling and capped allocation. Inherited calibration uses shared temporal context with **diagnostic** availability; this diff adds no historical fit. Selection receives no settlement labels. Shared `Cutoff`, seals and implementation closures bind artifacts; they do not upgrade inherited availability evidence.

State identity, 64/512-ticket accounting, explicit cash, one ticket-level `.65`, shared fixture-world dependence, independent evaluation RNG and freeze-before-settlement are supported by code and tests. R accounting is descriptive. Archived CI remains accounting-only; native evidence is separate.

I independently executed **34 Python tests and 53 R assertions**, all passing. Hash verification found:

- All **39 acceptance-bound files** unchanged.
- All three studies’ source/bundle/plan bindings and five implementation closures matching.
- **43 implementation/report files** matching the committed head.
- **201 state exports** verified; all three archive result bodies byte-identical to native results.

I reused hash-matching reviews and completed native replay evidence. I did **not** rerun full native replay, full R suites, Quarto renders or cutoff governance.

The stacked draft is honest with base pinned to `2798b83a`, reviewed head `b125a0d1`, and PI evidence explicitly recording these gaps. Live comparison shows **83 commits ahead of main and 7 behind**, with no matching open PR: main integration remains unreviewed. **Draft-ready historical research only; no prospective admission, merge approval or issue-closure recommendation.** No repository or GitHub mutations were made.