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
from io import StringIO
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
CONTRACT_AMENDMENT_V2 = "BJ-DATA-2025-SETTLEMENT-BACKFILL-001/v2"
# v1 was published before the v2 verifier extension.  Its exact source hash is
# retained so the known frozen v1 package remains independently replayable.
V1_PUBLISHED_IMPLEMENTATION_SHA256 = "a7d8f717e8d75093188a728a3aa24c2de6d8247f56c051f2fc5ac9377f4d3920"
# Pinned source receipts for the frozen v2 amendment.  This is the trusted
# external anchor that keeps a raw-page + manifest rewrite from becoming a new
# settlement truth claim.
V2_NOWSCORE_PAGE_SHA256 = {
    "25012": "f765b509998ebbae220d00dd32faf7aea71532cff87b8b6237acb3e99281ab31",
    "25014": "c594a92d54a3ccc4541e6bcb9b966595a2e2eed0ef7c84312d1e946b7ab8628a",
    "25023": "bf97e19fc01f658ab05b0f24cb84be05b8d1c9f59a3c15dea7dbb633f286380b",
    "25031": "7aa90c4e1cbad5d042b65b440f48006e7d96e6a816072462a65b57e884de1c42",
    "25032": "4f281478f5180bece4d7b59cd816955acb01ce3cdc955a4f263e7398787fbe20",
    "25043": "2708dc0060e4e3295d83ee5e8e6a49b5972b346b372bb77a3f4d427e29544351",
    "25085": "f2eacfe0e9386f7a69defb6966166814cf7d65cfc596201ab157a6212c6b6c78",
    "25092": "c32feb69854a8c2da2a455054b0d9972ff0c5fa472527f6843e3c0880eb66c72",
    "25093": "ca6ea3078c2cc78279c74bfa10f7682af85be0a8341f7775885d23b7dfbe6f7b",
    "25094": "a5483561c29d6802fe8d70197240948c0d231f877f9c56a2afb52f805e41e1b8",
    "25102": "060c2418804f506a41441daf0c4c699a700ac7fa808fedbd013a041ad406803a",
    "25103": "4378424b94fe8973e1268eec082a46ec61e55aa68c2591363275328d834a44cd",
    "25104": "c303273b4f59a955867ad7f423e3553247906bb9c726764198a1d52e4f2283da",
    "25105": "f38c07a5de0f9a405a9697e182eb8db5f6de28562551b2af20c7c7a437a58404",
    "25111": "1d72ff3e32af29e6b541765728af839aaf1d5babc7e8d273987a326671c56296",
    "25121": "576db55fd5b6c88f7c08db2c640795a0b8c67e8590c22a6820064ea238ef2fe7",
}
# Git does not preserve filesystem mtimes. Capture timestamps are immutable
# source-receipt fields, not properties of a particular checkout.
V2_NOWSCORE_CAPTURED_AT_UTC = {
    "25012": "2026-08-25T12:54:16+00:00",
    "25014": "2026-08-25T12:54:17+00:00",
    "25023": "2026-08-25T12:54:18+00:00",
    "25031": "2026-08-25T12:54:19+00:00",
    "25032": "2026-08-25T12:54:20+00:00",
    "25043": "2026-08-25T12:54:22+00:00",
    "25085": "2026-08-25T12:54:22+00:00",
    "25092": "2026-08-25T12:54:23+00:00",
    "25093": "2026-08-25T12:54:24+00:00",
    "25094": "2026-08-25T12:54:25+00:00",
    "25102": "2026-08-25T12:54:25+00:00",
    "25103": "2026-08-25T12:54:26+00:00",
    "25104": "2026-08-25T12:54:27+00:00",
    "25105": "2026-08-25T12:54:28+00:00",
    "25111": "2026-08-25T12:54:29+00:00",
    "25121": "2026-08-25T12:54:29+00:00",
}
V2_SOURCE_PROBE_RECEIPT_COLUMNS = (
    "source_id", "source_identity", "probe_path_or_url", "observed_at_utc",
    "sha256_or_absence_evidence", "exact_key_predicate",
    "exact_23_key_hit_count", "native_winning_sp_capability",
    "admissible_use", "probe_result",
)
# Read-only amendment-v2 source-lane probes for the exact 23 v1 no-SP keys.
# Local materialization hashes are audit receipts, not an elevation of a mutable
# database to independent settlement authority.
V2_SOURCE_PROBE_RECEIPT_ROWS = (
    ("500_kaijiang", "500.com authoritative result/native-SP issue pages", "raw/pages/*.html + raw/acquisition_receipts.csv", "2026-08-25T12:27:17+00:00", "7e906359b1a14ae674468d513a3a178d791915f4870202b1ed310292c5b1f915", "baseline unresolved (issue,match_idx) exact join", 23, "NO_NATIVE_SP_FOR_EXACT_23", "CANONICAL_NATIVE_SETTLEMENT_FOR_COMPLETE_ROWS", "23 exact baseline rows have official result/SP=- and remain non-settleable"),
    ("beidan_live_settlements", "local beidan_live.settlements SQLite materialization", "/home/drwho1985/workspace/soccer/beijing-lot/data/beidan_live.db:settlements", "2026-08-25T13:34:02+00:00", "c6b4ea52ed3d26b9d0b030f28125cb441afcc7f500bf236645be5f9352a12090", "INNER JOIN requested USING(issue,match_idx)", 0, "NO_EXACT_23_HITS", "EXHAUSTED_NO_ADDITIONAL_SETTLEMENT_EVIDENCE", "read-only/WAL-aware exact-key probe returned zero rows"),
    ("beidan_xlsm_bj268", "frozen local Beidan XLSM / BJ268 lineage", "/home/drwho1985/workspace/soccer/beijing-lot/data/raw/beidan.xlsm", "2026-08-25T13:34:02+00:00", "f825020658f2b0e95715659381107c246a24ec36b87801eebb63233921072d59", "conservative fixture identity probe for 23 baseline keys", 7, "NO_SOURCE_NATIVE_BEIJING_SP_RECEIPT", "CENSUS_AND_CROSSCHECK_ONLY", "7 exact fixture-identity hits; no source-native Beijing winning-SP receipt for any residual"),
    ("official_500_settlements", "local derived official_500_settlements SQLite table", "/home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite:official_500_settlements", "2026-08-25T13:35:04+00:00", "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f", "INNER JOIN requested USING(issue,match_idx)", 0, "NO_EXACT_23_HITS", "EXHAUSTED_DERIVED_DUPLICATE_OF_500_LANE", "read-only exact-key probe returned zero rows; table is not an independent raw source"),
    ("nowscore_issue_provider", "frozen Nowscore issue/provider snapshots", "raw/nowscore_issue_pages/*.html", "2026-08-25T12:54:16+00:00", "PER_PAGE_SHA256_PINNED_IN_V2_NOWSCORE_PAGE_SHA256", "INNER JOIN requested USING(issue,match_idx)", 23, "NO_NATIVE_BEIJING_WINNING_SP", "EXCLUSION_CLASSIFICATION_ONLY", "5 exact cancellations and 18 finished/no-native-SP rows; no payout or SP is inferred"),
)
V2_XLSM_IDENTITY_HITS = (
    ("25012", 81),
    ("25012", 98),
    ("25012", 118),
    ("25014", 252),
    ("25023", 24),
    ("25031", 315),
    ("25032", 341),
)
TARGET_ISSUES = tuple(
    f"25{suffix:03d}"
    for suffix in (
        11, 12, 13, 14, 21, 22, 23, 24, 31, 32, 33, 34, 35, 41, 42,
        43, 44, 51, 52, 53, 54, 55, 61, 62, 63, 64, 65, 71, 72, 73,
        74, 75, 81, 82, 83, 84, 85, 91, 92, 93, 94, 95, 101, 102, 103,
        104, 105, 111, 112, 113, 114, 115, 121, 122, 123, 124, 125,
    )
)
FROZEN_TARGET_ISSUES = TARGET_ISSUES


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


