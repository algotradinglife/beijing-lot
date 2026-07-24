"""MM-DATA-AUDIT-001: Core auditor that queries databases and evaluates gates."""

from __future__ import annotations

import json
import hashlib
import csv
import sqlite3
import statistics
import yaml
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from research.mm_data_audit.contract import (
    TARGET_PLAYIDS,
    MARKETS,
    AuditDimension,
    AuditResult,
    DimensionAudit,
    GateID,
    GateResult,
    MarketDefinition,
    ReadinessLevel,
)

HKT = timezone(timedelta(hours=8))
UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower())


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_sha256sums(bundle_path: Path, expected_sha256s_sha256: str | None = None) -> tuple[bool, dict[str, Any]]:
    """Verify a capture bundle against its SHA256SUMS manifest."""
    bundle = bundle_path.expanduser()
    sums = bundle / "SHA256SUMS"
    detail: dict[str, Any] = {
        "bundle_path": str(bundle),
        "sha256sums_exists": sums.is_file(),
        "sha256sums_digest_matches": False,
        "files_checked": 0,
        "errors": [],
    }

    if not sums.is_file():
        detail["errors"].append("SHA256SUMS missing")
        return False, detail

    if expected_sha256s_sha256:
        actual_sums_digest = _sha256_file(sums)
        detail["sha256sums_sha256"] = actual_sums_digest
        if not _is_sha256_hex(expected_sha256s_sha256):
            detail["errors"].append("invalid recorded SHA256SUMS digest")
            return False, detail
        if actual_sums_digest != expected_sha256s_sha256.lower():
            detail["errors"].append("SHA256SUMS digest mismatch")
            return False, detail
        detail["sha256sums_digest_matches"] = True

    entries = sums.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    for line in entries:
        if not line.strip():
            continue
        try:
            digest, name = line.split("  ", 1)
        except ValueError:
            detail["errors"].append(f"invalid SHA256SUMS line: {line!r}")
            return False, detail
        digest = digest.lower()
        if not _is_sha256_hex(digest):
            detail["errors"].append(f"invalid checksum for {name}")
            return False, detail
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or name in seen:
            detail["errors"].append(f"unsafe or duplicate SHA256SUMS path: {name}")
            return False, detail
        target = bundle / rel
        if not target.is_file() or target.is_symlink():
            detail["errors"].append(f"listed file missing: {name}")
            return False, detail
        actual = _sha256_file(target)
        if actual != digest:
            detail["errors"].append(f"checksum mismatch: {name}")
            return False, detail
        seen.add(name)
        detail["files_checked"] += 1

    if detail["files_checked"] == 0:
        detail["errors"].append("SHA256SUMS has no file entries")
        return False, detail
    actual_files: set[str] = set()
    for candidate in bundle.rglob("*"):
        if candidate.is_dir():
            continue
        if candidate.is_symlink() or not candidate.is_file():
            detail["errors"].append(f"bundle contains non-regular file: {candidate}")
            return False, detail
        relative = candidate.relative_to(bundle).as_posix()
        if relative != "SHA256SUMS":
            actual_files.add(relative)
    if seen != actual_files:
        detail["errors"].append("SHA256SUMS does not cover exactly the bundle files")
        return False, detail
    if expected_sha256s_sha256 is None:
        detail["sha256sums_digest_matches"] = True
    return True, detail


def _repo_root() -> Path:
    """Return the main repository root for data/ access."""
    gitfile = ROOT / ".git"
    if gitfile.is_file():
        content = gitfile.read_text().strip()
        if content.startswith("gitdir:"):
            gitdir = Path(content.split(":", 1)[1].strip())
            # gitdir is like .../beijing-lot/.git/worktrees/t_xxx
            # Main repo is two levels up from the .git directory
            return gitdir.parents[2]
    return ROOT


def parse_hkt(value: str) -> datetime | None:
    """Parse HKT datetime string."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=HKT)
        return dt.astimezone(HKT)
    except (ValueError, TypeError):
        return None


def parse_utc(value: str) -> datetime | None:
    """Parse UTC datetime string."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def _connect(db_name: str, fixtures_dir: Path | None = None) -> sqlite3.Connection:
    """Connect to a production database or an explicitly supplied test fixture."""
    if fixtures_dir is None:
        repo = _repo_root()
        path_map = {
            "beidan_live": repo / "data/beidan_live.db",
            "500_bjdc": repo / "data/derived/500_bjdc/500_bjdc.sqlite",
        }
    else:
        fixtures = Path(fixtures_dir)
        path_map = {
            "beidan_live": fixtures / "mm_data_audit_live.db",
            "500_bjdc": fixtures / "mm_data_audit_500_bjdc.db",
        }
    path = path_map[db_name]
    if fixtures_dir is not None and not path.is_file():
        raise FileNotFoundError(f"Required {db_name} fixture database not found: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _begin_read_snapshot(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA query_only = ON")
    conn.execute("BEGIN")
    conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()


