# Mainstream-only singles: league and fundamentals diagnosis

User-defined competitions: 英超/西甲/德甲/意甲/法甲/葡超/荷甲, exact match.
Exclude cups, European club cups and 荷甲附 regardless of teams. Only A singles
restricted; D/C doubles may come from any retained competition. Original p/q
probabilities, shared favorite q>=.5, ranking qTop1/qTop2/pTop2, N7 2A4D1C,
U3/U6 P5, zero-handicap Top2 disagreement exclusion unchanged. Reassemble from
full candidate pool, first disjoint then reuse; no eligible anchors means cash.
Not just dropping original groups. No automatic change to default.

48exposed issues100402–100607,1024CNY wallet,64/group,2CNY unit,
one ticket-level.65, initial100000. No experts/conversions/score protection.
192plans frozen before settlement. Original support/role/cash replayed exactly.
Feature-only inventory exported from prior diagnostic evidence, no audit labels
passed to selection; parent bytes, feature snapshot, factors and plans bound.
Shared Cutoffs and utc used: all2561feature clocks strictly precede decisions
by60–6060seconds. These remain historical proxies, not prospective availability.
First v1 freeze asserted equality incorrectly and stopped before plans/frozen
receipt; v2 uses strict-before requirement. No raw source data were corrected.

## Original single hit rates: league evidence

Unique issue/slot/provider/support, not repeated holdings:
- U3 mainstream22/39=56.41%, other98/167=58.68%.
- U6 mainstream23/40=57.50%, other103/176=58.52%.
Mainstream singles span16issues. U3/U6 overlap heavily, not independent evidence.
Observed rates do not establish that non-mainstream competitions are the cause
of missed issues. League cells are small: U3 日职乙2/7,法乙2/6,德甲2/5,法甲2/5;
do not blacklist leagues from these post-hoc cells.

Other original U3 unique-single strata:
|Giving-side venue PPG advantage|Matches|Hits|Rate|Baseline predicted|Market predicted|
|---|---:|---:|---:|---:|---:|
|Below0|22|14|63.64%|72.1%|52.7%|
|0to<.5|43|20|46.51%|64.3%|52.0%|
|.5to<1|59|35|59.32%|63.8%|53.7%|
|At least1|76|49|64.47%|62.0%|54.1%|

Six zero-handicap singles are outside this PPG partition,2hits.
giving_venue_ppg means giving team minus receiving team recent venue PPG,
not one team's own points and not necessarily the chosen side's advantage.
The relationship is not monotone; especially weak0–.5cell warrants diagnosis,
not a fitted causal gate. U6 corresponding21/45=46.67%, overlapping sample.
Absolute handicap strata U3:0 2/6,1 51/93,>=2 67/107; large handicap is not the
lowest realized single hit stratum, despite baseline overconfidence.
Total-goal model/market gap .5–1 U3:21/40=52.5% vs baseline66.0%; <.5 is94/160
=58.75%. Gap>=1 has only6matches and is not grounds for a routing rule.
Full leagues/strata and ALL versus missed-issue slices are in QMD104; never
use realized missed-issue membership as a pre-match feature.

## Fixed whitelist backtest

|Policy|Stake CNY|Net CNY|Stake ROI|Hit issues|Groups/hits|Max DD CNY|
|---|---:|---:|---:|---:|---:|---:|
|U3 original|16960|19946.49|117.61%|19|265/35|2057.14|
|U3 mainstream|3008|4139.05|137.60%|6|47/13|704.00|
|U6 original|31808|24713.37|77.70%|19|497/55|4416.06|
|U6 mainstream|5760|3987.70|69.23%|6|90/19|2081.88|

Whitelist can bet11/48issues versus original45/48. It leaves46144/43392CNY cash.
U3 rescues0missed issues and loses13previous hits; U6 rescues1 and loses14.
After reassembly, selected unique singles improve: U3 23/36=63.89% versus
original120/206=58.25%; U6 24/38=63.16% versus126/216=58.33%.
Holding-weighted rates are64/94=68.09% and123/180=68.33%, versus313/530
=59.06% and592/994=59.56%. These are different selected populations/periods,
not a paired estimate of league quality. They differ from the original
mainstream subset rates above because group eligibility and selection change.
Only17.74%/18.11%of original stake deployed. U3 ROI rises, net falls79.25%;
lower drawdown is confounded by far lower exposure. No broad improvement or
reliable mainstream quality advantage established. U6 ex-largest-profit-issue
net is negative348.31CNY. The20-issue longest no-hit streak includes no-bet
issues and is not20consecutive losing bets.
The fixed whitelist is an optional low-activity experiment, not a replacement
for current default or a proved cure for weak singles.

## Interface and reproducibility

consensus_candidates/next_consensus_roles/independent_consensus_portfolio add
anchor_slots: None unrestricted, empty list no A, unique known integer list
restricts A only. D/C eligibility/objective unchanged. Parameters bind allowlist.
Invalid lists fail even at zero budget; native cutoff and no-label validation
unchanged. Tests exercise all paths and portable whitelist archive.
Existing category_diagnostics/missed_issue_diagnostics and financial R helpers
are reused; no new R functions, dependencies or chronology implementation.

```
python scripts/mainstream_singles.py prepare --study NEW_STUDY
python scripts/mainstream_singles.py freeze --study NEW_STUDY
python scripts/mainstream_singles.py settle --study NEW_STUDY
python scripts/check_mainstream_singles.py --study NEW_STUDY
quarto render quarto/104_mainstream_singles.qmd --execute-dir . --execute --no-cache -P study:NEW_STUDY
```
prepare creates immutable feature inventory in the study parent; run once per
parent, reuse existing inventory for subsequent studies without overwriting.
Actual study mainstream-singles-v2; fixture tests/fixtures/mainstream_singles.json.gz
is portable report evidence only. Independent checker validates192rows/899groups,
actual A leagues, complete Cartesian tickets, U/P, budget and payout; report
features/audit match their authenticated inputs.
No full-repository/remote CI/merge/lifecycle acceptance claimed;419 blocked421.

## Final validation

-26Python tests passed across allowlist, consensus, retention, N6/N7 and
 unique-single shared paths, including portable fixture restoration.
-Six reused R diagnostic/accounting test files passed, no failures.
-Independent replay192plans/899groups passed; cutoff governance PASS.
-Live and archive QMD fresh renders passed. Programmatic checks verified
 six tables(8,248,4,4,192,48rows), two figures and all8ALL-category denominators.
 No pixel-level inspection claimed.
-Codex bounded review: no actionable findings; reviewer reran16requested
 tests/checker, verified source/factor/archive equality and all2561prior clocks
 plus league sample counts. R/QMD executed by root, not reviewer.
-Review evidence data/derived/fundamentals_417/mainstream-singles-review.txt.
-Original default retained; no adoption, merge or issue closure.
