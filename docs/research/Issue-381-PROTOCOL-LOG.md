# Issue #381 — PROTOCOL-LOG

Contract: `BJ-UNIFIED-N6-CORRECTED-ALL-R-001/v1`. Append-only interpretation record; new entries
`supersede` earlier rows where noted.

## Entry 001 — Fixed-R replacement-rule interpretation disclosure

- **Date / artifact**: 2026-08-24, Issue #381 build (analyst/bj381-n6-all-r branch).
- **Frozen text**: "fixed R means replace the second outcome with the
  QEU-ranked omitted outcome on the top-R support-pressure legs, with set-based
  saturation disclosed."
- **Applied reading**: the replacement is the accepted corrected #376 QEU Top-2
  transfer: on an activated leg the active support becomes
  `OUTCOMES - qeu_worst`, i.e. the baseline pair member that QEU ranks second
  is replaced by the QEU-ranked omitted outcome whenever the omitted outcome
  ranks above it (support pressure > 0). The dropped member can therefore be
  the probability-first pair member while still being QEU-second; on
  pressure-zero activated legs the support is unchanged (noop activation).
- **Why**: the issue requires exact R0/R3 parity with the corrected #376
  package; #376's accepted fixed-R3 definition IS the QEU Top-2 transfer.
  A literal "always keep the probability-first member" swap would break that
  parity on the 166 legs where the
  dropped member is the probability-first pair member.
- **Disclosure table (settled panel)**:
  - replaced legs total: **1643**
  - dropped member is the probability-first pair member: **166**
  - activated no-op legs (activated, support unchanged): **1969**
  - candidate (omitted-outcome) set size: max **1** (Mx3 => always 1)
  - set-based saturation events: **0** (structural zero)
- **Status**: interpretation recorded; no frozen numerical parameter changed.
  May be superseded only by a PI ruling amending the contract text.
