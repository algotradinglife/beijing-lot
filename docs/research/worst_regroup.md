# Worst-period seven-fixture regrouping

## Scope and controls

Fixed post-hoc diagnosis of the prior 23 paired worst JOINT issues, originally
selected from 939 issues. Missing score-grid issues 100105/101001 are not filled
with replacements. These failure-selected issues are not unseen validation;
no threshold fitting, historical calibration or prospective strategy is shipped.

Freeze original p/q, 1024 CNY per-issue budget cap, 2 CNY tickets, a single 0.65
payout multiplier, SP gate 1.3, target coverage 0.25, 256 CNY per-group cap and
shared seed 42501 with 256 worlds. Native cutoffs and implementation identities
remain bound; historical admission stays false. Labels are opened only after
all compared ticket plans freeze, except known labels used to select the window.

Original-group JOINT and third-excluded plans must exactly reproduce the prior
sealed BASE and ALL_DROP tickets. The third-excluded variant changes purchase
support, not estimated true probabilities. Original depths remain per group.

Reuse native Top2 search: ranked cyclic seven-fixture windows and one-leg swaps
of the highest-Top2-mass seven. Expansion keeps every original group, anchors the
four exact-union diversified Top2 groups, then alternates probability and model
expected-gross rankings, adding at most 24 selected fresh groups. Subsequent
additions overlap previously selected additions by at most four fixtures;
anchors and original groups themselves do not share that guarantee. Duplicate
original/fresh memberships are not added twice. Search is bounded, not exhaustive.

Nine original arms: OLD_JOINT, OLD_DROP, OLD_TOP2, EXP_JOINT, EXP_DROP, EXP_DROP_EV,
EXP_TOP2, TOP2_PROB and TOP2_DIVERSE. OLD/EXP use original/expanded membership.
The last two use the complete fresh Top2 search universe. Full Top2 buys 128
states per group and exact-union diversified selection; native JOINT uses its
existing coverage-depth admission and simulated marginal union selection.
Consequently, comparisons across support methods change admission and allocation
as well; only OLD versus EXP within a fixed method isolates bounded expansion.
EXP_DROP_EV changes ranking to estimated net per added CNY; it is not a gate
requiring positive estimated return.

## Attribution and implementation

Separate SP eligibility, original 25%-coverage/256-CNY option admission, full Top2
support, actual available purchase depth, and funded choices. The initial review
identified that core option admission must not be treated as candidate absence;
this was corrected before acceptance, with regression assertions. A subsequent
summary-column shadowing bug was caught by independent replay; the period-stage
summary now lives in a regression-tested function and all 23 stages replay exactly.

An actual winner inside an unbought candidate is an oracle diagnostic, not a
claim that its identity was observable before kickoff or affordable together
with all other candidate winners. No match collection, cleaning, expert training
or global production probability was changed.

Entry: quarto/247_worst_regroup.qmd; config/worst_regroup.json.
Functions: r/worst_regroup.R; tests/testthat/test-worst-regroup.R.
Independent replay: scripts/check_worst_regroup.R, reusing the direct ticket
settlement checker and independently checking candidates, controls, strict Top2
support, ranks, stage assignment and imported Python implementation closure.

The QMD contains all issue ledgers, group evidence, candidate/depth/funding
classification, ROI, largest-winning-period removal, and directly shareable plots.
No chronological drawdown is inferred from the discontinuous selected window.

## Removal of the 25% admission gate

At the user's direction, OLD_OPEN_DROP and EXP_OPEN_DROP add two controls.
25% remains a desired raw-probability depth, capped at 128 tickets; failing to
reach it no longer excludes a group. SP>=1.3, original p/q, strict Top2 support,
1024 total budget and the allocator remain unchanged. Independent replay verifies
that previously admitted options retain their exact state IDs and costs.
Current Python implementation closure is checked against the parent before the
run and again before freeze; the receipt records the current verified closure.

## Results and conclusion

18 issues missed by OLD_DROP decompose into 11 admission-gate rejections,
2 available winner options not funded, 4 gaps in original candidate membership,
and 1 with no Top2 winner in the bounded search. None of these 18 is exclusively
an admitted-group-underdepth case. Reachability is hindsight, not a decision rule.

