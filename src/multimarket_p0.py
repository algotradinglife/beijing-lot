"""P0 audit, 10h freeze, and settlement truth for BJDC target markets."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
HKT = timezone(timedelta(hours=8))
TARGET_PLAYIDS = (40, 42)
MARKET_KEY = {40: "total_goals", 42: "correct_score"}
EXPECTED_OUTCOMES = {40: 8, 42: 25}
DEFAULT_CAPTURE_ROOT = ROOT / "results/data_collection/multimarket_sp_capture_v1"
DEFAULT_FREEZE_ROOT = ROOT / "results/research/multimarket_10h_freeze_v1"
SCORE_RE = re.compile(r"^\s*(\d+)\s*[:-]\s*(\d+)\s*$")


class MultimarketP0Error(ValueError):
    """Raised when an immutable capture or research invariant fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_hkt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HKT)
    return parsed.astimezone(HKT)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def explicit_utc(value: str) -> str:
    return parse_utc(value).isoformat(timespec="microseconds")


def explicit_hkt(value: str) -> str:
    return parse_hkt(value).isoformat(timespec="seconds")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_sp_capture_batches (
            batch_id TEXT PRIMARY KEY,
            issue TEXT NOT NULL,
            playid INTEGER NOT NULL,
            market_key TEXT NOT NULL,
            source_url TEXT NOT NULL,
            fetched_at_utc TEXT NOT NULL,
            source_updated_at_hkt TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            bundle_path TEXT NOT NULL,
            bundle_sha256s_sha256 TEXT NOT NULL,
            match_rows INTEGER NOT NULL,
            outcome_rows INTEGER NOT NULL,
            complete_vector_rows INTEGER NOT NULL,
            open_rows INTEGER NOT NULL,
            terminal_rows INTEGER NOT NULL,
            classification_summary_json TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            UNIQUE(issue, playid, fetched_at_utc, payload_sha256)
        );
        CREATE INDEX IF NOT EXISTS idx_market_capture_issue
            ON market_sp_capture_batches(issue, playid, fetched_at_utc);

        CREATE TABLE IF NOT EXISTS multimarket_settlement_truth (
            issue TEXT NOT NULL,
            match_id TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            market_key TEXT NOT NULL,
            fthg INTEGER,
            ftag INTEGER,
            outcome_code TEXT,
            winning_sp REAL,
            settlement_status TEXT NOT NULL,
            special_flags_json TEXT NOT NULL,
            score_source TEXT NOT NULL,
            winning_sp_source TEXT NOT NULL,
            source_batch_id TEXT,
            generated_at_hkt TEXT NOT NULL,
            PRIMARY KEY(issue, match_idx, market_key)
        );
        """
    )
    if not _table_exists(conn, "live_market_sp_snapshots"):
        return
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(live_market_sp_snapshots)")}
    additions = {
        "match_id": "TEXT",
        "batch_id": "TEXT",
        "source_url": "TEXT",
        "fetched_at_utc": "TEXT",
        "source_updated_at_hkt": "TEXT",
        "sale_status": "TEXT NOT NULL DEFAULT 'unknown'",
        "sale_cutoff_hkt": "TEXT",
        "parlay_allowed": "TEXT NOT NULL DEFAULT 'unknown'",
        "parlay_modes_json": "TEXT NOT NULL DEFAULT '[]'",
        "stake_limit_json": "TEXT NOT NULL DEFAULT '{}'",
        "capture_classification": "TEXT NOT NULL DEFAULT 'legacy_unclassified'",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE live_market_sp_snapshots ADD COLUMN {name} {definition}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_live_market_sp_batch ON live_market_sp_snapshots(batch_id)"
    )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def verify_bundle(path: Path) -> dict[str, str]:
    sums = path / "SHA256SUMS"
    if not sums.is_file():
        raise MultimarketP0Error(f"SHA256SUMS missing: {path}")
    entries: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise MultimarketP0Error(f"invalid SHA256SUMS line: {line!r}") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or Path(name).name != name:
            raise MultimarketP0Error(f"invalid SHA256SUMS entry: {line!r}")
        target = path / name
        if not target.is_file() or sha256_file(target) != digest:
            raise MultimarketP0Error(f"checksum mismatch: {target}")
        entries[name] = digest
    if set(entries) != {"manifest.json", "raw.xml"}:
        raise MultimarketP0Error("capture bundle must contain manifest.json and raw.xml")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "multimarket_sp_capture_batch_v1":
        raise MultimarketP0Error("unsupported capture bundle schema")
    if manifest.get("payload_sha256") != entries["raw.xml"]:
        raise MultimarketP0Error("capture manifest payload digest mismatch")
    return entries


def _atomic_bundle(final: Path, raw_payload: bytes, manifest: Mapping[str, Any]) -> None:
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.tmp-", dir=final.parent))
    try:
        raw = stage / "raw.xml"
        raw.write_bytes(raw_payload)
        manifest_path = stage / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        sums = stage / "SHA256SUMS"
        sums.write_text(
            f"{sha256_file(manifest_path)}  manifest.json\n{sha256_file(raw)}  raw.xml\n",
            encoding="utf-8",
        )
        verify_bundle(stage)
        for path in (raw, manifest_path, sums):
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        descriptor = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        stage.rename(final)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _sale_metadata(conn: sqlite3.Connection, issue: str) -> dict[int, dict[str, str]]:
    if not _table_exists(conn, "matches"):
        return {}
    rows = conn.execute(
        "SELECT match_idx,end_time,disabled FROM matches WHERE issue=?", (issue,)
    ).fetchall()
    return {
        int(row[0]): {
            "sale_cutoff_hkt": explicit_hkt(str(row[1])) if row[1] else "",
            "sale_status": "open" if str(row[2] or "").lower() == "no" else "closed" if row[2] else "unknown",
        }
        for row in rows
    }


def classify_rows(
    conn: sqlite3.Connection,
    issue: str,
    playid: int,
    rows: list[dict[str, Any]],
    *,
    fetched_at_utc: str,
    source_updated_at_hkt: str,
) -> list[dict[str, Any]]:
    expected = EXPECTED_OUTCOMES.get(playid)
    if expected is None:
        return rows
    sale = _sale_metadata(conn, issue)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["row_idx"])].append(row)
    fetch_clock = parse_utc(fetched_at_utc).astimezone(HKT)
    source_clock = parse_hkt(source_updated_at_hkt)
    for match_idx, match_rows in grouped.items():
        metadata = sale.get(match_idx, {})
        cutoff_text = metadata.get("sale_cutoff_hkt", "")
        sale_status = metadata.get("sale_status", "unknown")
        positive = sum(float(row["sp"] or 0) > 0 for row in match_rows)
        before_cutoff = bool(
            cutoff_text
            and fetch_clock < parse_hkt(cutoff_text)
            and source_clock < parse_hkt(cutoff_text)
        )
        if before_cutoff and positive == expected and sale_status == "open":
            classification = "forward_complete_open"
        elif before_cutoff and positive == expected:
            classification = "forward_complete_sale_unknown"
        elif not before_cutoff and positive == 1:
            classification = "terminal_backfill_exploratory_only"
        elif not before_cutoff:
            classification = "post_cutoff_static_exploratory_only"
        else:
            classification = "forward_incomplete_rejected"
        for row in match_rows:
            row.update(
                {
                    "fetched_at_utc": explicit_utc(fetched_at_utc),
                    "source_updated_at_hkt": explicit_hkt(source_updated_at_hkt),
                    "match_id": f"{issue}_{match_idx:03d}",
                    "sale_status": sale_status,
                    "sale_cutoff_hkt": cutoff_text or None,
                    "parlay_allowed": "unknown",
                    "parlay_modes_json": "[]",
                    "stake_limit_json": "{}",
                    "capture_classification": classification,
                }
            )
    return rows


def publish_capture_batch(
    conn: sqlite3.Connection,
    *,
    issue: str,
    playid: int,
    source_url: str,
    fetched_at_utc: str,
    source_updated_at_hkt: str,
    raw_payload: bytes,
    rows: list[dict[str, Any]],
    capture_root: Path = DEFAULT_CAPTURE_ROOT,
) -> dict[str, Any]:
    if playid not in TARGET_PLAYIDS:
        raise MultimarketP0Error(f"P0 capture is limited to playids {TARGET_PLAYIDS}")
    if not _table_exists(conn, "market_sp_capture_batches"):
        raise MultimarketP0Error("P0 schema missing; run ensure_schema before publishing")
    rows = classify_rows(
        conn,
        issue,
        playid,
        rows,
        fetched_at_utc=fetched_at_utc,
        source_updated_at_hkt=source_updated_at_hkt,
    )
    payload_sha = sha256_bytes(raw_payload)
    identity = f"{issue}|{playid}|{explicit_utc(fetched_at_utc)}|{payload_sha}"
    batch_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    final = capture_root.expanduser().resolve() / issue / batch_id
    classifications = Counter(str(row["capture_classification"]) for row in rows)
    match_rows = len({int(row["row_idx"]) for row in rows})
    complete = len(
        {
            int(row["row_idx"])
            for row in rows
            if row["capture_classification"] == "forward_complete_open"
        }
    )
    open_rows = len({int(row["row_idx"]) for row in rows if row["sale_status"] == "open"})
    terminal = len(
        {
            int(row["row_idx"])
            for row in rows
            if row["capture_classification"] == "terminal_backfill_exploratory_only"
        }
    )
    manifest = {
        "schema_version": "multimarket_sp_capture_batch_v1",
        "batch_id": batch_id,
        "issue": issue,
        "playid": playid,
        "market_key": MARKET_KEY[playid],
        "source_url": source_url,
        "fetched_at_utc": explicit_utc(fetched_at_utc),
        "source_updated_at_hkt": explicit_hkt(source_updated_at_hkt),
        "payload_sha256": payload_sha,
        "match_rows": match_rows,
        "outcome_rows": len(rows),
        "expected_outcomes_per_match": EXPECTED_OUTCOMES[playid],
        "complete_forward_open_rows": complete,
        "open_rows": open_rows,
        "terminal_rows": terminal,
        "classification_summary": dict(sorted(classifications.items())),
        "sale_metadata": {
            "status_source": "same-cycle issue disabled flag plus target-market full vector",
            "parlay_allowed": "unknown",
            "parlay_modes": [],
            "stake_limit": {},
        },
        "research_policy": "terminal and legacy rows are exploratory_only_not_roi",
    }
    if final.exists():
        verify_bundle(final)
        existing = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
        if existing != manifest:
            raise MultimarketP0Error(f"immutable capture conflicts: {final}")
    else:
        _atomic_bundle(final, raw_payload, manifest)
    bundle_hash = sha256_file(final / "SHA256SUMS")
    for row in rows:
        row["batch_id"] = batch_id
        row["source_url"] = source_url
    conn.execute(
        """
        INSERT OR IGNORE INTO market_sp_capture_batches(
            batch_id,issue,playid,market_key,source_url,fetched_at_utc,
            source_updated_at_hkt,payload_sha256,bundle_path,bundle_sha256s_sha256,
            match_rows,outcome_rows,complete_vector_rows,open_rows,terminal_rows,
            classification_summary_json,schema_version
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            batch_id,
            issue,
            playid,
            MARKET_KEY[playid],
            source_url,
            manifest["fetched_at_utc"],
            manifest["source_updated_at_hkt"],
            payload_sha,
            str(final),
            bundle_hash,
            match_rows,
            len(rows),
            complete,
            open_rows,
            terminal,
            json.dumps(dict(classifications), sort_keys=True),
            manifest["schema_version"],
        ),
    )
    return {**manifest, "bundle_path": str(final), "bundle_sha256s_sha256": bundle_hash, "rows": rows}


