# BJ-BET-FREEZE-001 audit evidence

This tracked package records reviewable hashes and the verifier entrypoints.
It intentionally does not copy ignored operational input/plan files.  Reviewers
with the operational bundle run `scripts/verify_natural_day_segment_consistency.py`
against the recorded paths and compare the SHA-256 values below.

Segment 1 is explicitly **pre-freeze, out-of-contract evidence**: it is not
retroactively promoted to the v2 N×budget-matrix/ledger contract.  Segments 2
and 3 must use `publish_exact_n_segment_freeze.py`, which emits 15 independent
N×budget variants, a content-addressed artifact directory, and one append-only
ledger record.
