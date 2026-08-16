"""Issue #232 — loss-of-support waterfall (REQ-S06).

For each source family and each recoverable source candidate, counts rows at
every stage:

    RAW_ROWS -> IDENTITY_JOIN -> LINE_RECONCILIATION -> TIMESTAMP_GATE
        -> COMPLETE_TRIPLET -> CAUSAL_INTERSECTION

Every stage emits a DROP row (count removed, stable reason) and a PASS row
(remaining count) so the waterfall independently reconstructs every
raw-to-causal loss: RAW == sum(DROPs) + final PASS.  The final
CAUSAL_INTERSECTION PASS counts cells on the canonical #204/#203 axis where
the source value is causally available AND the Q_BJ anchor (calibrated
probability) is also causally available on the same cell — the controlling
support quantity for #209 divergence learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from . import contract


@dataclass
class WaterfallResult:
    rows: list[dict] = field(default_factory=list)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


class StageRecorder:
    """Records DROP rows (removed + reason) and PASS rows (remaining).

    Units: stages RAW..COMPLETE_TRIPLET count source rows; the
    CAUSAL_INTERSECTION stage counts canonical cells (match x 3 outcomes).
    ``expand`` inserts an explicit AXIS_EXPAND row so the waterfall is a
    replayable ledger: RAW - sum(DROPs) == rows; rows x 3 == sum(cell DROPs)
    + final cells.
    """

    def __init__(self, source: str, source_key: str) -> None:
        self.source = source
        self.source_key = source_key
        self.rows: list[dict] = []
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

    def drop(self, stage: str, dropped: int, reason: str, unit: str = "row") -> None:
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
        """Insert the row->cell axis-expansion transition.

        ``factor`` is 3 for match-level sources (one row per match expands to
        three 3/1/0 cells) and 1 for cell-level sources (EU de-vig is already
        one row per outcome cell).
        """
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
            [{"reason": reason, "count": count} for reason, count in self.reason_counts.items()]
        )


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
            "availability_status",
            "identity_timing_status",
        ]
    ].drop_duplicates()
    return meta


def _load_anchor_axis(root: Path) -> pd.DataFrame:
    """Canonical cell axis with Q_BJ causal availability (#204 + #203).

    Returns one row per (issue, match_idx, outcome_code) with the calibrated
    market probability and its causal availability computed by the same rule
    as #229: avg-EU cells carry euro_1h observed-at; pclose cells are graded
    RETROSPECTIVE_PROXY and are never causal.
    """
    pkg204 = contract.upstream_path(root, "bj204")
    features = pq.read_table(pkg204 / "common_cell_features.parquet").to_pandas()
    masks = pq.read_table(pkg204 / "common_cell_masks.parquet").to_pandas()
    axis = features.merge(
        masks,
        on=["cell_key", "market_probability", "native_handicap_line",
            "source_is_pclose", "source_is_average_eu", "market_proxy_complete",
            "predicted_final_sp_input"],
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
            "euro_1h_available_ts_utc",
            "predicted_sp_available_ts_utc",
            "identity_observed_ts_utc",
            "availability_status",
            "identity_timing_status",
        ]
    ].drop_duplicates()
    axis = axis.merge(
        meta, on=["issue", "match_idx"], how="left", validate="many_to_one"
    )

    cutoff = pd.to_datetime(axis["feature_cutoff_ts_utc"], errors="coerce", utc=True)
    euro_observed = pd.to_datetime(
        axis["euro_1h_available_ts_utc"], errors="coerce", utc=True
    )
    is_avg_eu = (
        pd.to_numeric(axis.get("source_is_average_eu"), errors="coerce")
        .fillna(0)
        .astype(float)
        .eq(1.0)
    )
    # Q_BJ causal availability: avg-EU cell with euro_1h observed at/before the
    # decision epoch.  pclose cells are RETROSPECTIVE_PROXY -> never causal.
    qbj_causal = (
        is_avg_eu
        & euro_observed.notna()
        & cutoff.notna()
        & euro_observed.le(cutoff)
    )
    axis["qbj_observed_at_utc"] = euro_observed
    axis["qbj_causal_available"] = qbj_causal
    return axis


def _sp_from_observations(root: Path) -> pd.DataFrame:
    """#214 decision-epoch BJ SP observations (committed)."""
    pkg214 = contract.upstream_path(root, "bj214")
    obs = pq.read_table(
        pkg214 / "sources/selected_market_observations.parquet"
    ).to_pandas()
    obs["snapshot_ts_utc"] = pd.to_datetime(obs["snapshot_ts_utc"], errors="coerce", utc=True)
    obs["match_id"] = obs["match_id"].astype(str)
    return obs


def _eu_from_bj203(root: Path) -> pd.DataFrame:
    """#203 per-cell de-vig EURO probability with observed-at."""
    pkg203 = contract.upstream_path(root, "bj203")
    values = pq.read_table(pkg203 / "inference/feature_values.parquet").to_pandas()
    identity = _load_identity(root)
    key_map = identity[["cell_join_key", "issue", "match_idx", "outcome_code"]]
    key_map["cell_join_key"] = key_map["cell_join_key"].astype(str)
    values["cell_join_key"] = values["cell_join_key"].astype(str)
    joined = values.merge(key_map, on="cell_join_key", how="inner", validate="one_to_one")
    joined["outcome_code"] = joined["outcome_code"].astype(str)
    return joined


def _power_from_bj180(root: Path) -> pd.DataFrame:
    """#180 power-model probabilities in native 3/1/0 space."""
    pkg180 = contract.upstream_path(root, "bj180")
    freeze = pd.read_csv(pkg180 / "match_probability_freeze.csv.gz", compression="gzip")
    freeze["issue"] = _parse_issue(freeze["issue"])
    freeze["match_idx"] = freeze["match_idx"].astype(int)
    return freeze


def _full_3sp_from_raw(root: Path) -> pd.DataFrame | None:
    """Optional official 3SP export; None when the raw asset is absent."""
    path = (root / "data/raw/beidan_full_3sp.csv").resolve()
    if not path.exists():
        return None
    frame = pd.read_csv(path, dtype={"expect": str})
    frame["issue"] = frame["expect"].str.strip()
    frame["match_idx"] = frame["match_no"].astype(int)
    frame["last_update_ts"] = pd.to_datetime(frame["last_update_ts"], errors="coerce")
    return frame


def _census_waterfall_sp_committed(
    root: Path, axis: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
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
              "availability_status", "identity_timing_status"]],
        on=["issue", "match_idx"],
        how="left",
        indicator=True,
    )
    matched = joined[joined["_merge"].eq("both")]
    rec.drop(contract.STAGE_IDENTITY_JOIN, len(joined) - len(matched),
             contract.REASON_NO_IDENTITY_MATCH)
    rec.pass_(contract.STAGE_IDENTITY_JOIN, len(matched))

    # decision epoch gate
    matched = matched.copy()
    matched["feature_cutoff_ts_utc"] = pd.to_datetime(
        matched["feature_cutoff_ts_utc"], errors="coerce", utc=True
    )
    no_epoch = matched["feature_cutoff_ts_utc"].isna()
    with_epoch = matched[~no_epoch]
    rec.drop(contract.STAGE_TIMESTAMP_GATE, int(no_epoch.sum()),
             contract.REASON_NO_CAUSAL_EPOCH)

    causal = with_epoch[with_epoch["snapshot_ts_utc"].le(with_epoch["feature_cutoff_ts_utc"])]
    rec.drop(contract.STAGE_TIMESTAMP_GATE, len(with_epoch) - len(causal),
             contract.REASON_POST_DECISION_OBSERVATION)
    rec.pass_(contract.STAGE_TIMESTAMP_GATE, len(causal))

    complete = causal[causal[["sp_3", "sp_1", "sp_0"]].notna().all(axis=1)]
    rec.drop(contract.STAGE_COMPLETE_TRIPLET, len(causal) - len(complete),
             contract.REASON_PARTIAL_SOURCE_TRIPLET)

    # Select the LATEST causal observation per (issue, match_idx): the
    # decision-epoch price is the most recent observation at/before the epoch.
    # Multiple snapshots for one match are one decision-epoch observation.
    complete = complete.sort_values("snapshot_ts_utc")
    latest = complete.groupby(["issue", "match_idx"], as_index=False).tail(1)
    rec.drop(contract.STAGE_COMPLETE_TRIPLET, len(complete) - len(latest),
             contract.REASON_DUPLICATE_SOURCE_ROW)
    rec.pass_(contract.STAGE_COMPLETE_TRIPLET, len(latest))

    # causal intersection with the Q_BJ anchor on the canonical axis.
    # Every complete match expands to 3 potential 3/1/0 cells; cells whose
    # (issue, match_idx) is absent from the modeling axis are NOT_IN_MODELING,
    # cells whose anchor is not causally available are ANCHOR_UNAVAILABLE.
    expanded = len(latest) * 3
    rec.expand(contract.STAGE_CAUSAL_INTERSECTION, expanded, factor=3)
    cells = latest.merge(
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

    return pd.DataFrame(rec.rows), rec.reason_frame()


def _census_waterfall_full_3sp(
    root: Path, axis: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Waterfall for the official 3SP export (recoverable raw asset)."""
    frame = _full_3sp_from_raw(root)
    if frame is None:
        rec = StageRecorder("Q_BJ_SP_DEVIG", "full_3sp_official")
        rec.rows.append(
            {
                "source": "Q_BJ_SP_DEVIG",
                "source_key": "full_3sp_official",
                "stage": contract.STAGE_RAW,
                "count": 0,
                "kind": "ABSENT",
                "reason": contract.REASON_RAW_ASSET_ABSENT,
            }
        )
        return pd.DataFrame(rec.rows), pd.DataFrame(
            [{"reason": contract.REASON_RAW_ASSET_ABSENT, "count": 0}]
        )

    meta = _load_match_meta(root)
    rec = StageRecorder("Q_BJ_SP_DEVIG", "full_3sp_official")

    frame = frame.copy()
    frame["issue"] = _parse_issue(frame["issue"])
    rec.raw(len(frame))

    joined = frame.merge(
        meta[["issue", "match_idx", "feature_cutoff_ts_utc", "kickoff_ts_utc"]],
        on=["issue", "match_idx"],
        how="left",
        indicator=True,
    )
    matched = joined[joined["_merge"].eq("both")]
    rec.drop(contract.STAGE_IDENTITY_JOIN, len(joined) - len(matched),
             contract.REASON_NO_IDENTITY_MATCH)
    rec.pass_(contract.STAGE_IDENTITY_JOIN, len(matched))

    matched = matched.copy()
    matched["feature_cutoff_ts_utc"] = pd.to_datetime(
        matched["feature_cutoff_ts_utc"], errors="coerce", utc=True
    )
    no_epoch = matched["feature_cutoff_ts_utc"].isna()
    with_epoch = matched[~no_epoch]
    rec.drop(contract.STAGE_TIMESTAMP_GATE, int(no_epoch.sum()),
             contract.REASON_NO_CAUSAL_EPOCH)

    causal = with_epoch[with_epoch["last_update_ts"].le(with_epoch["feature_cutoff_ts_utc"])]
    rec.drop(contract.STAGE_TIMESTAMP_GATE, len(with_epoch) - len(causal),
             contract.REASON_POST_DECISION_OBSERVATION)
    rec.pass_(contract.STAGE_TIMESTAMP_GATE, len(causal))

    complete = causal[~causal["winning_sp"].isna()]
    rec.drop(contract.STAGE_COMPLETE_TRIPLET, len(causal) - len(complete),
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

    return pd.DataFrame(rec.rows), rec.reason_frame()


def _eu_waterfall(root: Path, axis: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Waterfall for #203 de-vig EURO (Q_EU_RAW_1X2 / Q_EU_BJLINE)."""
    eu = _eu_from_bj203(root)
    meta = _load_match_meta(root)
    rec = StageRecorder("Q_EU_RAW_1X2", "bj203_devig_euro_probability")

    rec.raw(len(eu))
    meta_eu = _load_identity(root)[
        ["issue", "match_idx", "euro_1h_available_ts_utc"]
    ].drop_duplicates()
    eu = eu.merge(
        meta_eu, on=["issue", "match_idx"], how="left", validate="many_to_one"
    )
    eu = eu.merge(
        meta[["issue", "match_idx", "feature_cutoff_ts_utc", "kickoff_ts_utc"]],
        on=["issue", "match_idx"],
        how="left",
        indicator=True,
    )
    matched = eu[eu["_merge"].eq("both")]
    rec.drop(contract.STAGE_IDENTITY_JOIN, len(eu) - len(matched),
             contract.REASON_NO_IDENTITY_MATCH)
    rec.pass_(contract.STAGE_IDENTITY_JOIN, len(matched))

    matched = matched.copy()
    matched["feature_cutoff_ts_utc"] = pd.to_datetime(
        matched["feature_cutoff_ts_utc"], errors="coerce", utc=True
    )
    no_epoch = matched["feature_cutoff_ts_utc"].isna()
    with_epoch = matched[~no_epoch]
    rec.drop(contract.STAGE_TIMESTAMP_GATE, int(no_epoch.sum()),
             contract.REASON_NO_CAUSAL_EPOCH)

    observed = pd.to_datetime(
        matched["euro_1h_available_ts_utc"], errors="coerce", utc=True
    )
    causal = with_epoch[observed.loc[with_epoch.index].notna() & observed.loc[with_epoch.index].le(with_epoch["feature_cutoff_ts_utc"])]
    rec.drop(contract.STAGE_TIMESTAMP_GATE, len(with_epoch) - len(causal),
             contract.REASON_POST_DECISION_OBSERVATION)
    rec.pass_(contract.STAGE_TIMESTAMP_GATE, len(causal))

    complete = causal[~causal["devig_euro_probability"].isna()]
    rec.drop(contract.STAGE_COMPLETE_TRIPLET, len(causal) - len(complete),
             contract.REASON_PARTIAL_SOURCE_TRIPLET)
    rec.pass_(contract.STAGE_COMPLETE_TRIPLET, len(complete))

    # EU de-vig is already cell-level (one row per 3/1/0 outcome), so the
    # expansion factor is 1: every complete cell maps to one axis cell.
    expanded = len(complete)
    rec.expand(contract.STAGE_CAUSAL_INTERSECTION, expanded, factor=1)
    cells = complete.merge(
        axis[["issue", "match_idx", "outcome_code", "qbj_causal_available"]],
        on=["issue", "match_idx", "outcome_code"],
        how="left",
        validate="one_to_one",
    )
    in_axis = cells[cells["qbj_causal_available"].notna()]
    rec.drop(contract.STAGE_CAUSAL_INTERSECTION, expanded - len(in_axis),
             contract.REASON_NOT_IN_MODELING_AXIS, unit="cell")
    final = cells[cells["qbj_causal_available"].eq(True)]
    rec.drop(contract.STAGE_CAUSAL_INTERSECTION, len(in_axis) - len(final),
             contract.REASON_ANCHOR_UNAVAILABLE, unit="cell")
    rec.pass_(contract.STAGE_CAUSAL_INTERSECTION, len(final), unit="cell")

    return pd.DataFrame(rec.rows), rec.reason_frame()


def _power_waterfall(root: Path, axis: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Waterfall for #180 power probabilities (P_POWER_BJLINE)."""
    power = _power_from_bj180(root)
    meta = _load_match_meta(root)
    rec = StageRecorder("P_POWER_BJLINE", "bj180_match_probability_freeze")

    rec.raw(len(power))
    power = power.merge(
        meta[["issue", "match_idx", "feature_cutoff_ts_utc", "kickoff_ts_utc"]],
        on=["issue", "match_idx"],
        how="left",
        indicator=True,
    )
    matched = power[power["_merge"].eq("both")]
    rec.drop(contract.STAGE_IDENTITY_JOIN, len(power) - len(matched),
             contract.REASON_NO_IDENTITY_MATCH)
    rec.pass_(contract.STAGE_IDENTITY_JOIN, len(matched))

    matched = matched.copy()
    matched["feature_cutoff_ts_utc"] = pd.to_datetime(
        matched["feature_cutoff_ts_utc"], errors="coerce", utc=True
    )
    no_epoch = matched["feature_cutoff_ts_utc"].isna()
    with_epoch = matched[~no_epoch]
    rec.drop(contract.STAGE_TIMESTAMP_GATE, int(no_epoch.sum()),
             contract.REASON_NO_CAUSAL_EPOCH)

    # #180 carries its own per-match cutoff (feature_cutoff_ts, naive Beijing
    # time +08:00 per #229's verified binding).  Convert properly.
    power_ts_raw = pd.to_datetime(
        with_epoch.get("feature_cutoff_ts"), errors="coerce"
    )
    power_ts = power_ts_raw.dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC")
    causal = with_epoch[
        power_ts.notna() & power_ts.le(with_epoch["feature_cutoff_ts_utc"])
    ]
    rec.drop(contract.STAGE_TIMESTAMP_GATE, len(with_epoch) - len(causal),
             contract.REASON_POST_DECISION_OBSERVATION)
    rec.pass_(contract.STAGE_TIMESTAMP_GATE, len(causal))

    complete = causal[
        causal[["market_p3", "market_p1", "market_p0"]].notna().all(axis=1)
    ]
    rec.drop(contract.STAGE_COMPLETE_TRIPLET, len(causal) - len(complete),
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

    return pd.DataFrame(rec.rows), rec.reason_frame()


def build_waterfall(root: Path) -> WaterfallResult:
    """Build the full loss-of-support waterfall."""
    axis = _load_anchor_axis(root)
    sp_committed, sp_reasons = _census_waterfall_sp_committed(root, axis)
    full3sp, full3sp_reasons = _census_waterfall_full_3sp(root, axis)
    eu, eu_reasons = _eu_waterfall(root, axis)
    power, power_reasons = _power_waterfall(root, axis)

    waterfall = pd.concat(
        [sp_committed, full3sp, eu, power], ignore_index=True
    )
    reasons = (
        pd.concat(
            [sp_reasons, full3sp_reasons, eu_reasons, power_reasons],
            ignore_index=True,
        )
        .groupby("reason", as_index=False)["count"]
        .sum()
        .sort_values("count", ascending=False)
    )
    result = WaterfallResult()
    result.rows = waterfall.to_dict("records")
    result.tables["waterfall"] = waterfall
    result.tables["waterfall_reason_summary"] = reasons
    result.tables["anchor_axis"] = axis
    return result
