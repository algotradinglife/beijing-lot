"""Issue #306 state-dependent expert composition and dynamic funding intensity.

Frozen hierarchy used by every module in this package:

- Stage A: independent, expert-label-invariant BEST_FULL keep/skip (Issue #305
  contract layer).  The frozen output lives under results/issue-305 when Issue
  #305 has delivered; until then a local reference fit with identical semantics
  (issue features + BEST_FULL labels only, zero expert-label inputs) is used
  and explicitly tagged LOCAL_REFERENCE_FIT_PENDING_305.
- Stage B: shared action-conditioned expert value across the four realizable
  whole-bundle ledgers SMOOTH_M512 / Q_TAIL_M192 / DIVERGENCE_Z100_K1 /
  RARE_LOGIT_TOP64.
- Stage C: composition (relative expert/cash mixture) and intensity (total
  expert bankroll fraction in [0, 1]), learned from issue state and Stage-B
  outputs.  Weights become non-negative integer copies of complete bundles and
  total stake never exceeds current bankroll.
"""

EXPERT_IDS = ("SMOOTH_M512", "Q_TAIL_M192", "DIVERGENCE_Z100_K1", "RARE_LOGIT_TOP64")
CONTROL_EXPERT_IDS = ("FULL_CONTROL",) + EXPERT_IDS
BASELINE_ID = "B0_BEST_FULL"
INITIAL_CAPITAL_CNY = 100_000.0
PREDICTION_YEARS = (2021, 2022, 2023)
SEEDS = (306001, 306002, 306003, 306004, 306005)
PRIMARY = "GUARDED_DYNAMIC_EXPERT"
RAW_PRIMARY = "DYNAMIC_EXPERT"
OBJECTIVES = ("mean", "log_wealth", "downside")