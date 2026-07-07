# Postmatch Ticket-Pool Artifact Contract

Date: 2026-07-07

## Purpose

Frontend settlement review should consume strategy-owned ticket-pool artifacts
instead of deriving N-string conclusions from per-match review rows.

## Artifact

Path pattern:

```text
results/postmatch_ticket_pool_artifacts/{issue}_{YYYYMMDD}_{variant_id}/postmatch_ticket_pool_{issue}_{variant_id}.json
```

Current generated examples:

```text
results/postmatch_ticket_pool_artifacts/26071_20260707_shadow_v3.3.3/postmatch_ticket_pool_26071_shadow_v3.3.3.json
results/postmatch_ticket_pool_artifacts/26072_20260707_shadow_v3.3.3/postmatch_ticket_pool_26072_shadow_v3.3.3.json
```

Schema: `postmatch_ticket_pool_artifact_v1`

Generator:

```bash
python3 scripts/publish_postmatch_ticket_pool_artifacts.py \
  --issue 26072 \
  --structured-csv results/backtest_shadow_current_20260705/26072_20260704_shadow_v3.3.3/structured_shadow_26072.csv \
  --db data/derived/500_bjdc/500_bjdc.sqlite \
  --date-slug 20260707
```

Defaults:

```text
variant source: shadow_selection_codes
segment budget: 1000 yuan
stake per exact ticket: 2 yuan
budget fill mode: scale_to_budget
rolling window: 12h, extend through 18/24/36h to satisfy minimum matches
fixed N replay: N=3/4/5/6/7
```

## API

The settlement endpoint attaches the artifact when it exists:

```text
GET /api/issues/{issue}/settlement?decision_variant={variant_id}
```

Response fields:

```text
postmatch_ticket_pool_status
postmatch_ticket_pool
```

Missing behavior is explicit:

```json
{
  "postmatch_ticket_pool_status": {
    "status": "missing",
    "reason": "postmatch_ticket_pool_artifact_missing"
  }
}
```

The API does not synthesize this artifact from per-match review rows.

## Example Results

Dynamic policy is the rolling segment N selector under the same 1000 yuan
segment budget.

| issue | variant | segments | planned budget | dynamic tickets | stake | profit | ROI | coverage |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 26071 | shadow_v3.3.3 | 2 | 2000.00 | 1000 | 2000.00 | 2233.15 | 111.66% | 14/16 |
| 26072 | shadow_v3.3.3 | 4 | 4000.00 | 2000 | 4000.00 | -17.45 | -0.44% | 50/65 |

Fixed N replay at 1000 yuan per segment:

| issue | N | tickets | stake | profit | ROI | hit ticket rate | miss by 1 | miss by 2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 26071 | 3 | 1000 | 2000.00 | 2135.07 | 106.75% | 9.70% | 348 | 412 |
| 26071 | 4 | 1000 | 2000.00 | 2452.93 | 122.65% | 3.50% | 206 | 382 |
| 26071 | 5 | 1000 | 2000.00 | 3094.43 | 154.72% | 1.40% | 115 | 288 |
| 26071 | 6 | 1000 | 2000.00 | 2490.15 | 124.51% | 0.50% | 61 | 196 |
| 26071 | 7 | 1000 | 2000.00 | -2000.00 | -100.00% | 0.00% | 26 | 134 |
| 26072 | 3 | 2000 | 4000.00 | -453.39 | -11.33% | 2.90% | 462 | 940 |
| 26072 | 4 | 2000 | 4000.00 | -1981.76 | -49.54% | 0.80% | 135 | 586 |
| 26072 | 5 | 2000 | 4000.00 | -3048.37 | -76.21% | 0.10% | 60 | 298 |
| 26072 | 6 | 2000 | 4000.00 | -2198.67 | -54.97% | 0.05% | 7 | 134 |
| 26072 | 7 | 2000 | 4000.00 | -4000.00 | -100.00% | 0.00% | 4 | 51 |

## Difference From Frontend Approximation

- Frontend approximation starts from per-match postmatch review rows; this
  artifact starts from a frozen decision variant CSV and records `variant_id`.
- Frontend approximation can only infer leg-level hits; this artifact samples
  exact N-ticket units, settles them with final `winning_sp`, and records
  ticket counts, hit-ticket rate, miss-by-1/miss-by-2, and drag legs.
- The artifact uses rolling time segments and a 1000 yuan budget per segment.
  Default `budget_fill_mode=scale_to_budget` means small pools are scaled up to
  the configured budget rather than leaving unused capital.
- `match_attribution` allocates ticket appearances and profit contribution from
  the actual sampled ticket pool, not from a standalone per-leg estimate.
- Historical reruns must write a separate variant/version or explicitly use
  `--force`; post-settlement artifacts are review-only and cannot improve a
  pre-settlement recommendation retroactively.
