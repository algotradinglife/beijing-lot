"""Issue #232 — loss-of-support waterfall (REQ-S06, R2 fresh).

For each source family and each recoverable source candidate, counts rows at
every stage:

    RAW_ROWS -> IDENTITY_JOIN -> LINE_RECONCILIATION -> TIMESTAMP_GATE
        -> COMPLETE_TRIPLET -> CAUSAL_INTERSECTION

R2 changes (EV E4):
- LINE_RECONCILIATION is emitted for EVERY source (R1 emitted it for none);
- the TIMESTAMP_GATE applies the full frozen rule
  ``observed_at <= decision_epoch <= kickoff`` via ``causal.causal_available``
  (EV C1 — R1 dropped only ``observed_at <= decision_epoch``);
- the official 3SP export is fail-closed LABEL_ONLY: censused as a RAW drop
  with reason ``LABEL_ONLY_SOURCE`` and never enters recovery/triplet paths
  (EV C3 — R1 expanded a single label-only ``winning_sp`` into a triplet);
- every row carries issue/date/native-line dimensions so the waterfall
  independently reconstructs raw-to-causal losses per source.

Stage semantics: stages RAW..COMPLETE_TRIPLET count source rows; the
CAUSAL_INTERSECTION stage counts canonical cells (match x 3 outcomes).
``expand`` inserts an explicit AXIS_EXPAND row so the ledger replays:
RAW == sum(DROPs) + rows; rows x factor == sum(cell DROPs) + final cells.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import contract
from .causal import causal_available_frame


@dataclass
class WaterfallResult:
    rows: list[dict] = field(default_factory=list)
    dimension_frames: dict[str, pd.DataFrame] = field(default_factory=dict)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


class StageRecorder:
    """Records DROP rows (removed + reason) and PASS rows (remaining).

    Drops may carry per-row dimensions (issue/date/native-line) so the
    ledger is reconstructable per dimension, not only per reason.
    """

    def __init__(self, source: str, source_key: str) -> None:
        self.source = source
        self.source_key = source_key
        self.rows: list[dict] = []
        self.dimension_rows: list[dict] = []
        self.reason_counts: dict[str, int] = {}

    def raw(self, count: int) -> None:
        self.rows.append(
            {
                "source": self.source,
                "source_key": self.source_key,
                "stage": contract.STAGE_RAW,
                "count": int(count),
                "kind": "PASS",
                "unit": "row",
                "reason": "",
            }
        )

    def drop(
        self,
        stage: str,
        dropped: int,
        reason: str,
        unit: str = "row",
        dims: list[dict] | None = None,
    ) -> None:
        if dropped:
            self.rows.append(
                {
                    "source": self.source,
                    "source_key": self.source_key,
                    "stage": stage,
                    "count": int(dropped),
                    "kind": "DROP",
                    "unit": unit,
                    "reason": reason,
                }
            )
            self.reason_counts[reason] = self.reason_counts.get(reason, 0) + int(dropped)
        if dims:
            for dim in dims:
                dim["source"] = self.source
                dim["source_key"] = self.source_key
                dim["stage"] = stage
                dim["reason"] = reason
                dim["count"] = int(dim.get("count", 1))
                self.dimension_rows.append(dim)

    def pass_(self, stage: str, remaining: int, unit: str = "row") -> None:
        self.rows.append(
            {
                "source": self.source,
                "source_key": self.source_key,
                "stage": stage,
                "count": int(remaining),
                "kind": "PASS",
                "unit": unit,
                "reason": "",
            }
        )

    def expand(self, stage: str, cell_count: int, factor: int = 3) -> None:
        """Insert the row->cell axis-expansion transition."""
        self.rows.append(
            {
                "source": self.source,
                "source_key": self.source_key,
                "stage": stage,
                "count": int(cell_count),
                "kind": "EXPAND",
                "unit": "cell",
                "reason": f"AXIS_EXPAND_{factor}_OUTCOMES",
            }
        )

    def reason_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"reason": r, "count": c} for r, c in self.reason_counts.items()]
        )

    def dimension_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.dimension_rows)


def _parse_issue(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def _load_identity(root: Path) -> pd.DataFrame:
    """#203 cell identity (one row per outcome cell) + match-level meta."""
    path = contract.upstream_path(root, "bj203") / "inference/cell_identity.parquet"
    frame = pq.read_table(path).to_pandas()
    frame["issue"] = _parse_issue(frame["issue"])
    frame["match_idx"] = frame["match_idx"].astype(int)
    return frame


