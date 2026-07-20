# Handicap-draw score-projection research report

Date: 2026-07-18
Status: `blocked_fail_closed; research_only_nonselectable_roi_unauthorized`

## Result

There is no admissible evidence that score-distribution projection improves
Beijing handicap-draw probability in this worktree. The output is zero
predictions, zero calibration fits, and zero selection diagnostics.

The blocker is input provenance, not a negative performance result: the
committed tree contains no immutable historical P1/P2 score-margin panel with
the pre-decision clocks and input checksums required to establish no leakage.
No terminal correct-score price, final market price, result-derived feature, or
shared SQLite record was read as a substitute.

## What was checked

The G1/R3 committed forward material is a prospective three-way protection
contract, not a score-distribution archive. Its readiness section explicitly
says the prior overlap asset is not eligible for retrospective conversion. No
committed G2 score-margin artifact or P1/P2 historical record bundle was found.

The independent-Poisson reference supports the mathematical projection only:
for integer handicap `h`, sum score-grid mass by the sign of `home - away + h`.
The AH methodology separately cautions that independent Poisson misses a
low-score dependence degree of freedom, so G1 is retained as a baseline, not
treated as ground truth.

The correct-score research package was inspected for its immutable snapshot,
tail-mass, and fail-closed conventions. Its odds, EV/q diagnostic, and Top-k
functions were not invoked because this study excludes correct-score odds and
all price/return analysis.

## Controls delivered

`research.handicap_draw_projection` is an import-only pure research module.
It accepts immutable P1/P2 records, validates clocks and SHA-256 fields, makes
the entire panel ineligible on any bad record, and has no network, database,
file write, CLI, ticket, selection, price, or return path.

Its chronological loop compares frozen P1 baseline with G1 independent-Poisson
projection, evaluates binary and three-way proper scoring rules plus draw
calibration, and constrains calibration/blending to a small pre-registered
prior-settled candidate set. It reports a training-selected candidate only as a
diagnostic. A same-horizon baseline/G1 copy is included for fair post-warmup
comparison with fitted candidates.

The static [checksum artifact](artifacts/score_projection_handicap_draw_2026-07-18.json)
records the empty panel result; its canonical loop-payload SHA-256 is
`ed8cf1655c547ad41809f70292bd3faf9306198253adf374bd0946de46799413`.
The companion [artifact manifest](artifacts/score_projection_handicap_draw_manifest_2026-07-18.json)
checksums the plan, report, handoff, implementation, and focused test.

## Verification

Four direct focused checks passed in the available interpreter:

- normalized handicap projection and symmetry;
- reject a P2 timestamp after the decision time;
- prove every fitted/blended row trains only on earlier settlements;
- deterministic checksummed artifact with no return-oriented output.

`compileall` and `git diff --check` also passed. The standard pytest invocation
could not start because this worktree has no `.venv` and the available global
pytest installation is missing `pygments`; this is an environment limitation,
not a test failure.

## Risks

The main risk is not yet statistical: a newly supplied panel could have
ambiguous P1/P2 semantics, incomplete source coverage, or records whose
hashes do not tie to immutable raw snapshots. The loop deliberately rejects
timing faults but cannot prove a caller's claimed checksum is the correct raw
object. Independent Poisson may also remain miscalibrated at low scores even
after a valid input panel exists.

## Next step

Provide a separate, immutable historical P1/P2 export with the required
per-row clocks, input checksums, integer lines, and official settled handicap
outcomes. Freeze the export checksum before evaluation; then run the existing
pure loop without adding candidates or using any terminal correct-score odds.
