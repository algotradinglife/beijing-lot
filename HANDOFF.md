# HANDOFF — Issue #369 support-shape factorial

[SESSION] 20260824_183532_f2db47

## HEAD / deliverable

- Branch: `analyst/bj369-support-shape` (based on `pi/bj366-n7-chronology-sync` @ 406472a — the corrected N7 package source; stacks on PR #368 which is open/unmerged).
- Package: `results/n7_support_shape/` (18 artifacts + MANIFEST).
- Code: `src/n7_support_shape/{contract.py,pipeline.py}`, `scripts/{run,verify}_n7_support_shape.py`, `tests/test_n7_support_shape.py` (verifier + tamper + oracle).
- Notebook: `notebooks/research/n7-support-shape/n7_support_shape.ipynb` (executed).
- Report: `docs/research/Issue-369-N7-Support-Shape.md`.
- Contract: BJ-UNIFIED-N7-SUPPORT-SHAPE-001/v1; mode exploration; no method.yaml frozen.

## Completed

1. Replay #366 deterministic frames (verify_package PASS + frame-hash equality vs results/n7_chronology_sync/MANIFEST.json).
2. Per base+issue: initial supports taken EXACTLY from #366 decisions.support_json (R0 all-baseline; R3 baseline/qeu on the 3 pressure legs); contraction_score = max(p_supported)/sum(p_supported), retained = argmax q_eu; expansion_score = q_eu(omitted); rank desc with deterministic component+fixture-id tie breaks; disjoint ordered pair (c,e) by lexicographic (rank_c+rank_e, max, rank_c=contraction rank of c, rank_e=EXPANSION rank of e, c_id, e_id) — frozen across the 4 shape arms. (r1: fixed the rank_e bug caught by independent codex audit: e's rank must come from the expansion ranking, not the contraction ranking.)
3. 8 arms: CONTROL 128x4, CONTRACTION_ONLY 64x8, EXPANSION_ONLY 192 (units 128x3+64x2), BOTH 96 (32x6+64x5); extra units to lowest SHA-256(CONTRACT|issue|base|shape|ticket_code) per issue; fractional counterfactual 512/K units/ticket; per-issue stake exactly CNY 1,024 (integer and fractional).
4. Complete-ticket settlement with 0.65 exactly once; CNY100k capital; #366-identical risk metrics.
5. Controls EXACTLY reproduce #366: R0 CONTROL = -15,993.94; R3 CONTROL = +32,689.13.
6. Matched contrasts on the exact-common denominator (151 issues, identical across all 8 arms): within-base main effects + interaction; within-shape R3-R0 lifts; ex-largest-abs-paired-delta; 2,000-draw issue bootstrap (seeds 369_001 + crc32(contrast)).
7. OOF 2017-2021 diagnostic (runs FIRST, before evaluation paths are consumed): contraction scores PASS both bases (monotone 0.81/0.88, calibrated); expansion scores FAIL both bases (monotonicity ~ -0.02 / 0.25; bin cal err 0.17-0.20) — third-outcome probability systematically under-predicts realized rate. Reported, not repaired (decision.evidence_limitation = DEV_DIAGNOSTIC_FAIL_REPORTED_NOT_REPAIRED; thresholds echoed in decision/dev receipts).
8. Mechanism attribution is causal (events counted only on shapes that perform the op): contraction coverage loss = CONTRACTION_ONLY/BOTH, event = realized(c) == dropped (non-retained) outcome; expansion rescue = EXPANSION_ONLY/BOTH, event = realized(e) == omitted third outcome.
9. Expert admission gate: NO treatment shape qualifies → NON_PROMOTABLE_HISTORICAL_EVIDENCE.

## Corrected scientific results (after r1 rank_e fix)

8-arm ALL PnL (151 issues each):
- R0: CONTROL -15,994 | CONTRACTION_ONLY +16,683 | EXPANSION_ONLY -27,927 | BOTH -19,484
- R3: CONTROL +32,689 | CONTRACTION_ONLY +15,991 | EXPANSION_ONLY +31,067 | BOTH +70,886

Main effects / interaction (matched, per issue, 151 issues):
- R0 contraction +32,677 (median +33,335); R0 expansion -11,933; R0 interaction -24,234
- R3 contraction -16,698 (median -8,736); R3 expansion -1,622; R3 interaction +56,517 (p05 +6,291 — sign-robust)
- Within-shape R3-R0: CONTROL +48,683 (= #366 lift); CONTRACTION_ONLY -693; EXPANSION_ONLY +58,994; BOTH +90,369

Mechanism: R0 contraction coverage-loss 34 issues (+52,976 gross delta); R3 29 issues (+102,006); R3 BOTH rescue 51 issues (+108,705, vs +54,086 expansion-only) — contraction concentrates stake so rescue pays more when retained c hits. Integer-vs-fractional deltas small; integer allocation not the driver.

OOF diagnostic: contraction PASS both bases; expansion FAIL both bases (see Known issues).

Expert gate: R3 BOTH has aggregate +70,886, standalone ex-largest +21,631, matched lift +38,197, ex-largest matched lift +99,135, annual lifts 2/3 — but bootstrap p05 = -108,149 (single large negative paired delta dominates resampling) → not promotable. All other treatment arms fail earlier criteria. Verdict NON_PROMOTABLE_HISTORICAL_EVIDENCE.

## Key decisions / rationale

- Support-shape scores use q_eu ONLY; outcomes never enter (c,e) selection; enabled by tamper 4b + oracle tests.
- Per-base initial support = #366 decisions.support_json (frozen package) — the factorial operates on the corrected-N7 expert interface exactly; R3's pressure-leg qeu insurance is its initial two-outcome state.
- rank_e fields: r1 fix (independent codex audit caught the bug) + brute-force oracle test added.
- Expansion FAIL is pre-registered, honest; reported not repaired; it caveats every expansion-arm result.
- Verifier cross-reconciles every artifact file against the deterministic rebirth (defeats forged-manifest re-hash, REQ-E06 class 3), plus #366 replay + per-file manifests + tamper tests incl. future-information injection.
- PR stacks on #368 (unmerged). If #368 merges first, diff collapses to #369-only files.

## Known issues / risks

- Expansion score OOF diagnostic FAILS (reported, not repaired) → expansion-based promotion unsupported; verdict already accounts for it.
- R3 BOTH's matched lift is dominated by a large negative paired delta; bootstrap p05 heavily negative; single-outlier sensitivity disclosed.
- R3 CONTRACTION_ONLY: longest losing run 31, 50% max DD (risk amplification).
- 2022-2024 exposed evidence, no holdout; nothing tuned on 2022-2024.

## Next

- PI review: merge #368 first (or retarget), then merge #369; closure by PI. EV optional post-merge per deployed finalize_delivery.