"""Parse Nowscore's timestamped Beijing-lottery SP history pages."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

from bs4 import BeautifulSoup

from src.multimarket_p0 import HKT


TYPEID_MARKETS = {
    5: ("handicap_3way", ("3", "1", "0")),
    6: ("total_goals", ("0", "1", "2", "3", "4", "5", "6", "7+")),
    7: ("upper_lower_odd_even", ("upper_odd", "upper_even", "lower_odd", "lower_even")),
    8: (
        "correct_score",
        (
            "home_other", "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2",
            "draw_other", "0:0", "1:1", "2:2", "3:3", "away_other", "0:1", "0:2", "1:2",
            "0:3", "1:3", "2:3", "0:4", "1:4", "2:4",
        ),
    ),
    9: ("half_full", ("3-3", "3-1", "3-0", "1-3", "1-1", "1-0", "0-3", "0-1", "0-0")),
}
TYPEID_LABELS = {
    5: ("胜", "平", "负"),
    6: ("0球", "1球", "2球", "3球", "4球", "5球", "6球", "7+球"),
    7: ("上+单", "上+双", "下+单", "下+双"),
    8: (
        "胜其他", "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2",
        "平其他", "0:0", "1:1", "2:2", "3:3", "负其他", "0:1", "0:2", "1:2", "0:3",
        "1:3", "2:3", "0:4", "1:4", "2:4",
    ),
    9: ("胜-胜", "胜-平", "胜-负", "平-胜", "平-平", "平-负", "负-胜", "负-平", "负-负"),
}
TIME_RE = re.compile(r"^(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$")


class NowscoreHistoryError(ValueError):
    """Raised when an archive page violates its expected contract."""


@dataclass(frozen=True)
class HistoryVector:
    source_ts_hkt: str
    values: tuple[float, ...]


def history_url(issue: str, match_idx: int, typeid: int) -> str:
    if typeid not in TYPEID_MARKETS:
        raise ValueError(f"unsupported Nowscore typeid: {typeid}")
    return f"https://cp.nowscore.com/sp/danchang/{issue}_{match_idx}_{typeid}.html"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def infer_source_time(value: str, kickoff_hkt: datetime) -> datetime:
    match = TIME_RE.fullmatch(value.strip())
    if not match:
        raise NowscoreHistoryError(f"invalid source timestamp: {value!r}")
    month, day, hour, minute = (int(item) for item in match.groups())
    candidates: list[datetime] = []
    for year in (kickoff_hkt.year - 1, kickoff_hkt.year, kickoff_hkt.year + 1):
        try:
            candidates.append(datetime(year, month, day, hour, minute, tzinfo=HKT))
        except ValueError:
            continue
    if not candidates:
        raise NowscoreHistoryError(f"unresolvable source timestamp: {value!r}")
    selected = min(candidates, key=lambda item: abs((item - kickoff_hkt).total_seconds()))
    if selected < kickoff_hkt - timedelta(days=45) or selected > kickoff_hkt + timedelta(days=2):
        raise NowscoreHistoryError(f"source timestamp outside plausible window: {selected.isoformat()}")
    return selected


def parse_history_page(payload: bytes, typeid: int, kickoff_hkt: datetime) -> tuple[tuple[str, ...], list[HistoryVector]]:
    market = TYPEID_MARKETS.get(typeid)
    if market is None:
        raise ValueError(f"unsupported Nowscore typeid: {typeid}")
    soup = BeautifulSoup(payload.decode("utf-8", errors="replace"), "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if "Sp值变化表" not in title:
        raise NowscoreHistoryError(f"unexpected history page title: {title!r}")
    table = soup.find("table")
    if table is None:
        raise NowscoreHistoryError("history table missing")
    rows = table.find_all("tr")
    if not rows:
        raise NowscoreHistoryError("history rows missing")
    headers = tuple(cell.get_text(" ", strip=True) for cell in rows[0].find_all("td"))
    expected_codes = market[1]
    if headers != (*TYPEID_LABELS[typeid], "变化时间") or len(headers) != len(expected_codes) + 1:
        raise NowscoreHistoryError(f"history header mismatch: {headers}")
    vectors: list[HistoryVector] = []
    for node in rows[1:]:
        cells = [cell.get_text(" ", strip=True) for cell in node.find_all("td")]
        if len(cells) != len(headers):
            raise NowscoreHistoryError(f"history row width mismatch: {len(cells)} != {len(headers)}")
        try:
            values = tuple(float(value) for value in cells[:-1])
        except ValueError as exc:
            raise NowscoreHistoryError(f"non-numeric SP row: {cells[:-1]}") from exc
        source_time = infer_source_time(cells[-1], kickoff_hkt)
        vectors.append(HistoryVector(source_time.isoformat(timespec="minutes"), values))
    if not vectors:
        raise NowscoreHistoryError("history page contains no vectors")
    vectors.sort(key=lambda item: item.source_ts_hkt)
    return headers[:-1], vectors


def select_asof(vectors: Sequence[HistoryVector], kickoff_hkt: datetime, hours_before: float = 10.0) -> HistoryVector:
    return select_at(vectors, kickoff_hkt - timedelta(hours=hours_before))


def select_at(vectors: Sequence[HistoryVector], asof_hkt: datetime) -> HistoryVector:
    eligible = [
        vector
        for vector in vectors
        if datetime.fromisoformat(vector.source_ts_hkt) <= asof_hkt and all(value > 1 for value in vector.values)
    ]
    if not eligible:
        raise NowscoreHistoryError("no complete vector at or before asof")
    return max(eligible, key=lambda item: item.source_ts_hkt)


def selected_rows(
    *, issue: str, match_idx: int, typeid: int, kickoff_hkt: datetime, vector: HistoryVector,
    headers: Sequence[str], batch_id: str, source_url: str, asof_hkt: datetime,
    selection_mode: str,
) -> list[dict[str, Any]]:
    market_key, codes = TYPEID_MARKETS[typeid]
    source_ts = datetime.fromisoformat(vector.source_ts_hkt)
    return [
        {
            "issue": issue,
            "match_id": f"{issue}_{match_idx:03d}",
            "match_idx": match_idx,
            "market_key": market_key,
            "typeid": typeid,
            "outcome_code": code,
            "outcome_label": label,
            "sp": value,
            "kickoff_hkt": kickoff_hkt.isoformat(),
            "asof_hkt": asof_hkt.isoformat(),
            "minutes_to_kickoff": round((kickoff_hkt - asof_hkt).total_seconds() / 60, 3),
            "source_ts_hkt": vector.source_ts_hkt,
            "source_age_minutes": round((asof_hkt - source_ts).total_seconds() / 60, 3),
            "source_url": source_url,
            "batch_id": batch_id,
            "selection_mode": selection_mode,
            "capture_classification": "third_party_timestamped_archive",
        }
        for code, label, value in zip(codes, headers, vector.values, strict=True)
    ]


def manifest_policy(
    *, selection_mode: str = "standardized_offset", hours_before: float | None = 10.0,
    asof_hkt: str = "",
) -> dict[str, Any]:
    return {
        "execution_enabled": False,
        "roi_authorized": False,
        "archive_source": "cp.nowscore.com",
        "selection_mode": selection_mode,
        "hours_before_kickoff": hours_before,
        "asof_hkt": asof_hkt,
        "selection_rule": (
            "latest complete source vector at or before the segment/decision freeze timestamp"
            if selection_mode in {"segment_freeze", "explicit_asof"}
            else "latest complete source vector at or before each kickoff-relative offset"
        ),
        "fetched_after_event_allowed": True,
        "classification": "third_party_timestamped_archive",
    }


def verify_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "nowscore_bjdc_sp_history_v1":
        raise NowscoreHistoryError("unsupported manifest schema")
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        raise NowscoreHistoryError("manifest policy missing")
    if policy.get("execution_enabled") is not False or policy.get("roi_authorized") is not False:
        raise NowscoreHistoryError("manifest safety policy mismatch")
    selection_mode = policy.get("selection_mode")
    legacy_10h = (
        selection_mode is None
        and policy.get("selection_rule") == "latest complete source vector at or before kickoff-10h"
    )
    if not legacy_10h and selection_mode not in {"standardized_offset", "segment_freeze", "explicit_asof"}:
        raise NowscoreHistoryError("manifest selection mode invalid")
    return payload
