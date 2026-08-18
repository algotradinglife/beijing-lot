# Issue #254 — final source-schema integration decision

## Executive decision

The #250–#253 chain now forms one executable prototype data interface.  A clean
run from `BEIJING_LOT_DATA_ROOT` rebuilds a normalized SQLite/Parquet snapshot,
binds the exact predecessor review HEADs and merge commits, verifies the
physical invariants, reproduces byte-identical files, and validates an isolated
restore copy.

This closes the *schema decision*, not the *data recovery*.  Historical proxy
and strict-forward evidence remain separate.  Canonical real-world fixture,
team and competition identity remains unavailable.  Full historical Beijing
SP, bookmaker-level European odds and power features remain downstream work.

## Bound predecessor decisions

| Issue | Accepted review HEAD | Merge commit | Accepted boundary |
|---|---|---|---|
| #250 | `60a2edc3b45ba092dd6eff2e9d1b177d0c096222` | `99701cf984797db2646033c03467e404bfd8ecc8` | Source census and admissible-use evidence |
| #251 | `277dc11140bf2694dd1383f9f05957558c697da6` | `63729bc01c830f9a651ae55861c22b32a58bf3e6` | Restricted issue-local identity; no invented entity IDs |
| #252 | `596d044cfb178710d3b533f66e0c439f50d3faf5` | `17be9fdaef38e682ff88bd4d5f03f86771e920e1` | Historical proxy versus strict-forward temporal semantics |
| #253 | `a086c4750b678f24f578c2fa8ee3032bdb9c02e2` | `82fba7ed95354a5cf1f1087e3b640cfa28f46e4f` | Long M×3 physical schema and label isolation |

The integration manifest also binds the SHA-256 of every accepted predecessor
manifest.  Review HEAD and merge commit are separate fields; they are not
interchanged.

## Executed real-data receipt

The executed notebook rebuilt the external package from the current project
data root.

| Measure | Result |
|---|---:|
| Historical proxy years | 2014, 2015, 2016, 2017 |
| Issue-local slots | 8 |
| Distinct issue buckets | 6 |
| Observations | 16 |
| Long M×3 feature cells | 60 |
| Available feature cells | 58 |
| Explicitly missing feature cells | 2 |
| Historical-proxy cells | 36 |
| Strict-forward cells | 24 |
| Physically separate labels | 4 |
| Data-dictionary fields | 79 |
| Byte-identical rebuild | PASS |
| Isolated restore-copy verification | PASS |

The small sample is deliberately representative, not statistically complete.
It proves that multiple historical years and a strict-forward sample can pass
one physical contract without pooling their evidence grades.

## What is usable now

- Historical strategy exploration may consume the `historical_proxy` lane,
  including source-relative `initial/10h/1h` European 1X2 observations.
- Strict forward checks may consume only `strict_forward` pre-kickoff poll rows,
  retaining the inherited current-schedule/not-reschedule-as-of limitation.
- Model code may read the long feature Parquet.  It cannot reach result,
  winning-SP, settlement or payout fields through the feature reader.
- Missing observations remain null with an availability mask and reason code.
- The Beijing `0.65` coefficient remains an N-fold settlement concern and is
  absent from the source-feature layer.

## Downstream readiness interpretation

“The desired data does not yet exist” must not circularly block the Issue whose
purpose is to recover that data.  The machine-readable matrix therefore
separates graph/execution readiness from eventual model-data readiness.

| Issue | Execution decision after #234 closes | Data state |
|---|---|---|
| #235 | PI/user recovery checkpoint | Historical native-line/SP recovery required |
| #236 | PI/user recovery checkpoint | Bookmaker history and BJ-line mapping inputs required |
| #237 | PI scope review | Real-world team/competition identity path must be decided first |
| #248 | Ready to implement | Prospective collection still required |
| #249 | Ready to implement | Snapshot/restore implementation still required |

## Adversarial interpretation

- A passing replay does **not** make source-relative horizons exact timestamps.
- M×3 shape compatibility does **not** make European straight 1X2 identical to
  Beijing non-zero-handicap settlement outcomes.
- Issue-local slot identity does **not** establish a canonical real-world
  fixture/team join.
- A portable representative package does **not** prove full-history coverage.
- Closing #254/#234 releases recovery work; it does not authorize model,
  strategy, ROI or production claims.

## Route forward

After terminal acceptance, #234 may close.  The next user/PI discussion should
freeze #235 and #236 recovery scope before execution.  #237 requires a separate
identity-path decision, while #248 and #249 may use the physical interface
without waiting for model-data completion.