def classify_residuals_with_nowscore(residuals: pd.DataFrame, probes: pd.DataFrame) -> pd.DataFrame:
    """Classify only source-bound unresolved rows from exact Nowscore issue/slot probes.

    A finished score is evidence of final result only.  It never creates a
    winning SP; therefore finished rows remain excluded as
    ``NEVER_SETTLED_OFFICIAL_NO_SP``.  Cancellation requires the provider's
    direct cancellation status and an exact issue/slot identity.
    """
    required_residual = {"issue", "match_idx", "exclusion_reason", "source_row_evidence"}
    required_probe = {
        "issue", "match_idx", "identity_status", "nowscore_status",
        "nowscore_status_text", "nowscore_score", "nowscore_result_code",
        "nowscore_sp_url",
    }
    if not required_residual.issubset(residuals.columns):
        raise SettlementError("residual ledger missing nowscore classification keys")
    if not required_probe.issubset(probes.columns):
        raise SettlementError("nowscore probe ledger missing required fields")
    left = residuals.copy()
    left["issue"] = left["issue"].astype(str)
    left["match_idx"] = pd.to_numeric(left["match_idx"], errors="raise").astype(int)
    right = probes.copy()
    right["issue"] = right["issue"].astype(str)
    right["match_idx"] = pd.to_numeric(right["match_idx"], errors="raise").astype(int)
    if right.duplicated(["issue", "match_idx"]).any():
        raise SettlementError("nowscore probe duplicate issue/slot identity")
    merged = left.merge(right, on=["issue", "match_idx"], how="left", validate="one_to_one")
    for column in required_probe - {"issue", "match_idx"}:
        merged[column] = merged[column].fillna("").astype(str)
    unresolved = merged["exclusion_reason"].eq("UNRESOLVED_NATIVE_SETTLEMENT_ABSENT_ON_500_PAGE")
    exact = merged["identity_status"].eq("EXACT_ISSUE_SLOT")
    cancelled = exact & merged["nowscore_status_text"].str.contains("取消", regex=False)
    finished = (
        exact
        & merged["nowscore_status"].eq("finished")
        & merged["nowscore_result_code"].isin(["3", "1", "0"])
        & merged["nowscore_score"].str.fullmatch(r"\d+[-:]\d+")
    )
    merged.loc[unresolved & cancelled, "exclusion_reason"] = "POSTPONED_OR_CANCELLED"
    merged.loc[unresolved & finished, "exclusion_reason"] = "NEVER_SETTLED_OFFICIAL_NO_SP"
    merged.loc[unresolved & ~(cancelled | finished), "exclusion_reason"] = "UNRESOLVED_NATIVE_SETTLEMENT_GAP"
    return merged


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


