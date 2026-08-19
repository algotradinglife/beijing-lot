"""Rate-limited, immutable source probes for historical proxy recovery."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scripts.update_beidan_nowscore_sqlite import (
    parse_cp_issue_html,
    parse_titan_1x2_text,
)
from src.source_schema import publication


ISSUE_URL = "https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum={issue}"
TITAN_URL = "https://1x2d.titan007.com/{provider_match_id}.js"


@dataclass(frozen=True)
class FetchReceipt:
    source_kind: str
    source_key: str
    source_url: str
    requested_at_utc: str
    received_at_utc: str
    status_code: int
    payload_bytes: int
    payload_sha256: str
    parser_version: str = "bj267_v2"


@dataclass(frozen=True)
class ProbeResult:
    issue_code: str
    local_candidate_fixture_count: int
    source_fixture_count: int
    matched_slot_count: int
    local_only_slot_count: int
    source_only_slot_count: int
    issue_payload_sha256: str
    sampled_titan_match_count: int
    sampled_titan_success_count: int
    sampled_complete_triplets: int
    status: str


class ProbeClient:
    """Small requests-based client that records every response before parsing."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "close",
            }
        )

    def fetch(self, source_kind: str, source_key: str, url: str) -> tuple[bytes, FetchReceipt]:
        requested = datetime.now(UTC).isoformat(timespec="seconds")
        response = self.session.get(url, timeout=self.timeout)
        received = datetime.now(UTC).isoformat(timespec="seconds")
        response.raise_for_status()
        payload = response.content
        receipt = FetchReceipt(
            source_kind=source_kind,
            source_key=source_key,
            source_url=url,
            requested_at_utc=requested,
            received_at_utc=received,
            status_code=response.status_code,
            payload_bytes=len(payload),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
        )
        return payload, receipt


class StagedProbeClient:
    """Replay responses from an immutable, hash-bound staging namespace."""

    def __init__(self, staging_root: Path) -> None:
        self.staging_root = staging_root.expanduser().resolve()
        receipts = pd.read_csv(
            self.staging_root / "FETCH_RECEIPTS.csv",
            dtype=str,
            keep_default_na=False,
        )
        duplicate = receipts.duplicated(["source_kind", "source_key"], keep=False)
        if duplicate.any():
            keys = receipts.loc[duplicate, ["source_kind", "source_key"]].to_dict(
                "records"
            )
            raise ValueError(f"duplicate staged receipts: {keys[:5]}")
        self.receipts = {
            (row.source_kind, row.source_key): row._asdict()
            for row in receipts.itertuples(index=False)
        }

    def fetch(self, source_kind: str, source_key: str, url: str) -> tuple[bytes, FetchReceipt]:
        key = (str(source_kind), str(source_key))
        if key not in self.receipts:
            raise ValueError(f"staged receipt unavailable: {source_kind}/{source_key}")
        values = self.receipts[key]
        if values["source_url"] != url:
            raise ValueError(f"staged URL mismatch for {source_kind}/{source_key}")
        receipt = FetchReceipt(
            source_kind=values["source_kind"],
            source_key=values["source_key"],
            source_url=values["source_url"],
            requested_at_utc=values["requested_at_utc"],
            received_at_utc=values["received_at_utc"],
            status_code=int(values["status_code"]),
            payload_bytes=int(values["payload_bytes"]),
            payload_sha256=values["payload_sha256"],
            parser_version=values["parser_version"],
        )
        suffix = ".html" if source_kind == "issue_page" else ".js"
        path = (
            self.staging_root
            / "raw"
            / source_kind
            / f"{source_key}.{receipt.payload_sha256}{suffix}"
        )
        payload = path.read_bytes()
        if len(payload) != receipt.payload_bytes:
            raise ValueError(f"staged payload size mismatch: {path}")
        if hashlib.sha256(payload).hexdigest() != receipt.payload_sha256:
            raise ValueError(f"staged payload hash mismatch: {path}")
        return payload, receipt


def _write_raw(root: Path, receipt: FetchReceipt, payload: bytes) -> Path:
    suffix = ".html" if receipt.source_kind == "issue_page" else ".js"
    target = root / "raw" / receipt.source_kind / f"{receipt.source_key}.{receipt.payload_sha256}{suffix}"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != receipt.payload_sha256:
            raise ValueError(f"existing raw payload hash mismatch: {target}")
        return target
    publication.atomic_write_bytes(target, payload)
    return target


