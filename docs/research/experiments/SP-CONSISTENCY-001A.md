# SP-CONSISTENCY-001A — score distribution vs handicap 3/1/0

Status: `g0_r1_pending; no_formal_result`

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

## G0 revision R1

The original local-only G0 package is not cited as evidence: it did not bind every result-affecting input atomically and was not published durably. It remains untouched on the originating machine but is superseded, not repaired or overwritten.

R1 first exports an outcome-blind p34 SQLite subset and p0 handicap SQLite subset from read transactions, copies and verifies p42 segment packages, archives those p42 bytes deterministically, and writes a mechanical William Hill 1X2/O/U candidate inventory. G0 then reads only these exported inputs. All exported files, the audit JSON, and the fail-closed decision are copied into one new Freeze Protocol v1 package. The package is to be published as a durable release asset before PI evidence review.

The required R1 command is:

```bash
python scripts/run_sp_consistency_g0.py \
  --work-dir results/research/sp_consistency_001a/g0_work \
  --freeze-dir results/freeze/SP-CONSISTENCY-001A-G0-R1 \
  --audit-at-utc '<explicit UTC timestamp>' \
  --git-commit '<commit containing this preregistration>'
```

The R1 entry point records query-level outcome prohibitions, per-season/per-issue denominators and exclusions, all input hashes, model-input inventory/rejections, and verified p42 identities. It does not load final scores and cannot report predictive results.
