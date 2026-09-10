# Updated-input C1/C2 comparison (#419)

48 issues 100402–100607, 72 unchanged strategy definitions. This is post-exposure
retrospective diagnosis, not an independent holdout or prospective promotion.
No retraining: draw 1.1.0 and high-margin 0.1.0, both weights 0.5.
Each issue has CNY1,024 budget, CNY2 basic units, one ticket-level 0.65 factor,
and no correct-score protection. Market estimates use pre-match Euro+OU score
projection, never settlement SP for selection. Actual payouts use R/SQLite SP.

## Input expansion

Prepared input: `data/derived/fundamentals_417/new48-source-order-v2`.
3149 fixtures remain in scope; jointly usable fixtures increase 1886 → 2561.
All original 1886 p/q distributions are exactly unchanged. The additional675
fixtures make every issue eligible for seven-leg groups (previously33 bet/15 cash).
All2561 pass the existing settlement identity, score, handicap and SP audit.

The expansion includes owner-approved quote interpretation, not675 newly
downloaded pages: lowest numeric HTML row for same-minute ties, with the
newest-first assumption explicit; valid clocks outside ±31days excluded with
their raw rows retained. Strict pre-cutoff comparison remains unchanged.
These clocks remain historical proxies. Later clock-adjudication development
in another session is deliberately excluded from this frozen replay.

## Results

Budget ROI uses48×1024=49152, including cash. Drawdown is issue-end chronological
net P&L with initial capital100000, not intraday or fixture-time drawdown.

|Case|Rule|Net CNY|Budget ROI|Max drawdown CNY|Winning groups|Net excluding largest-profit issue|
|---|---|---:|---:|---:|---:|---:|
|D2 TOP2 FREE|GAP10|12036.56|24.49%|10490.74|47/768|4884.68|
|D2 COMPRESSED FREE|GAP10|6272.42|12.76%|10490.74|43/768|-805.53|
|D2 TOP2 FREE|GAP05|6060.02|12.33%|8412.03|41/768|-3550.15|
|D2 TOP2 FREE|BASE|2993.85|6.09%|8412.03|40/768|-6616.32|
|D2 TOP2 STRICT|TV20|153.71|0.31%|5894.81|28/564|-3309.52|

11/36 D2 variants have positive net returns; 0/36 D1 variants do. Only D2 TOP2
FREE GAP10 stays positive after its own largest-profit issue is removed.
Its net increases5478.52 from the previous incomplete-input comparison, but
drawdown also increases7232.00 →10490.74. More coverage is not lower risk.
No observed winner is installed as a new default.

QMD75 presents all72 variants, before/after net and ROI, actual stake/cash,
drawdown, concentration sensitivity, and3456 paired issue/strategy observations.
TOP2 ranks original double coverage; COMPRESSED ranks actual compressed groups.
STRICT caps fixture reuse2 and pairwise overlap2; FREE removes both caps.
GAP02/05/10 replaces later repeated doubles only when p2−p3 is within the bound;
ALL always replaces. TAIL05/TV10/15/20 are unchanged market-tail conflict gates.

## Reproduction and contracts

Runtime/versions: `config/compression_breadth_runtime.json`.
Existing `project_clean_validation.R`, `predict_clean_validation.py`,
`fuse_clean_validation.R`, `plan_clean_validation.py`, `settle_clean_validation.py`
produce `new48-expanded-validation-v1`; `market_conflict_validation.py` produces
`new48-expanded-market-conflict-v1`. Both independent checkers pass:1920 and2688
rows, with shared controls reconciled to3456 unique rows. No pending settlements.

`scripts/package_expanded_comparison.py` packages those results and the two
previously published report fixtures into `new48-expanded-comparison-v1`.
Before/after input identities, frozen models, code closures, report code,
generation time, and fixed parameters are receipt-bound. Old accepted reports
are archive evidence; they are not falsely reverified against newer parser code.
Prepared component metadata is superseded by the outer report's explicit
`UPDATED_INPUTS_POST_EXPOSURE_RETROSPECTIVE` classification.

```sh
quarto render quarto/75_expanded_new48_variants.qmd --execute-dir . --execute --no-cache
python scripts/prepare_n7_single_fixture.py --fixture tests/fixtures/expanded_comparison_report.json.gz --output /path/new-expanded-report
quarto render quarto/75_expanded_new48_variants.qmd --execute-dir . --execute --no-cache -P study:/path/new-expanded-report -P archived_report:true
```

`read_verified_report_archive` and `merge_variant_reports` map to
`tests/test_fundamentals_expanded_comparison.py`. R `expanded_variant_comparison`
maps to `tests/testthat/test-fundamentals-expanded-comparison.R`. Shared clock
selection maps to `tests/scripts/test_partial_clock_source_order.py` and the
existing clean-validation integration test. Archive restoration is also tested
by the existing parametrized N7 entry test. Pending rows remain visible, and
paired summaries use only issues complete across both versions and every rule.

The CI checkout excludes the6.2GiB `results/` dumps; all offline checks use saved
fixtures. This addresses the prior run34487637224 runner disk-exhaustion failure
without weakening test or render coverage. Remote CI is separate from local
acceptance; the frozen artifact directory holds final checks and Codex review.
