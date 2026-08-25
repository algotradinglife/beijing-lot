"""Immutable, source-bound 2025 settlement package builder for #396.

The online acquisition boundary writes one raw 500.com result page and exactly one
terminal receipt per requested issue.  The package builder is offline-only: it
consumes those frozen pages, reconstructs the canonical settlement table, and
fails closed on incomplete or semantically inconsistent rows.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.backfill.parser import parse_issue_html
from src.backfill.scraper import KAIJIANG_URL, DEFAULT_UA

CONTRACT_VERSION = "BJ-DATA-2025-SETTLEMENT-BACKFILL-001/v1"
DISPOSITION_READY = "READY_FOR_394_FULL_2025_REPLAY"
DISPOSITION_BLOCKED = "BLOCKED_RESIDUAL_2025_SETTLEMENT_GAPS"
TARGET_ISSUES = tuple(
    f"25{suffix:03d}"
    for suffix in (
        11, 12, 13, 14, 21, 22, 23, 24, 31, 32, 33, 34, 35, 41, 42,
        43, 44, 51, 52, 53, 54, 55, 61, 62, 63, 64, 65, 71, 72, 73,
        74, 75, 81, 82, 83, 84, 85, 91, 92, 93, 94, 95, 101, 102, 103,
        104, 105, 111, 112, 113, 114, 115, 121, 122, 123, 124, 125,
    )
)


class SettlementError(RuntimeError):
    """Raised when a source/package invariant is violated."""


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_replace(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)


def _write_json(path: Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _atomic_replace(tmp, path)


def _check_target_issues(issues: Iterable[str]) -> list[str]:
    normalized = [str(issue) for issue in issues]
    if normalized != list(TARGET_ISSUES):
        raise SettlementError("target census must be the complete ordered 2025 500.com calendar")
    return normalized


def fetch_raw_pages(raw_root: str | Path, *, issues: Iterable[str] = TARGET_ISSUES, timeout: int = 30, rate_seconds: float = 1.0) -> pd.DataFrame:
    """Acquire 500.com pages with one terminal, hash-bound receipt per issue.

    Existing success pages are not silently reused: their existing receipt is
    validated and then reported as an explicit immutable reuse. Network failures
    still produce terminal receipts, preserving the denominator.
    """
    issue_list = _check_target_issues(issues)
    root = Path(raw_root)
    pages = root / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    receipt_path = root / "acquisition_receipts.csv"
    prior: dict[str, dict] = {}
    if receipt_path.exists():
        for row in pd.read_csv(receipt_path, dtype=str).fillna("").to_dict("records"):
            prior[row["issue"]] = row
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    records: list[dict[str, object]] = []
    for position, issue in enumerate(issue_list):
        page = pages / f"{issue}.html"
        old = prior.get(issue, {})
        if page.is_file() and old.get("acquisition_result") == "SUCCESS" and old.get("payload_sha256") == _sha256(page):
            records.append({
                "issue": issue, "source_url": KAIJIANG_URL.format(issue=issue),
                "requested_at_utc": old.get("requested_at_utc", ""),
                "received_at_utc": old.get("received_at_utc", ""),
                "acquisition_result": "SUCCESS", "http_status": old.get("http_status", "200"),
                "payload_bytes": page.stat().st_size, "payload_sha256": _sha256(page),
                "error_class": "", "error_detail": "IMMUTABLE_REUSE",
            })
            continue
        requested = _utc_now()
        url = KAIJIANG_URL.format(issue=issue)
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.content
            decoded = payload.decode("gb18030", errors="strict")
            rows = parse_issue_html(decoded, issue)
            if not rows:
                raise SettlementError("page parsed zero match rows")
            tmp = page.with_suffix(".html.tmp")
            tmp.write_bytes(payload)
            _atomic_replace(tmp, page)
            records.append({
                "issue": issue, "source_url": url, "requested_at_utc": requested,
                "received_at_utc": _utc_now(), "acquisition_result": "SUCCESS",
                "http_status": response.status_code, "payload_bytes": len(payload),
                "payload_sha256": _sha256(page), "error_class": "", "error_detail": "",
            })
        except Exception as exc:  # terminal receipt is required even on failure
            records.append({
                "issue": issue, "source_url": url, "requested_at_utc": requested,
                "received_at_utc": _utc_now(), "acquisition_result": "FAILURE",
                "http_status": getattr(getattr(exc, "response", None), "status_code", ""),
                "payload_bytes": "", "payload_sha256": "", "error_class": type(exc).__name__,
                "error_detail": str(exc)[:500],
            })
        if position < len(issue_list) - 1 and rate_seconds > 0:
            import time
            time.sleep(rate_seconds)
    frame = pd.DataFrame(records)
    if frame["issue"].duplicated().any() or set(frame["issue"]) != set(issue_list):
        raise SettlementError("acquisition receipts must cover target census exactly once")
    tmp = receipt_path.with_suffix(".csv.tmp")
    frame.to_csv(tmp, index=False, encoding="utf-8")
    _atomic_replace(tmp, receipt_path)
    return frame


def _parse_frozen_raw(raw_root: Path, issues: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    receipt_path = raw_root / "acquisition_receipts.csv"
    if not receipt_path.is_file():
        raise SettlementError("missing acquisition receipt ledger")
    receipts = pd.read_csv(receipt_path, dtype=str).fillna("")
    if receipts["issue"].tolist() != issues or receipts["issue"].duplicated().any():
        raise SettlementError("receipt ledger does not exactly equal target census")
    records: list[dict] = []
    for receipt in receipts.to_dict("records"):
        issue = receipt["issue"]
        if receipt["acquisition_result"] != "SUCCESS":
            raise SettlementError(f"unresolved acquisition: {issue}")
        page = raw_root / "pages" / f"{issue}.html"
        if not page.is_file() or _sha256(page) != receipt["payload_sha256"]:
            raise SettlementError(f"raw page hash mismatch: {issue}")
        parsed = parse_issue_html(page.read_bytes().decode("gb18030", errors="strict"), issue)
        if not parsed:
            raise SettlementError(f"zero parsed rows: {issue}")
        for row in parsed:
            value = asdict(row)
            value["source_url"] = receipt["source_url"]
            value["source_payload_sha256"] = receipt["payload_sha256"]
            value["source_received_at_utc"] = receipt["received_at_utc"]
            value["correction_state"] = "CURRENT_AT_CAPTURE"
            value["settlement_availability_ts"] = receipt["received_at_utc"]
            records.append(value)
    table = pd.DataFrame(records)
    numeric = table[["handicap_line", "fthg", "ftag", "winning_sp"]].apply(pd.to_numeric, errors="coerce")
    derived = pd.Series("1", index=table.index)
    derived.loc[numeric["fthg"] + numeric["handicap_line"] > numeric["ftag"]] = "3"
    derived.loc[numeric["fthg"] + numeric["handicap_line"] < numeric["ftag"]] = "0"
    table["settlement_semantics"] = "NATIVE_HANDICAP_OUTCOME"
    void_refund = (numeric["winning_sp"] == 1.0) & numeric.notna().all(axis=1) & derived.ne(table["result_code"].astype(str))
    table.loc[void_refund, "settlement_semantics"] = "VOID_REFUND_NATIVE_SP_1"
    table.loc[numeric.isna().any(axis=1), "settlement_semantics"] = "MISSING_NATIVE_SETTLEMENT"
    return table, receipts


def _validate_settlements(table: pd.DataFrame, issues: list[str], *, require_all_issues: bool = True) -> pd.DataFrame:
    required = {
        "issue", "match_idx", "league", "kickoff_ts", "home", "away", "handicap_line",
        "fthg", "ftag", "result_code", "winning_sp", "avg_eu_home", "avg_eu_draw", "avg_eu_away",
        "source_url", "source_payload_sha256", "source_received_at_utc", "correction_state",
        "settlement_availability_ts", "settlement_semantics",
    }
    if set(table.columns) != required:
        raise SettlementError("settlement schema drift")
    if require_all_issues and set(table["issue"].astype(str)) != set(issues):
        raise SettlementError("settlement table does not cover target census")
    if not set(table["issue"].astype(str)).issubset(set(issues)):
        raise SettlementError("settlement table contains an out-of-census issue")
    if table.duplicated(["issue", "match_idx"]).any():
        raise SettlementError("duplicate issue/match identity")
    numeric = table[["match_idx", "handicap_line", "fthg", "ftag", "winning_sp"]].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or (numeric["match_idx"] < 1).any() or (numeric["winning_sp"] <= 0).any():
        raise SettlementError("incomplete native settlement values")
    expected = pd.Series("1", index=table.index)
    expected.loc[numeric["fthg"] + numeric["handicap_line"] > numeric["ftag"]] = "3"
    expected.loc[numeric["fthg"] + numeric["handicap_line"] < numeric["ftag"]] = "0"
    mismatch = expected.ne(table["result_code"].astype(str))
    allowed_void_refund = (
        table["settlement_semantics"].eq("VOID_REFUND_NATIVE_SP_1")
        & numeric["winning_sp"].eq(1.0)
    )
    if (mismatch & ~allowed_void_refund).any():
        raise SettlementError("native handicap outcome conflicts with result code")
    for field in ("league", "kickoff_ts", "home", "away", "source_url", "source_payload_sha256", "source_received_at_utc"):
        if table[field].isna().any() or table[field].astype(str).str.strip().eq("").any():
            raise SettlementError(f"missing required source-bound field: {field}")
    counts = table.groupby("issue", sort=False).size()
    if (require_all_issues and counts.index.tolist() != issues) or (counts <= 0).any():
        raise SettlementError("each required census issue must have one or more complete settlement records")
    return table.sort_values(["issue", "match_idx"], kind="stable").reset_index(drop=True)


def _raw_row_text(raw_root: Path, issue: str, match_idx: int) -> str:
    page = raw_root / "pages" / f"{issue}.html"
    soup = BeautifulSoup(page.read_bytes().decode("gb18030", errors="strict"), "lxml")
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        if cells and cells[0].get_text(strip=True) == str(match_idx):
            return tr.get_text(" ", strip=True)
    raise SettlementError(f"cannot locate raw source row: {issue}/{match_idx}")


def _partition_settlements(all_rows: pd.DataFrame, raw_root: Path, issues: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate fully evidenced settlement records from a fail-closed residual ledger."""
    numeric = all_rows[["match_idx", "handicap_line", "fthg", "ftag", "winning_sp"]].apply(pd.to_numeric, errors="coerce")
    complete = ~(numeric.isna().any(axis=1) | (numeric["match_idx"] < 1) | (numeric["winning_sp"] <= 0))
    included = _validate_settlements(all_rows.loc[complete].copy(), issues, require_all_issues=False)
    residual: list[dict[str, object]] = []
    for _, row in all_rows.loc[~complete].sort_values(["issue", "match_idx"], kind="stable").iterrows():
        text = _raw_row_text(raw_root, str(row["issue"]), int(row["match_idx"]))
        if "改期" in text:
            reason = "POSTPONED_ON_500_PAGE_NO_NATIVE_SETTLEMENT"
        elif "取消" in text:
            reason = "CANCELLED_ON_500_PAGE_NO_NATIVE_SETTLEMENT"
        else:
            reason = "UNRESOLVED_NATIVE_SETTLEMENT_ABSENT_ON_500_PAGE"
        residual.append({
            "issue": row["issue"], "match_idx": int(row["match_idx"]), "exclusion_reason": reason,
            "source_url": row["source_url"], "source_payload_sha256": row["source_payload_sha256"],
            "source_row_evidence": text,
        })
    exclusions = pd.DataFrame(residual, columns=["issue", "match_idx", "exclusion_reason", "source_url", "source_payload_sha256", "source_row_evidence"])
    if included.duplicated(["issue", "match_idx"]).any() or exclusions.duplicated(["issue", "match_idx"]).any():
        raise SettlementError("duplicate identity after settlement partition")
    if set(map(tuple, included[["issue", "match_idx"]].to_records(index=False))) & set(map(tuple, exclusions[["issue", "match_idx"]].to_records(index=False))):
        raise SettlementError("included/excluded identity overlap")
    if len(included) + len(exclusions) != len(all_rows):
        raise SettlementError("partition does not account for every source row")
    return included, exclusions


