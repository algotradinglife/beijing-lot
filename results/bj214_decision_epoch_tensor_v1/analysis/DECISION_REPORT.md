# #214 decision-epoch market/SP capability

Disposition: **BLOCKED_INSUFFICIENT_CAUSAL_SUPPORT**.

Controlling representative rule: `MEDIAN_KICKOFF_MINUS_10H`.
All other rules are sensitivity evidence and do not vote in the gate.

## Model-learning support gate

| cohort | evaluated issues | evaluated epochs | N7 epoch pass rate | causal core coverage | gate |
| --- | ---: | ---: | ---: | ---: | --- |
| development | 342 / 30 | 342 | 0.00% | 0.00% | FAIL |
| historical_model_unseen | 52 / 5 | 52 | 23.08% | 55.25% | FAIL |
| prospective_post_activation | 0 / 2 | 0 | 0.00% | 0.00% | FAIL |

## Ticket-operability gate

| cohort | evaluated issues | evaluated epochs | N7 epoch pass rate | ticket-eligible coverage | gate |
| --- | ---: | ---: | ---: | ---: | --- |
| development | 342 / 30 | 342 | 0.00% | 0.00% | FAIL |
| historical_model_unseen | 52 / 5 | 52 | 0.00% | 0.00% | FAIL |
| prospective_post_activation | 0 / 2 | 0 | 0.00% | 0.00% | FAIL |

The prospective activation sensitivity has 269 / 289 causal core matches (93.08%); it is not the controlling rule.

Model-learning is blocked independently: development lacks timestamped historical EURO plus Beijing-SP support. The valid alternatives are to obtain timestamped historical development support, accumulate a sufficient prospective training panel, or formally narrow #204 to a simpler or prospective-only design.

Ticket operability is also blocked because the frozen p34 source exposes neither verified sale-open nor parlay-allowed state. Repairing sale/parlay evidence alone does not create a causal historical training panel.

#204 remains blocked. A future Data capability must capture p34 sale/parlay state and separately repair model-learning support under the controlling rule. This negative result grants no model, betting, ROI, release or execution authority.