def _issue_ledger(settlements: pd.DataFrame, exclusions: pd.DataFrame, issue_list: list[str]) -> pd.DataFrame:
    included_counts = settlements.groupby("issue", sort=False).agg(
        included_fixture_count=("match_idx", "size"),
        first_kickoff_ts=("kickoff_ts", "min"),
        last_kickoff_ts=("kickoff_ts", "max"),
        maximum_settlement_availability_ts=("settlement_availability_ts", "max"),
    )
    excluded_counts = exclusions.groupby("issue", sort=False).size().rename("excluded_fixture_count")
    ledger = pd.DataFrame({"issue": issue_list}).join(included_counts, on="issue").join(excluded_counts, on="issue").fillna({"included_fixture_count": 0, "excluded_fixture_count": 0})
    ledger["inclusion_status"] = ledger["excluded_fixture_count"].map(lambda n: "INCLUDED" if int(n) == 0 else "PARTIAL_BLOCKED")
    ledger["reason"] = ledger["inclusion_status"].map({"INCLUDED": "COMPLETE_500_NATIVE_SETTLEMENT", "PARTIAL_BLOCKED": "SEE_EXCLUSION_LEDGER"})
    return ledger


def _v2_issue_ledger(settlements: pd.DataFrame, exclusions: pd.DataFrame, issue_list: list[str]) -> pd.DataFrame:
    """Emit v2 eligibility without elevating fixture exclusions to issue blocks."""
    ledger = _issue_ledger(settlements, exclusions, issue_list).copy()
    if (ledger["included_fixture_count"] <= 0).any():
        raise SettlementError("v2 issue eligibility requires canonical settlement rows for every census issue")
    partial = ledger["excluded_fixture_count"].astype(int).gt(0)
    ledger["downstream_eligible"] = True
    ledger.loc[partial, "inclusion_status"] = "INCLUDED_WITH_ADMISSIBLE_FIXTURE_EXCLUSIONS"
    ledger.loc[partial, "reason"] = "SEE_RESIDUAL_DISPOSITION_V2"
    return ledger


