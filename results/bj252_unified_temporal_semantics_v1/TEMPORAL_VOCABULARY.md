# Temporal vocabulary

- `historical_proxy`: `initial`, `10h`, `1h` are source-relative labels, never universal issue timestamps; rows have null `observed_at_utc`.
- `strict_forward`: a sealed selected receipt from `beidan_live.snapshots.snapshot_ts` with explicit UTC observation clock.
- issue cutoff: earliest issue kickoff minus a declared lead; per-fixture staleness is recorded.
- segment fallback: Asia/Shanghai local kickoff-date segment; cutoff is that segment's earliest kickoff minus the same lead.
- no model, ROI, ticket, or profitability claim is made.
