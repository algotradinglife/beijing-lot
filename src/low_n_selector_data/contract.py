"""Corrected scientific contract for Issues #354/#360."""

from __future__ import annotations

CONTRACT_ID = "BJ-UNIFIED-LOWN-CHRONOLOGY-CORRECTION-001/v2"
ISSUE_NUMBER = 360
HORIZON = "10h"
OUTCOMES = ("3", "1", "0")
OUTCOME_ORDER = {"3": 0, "1": 1, "0": 2}

WARMUP_YEARS = (2014, 2015, 2016)
OOF_YEARS = (2017, 2018, 2019, 2020, 2021)
TRANSFER_YEARS = (2022, 2023, 2024)
PANEL_YEARS = OOF_YEARS + TRANSFER_YEARS
SELECTOR_DEVELOPMENT_YEARS = (2019, 2020, 2021)

PROBABILITY_ATOL = 1e-10
MODEL_RANDOM_STATE = 354_2026
CALIBRATION_PRIOR_STRENGTH = 20.0
MASS_BIN_EDGES = tuple(index / 20 for index in range(21))

PROXY_CONTAINER_RELATIVE = "derived/bj268/eu_proxy_backfill_v3"
PROXY_RELATIVE = f"{PROXY_CONTAINER_RELATIVE}/eu_odds_proxy_v3"
CANDIDATE_SQLITE_RELATIVE = f"{PROXY_CONTAINER_RELATIVE}/candidate.sqlite"
LABEL_SQLITE_RELATIVE = "derived/beidan_xlsm/beidan_xlsm.sqlite"
ACCEPTED_238_RELATIVE = (
    "derived/bj238_divergence_materializer_v4r3/"
    "inference/relative_horizon_view.parquet"
)

FEATURE_KEY = ("issue", "issue_year", "issue_anchor_ts", "match_idx")
CELL_KEY = ("issue", "match_idx", "outcome_code")
LABEL_KEY = ("issue", "match_idx")
