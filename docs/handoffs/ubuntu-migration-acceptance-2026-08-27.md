# Ubuntu migration acceptance — 2026-08-27

This record applies the recovery sequence in
[`ubuntu-migration-project-handoff.md`](ubuntu-migration-project-handoff.md) to the
Ubuntu checkout at `/home/drwho1985/workspace/algotradinglife/beijing-lot`.
It records observed results; it does not change GitHub Issue Graph lifecycle or
research authority.

## Accepted boundary

The external drive contains only snapshot `bj249-core-20260820-v1`. The user
explicitly accepted this as the recovery point rather than requiring a newer
cutover snapshot. This is an operational rollback recovery, not a source-complete
reconstruction of the 2026-08-25 #400 execution environment.

- Snapshot files: 464
- Snapshot bytes: 35,538,877,815
- Manifest SHA-256: `fada8656907ebe4dcb9f2b493e06699c52b095e22159bf23b9a26af4c45f3d6f`
- External verification: `PASS`
- Restore verification: `PASS`, 464 assets byte-identical to the verified snapshot
- Restore target: `/home/drwho1985/beijing-lot-runtime/bj249-core-20260820-v1`
- Runtime link: repository `data` -> restored ext4 `data`

The immutable external snapshot remains unchanged. The restored runtime copy is
now a live database and changed after the successful one-shot collection.

## Code and control plane

- Git commit at recovery start: `626e8449231a47e047a7f3230f4758ac3f6c2cf3`
- `main` and `origin/main`: synchronized before local migration repairs
- Live GitHub native dependency, parent/sub-issue, Project, Status, and Milestone
  fields were read successfully.
- #210: `Blocked`, blocked by open #218.
- #218: `Inbox` in BJ Data Platform.
- #237: `Inbox` in BJ Data Platform.
- No lifecycle state or graph edge was changed.

## Runtime restoration

- Python: 3.14.4
- Pinned imports verified: Flask 3.1.3, NumPy 2.4.6, pandas 3.0.3,
  SciPy 1.17.1, scikit-learn 1.9.0, PyTorch 2.13.0+cpu
- `pip check`: no broken requirements
- Dashboard frontend: 26 tests passed and production build completed
- Dashboard/collector regression tests: 135 passed
- #249/#400 focused tests: 15 passed
- Cutoff governance: `PASS`

Migration exposed one missing runtime dependency: `scripts/live_sp_refresh_loop.py`
imports PyYAML but `requirements.txt` did not declare it. The checkout now pins
`pyyaml==6.0.3`.

## Data and research verification

Both restored key databases returned `PRAGMA integrity_check = ok`:

- `data/derived/500_bjdc/500_bjdc.sqlite`
- `data/beidan_live.db`

The #400 immutable package passed manifest, implementation, semantic, and
no-replay verification:

```text
status=PASS variants=21 bundle_rows=6174 ticket_rows=406504 source_bound_replay=false
```

Full source-bound replay correctly failed closed because the accepted snapshot
ends on 2026-08-20 while #400 consumed evidence through 2026-08-25. The mismatch
was isolated to the data-derived frames:

| Source hash | Stored #400 | Recovered 2026-08-20 data |
|---|---|---|
| `extension_panel_sha256` | `a0726f101cb248c756a9a59e638887c0c12842d66b96dac8cde8392e0da33bbb` | `3bb3b0828455625ea6f55c043f40981f0beeb45aefc7d8fb4f7bfa2bbf01e43f` |
| `learning_history_frame_sha256` | `87b62d5a0cc9eb9f87f02e689b98506ce928c2ff7b6094a33ca2f6a2b648147e` | `a7f73c7c9c356d7ecc4bda7816c28c5d1955d6bd75ae8c86f86ef62adde5a416` |

The base-history and extension-settlement hashes matched. The mismatch must not
be waived or rewritten as a successful full replay.

## Collector validation

The one-shot live collector succeeded against current issue `26088`:

- 84 discovered matches
- 84 snapshot rows inserted
- 54 rows with complete 3-SP vectors
- 32 settlement rows present after collection
- Current-issue SP refresh completed with 84 HTML rows and 420 live-SP match rows

The restored machine has no 500.com cookie file, so volume-percentage fields are
currently blank (`0` complete volume-percentage rows). This is an explicit data
coverage limitation, not a zero signal.

Four user services were adapted to the actual checkout path, validated, enabled,
and started:

- `beidanlot-sp-refresh.service`
- `beidanlot-score-refresh.service`
- `beidanlot-score-model-odds-refresh.service`
- `beidanlot-correct-score-price-refresh.service`

All four report `enabled` and `active`; user lingering is enabled. The tracked
unit templates gained `WantedBy=default.target` because the original files had
no installation target and therefore could not persist through `systemctl enable`.

## Dashboard validation

- React tests: 26 passed
- Production build: `apps/decision-dashboard/dist`
- Flask `/healthz`: HTTP 200
- Flask `/`: HTTP 200
- `/api/issues?include_replay=0`: HTTP 200, 80 issues
- `/api/issues/current/dashboard?view=summary`: HTTP 200, 84 matches

No dashboard server was exposed publicly. Private gate/operator environment files
were not present in the migration media and were not invented during recovery.

## Remaining limitations

1. Full #400 source replay cannot pass without the missing 2026-08-21 through
   2026-08-25 source-complete data. The user accepted the 2026-08-20 rollback
   boundary.
2. Volume-percentage collection remains unavailable until the 500.com cookie is
   restored through a private channel.
3. Dashboard gate/operator secrets remain unset; do not expose the API or static
   dashboard beyond loopback until private configuration is installed.
4. The local tracked dependency and systemd-template repairs require normal PI
   review before merge.
5. No research candidate gained release, betting, frontend-selectability, or ROI
   authority from this migration.