| Arm | Hit issues | Profitable issues | Stake CNY | Gross CNY | Net CNY | ROI |
|---|---:|---:|---:|---:|---:|---:|
| EXP_DROP | 8 | 6 | 21874.00 | 15210.99 | -6663.01 | -30.46% |
| EXP_DROP_EV | 5 | 4 | 22262.00 | 15327.45 | -6934.55 | -31.15% |
| EXP_JOINT | 3 | 1 | 22046.00 | 3184.59 | -18861.41 | -85.55% |
| EXP_OPEN_DROP | 7 | 6 | 22216.00 | 12327.56 | -9888.44 | -44.51% |
| EXP_TOP2 | 9 | 8 | 23552.00 | 16646.82 | -6905.18 | -29.32% |
| OLD_DROP | 5 | 3 | 22840.00 | 27203.94 | 4363.94 | 19.11% |
| OLD_JOINT | 0 | 0 | 23514.00 | 0.00 | -23514.00 | -100.00% |
| OLD_OPEN_DROP | 6 | 4 | 21974.00 | 10434.54 | -11539.46 | -52.51% |
| OLD_TOP2 | 11 | 5 | 23552.00 | 22055.05 | -1496.95 | -6.36% |
| TOP2_DIVERSE | 9 | 8 | 23552.00 | 16646.82 | -6905.18 | -29.32% |
| TOP2_PROB | 7 | 6 | 23552.00 | 25972.27 | 2420.27 | 10.28% |

OLD_TOP2 has the most hit issues (11/23) but remains at -6.36% ROI. Only OLD_DROP
and fresh TOP2_PROB have positive sample net; all arms lose after removing their
own largest profitable issue. Simple expansion did not improve the same-method
net returns. Removing admission increases old-pool hit issues 5->6, but rescues
three and loses two; 120407 alone loses 14901.98 CNY payout through reallocation.
This is not evidence that the obsolete 25% gate must remain. It shows that removal
and expansion expose an allocation/coverage tradeoff, not automatic improvement.
The priority supported here is admission and allocation within existing groups,
not assuming the seven fixtures themselves are the principal cause. No incremental
predictive benefit of handicap divergence is established by this experiment.

## Acceptance evidence

- Targeted native/new R tests passed, including admission-versus-depth regression.
- Both allocation QMDs and the standalone conclusion QMD render from clean sessions.
- Independent replay verifies 103372 original/expanded-arm tickets and 22095
  additional open-admission tickets, candidate support, ranks, all diagnosis stages,
  unchanged controls, preserved pre-existing options, and implementation closure.
- Full repository tests were not rerun: this scoped comparison uses targeted tests
  mapped to all new functions and their reused allocation/settlement dependencies.
- Rejected/interrupted v1/v2 intermediate outputs carry rejection records and
  are not promoted as accepted results.

Accepted data targets: audits/worst-regroup-v3 and audits/worst-regroup-open-v2.
Conclusion entry: quarto/249_worst_regroup_conclusion.qmd with
config/regroup_conclusion.json; rendered report reports/worst-regroup-conclusion-v1.
All outputs are post-hoc diagnostics; no production strategy or probability changed.

### Reproduction commands

Use the declared project Python in RETICULATE_PYTHON and FUNDAMENTALS_PYTHON,
repository root in PYTHONPATH, and project r_lib in R_LIBS_USER. Quarto renders
use QUARTO_R=/usr/local/bin, execution enabled and cache/freeze disabled in QMD.

```sh
Rscript -e 'testthat::test_dir("tests/testthat", filter="^(worst-regroup|regroup-open-pool|line-gap-third|top2-fresh-groups|joint-candidate-comparison)$", reporter="summary", stop_on_failure=TRUE)'
Rscript scripts/check_worst_regroup.R config/worst_regroup.json
Rscript scripts/check_regroup_open.R config/regroup_open.json
quarto render /run/media/drwho1985/Sandisk/data/beijing-lot/reports/worst-regroup-conclusion-v1/report.qmd -P config:"$PWD/config/regroup_conclusion.json"
```

Acceptance used standalone copies under external reports/ to avoid repository
website configuration. Allocation QMDs require a new versioned output directory,
never overwrite existing frozen evidence. The conclusion QMD is read-only over
its declared hash-bound receipts and can be rendered repeatedly.