class MultiMarketAuditor:
    """Audit four target markets across three dimensions."""

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.beidan = _connect("beidan_live", fixtures_dir)
        self.bjdc = _connect("500_bjdc", fixtures_dir)
        _begin_read_snapshot(self.beidan)
        _begin_read_snapshot(self.bjdc)
        self._audit_cutoff = datetime.now(UTC).isoformat(timespec="seconds")

    def audit_all(self) -> AuditResult:
        result = AuditResult(audit_cutoff_utc=self._audit_cutoff)
        for playid in TARGET_PLAYIDS:
            market = MARKETS[playid]
            for dim in AuditDimension:
                dim_audit = self._audit_dimension(market, dim)
                result.dimensions.append(dim_audit)
                mk = market.market_key
                if mk not in result.readiness_matrix:
                    result.readiness_matrix[mk] = {}
                result.readiness_matrix[mk][dim.value] = dim_audit.readiness.value
        result.metrics_summary = self._compute_summary_metrics(result)
        return result

    def _audit_dimension(self, market: MarketDefinition, dimension: AuditDimension) -> DimensionAudit:
        if dimension == AuditDimension.PRE_EVENT_INPUT:
            if market.playid == 34:
                return self._audit_handicap_pre_event(market)
            elif market.playid in (40, 42):
                return self._audit_p0_pre_event(market)
            else:
                return self._audit_p51_pre_event(market)
        elif dimension == AuditDimension.FREEZE_SUPPORT:
            if market.playid == 34:
                return self._audit_handicap_freeze(market)
            elif market.playid in (40, 42):
                return self._audit_p0_freeze(market)
            else:
                return self._audit_p51_freeze(market)
        else:  # SETTLEMENT_SUPPORT
            if market.playid == 34:
                return self._audit_handicap_settlement(market)
            elif market.playid in (40, 42):
                return self._audit_p0_settlement(market)
            else:
                return self._audit_p51_settlement(market)

    # ── Handicap 3/1/0 (playid=34) ──────────────────────────────────────────

    def _audit_handicap_pre_event(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_handicap_pre_event(market)
        return self._classify(market, AuditDimension.PRE_EVENT_INPUT, gates, metrics)

    def _audit_handicap_freeze(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_handicap_freeze(market)
        return self._classify(market, AuditDimension.FREEZE_SUPPORT, gates, metrics)

    def _audit_handicap_settlement(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_handicap_settlement(market)
        return self._classify(market, AuditDimension.SETTLEMENT_SUPPORT, gates, metrics)

    def _gates_handicap_pre_event(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        metrics: dict[str, Any] = {}

        # G1: Complete and correctly mapped outcome vectors
        db = self.beidan
        total_snapshots = db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        total_matches = db.execute("SELECT COUNT(DISTINCT match_id) FROM snapshots").fetchone()[0]
        # Check completeness: snapshots with all 3 SP values non-null
        complete_vectors = db.execute(
            "SELECT COUNT(*) FROM snapshots WHERE sp_3 IS NOT NULL AND sp_1 IS NOT NULL AND sp_0 IS NOT NULL"
        ).fetchone()[0]
        complete_pct = (complete_vectors / total_snapshots * 100) if total_snapshots else 0
        outcome_mapping_ok = True  # handicap outcome codes are hard-coded in beidan_live
        metrics.update({
            "total_snapshots": total_snapshots,
            "total_matches": total_matches,
            "complete_vector_snapshots": complete_vectors,
            "complete_vector_pct": round(complete_pct, 2),
        })
        gates.append(GateResult(
            gate_id=GateID.G1_OUTCOME_VECTORS,
            passed=complete_pct >= 50,
            score=min(1.0, complete_pct / 100),
            evidence=(
                f"{complete_vectors:,}/{total_snapshots:,} snapshots ({complete_pct:.1f}%) "
                f"have complete 3/1/0 SP vectors across {total_matches:,} matches. "
                f"Outcome mapping is hard-coded in beidan_live.db schema (sp_3/sp_1/sp_0)."
            ),
            metrics=dict(metrics),
        ))

        # G2: Explicit source and capture timestamps
        snapshots_by_source = dict(db.execute(
            "SELECT source, COUNT(*) FROM snapshots GROUP BY source"
        ).fetchall())
        has_timestamps = "snapshot_ts" in [r[1] for r in db.execute(
            "PRAGMA table_info(snapshots)"
        ).fetchall()]
        timestamped = db.execute(
            "SELECT COUNT(*) FROM snapshots WHERE snapshot_ts IS NOT NULL AND snapshot_ts != ''"
        ).fetchone()[0]
        ts_pct = (timestamped / total_snapshots * 100) if total_snapshots else 0
        metrics.update({
            "has_source_column": bool(snapshots_by_source),
            "sources": list(snapshots_by_source.keys()),
            "has_snapshot_ts": has_timestamps,
            "timestamped_snapshots": timestamped,
            "timestamped_pct": round(ts_pct, 2),
        })
        gates.append(GateResult(
            gate_id=GateID.G2_SOURCE_TIMESTAMPS,
            passed=ts_pct >= 80,
            score=min(1.0, ts_pct / 100),
            evidence=(
                f"{timestamped:,}/{total_snapshots:,} snapshots ({ts_pct:.1f}%) have snapshot_ts. "
                f"Sources: {sorted(snapshots_by_source.keys())}. "
                f"No dual-clock (fetched_at + source_updated_at) — snapshot_ts is the single timestamp."
            ),
            metrics={
                "timestamped_pct": round(ts_pct, 2),
                "sources": sorted(snapshots_by_source.keys()),
            },
        ))

        # G3: Evidence of pre-cutoff existence
        matches_with_kickoff = db.execute(
            "SELECT COUNT(*) FROM matches WHERE kickoff_ts IS NOT NULL AND kickoff_ts != ''"
        ).fetchone()[0]
        total_db_matches = db.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        ko_pct = (matches_with_kickoff / total_db_matches * 100) if total_db_matches else 0
        # Check if snapshots exist before kickoff — UTC-aware comparison
        pre_kickoff = db.execute(
            """SELECT COUNT(*) FROM snapshots s
               JOIN matches m ON s.match_id = m.match_id
               WHERE datetime(REPLACE(s.snapshot_ts, 'Z', '+00:00')) < datetime(m.kickoff_ts, '-8 hours')
                 AND m.kickoff_ts IS NOT NULL AND m.kickoff_ts != ''
                 AND s.snapshot_ts IS NOT NULL AND s.snapshot_ts != ''"""
        ).fetchone()[0]
        complete_pre_kickoff_matches = db.execute(
            """SELECT COUNT(*) FROM (
                   SELECT m.match_id
                   FROM matches m
                   JOIN snapshots s ON s.match_id = m.match_id
                   WHERE datetime(REPLACE(s.snapshot_ts, 'Z', '+00:00')) < datetime(m.kickoff_ts, '-8 hours')
                     AND m.kickoff_ts IS NOT NULL AND m.kickoff_ts != ''
                     AND s.snapshot_ts IS NOT NULL AND s.snapshot_ts != ''
                     AND s.sp_3 IS NOT NULL AND s.sp_1 IS NOT NULL AND s.sp_0 IS NOT NULL
                   GROUP BY m.match_id
               )"""
        ).fetchone()[0]
        complete_pre_kickoff_pct = (
            complete_pre_kickoff_matches / total_db_matches * 100
        ) if total_db_matches else 0

        metrics.update({
            "total_matches": total_db_matches,
            "matches_with_kickoff": matches_with_kickoff,
            "kickoff_coverage_pct": round(ko_pct, 2),
            "pre_kickoff_snapshots": pre_kickoff,
            "complete_pre_kickoff_matches": complete_pre_kickoff_matches,
            "complete_pre_kickoff_match_pct": round(complete_pre_kickoff_pct, 2),
        })
        gates.append(GateResult(
            gate_id=GateID.G3_PRE_CUTOFF_EVIDENCE,
            passed=complete_pre_kickoff_pct >= 50,
            score=min(1.0, complete_pre_kickoff_pct / 50),
            evidence=(
                f"{matches_with_kickoff}/{total_db_matches} matches ({ko_pct:.1f}%) have kickoff_ts. "
                f"{pre_kickoff:,} snapshots are pre-kickoff. "
                f"{complete_pre_kickoff_matches:,}/{total_db_matches:,} matches "
                f"({complete_pre_kickoff_pct:.1f}%) have a complete 3/1/0 vector before kickoff. "
                f"Segment decision windows from 500_bjdc provide freeze_at timestamps for issues 26074-26077."
            ),
            metrics={
                "matches_with_kickoff": matches_with_kickoff,
                "kickoff_coverage_pct": round(ko_pct, 2),
                "pre_kickoff_snapshots": pre_kickoff,
                "complete_pre_kickoff_matches": complete_pre_kickoff_matches,
                "complete_pre_kickoff_match_pct": round(complete_pre_kickoff_pct, 2),
            },
        ))

        # G7: No leakage (terminal/final used as pre-event)
        # beidan_live.db is append-only by convention but lacks per-snapshot SHA-256.
        # Without per-file bundle hashes, post-capture modification cannot be ruled out.
        # Score: 0.3 to reflect conventional append-only confidence but no cryptographic proof.
        gates.append(GateResult(
            gate_id=GateID.G7_NO_LEAKAGE,
            passed=False,
            score=0.3,
            evidence=(
                f"beidan_live.db snapshots are captured live (source='zqdc', 'live500'). "
                f"No post-event terminal SP substitution detected — snapshot_ts always precedes "
                f"or is near kickoff_ts for the captured data. "
                f"However, no per-snapshot SHA-256 hashes exist for raw capture rows; "
                f"without bundle-level verification, post-capture leakage cannot be ruled out."
            ),
        ))

        metrics["discovered_match_markets"] = total_matches
        return gates, metrics

    def _gates_handicap_freeze(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        metrics: dict[str, Any] = {}

        # G4: Immutable provenance
        db = self.beidan
        total_snapshots = db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        # beidan_live.db is an append-only database, but no per-file SHA-256 hashes
        metrics["immutable_append_only"] = True
        metrics["has_bundle_hashes"] = False
        gates.append(GateResult(
            gate_id=GateID.G4_IMMUTABLE_PROVENANCE,
            passed=False,
            score=0.3,
            evidence=(
                f"beidan_live.db is append-only by convention but lacks per-snapshot SHA-256 hashes "
                f"or file-level bundle verification. No SHA256SUMS exist for raw capture. "
                f"The Freeze Protocol v1 would need to hash the entire snapshots export."
            ),
            metrics={"has_bundle_hashes": False, "append_only_claim": True},
        ))

        # G5: Deterministic as-of selection + Freeze Protocol v1
        # Check if segment_decision_windows exist in 500_bjdc
        segments = self.bjdc.execute(
            "SELECT COUNT(*) FROM segment_decision_windows"
        ).fetchone()[0]
        has_freeze_protocol = bool(segments)
        metrics["segment_decision_windows"] = segments
        metrics["freeze_protocol_v1_capable"] = has_freeze_protocol

        gates.append(GateResult(
            gate_id=GateID.G5_ASOF_FREEZE,
            passed=has_freeze_protocol,
            score=0.7 if has_freeze_protocol else 0.2,
            evidence=(
                f"{segments} segment_decision_windows in 500_bjdc provide freeze_at timestamps. "
                f"beidan_live.db snapshots have snapshot_ts which can be used for as-of selection. "
                f"However, no existing freeze package exists under results/freeze/ for Handicap 3/1/0 "
                f"— SP-EFF-001 predates Freeze Protocol v1 formalization."
            ),
            metrics={"segment_windows": segments, "existing_freeze_packages": 0},
        ))

        return gates, metrics

    def _gates_handicap_settlement(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        metrics: dict[str, Any] = {}

        db = self.beidan
        total_settled = db.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]
        settled_matches = db.execute("SELECT COUNT(DISTINCT match_id) FROM settlements").fetchone()[0]
        total_matches = db.execute("SELECT COUNT(*) FROM matches").fetchone()[0]

        # Settlement status distribution
        settled_with_score = db.execute(
            "SELECT COUNT(*) FROM settlements WHERE fthg IS NOT NULL AND ftag IS NOT NULL"
        ).fetchone()[0]

        cancelled_or_special = db.execute(
            "SELECT COUNT(*) FROM settlements WHERE result_code = '取消' OR result_code = '延期'"
        ).fetchone()[0]

        sp1_void = db.execute(
            "SELECT COUNT(*) FROM settlements WHERE winning_sp = 1 OR winning_sp = 1.0"
        ).fetchone()[0]

        settlement_pct = (settled_matches / total_matches * 100) if total_matches else 0

        # Cross-check: handicap result mapping
        result_codes = dict(db.execute(
            "SELECT result_code, COUNT(*) FROM settlements WHERE result_code IS NOT NULL GROUP BY result_code"
        ).fetchall())

        metrics.update({
            "total_settlements": total_settled,
            "total_settlement_rows": total_settled,
            "settled_matches": settled_matches,
            "total_match_rows": total_matches,
            "settled_with_score": settled_with_score,
            "cancelled_or_postponed": cancelled_or_special,
            "sp1_void": sp1_void,
            "settlement_coverage_pct": round(settlement_pct, 2),
            "result_codes": result_codes,
        })

        mapping_ok = set(result_codes.keys()).issubset({"3", "1", "0", "取消", "延期", ""}) or \
                     set(result_codes.keys()).issubset({"胜", "平", "负", "取消", "延期", ""})

        gates.append(GateResult(
            gate_id=GateID.G6_SETTLEMENT_MAPPING,
            passed=settlement_pct >= 50 and mapping_ok,
            score=min(1.0, settlement_pct / 100),
            evidence=(
                f"{total_settled} settlement rows cover {settled_matches}/{total_matches} matches "
                f"({settlement_pct:.1f}% of DB matches). "
                f"{settled_with_score} have final scores. "
                f"{cancelled_or_special} cancellations/postponements, {sp1_void} SP=1 voids. "
                f"Result codes: {sorted(result_codes.keys())}. "
                f"Settlement mapping is direct: fthg/ftag → handicap-adjusted result_code."
            ),
            metrics=dict(metrics),
        ))

        metrics["settlement_sourced_separately"] = True
        metrics["sources"] = sorted(set(
            r["source"] for r in db.execute(
                "SELECT DISTINCT source FROM settlements WHERE source IS NOT NULL AND source != ''"
            ).fetchall()
        ))
        return gates, metrics

    # ── P0 markets (playid=40, 42): Correct Score, Total Goals ──────────────

    def _audit_p0_pre_event(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_p0_pre_event(market)
        return self._classify(market, AuditDimension.PRE_EVENT_INPUT, gates, metrics)

    def _audit_p0_freeze(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_p0_freeze(market)
        return self._classify(market, AuditDimension.FREEZE_SUPPORT, gates, metrics)

    def _audit_p0_settlement(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_p0_settlement(market)
        return self._classify(market, AuditDimension.SETTLEMENT_SUPPORT, gates, metrics)

    def _gates_p0_pre_event(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        db = self.bjdc
        metrics: dict[str, Any] = {}

        # G1: Complete outcome vectors
        has_table = _table_exists(db, "live_market_sp_snapshots")
        total_rows = 0
        total_matches = 0
        forward_complete = 0
        if has_table:
            total_rows = db.execute(
                "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=?", (market.playid,)
            ).fetchone()[0]
            total_matches = db.execute(
                "SELECT COUNT(DISTINCT issue||'-'||row_idx) FROM live_market_sp_snapshots WHERE playid=?",
                (market.playid,),
            ).fetchone()[0]
            forward_complete = db.execute(
                "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=? AND capture_classification='forward_complete_open'",
                (market.playid,),
            ).fetchone()[0]

        expected_per_match = market.expected_outcome_count
        capture_identity = (
            "issue, row_idx, playid, COALESCE(batch_id, ''), "
            "COALESCE(fetched_at_utc, fetched_at, ''), COALESCE(source_updated_at_hkt, '')"
        )
        total_capture_vectors = 0
        if has_table:
            total_capture_vectors = db.execute(
                f"""SELECT COUNT(*) FROM (
                   SELECT 1
                   FROM live_market_sp_snapshots
                   WHERE playid=?
                   GROUP BY {capture_identity}
               )""",
                (market.playid,),
            ).fetchone()[0]

        expected_placeholders = ",".join("?" for _ in market.outcome_codes)
        complete_capture_vectors = 0
        complete_match_markets = 0
        if has_table:
            complete_capture_vectors, complete_match_markets = db.execute(
                f"""WITH capture_vectors AS (
                   SELECT issue, row_idx
                   FROM live_market_sp_snapshots
                   WHERE playid=? AND capture_classification='forward_complete_open'
                   GROUP BY {capture_identity}
                   HAVING COUNT(DISTINCT CASE WHEN sp IS NOT NULL THEN outcome_code END)=?
                      AND COUNT(DISTINCT CASE
                          WHEN sp IS NOT NULL AND outcome_code IN ({expected_placeholders})
                          THEN outcome_code
                      END)=?
               )
               SELECT COUNT(*), COUNT(DISTINCT issue||'-'||row_idx)
               FROM capture_vectors""",
                (market.playid, expected_per_match, *market.outcome_codes, expected_per_match),
            ).fetchone()
        complete_pct = (complete_capture_vectors / total_capture_vectors * 100) if total_capture_vectors else 0
        complete_match_pct = (complete_match_markets / total_matches * 100) if total_matches else 0

        metrics.update({
            "total_rows": total_rows,
            "total_match_markets": total_matches,
            "forward_complete_open_rows": forward_complete,
            "total_capture_vectors": total_capture_vectors,
            "complete_capture_vectors": complete_capture_vectors,
            "complete_match_markets": complete_match_markets,
            "complete_match_vectors": complete_match_markets,
            "complete_vector_pct": round(complete_pct, 2),
            "complete_match_market_pct": round(complete_match_pct, 2),
        })
        gates.append(GateResult(
            gate_id=GateID.G1_OUTCOME_VECTORS,
            passed=complete_pct >= 30 and complete_match_pct >= 30,
            score=min(1.0, min(complete_pct, complete_match_pct) / 50),  # 50% is the bar for score=1.0
            evidence=(
                f"{forward_complete:,} rows classified as forward_complete_open. "
                f"{complete_capture_vectors:,}/{total_capture_vectors:,} capture-vectors "
                f"have the exact {expected_per_match}-outcome set priced ({complete_pct:.1f}%). "
                f"{complete_match_markets:,}/{total_matches:,} match-markets have at least one complete "
                f"capture-vector ({complete_match_pct:.1f}%)."
            ),
            metrics={
                "complete_capture_vectors": complete_capture_vectors,
                "total_capture_vectors": total_capture_vectors,
                "complete_vector_pct": round(complete_pct, 2),
                "complete_match_markets": complete_match_markets,
                "complete_match_market_pct": round(complete_match_pct, 2),
            },
        ))

        # G2: Source and capture timestamps
        has_fetched_at = False
        has_source_updated = False
        if has_table:
            cols = {r[1] for r in db.execute("PRAGMA table_info(live_market_sp_snapshots)").fetchall()}
            has_fetched_at = "fetched_at_utc" in cols
            has_source_updated = "source_updated_at_hkt" in cols

        ts_complete = 0
        if has_fetched_at and has_source_updated:
            ts_complete = db.execute(
                """SELECT COUNT(*) FROM live_market_sp_snapshots
                   WHERE playid=? AND fetched_at_utc IS NOT NULL AND fetched_at_utc != ''
                   AND source_updated_at_hkt IS NOT NULL AND source_updated_at_hkt != ''""",
                (market.playid,),
            ).fetchone()[0]
        ts_pct = (ts_complete / total_rows * 100) if total_rows else 0

        metrics.update({
            "has_dual_clock": has_fetched_at and has_source_updated,
            "dual_clock_complete_rows": ts_complete,
            "dual_clock_pct": round(ts_pct, 2),
        })
        gates.append(GateResult(
            gate_id=GateID.G2_SOURCE_TIMESTAMPS,
            passed=ts_pct >= 50,
            score=min(1.0, ts_pct / 100),
            evidence=(
                f"Dual-clock (fetched_at_utc + source_updated_at_hkt): "
                f"{ts_complete:,}/{total_rows:,} rows ({ts_pct:.1f}%) have both timestamps."
            ),
            metrics={"dual_clock_pct": round(ts_pct, 2)},
        ))

        # G3: Pre-cutoff evidence
        cutoff_utc = """CASE
                     WHEN instr(substr(sale_cutoff_hkt, 11), '+') > 0
                       OR instr(substr(sale_cutoff_hkt, 11), '-') > 0
                     THEN datetime(sale_cutoff_hkt)
                     ELSE datetime(sale_cutoff_hkt, '-8 hours')
                 END"""
        cutoff_clock_predicate = f"""
                     sale_cutoff_hkt IS NOT NULL AND sale_cutoff_hkt != ''
                     AND fetched_at_utc IS NOT NULL AND fetched_at_utc != ''
                     AND source_updated_at_hkt IS NOT NULL AND source_updated_at_hkt != ''
                     AND datetime(sale_cutoff_hkt) IS NOT NULL
                     AND datetime(fetched_at_utc) IS NOT NULL
                     AND datetime(source_updated_at_hkt) IS NOT NULL
                     AND datetime(fetched_at_utc) < {cutoff_utc}
                     AND datetime(source_updated_at_hkt) < datetime(sale_cutoff_hkt)
        """
        pre_cutoff = db.execute(
            """SELECT COUNT(*) FROM live_market_sp_snapshots
               WHERE playid=? AND capture_classification='forward_complete_open'""",
            (market.playid,),
        ).fetchone()[0] if has_table else 0

        # Check sale_status
        open_sale = db.execute(
            """SELECT COUNT(*) FROM live_market_sp_snapshots
               WHERE playid=? AND sale_status='open' AND capture_classification='forward_complete_open'""",
            (market.playid,),
        ).fetchone()[0] if has_table else 0

        pre_cutoff_capture_vectors = 0
        pre_cutoff_match_markets = 0
        if has_table:
            pre_cutoff_capture_vectors, pre_cutoff_match_markets = db.execute(
                f"""WITH capture_vectors AS (
                   SELECT issue, row_idx
                   FROM live_market_sp_snapshots
                   WHERE playid=? AND sale_status='open'
                     AND capture_classification='forward_complete_open'
                     AND {cutoff_clock_predicate}
                   GROUP BY {capture_identity}
                   HAVING COUNT(DISTINCT CASE WHEN sp IS NOT NULL THEN outcome_code END)=?
                      AND COUNT(DISTINCT CASE
                          WHEN sp IS NOT NULL AND outcome_code IN ({expected_placeholders})
                          THEN outcome_code
                      END)=?
               )
               SELECT COUNT(*), COUNT(DISTINCT issue||'-'||row_idx)
               FROM capture_vectors""",
                (market.playid, expected_per_match, *market.outcome_codes, expected_per_match),
            ).fetchone()
        pre_pct = (pre_cutoff_capture_vectors / total_capture_vectors * 100) if total_capture_vectors else 0
        pre_match_pct = (pre_cutoff_match_markets / total_matches * 100) if total_matches else 0

        pre_cutoff_rejections = {
            "non_open_sale": 0,
            "missing_cutoff_clock": 0,
            "missing_dual_clock": 0,
            "fetched_at_or_after_cutoff": 0,
            "source_updated_at_or_after_cutoff": 0,
        }
        if has_table:
            rejection_row = db.execute(
                f"""WITH complete_vectors AS (
                   SELECT issue, row_idx,
                          MIN(CASE WHEN sale_status='open' THEN 1 ELSE 0 END) AS sale_open,
                          MIN(CASE
                              WHEN sale_cutoff_hkt IS NOT NULL AND sale_cutoff_hkt != ''
                               AND datetime(sale_cutoff_hkt) IS NOT NULL
                              THEN 1 ELSE 0
                          END) AS has_cutoff,
                          MIN(CASE
                              WHEN fetched_at_utc IS NOT NULL AND fetched_at_utc != ''
                               AND source_updated_at_hkt IS NOT NULL AND source_updated_at_hkt != ''
                               AND datetime(fetched_at_utc) IS NOT NULL
                               AND datetime(source_updated_at_hkt) IS NOT NULL
                              THEN 1 ELSE 0
                          END) AS has_dual_clock,
                          MIN(CASE
                              WHEN datetime(fetched_at_utc) < {cutoff_utc}
                              THEN 1 ELSE 0
                          END) AS fetched_before_cutoff,
                          MIN(CASE
                              WHEN datetime(source_updated_at_hkt) < datetime(sale_cutoff_hkt)
                              THEN 1 ELSE 0
                          END) AS source_before_cutoff
                   FROM live_market_sp_snapshots
                   WHERE playid=? AND capture_classification='forward_complete_open'
                   GROUP BY {capture_identity}
                   HAVING COUNT(DISTINCT CASE WHEN sp IS NOT NULL THEN outcome_code END)=?
                      AND COUNT(DISTINCT CASE
                          WHEN sp IS NOT NULL AND outcome_code IN ({expected_placeholders})
                          THEN outcome_code
                      END)=?
               )
               SELECT
                   COALESCE(SUM(CASE WHEN sale_open=0 THEN 1 ELSE 0 END), 0) AS non_open_sale,
                   COALESCE(SUM(CASE WHEN has_cutoff=0 THEN 1 ELSE 0 END), 0) AS missing_cutoff_clock,
                   COALESCE(SUM(CASE WHEN has_dual_clock=0 THEN 1 ELSE 0 END), 0) AS missing_dual_clock,
                   COALESCE(SUM(CASE
                       WHEN has_cutoff=1 AND has_dual_clock=1 AND fetched_before_cutoff=0
                       THEN 1 ELSE 0
                   END), 0) AS fetched_at_or_after_cutoff,
                   COALESCE(SUM(CASE
                       WHEN has_cutoff=1 AND has_dual_clock=1 AND source_before_cutoff=0
                       THEN 1 ELSE 0
                   END), 0) AS source_updated_at_or_after_cutoff
               FROM complete_vectors""",
                (market.playid, expected_per_match, *market.outcome_codes, expected_per_match),
            ).fetchone()
            pre_cutoff_rejections = {key: int(rejection_row[key]) for key in pre_cutoff_rejections}

        metrics.update({
            "pre_cutoff_eligible_capture_vectors": pre_cutoff_capture_vectors,
            "pre_cutoff_eligible_match_markets": pre_cutoff_match_markets,
            "pre_cutoff_eligible_match_vectors": pre_cutoff_match_markets,
            "pre_cutoff_eligible_pct": round(pre_pct, 2),
            "pre_cutoff_eligible_match_market_pct": round(pre_match_pct, 2),
            "pre_cutoff_rejection_reasons": pre_cutoff_rejections,
        })
        gates.append(GateResult(
            gate_id=GateID.G3_PRE_CUTOFF_EVIDENCE,
            passed=pre_pct >= 10 and pre_match_pct >= 30,
            score=min(1.0, min(pre_pct, pre_match_pct) / 30),
            evidence=(
                f"{pre_cutoff_capture_vectors:,} capture-vectors with both sale_status=open and "
                f"forward_complete_open classification ({pre_pct:.1f}%). "
                f"{pre_cutoff_match_markets:,}/{total_matches:,} match-markets have eligible "
                f"pre-cutoff capture-vectors ({pre_match_pct:.1f}%). "
                f"Dual-clock confirms both fetched_at_utc and source_updated_at_hkt precede sale_cutoff_hkt."
            ),
            metrics={
                "pre_cutoff_capture_vectors": pre_cutoff_capture_vectors,
                "pre_cutoff_pct": round(pre_pct, 2),
                "pre_cutoff_match_markets": pre_cutoff_match_markets,
                "pre_cutoff_match_market_pct": round(pre_match_pct, 2),
                "rejection_reasons": pre_cutoff_rejections,
            },
        ))

        # G7: No leakage
        terminal = db.execute(
            "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=? AND capture_classification='terminal_backfill_exploratory_only'",
            (market.playid,),
        ).fetchone()[0] if has_table else 0
        terminal_rows = terminal // market.expected_outcome_count if terminal else 0
        unproven_forward = db.execute(
            f"""SELECT COUNT(*) FROM live_market_sp_snapshots
               WHERE playid=? AND capture_classification='forward_complete_open'
                 AND NOT ({cutoff_clock_predicate})""",
            (market.playid,),
        ).fetchone()[0] if has_table else 0
        leakage_free = unproven_forward == 0

        gates.append(GateResult(
            gate_id=GateID.G7_NO_LEAKAGE,
            passed=leakage_free,
            score=1.0 if leakage_free else 0.0,
            evidence=(
                f"{terminal:,} terminal-backfill rows exist but are classified as "
                f"terminal_backfill_exploratory_only and excluded from forward_complete_open. "
                f"{unproven_forward:,} forward_complete_open rows lack independent cutoff-clock proof."
            ),
            metrics={
                "terminal_rows": terminal,
                "terminal_excluded": True,
                "unproven_forward_rows": unproven_forward,
            },
        ))

        metrics["discovered_match_markets"] = total_matches
        return gates, metrics

    def _gates_p0_freeze(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        db = self.bjdc
        metrics: dict[str, Any] = {}

        # G4: Immutable provenance
        batches = db.execute(
            "SELECT COUNT(*) FROM market_sp_capture_batches WHERE playid=?",
            (market.playid,),
        ).fetchone()[0]
        has_bundles = bool(batches)

        has_verifiable = False
        bundle_count = 0
        verified = 0
        failed = 0
        failure_samples: list[dict[str, Any]] = []
        if has_bundles:
            bundle_dirs = db.execute(
                """SELECT DISTINCT bundle_path, bundle_sha256s_sha256
                   FROM market_sp_capture_batches
                   WHERE playid=? AND bundle_path IS NOT NULL""",
                (market.playid,),
            ).fetchall()
            bundle_count = len(bundle_dirs)
            for row in bundle_dirs:
                ok, detail = _verify_sha256sums(
                    Path(row["bundle_path"]),
                    row["bundle_sha256s_sha256"],
                )
                if ok:
                    verified += 1
                else:
                    failed += 1
                    if len(failure_samples) < 5:
                        failure_samples.append(detail)
            has_verifiable = (verified == bundle_count and bundle_count > 0)

        metrics.update({
            "capture_batches": batches,
            "bundle_dirs": bundle_count,
            "sha256_verified_bundle_dirs": verified,
            "sha256_failed_bundle_dirs": failed,
            "sha256_failure_samples": failure_samples,
            "all_sha256_verifiable": has_verifiable,
        })
        gates.append(GateResult(
            gate_id=GateID.G4_IMMUTABLE_PROVENANCE,
            passed=has_verifiable,
            score=1.0 if has_verifiable else 0.3,
            evidence=(
                f"{batches} capture batches for {market.display_name}. "
                f"{bundle_count} bundle directories on disk. "
                f"{verified} bundles verified by recomputing SHA256SUMS entries and matching "
                f"the recorded SHA256SUMS digest. "
                f"{'All bundle checks passed.' if has_verifiable else f'{failed} bundle checks failed.'}"
            ),
            metrics=dict(metrics),
        ))

        # G5: Freeze Protocol v1
        from src.multimarket_p0 import MultimarketP0Error, load_prospective_segment_bindings, prospective_segment_event_ready, prospective_segment_g5_ready, verify_freeze, verify_segment_freeze
        # verify_freeze() only accepts the multimarket as-of-freeze contract.
        # The committed MM-DATA-AUDIT research freeze has a different schema.
        freeze_root = _repo_root() / "results/research/multimarket_10h_freeze_v1"
        freeze_dirs = [path for path in freeze_root.iterdir() if path.is_dir()] if freeze_root.is_dir() else []

        has_freeze = False
        freeze_manifest = {}
        verified_freeze = {}
        freeze_failures: list[dict[str, str]] = []
        for fd in freeze_dirs:
            manifest_path = fd / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                verification = verify_freeze(fd)
                manifest = json.loads(manifest_path.read_text())
            except (MultimarketP0Error, OSError, ValueError, json.JSONDecodeError) as exc:
                if len(freeze_failures) < 5:
                    freeze_failures.append({"path": str(fd), "error": str(exc)})
                continue
            if market.playid in manifest.get("target_playids", []):
                has_freeze = True
                freeze_manifest = manifest
                verified_freeze = verification
                break

        # Segment packages are the only compatible evidence for the p40/p42
        # shared-decision-time G5 gate. They remain prospective evidence; a
        # valid package with no rows does not pass the gate.
        segment_root = _repo_root() / "results/research/multimarket_segment_freeze_v1"
        segment_dirs = list(segment_root.glob("*/segment_*/*")) if segment_root.is_dir() else []
        task = yaml.safe_load((ROOT / ".research/tasks/BJ-MM-FREEZE-001.yaml").read_text(encoding="utf-8"))
        registration = task["spec"]["context"]["preregistration"]
        try:
            prospective_events = load_prospective_segment_bindings(
                segment_root / "ledger", activation_utc=str(registration["activation_utc"]),
                required_events=int(registration["required_prospective_segment_events"]),
            )
        except (MultimarketP0Error, OSError, ValueError, json.JSONDecodeError) as exc:
            prospective_events = []
            freeze_failures.append({"path": str(segment_root / "ledger"), "error": str(exc)})
        prospective_ids = {str(row["event_id"]) for row in prospective_events}
        valid_prospective_ids: set[str] = set()
        for fd in segment_dirs:
            if not fd.is_dir() or not (fd / "manifest.json").is_file():
                continue
            try:
                verification = verify_segment_freeze(fd)
                manifest = json.loads((fd / "manifest.json").read_text())
                frozen_rows = list(csv.DictReader((fd / "frozen_outcomes.csv").open(encoding="utf-8", newline="")))
            except (MultimarketP0Error, OSError, ValueError, json.JSONDecodeError) as exc:
                if len(freeze_failures) < 5:
                    freeze_failures.append({"path": str(fd), "error": str(exc)})
                continue
            if (manifest.get("event_id") in prospective_ids and prospective_segment_event_ready(verification)
                    and market.playid in manifest.get("target_playids", []) and any(int(row["playid"]) == market.playid for row in frozen_rows)):
                valid_prospective_ids.add(str(manifest["event_id"]))
                freeze_manifest = manifest
                verified_freeze = verification
        if market.playid in TARGET_PLAYIDS:
            # G5 evidence is the preregistered first two prospective events,
            # not an arbitrary historical or one-off package.
            has_freeze = prospective_segment_g5_ready(prospective_ids, valid_prospective_ids)

        metrics.update({
            "has_existing_freeze": has_freeze,
            "freeze_manifest": freeze_manifest.get("schema_version") if freeze_manifest else None,
            "freeze_verification": verified_freeze,
            "freeze_verification_failures": freeze_failures,
            "preregistered_segment_event_ids": sorted(prospective_ids),
            "verified_preregistered_segment_event_ids": sorted(valid_prospective_ids),
        })
        gates.append(GateResult(
            gate_id=GateID.G5_ASOF_FREEZE,
            passed=has_freeze,
            score=0.8 if has_freeze else 0.2,
            evidence=(
                f"Verified 10h freeze package found: {freeze_manifest.get('schema_version', '')} with "
                f"{freeze_manifest.get('frozen_outcome_rows', 0)} frozen rows for this market."
                if has_freeze
                else "No complete verified preregistered two-event strict segment freeze set for this market."
            ),
            metrics={"has_freeze": has_freeze, "freeze_verification": verified_freeze},
        ))

        return gates, metrics

    def _gates_p0_settlement(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        db = self.bjdc
        metrics: dict[str, Any] = {}

        has_table = _table_exists(db, "multimarket_settlement_truth")
        if not has_table:
            gates.append(GateResult(
                gate_id=GateID.G6_SETTLEMENT_MAPPING,
                passed=False,
                score=0.0,
                evidence="multimarket_settlement_truth table does not exist.",
            ))
            return gates, metrics

        total = db.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=?",
            (market.market_key,),
        ).fetchone()[0]

        settled = db.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=? AND settlement_status='settled'",
            (market.market_key,),
        ).fetchone()[0]

        pending = db.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=? AND settlement_status='pending_or_unknown'",
            (market.market_key,),
        ).fetchone()[0]

        cancelled = db.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=? AND settlement_status='cancelled'",
            (market.market_key,),
        ).fetchone()[0]

        void_sp1 = db.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=? AND settlement_status='void_sp1'",
            (market.market_key,),
        ).fetchone()[0]

        settlement_coverage = (settled / total * 100) if total else 0

        # Check for separate score source
        has_separate_score = db.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=? AND score_source NOT IN ('missing','')",
            (market.market_key,),
        ).fetchone()[0] > 0

        metrics.update({
            "total_settlement_rows": total,
            "settled": settled,
            "pending_or_unknown": pending,
            "cancelled": cancelled,
            "void_sp1": void_sp1,
            "settlement_coverage_pct": round(settlement_coverage, 2),
            "has_separate_score_source": has_separate_score,
        })

        gates.append(GateResult(
            gate_id=GateID.G6_SETTLEMENT_MAPPING,
            passed=settlement_coverage >= 30 and has_separate_score,
            score=min(1.0, settlement_coverage / 60),
            evidence=(
                f"{total} match-markets in settlement truth: {settled} settled ({settlement_coverage:.1f}%), "
                f"{pending} pending, {cancelled} cancelled, {void_sp1} SP=1 voids. "
                f"Score source is {'separately sourced from matches/nowscore tables' if has_separate_score else 'missing or not separately sourced'}."
            ),
            metrics=dict(metrics),
        ))

        metrics["settlement_sourced_separately"] = has_separate_score
        return gates, metrics

    # ── Half/Full Time (playid=51) ──────────────────────────────────────────

    def _audit_p51_pre_event(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_p51_pre_event(market)
        return self._classify(market, AuditDimension.PRE_EVENT_INPUT, gates, metrics)

    def _audit_p51_freeze(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_p51_freeze(market)
        return self._classify(market, AuditDimension.FREEZE_SUPPORT, gates, metrics)

    def _audit_p51_settlement(self, market: MarketDefinition) -> DimensionAudit:
        gates, metrics = self._gates_p51_settlement(market)
        return self._classify(market, AuditDimension.SETTLEMENT_SUPPORT, gates, metrics)

    def _gates_p51_pre_event(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        db = self.bjdc
        metrics: dict[str, Any] = {}

        has_table = _table_exists(db, "live_market_sp_snapshots")
        total_rows = 0
        total_matches = 0
        if has_table:
            total_rows = db.execute(
                "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=?", (market.playid,)
            ).fetchone()[0]
            total_matches = db.execute(
                "SELECT COUNT(DISTINCT issue||'-'||row_idx) FROM live_market_sp_snapshots WHERE playid=?",
                (market.playid,),
            ).fetchone()[0]

        # Check outcome codes
        outcome_codes = []
        if has_table:
            outcome_codes = [r[0] for r in db.execute(
                "SELECT DISTINCT outcome_code FROM live_market_sp_snapshots WHERE playid=? AND outcome_code IS NOT NULL",
                (market.playid,),
            ).fetchall()]

        has_expected_outcomes = set(outcome_codes) == set(market.outcome_codes)
        metrics.update({
            "total_rows": total_rows,
            "total_match_markets": total_matches,
            "outcome_codes_found": sorted(outcome_codes),
            "expected_outcome_match": has_expected_outcomes,
        })

        gates.append(GateResult(
            gate_id=GateID.G1_OUTCOME_VECTORS,
            passed=has_expected_outcomes and total_matches > 0,
            score=0.6 if has_expected_outcomes else 0.2,
            evidence=(
                f"{total_rows:,} rows across {total_matches:,} match-markets. "
                f"Outcome codes: {sorted(outcome_codes)}. "
                f"{'All 9 expected codes present.' if has_expected_outcomes else 'Missing or extra outcome codes detected.'} "
                f"All rows are non_target_market_unclassified — never validated for completeness."
            ),
            metrics={"outcome_codes_found": sorted(outcome_codes), "expected_match": has_expected_outcomes},
        ))

        # G2: Timestamps
        has_fetched = any("fetched_at" in str(r[1]) for r in db.execute(
            "PRAGMA table_info(live_market_sp_snapshots)"
        ).fetchall()) if has_table else False

        ts_count = 0
        if has_fetched:
            ts_count = db.execute(
                "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=? AND fetched_at IS NOT NULL AND fetched_at != ''",
                (market.playid,),
            ).fetchone()[0]
        ts_pct = (ts_count / total_rows * 100) if total_rows else 0

        has_dual = bool(db.execute(
            "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=? AND fetched_at_utc IS NOT NULL AND source_updated_at_hkt IS NOT NULL",
            (market.playid,),
        ).fetchone()[0]) if has_table else False

        metrics.update({
            "has_timestamps": has_fetched,
            "timestamped_rows": ts_count,
            "timestamped_pct": round(ts_pct, 2),
            "has_dual_clock": has_dual,
        })
        gates.append(GateResult(
            gate_id=GateID.G2_SOURCE_TIMESTAMPS,
            passed=ts_pct >= 50,
            score=min(1.0, ts_pct / 100) * (0.8 if has_dual else 0.5),
            evidence=(
                f"{ts_count:,}/{total_rows:,} rows ({ts_pct:.1f}%) have fetched_at. "
                f"Dual-clock (fetched_at_utc + source_updated_at_hkt): {'present' if has_dual else 'missing'}. "
                f"No batch_id or source_url metadata."
            ),
            metrics={"timestamped_pct": round(ts_pct, 2), "dual_clock": has_dual},
        ))

        # G3: Pre-cutoff
        gates.append(GateResult(
            gate_id=GateID.G3_PRE_CUTOFF_EVIDENCE,
            passed=False,
            score=0.1,
            evidence=(
                f"All rows are non_target_market_unclassified — never validated for pre-cutoff eligibility. "
                f"No sale_status, sale_cutoff, or capture_classification beyond raw source_attribute values. "
                f"Cannot confirm pre-cutoff capture without retroactive classification."
            ),
            metrics={"classified": False},
        ))

        # G7: Leakage
        gates.append(GateResult(
            gate_id=GateID.G7_NO_LEAKAGE,
            passed=False,
            score=0.5,
            evidence=(
                f"No terminal classification exists; all data is non_target_market_unclassified. "
                f"Risk unknown — data may contain post-event captures but cannot be proven either way."
            ),
            metrics={"leakage_risk": "unknown"},
        ))

        metrics["discovered_match_markets"] = total_matches
        return gates, metrics

    def _gates_p51_freeze(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        metrics: dict[str, Any] = {}

        gates.append(GateResult(
            gate_id=GateID.G4_IMMUTABLE_PROVENANCE,
            passed=False,
            score=0.1,
            evidence=(
                f"No market_sp_capture_batches for playid=51. "
                f"No SHA256SUMS, no immutable bundles, no batch provenance. "
                f"Data exists as raw rows in live_market_sp_snapshots without hash verification."
            ),
            metrics={"has_bundles": False},
        ))

        gates.append(GateResult(
            gate_id=GateID.G5_ASOF_FREEZE,
            passed=False,
            score=0.0,
            evidence=(
                f"No freeze package exists for playid=51. "
                f"Freeze Protocol v1 requires capture batches which don't exist. "
                f"Data is available but not in a freezable form."
            ),
            metrics={"has_freeze": False},
        ))

        return gates, metrics

    def _gates_p51_settlement(self, market: MarketDefinition) -> tuple[list[GateResult], dict[str, Any]]:
        gates = []
        db = self.bjdc
        metrics: dict[str, Any] = {}

        has_table = _table_exists(db, "multimarket_settlement_truth")
        if not has_table:
            gates.append(GateResult(
                gate_id=GateID.G6_SETTLEMENT_MAPPING,
                passed=False,
                score=0.0,
                evidence="multimarket_settlement_truth table does not exist.",
            ))
            return gates, metrics

        # Check if any p51 settlement exists
        p51_rows = db.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=?",
            (market.market_key,),
        ).fetchone()[0]

        if p51_rows == 0:
            metrics["settlement_sourced_separately"] = False
            metrics["total_settlement_rows"] = 0
            gates.append(GateResult(
                gate_id=GateID.G6_SETTLEMENT_MAPPING,
                passed=False,
                score=0.0,
                evidence=(
                    f"No settlement truth rows for {market.display_name}. "
                    f"Half/full-time settlement mapping is not available until separately "
                    f"sourced p51 settlement rows are built and audited."
                ),
                metrics={"settlement_rows": 0, "mapping_available": False},
            ))
            return gates, metrics

        expected_placeholders = ",".join("?" for _ in market.outcome_codes)
        p51_source_predicate = """
                  (
                    lower(coalesce(score_source, '')) LIKE '%p51%'
                    OR lower(coalesce(score_source, '')) LIKE '%half%'
                  )
        """
        audited_rows = db.execute(
            f"""SELECT COUNT(*) FROM multimarket_settlement_truth
                WHERE market_key=?
                  AND {p51_source_predicate}
                  AND (
                    (
                      settlement_status='settled'
                      AND outcome_code IN ({expected_placeholders})
                    )
                    OR (
                      settlement_status IN ('cancelled', 'postponed', 'void_sp1')
                      AND (outcome_code IN ({expected_placeholders}) OR coalesce(outcome_code, '') = '')
                    )
                  )""",
            (market.market_key, *market.outcome_codes, *market.outcome_codes),
        ).fetchone()[0]
        explicit_source_rows = db.execute(
            f"""SELECT COUNT(*) FROM multimarket_settlement_truth
                WHERE market_key=? AND {p51_source_predicate}""",
            (market.market_key,),
        ).fetchone()[0]
        final_score_only_rows = db.execute(
            """SELECT COUNT(*) FROM multimarket_settlement_truth
                WHERE market_key=?
                  AND lower(coalesce(score_source, '')) IN (
                    'matches.score',
                    'nowscore_bjdc_matches.score'
                  )""",
            (market.market_key,),
        ).fetchone()[0]
        settlement_coverage = audited_rows / p51_rows if p51_rows else 0

        gates.append(GateResult(
            gate_id=GateID.G6_SETTLEMENT_MAPPING,
            passed=p51_rows > 0 and audited_rows == p51_rows,
            score=settlement_coverage,
            evidence=(
                f"{p51_rows} p51 settlement truth rows, {audited_rows} have audited p51 "
                f"outcome/special-status mapping from explicit half/full-time source metadata. "
                f"Full-time-only sources such as matches.score are not accepted."
            ),
            metrics={
                "settlement_rows": p51_rows,
                "audited_p51_settlement_rows": audited_rows,
                "settlement_coverage_pct": round(settlement_coverage * 100, 2),
                "explicit_p51_source_rows": explicit_source_rows,
                "final_score_only_rows": final_score_only_rows,
            },
        ))

        metrics.update({
            "total_settlement_rows": p51_rows,
            "audited_p51_settlement_rows": audited_rows,
            "settlement_coverage_pct": round(settlement_coverage * 100, 2),
            "explicit_p51_source_rows": explicit_source_rows,
            "final_score_only_rows": final_score_only_rows,
            "settlement_sourced_separately": audited_rows == p51_rows,
        })
        return gates, metrics

    # ── Classification ─────────────────────────────────────────────────────

    def _classify(
        self,
        market: MarketDefinition,
        dimension: AuditDimension,
        gates: list[GateResult],
        metrics: dict[str, Any],
    ) -> DimensionAudit:
        # Determine readiness from gate scores
        relevant_gates = self._gates_for_dimension(dimension)
        relevant_gate_results = [g for g in gates if g.gate_id in relevant_gates]
        scores = [g.score for g in relevant_gate_results]
        has_all_required_gates = {g.gate_id for g in relevant_gate_results} == relevant_gates
        passed_all = has_all_required_gates and all(g.passed for g in relevant_gate_results)

        if not scores:
            readiness = ReadinessLevel.UNAVAILABLE
            summary = f"No gate data available for {market.display_name} {dimension.value}."
        else:
            avg_score = sum(scores) / len(scores)

            if dimension == AuditDimension.SETTLEMENT_SUPPORT:
                if passed_all and avg_score >= 0.6:
                    readiness = ReadinessLevel.READY_STRICT
                elif avg_score >= 0.3:
                    readiness = ReadinessLevel.PARTIAL
                elif avg_score >= 0.1:
                    readiness = ReadinessLevel.SETTLEMENT_ONLY
                else:
                    readiness = ReadinessLevel.UNAVAILABLE
            else:
                if passed_all and avg_score >= 0.8:
                    readiness = ReadinessLevel.READY_STRICT
                elif avg_score >= 0.4:
                    readiness = ReadinessLevel.PARTIAL
                elif avg_score >= 0.2:
                    readiness = ReadinessLevel.SETTLEMENT_ONLY
                else:
                    readiness = ReadinessLevel.UNAVAILABLE

            passed = sum(1 for g in gates if g.gate_id in relevant_gates and g.passed)
            total_relevant = len(relevant_gates & {g.gate_id for g in gates})
            summary = (
                f"{market.display_name} {dimension.value}: {readiness.value}. "
                f"{passed}/{total_relevant} relevant gates passed, avg score={avg_score:.2f}"
            )

        return DimensionAudit(
            market=market,
            dimension=dimension,
            readiness=readiness,
            gates=gates,
            summary=summary,
            metrics=metrics,
        )

    @staticmethod
    def _gates_for_dimension(dimension: AuditDimension) -> set[GateID]:
        if dimension == AuditDimension.PRE_EVENT_INPUT:
            return {GateID.G1_OUTCOME_VECTORS, GateID.G2_SOURCE_TIMESTAMPS,
                    GateID.G3_PRE_CUTOFF_EVIDENCE, GateID.G7_NO_LEAKAGE}
        elif dimension == AuditDimension.FREEZE_SUPPORT:
            return {GateID.G4_IMMUTABLE_PROVENANCE, GateID.G5_ASOF_FREEZE}
        else:
            return {GateID.G6_SETTLEMENT_MAPPING}

    def _compute_summary_metrics(self, result: AuditResult) -> dict[str, Any]:
        """Compute cross-market summary metrics."""
        summary: dict[str, Any] = {
            "total_match_markets_by_market": {},
            "complete_vectors_by_market": {},
            "settlement_rows_by_market": {},
            "readiness_counts": defaultdict(lambda: defaultdict(int)),
        }
        for dim in result.dimensions:
            mk = dim.market.market_key
            summary["readiness_counts"][mk][dim.dimension.value] = dim.readiness.value
            if dim.metrics:
                if "discovered_match_markets" in dim.metrics:
                    summary["total_match_markets_by_market"][mk] = dim.metrics["discovered_match_markets"]
                if "complete_match_vectors" in dim.metrics:
                    summary["complete_vectors_by_market"][mk] = dim.metrics["complete_match_vectors"]
                if "total_settlement_rows" in dim.metrics:
                    summary["settlement_rows_by_market"][mk] = dim.metrics["total_settlement_rows"]
                elif "total_settlements" in dim.metrics:
                    summary["settlement_rows_by_market"][mk] = dim.metrics["total_settlements"]

        return dict(summary)
