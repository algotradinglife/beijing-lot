# #407 execution ledger — incomplete

Live control plane: https://github.com/algotradinglife/beijing-lot/issues/407.
This ledger records evidence, not lifecycle or dependency state. The full census
and independent adjudication acceptance remain unfinished.

## Frozen diagnostic panel

`/tmp/bj407-census/panel.json` freezes 100 distinct provider candidates at
2026-09-05T10:30:45.494179+00:00: 35 from issue 25053, 35 from 25075 and
30 then-unstarted candidates from 26092. The complete source-native denominator
is 1082 rows. Eight requested competition strata are English League One/Two,
Dutch Eerste Divisie, Japanese J1/J2, Brazilian Serie A/B and MLS.

Selection uses explicit issue quotas, round-robin competition allocation and
stable SHA-256 ordering of issue/slot/provider ID. This is diagnostic sampling,
not learned fixture selection. Actual collection time is evaluated separately;
being upcoming when sampled does not prove every required payload arrived
before kickoff. Original and replay anomaly cases remain a separate panel.

## Source schema findings

- Titan and Nowscore historical arrays store match identity at different indexes:
  15 and 20 respectively. Offline fixtures test reconciliation by event ID.
- Recent Nowscore HTML references `/analysisJs/data{ID}.js`. Without the captured
  referenced asset, parsing must fail rather than report absent history.
- Season standings must be recognized by the exact standings column contract.
  Handicap-market tables are not standings, even where both contain a total row.
- Last-match lineups are not confirmed starting lineups for the target fixture.
- Original HTTP entity bytes and capture metadata are retained. UTF-8 decoding
  is explicit. JSON5 parses declared literals without executing source code.

## Independent evidence capture

Six official responses saved under `/tmp/bj407-census/official/`, with URL,
final URL, timestamps, HTTP status, original body, byte count and SHA-256.
These are evidence candidates, not six approved resolutions.

- Exeter's original club report separates regulation from extra time:
  https://www.exetercityfc.co.uk/news/2020/june/-match-report-exeter-city-3--colchester-united-1
- J.League's original rules-error announcement and restarted-match report:
  https://www.jleague.jp/news/article/22134/ and
  https://www.jleague.jp/news/article/23214/
- Urawa's own match result provides an agreement spot-check candidate and
  distinguishes actual 16:03 kickoff from a scheduled 16:00 timestamp:
  https://www.urawa-reds.co.jp/en/topteamtopics/226988/
- San Diego's original club report is a second agreement spot-check candidate:
  https://www.sandiegofc.com/news/match-recap-san-diego-fc-secures-third-straight-win-with-2-0-victory-over-colorado-rapids
- KNVB's replay URL returned HTTP 200 with maintenance content. It cannot resolve
  a conflict until substantive original content is available:
  https://www.knvb.nl/nieuws/betaald-voetbal/jupiler-league/39427/wedstrijd-fc-oss-jong-az-wordt-overgespeeld

First-party narrative is the evidence assessed here. Embedded statistics on an
official site do not automatically have an independent upstream feed. Historical
captures remain diagnostic historical proxies; no settlement or feature is admitted.

## Verification so far

- `.venv/bin/python -m pytest tests/test_fundamentals_census.py -q`: 30 passed.
  Covers all ten census functions, real inline/external source schemas, receipt
  failures, identifiers/null/zero, literal safety, conflict preservation,
  deterministic sampling/replay, immutable output and publish rollback.
  Integration and boundary coverage still needs extension before acceptance.
- `Rscript tests/testthat.R`: passed with external database access. The initial
  sandbox run failed an existing hard-coded external settlement database test;
  this is a reproducibility debt in `test-mapping-engine.R`, not a census result.
- `.venv/bin/python scripts/check_cutoff_governance.py`: PASS.
- Quarto 1.10.18 clean fixture render: passed with explicit input_dir, execution
  enabled, cache/freeze disabled and errors fatal. The sandbox Dart theme
  compilation failed; the identical authorized normal-environment command passed.
  Full-corpus rendering and visual inspection remain outstanding. Render and
  project functions do not install dependencies.

## Remaining acceptance

Both 100-document source batches are complete. The remaining 99 declared
external assets are being captured by live execution cell 67; one was already saved.
Complete the assets;
inspect field denominators and actual differences; complete the separate
regression panel, competition evidence registry and versioned adjudication
records; save durable raw receipts and bind sampling/asset provenance; finish
helper governance inventory, CI and reproducible runtime declarations; render
and visually inspect the full report; independently replay the final corpus;
then perform PI review against the live issue before any closure.

## Revision after full-population replay