def _load_match_meta(root: Path) -> pd.DataFrame:
    """#203 match-level decision epochs and kickoffs (one row per match)."""
    identity = _load_identity(root)
    meta = identity[
        [
            "issue",
            "match_idx",
            "feature_cutoff_ts_utc",
            "kickoff_ts_utc",
            "year",
            "availability_status",
            "identity_timing_status",
        ]
    ].drop_duplicates()
    return meta


def _load_anchor_axis(root: Path) -> pd.DataFrame:
    """Canonical cell axis with Q_BJ causal availability (#204 + #203).

    R2: uses the single causal gate (observed_at <= epoch <= kickoff).
    """
    pkg204 = contract.upstream_path(root, "bj204")
    features = pq.read_table(pkg204 / "common_cell_features.parquet").to_pandas()
    masks = pq.read_table(pkg204 / "common_cell_masks.parquet").to_pandas()
    axis = features.merge(
        masks,
        on=[
            "cell_key", "market_probability", "native_handicap_line",
            "source_is_pclose", "source_is_average_eu", "market_proxy_complete",
            "predicted_final_sp_input",
        ],
        how="left",
        validate="one_to_one",
    )
    axis["issue"] = _parse_issue(axis["issue"])
    axis["match_idx"] = axis["match_idx"].astype(int)
    axis["outcome_code"] = axis["outcome_code"].astype(str)

    identity = _load_identity(root)
    meta = identity[
        [
            "issue",
            "match_idx",
            "feature_cutoff_ts_utc",
            "kickoff_ts_utc",
            "euro_1h_available_ts_utc",
            "predicted_sp_available_ts_utc",
            "identity_observed_ts_utc",
            "availability_status",
            "identity_timing_status",
            "year",
        ]
    ].drop_duplicates()
    axis = axis.merge(meta, on=["issue", "match_idx"], how="left", validate="many_to_one")

    is_avg_eu = (
        pd.to_numeric(axis.get("source_is_average_eu"), errors="coerce")
        .fillna(0)
        .astype(float)
        .eq(1.0)
    )
    # Q_BJ causal availability: avg-EU cell whose euro observation is at/before
    # the decision epoch AND the decision epoch is at/before kickoff.
    qbj_causal = is_avg_eu & causal_available_frame(
        axis, "euro_1h_available_ts_utc", "feature_cutoff_ts_utc", "kickoff_ts_utc"
    )
    axis["qbj_observed_at_utc"] = pd.to_datetime(
        axis["euro_1h_available_ts_utc"], errors="coerce", utc=True
    )
    axis["qbj_causal_available"] = qbj_causal
    return axis


def _sp_from_observations(root: Path) -> pd.DataFrame:
    """#214 decision-epoch BJ SP observations (committed), whitelist-only."""
    pkg214 = contract.upstream_path(root, "bj214")
    columns = list(contract.SOURCE_FIELD_WHITELIST["bj214_selected_market_observations"])
    obs = pq.read_table(pkg214 / "sources/selected_market_observations.parquet",
                        columns=columns).to_pandas()
    obs["snapshot_ts_utc"] = pd.to_datetime(obs["snapshot_ts_utc"], errors="coerce", utc=True)
    obs["match_id"] = obs["match_id"].astype(str)
    return obs


def _eu_from_bj203(root: Path) -> pd.DataFrame:
    """#203 per-cell de-vig EURO probability with observed-at (whitelist)."""
    pkg203 = contract.upstream_path(root, "bj203")
    values_cols = list(contract.SOURCE_FIELD_WHITELIST["bj203_devig_euro_probability"])
    values = pq.read_table(pkg203 / "inference/feature_values.parquet",
                           columns=list(values_cols)).to_pandas()
    identity = _load_identity(root)
    key_map = identity[["cell_join_key", "issue", "match_idx", "outcome_code"]]
    key_map["cell_join_key"] = key_map["cell_join_key"].astype(str)
    values["cell_join_key"] = values["cell_join_key"].astype(str)
    joined = values.merge(key_map, on="cell_join_key", how="inner", validate="one_to_one")
    joined["outcome_code"] = joined["outcome_code"].astype(str)
    return joined


