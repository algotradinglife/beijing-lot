"""Issue #209 — Unified Learning: divergence-aware M×3 value model, Gate A contract.

Frozen scientific contract for BJ-UNIFIED-FULL-CYCLE-HIST-001 / v3 (PI amendment
2026-08-20, accepted #238 interface). This module is the single source of frozen
semantics: chronological roles, feature surface, model budget, distributional
losses, ticket economics and the Gate-A freeze identity. 2024+ labels stay sealed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

CONTRACT_VERSION: Final = "BJ-UNIFIED-FULL-CYCLE-HIST-001/v3-gate-a"
PI_AMENDMENT: Final = "2026-08-20 accepted #238 interface"
AUDIT_MODE: Final = "exploration"  # exploration: [EVIDENCE] debt trackable; [CONCLUSION] always rejects

# ---------------------------------------------------------------------------
# Source surface (accepted #268/#238)
# ---------------------------------------------------------------------------
REPOSITORY_ROOT: Final = Path(
    os.environ.get("BEIJING_LOT_RUNTIME_ROOT", Path(__file__).resolve().parents[2])
).resolve()
DATA_ROOT: Final = REPOSITORY_ROOT / "data/derived"
BJ238_PACKAGE: Final = DATA_ROOT / "bj238_divergence_materializer_v4r3"
INFERENCE_VIEW: Final = BJ238_PACKAGE / "inference/relative_horizon_view.parquet"
LABELS_PRE2024: Final = BJ238_PACKAGE / "development/labels_pre2024.parquet"
LABELS_SQLITE: Final = DATA_ROOT / "beidan_xlsm/beidan_xlsm.sqlite"

OUTCOMES: Final = ("3", "1", "0")          # Beijing native handicap W/D/L
HORIZONS: Final = ("initial", "10h", "1h")  # relative-horizon EU proxies
CAUSAL_GRADE: Final = "RETROSPECTIVE_RELATIVE_PROXY"

# Chronological roles (frozen; never silently moved)
FIT_END: Final = "2021-12-31 23:59:59"
TUNE_YEAR: Final = 2022
CALIBRATION_YEAR: Final = 2023
SEALED_START_YEAR: Final = 2024            # labels MUST stay sealed in Gate A
SEALED_ISSUE_MIN: Final = 23114            # first 2024 issue code (2311+ -> 2023-12; 240x -> 2024)

# Probability source channels (first-cycle, per PI amendment)
# q_bj_sp_devig does NOT exist -> null. q_line_only_control is a coarse line prior.
PROBABILITY_FEATURES: Final = (
    # outcome-level per-cell probabilities (long-atom features area)
    "q_eu_raw_1x2",
    "q_line_only_control",
    "q_eu_bjline",
    "q_eu_bjline_candidate_diagnostic",
)
DISAGREEMENT_CHANNELS: Final = (
    "eu_vs_line_divergence",   # q_eu_bjline - q_line_only_control (REQ-209-03)
)
CONTEXT_FEATURES: Final = (
    "native_handicap_line",
    "n_available_books",
    "snapshot_kind_initial",
    "snapshot_kind_10h",
    "snapshot_kind_1h",
    "mapping_accepted",
)

# Settlement label columns
SP_COLUMNS: Final = ("official_sp_3", "official_sp_1", "official_sp_0", "winning_sp")

# ---------------------------------------------------------------------------
# Distributional learning (REQ-209-04)
# ---------------------------------------------------------------------------
# Decomposed objectives; a single MSE against Y×SP is explicitly forbidden.
OUTCOME_LOSS: Final = "categorical_cross_entropy"   # + Brier + ECE
SP_LOSS: Final = ("quantile", "huber")               # maintained-library robust losses
VALUE_LOSS: Final = ("gaussian_nll", "huber")        # distributional value
QUANTILES: Final = (0.10, 0.50, 0.90)

# Model budget (frozen before fitting; REQ-209-04/05)
MODEL_BUDGET: Final = {
    "baselines": ("MARKET_ONLY_CELL", "CALIBRATED_LOGISTIC"),
    "tree": "HIST_GRADIENT_BOOSTING",   # at most one, if deps support
    "neural": "PYTORCH_MLP",
    "max_neural_hidden": (64, 64),
    "max_epochs": 30,
    "lr": 1e-3,
    "batch_size": 256,
    "seed_count": 3,
    "tune_grid": 8,                     # bounded hyperparameter budget
}

# Bankroll / ticket economics
INITIAL_BANKROLL: Final = 100_000.0
TICKET_STAKE: Final = 2.0                # CNY2 granularity
TAX_FACTOR: Final = 0.65                 # applied ONCE per winning N-fold ticket
N_RANGE: Final = (3, 5, 7, 8)            # bounded experimental action anchors
K_RANGE: Final = (8, 32, 128, 512)       # anchors, not an operational stake cap
POLICIES: Final = (
    "DIV_LEARNED_VALUE",
    "MARKET_ONLY_CELL",
    "BEST_FULL_LEGACY",
    "CASH_NO_BET",
)

# Required matched controls (contract)
MATCHED_CONTROLS: Final = (
    "MARKET_ONLY_CELL",
    "BEST_FULL_LEGACY",
    "FIXED_N7_INCUMBENT_#207",
    "FROZEN_UNIFIED_CANDIDATE",
    "CASH_NO_BET",
)

# Determinism
SEEDS: Final = (209001, 209002, 209003)
BOOTSTRAP_DRAWS: Final = 2000
BOOTSTRAP_SEED: Final = 209026

# Legacy BEST_FULL frozen baseline (contract: -9.4679% on exact inherited support)
BEST_FULL_LEGACY_ROI: Final = -0.094679
