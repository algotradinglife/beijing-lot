# #214 decision-epoch market/SP capability

Disposition: **BLOCKED_INSUFFICIENT_CAUSAL_SUPPORT**.

| cohort | evaluated issues | evaluated epochs | N7 epoch pass rate | strict core coverage | gate |
| --- | ---: | ---: | ---: | ---: | --- |
| development | 342 / 30 | 2394 | 0.00% | 0.00% | FAIL |
| historical_model_unseen | 52 / 5 | 364 | 0.00% | 0.00% | FAIL |
| prospective_post_activation | 1 / 2 | 2 | 0.00% | 0.00% | FAIL |

The package distinguishes timestamped price availability from strict ticket eligibility. p34 price observations exist, but the frozen source exposes neither verified sale-open nor parlay-allowed state. Named historical 1h/10h fields are diagnostic-only because they do not carry observation timestamps.

#204 remains blocked. A future Data capability must capture p34 sale/parlay state and immutable raw provenance at the same decision epochs, then satisfy the predeclared gate. This negative result grants no model, betting, ROI, release or execution authority.
