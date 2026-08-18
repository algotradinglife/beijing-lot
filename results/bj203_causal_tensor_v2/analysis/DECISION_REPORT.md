# #203 downstream readiness decision

Decision: **#204 remains BLOCKED_PENDING_DATA_CAPABILITY**.

The current development coverage is:

| core input | causal unmasked coverage |
| --- | ---: |
| `calibrated_market_probability` | 0.970154% |
| `devig_euro_probability` | 0.977070% |
| `euro_1h_odds` | 0.977070% |
| `predicted_final_sp` | 7.682200% |
| `bj_sp_snapshot` | 0.000000% |

These rates do not support representing #204 as a usable market-anchored probability/SP learning capability. The 2026 held-out extension is identity only and does not change that conclusion.

Required PI-owned Data capability: `BJ-UNIFIED-MARKET-COVERAGE-001` under **BJ Data Platform**, covering causally timestamped development 1h EURO/market probability and pre-event Beijing SP, exact provenance, matched coverage, and a PI-approved representative-support gate. PI must create the native Issue and graph edge; this package only records the evidence-backed disposition.
