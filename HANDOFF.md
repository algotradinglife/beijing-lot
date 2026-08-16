# Issue #234 delivery handoff (run 332, retry after run 331 crash)

[SESSION] 20260816_140648

- HEAD: `de81ec2` on `engineer/bj234-issue` (repo base 784a23b)
- PR: https://github.com/algotradinglife/beijing-lot/pull/242 (Closes #234)
- Superseded PR #241 (crashed run 331, off-convention branch) closed.

## What was completed

1. **Executed notebook** `notebooks/research/issue-234/bj234_source_schema.ipynb`
   — 15/15 code cells, 0 errors; read-only census of all 7 databases +
   #203/#214/#229 packages (tables, keys, time ranges, nulls, duplicates,
   source clocks, content hashes).
2. **Immutable package** `results/bj234_source_schema_contract_v1/` (21 files):
   versioned SQL DDL, PyArrow schemas, domain dictionary, identity crosswalk,
   source registry + feasibility matrix, migration-free replacement plan,
   REQ-DS evidence, MANIFEST/SHA256SUMS/REPLAY.
3. **Reusable code** `src/source_schema/` (11 modules) + build/verify/execute
   CLIs.
4. **Tests** `tests/test_bj234_source_schema.py` — 23 passed incl. tamper
   self-tests (REQ-E06).

## Key decisions

- Census resolves gitignored `data/` through `git --git-common-dir` (works
  from a linked worktree); never mutates the DBs (mode=ro).
- Large legacy tables (>=1M rows) skip per-column NULL/DISTINCT scans;
  timestamp columns still measured.
- Legacy identity defects named: beidan_xlsm.matches 2,560 duplicate
  (issue, match_idx) rows; canonical fixture enforces UNIQUE.
- beidan_live.snapshots (1.49M rows, TIMESTAMPED_UTC) = primary prospective
  causal source; workbook labels stay LABEL_RELATIVE/RETROSPECTIVE_PROXY.
- 0.65 payout factor absent from all source/quote/probability tables.

## Known limitations / risks

- Licensed EU feed (Odds API) graded B pending coverage evaluation; no
  provider purchased (issue boundary).
- 500_bjdc.sqlite is 17GB — census hashes it (takes ~1-2 min per build).

## Next steps

- EV independent verification (fresh checkout, focused tests + notebook
  clean-run + manifest coverage).
- Downstream branches (#235/#236/#237/#238) consume
  `contract/downstream_handoff.md` per-branch selected sources.