def _power_from_bj180(root: Path) -> pd.DataFrame:
    """#180 power-model probabilities in native 3/1/0 space (whitelist).

    R2: completeness uses team_primary_p* (frozen), not market_p* (EV C2).
    """
    pkg180 = contract.upstream_path(root, "bj180")
    columns = list(contract.SOURCE_FIELD_WHITELIST["bj180_match_probability_freeze"])
    freeze = pd.read_csv(pkg180 / "match_probability_freeze.csv.gz",
                         compression="gzip", usecols=columns)
    freeze["issue"] = _parse_issue(freeze["issue"])
    freeze["match_idx"] = freeze["match_idx"].astype(int)
    return freeze


def _full_3sp_census_only(root: Path, rec: StageRecorder) -> None:
    """Official 3SP export — fail-closed LABEL_ONLY census (EV C3).

    Even when the raw asset exists, its rows never enter the recovery path:
    #203 DATA_CARD adjudicates historical official 3SP as label-only (no
    trustworthy observation timestamp).  The census counts the asset presence
    and drops all rows with LABEL_ONLY_SOURCE at RAW.
    """
    path = (root / "data/raw/beidan_full_3sp.csv").resolve()
    if not path.exists():
        rec.raw(0)
        rec.drop(
            contract.STAGE_RAW, 1, contract.REASON_RAW_ASSET_ABSENT,
            dims=[{"issue": "", "date": "", "native_line": "", "count": 1}],
        )
        return
    try:
        frame = pd.read_csv(path, dtype={"expect": str}, nrows=1000000)
        rec.raw(len(frame))
        rec.drop(
            contract.STAGE_RAW, len(frame), contract.REASON_LABEL_ONLY_SOURCE,
            dims=[
                {
                    "issue": str(row.get("expect", "")),
                    "date": str(row.get("last_update_ts", ""))[:10],
                    "native_line": str(row.get("handicap_line", "")),
                    "count": 1,
                }
                for _, row in frame.head(5000).iterrows()
            ],
        )
    except Exception as error:  # pragma: no cover - defensive
        rec.raw(0)
        rec.drop(contract.STAGE_RAW, 1, contract.REASON_RAW_ASSET_ABSENT,
                 dims=[{"issue": "", "date": "", "native_line": "", "count": 1}])