def resolve_kickoff_hkt(sale_cutoff: str, kickoff_time: str) -> datetime | None:
    if not sale_cutoff or not kickoff_time:
        return None
    cutoff = parse_hkt(sale_cutoff)
    try:
        hour, minute = (int(value) for value in kickoff_time.split(":", 1))
    except (TypeError, ValueError):
        return None
    candidates = [
        (cutoff + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        for offset in (-1, 0, 1)
    ]
    plausible = [item for item in candidates if cutoff <= item <= cutoff + timedelta(hours=6)]
    return min(plausible, default=None)


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_freeze(path: Path) -> dict[str, Any]:
    output = path.expanduser().resolve()
    sums = output / "SHA256SUMS"
    if not sums.is_file():
        raise MultimarketP0Error(f"SHA256SUMS missing: {output}")
    expected_names = {"frozen_outcomes.csv", "manifest.json", "rejections.csv"}
    entries: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise MultimarketP0Error(f"invalid SHA256SUMS line: {line!r}") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or Path(name).name != name:
            raise MultimarketP0Error(f"invalid SHA256SUMS entry: {line!r}")
        target = output / name
        if not target.is_file() or sha256_file(target) != digest:
            raise MultimarketP0Error(f"checksum mismatch: {target}")
        entries[name] = digest
    if set(entries) != expected_names:
        raise MultimarketP0Error(f"freeze bundle files mismatch: {sorted(entries)}")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "multimarket_asof_freeze_v1":
        raise MultimarketP0Error("unsupported freeze bundle schema")
    with (output / "frozen_outcomes.csv").open(encoding="utf-8", newline="") as handle:
        frozen = list(csv.DictReader(handle))
    with (output / "rejections.csv").open(encoding="utf-8", newline="") as handle:
        rejected = list(csv.DictReader(handle))
    if len(frozen) != int(manifest.get("frozen_outcome_rows", -1)):
        raise MultimarketP0Error("freeze outcome row count mismatch")
    if len(rejected) != int(manifest.get("rejected_match_markets", -1)):
        raise MultimarketP0Error("freeze rejection row count mismatch")
    match_markets = {(row["match_idx"], row["playid"]) for row in frozen}
    if len(match_markets) != int(manifest.get("frozen_match_markets", -1)):
        raise MultimarketP0Error("freeze match-market count mismatch")
    return {
        "status": "valid",
        "output_dir": str(output),
        "frozen_outcome_rows": len(frozen),
        "rejected_match_markets": len(rejected),
        "sha256s_sha256": sha256_file(sums),
    }


def freeze_10h(
    conn: sqlite3.Connection,
    issue: str,
    output_dir: Path,
    *,
    target_hours: float = 10.0,
    playids: Iterable[int] = TARGET_PLAYIDS,
) -> dict[str, Any]:
    ensure_schema(conn)
    output = output_dir.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"freeze output already exists: {output}")
    matches = conn.execute(
        """
        SELECT m.issue,m.match_idx,m.end_time,
               COALESCE(n.kickoff_time,'') AS kickoff_time
        FROM matches m
        LEFT JOIN nowscore_bjdc_matches n
          ON n.issue=m.issue AND n.match_idx=m.match_idx
        WHERE m.issue=? ORDER BY m.match_idx
        """,
        (issue,),
    ).fetchall()
    if not matches:
        raise MultimarketP0Error(f"issue has no matches: {issue}")
    frozen: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    selected_batches: set[str] = set()
    for match in matches:
        match_idx = int(match["match_idx"])
        kickoff = resolve_kickoff_hkt(str(match["end_time"] or ""), str(match["kickoff_time"] or ""))
        for playid in playids:
            market_key = MARKET_KEY.get(playid, str(playid))
            if kickoff is None:
                rejected.append({"issue": issue, "match_idx": match_idx, "market_key": market_key, "reason": "kickoff_unknown"})
                continue
            target = kickoff - timedelta(hours=target_hours)
            batches = conn.execute(
                """
                SELECT batch_id,fetched_at_utc,source_updated_at_hkt,payload_sha256,
                       source_url,bundle_path,bundle_sha256s_sha256
                FROM market_sp_capture_batches
                WHERE issue=? AND playid=?
                  AND datetime(fetched_at_utc)<=datetime(?)
                  AND datetime(source_updated_at_hkt)<=datetime(?)
                ORDER BY datetime(source_updated_at_hkt) DESC, datetime(fetched_at_utc) DESC
                """,
                (issue, playid, target.astimezone(timezone.utc).isoformat(), target.isoformat()),
            ).fetchall()
            selected: tuple[sqlite3.Row, list[sqlite3.Row]] | None = None
            last_reason = "no_asof_snapshot"
            for batch in batches:
                rows = conn.execute(
                    """
                    SELECT match_id,outcome_code,outcome_label,sp,sale_status,sale_cutoff_hkt,parlay_allowed,
                           capture_classification,fetched_at_utc,source_updated_at_hkt
                    FROM live_market_sp_snapshots
                    WHERE batch_id=? AND row_idx=? ORDER BY outcome_code
                    """,
                    (batch["batch_id"], match_idx),
                ).fetchall()
                if len(rows) != EXPECTED_OUTCOMES[playid] or any(row["sp"] is None or float(row["sp"]) <= 1 for row in rows):
                    last_reason = "incomplete_or_invalid_vector"
                    continue
                if any(row["sale_status"] != "open" for row in rows):
                    last_reason = "not_confirmed_sale_open"
                    continue
                if any(row["capture_classification"] != "forward_complete_open" for row in rows):
                    last_reason = "not_forward_complete"
                    continue
                expected_match_id = f"{issue}_{match_idx:03d}"
                if any(
                    row["match_id"] != expected_match_id or not row["sale_cutoff_hkt"]
                    for row in rows
                ):
                    last_reason = "audit_fields_missing_or_mismatched"
                    continue
                bundle = Path(str(batch["bundle_path"]))
                verify_bundle(bundle)
                if sha256_file(bundle / "SHA256SUMS") != batch["bundle_sha256s_sha256"]:
                    last_reason = "bundle_digest_mismatch"
                    continue
                selected = (batch, rows)
                break
            if selected is None:
                rejected.append(
                    {
                        "issue": issue,
                        "match_idx": match_idx,
                        "market_key": market_key,
                        "kickoff_hkt": kickoff.isoformat(),
                        "target_hkt": target.isoformat(),
                        "reason": last_reason,
                    }
                )
                continue
            batch, rows = selected
            selected_batches.add(str(batch["batch_id"]))
            for row in rows:
                frozen.append(
                    {
                        "issue": issue,
                        "match_id": row["match_id"],
                        "match_idx": match_idx,
                        "market_key": market_key,
                        "playid": playid,
                        "outcome_code": row["outcome_code"],
                        "outcome_label": row["outcome_label"],
                        "sp": row["sp"],
                        "kickoff_hkt": kickoff.isoformat(),
                        "target_hkt": target.isoformat(),
                        "fetched_at_utc": row["fetched_at_utc"],
                        "source_updated_at_hkt": row["source_updated_at_hkt"],
                        "sale_status": row["sale_status"],
                        "sale_cutoff_hkt": row["sale_cutoff_hkt"],
                        "parlay_allowed": row["parlay_allowed"],
                        "batch_id": batch["batch_id"],
                        "payload_sha256": batch["payload_sha256"],
                        "source_url": batch["source_url"],
                    }
                )
    if not frozen:
        raise MultimarketP0Error("no valid 10h target-market rows; refusing empty freeze")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        fields = list(frozen[0])
        rejection_fields = ["issue", "match_idx", "market_key", "kickoff_hkt", "target_hkt", "reason"]
        _write_csv(stage / "frozen_outcomes.csv", frozen, fields)
        _write_csv(stage / "rejections.csv", rejected, rejection_fields)
        manifest = {
            "schema_version": "multimarket_asof_freeze_v1",
            "issue": issue,
            "target_hours_before_kickoff": target_hours,
            "target_playids": list(playids),
            "frozen_outcome_rows": len(frozen),
            "frozen_match_markets": len({(row["match_idx"], row["playid"]) for row in frozen}),
            "rejected_match_markets": len(rejected),
            "selected_batch_ids": sorted(selected_batches),
            "policy": {
                "dual_clock_at_or_before_target": True,
                "complete_vector_required": True,
                "sale_status_required": "open",
                "terminal_or_legacy_allowed": False,
                "roi_authorized": False,
                "parlay_metadata": "retained_but_currently_unknown",
            },
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payloads = sorted(path for path in stage.iterdir() if path.name != "SHA256SUMS")
        (stage / "SHA256SUMS").write_text(
            "".join(f"{sha256_file(path)}  {path.name}\n" for path in payloads), encoding="utf-8"
        )
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    verification = verify_freeze(output)
    return {**manifest, "output_dir": str(output), "sha256s_sha256": verification["sha256s_sha256"]}


def parse_score(value: str) -> tuple[int, int] | None:
    match = SCORE_RE.match(value or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def correct_score_outcome(fthg: int, ftag: int) -> str:
    exact = {
        "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2",
        "0:0", "1:1", "2:2", "3:3",
        "0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4",
    }
    score = f"{fthg}:{ftag}"
    if score in exact:
        return score
    return "home_other" if fthg > ftag else "draw_other" if fthg == ftag else "away_other"


def _winning_sp(conn: sqlite3.Connection, issue: str, match_idx: int, playid: int, outcome_code: str) -> tuple[float | None, str, str]:
    row = conn.execute(
        """
        SELECT sp,COALESCE(batch_id,''),COALESCE(capture_classification,'legacy_unclassified')
        FROM live_market_sp_snapshots
        WHERE issue=? AND row_idx=? AND playid=? AND outcome_code=? AND sp IS NOT NULL
        ORDER BY (COALESCE(batch_id,'')<>'') DESC,
                 datetime(COALESCE(fetched_at_utc,fetched_at)) DESC LIMIT 1
        """,
        (issue, match_idx, playid, outcome_code),
    ).fetchone()
    if row is None:
        return None, "missing", ""
    source = str(row[2] or "legacy_unclassified")
    if not row[1]:
        source = "legacy_terminal_backfill_exploratory_only"
    return float(row[0]), source, str(row[1] or "")


def build_settlement_truth(conn: sqlite3.Connection, issue: str) -> dict[str, Any]:
    ensure_schema(conn)
    if _table_exists(conn, "nowscore_bjdc_matches"):
        rows = conn.execute(
            """
            SELECT m.match_idx,m.score,m.disabled,m.end_time,
                   COALESCE(n.score,'') AS nowscore_score,
                   COALESCE(n.status_text,'') AS status_text,
                   COALESCE(n.status,'') AS provider_status
            FROM matches m LEFT JOIN nowscore_bjdc_matches n
              ON n.issue=m.issue AND n.match_idx=m.match_idx
            WHERE m.issue=? ORDER BY m.match_idx
            """,
            (issue,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT match_idx,score,disabled,end_time,'' AS nowscore_score,
                   '' AS status_text,'' AS provider_status
            FROM matches WHERE issue=? ORDER BY match_idx
            """,
            (issue,),
        ).fetchall()
    if not rows:
        raise MultimarketP0Error(f"issue has no matches: {issue}")
    generated = datetime.now(HKT).isoformat(timespec="seconds")
    counts: Counter[str] = Counter()
    for row in rows:
        match_idx = int(row["match_idx"])
        score_text = str(row["score"] or row["nowscore_score"] or "")
        score = parse_score(score_text)
        status_text = f"{row['status_text']} {row['provider_status']}".lower()
        flags: list[str] = []
        if any(value in status_text for value in ("取消", "cancel")):
            flags.append("cancelled")
        if any(value in status_text for value in ("延期", "推迟", "postpon")):
            flags.append("postponed")
        for playid in TARGET_PLAYIDS:
            market = MARKET_KEY[playid]
            fthg = score[0] if score else None
            ftag = score[1] if score else None
            outcome = (
                (str(min(fthg + ftag, 7)) if fthg + ftag < 7 else "7+")
                if score and playid == 40
                else correct_score_outcome(fthg, ftag)
                if score
                else ""
            )
            winning_sp, winning_source, batch_id = _winning_sp(conn, issue, match_idx, playid, outcome) if outcome else (None, "missing", "")
            local_flags = list(flags)
            if winning_sp == 1:
                local_flags.append("sp1_void")
            if "cancelled" in local_flags:
                settlement_status = "cancelled"
            elif "postponed" in local_flags:
                settlement_status = "postponed"
            elif winning_sp == 1:
                settlement_status = "void_sp1"
            elif score is None:
                settlement_status = "pending_or_unknown"
            elif winning_sp is None:
                settlement_status = "result_complete_sp_missing"
            else:
                settlement_status = "settled"
            counts[settlement_status] += 1
            conn.execute(
                """
                INSERT INTO multimarket_settlement_truth(
                    issue,match_id,match_idx,market_key,fthg,ftag,outcome_code,
                    winning_sp,settlement_status,special_flags_json,score_source,
                    winning_sp_source,source_batch_id,generated_at_hkt
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(issue,match_idx,market_key) DO UPDATE SET
                    fthg=excluded.fthg,ftag=excluded.ftag,outcome_code=excluded.outcome_code,
                    winning_sp=excluded.winning_sp,settlement_status=excluded.settlement_status,
                    special_flags_json=excluded.special_flags_json,score_source=excluded.score_source,
                    winning_sp_source=excluded.winning_sp_source,source_batch_id=excluded.source_batch_id,
                    generated_at_hkt=excluded.generated_at_hkt
                """,
                (
                    issue,
                    f"{issue}_{match_idx:03d}",
                    match_idx,
                    market,
                    fthg,
                    ftag,
                    outcome or None,
                    winning_sp,
                    settlement_status,
                    json.dumps(local_flags, ensure_ascii=False),
                    "matches.score" if row["score"] else "nowscore_bjdc_matches.score" if row["nowscore_score"] else "missing",
                    winning_source,
                    batch_id or None,
                    generated,
                ),
            )
    conn.commit()
    return {"issue": issue, "market_rows": len(rows) * len(TARGET_PLAYIDS), "status_counts": dict(counts), "generated_at_hkt": generated}
