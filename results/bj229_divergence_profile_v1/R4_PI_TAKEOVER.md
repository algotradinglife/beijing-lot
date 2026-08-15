# Issue #229 R4 PI takeover

## Root cause

R3 answered the wrong readiness question. It treated 228 causally available
`Q_BJ_CALIBRATED` cells as a usable handoff even though the downstream learner
needs a pre-event SP and an independent probability estimate in the same
Beijing handicap-result space. Independent recomputation showed:

- `Q_BJ_CALIBRATED × Q_EU_BJLINE`: 0 cells;
- `Q_BJ_CALIBRATED × P_POWER_BJLINE`: 0 cells;
- `Q_BJ_CALIBRATED × Q_BJ_SP_DEVIG`: 0 cells;
- therefore every SP-backed divergence interface: 0 cells.

The second conclusion-affecting defect was reusable POWER materialization:
the source `handicap_line_norm` was discarded before merge, so a future source
refresh could silently combine a probability vector from one handicap line
with a target cell from another.

## Candidate-mode correction

1. Readiness now requires positive causal `Q_BJ × SP` support and at least one
   positive SP-backed independent divergence pair (`Q_BJ × EU × SP` or
   `Q_BJ × POWER × SP`). Anchor-only support is always
   `BLOCKED_DATA_DEFECT`.
2. POWER retains and compares its source handicap line against
   `BJ_LINE_BOUNDARY`; mismatches publish no probability vector and carry
   `SOURCE_HANDICAP_LINE_MISMATCH`.
3. Empty chart sources now publish `UNAVAILABLE`, a stable reason and a row
   count instead of being labelled `BOUND`.
4. The independent package verifier recomputes the same readiness rule and
   source-line boundary.

The contract audit mode is `candidate`: conclusion and reusable-interface
correctness are mandatory. Evidence-only hardening is explicit in
`DEBT-LEDGER.md` and must close at `finalize`.