def _manifest(root: Path, *, implementation_sha: str, disposition: str) -> dict:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.json":
            files[path.relative_to(root).as_posix()] = _sha256(path)
    return {
        "contract": CONTRACT_VERSION,
        "disposition": disposition,
        "implementation_sha256": implementation_sha,
        "files": files,
    }


def build_package(raw_root: str | Path, package_root: str | Path, *, issues: Iterable[str] = TARGET_ISSUES) -> Path:
    """Build a portable, replayable package solely from immutable raw receipts."""
    issue_list = _check_target_issues(issues)
    raw = Path(raw_root)
    all_rows, receipts = _parse_frozen_raw(raw, issue_list)
    settlements, exclusions = _partition_settlements(all_rows, raw, issue_list)
    disposition = DISPOSITION_READY if exclusions.empty else DISPOSITION_BLOCKED
    destination = Path(package_root)
    if destination.exists():
        raise SettlementError("refusing to overwrite an existing package")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="bj396-", dir=str(destination.parent)))
    try:
        (staging / "raw" / "pages").mkdir(parents=True)
        for page in sorted((raw / "pages").glob("*.html")):
            shutil.copy2(page, staging / "raw" / "pages" / page.name)
        receipts.to_csv(staging / "raw" / "acquisition_receipts.csv", index=False, encoding="utf-8")
        settlements.to_parquet(staging / "canonical_settlements.parquet", index=False)
        exclusions.to_csv(staging / "exclusion_ledger.csv", index=False, encoding="utf-8")
        included_counts = settlements.groupby("issue", sort=False).agg(
            included_fixture_count=("match_idx", "size"),
            first_kickoff_ts=("kickoff_ts", "min"),
            last_kickoff_ts=("kickoff_ts", "max"),
            maximum_settlement_availability_ts=("settlement_availability_ts", "max"),
        )
        excluded_counts = exclusions.groupby("issue", sort=False).size().rename("excluded_fixture_count")
        issue_ledger = pd.DataFrame({"issue": issue_list}).join(included_counts, on="issue").join(excluded_counts, on="issue").fillna({"included_fixture_count": 0, "excluded_fixture_count": 0})
        issue_ledger["inclusion_status"] = issue_ledger["excluded_fixture_count"].map(lambda n: "INCLUDED" if int(n) == 0 else "PARTIAL_BLOCKED")
        issue_ledger["reason"] = issue_ledger["inclusion_status"].map({"INCLUDED": "COMPLETE_500_NATIVE_SETTLEMENT", "PARTIAL_BLOCKED": "SEE_EXCLUSION_LEDGER"})
        issue_ledger.to_csv(staging / "issue_ledger.csv", index=False, encoding="utf-8")
        inventory = pd.DataFrame([
            {"source_id": "500_kaijiang", "classification": "AUTHORITATIVE_PUBLIC_RESULT_PAGE", "admissible_use": "CANONICAL_NATIVE_SETTLEMENT", "coverage": "all 57 target issues", "notes": "native handicap, final score, 3/1/0 result and winning SP"},
            {"source_id": "beidan_xlsm", "classification": "LOCAL_LEGACY_LINEAGE", "admissible_use": "CENSUS_AND_CROSSCHECK_ONLY", "coverage": "25011-25042 only", "notes": "absence after 25042 is not an exclusion reason"},
            {"source_id": "bj268_nowscore_titan", "classification": "IMMUTABLE_ODDS_RECOVERY", "admissible_use": "FIXTURE_IDENTITY_CROSSCHECK_ONLY", "coverage": "25043-25125", "notes": "does not supply native winning SP settlement"},
        ])
        inventory.to_csv(staging / "source_inventory.csv", index=False, encoding="utf-8")
        maximum = settlements["settlement_availability_ts"].max()
        decision = {
            "contract": CONTRACT_VERSION,
            "disposition": disposition,
            "target_issue_count": len(issue_list),
            "included_issue_count": int((issue_ledger["included_fixture_count"] > 0).sum()),
            "excluded_issue_count": int((issue_ledger["excluded_fixture_count"] > 0).sum()),
            "source_row_count": int(len(all_rows)),
            "settlement_record_count": int(len(settlements)),
            "excluded_fixture_count": int(len(exclusions)),
            "unresolved_native_settlement_count": int(exclusions["exclusion_reason"].eq("UNRESOLVED_NATIVE_SETTLEMENT_ABSENT_ON_500_PAGE").sum()),
            "first_issue": issue_list[0],
            "last_issue": issue_list[-1],
            "maximum_settlement_availability_timestamp": maximum,
            "strategy_execution_authorized": False,
        }
        _write_json(staging / "decision.json", decision)
        implementation_sha = _sha256(Path(__file__))
        _write_json(staging / "MANIFEST.json", _manifest(staging, implementation_sha=implementation_sha, disposition=disposition))
        _atomic_replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def verify_package(package_root: str | Path) -> dict:
    """Verify all content hashes and independently reconstruct settlements from raw pages."""
    root = Path(package_root)
    manifest_path = root / "MANIFEST.json"
    if not manifest_path.is_file():
        raise SettlementError("missing package manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract") != CONTRACT_VERSION or manifest.get("disposition") not in {DISPOSITION_READY, DISPOSITION_BLOCKED}:
        raise SettlementError("manifest contract/disposition mismatch")
    if manifest.get("implementation_sha256") != _sha256(Path(__file__)):
        raise SettlementError("implementation binding mismatch")
    expected_files = manifest.get("files")
    actual_files = {p.relative_to(root).as_posix(): _sha256(p) for p in root.rglob("*") if p.is_file() and p.name != "MANIFEST.json"}
    if expected_files != actual_files:
        raise SettlementError("package file census or content hash mismatch")
    decision = json.loads((root / "decision.json").read_text(encoding="utf-8"))
    if decision.get("disposition") != manifest.get("disposition"):
        raise SettlementError("decision/manifest disposition mismatch")
    all_rows, _ = _parse_frozen_raw(root / "raw", list(TARGET_ISSUES))
    replay, expected_exclusions = _partition_settlements(all_rows, root / "raw", list(TARGET_ISSUES))
    expected_disposition = DISPOSITION_READY if expected_exclusions.empty else DISPOSITION_BLOCKED
    if expected_disposition != decision.get("disposition"):
        raise SettlementError("disposition does not match source recovery state")
    emitted = pd.read_parquet(root / "canonical_settlements.parquet")
    emitted = _validate_settlements(emitted, list(TARGET_ISSUES), require_all_issues=False)
    if list(emitted.columns) != list(replay.columns) or not emitted.equals(replay):
        raise SettlementError("semantic replay differs from emitted settlement table")
    exclusions = pd.read_csv(root / "exclusion_ledger.csv", dtype=str).fillna("")
    expected_exclusions = expected_exclusions.astype(str).fillna("")
    if list(exclusions.columns) != list(expected_exclusions.columns) or not exclusions.equals(expected_exclusions):
        raise SettlementError("exclusion ledger differs from raw source evidence")
    ledger = pd.read_csv(root / "issue_ledger.csv", dtype=str).fillna("")
    if ledger["issue"].tolist() != list(TARGET_ISSUES):
        raise SettlementError("issue ledger does not exactly represent target census")
    if int(decision.get("settlement_record_count", -1)) != len(emitted) or int(decision.get("excluded_fixture_count", -1)) != len(exclusions):
        raise SettlementError("decision count mismatch")
    if decision.get("disposition") == DISPOSITION_READY and not exclusions.empty:
        raise SettlementError("ready disposition contains excluded fixtures")
    return {"status": "PASS", "disposition": decision["disposition"], "files": len(actual_files), "settlement_records": len(emitted), "excluded_records": len(exclusions), "issues": len(TARGET_ISSUES)}