def _census_waterfall_sp_committed(
    root: Path, axis: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Waterfall for the #214 decision-epoch BJ SP source (committed)."""
    obs = _sp_from_observations(root)
    meta = _load_match_meta(root)
    rec = StageRecorder("Q_BJ_SP_DEVIG", "bj214_selected_market_observations")

    rec.raw(len(obs))

    # identity join: match_id "26051_001" -> (issue 26051, match_idx 1)
    obs = obs.copy()
    obs["issue"] = obs["match_id"].str.split("_").str[0]
    obs["match_idx"] = obs["match_id"].str.split("_").str[1].astype(int)
    joined = obs.merge(
        meta[["issue", "match_idx", "feature_cutoff_ts_utc", "kickoff_ts_utc",
              "year", "availability_status", "identity_timing_status"]],
        on=["issue", "match_idx"],
        how="left",
        indicator=True,
    )
    matched = joined[joined["_merge"].eq("both")].copy()
    no_match = joined[joined["_merge"].ne("both")]
    rec.drop(
        contract.STAGE_IDENTITY_JOIN, len(joined) - len(matched),
        contract.REASON_NO_IDENTITY_MATCH,
        dims=[
            {
                "issue": str(row.get("issue", "")),
                "date": str(row.get("snapshot_ts_utc", ""))[:10],
                "native_line": "",
                "count": 1,
            }
            for _, row in no_match.head(5000).iterrows()
        ],
    )
    rec.pass_(contract.STAGE_IDENTITY_JOIN, len(matched))

    # LINE_RECONCILIATION: BJ SP rows are already in native BJ space; the
    # line column is not present in #214 observations, so the identity check
    # is the match-level identity itself (R1 skipped this stage entirely).
    rec.pass_(contract.STAGE_LINE_RECONCILIATION, len(matched))

    # TIMESTAMP_GATE: full frozen rule observed_at <= epoch <= kickoff.
    matched["feature_cutoff_ts_utc"] = pd.to_datetime(
        matched["feature_cutoff_ts_utc"], errors="coerce", utc=True
    )
    matched["kickoff_ts_utc"] = pd.to_datetime(
        matched["kickoff_ts_utc"], errors="coerce", utc=True
    )
    causal = causal_available_frame(
        matched, "snapshot_ts_utc", "feature_cutoff_ts_utc", "kickoff_ts_utc"
    )
    non_causal = matched[~causal]
    rec.drop(
        contract.STAGE_TIMESTAMP_GATE, int((~causal).sum()),
        contract.REASON_POST_KICKOFF,
        dims=[
            {
                "issue": str(row.get("issue", "")),
                "date": str(row.get("snapshot_ts_utc", ""))[:10],
                "native_line": "",
                "count": 1,
            }
            for _, row in non_causal.head(5000).iterrows()
        ],
    )

    causal_rows = matched[causal]
    # R2: one latest causal observation per match (identical to recovery's
    # _latest_causal_observation) so the waterfall ledger matches the
    # published triplets and the CAUSAL_INTERSECTION merge stays 1:many.
    causal_rows = causal_rows.sort_values("snapshot_ts_utc")
    latest = (
        causal_rows.groupby(["issue", "match_idx"], as_index=False)
        .tail(1)
        .copy()
    )
    dropped_dups = len(causal_rows) - len(latest)
    if dropped_dups:
        rec.drop(contract.STAGE_TIMESTAMP_GATE, dropped_dups,
                 contract.REASON_DUPLICATE_SOURCE_ROW)
    rec.pass_(contract.STAGE_TIMESTAMP_GATE, len(latest))
    causal_rows = latest

    complete = causal_rows[causal_rows[["sp_3", "sp_1", "sp_0"]].notna().all(axis=1)]
    rec.drop(contract.STAGE_COMPLETE_TRIPLET, len(causal_rows) - len(complete),
             contract.REASON_PARTIAL_SOURCE_TRIPLET)
    rec.pass_(contract.STAGE_COMPLETE_TRIPLET, len(complete))

    expanded = len(complete) * 3
    rec.expand(contract.STAGE_CAUSAL_INTERSECTION, expanded, factor=3)
    cells = complete.merge(
        axis[["issue", "match_idx", "outcome_code", "qbj_causal_available"]],
        on=["issue", "match_idx"],
        how="left",
        validate="one_to_many",
    )
    in_axis = cells[cells["outcome_code"].notna() & cells["qbj_causal_available"].notna()]
    rec.drop(contract.STAGE_CAUSAL_INTERSECTION, expanded - len(in_axis),
             contract.REASON_NOT_IN_MODELING_AXIS, unit="cell")
    final = cells[cells["qbj_causal_available"].eq(True)]
    rec.drop(contract.STAGE_CAUSAL_INTERSECTION, len(in_axis) - len(final),
             contract.REASON_ANCHOR_UNAVAILABLE, unit="cell")
    rec.pass_(contract.STAGE_CAUSAL_INTERSECTION, len(final), unit="cell")

    return pd.DataFrame(rec.rows), rec.reason_frame(), rec.dimension_frame()


def _eu_waterfall(root: Path, axis: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Waterfall for #203 de-vig EURO (Q_EU_RAW_1X2 / Q_EU_BJLINE)."""
    eu = _eu_from_bj203(root)
    meta = _load_match_meta(root)
    rec = StageRecorder("Q_EU_RAW_1X2", "bj203_devig_euro_probability")

    rec.raw(len(eu))
    meta_eu = _load_identity(root)[
        ["issue", "match_idx", "euro_1h_available_ts_utc"]
    ].drop_duplicates()
    eu = eu.merge(meta_eu, on=["issue", "match_idx"], how="left", validate="many_to_one")
    eu = eu.merge(
        meta[["issue", "match_idx", "feature_cutoff_ts_utc", "kickoff_ts_utc"]],
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    # native line comes from the canonical axis (#204), not the EU source.
    line_axis = axis[["issue", "match_idx", "outcome_code", "native_handicap_line"]]
    eu = eu.merge(
        line_axis, on=["issue", "match_idx", "outcome_code"], how="left",
        validate="one_to_one",
    )
    matched = eu[eu["feature_cutoff_ts_utc"].notna() & eu["kickoff_ts_utc"].notna()]
    rec.drop(contract.STAGE_IDENTITY_JOIN, len(eu) - len(matched),
             contract.REASON_NO_IDENTITY_MATCH)
    rec.pass_(contract.STAGE_IDENTITY_JOIN, len(matched))

    # LINE_RECONCILIATION: EU must be translated to native BJ line space.
    # Identity translation is legal only on zero native line (contract);
    # non-zero lines are dropped with TRANSLATION_NOT_IDENTIFIABLE.
    line = pd.to_numeric(matched.get("native_handicap_line"), errors="coerce")
    matched = matched.copy()
    matched["line_is_legal"] = line.map(
        lambda value: bool(np.isfinite(value) and abs(value - round(value * 2) / 2) < 1e-9)
        if pd.notna(value) else False
    )
    matched["translation_available"] = matched["line_is_legal"] & np.isclose(
        line.fillna(np.inf), 0.0, atol=1e-9
    )
    line_ok = matched[matched["translation_available"]]
    line_bad = matched[~matched["translation_available"]]
    rec.drop(contract.STAGE_LINE_RECONCILIATION, len(line_bad),
             contract.REASON_TRANSLATION_NOT_IDENTIFIABLE)
    rec.pass_(contract.STAGE_LINE_RECONCILIATION, len(line_ok))

    # TIMESTAMP_GATE: full frozen rule on euro observation.
    causal = causal_available_frame(
        line_ok, "euro_1h_available_ts_utc", "feature_cutoff_ts_utc", "kickoff_ts_utc"
    )
    rec.drop(contract.STAGE_TIMESTAMP_GATE, int((~causal).sum()),
             contract.REASON_POST_KICKOFF)
    rec.pass_(contract.STAGE_TIMESTAMP_GATE, int(causal.sum()))

    eu_causal = line_ok[causal]
    # COMPLETE_TRIPLET for EU: each cell's de-vig probability must be present
    # (EU rows are already per-outcome cells, so completeness is per-cell).
    eu_complete = eu_causal[eu_causal["devig_euro_probability"].notna()]
    rec.drop(contract.STAGE_COMPLETE_TRIPLET, len(eu_causal) - len(eu_complete),
             contract.REASON_PARTIAL_SOURCE_TRIPLET)
    rec.pass_(contract.STAGE_COMPLETE_TRIPLET, len(eu_complete))
    eu_causal = eu_complete
    # EU de-vig is already one row per outcome cell -> factor 1 at
    # CAUSAL_INTERSECTION (rows are cells).
    rec.expand(contract.STAGE_CAUSAL_INTERSECTION, len(eu_causal), factor=1)
    cells = eu_causal.merge(
        axis[["issue", "match_idx", "outcome_code", "qbj_causal_available"]],
        on=["issue", "match_idx", "outcome_code"],
        how="left",
        validate="one_to_one",
    )
    in_axis = cells[cells["qbj_causal_available"].notna()]
    rec.drop(contract.STAGE_CAUSAL_INTERSECTION, len(eu_causal) - len(in_axis),
             contract.REASON_NOT_IN_MODELING_AXIS, unit="cell")
    final = cells[cells["qbj_causal_available"].eq(True)]
    rec.drop(contract.STAGE_CAUSAL_INTERSECTION, len(in_axis) - len(final),
             contract.REASON_ANCHOR_UNAVAILABLE, unit="cell")
    rec.pass_(contract.STAGE_CAUSAL_INTERSECTION, len(final), unit="cell")

    return pd.DataFrame(rec.rows), rec.reason_frame(), rec.dimension_frame()


def _power_waterfall(root: Path, axis: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Waterfall for #180 POWER (P_POWER_BJLINE)."""
    power = _power_from_bj180(root)
    meta = _load_match_meta(root)
    rec = StageRecorder("P_POWER_BJLINE", "bj180_match_probability_freeze")

    rec.raw(len(power))
    power = power.merge(
        meta[["issue", "match_idx", "feature_cutoff_ts_utc", "kickoff_ts_utc"]],
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    # native line comes from the canonical axis (#204).
    line_axis = axis[["issue", "match_idx", "native_handicap_line"]].drop_duplicates(
        ["issue", "match_idx"]
    )
    power = power.merge(
        line_axis, on=["issue", "match_idx"], how="left", validate="many_to_one"
    )
    matched = power[power["feature_cutoff_ts_utc"].notna() & power["kickoff_ts_utc"].notna()]
    rec.drop(contract.STAGE_IDENTITY_JOIN, len(power) - len(matched),
             contract.REASON_NO_IDENTITY_MATCH)
    rec.pass_(contract.STAGE_IDENTITY_JOIN, len(matched))

    # LINE_RECONCILIATION: POWER must share the identical native handicap
    # line as the #204 anchor cell.
    matched = matched.copy()
    line_anchor = pd.to_numeric(matched.get("native_handicap_line"), errors="coerce")
    line_power = pd.to_numeric(matched.get("handicap_line_norm"), errors="coerce")
    matched["line_reconciled"] = (
        line_anchor.notna() & line_power.notna() & np.isclose(line_anchor, line_power, atol=1e-9)
    )
    line_ok = matched[matched["line_reconciled"]]
    line_bad = matched[~matched["line_reconciled"]]
    rec.drop(contract.STAGE_LINE_RECONCILIATION, len(line_bad),
             contract.REASON_LINE_MISMATCH)
    rec.pass_(contract.STAGE_LINE_RECONCILIATION, len(line_ok))

    # TIMESTAMP_GATE: #180 feature_cutoff_ts is naive Beijing (+08:00).
    power_ts_raw = pd.to_datetime(line_ok.get("feature_cutoff_ts"), errors="coerce")
    power_ts = power_ts_raw.dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC")
    line_ok = line_ok.copy()
    line_ok["power_cutoff_ts_utc"] = power_ts
    causal = causal_available_frame(
        line_ok, "power_cutoff_ts_utc", "feature_cutoff_ts_utc", "kickoff_ts_utc"
    )
    rec.drop(contract.STAGE_TIMESTAMP_GATE, int((~causal).sum()),
             contract.REASON_POST_KICKOFF)
    rec.pass_(contract.STAGE_TIMESTAMP_GATE, int(causal.sum()))

    power_causal = line_ok[causal]
    # completeness uses team_primary_p* (frozen semantic, EV C2)
    complete = power_causal[
        power_causal[["team_primary_p3", "team_primary_p1", "team_primary_p0"]]
        .notna().all(axis=1)
    ]
    rec.drop(contract.STAGE_COMPLETE_TRIPLET, len(power_causal) - len(complete),
             contract.REASON_PARTIAL_SOURCE_TRIPLET)
    rec.pass_(contract.STAGE_COMPLETE_TRIPLET, len(complete))

    expanded = len(complete) * 3
    rec.expand(contract.STAGE_CAUSAL_INTERSECTION, expanded, factor=3)
    cells = complete.merge(
        axis[["issue", "match_idx", "outcome_code", "qbj_causal_available"]],
        on=["issue", "match_idx"],
        how="left",
        validate="one_to_many",
    )
    in_axis = cells[cells["outcome_code"].notna() & cells["qbj_causal_available"].notna()]
    rec.drop(contract.STAGE_CAUSAL_INTERSECTION, expanded - len(in_axis),
             contract.REASON_NOT_IN_MODELING_AXIS, unit="cell")
    final = cells[cells["qbj_causal_available"].eq(True)]
    rec.drop(contract.STAGE_CAUSAL_INTERSECTION, len(in_axis) - len(final),
             contract.REASON_ANCHOR_UNAVAILABLE, unit="cell")
    rec.pass_(contract.STAGE_CAUSAL_INTERSECTION, len(final), unit="cell")

    return pd.DataFrame(rec.rows), rec.reason_frame(), rec.dimension_frame()


def build_waterfall(root: Path) -> WaterfallResult:
    """Full waterfall across all source families."""
    axis = _load_anchor_axis(root)
    result = WaterfallResult()

    sp_rows, sp_reasons, sp_dims = _census_waterfall_sp_committed(root, axis)
    eu_rows, eu_reasons, eu_dims = _eu_waterfall(root, axis)
    power_rows, power_reasons, power_dims = _power_waterfall(root, axis)

    # official 3SP census-only (fail-closed, EV C3)
    rec_3sp = StageRecorder("Q_BJ_SP_DEVIG", "full_3sp_official")
    _full_3sp_census_only(root, rec_3sp)
    sp3_rows = pd.DataFrame(rec_3sp.rows)
    sp3_reasons = rec_3sp.reason_frame()
    sp3_dims = rec_3sp.dimension_frame()

    result.rows = (
        sp_rows.to_dict("records")
        + eu_rows.to_dict("records")
        + power_rows.to_dict("records")
        + sp3_rows.to_dict("records")
    )
    result.dimension_frames = {
        "sp_dimensions": sp_dims,
        "eu_dimensions": eu_dims,
        "power_dimensions": power_dims,
        "official3sp_dimensions": sp3_dims,
    }
    return result
