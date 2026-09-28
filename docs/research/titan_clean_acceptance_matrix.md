# Titan-only clean lane acceptance matrix

| Requirement | Evidence | Status |
| --- | --- | --- |
| No legacy import or merge | Collector has no legacy-data, SQLite, Parquet, Excel or Nowscore input; tests build only fresh temporary roots. | Verified |
| Titan-independent fixture discovery | Titan roster script discovered current IDs; a roster-listed ID was fetched through Titan's own 1X2 route in read-only probes. | Verified capability |
| Titan raw and normalized market storage | Content-addressed raw receipts, roster/fixture records, and `euro_1x2_quote` normalization are Titan-only. | Verified |
| Strict causal availability | Pinned release as-of materialization admits only `trusted_received_at_utc < Cutoff`; equality and post-release mutation are tested. | Verified |
| Immutable replay | Sealed SQLite snapshot, manifest/raw hash validation, and tamper detection are tested. | Verified |
| ID reuse safety | Release diagnostics report repeated source IDs without merge; settlement bridge anchors exact fixture-capture batches. | Verified |
| 500 isolation | Separate storage and a minimal, imported frozen bridge are required before label write/export. | Verified |
| Nowscore removal | The clean lane neither imports nor calls Nowscore; no bridge role remains. | Verified |
| Authorized unattended Titan collection | Operational CLI accepts a provider authorization receipt; the user may instead submit an explicit bounded low-frequency risk acknowledgement. No provider authorization receipt has been supplied. | User-risk opt-in implemented |

A risk acknowledgement never promotes public readability or successful probes into
a provider-authorization claim. It only enables an operator-attributable path
with a content hash, 12 HTTP requests/minute maximum, three fixtures/run maximum,
and a pre-network rolling-window reservation.
