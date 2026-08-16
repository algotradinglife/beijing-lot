"""Issue #232 — zero-overlap diagnosis (contract item 2, R2 fresh).

Reconstructs why the causal intersections are zero from the waterfall
ledger evidence: absent observations, incompatible clocks, wrong join keys,
issue-calendar mismatch, line-space mismatch, or genuinely unavailable
historical data.  All rows derive from the waterfall — no hand-written
conclusions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import contract
from .waterfall import _load_anchor_axis


@dataclass
class Diagnosis:
    rows: list[dict] = field(default_factory=list)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def _drops(frame: pd.DataFrame, stage: str) -> int:
    sub = frame[frame["stage"].eq(stage) & frame["kind"].eq("DROP")]
    return int(sub["count"].sum()) if len(sub) else 0


def _pass_count(frame: pd.DataFrame, stage: str) -> int:
    sub = frame[frame["stage"].eq(stage) & frame["kind"].eq("PASS")]
    return int(sub["count"].sum()) if len(sub) else 0


def diagnose(root: Path, waterfall: pd.DataFrame) -> Diagnosis:
    """Derive root-cause rows from the waterfall ledger."""
    diag = Diagnosis()
    if not len(waterfall):
        return diag

    sp = waterfall[waterfall["source_key"].eq("bj214_selected_market_observations")]
    eu = waterfall[waterfall["source_key"].eq("bj203_devig_euro_probability")]
    power = waterfall[waterfall["source_key"].eq("bj180_match_probability_freeze")]
    official = waterfall[waterfall["source_key"].eq("full_3sp_official")]

    sp_raw = _pass_count(sp, contract.STAGE_RAW)
    sp_identity = _drops(sp, contract.STAGE_IDENTITY_JOIN)
    sp_timestamp = _drops(sp, contract.STAGE_TIMESTAMP_GATE)
    sp_triplet = _drops(sp, contract.STAGE_COMPLETE_TRIPLET)
    eu_raw = _pass_count(eu, contract.STAGE_RAW)
    eu_line = _drops(eu, contract.STAGE_LINE_RECONCILIATION)
    eu_timestamp = _drops(eu, contract.STAGE_TIMESTAMP_GATE)
    power_raw = _pass_count(power, contract.STAGE_RAW)
    power_line = _drops(power, contract.STAGE_LINE_RECONCILIATION)
    power_timestamp = _drops(power, contract.STAGE_TIMESTAMP_GATE)
    official_drop = _drops(official, contract.STAGE_RAW)
    official_reason = (
        official[official["kind"].eq("DROP")]["reason"].iloc[0]
        if len(official[official["kind"].eq("DROP")])
        else ""
    )

    # Q_BJ anchor availability from the canonical axis
    axis = _load_anchor_axis(root)
    anchor_issues = int(axis[axis["qbj_causal_available"]]["issue"].nunique())
    anchor_cells = int(axis["qbj_causal_available"].sum())

    if sp_identity > 0:
        root_class = contract.ROOT_ISSUE_CALENDAR_MISMATCH
        message = (
            "SP rows fail the identity join against the #203 issue calendar; "
            f"drops={sp_identity}"
        )
    elif sp_timestamp > 0:
        root_class = contract.ROOT_GENUINELY_UNAVAILABLE
        message = (
            "SP observations exist for the identity join but fail the frozen "
            "timestamp gate (observed_at <= decision_epoch <= kickoff); "
            f"drops={sp_timestamp}"
        )
    elif eu_line > 0 and power_line == 0:
        root_class = contract.ROOT_LINE_SPACE_MISMATCH
        message = (
            "EU de-vig cells fail the zero-line identity translation; "
            f"line drops={eu_line}"
        )
    elif power_line > 0:
        root_class = contract.ROOT_LINE_SPACE_MISMATCH
        message = (
            "POWER rows fail the exact native-line reconciliation; "
            f"line drops={power_line}"
        )
    else:
        root_class = contract.ROOT_ABSENT_OBSERVATIONS
        message = (
            "No causal observation overlaps the Q_BJ anchor issue space; "
            "the anchor and the SP source occupy disjoint issue calendars."
        )

    diag.rows.append(
        {
            "interface": "Q_BJ_x_SP",
            "root_class": root_class,
            "evidence": message,
            "anchor_issue_count": anchor_issues,
            "anchor_cell_count": anchor_cells,
            "sp_raw_rows": sp_raw,
            "sp_identity_drops": sp_identity,
            "sp_timestamp_drops": sp_timestamp,
            "sp_triplet_drops": sp_triplet,
            "eu_raw_rows": eu_raw,
            "eu_line_drops": eu_line,
            "eu_timestamp_drops": eu_timestamp,
            "power_raw_rows": power_raw,
            "power_line_drops": power_line,
            "power_timestamp_drops": power_timestamp,
            "official_3sp_raw_drops": official_drop,
            "official_3sp_reason": official_reason,
        }
    )
    return diag
