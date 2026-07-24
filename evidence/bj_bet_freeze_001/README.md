# BJ-BET-FREEZE-001 audit evidence

This tracked package contains the immutable Segment 1 source bundle, its
original `SHA256SUMS`, and a clean-checkout verifier. Run:

`python3 evidence/bj_bet_freeze_001/verify_segment_1_missed_evidence.py`

Segment 1 is explicitly **pre-freeze, out-of-contract evidence**: it is not
retroactively promoted to the v2 N×budget-matrix/ledger contract. Its
correct-score JSON is incident evidence, not a valid unavailable freeze.
Segments 2 and 3 remain pending until prospective packages and receipts exist.
