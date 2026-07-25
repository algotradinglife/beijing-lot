# SP-CONSISTENCY-001A — score distribution vs handicap 3/1/0

Status: `g0_r4_frozen_insufficient_strict_data; no_formal_result`

This is a Phase 1 market-information experiment, not a betting or portfolio study. It may not create tickets, stakes, expected-value filters, ROI claims, release authority, or frontend/API choices.

## Questions and hypotheses

RQ1 asks whether a complete score distribution, mechanically mapped to Beijing handicap 3/1/0 at the same decision time, differs from de-vigged p34 probabilities in a stable way. RQ2 asks whether the score-derived vector adds chronological-holdout predictive information beyond p34 SP alone.

The default conclusion is `insufficient_or_no_incremental_evidence`. Any discrepancy can be a timestamp, overround, incomplete-tail, mapping, or sampling artifact; the experiment does not assign causal meaning or claim an advantage.

## Preregistered gates

G0 is outcome-blind and must be frozen first. It requires at least 200 strict paired match-markets across at least 8 issue blocks. A strict pair has complete p34 and score vectors, one identical declared decision time, `source_observed_at <= fetched_at <= decision_at < kickoff_at`, and immutable raw provenance. Legacy/static rows, terminal or winning SP, post-kickoff records, unclocked historical cards, and cross-clock joins are excluded.

G1 maps `P(home_goals, away_goals)` to 3/1/0 using `home_goals + handicap - away_goals`. It is tested for positive, zero, and negative integer handicaps. G2 never renormalizes a finite Poisson grid: omitted mass becomes a deterministic bound. p42 other-score categories are point-mappable only when their goal-difference category is sufficient for the particular handicap; otherwise they remain bounded or ineligible.

Only after frozen G0–G2 approval may the experiment inspect settled outcomes.

## Predeclared formal analysis, if authorised

The p34 baseline B0 is proportional inverse-SP de-vigging. B1 is one score-derived 3/1/0 vector, reported separately for strict p42 market data and strict William Hill 1X2/O/U independent-Poisson inputs. B2 is `alpha * B0 + (1-alpha) * B1`; `alpha` is selected only by issue-block cross-validation from `{0.00, 0.25, 0.50, 0.75, 1.00}` on the training issues.

Eligible issue IDs are sorted chronologically. The earliest 70% are training/calibration blocks and the final 30% are untouched holdout blocks. The primary metric is multiclass log loss; multiclass Brier score is secondary. The primary B2-minus-B0 holdout delta receives a 95% whole-issue bootstrap interval. Any additional predeclared strata use Holm correction. No test outcome may choose a blend, threshold, horizon, tail treatment, or sample boundary.

## G0 revision R4

The original local-only G0 package is not cited as evidence: it did not bind every result-affecting input atomically and was not published durably. It remains untouched on the originating machine but is superseded, not repaired or overwritten.

The R2 package remains available but is superseded for PI evidence review: its p34 export did not itself establish whether the source schema contained strict provenance, and its model-source inventory did not implement a William Hill 1X2/O/U contract validator.

R4 first freezes the p34 source `matches`/`snapshots` schema inventory, required provenance-field availability and non-empty counts from the same read transaction as the exported p34 subset. If every required field exists, the canonical source-observed clock, fetch clock, raw batch ID, and immutable bundle hash are exported and evaluated. R4 also exports the p0 handicap subset, copies and verifies p42 segment packages, archives those p42 bytes deterministically, and writes a mechanical William Hill 1X2/O/U candidate inventory. G0 then reads only these exported inputs. All exported files, the audit JSON, and the fail-closed decision are copied into one new Freeze Protocol v1 package. Paths inside the frozen JSON are logical rather than workstation-local.

The required R4 command is:

```bash
python scripts/run_sp_consistency_g0.py \
  --work-dir results/research/sp_consistency_001a/g0_work \
  --freeze-dir results/freeze/SP-CONSISTENCY-001A-G0-R4 \
  --audit-at-utc '<explicit UTC timestamp>' \
  --git-commit '<commit containing this preregistration>'
```

The R4 entry point records query-level outcome prohibitions, per-season/per-issue denominators and exclusions, all input hashes, model-input inventory status, source-schema provenance evidence, and verified p42 identities. A filename/hash inventory without a contract validator is reported as `UNKNOWN_NOT_EVALUATED`, not as zero strict model coverage. It does not load final scores and cannot report predictive results.

## Frozen evidence

The independently downloadable R4 package is [SP-CONSISTENCY-001A-G0-R4.tar.gz](https://github.com/algotradinglife/beijing-lot/releases/download/sp-consistency-001a-g0-r4/SP-CONSISTENCY-001A-G0-R4.tar.gz). Its archive SHA-256 is `38da775b022f458b3d8024b6d710b7937d8042e9687b3fc0421aa7e9f710668d` (18,119,742 bytes). It contains the complete Freeze Protocol v1 package and is anchored by tag `sp-consistency-001a-g0-r4` at code commit `126218bb975bc54d741e0562382fc09b832c0245`.

- Freeze ID: `12db65db1b7e4e976336c75df424d3866a0066dec5bbd92bce39accfe4c8fd4e`
- Manifest SHA-256: `45e19d58dee645b82366e362da6d13b9f3b3151f3db9b99c159c89668136ca0b`
- Package checksum-list SHA-256: `dbae108a06dff41588d04f896200ccf51ef373b27b2b5d6ccaa33e47b6c6ee15`
- Verification: `python scripts/manage_research_freeze.py verify-freeze --package-dir SP-CONSISTENCY-001A-G0-R4` returns `status: valid` after unpacking.

The same-transaction source-schema inventory is frozen as `p34_source_schema.json` (SHA-256 `cd0983468a96af93fa09faebcfca2fa40defd0630d1cb5bed943566e6bbaf994`). It establishes that the p34 source `snapshots` schema has none of the four required roles: source-observed clock, fetch clock, raw batch ID, or immutable bundle hash. Accordingly, 3,790 p34 match-markets over 25 issues yield zero strict p34 match-markets by a source-schema-supported gate, not by an intentionally lossy export. The copied and verified p42 input has 31 strict match-markets (20 exact-tail mappings). The frozen filename/hash inventory identifies 365 model-source candidates, but its strict eligibility is `UNKNOWN_NOT_EVALUATED`; it is not treated as zero coverage and no model pairing is reported.

The frozen G0 verdict is `INSUFFICIENT_STRICT_DATA`; G1/G2, Stage A, Stage B, settled-outcome access, prediction scoring, and backtests remain unauthorized.
