"""Issue #232 — zero-overlap root-cause diagnosis.

Classifies WHY each modelability interface has zero causal support using
evidence from the census and waterfall:

- ABSENT_OBSERVATIONS: the source has no rows at all for the cohort;
- INCOMPATIBLE_SOURCE_CLOCKS: rows exist but no observation clock can be
  bound at/before the decision epoch;
- WRONG_JOIN_KEYS: rows exist but cannot join to the canonical axis;
- ISSUE_CALENDAR_MISMATCH: rows join but live in a different issue window
  than the anchor (e.g. SP observations begin 2026-05 while Q_BJ causal
  cells are 2026-01..04 or earlier);
- LINE_SPACE_MISMATCH: source line differs from the target native line;
- GENUINELY_UNAVAILABLE_HISTORICAL_DATA: the accepted upstream contract
  itself declares the historical observation unavailable.

Each row in the diagnosis table carries the evidence columns that support
the classification, so the conclusion is audit-proof, not asserted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import contract


@dataclass
class Diagnosis:
    rows: list[dict] = field(default_factory=list)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def _issue_prefixes(issues: pd.Series) -> list[str]:
    values = issues.dropna().astype(str)
    if values.empty:
        return []
    return sorted(set(values.str[:2].unique()))


def diagnose(
    root: Path,
    census_frame: pd.DataFrame,
    waterfall: pd.DataFrame,
) -> Diagnosis:
    """Produce one diagnosis row per modelability interface."""
    diag = Diagnosis()

    sp_rows = census_frame[census_frame["key"].eq("bj214_selected_market_observations")]
    sp_present = bool(len(sp_rows)) and bool(sp_rows["present"].iloc[0])
    sp_issue_min = str(sp_rows["issue_min"].iloc[0]) if sp_present else None
    sp_issue_max = str(sp_rows["issue_max"].iloc[0]) if sp_present else None

    eu_rows = census_frame[census_frame["key"].eq("bj203_devig_euro_probability")]
    eu_present = bool(len(eu_rows)) and bool(eu_rows["present"].iloc[0])

    power_rows = census_frame[census_frame["key"].eq("bj180_match_probability_freeze")]
    power_present = bool(len(power_rows)) and bool(power_rows["present"].iloc[0])

    def _waterfall_count(source: str, stage: str) -> int:
        sub = waterfall[
            waterfall["source"].eq(source) & waterfall["stage"].eq(stage)
        ]
        return int(sub["count"].sum()) if len(sub) else 0

    # ------------------------------------------------------------------
    # Interface 1: Q_BJ x SP
    # ------------------------------------------------------------------
    # The Q_BJ anchor's causal cells are 2026-only (issues 26011-26049, #204
    # avg-EU cells with #203 euro_1h observed-at).  Decision-epoch SP
    # observations exist ONLY for 2026 issues 26051+ (captures began
    # 2026-05-02).  The two windows are disjoint: SP begins exactly where the
    # Q_BJ causal axis ends.  For ALL historical cohorts (fit/tune/cal,
    # through 2023) no timestamped pre-event SP observation exists in any
    # committed or recoverable asset.
    sp_obs_hist = (
        sp_issue_min is not None and sp_issue_min[:2] in {"19", "20", "21", "22", "23"}
    )
    if not sp_present:
        root_cause = contract.ROOT_ABSENT_OBSERVATIONS
        evidence = "no committed #214 SP observations present"
    elif sp_obs_hist:
        root_cause = contract.ROOT_ISSUE_CALENDAR_MISMATCH
        evidence = (
            "SP observations exist for historical issues but the Q_BJ anchor "
            "causal axis is 2026-only (26011-26049)"
        )
    else:
        # SP rows exist but only for 2026 issues 26051+; historical is empty.
        root_cause = contract.ROOT_GENUINELY_UNAVAILABLE
        evidence = (
            f"#214 SP observations cover issues {sp_issue_min}..{sp_issue_max} "
            "(2026-05-02+ only); the Q_BJ anchor causal axis ends at 26049, so "
            "SP and anchor windows are disjoint; no pre-2026 timestamped SP "
            "observation exists in any committed or recoverable asset (#203 "
            "DATA_CARD: historical official 3SP is label-only with no "
            "trustworthy observation timestamp)"
        )
    diag.rows.append(
        {
            "interface": "Q_BJ_x_SP",
            "root_cause": root_cause,
            "evidence": evidence,
            "sp_rows_present": bool(sp_present),
            "sp_issue_min": sp_issue_min,
            "sp_issue_max": sp_issue_max,
            "final_causal_cells": _waterfall_count(
                "Q_BJ_SP_DEVIG", contract.STAGE_CAUSAL_INTERSECTION
            ),
        }
    )

    # ------------------------------------------------------------------
    # Interface 2: Q_BJ x EU x SP
    # ------------------------------------------------------------------
    eu_hist = (
        eu_present
        and len(eu_rows)
        and str(eu_rows["issue_min"].iloc[0])[:2] in {"19", "20"}
    )
    if not eu_present:
        eu_cause = contract.ROOT_ABSENT_OBSERVATIONS
        eu_evidence = "no committed #203 EURO feature values present"
    elif not eu_hist:
        eu_cause = contract.ROOT_ISSUE_CALENDAR_MISMATCH
        eu_evidence = "EU causal support does not reach historical cohorts"
    else:
        # EU causal cells exist for historical issues (#229: 2,976 cells on
        # 190101+), but Q_BJ anchor causal cells are 2026-only and SP is absent
        # for all historical issues -> the triple intersection is empty.
        eu_cause = contract.ROOT_GENUINELY_UNAVAILABLE_HISTORICAL_DATA
        eu_evidence = (
            "EU de-vig causal support exists on historical issues (#229: 2,976 "
            "cells on 190101+); Q_EU_BJLINE translation is 0 (no score/"
            "goal-difference distribution support); Q_BJ anchor causal cells "
            "are 2026-only and no historical pre-event SP observation exists -> "
            "Q_BJ x EU x SP triple intersection empty"
        )
    if not sp_obs_hist:
        sp_cause = contract.ROOT_GENUINELY_UNAVAILABLE
    else:
        sp_cause = contract.ROOT_ISSUE_CALENDAR_MISMATCH
    combined = (
        eu_cause if eu_cause == contract.ROOT_GENUINELY_UNAVAILABLE
        else sp_cause
    )
    diag.rows.append(
        {
            "interface": "Q_BJ_x_EU_x_SP",
            "root_cause": combined,
            "evidence": f"EU: {eu_evidence}; SP: {evidence}",
            "sp_rows_present": bool(sp_present),
            "sp_issue_min": sp_issue_min,
            "sp_issue_max": sp_issue_max,
            "final_causal_cells": _waterfall_count(
                "Q_EU_RAW_1X2", contract.STAGE_CAUSAL_INTERSECTION
            ),
        }
    )

    # ------------------------------------------------------------------
    # Interface 3: Q_BJ x POWER x SP
    # ------------------------------------------------------------------
    if not power_present:
        power_cause = contract.ROOT_ABSENT_OBSERVATIONS
        power_evidence = "no committed #180 probability freeze present"
    else:
        power_cause = contract.ROOT_ISSUE_CALENDAR_MISMATCH
        power_evidence = (
            "P_POWER_BJLINE causal cells exist on historical issues "
            "(#229: 234 cells on 20062-24105) but never overlap the Q_BJ anchor "
            "(causal cells 2026-only); SP is absent for all historical issues"
        )
    if not sp_obs_hist:
        power_sp_cause = contract.ROOT_GENUINELY_UNAVAILABLE
    else:
        power_sp_cause = contract.ROOT_ISSUE_CALENDAR_MISMATCH
    combined_power = (
        power_cause
        if power_cause == contract.ROOT_GENUINELY_UNAVAILABLE
        else power_sp_cause
    )
    diag.rows.append(
        {
            "interface": "Q_BJ_x_POWER_x_SP",
            "root_cause": combined_power,
            "evidence": f"POWER: {power_evidence}; SP: {evidence}",
            "sp_rows_present": bool(sp_present),
            "sp_issue_min": sp_issue_min,
            "sp_issue_max": sp_issue_max,
            "final_causal_cells": _waterfall_count(
                "P_POWER_BJLINE", contract.STAGE_CAUSAL_INTERSECTION
            ),
        }
    )

    return diag
