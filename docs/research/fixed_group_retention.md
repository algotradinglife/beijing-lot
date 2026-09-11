# Fixed groups: retention probability source and weak singles

48exposed issues100402–100607. Reuse exact current U3(265groups) and U6(497groups)
original holdings. For each U keep7slots, order,2singles/5baseline doubles,
stake/cash, total reuse and pair overlap unchanged. Wallet1024CNY,64/group,
2CNY unit, one ticket-level.65, capital100000. No experts, score protection,
large-handicap projection changes, group rebuilding or new cutoff learning.
Zero-handicap differing-Top2 candidate exclusion retained.

New RETENTION_P/Q/MIX policies in reselect_group_singles. All candidates must
have shared p/q favorite and q>=.5. Rank common favorite mass divided by mass
on the same original baseline Top2 set under p, q or .5p+.5q. Do not change
second outcome when probability source changes. Original groups guarantee
at least2eligible candidates; otherwise raise instead of changing exposure.
Ties by slot, direction WDL. All other5supports remain baseline Top2.
This isolates probability-source ranking on current groups, not an exact
replay of the old pool/mixture experiment.

384plans freeze before audit access. Existing source plans are inventoried
evidence, source/cutoff/implementation/parameters/QMD/audit-pointer hashes bind
the result. No prospective/simultaneous-ticket availability claimed.
Source p is baseline score projection, q market Euro+OU score projection to
handicap WDL; neither is plain unadjusted Euro WDL.

## Portfolio results (CNY)

|U|Policy|Stake|Net|Stake ROI|Hit issues|Max DD|Rescued/lost|
|---|---|---:|---:|---:|---:|---:|---:|
|3|Original|16960|19946.49|117.61%|19|2057.14|0/0|
|3|P|16960|5947.23|35.07%|18|4472.77|3/4|
|3|Q|16960|16986.85|100.16%|19|1917.95|2/2|
|3|MIX|16960|8816.46|51.98%|19|2663.72|3/3|
|6|Original|31808|24713.37|77.70%|19|4416.06|0/0|
|6|P|31808|13097.05|41.18%|19|4009.29|4/4|
|6|Q|31808|20453.24|64.30%|19|4785.87|2/2|
|6|MIX|31808|16572.37|52.10%|20|3840.00|4/3|

No rule raises net. U3 Q has modestly smaller drawdown at equal exposure,
same hit issues and longest miss5vs7, but15%less net. U6 MIX adds one hit issue
and lower DD but sacrifices33%net. Retain current default; do not automatically
promote sample-specific alternatives.

## Single-probability diagnosis

Original U3:219/265groups(82.6%) have weaker market single in[50%,55%);
U6:407/497(81.9%). No original group has both market singles>=60%.
This is about frozen groups, not proof that whole issue pool lacks such pairs.
At least one baseline single below50%:64U3groups and124U6groups.

|Original|Mean weaker p|Mean weaker q|Mean p joint|Mean q joint|Both singles hit|
|---|---:|---:|---:|---:|---:|
|U3|57.9%|52.7%|41.1%|28.7%|87/265=32.8%|
|U6|58.1%|52.8%|41.5%|28.9%|161/497=32.4%|

P retention increases predicted p joint to45.1%/45.7%, but realized both-hit
falls to29.1%/28.6%. Higher p estimates did not improve outcomes in this sample.
These are holding-weighted descriptive counts, not independent observations
or a statistical test; issue/match/group overlaps prevent naive inference.

Q joint[.25,.30):194U3groups, both-hit29.9%;356U6groups,28.7%.
Q joint[.30,.35):65U3groups,40.0%;129U6groups,41.1%.
Highest observed bin[.35,.40) has only6/12groups across2issues:50%both-hit.
This supports further examination of joint probability but does not establish
a profitable gate. Complete-seven hit rates do not automatically follow
two-single rates; five doubles still matter.

R single_probability_diagnostics accepts settled leg table and explicit bin
breaks; returns group min/joint for P/Q/MIX and tidy bin counts/observed rates.
Joint multiplication assumes fixture independence. Min probability is a
stratifier, not expected both-hit probability. No thresholds fitted, no betting
gate introduced. No-bet issues remain financial rows and have no group metrics.

## Replay and tests

New R function in r/fundamentals_single_probability.R; all functions remain
outside QMD. Tests cover exact metrics, distinction between both/group hits,
[0,1]endpoint, malformed supports, normalization, missing/empty and duplicate.
Python tests cover all three retention ranks, nonmutation, fixed exposure,
eligibility failure, labels rejected, and portable archive restoration.
Existing MARKET/VALUE behavior remains tested.

```
python scripts/fixed_group_retention.py freeze --study NEW_DIRECTORY
python scripts/fixed_group_retention.py settle --study NEW_DIRECTORY
python scripts/check_fixed_group_retention.py --study NEW_DIRECTORY
python -m pytest tests/test_fundamentals_fixed_retention.py tests/test_fundamentals_within_group_singles.py -q
python scripts/check_cutoff_governance.py
quarto render quarto/103_fixed_group_retention.qmd --execute-dir . --execute --no-cache -P study:NEW_DIRECTORY
```

Study data/derived/fundamentals_417/fixed-group-retention-v1.
Fixture tests/fixtures/fixed_group_retention.json.gz is report-only.
Independent replay validates384rows/3048groups, unchanged identities/support
source probabilities/exposure, exact ranking and complete tickets, one payout,
and every exported diagnostic leg/label. No new dependencies.
QMD103 contains full per-issue ROI, rescue/loss, min/joint probability bins,
per-issue quality, equity/DD curves. Full unrelated repository suites and
remote CI not claimed; issue419 remains blocked by421, no closure/merge.

## Final validation

-9Python tests passed across new fixed-retention and existing within-group cases.
-New R diagnostic16assertions passed; all5affected/reused R test files passed.
-Independent checker384rows/3048groups passed, including exported diagnostic legs.
-Fresh live and portable archive QMD passed with cache/freeze disabled;
 programmatic inspection confirmed6tables(8,8,384,8,250,360rows),2figures,
 no error cells and all48policy/basis/metric denominators. No pixel claim.
-Cutoff governance PASS.
-Codex local review: no actionable findings; independently reran9Python tests
 and full checker. R/QMD execution performed by root, not repeated by reviewer.
-Evidence data/derived/fundamentals_417/fixed-group-retention-review.txt.
-No remote CI/full-repository pass, merge or lifecycle acceptance claimed.
