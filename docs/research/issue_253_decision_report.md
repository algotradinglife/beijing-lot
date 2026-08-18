# Issue #253 decision report — prototype M×3 physical layer

## Decision summary

The minimum end-to-end physical interface works and is ready for the model
prototype.  It uses the accepted issue-local grain:

`issue_code × match_idx × outcome_code(3/1/0) × observation × feature_name`

SQLite stores source, slot, play, outcome, observation and quality-control
metadata.  Parquet stores the long analytical feature cells.  Settlement
labels live in a separate SQLite database and a separate Parquet namespace;
the model-facing reader has no settlement path.

This is not a claim that current sources identify canonical real-world
fixtures, teams or competitions.  Those fields remain unavailable rather than
being inferred from labels.  Live URL-expect issue assignments remain
noncanonical even where a provider `fid` is retained as provenance.

## Executed representative build

The executed notebook built a real-data sample under
`BEIJING_LOT_DATA_ROOT/derived/bj253_physical_schema_v1` from the accepted #251
identity package, historical workbook proxy and live poll database.

| Surface | Rows |
|---|---:|
| Issue-local slots | 8 |
| Issues/buckets | 3 |
| Observations | 16 |
| Long M×3 feature cells | 60 |
| Available feature cells | 58 |
| Explicitly missing feature cells | 2 |
| Historical-proxy cells | 36 |
| Strict-forward cells | 24 |
| Separate settlement labels | 4 |

The sample includes historical `initial/10h/1h` European-odds proxy cells,
pre-kickoff live Beijing SP and European-odds cells, and a deliberately retained
incomplete SP triplet.  Missing values remain null with a reason code; they are
not converted to zero.

## Accepted boundaries

- `BEIJING_LOT_DATA_ROOT` is the only storage-root interface.  Databases, raw
  slices and Parquet remain outside Git; code, notebook, reports and manifests
  are tracked.
- `historical_proxy` rows have source-relative horizon labels and no fabricated
  wall-clock observation time.
- `strict_forward` rows require a pre-kickoff poll-start timestamp, but the
  current live sample remains bounded by current-schedule/not-reschedule-as-of
  semantics inherited from #252.
- Feature inputs contain no result, winning-SP, settlement or payout columns.
  The Beijing 0.65 coefficient belongs only to downstream N-fold settlement,
  never to per-cell source normalization.
- The representative package proves the interface, not full-history coverage,
  model performance or data completion.

## Route forward

#254 should integrate this interface with the #234 source contract without
adding a warehouse framework or compatibility layer.  Historical completion
remains #235/#236, power features remain #237, and prospective collection
remains #248.
