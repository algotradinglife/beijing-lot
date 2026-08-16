# R2 SAME-CLASS SWEEP EVIDENCE — Issue #237 (EV R1 REJECT, REWORK_TYPE=method)

EV R1 required the worker to declare "我检查了所有 <类别> 点" with file /
function / call-point / exception-path lists for each defect class.  This
file is the machine-checkable inventory of that sweep.  Every item below
was read line-by-line in R2; the fix location is named where one exists.

---

## 1. C-01 class: line / NaN / finite-default / handicap-mapping paths

Checked EVERY call point that touches `handicap_line_norm`, NaN coercion,
`finite(default=0.0)`, or the 3/1/0 handicap mapping:

| # | File / function | Line(s) | Finding | Fix |
|---|---|---|---|---|
| 1 | `scripts/bj237_power_lib.py::line_is_publishable` | new | FAIL-CLOSED single predicate | added |
| 2 | `scripts/bj237_power_lib.py::line_value` | new | returns None unless publishable | added |
| 3 | `scripts/bj237_build_features.py::build_features` | line gate | R1 used `_finite(NaN)=0.0`; now `lib.line_value` before core call | fixed |
| 4 | `scripts/bj237_build_features.py::support_summary` | filter | R1 `line_ok` included NaN-coerced rows; now requires `native_handicap_line.notna()` | fixed |
| 5 | `scripts/bj237_build_features.py::calibration_through_2023` | filter | same fail-closed filter | fixed |
| 6 | `scripts/bj237_waterfall.py::build_full_waterfall` | line stage | R1 `notna()` only; now `lib.line_is_publishable` (grid + finite) | fixed |
| 7 | `scripts/bj237_verify_package.py::verify` | C-01 checks | R1 checked line domain after `dropna()` (missed null-line rows); now asserts line_ok⇒non-null grid AND ~line_ok⇒null | fixed |
| 8 | `tests/scripts/test_bj237_power_features.py::TestFailClosedLineSemantics` | new | 7 tests incl. NaN→0 regression | added |
| 9 | `scripts/bj180_team_matchup_core.py::finite` | 74-79 | accepted freeze; default 0.0 retained but unreachable for non-publishable rows (builder gates first) | documented |
| 10 | `scripts/bj180_team_matchup_core.py::handicap_result` | 93-95 | called only with validated grid line from publishable rows | documented |
| 11 | `scripts/bj180_team_matchup_core.py::family_vectors` | 346 | `finite(row.get("handicap_line_norm"))` — reached with raw value; builder passes raw and gates on output | documented |
| 12 | `scripts/bj180_team_matchup_core.py::poisson_handicap` | 98-114 | line clamped only after validated grid membership | documented |

Boundary samples exercised in tests: `None`, `NaN`, `inf`, `"not-a-line"`,
`0.0`, `-1.5`, `3.5` → all fail-closed correctly (see
`test_line_predicate_never_defaults_nan_to_zero`).

## 2. C-02 class: producer-written flag / reason / summary read as primitive

Checked every producer-written flag / reason / summary column that the
package reads and could mistake for a primitive:

| # | File / function | Read | Finding | Fix |
|---|---|---|---|---|
| 1 | `scripts/bj237_waterfall.py::reconstruct_229_power_intersection` | `P_POWER_BJLINE_available` | R1 terminal gate; now G1..G6 from primitives (vector, observed_at≤epoch, freeze triplet, exact non-null line) | fixed |
| 2 | `scripts/bj237_waterfall.py::reconstruct_229_power_intersection` | `BJ_LINE_BOUNDARY_available` | not used in R2 | audited |
| 3 | `scripts/bj237_build_features.py::build_features` | epoch map from #203 `issue_offsets` | primitive (decision epoch) — correct | audited |
| 4 | `scripts/bj237_verify_package.py::verify` | manifest headline | R1 could trust manifest; now headline recomputed from artifact | fixed |
| 5 | `scripts/bj237_verify_package.py::verify` | support/calibration | recomputed from `power_features` (+ labels) and compared to committed | fixed |
| 6 | `notebooks/.../bj237_power_feature_support.ipynb` | all | reads only package artifacts; no availability-flag gates | audited |

Gate-level rows/issues (primitives): cells 357,705 → vector 4,674 →
causal epoch 234 → freeze 234 → line 234 → published 234 / 9 issues.

## 3. C-03 class: window / groupby / aggregate definitions

Checked every groupby / agg / count in the package; frozen key, unit,
denominator:

