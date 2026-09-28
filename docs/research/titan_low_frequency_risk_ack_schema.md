# Titan low-frequency risk acknowledgement

Use this only when the operator explicitly accepts responsibility for direct
collection without a provider-issued automation authorization. It is not a
provider permission and it does not override site terms or law.

```json
{
  "schema_version": "titan_low_frequency_risk_ack_v1",
  "source_id": "titan",
  "operator_accepts_risk": true,
  "allowed_origins": ["data.titan007.com", "1x2d.titan007.com"],
  "max_requests_per_minute": 12,
  "max_fixture_ids_per_run": 1
}
```

Limits are intentionally capped at 12 HTTP requests/minute and 3 fixture IDs/run.
The collector reserves all requests for a run in the local control database
before network access, rejecting a run that would exceed the rolling one-minute
limit. Store the acknowledgement outside the data root; only its SHA-256 is
recorded in a Titan capture/release.

Run with:

```bash
python scripts/collect_titan_clean_roster.py \
  --data-root "$BEIJING_LOT_DATA_ROOT/clean_v1" \
  --capture-key "titan-<UTC-capture-key>" \
  --fixture-id <Titan-ID> \
  --risk-acknowledgment /secure/path/titan-risk-ack.json
```
