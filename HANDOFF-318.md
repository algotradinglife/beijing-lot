# Issue #318 PI takeover handoff

- Contract: `BJ-UNIFIED-SP-PROXY-AUDIT-001/v1`
- Delivery PR: #320
- Terminal disposition: `NO_CAUSAL_PRICE_SUPPORT`
- Manifest SHA-256: `144096904442a57d506faa986887ea628d051c6952b3af1d3c71cf8b8509a15b`

## Superseded delivery

The original package treated data absent from an isolated worktree as globally
missing, consumed most sources only as inventory, counted unusable vectors as
N7-feasible, permitted duplicate M×3 keys and rendered placeholder figures.
The PI R1 takeover replaces that package in full.

## Final evidence

- All six frozen sources are present, bound and consumed read-only.
- 2,724,201 graded cells; 1,916,376 accepted proxy cells; 822 accepted strict
  cells; 2,466 strict/proxy overlap cells across one issue.
- All three proxy horizons fail the frozen scientific thresholds. Strict
  historical coverage is zero in development/validation/terminal partitions.
- Exact-key M×3 atomicity, accepted-only N7 capacity, issue-equal metrics,
  2,000 issue bootstrap draws and terminal disposition are computed, not
  hard-coded.
- The notebook contains executed completeness, coverage, overlap, distortion,
  exclusions and decision sections with four real figures.
- Two consecutive full replays are byte-identical:
  - package manifest: `144096904442a57d506faa986887ea628d051c6952b3af1d3c71cf8b8509a15b`;
  - notebook: `17e4a4abd19851eda7aa550fe93c99402673a53a9d240393d7065bdfcd5b57a5`.
- Focused adversarial tests: 8 passed. Package verifier: PASS.

## Successor boundary

#319 may proceed using probability-only stable-center inputs. Historical
Beijing-SP value ranking and the evaluated European fair-odds proxy are not
admissible. #218 continues prospective strict-SP accumulation independently.
