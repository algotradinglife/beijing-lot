# Nowscore-only settlement reconstruction (#405)

Owner authorized the source-contract replacement on 2026-09-05. The live issue
contract was updated and read back; parent, Project and native relationships
were not changed. The task remains In Progress.

## Scope and boundaries

The new entry point is `scripts/rebuild_nowscore_settlement.py`; the parser and
deterministic audit live in `src/nowscore_settlement.py`. They do not load 500,
Titan databases, mixed-source tables, or the old correction/void ledgers.
Existing old data and programs are historical evidence, not dependencies of
this entry point. No services have been disabled and no old data removed.

This first release covers 12 explicitly selected diagnostic issues, not the
complete historical universe. The regression scope includes previously discussed
issues and a recent issue; it does not define an unbiased error-rate sample.
Historical expansion must obtain its issue inventory from Nowscore, not 500.

## Run

From the repository root, choose a **new** run directory:

```sh
.venv/bin/python scripts/rebuild_nowscore_settlement.py capture \
  --run-root data/derived/nowscore_only/20260905_pilot \
  --issues 130408,130509,130511,140706,141112,150903,23054,23093,24051,25033,25053,26082

.venv/bin/python scripts/rebuild_nowscore_settlement.py build \
  --run-root data/derived/nowscore_only/20260905_pilot \
  --output data/derived/nowscore_only/20260905_pilot/final.sqlite

# Independent offline replay: output must not already exist.
.venv/bin/python scripts/rebuild_nowscore_settlement.py build \
  --run-root data/derived/nowscore_only/20260905_pilot \
  --output data/derived/nowscore_only/20260905_pilot/replay.sqlite

# After explicit user approval only: preserve raw data and add derived views.
.venv/bin/python scripts/apply_nowscore_bf_derivations.py \
  --source-db data/derived/nowscore_only/20260905_pilot/final.sqlite \
  --approved-verification data/derived/nowscore_only/20260905_bf_history/verification.json \
  --output data/derived/nowscore_only/20260905_pilot/approved.sqlite

quarto render quarto/05_nowscore_internal_audit.qmd
```

The declared Quarto parameter `-P audit_db:path/to/snapshot.sqlite` selects the input. Preview performs
read-only queries, no network calls, and no corrections. Explicit render executes
the report. A capture run refuses an existing directory; a build refuses an
existing database. To retry a failed capture, use a new explicit run directory.
Interrupted capture logs and raw bytes are retained but an unsealed manifest
cannot be built. There is deliberately no silent resume/overwrite behavior.

The current QMD reads `pilot_closed.sqlite` and its effective views. The immutable
`final.sqlite` remains the raw diagnostic input, not the current report input.
The approval sidecar `approved.decisions.json` is local-only. Rebuild another
approved copy using `--ledger` with that exact sidecar, rather than regenerating
approval for different data. Raw `option_sp.sp` is never changed; consumers of
this explicitly approved layer use `effective_option_sp.effective_sp` and keep
its decision ID and evidence class. Original findings remain in `finding`;
only resolved, approved missing-option flags are excluded from `effective_finding`.
This does not switch production or backtest consumers.

The manual layer is reproduced from `approved.sqlite` with:

```sh
.venv/bin/python scripts/apply_nowscore_manual_all_one.py \
  --source-db data/derived/nowscore_only/20260905_pilot/approved.sqlite \
  --output data/derived/nowscore_only/20260905_pilot/manual_reviewed_six.sqlite \
  --target 23054:335 --target 24051:90 --target 25033:221 \
  --target 130408:82 --target 130511:3 --target 141112:49 \
  --reviewed-at 2026-09-05T18:47:33+08:00
```

Only these explicit user-confirmed targets are admitted. The first three fill
empty options; the latter three overlay reference vectors with settlement SP=1,
requiring consistent abnormal status, absent scores and BF summary SP=1.
Original status and reference values remain intact. No refund attribute is added;
the later strategy settlement code handles status plus SP. The receipt records
manual evidence, source/implementation hashes and no verified official notice.
The previous `manual_all_one.sqlite` snapshot is retained unchanged.

History-supported completion adds 26082/23 (负其他, 56.7144) and 26082/39
(胜其他, 9.4130). Replay the saved raw history pages, requiring their hashes,
latest unique winning option, score agreement, rounded SP agreement and no
conflicting single-option history. Keep the four-decimal roster settlement SP.
The new evidence class is `history_supported_score_summary_derivation`.

```sh
.venv/bin/python scripts/apply_nowscore_bf_derivations.py \
  --source-db data/derived/nowscore_only/20260905_pilot/final.sqlite \
  --approved-verification data/derived/nowscore_only/20260905_bf_history/verification.json \
  --history-root data/derived/nowscore_only/20260905_bf_history \
  --output data/derived/nowscore_only/20260905_pilot/approved_history.sqlite
```

