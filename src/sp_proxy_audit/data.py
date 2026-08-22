"""Read-only source readers for the Issue #318 SP admissibility audit."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as pads

from .grading import OUTCOMES

SHANGHAI = "Asia/Shanghai"


@dataclass(frozen=True)
class AuditPaths:
    repo_root: Path
    data_root: Path

    @property
    def beidan(self) -> Path:
        return self.data_root / "data/derived/beidan_xlsm/beidan_xlsm.sqlite"

    @property
    def candidate(self) -> Path:
        return (
            self.data_root / "data/derived/bj268/eu_proxy_backfill_v3/candidate.sqlite"
        )

    @property
    def materializer(self) -> Path:
        return self.data_root / "data/derived/bj238_divergence_materializer_v4r3"

    @property
    def receipt(self) -> Path:
        return self.repo_root / "docs/research/evidence/bj238/SOURCE_RECEIPT.json"

    @property
    def strict_panel(self) -> Path:
        return self.repo_root / "results/bj216_model_support_panel_v1"

    @property
    def registry(self) -> Path:
        return self.data_root / "data/derived/500_bjdc/500_bjdc.sqlite"


SOURCE_SPECS = (
    ("beidan_xlsm", "data/derived/beidan_xlsm/beidan_xlsm.sqlite", "sqlite"),
    (
        "eu_proxy_backfill",
        "data/derived/bj268/eu_proxy_backfill_v3/candidate.sqlite",
        "sqlite",
    ),
    (
        "bj238_materializer",
        "data/derived/bj238_divergence_materializer_v4r3",
        "directory",
    ),
    (
        "bj238_source_receipt",
        "docs/research/evidence/bj238/SOURCE_RECEIPT.json",
        "json",
    ),
    ("bj216_strict_panel", "results/bj216_model_support_panel_v1", "directory"),
    ("issue_registry", "data/derived/500_bjdc/500_bjdc.sqlite", "sqlite"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _registry_digest(path: Path) -> str:
    """Hash only the contract-read registry table, not unrelated live tables."""
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT CAST(issue AS TEXT), ordinal, label, is_selected, is_current,
                   year, first_seen_at, last_seen_at
            FROM issues ORDER BY CAST(issue AS TEXT)
            """
        ).fetchall()
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    connection = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _to_utc(values: pd.Series, *, naive_timezone: str | None = None) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    if getattr(parsed.dt, "tz", None) is not None:
        return parsed.dt.tz_convert("UTC")
    if naive_timezone is None:
        return pd.to_datetime(values, errors="coerce", utc=True)
    return parsed.dt.tz_localize(
        naive_timezone, ambiguous="NaT", nonexistent="NaT"
    ).dt.tz_convert("UTC")


def _iso_utc(values: pd.Series, *, naive_timezone: str | None = None) -> pd.Series:
    parsed = _to_utc(values, naive_timezone=naive_timezone)
    return parsed.dt.strftime("%Y-%m-%dT%H:%M:%SZ").astype("string")


