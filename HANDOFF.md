# HANDOFF — Issue #394 final delivery

- Contract: `BJ-UNIFIED-N7-MIXED-FULL-HISTORY-001/v1`
- Branch: `analyst/bj394-n7-mixed-full-history-v2`
- Evidence cutoff: `2026-08-25T14:10:00Z`
- Decision: `NO_MIXED_N7_EXTENSION_INCREMENT`

## Delivered

1. Rebuilt frozen corrected-N7 `R3_CONTROL`, `C1E3_SECONDARY`, and the fixed
   integer `MIXED_50_50` portfolio through the evidence cutoff.  The mixed
   portfolio is one CNY1,024 issue-level flow: CNY512 per arm, never CNY1,024
   per arm.
2. Reopened the complete 57-issue 2025 calendar (`25011`–`25125`) using the
   accepted #396 package: 16,117 canonical settlement rows and 120 admissible
   fixture exclusions.  Frozen selection is reconstructed before settlement;
   56 issues settle and only `25094` is excluded because selected fixture 440
   is in the exclusion ledger.
3. Corrected the three post-merge #396 EV findings without changing any
   settlement result or winning SP:
   - Nowscore capture provenance now uses immutable receipt timestamps instead
     of filesystem mtime;
   - issue `25011` fixtures 1–2 resolve to `2024-12-31` via rollover-aware
     parsing;
   - the XLSM lane records its seven exact identity hits while remaining
     explicitly non-admissible for source-native winning SP.
4. Corrected mixed-portfolio path accounting. Performance, drawdown, losing
   runs, underwater duration, concentration, decision gates, and the figure
   now aggregate the two CNY512 arm flows into one CNY1,024 issue flow.
5. Added deterministic source replay, package verifier, executed notebook,
   report, chart, matched contrasts, moving-block bootstrap, settlement and
   selected-fixture receipts, and adversarial tests.

## Scientific result

- Pre-2025 mixed PnL: `+52,666.80` CNY.
- 2025 mixed PnL: `-12,447.48` CNY on 56 settled issues.
- 2026 mixed PnL: `+11,348.53` CNY on 61 settled issues.
- 2025–2026 extension PnL: `-1,098.95` CNY; ex-largest
  `-14,174.27` CNY.
- All-history mixed PnL: `+51,567.85` CNY; ex-largest `+22,122.65` CNY.
- The extension reverses the pre-2025 R3 result, the two extension years have
  opposite signs, bootstrap lower bounds are negative, and the mixed path does
  not reduce maximum drawdown below both standalone arms.  The exposed history
  therefore does not establish a new increment or authorize promotion.

## Evidence boundary and debt

- 2022–2026 outcomes are consumed retrospective evidence; future prospective
  evidence must begin strictly after the recorded cutoff.
- #210 and #218 are unchanged and unconsumed.
- #396 `settlement_availability_ts` remains a conservative source-capture upper
  bound rather than observed first-publication time.  This is acceptable for
  the current retrospective replay but must be closed before fine-grained
  temporal-learning reuse.

## Reproduction

```bash
PYTHONPATH=. python scripts/run_n7_mixed_full_history.py --data-root /path/to/data --force
PYTHONPATH=. python scripts/verify_n7_mixed_full_history.py --data-root /path/to/data
PYTHONPATH=. pytest -q tests/backfill/test_parser.py tests/test_bj396_settlement.py tests/test_n7_mixed_full_history.py
```