Then replay the six manual targets above using `approved_history.sqlite` as
source and `history_completed.sqlite` as output. Existing snapshots are retained.
For ledger replay, `--history-root` remains mandatory for history-backed decisions.
Reusable BF application functions now live in `src/nowscore_bf_derivations.py`;
the script is only a command entry point. The report lists the remaining nine
abnormal-status matches, including 130408/151 with seven BF and one BQ raw zero
cells. Their reference SPs are not changed by this completion step.

## Pilot closure before historical expansion

The owner authorized closure of the remaining diagnostic sample, not historical
expansion or production switching. All previous snapshots remain immutable.
Reproduce the current input with:

```sh
.venv/bin/python scripts/apply_nowscore_manual_all_one.py \
  --source-db data/derived/nowscore_only/20260905_pilot/approved_history.sqlite \
  --output data/derived/nowscore_only/20260905_pilot/pilot_closed.sqlite \
  --target 23054:335 --target 24051:90 --target 25033:221 \
  --target 130408:82 --target 130511:3 --target 141112:49 \
  --target 130408:151 --target 130509:138 --target 130509:142 \
  --target 130511:80 --target 140706:115 --target 150903:57 \
  --target 150903:71 --target 150903:381 --target 23054:140 \
  --zero-target 130408:151 --reviewed-at 2026-09-05T22:26:06+08:00
quarto render quarto/05_nowscore_internal_audit.qmd --execute --no-cache
```

130408/151's seven BF and one BQ original `0.00` cells were reproduced from
hash-checked saved HTML. This proves source origin, not a placeholder meaning.
The explicit manual exception uses cross-play postponed status, absent scores
and BF summary SP=1; all 49 settlement options become 1. No automatic zero-to-one
conversion is introduced. `manual_all_one.original_raw_sp` distinguishes these
zeros from truly empty cells; the source parsed NULL and original bytes remain.

Five source-observed full-domain all-one matches (24051/377, 25033/362,
25033/397, 25053/250, 25053/442) are validated across all five plays and stored
as `special_settlement_notice`, separate from actionable `effective_finding`.
Conflicting or incomplete all-one records remain findings. Neither manual
decisions nor notices claim official announcement verification or a refund flag.

Final sample: 3,207 matches, 16,035 play observations, 157,143 option cells;
130 BF derivations; 15 manual fixtures / 735 effective all-one cells (132 empty
cells filled, 580 reference SPs replaced, 8 original zeros reviewed, 15 already
one). Five additional source all-one fixtures are notices, totaling 20 special
fixtures. All original 232 audit flags remain; actionable settlement flags = 0.
All ordinary observations were checked for exact option domains and one
score-consistent winning SP > 1; all special fixtures have 49 effective SP=1.
Raw tables, prior BF decisions and previous manual values are unchanged.
Independent replay produced identical persisted receipts, decisions and views.

Function/test mapping: `special_notices`, `prepare_decisions`,
`persist_decisions`, `apply_decisions`, and the manual CLI are covered by
`tests/test_nowscore_manual_all_one.py`, including explicit zero authorization,
conflict rejection, rollback, repeat refusal, replay, notice separation and a
clean synthetic QMD render. `read_nowscore_audit` is covered by
`tests/testthat/test-nowscore-audit.R`. BF derivation/history functions retain
their corresponding Python regression suites. R/Python/Quarto setup is declared
in `config/nowscore_settlement_runtime.json` and `requirements.txt`.
`.github/workflows/nowscore-settlement.yml` runs offline synthetic tests and a
clean report without private captures. Remote CI has not been dispatched.

Local acceptance commands:

```sh
QUARTO_BIN=/usr/lib/rstudio-server/bin/quarto/bin/quarto .venv/bin/python -m pytest -q tests/test_nowscore_bf_derivations.py tests/test_nowscore_manual_all_one.py tests/test_nowscore_settlement.py tests/test_verify_nowscore_bf_history.py tests/scripts/test_nowscore_bjdc_sp_history.py
Rscript -e 'testthat::test_file("tests/testthat/test-nowscore-audit.R", stop_on_failure=TRUE)'
.venv/bin/python scripts/check_cutoff_governance.py
```

The full `Rscript tests/testthat.R` run encountered two unrelated existing
`test-mapping-regression.R` errors (unsupported `fetch_raw` arguments and
`exact-remap targets collide`). Nowscore-specific R checks and real/synthetic
report renders pass; the repository-wide R suite is not claimed as passing.
No unrelated mapping code was changed. Issue #405 remains In Progress for the
future historical expansion; no private data or local audit details were posted.
Final local results: 75 Python tests passed (including synthetic clean render),
8 Nowscore R assertions passed, cutoff governance passed, affected Python lint
and `git diff --check` passed. Real report inspection verified 735 manual-option
rows, 8 original-zero rows, 5 source special notices and 0 actionable findings.

