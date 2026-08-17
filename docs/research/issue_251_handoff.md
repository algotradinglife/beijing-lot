# Issue #251 handoff

[SESSION] 20260818_014309_4c1d97

- Base / current pre-delivery HEAD: `d2cc56d` (`engineer/bj234-issue`); delivery commit and PR are recorded in the GitHub handoff comment.
- Implemented `BJ-UNIFIED-CANONICAL-IDENTITY-001-v1` as a candidate. The only automatic fixture identity is `bjfi:<issue_code>:<match_idx:03d>` from an exact populated source slot. It takes no outcome/result/payout input and never accepts fuzzy candidates.
- Full regenerable crosswalk remains external at the path recorded in `results/bj251_canonical_identity_evidence_v1/MANIFEST.json`; Git contains the hash-bound summaries, exception ledger, bounded temporal aliases, executed notebook, reusable code, tests and decision report.
- Current evidence: 214,854 canonical fixtures; 236,327 traces; 2,560 workbook missing-slot rows quarantined; 18,349 cross-source entity-alias conflicts routed to manual review. `beidan_history_db` is settlement-only and must not become an inference input.
- Verification: `python -m pytest tests/test_bj251_canonical_identity.py -q` (12 passed); `python scripts/build_bj251_canonical_identity.py --verify-only` (verified); `python scripts/execute_bj251_notebook.py` (executed via dependency-free fallback). Tamper tests cover trace rewrite, manifest rewrite plus recomputed checksums against a trusted anchor, outcome/payout injection, fuzzy candidate, temporal overlap and missing/duplicate M×3 cells.
- PI decisions still required: accept `(issue_code, match_idx)` key; acceptable 1.311% historical unmatched rate; alias-review owner/SLA; exceptional-case policy; any source exclusion.