def _v2_source_probe_receipts() -> pd.DataFrame:
    """Return the frozen amendment-v2 source-lane probe receipt in canonical order."""
    return pd.DataFrame(V2_SOURCE_PROBE_RECEIPT_ROWS, columns=V2_SOURCE_PROBE_RECEIPT_COLUMNS)


def _validate_v2_source_probe_receipts(receipts: pd.DataFrame) -> pd.DataFrame:
    """Reject semantic changes to the all-lane exact-23 source audit receipt."""
    expected = _v2_source_probe_receipts().astype(str).fillna("")
    actual = receipts.copy().astype(str).fillna("")
    if list(actual.columns) != list(expected.columns) or not actual.equals(expected):
        raise SettlementError("v2 source-probe receipt differs from frozen source-lane audit")
    if actual["source_id"].duplicated().any() or len(actual) != 5:
        raise SettlementError("v2 source-probe receipt must represent each declared lane exactly once")
    if actual["exact_23_key_hit_count"].astype(int).tolist() != [23, 0, 7, 0, 23]:
        raise SettlementError("v2 source-probe receipt exact-key coverage mismatch")
    return actual


def _v2_xlsm_identity_probe_ledger() -> pd.DataFrame:
    """Freeze the seven exact XLSM/BJ268 fixture-identity corroborations.

    These rows prove identity only. They deliberately carry no winning SP and
    cannot make an otherwise excluded fixture settleable.
    """
    return pd.DataFrame(
        [
            {
                "issue": issue,
                "match_idx": match_idx,
                "source_id": "beidan_xlsm_bj268",
                "source_sha256": "f825020658f2b0e95715659381107c246a24ec36b87801eebb63233921072d59",
                "evidence_class": "FIXTURE_IDENTITY_ONLY",
                "native_winning_sp_admissible": False,
            }
            for issue, match_idx in V2_XLSM_IDENTITY_HITS
        ]
    )


def _validate_v2_xlsm_identity_probe_ledger(ledger: pd.DataFrame) -> pd.DataFrame:
    expected = _v2_xlsm_identity_probe_ledger().astype(str).fillna("")
    actual = ledger.copy().astype(str).fillna("")
    if list(actual.columns) != list(expected.columns) or not actual.equals(expected):
        raise SettlementError("v2 XLSM identity-probe ledger differs from frozen evidence")
    if actual.duplicated(["issue", "match_idx"]).any() or len(actual) != 7:
        raise SettlementError("v2 XLSM identity-probe ledger key census mismatch")
    if actual["native_winning_sp_admissible"].str.lower().ne("false").any():
        raise SettlementError("XLSM identity evidence must not authorize winning SP")
    return actual


def _validate_v2_500_receipt_anchor(receipts: pd.DataFrame, raw_root: Path) -> None:
    """Bind the 500 source-probe receipt to the immutable acquisition ledger bytes."""
    source = receipts.loc[receipts["source_id"].eq("500_kaijiang")]
    if len(source) != 1:
        raise SettlementError("v2 source-probe receipt lacks a unique 500 lane")
    expected = str(source.iloc[0]["sha256_or_absence_evidence"])
    receipt_path = raw_root / "acquisition_receipts.csv"
    if not receipt_path.is_file() or _sha256(receipt_path) != expected:
        raise SettlementError("frozen 500 acquisition receipt differs from source-probe anchor")


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
        issue_ledger = _issue_ledger(settlements, exclusions, issue_list)
        issue_ledger.to_csv(staging / "issue_ledger.csv", index=False, encoding="utf-8")
        inventory = pd.DataFrame([
            {"source_id": "500_kaijiang", "classification": "AUTHORITATIVE_PUBLIC_RESULT_PAGE", "admissible_use": "CANONICAL_NATIVE_SETTLEMENT", "coverage": "all 57 target issues", "notes": "native handicap, final score, 3/1/0 result and winning SP"},
            {"source_id": "beidan_xlsm", "classification": "LOCAL_LEGACY_LINEAGE", "admissible_use": "CENSUS_AND_CROSSCHECK_ONLY", "coverage": "25011-25042 only", "notes": "absence after 25042 is not an exclusion reason"},
            {"source_id": "bj268_nowscore_titan", "classification": "IMMUTABLE_ODDS_RECOVERY", "admissible_use": "FIXTURE_IDENTITY_CROSSCHECK_ONLY", "coverage": "25043-25125", "notes": "does not supply native winning SP settlement"},
        ])
        inventory.to_csv(staging / "source_inventory.csv", index=False, encoding="utf-8")
        maximum = None if settlements.empty else str(settlements["settlement_availability_ts"].max())
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