The owner accepted score-derived other outcomes with Nowscore summary settlement
SP for the reviewed empty-history targets. Empty history is therefore not a
blocker for this approved scope, but neither proves a storage cause nor historical
pre-match availability. The earlier no-synthesis rule describes raw parsing;
the separate user-confirmed derivation layer is the explicit exception, not an
automatic fallback for all missing data or future issues.

## Evidence and interpretation

- Preserve original bytes by SHA256, request URL, successful receipt time and
  failed-request entries. The manifest covers every requested issue × five plays.
- Validate selected issue, play title, native team/match IDs, per-row SP links,
  and embedded JavaScript roster against the visible `all=1` roster.
- Preserve 3 SPF, 8 total-goal, 4 upper/lower odd/even, 25 correct-score and
  9 half/full-time cells per fixture when their domains are valid. Empty is not
  zero. Correct-score cells are mapped by displayed labels, not numeric IDs.
- Audit sporting scores, missing/invalid fields, source status, SP shapes and
  cross-play identity/score/status/schedule/handicap differences. Preserve all
  observations, including duplicates; flag rather than silently deduplicate.
- Full-domain all-one is special-settlement **evidence**, not an official void
  notice. One SP=1, a score or an abnormal status alone cannot authorize a refund.
  Nonfinished multi-cell vectors are not treated as unique winning payouts.
- Retain the correct-score row-level summary SP separately. If the source's
  entire option grid is blank but the summary exists, flag
  `summary_sp_without_option`; do not synthesize an option payout from the score.
- No automatic correction or payout computation. Findings are review flags,
  not all proven source errors. Passing the checks does not certify an official
  settlement. The database has no production-approved settlement view.
- Compare both `data_sha256` and `audit_sha256`, and the complete receipt, between
  independent builds. Receipt binds manifest, parser and imported implementation
  hashes and runtime versions; SQLite stores raw vectors and observation JSON.

Chronology evidence class is `HISTORICAL_PROXY`: a page fetched now does not prove
availability before the historical match. No historical learning, fitting or
selection functions are invoked. Prospective or model-facing use remains outside
this diagnostic interface and must use the shared temporal-learning library.

## Remaining work

Establish a source-native historical issue inventory and coverage denominator,
expand capture with an explicit year/issue scope, investigate the resulting
Nowscore-only findings, then explicitly verify downstream consumers before
switching production/backtest inputs. Do not describe this pilot as a completed
whole-history or production migration.

## First diagnostic result (2026-09-05)

The sealed 60-page sample parsed without page failures: 12 issues, 3,207
issue/slot fixtures, 16,035 fixture/play observations and 157,143 option cells.
There were no unique-option/score mismatches or cross-play conflicts in this
sample. There were 232 review flags affecting 150 fixtures:

| Flag | Fixture/play flags | Distinct fixtures |
| --- | ---: | ---: |
| Summary SP exists but correct-score option grid is empty | 130 | 130 |
| Abnormal status, not a full-domain all-one vector | 60 | 12 |
| Full-domain all-one vector | 25 | 5 |
| Single option SP=1 | 15 | 3 |
| Invalid SP (raw zero retained; overlaps abnormal-status group) | 2 | 1 |

The 130 missing option grids all correspond to score-derived `胜其他`,
`平其他` or `负其他`. This is a source presentation discrepancy, not permission
to synthesize payouts. Example: 130408/104 displays 5-2 and summary SP 43.3629
but its 25-cell grid is empty. 130408/151 has raw SP 0.00 cells in BF and BQ
reference vectors and remains postponed.

28 Python tests, lint, 57 legacy R assertions and SQLite integrity checks passed.
Independent offline rebuild compared every table, including the entire receipt,
exactly. Final artifact: `data/derived/nowscore_only/20260905_pilot/final.sqlite`.
The `data` symlink resolves to the existing external runtime tree; it is not the
old Sandisk 500 database. The earlier `audit.sqlite` is an intermediate diagnostic
build, not the report input.

- Manifest SHA256: `3a83c2d4a73717f7b93b471b27dc609bdea51d0f27c82d29f3a84415952ec5f8`
- Parsed data SHA256: `1743e3c25e0cb2a1c8898a38b0c4336959e6df4cf7502c72565807d17b721723`
- Audit SHA256: `1d0eef39201a2744c37b0a0e0e0dd09af8099b843028824987420b6332280e9a`
