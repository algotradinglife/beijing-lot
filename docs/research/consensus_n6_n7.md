# N6 versus N7 under fixed consensus roles

Scope: 48 exposed issues100402–100607, not new validation. No expert,
conversion purchases or score protection. Exclude handicap0 with differing p/q
Top2 sets. 1024CNY/issue wallet,2CNY units, one ticket-level0.65, initial100000CNY.
N7 has2A/4D/1C; N6 has2A/3D/1C. A: agreed favorite q>=.5; D: agreed Top2;
C: differing Top2, purchased as baseline double. Scores remain qTop1/qTop2/pTop2.
Greedy per-group MILP, first disjoint then explicit U3/U6 and P5. P5 is an
absolute overlap cap, hence permits5/6 overlap for N6 versus5/7 for N7.
No forced spending; cash retained. Not global portfolio optimization.

All192plans frozen before target audit access. N7 both caps independently
regenerated and verified against prior plans for every slot/role/support,
group count, spend and cash. Metadata now records group_size; old packages
remain inventoried evidence. No new fitting or learned threshold. Cutoffs
come from src/temporal_learning; hashes bind source, transitive implementation,
parameters, report and audited-label pointer. Historical timestamp proxies do
not prove prospective or simultaneous-ticket availability. #419 remains
blocked by open #421; no lifecycle acceptance is implied.

## Results

|Policy|Groups/hits|Hit issues|Stake CNY|Net CNY|Stake ROI|Budget ROI|Max DD CNY|
|---|---:|---:|---:|---:|---:|---:|---:|
|N7 U3|265/35|19/48|16960|19946.49|117.61%|40.58%|2057.14|
|N6 U3|278/37|15/48|8896|3198.61|35.96%|6.51%|992.00|
|N7 U6|497/55|19/48|31808|24713.37|77.70%|50.28%|4416.06|
|N6 U6|565/72|17/48|18080|5290.39|29.26%|10.76%|3588.61|

Group hit rates N7/N6: U3 13.21%/13.31%, U6 11.07%/12.74%.
N6 buys modestly more groups, not twice as many, because role supply/reuse
limits still bind. Its lower absolute drawdown accompanies much lower exposure.
Higher group hit rate does not yield more hit issues or higher net/ROI.
Group construction is rerun at N6; this is not a nested removal of one leg from
each original group. No monotonic increase in realized issue hits is implied.
Both N6 variants remain profitable on this exposed sample but do not replace
N7 on return/issue-hit evidence. No new automatic strategy promotion.

## Interface and replay

Changed functions in src/fundamentals_consensus_portfolio.py:
- consensus_component: group_size=6/7, same Cartesian ticket/settlement contract.
- next_consensus_roles: exact2/(N-3)/1 roles and group-size overlap validation.
- independent_consensus_portfolio: explicit group_size,32/64CNY primary groups.
Existing consensus_portfolios remains N7; shared candidates/settlement unchanged.
Every changed function is exercised by tests/test_fundamentals_consensus_n6_n7.py
and existing consensus/unique-single tests. New tests cover sizes, both reuse
caps, deterministic choices, budget, infeasibility, forbidden labels/cutoffs,
wrong size, role maps, conversion quota plumbing and archived report restore.
No new dependencies or R functions. Reuse existing pure-report, missed-summary,
equity-curves R interfaces; their tests run separately.

Commands (project validation Python selected explicitly in execution):
```
python scripts/consensus_n6_n7.py freeze --study NEW_DIRECTORY
python scripts/consensus_n6_n7.py settle --study NEW_DIRECTORY
python scripts/check_consensus_n6_n7.py --study NEW_DIRECTORY
python -m pytest tests/test_fundamentals_consensus_portfolio.py tests/test_fundamentals_consensus_n6_n7.py tests/test_fundamentals_unique_single.py tests/test_fundamentals_candidate_exclusion.py -q
python scripts/check_cutoff_governance.py
quarto render quarto/101_consensus_n6_n7.qmd --execute-dir . --execute --no-cache -P study:NEW_DIRECTORY
```

Delivery study: data/derived/fundamentals_417/consensus-n6-n7-v2.
Portable fixture: tests/fixtures/consensus_n6_n7.json.gz (report evidence only).
QMD101 includes192period/policy rows, aggregate stake and budget ROI,
equity and absolute drawdown curves. Independent checker recomputes
Cartesian supports, identity/handicap, role eligibility, caps and all1605group
payoffs without the production settlement function.
Initial v1 was superseded by v2 for final documentation/hash bindings, with
unchanged rules and numerical results. No label-derived selection changes.

## Final validation

-25Python tests passed across consensus, N6/N7, unique-single and exclusion.
-R tests via Rscript/testthat::test_file: equity-curves25assertions,
 missed-summary6, pure-report6; zero failures/warnings/skips.
-Independent checker:192issue/policy rows,1605groups passed.
-Cutoff governance PASS.
-Fresh live and portable archive QMD executes passed; programmatically verified
 tables of4/192rows and2figures with no execution-error cells. No pixel inspection.
 An initial archive --output override failed Quarto resource resolution;
 rerunning the normal output path succeeded. No analysis code change required.
-Codex local review: no actionable findings; independently reran25tests,
 checker and governance. Reviewer did not rerender QMD.
-Remote CI and full-repository R/Python suites not run; checks target the affected
 Python functions and reused R reporting APIs in this shared worktree.
-No merge, issue closure or prospective acceptance. Issue419 remains blocked421.

Review evidence: data/derived/fundamentals_417/consensus-n6-n7-review.txt.