| # | File / function | Old key | R2 key | Unit | Denominator |
|---|---|---|---|---|---|
| 1 | `bj237_build_features.py::support_summary` | (year, league, line) | (issue, year, league, line) | rows=outcome cells; matches=per-issue match_idx nunique | publishable rows only (triplet+line+seen) |
| 2 | `bj237_build_features.py::calibration_through_2023` | (year, league, outcome) | (issue, year, league, line, outcome) | n=hit count; mean_pred/mean_actual | valid labels ≤2023 |
| 3 | `bj237_verify_package.py::_recompute_support` | — | same key as builder | same | same |
| 4 | `bj237_verify_package.py::_recompute_calibration` | — | same key as builder | same | same |
| 5 | notebook by-year table | (year) | (year) with corrected cells/matches/issues | cells/matches/issues | publishable |
| 6 | `docs/research/issue-237/REPORT.md` annual table | wrong (57 issues 2025 etc.) | corrected (15 issues 2025; 35,781 cells 2020) | — | — |

Cross-layer consistency checks (verifier + tests):
- `support_summary.rows.sum() == publishable cells` ✓
- `support_summary.matches.sum() == distinct (issue, match_idx) pairs` ✓
- `support_summary.issues == 1` per group ✓
- `calibration.n.sum()` recompute equality ✓
- `REPORT.md`/notebook annual numbers match artifact ✓

## 4. C-04 class: identity / alias joins

Checked every identity/alias join and the #234 interface consumption:

| # | File / function | Join | Finding | Fix |
|---|---|---|---|---|
| 1 | `bj237_power_lib.py::canonical_fixture_id` | (issue, match_idx) | deterministic #234 rule | added |
| 2 | `bj237_power_lib.py::alias_active` | valid_from/valid_to vs asof | temporal validity; future alias inactive | added |
| 3 | `bj237_power_lib.py::resolve_team_identity` | source key → team_id | UNIDENTIFIED / AMBIGUOUS, never fuzzy | added |
| 4 | `bj237_power_lib.py::fixture_identity_status` | fixture row | CANONICAL/AMBIGUOUS/UNIDENTIFIED | added |
| 5 | `bj237_build_features.py::build_features` | xlsm team/league | consumes #234 identity; dup (issue,match_idx) → AMBIGUOUS | fixed |
| 6 | `bj237_waterfall.py::build_identity_waterfall` | dup key check | unchanged (correct) | audited |
| 7 | `bj237_verify_package.py::verify` | cross-table identity | features vs diagnostics teams/league/line | added |
| 8 | tests `TestCanonicalIdentity` | 6 tests | temporal validity, unknown alias, duplicate fixture, future alias mutation | added |

## 5. E-01 class: decision-facing payloads + remanifested tamper coverage

All 13 EV-listed semantic tampers are implemented as copy+mutate+
re-manifest attacks; production `verify()` must FAIL each (see
`bj237_verify_package.py::tamper_attacks` and
`tests/.../TestTamperSelfDefense`):

| # | Tamper | Detection mechanism |
|---|---|---|
| 1 | probability outcome permutation | cross-table power_p{code} |
| 2 | legal line rewrite (0.0→0.5) | cross-table native_handicap_line |
| 3 | home/away team swap | cross-table team ids |
| 4 | league rewrite | cross-table league |
| 5 | epoch shift | cross-table decision_epoch_utc |
| 6 | history depth forgery | cross-table min_history_n |
| 7 | outcome domain forgery (compensated) | triplet normalization + domain + cross-table |
| 8 | whole-issue history digest forgery | manifest issue_digests anchor |
| 9 | support zeroing | aggregate recompute |
| 10 | calibration forgery | aggregate recompute |
| 11 | manifest output/source hash forgery | source receipt hash recompute |
| 12 | schema clear | schema coverage check |
| 13 | delete support_summary | file-existence closure |

## 6. E-02 class: write points / publication

Checked every write point in the package:

| # | File / function | Old behavior | R2 behavior |
|---|---|---|---|
| 1 | `bj237_build_features.py::write_package` → `pub.atomic_publish_directory` | direct overwrite | fail-on-existing + same-parent staging + fsync tree + atomic rename + rollback |
| 2 | `feature_schema.json` | 2 tables, column names only | 4 tables, physical/logical types, nullability, domains, FKs |
| 3 | `manifest.json` | base main commit; listed non-participating DBs | producer HEAD; receipts only participating sources (xlsm + 3 packages) |
| 4 | `SHA256SUMS.json` | post-hoc refresh bug | written once in staging after all files |
| 5 | `bj237_verify_package.py` | no source-hash/output-count/model-blob checks | source hashes + output counts + schema coverage |
| 6 | `PROTOCOL-LOG.md` | absent | created with entries 001-006 |
