# Analysis data contracts

- R analysis outputs are tibbles; each table declares row meaning and keys.
- Mapping report row: one `(issue, slot)`; joins validate one-to-one cardinality.
- `issue` and provider IDs are character data; slots and valid 500 fixture IDs are integers.
- Dates use `Date`; source wall times use `POSIXct` with Asia/Shanghai semantics; snapshot outputs normalize to UTC.
- Missing odds stay `NA_real_`; missing times stay typed `NA`; empty snapshot tables retain their schema.
- Mapping inputs retain their original bytes and SHA-256 hashes; decoding failures stop processing.
- `record_capture()` requires an explicit capture key/time, source URLs, raw bytes, coverage, and alignment.
- Exact retries reuse receipts; changed payload or alignment under the same key fails. Rebuild uses one database transaction.
- Duplicate mapping keys or non-injective alignment fail; remapped void slots are isolated under the 500 slot identity.
- Snapshot outputs retain Python receipts in the `receipts` attribute; save that attribute alongside exported tables.
- Snapshot receipts identify `HISTORICAL_PROXY` and prohibit prospective use; missing chronology or pre-kickoff quotes fails closed.
- No historical fitting or policy tuning is introduced by these adapters; decision-facing learning still requires shared cutoff contexts and independent replay.
