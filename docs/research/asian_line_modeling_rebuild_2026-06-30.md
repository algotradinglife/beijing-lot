# Asian Line Modeling Rebuild

Date: 2026-06-30

## Scope

This rebuild completes Hermes card `t_7adcb161` after the 2026 Nowscore Asian handicap backfill.

Inputs:

- update DB: `data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite`
- historical modeling DB: `/home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- combined output DB: `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`

Commands run:

```bash
python3 scripts/build_beidan_modeling_tables.py \
  --sqlite data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite

python3 scripts/build_beidan_modeling_plus_update.py \
  --history-db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --update-db data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite \
  --output-db data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite
```

## Validation

SQLite quick check passed: `ok`.

`py_compile` passed for:

- `scripts/build_beidan_modeling_tables.py`
- `scripts/build_beidan_modeling_plus_update.py`
- `scripts/backfill_beidan_nowscore_lines.py`
- `scripts/update_beidan_nowscore_sqlite.py`
- `scripts/validate_beidan_nowscore_update.py`

Combined DB row counts:

| table | rows |
|---|---:|
| matches | 201270 |
| market_consensus | 3196316 |
| match_features | 201270 |
| outcome_features | 603810 |
| action_candidates | 1610160 |

Issue coverage:

| scope | min issue | max issue | issues | matches |
|---|---:|---:|---:|---:|
| combined | 140101 | 26051 | 735 | 201270 |
| 2026 update | 26011 | 26051 | 34 | 6001 |

Source meta:

| key | value |
|---|---|
| built_at | 2026-06-30T04:13:04+00:00 |
| history_db | `/home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite` |
| update_db | `data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite` |
| update_match_id_offset | 195269 |

## Asian Handicap Coverage

The rebuild adds the 2026 Asian handicap consensus rows to the combined DB. The full combined DB now has one `asian_handicap` consensus row per match per snapshot.

| scope | snapshot | matches | rows | complete bookmaker rows | v2_avg matches | avg abs line gap |
|---|---|---:|---:|---:|---:|---:|
| combined all | 10h | 201270 | 201270 | 2424480 | 196633 | 0.2797 |
| combined all | 1h | 201270 | 201270 | 2473499 | 198549 | 0.2893 |
| combined all | final | 201270 | 201270 | 2424515 | 198564 | 0.2960 |
| combined all | initial | 201270 | 201270 | 1914726 | 198564 | 0.2839 |
| update 2026 | 10h | 6001 | 6001 | 57287 | 5999 | 0.2646 |
| update 2026 | 1h | 6001 | 6001 | 57322 | 5999 | 0.2646 |
| update 2026 | final | 6001 | 6001 | 57322 | 5999 | 0.2646 |
| update 2026 | initial | 6001 | 6001 | 57322 | 5999 | 0.2708 |

`line_gap` is not materialized as a separate table in this card. Downstream scripts already compute it from:

```sql
(-match_features.handicap_line_norm - market_consensus.v2_avg)
```

for `market_consensus.market='asian_handicap'`.

Two 2026 matches have `asian_handicap` rows but no usable `v2_avg` line values across all snapshots, so downstream line-gap logic should treat them as unknown:

| issue | match_idx | league | home | away | handicap_line_norm |
|---|---:|---|---|---|---:|
| 26018 | 58 | 芬联杯 | 拉赫蒂 | 赫尔辛基 | 1.0 |
| 26051 | 331 | 冰岛超 | IA阿克拉内斯 | 斯塔尔南 | 0.0 |

## Output Files

- `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`
- `results/asian_line_modeling_rebuild_20260630/coverage_summary.csv`
- `results/asian_line_modeling_rebuild_20260630/missing_line_gap_2026.csv`

## Next Step

Hermes card `t_f7482aec` can now run the post-backfill strategy replay:

1. q/conf/drift joint rows.
2. high-N selector with line-gap diagnostics.
3. N5 overlap sleeve.
4. core ticket protection.
5. fixed-256 allocation grid.
6. large protection overlay.
7. final sleeve mix.
