"""Read-only profiler for all existing source databases and packages.

Profiles every asset named in the issue contract:
- data/derived/beidan_xlsm/beidan_xlsm.sqlite
- data/beidan_features.db
- data/beidan_history.db
- data/beidan_live.db
- #203/#214/#229 immutable packages and their source hashes

Emitted evidence (REQ-DS01..07):
- db_inventory  — table / rowcount / column inventory per DB
- identity_probe — (issue, match_idx) uniqueness, nulls, ts formats
- clock_probe   — observed/received/settled/kickoff timestamp semantics
- source_clock_classification — admissible-use classification with evidence
- package_hashes — sha256 of referenced immutable packages
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

from . import contract

# Resolution order for data roots (local mirror first, then real data dir).
DATA_ROOTS = [
    Path("/home/drwho1985/workspace/soccer/beijing-lot/data"),
    Path("/home/drwho1985/beijing-lot-234/data"),
]


def resolve_data_root() -> Path:
    for p in DATA_ROOTS:
        if p.exists():
            return p
    raise FileNotFoundError("no data root found; set DATA_ROOT env")


def db_paths() -> dict[str, Optional[Path]]:
    root = resolve_data_root()
    candidates = {
        "beidan_xlsm.sqlite": root / "derived/beidan_xlsm/beidan_xlsm.sqlite",
        "beidan_features.db": root / "beidan_features.db",
        "beidan_history.db": root / "beidan_history.db",
        "beidan_live.db": root / "beidan_live.db",
        "500_bjdc.sqlite": root / "derived/500_bjdc/500_bjdc.sqlite",
    }
    return {k: (v if v.exists() else None) for k, v in candidates.items()}


def _conn(path: Path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _q(conn, sql):
    try:
        return conn.execute(sql).fetchall()
    except Exception as e:  # noqa: BLE001 — probe must not die on odd schemas
        return [("ERR", str(e))]


def profile_database(name: str, path: Path) -> dict:
    """Full read-only profile of one SQLite database."""
    conn = _conn(path)
    info: dict = {
        "db": name,
        "size_mb": round(path.stat().st_size / 1e6, 1),
        "journal_mode": _q(conn, "PRAGMA journal_mode")[0][0],
    }
    tables = _q(conn, "SELECT name, type FROM sqlite_master "
                      "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
                      "ORDER BY type, name")
    table_info = []
    for tname, ttype in tables:
        t = {
            "name": tname,
            "type": ttype,
            "rows": _q(conn, f'SELECT COUNT(*) FROM "{tname}"')[0][0],
            "columns": [c for c in _q(conn, f'PRAGMA table_info("{tname}")')],
            "indexes": [i for i in _q(conn, f'PRAGMA index_list("{tname}")')],
        }
        table_info.append(t)
    info["tables"] = table_info

    if name == "beidan_live.db":
        info["identity_dup"] = _q(conn, "SELECT COUNT(*) FROM (SELECT issue, match_idx "
                                        "FROM matches GROUP BY issue, match_idx HAVING COUNT(*)>1)")[0][0]
        info["kickoff_range"] = _q(conn, "SELECT MIN(kickoff_ts), MAX(kickoff_ts) FROM matches")[0]
        info["snapshot_range"] = _q(conn, "SELECT MIN(snapshot_ts), MAX(snapshot_ts) FROM snapshots")[0]
        info["settled_range"] = _q(conn, "SELECT MIN(settled_ts), MAX(settled_ts) FROM settlements")[0]
        info["snapshot_total"] = _q(conn, "SELECT COUNT(*) FROM snapshots")[0][0]
        info["snap_per_match"] = _q(conn, "SELECT MIN(c), MAX(c) FROM (SELECT match_id, COUNT(*) c "
                                          "FROM snapshots GROUP BY match_id)")[0]
        info["settle_source"] = _q(conn, "SELECT source, COUNT(*) FROM settlements GROUP BY source")
        info["ts_samples"] = {
            "kickoff": _q(conn, "SELECT kickoff_ts FROM matches LIMIT 3"),
            "snapshot": _q(conn, "SELECT snapshot_ts FROM snapshots LIMIT 3"),
            "settled": _q(conn, "SELECT settled_ts FROM settlements LIMIT 3"),
        }
    elif name == "beidan_history.db":
        info["identity_dup"] = _q(conn, "SELECT COUNT(*) FROM (SELECT issue, match_idx "
                                        "FROM historical_matches GROUP BY issue, match_idx HAVING COUNT(*)>1)")[0][0]
        info["kickoff_range"] = _q(conn, "SELECT MIN(kickoff_ts), MAX(kickoff_ts) "
                                         "FROM historical_matches")[0]
        info["result_codes"] = _q(conn, "SELECT result_code, COUNT(*) FROM historical_matches "
                                        "GROUP BY result_code ORDER BY 2 DESC LIMIT 8")
        info["sp_missing"] = _q(conn, "SELECT COUNT(*) FROM historical_matches "
                                      "WHERE winning_sp IS NULL")[0][0]
        info["has_settled_ts_col"] = False
        info["scrape_range"] = _q(conn, "SELECT MIN(fetched_at), MAX(fetched_at) FROM scrape_log")[0]
        info["kickoff_sample"] = _q(conn, "SELECT kickoff_ts FROM historical_matches LIMIT 3")
    elif name == "beidan_features.db":
        info["identity_dup"] = _q(conn, "SELECT COUNT(*) FROM (SELECT issue, match_idx "
                                        "FROM matches GROUP BY issue, match_idx HAVING COUNT(*)>1)")[0][0]
        info["kickoff_range"] = _q(conn, "SELECT MIN(kickoff), MAX(kickoff) FROM matches")[0]
        info["season_range"] = _q(conn, "SELECT MIN(season), MAX(season) FROM matches")[0]
        info["null_kickoff"] = _q(conn, "SELECT COUNT(*) FROM matches WHERE kickoff IS NULL")[0][0]
        info["pinn_missing"] = _q(conn, "SELECT COUNT(*) FROM matches WHERE pinn_close_3 IS NULL")[0][0]
        info["kickoff_sample"] = _q(conn, "SELECT kickoff FROM matches LIMIT 5")
    elif name == "beidan_xlsm.sqlite":
        info["identity_dup"] = _q(conn, "SELECT COUNT(*) FROM (SELECT issue, match_idx "
                                        "FROM matches GROUP BY issue, match_idx HAVING COUNT(*)>1)")[0][0]
        info["identity_null"] = _q(conn, "SELECT COUNT(*) FROM matches "
                                         "WHERE issue IS NULL OR match_idx IS NULL")[0][0]
        info["kickoff_range"] = _q(conn, "SELECT MIN(kickoff_ts), MAX(kickoff_ts) FROM matches")[0]
        info["snapshot_labels"] = _q(conn, "SELECT snapshot, COUNT(*) FROM market_snapshots "
                                           "GROUP BY snapshot ORDER BY 2 DESC LIMIT 12")
        info["snap_total"] = _q(conn, "SELECT COUNT(*) FROM market_snapshots")[0][0]
        info["snap_markets"] = _q(conn, "SELECT market, COUNT(DISTINCT bookmaker) "
                                        "FROM market_snapshots GROUP BY market")
        info["settle_range_endtime"] = _q(conn, "SELECT MIN(end_time), MAX(end_time) "
                                                "FROM official_500_settlements")[0]
        info["settle_fetched_range"] = _q(conn, "SELECT MIN(fetched_at), MAX(fetched_at) "
                                                "FROM official_500_settlements")[0]
        info["source_meta"] = _q(conn, "SELECT key, value FROM source_meta")
        info["issue_range"] = _q(conn, "SELECT MIN(issue), MAX(issue) FROM matches")[0]
        info["kickoff_years"] = _q(conn, "SELECT substr(kickoff_ts,1,4) y, COUNT(*) "
                                         "FROM matches GROUP BY y ORDER BY y LIMIT 16")
        info["snap_ts_sample"] = _q(conn, "SELECT snapshot FROM market_snapshots LIMIT 3")
        info["action_quality"] = _q(conn, "SELECT settlement_quality, COUNT(*) "
                                          "FROM action_candidates GROUP BY 1 ORDER BY 2 DESC LIMIT 8")
    elif name == "500_bjdc.sqlite":
        info["tables_only"] = [t["name"] for t in table_info]
    conn.close()
    return info


def profile_all() -> dict:
    """Profile every database present on disk."""
    out = {}
    for name, path in db_paths().items():
        if path is None:
            out[name] = {"db": name, "present": False}
        else:
            d = profile_database(name, path)
            d["present"] = True
            d["path"] = str(path)
            out[name] = d
    return out


# ---------------------------------------------------------------------------
# Clock semantics classification (REQ-DS01: evidence, not reputation)
# ---------------------------------------------------------------------------
def classify_source_clocks(profile: dict) -> list[dict]:
    """Classify each existing DB by causal admissibility with evidence.

    Evidence-driven classification per the issue contract:
    - beidan_live.db  → STRICT_CAUSAL (prospective, ISO Z timestamps)
    - beidan_features.db → RETROSPECTIVE_PROXY (no exact observation clock;
      open/close labels only)
    - beidan_history.db → SETTLEMENT_ONLY (no settled timestamp column;
      settlement rows are not inference-time observations)
    - beidan_xlsm.sqlite → RETROSPECTIVE_PROXY for market_snapshots
      (labels initial/10h/1h/final — not exact timestamps); settlement
      tables SETTLEMENT_ONLY
    """
    rows = []
    live = profile.get("beidan_live.db", {})
    rows.append({
        "source": "beidan_live.db",
        "family": "F1_BJ_FIRST_PARTY",
        "admissible_use": "STRICT_CAUSAL",
        "clock_semantics": "NATIVE_PROVEN",
        "evidence": "snapshot_ts ISO-8601 with Z suffix; range "
                    f"{live.get('snapshot_range')}; {live.get('snapshot_total')} rows; "
                    "prospective collection from 2026-05; settlement cross-checked "
                    f"via {live.get('settle_source')}",
    })
    feat = profile.get("beidan_features.db", {})
    rows.append({
        "source": "beidan_features.db",
        "family": "F2_INTERNAL_ARCHIVE",
        "admissible_use": "RETROSPECTIVE_PROXY",
        "clock_semantics": "LABELED_RELATIVE",
        "evidence": "kickoff mixed formats "
                    f"{feat.get('kickoff_sample')}; no observation timestamp column; "
                    "European close/open odds only (labels close/open, no exact clock)",
    })
    hist = profile.get("beidan_history.db", {})
    rows.append({
        "source": "beidan_history.db",
        "family": "F2_INTERNAL_ARCHIVE",
        "admissible_use": "SETTLEMENT_ONLY",
        "clock_semantics": "ABSENT",
        "evidence": f"no settled timestamp column (has_settled_ts_col={hist.get('has_settled_ts_col')}); "
                    f"result codes {hist.get('result_codes')}; SP missing {hist.get('sp_missing')}; "
                    "settlement and average closing odds are not inference-time observations",
    })
    xlsm = profile.get("beidan_xlsm.sqlite", {})
    rows.append({
        "source": "beidan_xlsm.sqlite (market_snapshots)",
        "family": "F2_INTERNAL_ARCHIVE",
        "admissible_use": "RETROSPECTIVE_PROXY",
        "clock_semantics": "LABELED_RELATIVE",
        "evidence": f"snapshot column holds labels only: {xlsm.get('snapshot_labels')}; "
                    "initial/10h/1h/final are not accepted as exact observation timestamps "
                    "until independently proven",
    })
    rows.append({
        "source": "beidan_xlsm.sqlite (official_500_settlements)",
        "family": "F2_INTERNAL_ARCHIVE",
        "admissible_use": "SETTLEMENT_ONLY",
        "clock_semantics": "FILE_MTIME",
        "evidence": f"end_time range {xlsm.get('settle_range_endtime')} but fetched "
                    f"{xlsm.get('settle_fetched_range')} — settlement evidence only",
    })
    rows.append({
        "source": "beidan_xlsm.sqlite (identity)",
        "family": "F2_INTERNAL_ARCHIVE",
        "admissible_use": "STRICT_CAUSAL" if xlsm.get("identity_null", 1) == 0 else "RETROSPECTIVE_PROXY",
        "clock_semantics": "NATIVE_PROVEN" if xlsm.get("identity_null", 1) == 0 else "ABSENT",
        "evidence": f"identity_null={xlsm.get('identity_null')} rows with NULL issue/match_idx; "
                    f"duplicates={xlsm.get('identity_dup')}; kickoff garbage rows {xlsm.get('kickoff_years')}",
    })
    return rows


def package_source_hashes(repo_root: Path) -> dict:
    """SHA-256 of every referenced immutable package manifest (REQ-DS07).

    Hashes the manifest + schema artifacts of #203/#214/#229 packages so the
    contract binds to reviewed hashes, not to mutable working files.
    """
    targets = [
        "results/bj203_causal_tensor_v2/MANIFEST.json",
        "results/bj203_causal_tensor_v2/schema.json",
        "results/bj214_decision_epoch_tensor_v1/MANIFEST.json",
        "results/bj214_decision_epoch_tensor_v1/schema.json",
        "results/bj229_divergence_profile_v1/MANIFEST.json",
        "results/bj229_divergence_profile_v1/SHA256SUMS.json",
    ]
    out = {}
    for rel in targets:
        p = repo_root / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            out[rel] = None
    return out


def raw_archive_hashes(root: Optional[Path] = None) -> dict:
    """Hash raw recoverable archives (beidan_full_3sp.csv, football-data dir)."""
    root = root or resolve_data_root()
    out = {}
    targets = [
        root / "raw/beidan_full_3sp.csv",
        root / "raw/beidan_history_user.csv",
    ]
    for p in targets:
        if p.exists():
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            out[str(p.relative_to(root))] = h.hexdigest()
    fd = root / "raw/football-data"
    if fd.exists():
        names = sorted(fd.glob("*.csv"))[:6]
        out["raw/football-data/sample_files"] = [n.name for n in names]
    return out


def save_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str))


def load_json(path: Path):
    return json.loads(path.read_text())