def _check_v2_nowscore_freeze(issue: str, payload: bytes) -> str:
    """Return a pinned payload digest or fail closed outside amendment-v2 receipts."""
    expected = V2_NOWSCORE_PAGE_SHA256.get(str(issue))
    actual = sha256(payload).hexdigest()
    if expected is None or actual != expected:
        raise SettlementError(f"Nowscore snapshot hash differs from frozen receipt for issue {issue}")
    return actual


def _nowscore_probe_ledger(raw_root: Path, residuals: pd.DataFrame) -> pd.DataFrame:
    """Parse immutable Nowscore issue snapshots for precisely the v1 gap set."""
    from scripts.scrape_nowscore_bjdc import NOWSCORE_URL, parse_rows

    targets = residuals.loc[
        residuals["exclusion_reason"].eq("UNRESOLVED_NATIVE_SETTLEMENT_ABSENT_ON_500_PAGE"),
        ["issue", "match_idx"],
    ].copy()
    targets["issue"] = targets["issue"].astype(str)
    targets["match_idx"] = pd.to_numeric(targets["match_idx"], errors="raise").astype(int)
    if targets.duplicated(["issue", "match_idx"]).any():
        raise SettlementError("baseline residual ledger has duplicate issue/slot")
    target_issues = set(targets["issue"].unique())
    if target_issues != set(V2_NOWSCORE_PAGE_SHA256):
        raise SettlementError("v2 Nowscore probe issue census differs from frozen contract")
    if target_issues != set(V2_NOWSCORE_CAPTURED_AT_UTC):
        raise SettlementError("v2 Nowscore capture-time census differs from frozen contract")
    records: list[dict[str, object]] = []
    for issue in sorted(target_issues):
        page = raw_root / f"{issue}.html"
        if not page.is_file():
            raise SettlementError(f"missing Nowscore issue snapshot: {issue}")
        payload = page.read_bytes()
        payload_sha256 = _check_v2_nowscore_freeze(issue, payload)
        captured_at = V2_NOWSCORE_CAPTURED_AT_UTC[issue]
        parsed = {
            int(row["match_idx"]): row
            for row in parse_rows(issue, payload.decode("utf-8", errors="strict"), "FROZEN_IN_RECEIPT")
        }
        for target in targets.loc[targets["issue"].eq(issue)].to_dict("records"):
            row = parsed.get(int(target["match_idx"]))
            fields = {
                "issue": issue,
                "match_idx": int(target["match_idx"]),
                "nowscore_issue_url": NOWSCORE_URL.format(issue=issue),
                "nowscore_captured_at_utc": captured_at,
                "nowscore_payload_sha256": payload_sha256,
                "nowscore_payload_bytes": len(payload),
                "identity_status": "MISSING_OR_AMBIGUOUS" if row is None else "EXACT_ISSUE_SLOT",
                "provider_match_id": "", "nowscore_status": "", "nowscore_status_text": "",
                "nowscore_score": "", "nowscore_result_code": "", "nowscore_handicap_line": "",
                "nowscore_home": "", "nowscore_away": "", "nowscore_sp_url": "", "nowscore_raw_row_hash": "",
            }
            if row is not None:
                fields.update({
                    "provider_match_id": str(row["provider_match_id"]),
                    "nowscore_status": str(row["status"]),
                    "nowscore_status_text": str(row["status_text"]),
                    "nowscore_score": str(row["score"]),
                    "nowscore_result_code": str(row["result_code"] or ""),
                    "nowscore_handicap_line": "" if row["handicap_line"] is None else str(row["handicap_line"]),
                    "nowscore_home": str(row["home"]), "nowscore_away": str(row["away"]),
                    "nowscore_sp_url": str(row["sp_url"]), "nowscore_raw_row_hash": str(row["raw_row_hash"]),
                })
            records.append(fields)
    probes = pd.DataFrame(records)
    if len(probes) != len(targets) or probes.duplicated(["issue", "match_idx"]).any():
        raise SettlementError("Nowscore probe coverage does not equal unresolved baseline rows")
    return probes.sort_values(["issue", "match_idx"], kind="stable").reset_index(drop=True)


