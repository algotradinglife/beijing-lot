# Issue #235 historical relative-horizon proxy

This package retains `initial`, `10h`, and `1h` separately. It is a RETROSPECTIVE_PROXY: labels are not wall-clock observations. Raw SP and normalized inverse-SP probability are separate fields; unavailable vectors have probability zero and an explicit reason. No final snapshot, settlement, outcome, winning SP, or Beijing payout coefficient is read or emitted.