def _sqlite_schema(path: Path, tables: tuple[str, ...]) -> dict[str, object]:
    with _connect(path) as connection:
        placeholders = ",".join("?" for _ in tables)
        rows = connection.execute(
            f"SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN ({placeholders}) ORDER BY name",
            tables,
        ).fetchall()
        counts = {
            table: int(
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
            for table, _ in rows
        }
    return {"tables": {name: {"rows": counts[name], "ddl": ddl} for name, ddl in rows}}


def _sqlite_profile(source_id: str, path: Path) -> dict[str, object]:
    """Small deterministic profiles proving that named tables were consumed."""
    with _connect(path) as connection:
        if source_id == "beidan_xlsm":
            row = connection.execute(
                """
                SELECT COUNT(*),
                       SUM(official_sp_3 IS NOT NULL AND official_sp_1 IS NOT NULL
                           AND official_sp_0 IS NOT NULL)
                FROM match_features
                """
            ).fetchone()
            settlement_columns = {
                column[1]
                for column in connection.execute(
                    "PRAGMA table_info(official_500_settlements)"
                ).fetchall()
            }
            winning_expr = (
                "SUM(winning_sp IS NOT NULL)"
                if "winning_sp" in settlement_columns
                else "NULL"
            )
            fetched_expr = (
                "MIN(fetched_at), MAX(fetched_at)"
                if "fetched_at" in settlement_columns
                else "NULL, NULL"
            )
            settlement = connection.execute(
                f"""
                SELECT COUNT(*), {winning_expr},
                       SUM(sp_home IS NOT NULL AND sp_draw IS NOT NULL AND sp_away IS NOT NULL),
                       {fetched_expr}, MIN(imported_at), MAX(imported_at)
                FROM official_500_settlements
                """
            ).fetchone()
            return {
                "match_feature_rows": int(row[0]),
                "complete_official_sp_triplets": int(row[1] or 0),
                "settlement_rows": int(settlement[0]),
                "winning_sp_rows": int(settlement[1] or 0),
                "complete_settlement_triplets": int(settlement[2] or 0),
                "fetched_at_range": [settlement[3], settlement[4]],
                "imported_at_range": [settlement[5], settlement[6]],
            }
        if source_id == "eu_proxy_backfill":
            horizon = connection.execute(
                """
                SELECT snapshot_kind, COUNT(*), COUNT(DISTINCT issue_code),
                       COUNT(DISTINCT bookmaker_id)
                FROM resolved_quotes GROUP BY snapshot_kind ORDER BY snapshot_kind
                """
            ).fetchall()
            inventory = connection.execute(
                "SELECT COUNT(*), COUNT(DISTINCT issue_code), MIN(kickoff_ts), MAX(kickoff_ts) FROM inventory"
            ).fetchone()
            return {
                "inventory": {
                    "fixtures": int(inventory[0]),
                    "issues": int(inventory[1]),
                    "kickoff_range": [inventory[2], inventory[3]],
                },
                "resolved_quote_horizons": [
                    {
                        "snapshot_kind": row[0],
                        "rows": int(row[1]),
                        "issues": int(row[2]),
                        "bookmakers": int(row[3]),
                    }
                    for row in horizon
                ],
            }
        if source_id == "issue_registry":
            years = connection.execute(
                "SELECT year, COUNT(*) FROM issues GROUP BY year ORDER BY year"
            ).fetchall()
            return {"issues_by_year": {str(year): int(count) for year, count in years}}
    return {}


def source_inventory(paths: AuditPaths) -> pd.DataFrame:
    """Bind the six frozen logical inputs without exposing machine-specific paths."""
    mapping = {
        "beidan_xlsm": paths.beidan,
        "eu_proxy_backfill": paths.candidate,
        "bj238_materializer": paths.materializer,
        "bj238_source_receipt": paths.receipt,
        "bj216_strict_panel": paths.strict_panel,
        "issue_registry": paths.registry,
    }
    receipt = (
        json.loads(paths.receipt.read_text(encoding="utf-8"))
        if paths.receipt.is_file()
        else {}
    )
    rows: list[dict[str, object]] = []
    for source_id, logical_path, kind in SOURCE_SPECS:
        path = mapping[source_id]
        digest_path = path if path.is_file() else path / "MANIFEST.json"
        available = path.exists() and digest_path.is_file()
        digest = (
            _registry_digest(path)
            if available and source_id == "issue_registry"
            else sha256(digest_path)
            if available
            else pd.NA
        )
        availability = "PRESENT" if available else "SOURCE_MISSING"
        if source_id == "eu_proxy_backfill" and available:
            expected = receipt.get(
                "candidate_sqlite_sha256_from_accepted_268_verification"
            )
            if not isinstance(expected, str) or digest != expected:
                availability = "MANIFEST_MISMATCH"
        provenance: dict[str, object] = {}
        if availability == "PRESENT" and kind == "sqlite":
            tables = {
                "beidan_xlsm": (
                    "match_features",
                    "official_500_settlements",
                    "matches",
                ),
                "eu_proxy_backfill": (
                    "inventory",
                    "resolved_quotes",
                    "duplicate_resolution_ledger",
                    "acquisition_receipts",
                ),
                "issue_registry": ("issues",),
            }[source_id]
            provenance = _sqlite_schema(path, tables)
            provenance["profile"] = _sqlite_profile(source_id, path)
        elif availability == "PRESENT" and kind == "directory":
            provenance = json.loads(digest_path.read_text(encoding="utf-8"))
        elif availability == "PRESENT" and kind == "json":
            provenance = json.loads(path.read_text(encoding="utf-8"))
        if source_id == "issue_registry" and availability == "PRESENT":
            provenance["digest_scope"] = (
                "issues table ordered by issue; unrelated live tables excluded"
            )
        rows.append(
            {
                "source_id": source_id,
                "relative_path": logical_path,
                "kind": kind,
                "availability": availability,
                "sha256": digest,
                "bytes": (
                    path.stat().st_size
                    if path.is_file() and source_id != "issue_registry"
                    else pd.NA
                ),
                "schema_or_provenance": json.dumps(
                    provenance, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    return pd.DataFrame(rows)


def _identities(
    paths: AuditPaths,
    *,
    candidate_available: bool,
    beidan_available: bool,
    registry_available: bool,
) -> pd.DataFrame:
    if candidate_available:
        with _connect(paths.candidate) as connection:
            candidate = pd.read_sql_query(
                """
            SELECT CAST(issue_code AS TEXT) AS issue_code, match_idx,
                   CAST(provider_match_id AS TEXT) AS provider_match_id,
                   kickoff_ts AS candidate_kickoff, reconciled_source
            FROM inventory ORDER BY issue_code, match_idx
            """,
                connection,
            )
    else:
        candidate = pd.DataFrame(
            columns=[
                "issue_code",
                "match_idx",
                "provider_match_id",
                "candidate_kickoff",
                "reconciled_source",
            ]
        )
    if beidan_available:
        with _connect(paths.beidan) as connection:
            historical = pd.read_sql_query(
                """
            SELECT CAST(issue AS TEXT) AS issue_code, match_idx,
                   kickoff_ts AS beidan_kickoff,
                   CAST(provider_match_id AS TEXT) AS beidan_provider_match_id
            FROM matches WHERE issue IS NOT NULL AND match_idx IS NOT NULL
            ORDER BY issue, match_idx
            """,
                connection,
            )
    else:
        historical = pd.DataFrame(
            columns=[
                "issue_code",
                "match_idx",
                "beidan_kickoff",
                "beidan_provider_match_id",
            ]
        )
    if registry_available:
        with _connect(paths.registry) as connection:
            registry = pd.read_sql_query(
                "SELECT CAST(issue AS TEXT) AS issue_code, year AS registry_year FROM issues",
                connection,
            )
    else:
        registry = pd.DataFrame(columns=["issue_code", "registry_year"])
    if candidate.duplicated(["issue_code", "match_idx"]).any():
        raise ValueError("candidate inventory identity is not unique")
    if historical.duplicated(["issue_code", "match_idx"]).any():
        raise ValueError("beidan match identity is not unique")
    result = candidate.merge(
        historical, on=["issue_code", "match_idx"], how="left", validate="one_to_one"
    )
    result = result.merge(registry, on="issue_code", how="left", validate="many_to_one")
    if result.empty:
        return pd.DataFrame(
            {
                "issue_code": pd.Series(dtype="string"),
                "match_idx": pd.Series(dtype="int64"),
                "provider_match_id": pd.Series(dtype="string"),
                "kickoff_utc": pd.Series(dtype="string"),
                "identity_consistent": pd.Series(dtype="bool"),
                "fixture_identity": pd.Series(dtype="string"),
                "reconciled_source": pd.Series(dtype="string"),
            }
        )
    candidate_utc = _to_utc(result["candidate_kickoff"], naive_timezone=SHANGHAI)
    beidan_utc = _to_utc(result["beidan_kickoff"], naive_timezone=SHANGHAI)
    agrees = result["registry_year"].notna() & (
        result["beidan_kickoff"].isna() | (candidate_utc == beidan_utc)
    )
    result["kickoff_utc"] = candidate_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ").astype(
        "string"
    )
    result["identity_consistent"] = agrees.fillna(False)
    result["fixture_identity"] = result["issue_code"].map(
        lambda issue: f"bjslot:{issue}:"
    ) + result["match_idx"].astype(str).str.zfill(3)
    return result[
        [
            "issue_code",
            "match_idx",
            "provider_match_id",
            "kickoff_utc",
            "identity_consistent",
            "fixture_identity",
            "reconciled_source",
        ]
    ]


def _long_triplets(
    frame: pd.DataFrame,
    *,
    price_columns: dict[str, str],
    source_id: str,
    snapshot_kind: str,
    semantics: str,
    provenance_sha256: str,
    observed_column: str | None = None,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    base_columns = [
        "issue_code",
        "match_idx",
        "kickoff_utc",
        "fixture_identity",
        "identity_consistent",
    ]
    for outcome in OUTCOMES:
        part = frame[base_columns].copy()
        part["outcome_code"] = outcome
        part["sp_value"] = pd.to_numeric(frame[price_columns[outcome]], errors="coerce")
        part["source_id"] = source_id
        part["snapshot_kind"] = snapshot_kind
        part["provenance_sha256"] = provenance_sha256
        part["observed_at_utc"] = frame[observed_column] if observed_column else pd.NA
        part["decision_epoch_utc"] = pd.NA
        part["source_semantics"] = semantics
        part["probability_source"] = "UNAVAILABLE"
        part["probability_value"] = np.nan
        part["q_value"] = np.nan
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def load_historical_cells(
    paths: AuditPaths, identities: pd.DataFrame, beidan_sha256: str
) -> pd.DataFrame:
    """Audit unstamped historical SP and explicitly settlement-derived SP separately."""
    with _connect(paths.beidan) as connection:
        features = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue_code, match_idx, kickoff_ts,
                   official_sp_3, official_sp_1, official_sp_0
            FROM match_features
            WHERE issue IS NOT NULL AND match_idx IS NOT NULL
            ORDER BY issue, match_idx
            """,
            connection,
        )
        settlements = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue_code, match_idx,
                   sp_home, sp_draw, sp_away, imported_at
            FROM official_500_settlements
            ORDER BY issue, match_idx
            """,
            connection,
        )

    historical_identity = identities[
        ["issue_code", "match_idx", "fixture_identity", "identity_consistent"]
    ]
    features = features.merge(
        historical_identity,
        on=["issue_code", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    features["fixture_identity"] = features["fixture_identity"].fillna(
        "bjslot:"
        + features["issue_code"]
        + ":"
        + features["match_idx"].astype(str).str.zfill(3)
    )
    features["identity_consistent"] = features["identity_consistent"].fillna(True)
    features["kickoff_utc"] = _iso_utc(features["kickoff_ts"], naive_timezone=SHANGHAI)
    unstamped = _long_triplets(
        features,
        price_columns={
            "3": "official_sp_3",
            "1": "official_sp_1",
            "0": "official_sp_0",
        },
        source_id="beidan_match_features_official_sp",
        snapshot_kind="historical_unstamped",
        semantics="timestamp_unproven",
        provenance_sha256=beidan_sha256,
    )

    settlements = settlements.merge(
        features[
            [
                "issue_code",
                "match_idx",
                "kickoff_utc",
                "fixture_identity",
                "identity_consistent",
            ]
        ],
        on=["issue_code", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    settlements["fixture_identity"] = settlements["fixture_identity"].fillna(
        "bjslot:"
        + settlements["issue_code"]
        + ":"
        + settlements["match_idx"].astype(str).str.zfill(3)
    )
    settlements["identity_consistent"] = settlements["identity_consistent"].fillna(True)
    settlements["imported_at"] = _iso_utc(settlements["imported_at"])
    settlement = _long_triplets(
        settlements,
        price_columns={"3": "sp_home", "1": "sp_draw", "0": "sp_away"},
        source_id="official_500_settlement_sp",
        snapshot_kind="settlement_import",
        semantics="settlement",
        provenance_sha256=beidan_sha256,
        observed_column="imported_at",
    )
    return pd.concat([unstamped, settlement], ignore_index=True)


def load_proxy_cells(
    paths: AuditPaths, identities: pd.DataFrame, materializer_sha256: str
) -> pd.DataFrame:
    """Load the accepted #238 consensus probabilities as a relative fair-odds proxy."""
    view = paths.materializer / "inference/relative_horizon_view.parquet"
    columns = [
        "issue_code",
        "match_idx",
        "snapshot_kind",
        "outcome_code",
        "q_eu_raw_1x2",
        "q_eu_bjline",
        "causal_grade",
        "mapping_accepted",
    ]
    frame = pads.dataset(view, format="parquet").to_table(columns=columns).to_pandas()
    frame["issue_code"] = frame["issue_code"].astype("string")
    frame["outcome_code"] = frame["outcome_code"].astype("string")
    frame = frame.merge(
        identities[
            [
                "issue_code",
                "match_idx",
                "kickoff_utc",
                "fixture_identity",
                "identity_consistent",
            ]
        ],
        on=["issue_code", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    frame["source_id"] = "eu_consensus_fair_odds_268"
    frame["sp_value"] = 1.0 / pd.to_numeric(frame["q_eu_raw_1x2"], errors="coerce")
    frame["probability_source"] = "Q_EU_BJLINE_238"
    frame["probability_value"] = pd.to_numeric(frame["q_eu_bjline"], errors="coerce")
    frame["q_value"] = frame["probability_value"] * frame["sp_value"]
    frame["observed_at_utc"] = pd.NA
    frame["decision_epoch_utc"] = pd.NA
    frame["source_semantics"] = "relative_proxy"
    frame["provenance_sha256"] = materializer_sha256
    frame["identity_consistent"] = frame["identity_consistent"].fillna(False)
    frame["fixture_identity"] = frame["fixture_identity"].fillna("")
    return frame[
        [
            "issue_code",
            "match_idx",
            "outcome_code",
            "source_id",
            "snapshot_kind",
            "observed_at_utc",
            "decision_epoch_utc",
            "kickoff_utc",
            "sp_value",
            "probability_source",
            "probability_value",
            "q_value",
            "fixture_identity",
            "provenance_sha256",
            "source_semantics",
            "identity_consistent",
        ]
    ]


def load_strict_cells(
    paths: AuditPaths, identities: pd.DataFrame, panel_sha256: str
) -> pd.DataFrame:
    """Select one latest decision-available #216 SP vector per exact fixture."""
    root = paths.strict_panel
    snapshots = pd.read_parquet(root / "sources/selected_snapshots.parquet")
    epochs = pd.read_parquet(
        root / "inference/issue_epochs.parquet", columns=["issue", "decision_epoch_utc"]
    )
    matches = pd.read_parquet(
        root / "sources/matches.parquet",
        columns=["match_id", "issue", "match_idx", "kickoff_ts_utc"],
    )
    if epochs.duplicated("issue").any() or matches.duplicated("match_id").any():
        raise ValueError("#216 strict identity or epoch is not unique")
    snapshots = snapshots.merge(
        matches, on="match_id", how="left", validate="many_to_one"
    )
    snapshots = snapshots.merge(epochs, on="issue", how="left", validate="many_to_one")
    observed = pd.to_datetime(
        snapshots["market_observed_ts_utc"], utc=True, errors="coerce"
    )
    decision = pd.to_datetime(
        snapshots["decision_epoch_utc"], utc=True, errors="coerce"
    )
    snapshots["pre_decision"] = observed.le(decision)
    snapshots["observed_sort"] = observed
    snapshots = (
        snapshots.sort_values(
            ["match_id", "pre_decision", "observed_sort", "id"],
            ascending=[True, True, True, True],
            kind="mergesort",
        )
        .groupby("match_id", sort=False, as_index=False)
        .tail(1)
    )
    snapshots["issue_code"] = snapshots["issue"].astype("string")
    snapshots = snapshots.merge(
        identities[
            [
                "issue_code",
                "match_idx",
                "kickoff_utc",
                "fixture_identity",
                "identity_consistent",
            ]
        ],
        on=["issue_code", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    source_kickoff = _to_utc(snapshots["kickoff_ts_utc"])
    candidate_kickoff = _to_utc(snapshots["kickoff_utc"])
    snapshots["identity_consistent"] = (
        snapshots["identity_consistent"].fillna(False)
        & source_kickoff.notna()
        & candidate_kickoff.notna()
        & source_kickoff.eq(candidate_kickoff)
    )
    snapshots["observed_at_utc"] = _iso_utc(snapshots["market_observed_ts_utc"])
    snapshots["decision_epoch_utc"] = _iso_utc(snapshots["decision_epoch_utc"])
    rows: list[pd.DataFrame] = []
    for outcome, column in (("3", "sp_3"), ("1", "sp_1"), ("0", "sp_0")):
        part = snapshots[
            [
                "issue_code",
                "match_idx",
                "observed_at_utc",
                "decision_epoch_utc",
                "kickoff_utc",
                "fixture_identity",
                "identity_consistent",
            ]
        ].copy()
        part["outcome_code"] = outcome
        part["sp_value"] = pd.to_numeric(snapshots[column], errors="coerce")
        part["source_id"] = "strict_prospective_216"
        part["snapshot_kind"] = "strict_decision_epoch"
        part["probability_source"] = "UNAVAILABLE"
        part["probability_value"] = np.nan
        part["q_value"] = np.nan
        part["provenance_sha256"] = panel_sha256
        part["source_semantics"] = "strict"
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def load_all_cells(paths: AuditPaths, inventory: pd.DataFrame) -> pd.DataFrame:
    by_source = inventory.set_index("source_id")
    present = {
        source: by_source.loc[source, "availability"] == "PRESENT"
        for source in by_source.index
    }
    identities = _identities(
        paths,
        candidate_available=present["eu_proxy_backfill"],
        beidan_available=present["beidan_xlsm"],
        registry_available=present["issue_registry"],
    )
    frames: list[pd.DataFrame] = []
    if present["beidan_xlsm"]:
        frames.append(
            load_historical_cells(
                paths, identities, str(by_source.loc["beidan_xlsm", "sha256"])
            )
        )
    if present["eu_proxy_backfill"] and present["bj238_materializer"]:
        frames.append(
            load_proxy_cells(
                paths, identities, str(by_source.loc["bj238_materializer", "sha256"])
            )
        )
    if present["eu_proxy_backfill"] and present["bj216_strict_panel"]:
        frames.append(
            load_strict_cells(
                paths, identities, str(by_source.loc["bj216_strict_panel", "sha256"])
            )
        )
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(
        columns=[
            "issue_code",
            "match_idx",
            "outcome_code",
            "source_id",
            "snapshot_kind",
            "observed_at_utc",
            "decision_epoch_utc",
            "kickoff_utc",
            "sp_value",
            "probability_source",
            "probability_value",
            "q_value",
            "fixture_identity",
            "provenance_sha256",
            "source_semantics",
            "identity_consistent",
        ]
    )
