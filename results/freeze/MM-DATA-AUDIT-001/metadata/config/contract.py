"""MM-DATA-AUDIT-001: Data contracts, enums, and market definitions."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ReadinessLevel(str, enum.Enum):
    READY_STRICT = "READY_STRICT"
    PARTIAL = "PARTIAL"
    SETTLEMENT_ONLY = "SETTLEMENT_ONLY"
    UNAVAILABLE = "UNAVAILABLE"


class GateID(str, enum.Enum):
    G1_OUTCOME_VECTORS = "g1_outcome_vectors"
    G2_SOURCE_TIMESTAMPS = "g2_source_timestamps"
    G3_PRE_CUTOFF_EVIDENCE = "g3_pre_cutoff_evidence"
    G4_IMMUTABLE_PROVENANCE = "g4_immutable_provenance"
    G5_ASOF_FREEZE = "g5_asof_freeze"
    G6_SETTLEMENT_MAPPING = "g6_settlement_mapping"
    G7_NO_LEAKAGE = "g7_no_leakage"


class AuditDimension(str, enum.Enum):
    PRE_EVENT_INPUT = "pre_event_input"
    FREEZE_SUPPORT = "freeze_support"
    SETTLEMENT_SUPPORT = "settlement_support"


@dataclass
class MarketDefinition:
    playid: int
    market_key: str
    display_name: str
    outcome_codes: list[str]
    outcome_labels: list[str]
    expected_outcome_count: int
    data_source: str  # 'beidan_live' or '500_bjdc'
    live_sp_table: str  # 'snapshots', 'live_sp_snapshots', or 'live_market_sp_snapshots'

    def __hash__(self) -> int:
        return hash(self.playid)


MARKETS = {
    34: MarketDefinition(
        playid=34,
        market_key="handicap_310",
        display_name="Handicap 3/1/0",
        outcome_codes=["3", "1", "0"],
        outcome_labels=["胜(H)", "平(D)", "负(A)"],
        expected_outcome_count=3,
        data_source="beidan_live",
        live_sp_table="snapshots",
    ),
    40: MarketDefinition(
        playid=40,
        market_key="total_goals",
        display_name="Total Goals",
        outcome_codes=["0", "1", "2", "3", "4", "5", "6", "7+"],
        outcome_labels=["0", "1", "2", "3", "4", "5", "6", "7+"],
        expected_outcome_count=8,
        data_source="500_bjdc",
        live_sp_table="live_market_sp_snapshots",
    ),
    42: MarketDefinition(
        playid=42,
        market_key="correct_score",
        display_name="Correct Score",
        outcome_codes=[
            "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2",
            "0:0", "1:1", "2:2", "3:3",
            "0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4",
            "home_other", "draw_other", "away_other",
        ],
        outcome_labels=[
            "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2",
            "0:0", "1:1", "2:2", "3:3",
            "0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4",
            "主其他(Other H)", "平其他(Other D)", "客其他(Other A)",
        ],
        expected_outcome_count=25,
        data_source="500_bjdc",
        live_sp_table="live_market_sp_snapshots",
    ),
    51: MarketDefinition(
        playid=51,
        market_key="half_full_time",
        display_name="Half/Full Time",
        outcome_codes=[
            "3-3", "3-1", "3-0",
            "1-3", "1-1", "1-0",
            "0-3", "0-1", "0-0",
        ],
        outcome_labels=[
            "胜-胜", "胜-平", "胜-负",
            "平-胜", "平-平", "平-负",
            "负-胜", "负-平", "负-负",
        ],
        expected_outcome_count=9,
        data_source="500_bjdc",
        live_sp_table="live_market_sp_snapshots",
    ),
}

TARGET_PLAYIDS = (34, 40, 42, 51)
MARKET_KEY = {m.playid: m.market_key for m in MARKETS.values()}
HKT_OFFSET = "+08:00"


@dataclass
class GateResult:
    """Result of a single gate check for one market+dimension."""
    gate_id: GateID
    passed: bool
    score: float  # 1.0 = full pass, 0.0 = fail, partial otherwise
    evidence: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class DimensionAudit:
    """Audit result for one market+dimension."""
    market: MarketDefinition
    dimension: AuditDimension
    readiness: ReadinessLevel
    gates: list[GateResult]
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditResult:
    """Complete audit result for all markets."""
    audit_id: str = "MM-DATA-AUDIT-001"
    audit_cutoff_utc: str = ""
    dimensions: list[DimensionAudit] = field(default_factory=list)
    readiness_matrix: dict[str, dict[str, str]] = field(default_factory=dict)
    metrics_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        matrix = {}
        for dim in self.dimensions:
            mk = dim.market.market_key
            if mk not in matrix:
                matrix[mk] = {}
            matrix[mk][dim.dimension.value] = dim.readiness.value
        return {
            "audit_id": self.audit_id,
            "audit_cutoff_utc": self.audit_cutoff_utc,
            "readiness_matrix": matrix,
            "dimensions": [
                {
                    "market_key": d.market.market_key,
                    "market_display": d.market.display_name,
                    "playid": d.market.playid,
                    "dimension": d.dimension.value,
                    "readiness": d.readiness.value,
                    "summary": d.summary,
                    "metrics": d.metrics,
                    "gates": [
                        {
                            "gate_id": g.gate_id.value,
                            "passed": g.passed,
                            "score": g.score,
                            "evidence": g.evidence,
                            "metrics": g.metrics,
                        }
                        for g in d.gates
                    ],
                }
                for d in self.dimensions
            ],
            "metrics_summary": self.metrics_summary,
        }
