# Issue #250 R3 handoff

[SESSION] 20260817_184756_9b3b73

## Delivery state

- Branch: `engineer/bj250-rework-r1`, updating PR #255.
- Base: `engineer/bj234-issue`; prior rejected head: `75a2b83667de0dfbd2b2ca018937d4fd033a9ce1`.
- Evidence package: `results/bj250_source_census_v2`.
- External verification input: an EV-supplied trusted-anchor JSON stored outside this worktree/package; it is intentionally not generated or committed by this builder.
- Executed notebook: `notebooks/research/issue-250/bj250_source_census.ipynb`.
- External data contract: `BEIJING_LOT_DATA_ROOT` is mandatory; each SQLite source is opened with URI `mode=ro`.

## R2 reject: root-cause classes and complete class sweep

| Defect class | R3 correction | Complete same-class sweep |
| --- | --- | --- |
| Key/grain collapse | Explicit p34 logical-match (`issue,row_idx`), snapshot (`issue,fetched_at,row_idx`), and cell (`issue,playid,fetched_at,row_idx,outcome_code`) primitives. | `_source_aggregate`, `_coverage_count_expr`, `_coverage_row`, `_duplicate_profile`, `_m_per_issue`, `_snapshot_completeness`, field tables, figures, report, notebook and verifier inputs. `playid` is no longer used as a match key. |
| Role fail-open | `role_from_profile` returns `RECOVER` for unprofiled coverage and demotes an empty historical-proxy surface to `RAW_ONLY`. | All seven `SourceSpec` paths, missing-table path, proxy triplet path, strict clock path, derived-lineage path, source role matrix and downstream routing. |
| Role collapse / leakage | `field_inventory.csv` now gives every discovered table/column `admissible_use` plus `terminal_denylisted`; final/official/winning SP and result-derived fields are `SETTLEMENT_ONLY`. | All table/column enumeration, field-family classifier, source-feature view, source-role matrix, decision report and terminal denylist tests. |
| Verifier closure | A required, independently supplied trusted anchor binds all package payload semantic hashes and the producer implementation hash; the builder cannot create it. | Manifest, checksum inventory, all decision tables, evidence, figures, report and re-signed manifest mutation path. |

This assessment stays read-only and assessment-only. It does not use label values to choose feature availability, and it makes no identity/temporal/schema policy decision.

## Key decisions / risks for PI and EV

- `initial`/`10h`/`1h` remain historical relative-time proxies, not strict observations.
- Final, official, winning-SP, score, result, settlement, payout, hit/profit/ROI and halftime fields are terminal-denylisted even when they coexist with proxy fields.
- Candidate identity ranges remain non-authoritative pending #251; canonical causal overlap remains `NOT_YET_EVALUATED` pending #251 + #252.
- Mutable live inputs remain `RAW_ONLY` or `MUTABLE_UNFROZEN`; a dynamic count is not a freeze receipt. #252 owns source/capture-clock sealing criteria.
- The trusted anchor must be independently generated and held outside the builder/worktree. A verifier without it fails closed; a builder-generated anchor would not resist a full re-sign attack.

## Verification to rerun

```bash
BEIJING_LOT_DATA_ROOT=/home/drwho1985/workspace/soccer/beijing-lot/data \
  /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/build_bj250_source_census.py
BEIJING_LOT_DATA_ROOT=/home/drwho1985/workspace/soccer/beijing-lot/data \
  /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/execute_bj250_notebook.py
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/build_bj250_source_census.py --verify-only --trusted-anchor /outside/package/expected-anchor.json
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python -m pytest tests/test_bj250_source_census.py -q
```

## Next action

After the external-root build and notebook finish successfully: inspect generated R3 package rows and anchor, commit all evidence, push the existing PR #255 head, post the delivery/handoff block, and self-transition #250 to `EV Review`.