def extend_package_amendment_v2(baseline_root: str | Path, nowscore_raw_root: str | Path, package_root: str | Path) -> Path:
    """Extend, never overwrite, the v1 package with receipted source-lane probes."""
    baseline = Path(baseline_root)
    destination = Path(package_root)
    if destination.exists() or not (baseline / "MANIFEST.json").is_file():
        raise SettlementError("v2 requires an existing v1 baseline and an absent destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="bj396-v2-", dir=str(destination.parent)))
    try:
        shutil.copytree(baseline, staging, dirs_exist_ok=True)
        shutil.copy2(staging / "MANIFEST.json", staging / "baseline_manifest_v1.json")
        baseline_exclusions = pd.read_csv(staging / "exclusion_ledger.csv", dtype=str).fillna("")
        probes = _nowscore_probe_ledger(Path(nowscore_raw_root), baseline_exclusions)
        (staging / "raw" / "nowscore_issue_pages").mkdir(parents=True)
        for issue in sorted(probes["issue"].unique()):
            shutil.copy2(Path(nowscore_raw_root) / f"{issue}.html", staging / "raw" / "nowscore_issue_pages" / f"{issue}.html")
        probes.to_csv(staging / "nowscore_probe_ledger.csv", index=False, encoding="utf-8")
        revised = classify_residuals_with_nowscore(baseline_exclusions, probes)
        revised.loc[revised["exclusion_reason"].eq("POSTPONED_ON_500_PAGE_NO_NATIVE_SETTLEMENT"), "exclusion_reason"] = "POSTPONED_OR_CANCELLED"
        revised.loc[revised["exclusion_reason"].eq("CANCELLED_ON_500_PAGE_NO_NATIVE_SETTLEMENT"), "exclusion_reason"] = "POSTPONED_OR_CANCELLED"
        unresolved = revised["exclusion_reason"].eq("UNRESOLVED_NATIVE_SETTLEMENT_GAP")
        disposition = DISPOSITION_BLOCKED if unresolved.any() else DISPOSITION_READY
        revised.to_csv(staging / "residual_disposition_v2.csv", index=False, encoding="utf-8")
        settlements = pd.read_parquet(staging / "canonical_settlements.parquet")
        issue_ledger = _v2_issue_ledger(settlements, revised, list(TARGET_ISSUES))
        issue_ledger.to_csv(staging / "issue_ledger.csv", index=False, encoding="utf-8")
        source_probe_receipts = _validate_v2_source_probe_receipts(_v2_source_probe_receipts())
        source_probe_receipts.to_csv(staging / "source_probe_receipts_v2.csv", index=False, encoding="utf-8")
        xlsm_identity = _validate_v2_xlsm_identity_probe_ledger(
            _v2_xlsm_identity_probe_ledger()
        )
        xlsm_identity.to_csv(
            staging / "xlsm_identity_probe_ledger.csv",
            index=False,
            encoding="utf-8",
        )
        decision = json.loads((staging / "decision.json").read_text(encoding="utf-8"))
        decision.pop("excluded_issue_count", None)
        decision.update({
            "contract": CONTRACT_AMENDMENT_V2, "disposition": disposition,
            "downstream_eligible_issue_count": int(issue_ledger["downstream_eligible"].sum()),
            "issues_with_admissible_fixture_exclusions": int(issue_ledger["excluded_fixture_count"].astype(int).gt(0).sum()),
            "nowscore_probed_fixture_count": int(len(probes)),
            "postponed_or_cancelled_fixture_count": int(revised["exclusion_reason"].eq("POSTPONED_OR_CANCELLED").sum()),
            "never_settled_official_no_sp_count": int(revised["exclusion_reason"].eq("NEVER_SETTLED_OFFICIAL_NO_SP").sum()),
            "unresolved_native_settlement_count": int(unresolved.sum()),
            "strategy_execution_authorized": False,
        })
        _write_json(staging / "decision.json", decision)
        _write_json(staging / "MANIFEST.json", _manifest(staging, implementation_sha=_sha256(Path(__file__)), disposition=disposition) | {"contract": CONTRACT_AMENDMENT_V2})
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
    contract = manifest.get("contract")
    if contract not in {CONTRACT_VERSION, CONTRACT_AMENDMENT_V2} or manifest.get("disposition") not in {DISPOSITION_READY, DISPOSITION_BLOCKED}:
        raise SettlementError("manifest contract/disposition mismatch")
    implementation_hash = manifest.get("implementation_sha256")
    allowed_implementation_hashes = {_sha256(Path(__file__))}
    if contract == CONTRACT_VERSION:
        allowed_implementation_hashes.add(V1_PUBLISHED_IMPLEMENTATION_SHA256)
    if implementation_hash not in allowed_implementation_hashes:
        raise SettlementError("implementation binding mismatch")
    expected_files = manifest.get("files")
    actual_files = {p.relative_to(root).as_posix(): _sha256(p) for p in root.rglob("*") if p.is_file() and p.name != "MANIFEST.json"}
    if expected_files != actual_files:
        raise SettlementError("package file census or content hash mismatch")
    decision = json.loads((root / "decision.json").read_text(encoding="utf-8"))
    if decision.get("disposition") != manifest.get("disposition"):
        raise SettlementError("decision/manifest disposition mismatch")
    if decision.get("strategy_execution_authorized") is not False:
        raise SettlementError("settlement package must not authorize strategy execution")
    all_rows, _ = _parse_frozen_raw(root / "raw", list(TARGET_ISSUES))
    replay, expected_exclusions = _partition_settlements(all_rows, root / "raw", list(TARGET_ISSUES))
    expected_disposition = DISPOSITION_READY if expected_exclusions.empty else DISPOSITION_BLOCKED
    if contract == CONTRACT_VERSION and expected_disposition != decision.get("disposition"):
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
    ledger_builder = _v2_issue_ledger if contract == CONTRACT_AMENDMENT_V2 else _issue_ledger
    expected_ledger = ledger_builder(replay, expected_exclusions, list(TARGET_ISSUES))
    expected_ledger = pd.read_csv(StringIO(expected_ledger.to_csv(index=False)), dtype=str).fillna("")
    if list(ledger.columns) != list(expected_ledger.columns) or not ledger.equals(expected_ledger):
        raise SettlementError("issue ledger differs from source recovery state")
    if ledger["issue"].tolist() != list(TARGET_ISSUES):
        raise SettlementError("issue ledger does not exactly represent target census")
    expected_decision_counts = {
        "target_issue_count": len(TARGET_ISSUES),
        "included_issue_count": int(emitted["issue"].astype(str).nunique()),
        "source_row_count": len(all_rows),
        "settlement_record_count": len(emitted),
        "excluded_fixture_count": len(exclusions),
    }
    if contract == CONTRACT_AMENDMENT_V2:
        expected_decision_counts.update({
            "downstream_eligible_issue_count": len(TARGET_ISSUES),
            "issues_with_admissible_fixture_exclusions": int(exclusions["issue"].astype(str).nunique()),
        })
        if "excluded_issue_count" in decision:
            raise SettlementError("v2 decision must not label admissibly partial issues as excluded")
    else:
        expected_decision_counts["excluded_issue_count"] = int(exclusions["issue"].astype(str).nunique())
    for key, expected in expected_decision_counts.items():
        if int(decision.get(key, -1)) != expected:
            raise SettlementError(f"decision count mismatch: {key}")
    if decision.get("first_issue") != TARGET_ISSUES[0] or decision.get("last_issue") != TARGET_ISSUES[-1]:
        raise SettlementError("decision target bounds mismatch")
    expected_maximum_timestamp = None if emitted.empty else str(emitted["settlement_availability_ts"].max())
    if decision.get("maximum_settlement_availability_timestamp") != expected_maximum_timestamp:
        raise SettlementError("decision settlement availability timestamp mismatch")
    if decision.get("disposition") == DISPOSITION_READY and contract == CONTRACT_VERSION and not exclusions.empty:
        raise SettlementError("ready disposition contains excluded fixtures")
    if contract == CONTRACT_AMENDMENT_V2:
        baseline_manifest = json.loads((root / "baseline_manifest_v1.json").read_text(encoding="utf-8"))
        if baseline_manifest.get("contract") != CONTRACT_VERSION:
            raise SettlementError("missing immutable v1 baseline receipt")
        emitted_source_probes = pd.read_csv(root / "source_probe_receipts_v2.csv", dtype=str).fillna("")
        _validate_v2_source_probe_receipts(emitted_source_probes)
        emitted_xlsm_identity = pd.read_csv(
            root / "xlsm_identity_probe_ledger.csv", dtype=str
        ).fillna("")
        _validate_v2_xlsm_identity_probe_ledger(emitted_xlsm_identity)
        if tuple(TARGET_ISSUES) == FROZEN_TARGET_ISSUES:
            _validate_v2_500_receipt_anchor(emitted_source_probes, root / "raw")
        probes = _nowscore_probe_ledger(root / "raw" / "nowscore_issue_pages", exclusions)
        emitted_probes = pd.read_csv(root / "nowscore_probe_ledger.csv", dtype=str).fillna("")
        expected_probes = probes.astype(str).fillna("")
        if list(emitted_probes.columns) != list(expected_probes.columns) or not emitted_probes.equals(expected_probes):
            raise SettlementError("Nowscore probe ledger differs from immutable source pages")
        revised = classify_residuals_with_nowscore(exclusions, probes)
        revised.loc[revised["exclusion_reason"].eq("POSTPONED_ON_500_PAGE_NO_NATIVE_SETTLEMENT"), "exclusion_reason"] = "POSTPONED_OR_CANCELLED"
        revised.loc[revised["exclusion_reason"].eq("CANCELLED_ON_500_PAGE_NO_NATIVE_SETTLEMENT"), "exclusion_reason"] = "POSTPONED_OR_CANCELLED"
        expected_revised = revised.astype(str).fillna("")
        emitted_revised = pd.read_csv(root / "residual_disposition_v2.csv", dtype=str).fillna("")
        if list(emitted_revised.columns) != list(expected_revised.columns) or not emitted_revised.equals(expected_revised):
            raise SettlementError("v2 residual disposition differs from source evidence")
        allowed = {"POSTPONED_OR_CANCELLED", "NEVER_SETTLED_OFFICIAL_NO_SP"}
        unresolved = ~emitted_revised["exclusion_reason"].isin(allowed)
        expected_disposition = DISPOSITION_BLOCKED if unresolved.any() else DISPOSITION_READY
        if decision.get("disposition") != expected_disposition:
            raise SettlementError("v2 disposition does not match residual evidence")
        if int(decision.get("nowscore_probed_fixture_count", -1)) != len(probes):
            raise SettlementError("v2 Nowscore probe count mismatch")
        if int(decision.get("unresolved_native_settlement_count", -1)) != int(unresolved.sum()):
            raise SettlementError("v2 unresolved count mismatch")
        for key, reason in {
            "postponed_or_cancelled_fixture_count": "POSTPONED_OR_CANCELLED",
            "never_settled_official_no_sp_count": "NEVER_SETTLED_OFFICIAL_NO_SP",
        }.items():
            if int(decision.get(key, -1)) != int(emitted_revised["exclusion_reason"].eq(reason).sum()):
                raise SettlementError(f"v2 residual category count mismatch: {key}")
    return {"status": "PASS", "contract": contract, "disposition": decision["disposition"], "files": len(actual_files), "settlement_records": len(emitted), "excluded_records": len(exclusions), "issues": len(TARGET_ISSUES)}
