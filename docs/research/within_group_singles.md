# Rechoose two singles within fixed original groups

Keep current zero-handicap Top2-disagreement exclusion and the entire frozen
C000 non-converting group sequence. Remove unique-single cap. Each variant uses
exactly the same497groups,31808CNY stake across48issues,1024CNY/issue budget limit,
64CNY/group,2CNY unit, one ticket-level.65. Held cash unchanged, no score protection.
The existing U6/P5 group reuse is therefore unchanged by construction.

MARKET: for every fixture identify market favorite qTop1, rank seven fixtures
by that q, single the top two. VALUE: same favorite directions, rank by p/q
(baseline probability times estimated SP1/q), single top two.
Remaining five become baseline Top2 doubles. No q>=.5 or p/q-consensus eligibility
requirement on the new singles. Ties by slot and W,D,L. No third-outcome search.
VALUE is a per-leg return proxy, NOT maximum whole-ticket EV; no settlement price
enters the selection. q itself comes from Euro+OU score projection to handicap WDL.
Using q*(1/q) would be constant and cannot rank expected returns.

One new function: src/fundamentals_within_group_singles.py::reselect_group_singles.
Explicit plan/frame/cutoffs/policy/budget/unit/payout; checks input/seals/identities,
returns fresh sealed supports/tickets/choice ledger. No I/O, labels, fitting or
cache. Old roles recorded only as original_role; current support coverage/value
are recomputed. Tests map both policies to exact selection, stake/groups,
nonmutation, wrong policy/cutoff/label/seal errors.

Run:
```
python scripts/within_group_singles.py freeze --study NEW_STUDY
python scripts/within_group_singles.py settle --study NEW_STUDY
python scripts/check_within_group_singles.py --study NEW_STUDY
quarto render quarto/100_within_group_singles.qmd --execute-dir . --execute --no-cache -P study:NEW_STUDY
```
All144plans freeze before target settlement. The old source plan remains inventoried
group evidence; no current old-model replay claim. Raw source/input/plan hashes,
filter ledgers, native cutoff objects, transitive code and QMD bindings recorded.
Original groups settled again through same audited API. Independent checker
recomputes choices and Cartesian supports, verifies same slots/stake and cash,
and reconciles outcome/payoff without production settlement.
Historical clock proxies cannot authorize prospective/simultaneous ticket claims.
No new runtime dependency; existing declared config. QMD uses existing R report
functions. #419/#421 remain open; local review is not cross-year acceptance.

## Results (48 issues, identical497groups and31808CNY stake each)

| Metric | Original D2 | Market probability | Favorite p/q proxy |
|---|---:|---:|---:|
| Winning groups |55|53|39|
| Group hit rate |11.07%|10.66%|7.85%|
| Hit issues |19|19|17|
| Net CNY |24713.37|19467.70|7757.35|
| Stake ROI |77.70%|61.20%|24.39%|
| Budget ROI |50.28%|39.61%|15.78%|
| Max drawdown CNY |4416.06|4224.00|5731.00|
| Longest miss streak |7|9|6|

Neither fixed replacement improves return/hits on this exposed sample.
Market has slightly smaller absolute DD but lower net at identical exposure.
This does not test choosing any of3directions by p/q, nor optimizing whole-ticket
expected return; current VALUE restricts each fixture to its market favorite.

Checks: four function/archive tests passed; cutoff governance PASS; independent
checker verified144rows/1491groups. Live QMD executed successfully.
Archive render and Codex local technical review are required before delivery.

Final validation:
-4targeted tests passed, including portable archive restore and equal exposure.
-Independent checker passed144rows/1491groups.
-Live and archive QMD execution passed; tables3/144/30rows and2figures verified
 programmatically. No pixel inspection.
-Codex local technical review: no actionable defects; reviewer reran4tests and
 independent checker. QMD/CI inspected but not rerun by reviewer.
-Cutoff governance PASS. Remote CI/full repository suite not claimed run.
-Review is not prospective or issue acceptance;419/421 remain open.
Evidence: data/derived/fundamentals_417/within-group-singles-review.txt.
Archive: within-group-singles-archive-v1; actual study within-group-singles-v1.
