# #204 Gate A — market-anchored residual model preregistration

This is an immutable **outcome-unexposed** Track-A contract.  It verifies and
uses only the #203 inference namespace.  It does not import, open, copy or
emit development or retrospective settlement labels.

* Development: [2019, 2020, 2021, 2022, 2023]
* Frozen one-shot retrospective test: 2024
* Embargoed for #210: 2025 onward
* Candidate models: market-only, logistic residual, shallow gradient residual,
  then a set-context residual only if the controls justify it.

The hard action gate is `BJ204_MARKET_OR_NO_BET_V1`: an incomplete, nonfinite,
out-of-distribution or failed-calibration row reproduces the frozen market
baseline where it is valid, otherwise it is `NO_BET_FROZEN`.

No historical result authorizes betting, production, release or downstream
#205 work.  Gate B requires PI acceptance of this exact package.
