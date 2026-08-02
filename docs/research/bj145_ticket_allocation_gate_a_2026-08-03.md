# #145 Gate A — calibrated ticket allocation freeze

## Boundary

This is an outcome-unexposed allocation freeze for `BJ-HIST-TICKET-ALLOCATION-001`.
It is separate from #134's fundamental overlay and does not reopen #137/#151
candidate selection. The controlling primary identity is the accepted #151
`NO_GATE/K4` candidate. The only secondary identity sensitivity is the exact
#137 `ESP300_GM290/K8` participation list. Both preserve complete issue units;
source segments are not selection units.

The package is `results/bj145_gate_a_preoutcome_v5` with manifest
`7fd0432e6af30f26a2ebc59e7f5c0846a4b8b8af4c368cd8a5b1c57afc99ab44`.
It contains 696 issue-arm rows, 3,540 selected identities, 24,780 role rows,
and 1,006,416 allocation-plan rows. The primary arm has 339 available and 9
explicit K4 no-bets; the secondary arm has 273 available and 75 explicit K8
no-bets.

## Frozen comparison surface

The same identity lists, issue stake rule and six probability/value sources are
retained across:

- `MODEL_P_CAL`, `MARKET_WF_CAL`, `BLEND_A25`, `BLEND_A50`, `BLEND_A75`, and
  `Q_WEIGHT`;
- weighted WR duplicate-stake and weighted WOR-distinct draws using the exact
  #137 namespace and seeds `137001`, `137002`, `137003`;
- deterministic residual/systematic proportional allocation;
- capped proportional repeats with cap `{1,2,4,8}`;
- deterministic top-mass control and exact FULL enumeration.

The low-M surface is `16,32,...,256`; selected convergence controls are
`512,1024,1458,2187`. Each selected N7 identity contributes `M × ¥2`; exact
repeats remain separate tickets. The mechanism contract also records the
expected-unique formula and realized-unique rule for every arm (including
duplicate retention for WR and exact distinctness for WOR/FULL). The package records the per-ticket tax rule
but computes no tax at Gate A and never pools tickets by issue or policy.

The package additionally binds `bj145_allocation_engine.py` (SHA-256 recorded
in `allocation_binding.json`) and six N7 golden-vector fingerprints in
`allocation_golden_vectors.json`. The module implements weighted WR, weighted
WOR, Hamilton residual, iterated capped-Hamilton, deterministic top-mass, and
FULL multiplicities by base-3 ticket ordinal. Gate B must byte-verify this
module and binding before consuming any settled rows.

## Timing and review boundary

All source vectors and seeds are copied from accepted pre-outcome packages.
No score, result code, final/winning SP, settlement, payout, ROI, tax
realization or post-kickoff field is read or emitted. Gate B, if authorized,
must report pre-tax `no_tax_roi` first and individual-ticket tax second, with
mechanism-minus-mechanism and FULL deltas, duplicate/coverage, seed dispersion,
YEAR/FOLD/LOYO, issue bootstrap, largest-issue exclusion and
multiple-comparison controls. No positive historical result is promotion
authority.
