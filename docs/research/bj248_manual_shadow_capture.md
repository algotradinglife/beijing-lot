# #248 manual Nowscore shadow capture — 2026-08-19

This is one manual, read-only shadow probe. It did **not** start an unattended
scheduler or write to a production root. The external raw evidence remains
outside Git at the temporary operator-selected path shown below; this document
contains only its reproducible receipt facts.

## Request and captured issue page

- Request URL: `https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=26086`
- Request / trusted receive UTC: `2026-08-19T15:48:18Z` /
  `2026-08-19T15:48:19Z`
- Temporary operator-selected shadow root (not a production data root; do not
  rely on its retention)
- Raw issue-page SHA-256:
  `8c088530f517f8e9902bac3fa8e12a6bc8a96d97297d7ee6df1d19bda4cda4bd`
- Raw issue-page bytes: `333962`
- Parser result: `OK`, `80` recognized fixture rows
- All discovered history URLs had the allowlisted host
  `cp.nowscore.com` and the expected `/sp/danchang/26086_<slot>_5.html`
  route.

## Observed compatibility and causal outcome

- The issue page contained 16 rows classified `finished` and 64 rows
  classified `scheduled`; 64 rows carried `cansale=true`.
- The first three parsed rows nevertheless had 2026-08-18 local kickoff dates;
  their calculated kickoffs were 2026-08-17T19:00:00Z,
  2026-08-17T19:00:00Z and 2026-08-17T20:00:00Z. This is inconsistent with a
  live-sale interpretation at the receive time and is treated as source/sale
  metadata needing further qualification, not as a forward observation.
- All 80 referenced history pages were fetched once at one-second pacing. None
  was admitted to the forward store: 42 failed the strictly pre-kickoff receipt
  gate and 38 failed the complete finite `3/1/0` SP domain gate.
- The collector emitted 80 explicit `sp_history` failure records (rather than
  producing missing-as-zero rows), so `capture_receipt=0` and
  `sp_change_vector=0` is an explicit no-admission result.

## Decision boundary

This probe confirms the concrete issue-page and history URL shape, and it
exercised actual parser/allowlist/failure-observability paths. It does **not**
qualify source retention, active-sale truth, successful forward-vector
collection, cadence, or learning sufficiency. Do not enable unattended
collection until a fresh issue has a source schedule/sale state whose local
kickoff is demonstrably in the future and at least one complete causal `3/1/0`
vector is admitted.