The original 100 pairs and 100 referenced Nowscore JS assets completed. Full
v1 output is `/tmp/bj407-full-v1`; it is diagnostic evidence of a discovered
parser error, not the accepted sample release. Nowscore row `name` is a lottery
calendar grouping, so concatenating it with the hidden clock shifted 58 selected
kickoffs one day early. The corrected adapter preserves the grouping and clock,
anchors to the explicit sale-deadline calendar date, advances the clock only
when before that deadline, and labels this as diagnostic reconstruction. It is
checked separately against analysis identity and does not prove actual kickoff.

The original frozen files are untouched. `/tmp/bj407-census-v2/` contains a revised
100-row panel with the same 35/35/30 quotas, 1082-row denominator, and
`sampling-revision.json` binding old/new hashes and actual revision time. Five
members changed. Existing raw files are reused without mutation; the five new
pairs are being acquired. Four selected roster/analysis clock differences remain
for independent investigation: 2741446, 2741602, 2741604 and 2741612.

`/tmp/bj407-regression/` separately holds fresh source-native identities for
20064/293 (1870517), 22041/247 (2148390), and 161103/91 (1326813), with original
rosters and full denominators. The two additional regression pairs and the five
new main-panel pairs run in execution cell 108; referenced auxiliary scripts
must still be enumerated from these captured documents and acquired if present.

Eight official competition registry entries and actual access receipts are in
`/tmp/bj407-census/official-registry.json` and `official/`. CBF A/B probes failed
DNS and remain explicit transport failures; KNVB replay returned maintenance
content. Two independently corroborated agreement checks bind source history
rows, official original-club raw evidence, reviewer, rationale and version in
`agreement-spotchecks.v1.json`. Their checked facts alone are corroborated; no
prospective or lottery admission follows.

Helper inventory: `docs/research/fundamentals_helper_governance_407.md`.
Added portable offline CI, runtime declarations, thin CLI and real-roster date
regression. Final full-corpus tests, replay, publication, visual QA and native
Issue Graph review/closure remain outstanding.

## Final corpus verification (2026-09-05, ongoing acceptance)

- Revision supplement capture and required JS completed. No acquisition loop is
  running. The revised main corpus parses 200/200 documents; three separate
  regression fixtures parse 6/6 documents after supporting the labelled visible
  kickoff in the archived 2016 Nowscore profile.
- Final parser also recognizes Titan future-schedule `时间` headers and separate
  previous-match appearance tables. Injury player links are not lineup rows.
- Main findings: 4093 history membership/depth differences, eight roster/analysis
  timestamp observations across four fixtures, no same-ID historical goal or
  standings-total value conflict in this bounded panel.
- Seven versioned original-source review cases are saved. Three ten-minute
  advertised/possibly-actual clock distinctions remain unresolved; Houston/LA
  Galaxy and Yamagata/Okayama show reschedule/restart instance risk. Original
  FIFA replay order and Exeter regulation/extra-time narrative supply separate
  regression evidence. Two agreement spot-checks are also preserved.
- `.venv/bin/python -m pytest tests/test_fundamentals_census.py tests/test_nowscore_settlement.py -q`:
  **62 passed**. `Rscript tests/testthat.R` passed with authorized existing external
  DB access. Cutoff governance PASS. A later R-only correction distinguishes
  textual roster status from integer HTTP status; its targeted tests pass and
  full R suite must be rerun after this final change.
- `/tmp/bj407-release-main` and `/tmp/bj407-release-regression` are Python outputs
  from frozen final Python code. Fresh independent subprocess replay to
  `/tmp/bj407-replay-main` and `/tmp/bj407-replay-regression` matched the **complete
  receipts and every CSV hash**. `/tmp/bj407-replay-verification.json` records PASS.
- Durable bundle staged at
  `data/derived/fundamentals_census/20260905_full/`: `raw_main`, `raw_regression`,
  `main`, `regression`, `official`, review/registry JSON, old sampling version and
  code snapshots. It is not sealed yet. Refresh copied R code after its last fix,
  add successful rendered report, tests/replay evidence, documents and a complete
  file hash manifest, then verify hashes.
- Complete Quarto render is running as exec session **59603**. Earlier complete
  render failed on `panel.status` coercion; do not use the old fixture HTML as
  full-panel acceptance. After render succeeds, inspect actual tables and visual
  layout via Chrome, then perform live #407 requirement-by-requirement PI review.

The `final-main`/`final-regression` and v1/v2 provisional directories under `/tmp`
precede the last parser fixes; use only `release-main`/`release-regression` for
final Python output. No issue was closed, no PR merged, no settlement changed.