def probe_issue(
    client: ProbeClient,
    issue_code: str,
    expected: pd.DataFrame,
    staging_root: Path,
    *,
    titan_samples: int = 1,
) -> tuple[
    ProbeResult,
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Probe one issue page and a bounded number of Titan match histories."""

    issue_code = str(issue_code)
    expected_issue = expected.loc[expected.issue_code.eq(issue_code)].copy()
    expected_slots = set(expected_issue.match_idx.astype(int))
    payload, issue_receipt = client.fetch(
        "issue_page", issue_code, ISSUE_URL.format(issue=issue_code)
    )
    _write_raw(staging_root, issue_receipt, payload)
    text = payload.decode("utf-8", errors="replace")
    rows = parse_cp_issue_html(text, issue_code)
    source_slots = {int(row["match_idx"]) for row in rows}

    receipts: list[dict[str, Any]] = [asdict(issue_receipt)]
    titan_rows: list[dict[str, Any]] = []
    sampled = rows[: max(0, titan_samples)]
    successes = 0
    complete_triplets = 0
    for row in sampled:
        provider_id = str(row["provider_match_id"])
        try:
            titan_payload, titan_receipt = client.fetch(
                "titan_1x2", provider_id, TITAN_URL.format(provider_match_id=provider_id)
            )
            _write_raw(staging_root, titan_receipt, titan_payload)
            receipts.append(asdict(titan_receipt))
            meta, odds, _ = parse_titan_1x2_text(
                titan_payload.decode("utf-8-sig", errors="replace")
            )
            valid = [
                item
                for item in odds
                if item[3] in {"initial", "10h", "1h"}
                and all(value is not None for value in item[4:7])
            ]
            complete_triplets += len(valid)
            successes += 1
            titan_rows.append(
                {
                    "issue_code": issue_code,
                    "match_idx": int(row["match_idx"]),
                    "provider_match_id": provider_id,
                    "kickoff_ts": meta.get("kickoff"),
                    "complete_initial_triplets": sum(item[3] == "initial" for item in valid),
                    "complete_10h_triplets": sum(item[3] == "10h" for item in valid),
                    "complete_1h_triplets": sum(item[3] == "1h" for item in valid),
                    "status": "AVAILABLE",
                }
            )
        except (requests.RequestException, ValueError) as exc:
            titan_rows.append(
                {
                    "issue_code": issue_code,
                    "match_idx": int(row["match_idx"]),
                    "provider_match_id": provider_id,
                    "kickoff_ts": None,
                    "complete_initial_triplets": 0,
                    "complete_10h_triplets": 0,
                    "complete_1h_triplets": 0,
                    "status": f"UNAVAILABLE:{type(exc).__name__}",
                }
            )

    local_only = expected_slots - source_slots
    source_only = source_slots - expected_slots
    status = "AUTHORITATIVE_ISSUE_MEMBERSHIP_AVAILABLE" if rows else "SOURCE_UNAVAILABLE"
    result = ProbeResult(
        issue_code=issue_code,
        local_candidate_fixture_count=len(expected_slots),
        source_fixture_count=len(source_slots),
        matched_slot_count=len(expected_slots & source_slots),
        local_only_slot_count=len(local_only),
        source_only_slot_count=len(source_only),
        issue_payload_sha256=issue_receipt.payload_sha256,
        sampled_titan_match_count=len(sampled),
        sampled_titan_success_count=successes,
        sampled_complete_triplets=complete_triplets,
        status=status,
    )
    source_rows = [
        {
            "issue_code": issue_code,
            "match_idx": int(row["match_idx"]),
            "provider_match_id": str(row["provider_match_id"]),
            "league": row.get("league"),
            "home": row.get("home"),
            "away": row.get("away"),
            "kickoff_ts": None,
            "issue_deadline_ts": row.get("issue_deadline_ts"),
            "native_handicap_line": row.get("handicap_line"),
            "present_in_local_candidate": int(row["match_idx"]) in expected_slots,
        }
        for row in rows
    ]
    return result, receipts, source_rows, titan_rows
