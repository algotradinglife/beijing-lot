# #407 helper and evidence-store inventory

This census performs acquisition, parsing, comparison and reporting only. It
calls no historical fit, tune, recency weight, imputation, normalization, model
gate, ticket selection or historical cache function. Its explicit sampling time
freezes a diagnostic population; it is not a decision-facing cutoff.

| Component | Actual use / finding | Census decision |
| --- | --- | --- |
| `src/nowscore_settlement.py:parse_page` | Validates selected native issue/play, row identities and UTF-8; calls `source_url`, uses shared play labels. | Reuse for source-native rosters only; no settlement database writes or corrections. |
| `src/nowscore_bjdc_sp_history.py:TYPEID_LABELS` | Transitive imported constant; module imports `HKT` from `src/multimarket_p0.py`. | Bind both imported files in implementation receipt; no history/settlement/learning functions invoked. |
| `scripts/scrape_nowscore_match_details.py:js_array` | Returns `[]` for absent, malformed or unsupported JS data, collapsing parser failure into empty data. `safe_float`/`safe_int` similarly coerce failure; summaries truncate to fixed windows. | Do not reuse these parser/summary interfaces. New census uses JSON5 literals and explicit failure/absence. P0 must replace obsolete parsing on integration, without compatibility wrappers. |
| `src/titan_clean/fundamentals.py:parse_analysis_fundamentals` | UTF-8 replacement decoding; regex returns untyped text blocks; season tables use a 700-character slice. Docstring asserts pre-match snapshot availability without capture-bound proof. | Not used or considered a clean historical feature interface. Diagnostic parsing validates cells and records observed collection time. P0 must remove the obsolete production parser when its replacement passes acceptance. |
| `src/titan_clean/store.py` | Existing source-pure Titan append-only raw store, source identity and collection receipt contract. | Inventory only; do not write mixed-source audit evidence into its production lane. Census files are immutable diagnostic releases, not a second business settlement store. |
| `src/message_evidence/ledger.py` | Existing message attestation/ledger with its own timestamp/effective-cutoff methods. It serves a different evidence domain. | Not imported. Future decision-facing use requires shared `src/temporal_learning` audit, not copied chronology functions. |
| `r/bootstrap.R` | Existing environment setup can install packages. | Do not source it during report rendering; CI/setup installs declared versions first. |
| `tests/testthat/test-mapping-engine.R` | Existing integration test opens a hard-coded personal external database and conditionally skips if absent. | Reproducibility debt; full local run passes with authorized disk access, but offline census CI uses its own deterministic tests. This test does not prove portable settlement coverage. |
| `quarto/score_conflict_review_pending.md` | Historical mixed-source proposed corrections and replay links. | Discovery leads only. Source-native roster identity and original official evidence are captured afresh; no values imported into settlement. |
| `src/temporal_learning/` | Authoritative chronology, availability, partitions, recency weights, ESS, cache keys, receipts and replay for future learned clients. | Required for later learned features. No learned client is implemented or admitted by #407. |

## New function/test mapping

`tests/test_fundamentals_census.py` exercises `canonical`, `read_response`,
`roster_records`, `select_panel`, `js_value`, `plain_text`, `analysis_record`,
`compare_pair`, `write_rows`, and `build_outputs`. Saved source fixtures cover
both source array layouts, correct standings vs market tables, and required
external JS. Tests assert null/zero/identifier preservation, failures, conflict
immutability, deterministic replay, hashes, availability across timezone
representations, no overwrite and publication rollback. CLI subprocess tests
exercise fixture materialization and the thin replay command.

`tests/testthat/test-fundamentals-census.R` exercises all four R functions:
`read_fundamentals_census`, `summarize_fundamentals_coverage`, and
`summarize_fundamentals_access`, and `read_fundamentals_review`. It covers hash tampering, typed UTC values,
leading-zero IDs, missing/zero values, empty findings and failed-response
coverage denominators. The QMD defines no reusable functions.

CI configuration is `.github/workflows/fundamentals-census.yml`. Runtime and
direct versions are in `config/fundamentals_census_runtime.json`; Python JSON5 is
also pinned in project `requirements.txt`. The workflow must run against a
published change before any claim of remote CI success.

## Remediation routing

The live graph already places production dual-source collection and independent
adjudication in #408, blocked by #407. The parser replacement and future feature
admission gaps above are explicit inputs to that existing work, not permission
to reuse unsafe helpers. Native graph state remains authoritative; this table
neither creates dependencies nor changes statuses. No project-wide claim of
all existing functions being tested is made by the census tests.
