# #137 Gate B v3r1 — report-only common-support correction

This immutable derivative reads and verifies the v3 parent package only. It does not reopen Gate A, resample tickets, alter the v2r1 ledger, recompute common-support effects, or change the candidate rule.

## Primary economic scale and attribution

All rankings below use pre-tax `no_tax_roi` / `no_tax_roi_delta`: the Beijing Single Match 0.65 factor is already included in gross payout, while the per-ticket 20% tax remains a secondary execution sensitivity. The selector comparison is FULL K versus same-gate K_ALL FULL; sampler attribution is the sampler versus exact-K FULL on exact common settled complete-issue support.

NO_GATE/K1 FULL versus K_ALL FULL has candidate/baseline/common support 271/187/187; pre-tax delta +1.02pp, tax-adjusted delta +0.10pp. Across all selector groups, 4 are ALL positive and 0 are LOYO-stable; selection alone is not a promoted edge.

## Primary candidate: Q-informed WOR, NO_GATE/K4

`NO_GATE / K4 / Q_INFORMED_WOR_DISTINCT / M64` is the sole all-seed positive absolute pre-tax candidate. It has 254 matched complete issue instances per seed and remains a strict-independent-EV candidate only; it has no promotion authority.

| M | seed 137001: ROI / delta | seed 137002: ROI / delta | seed 137003: ROI / delta | worst LOYO delta |
| ---: | --- | --- | --- | ---: |
| 32 | -21.24% / -5.47pp | +35.61% / +51.38pp | -24.15% / -8.38pp | -26.42pp |
| 64 | +16.38% / +32.15pp | +11.77% / +27.54pp | +2.67% / +18.44pp | +8.08pp |
| 128 | -4.12% / +11.65pp | +4.47% / +20.24pp | +2.23% / +18.00pp | +5.40pp |
| 256 | -1.51% / +14.26pp | -8.53% / +7.24pp | -30.25% / -14.48pp | -22.60pp |

The M64 pre-tax ROI is +16.38% / +11.77% / +2.67%, with matched sampler-minus-FULL lift +32.15pp / +27.54pp / +18.44pp. Its tax-adjusted ROI remains secondary: +5.06% / +5.95% / -3.02%.

## Secondary ESP300/GM*/K8/Q/M128 sensitivity

This is a lower-concentration, near-break-even diagnostic only, not a replacement candidate. Its concentration is not available in v3 `candidate_fragility.csv`, which was contractually emitted for absolute-edge candidates only.

| gate | matched support by seed | pre-tax ROI (137001/2/3) | matched pre-tax lift (137001/2/3) | worst LOYO lift |
| --- | --- | --- | --- | ---: |
| ESP300_GM290 | 191 / 191 / 191 | +4.46% / -2.23% / +4.46% | +20.58% / +13.89% / +20.58% | +5.90pp |
| ESP300_GM300 | 191 / 191 / 191 | +4.46% / -2.23% / +4.46% | +20.58% / +13.89% / +20.58% | +5.90pp |
| ESP300_GM305 | 191 / 191 / 191 | +4.46% / -2.23% / +4.46% | +20.58% / +13.89% / +20.58% | +5.90pp |

## Probability-vector and draw-mechanism surface

Counts below are distinct gate × K × sampler × M groups in the sampler-minus-exact-FULL surface. `ALL positive` requires every frozen seed (or the deterministic no-seed row) to have a positive pre-tax delta; `LOYO stable` additionally requires every leave-one-year-out row to be positive; `absolute edge` also requires positive pre-tax ROI in every required seed.

| vector | mechanism | seed rule | groups | ALL positive | LOYO stable | absolute edge |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| BLEND_A25 | WEIGHTED_WITHOUT_REPLACEMENT | THREE_FROZEN_SEEDS | 650 | 43 | 0 | 0 |
| BLEND_A50 | WEIGHTED_WITHOUT_REPLACEMENT | THREE_FROZEN_SEEDS | 650 | 51 | 0 | 0 |
| BLEND_A75 | WEIGHTED_WITHOUT_REPLACEMENT | THREE_FROZEN_SEEDS | 650 | 51 | 1 | 0 |
| MARKET_WF_CAL | WEIGHTED_WITHOUT_REPLACEMENT | THREE_FROZEN_SEEDS | 650 | 53 | 0 | 0 |
| MODEL_P_CAL | DETERMINISTIC_TOP_MASS | DETERMINISTIC_NO_SEED | 650 | 102 | 13 | 0 |
| MODEL_P_CAL | GLOBAL_SINGLE_CODE_DELETE | DETERMINISTIC_NO_SEED | 50 | 40 | 16 | 0 |
| MODEL_P_CAL | INDEPENDENT_WITH_REPLACEMENT | THREE_FROZEN_SEEDS | 650 | 57 | 1 | 0 |
| MODEL_P_CAL | WEIGHTED_WITHOUT_REPLACEMENT | THREE_FROZEN_SEEDS | 650 | 98 | 19 | 0 |
| Q_WEIGHT | GLOBAL_SINGLE_CODE_DELETE | DETERMINISTIC_NO_SEED | 50 | 50 | 13 | 0 |
| Q_WEIGHT | WEIGHTED_WITHOUT_REPLACEMENT | THREE_FROZEN_SEEDS | 650 | 111 | 29 | 1 |

The raw ALL-scope maximum is deliberately not promoted: ESP280_GM305/K1/MODEL_P_CAL_WR_DUPLICATE_STAKES/M1/seed 137001 has pre-tax delta +790.06pp, but all-seed=False, LOYO-stable=False, absolute-edge=False. It is a one-row maximum, not the controlling rule outcome.

## Concentration and uncertainty of the primary candidate

| seed | top issue share | ex-largest absolute pre-tax ROI | ex-largest matched delta | worst leave-one-issue-out delta | bootstrap 95% delta interval |
| --- | ---: | ---: | ---: | ---: | --- |
| 137001 | +24.23% | -11.47% | +5.24pp | +5.24pp | -23.64pp to +108.79pp |
| 137002 | +10.82% | +0.08% | +16.67pp | +16.67pp | -15.22pp to +73.40pp |
| 137003 | +12.16% | -9.46% | +7.53pp | +7.53pp | -22.28pp to +66.98pp |

Two ex-largest absolute ROIs are negative; seed 137002 is essentially break-even positive (+0.08%), not negative. All issue-bootstrap intervals cross zero. This is why the correct tier is positive-but-concentrated and strict independent EV is required before any interpretation beyond historical research.
