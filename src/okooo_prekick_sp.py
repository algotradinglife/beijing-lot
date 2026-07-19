"""Parse and freeze the legacy Okooo pre-kick SP pages without future leakage."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bs4 import BeautifulSoup


MARKET_PATHS = {
    "correct_score": "cs",
    "half_full": "htft",
    "asian_handicap": "ah",
    "over_under": "overunder",
}
PROVIDER_NAMES = {"14": "william_hill"}
PROVIDER_LABELS = {"14": "威廉希尔"}
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "results/data_collection/okooo_prekick_sp_v1"
RELATIVE_TIME_RE = re.compile(
    r"赛前\s*(?:(?P<days>\d+)\s*天)?\s*(?:(?P<hours>\d+)\s*(?:小时|时))?"
    r"\s*(?:(?P<minutes>\d+)\s*分)?"
)
NUMBER_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
META_HEADER_RE = re.compile(r"时间|更新|变化|日期|公司|序号|状态")


class OkoooParseError(ValueError):
    """Raised when an Okooo page cannot be trusted as a historical SP page."""


@dataclass(frozen=True)
class IssueMatch:
    issue: str
    match_idx: int
    match_id: str
    league: str
    kickoff_text: str
    home: str
    away: str


@dataclass(frozen=True)
class HistoryRow:
    row_order: int
    relative_label: str
    minutes_before_kickoff: int
    cells: tuple[str, ...]
    headers: tuple[str, ...]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _soup(payload: bytes) -> BeautifulSoup:
    return BeautifulSoup(payload.decode("utf-8", errors="replace"), "html.parser")


def reject_block_page(payload: bytes, source_url: str = "") -> None:
    soup = _soup(payload)
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = " ".join(soup.get_text(" ", strip=True).split())
    if title in {"405", "403"} or "访问的URL有可能对网站造成安全威胁" in text:
        raise OkoooParseError(f"okooo_auth_required_or_waf_blocked: {source_url or title}")
    if title == "登录注册" or ("密码登录" in text and "手机登录" in text):
        raise OkoooParseError(f"okooo_login_required: {source_url or title}")
    if "访问频率" in text or "验证码" in text:
        raise OkoooParseError(f"okooo_rate_limited_or_challenged: {source_url}")


def parse_issue_page(payload: bytes, issue: str) -> list[IssueMatch]:
    reject_block_page(payload)
    soup = _soup(payload)
    matches: list[IssueMatch] = []
    for node in soup.select("tr[matchid]"):
        match_id = str(node.get("matchid") or "").strip()
        first_cell = node.select_one("td.graytx")
        index_node = first_cell.select_one("span") if first_cell else None
        index_text = index_node.get_text(" ", strip=True) if index_node else ""
        if not match_id.isdigit() or not index_text.isdigit():
            continue
        gray_cells = node.select("td.graytx")
        kickoff_text = gray_cells[1].get_text(" ", strip=True) if len(gray_cells) > 1 else ""
        league_node = node.select_one(".ssname")
        home_node = node.select_one(".ctrl_homename")
        away_node = node.select_one(".ctrl_awayname")
        matches.append(
            IssueMatch(
                issue=str(issue),
                match_idx=int(index_text),
                match_id=match_id,
                league=league_node.get_text(" ", strip=True) if league_node else "",
                kickoff_text=kickoff_text,
                home=home_node.get_text(" ", strip=True) if home_node else "",
                away=away_node.get_text(" ", strip=True) if away_node else "",
            )
        )
    matches.sort(key=lambda item: item.match_idx)
    if not matches:
        raise OkoooParseError("okooo_issue_page_has_no_matches")
    if len({item.match_idx for item in matches}) != len(matches):
        raise OkoooParseError("okooo_issue_page_has_duplicate_match_idx")
    return matches


def parse_minutes_before_kickoff(label: str) -> int | None:
    match = RELATIVE_TIME_RE.search(label.replace("：", ":"))
    if not match or not any(match.group(name) for name in ("days", "hours", "minutes")):
        return None
    return (
        int(match.group("days") or 0) * 24 * 60
        + int(match.group("hours") or 0) * 60
        + int(match.group("minutes") or 0)
    )


def _unique_headers(values: Sequence[str]) -> tuple[str, ...]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for index, raw in enumerate(values, start=1):
        base = " ".join(raw.split()) or f"field_{index:03d}"
        seen[base] = seen.get(base, 0) + 1
        result.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return tuple(result)


def _candidate_headers(table: Any, width: int) -> tuple[str, ...]:
    candidates: list[tuple[str, ...]] = []
    for row in table.select("tr"):
        cells = row.select("th,td")
        values = tuple(cell.get_text(" ", strip=True) for cell in cells)
        if len(values) == width and row.select("th"):
            candidates.append(_unique_headers(values))
    return candidates[-1] if candidates else tuple(f"field_{index:03d}" for index in range(1, width + 1))


def parse_history_page(payload: bytes, source_url: str = "") -> list[HistoryRow]:
    reject_block_page(payload, source_url)
    soup = _soup(payload)
    candidates: list[tuple[Any, list[tuple[int, tuple[str, ...], str, int]]]] = []
    for table in soup.select("table"):
        rows: list[tuple[int, tuple[str, ...], str, int]] = []
        for order, node in enumerate(table.select("tr")):
            cells = tuple(cell.get_text(" ", strip=True) for cell in node.select("td"))
            relative = next((value for value in cells if parse_minutes_before_kickoff(value) is not None), "")
            minutes = parse_minutes_before_kickoff(relative)
            if cells and minutes is not None:
                rows.append((order, cells, relative, minutes))
        if rows:
            candidates.append((table, rows))
    if not candidates:
        raise OkoooParseError(f"okooo_history_table_missing: {source_url}")
    table, raw_rows = max(candidates, key=lambda item: len(item[1]))
    widths = {len(item[1]) for item in raw_rows}
    if len(widths) != 1:
        raise OkoooParseError(f"okooo_history_row_width_changed: {sorted(widths)}")
    width = widths.pop()
    headers = _candidate_headers(table, width)
    return [
        HistoryRow(
            row_order=order,
            relative_label=relative,
            minutes_before_kickoff=minutes,
            cells=cells,
            headers=headers,
        )
        for order, cells, relative, minutes in raw_rows
    ]


def select_asof_10h(rows: Sequence[HistoryRow], target_minutes: int = 600) -> HistoryRow:
    eligible = [row for row in rows if row.minutes_before_kickoff >= target_minutes]
    if not eligible:
        raise OkoooParseError("no_history_row_at_or_before_10h")
    return min(eligible, key=lambda row: (row.minutes_before_kickoff, row.row_order))


def outcome_values(row: HistoryRow) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, (header, value) in enumerate(zip(row.headers, row.cells, strict=True), start=1):
        if value == row.relative_label or META_HEADER_RE.search(header):
            continue
        cleaned = value.replace("↑", "").replace("↓", "").replace("→", "").strip()
        numeric = float(cleaned) if NUMBER_RE.fullmatch(cleaned) else None
        result.append(
            {
                "field_index": index,
                "outcome_label": header,
                "raw_value": cleaned,
                "sp": numeric,
            }
        )
    return result


def history_url(match_id: str, market: str, provider_code: str = "14") -> str:
    try:
        path = MARKET_PATHS[market]
    except KeyError as exc:
        raise ValueError(f"unsupported Okooo market: {market}") from exc
    return f"https://www.okooo.com/soccer/match/{match_id}/{path}/change/{provider_code}/"


def issue_url(issue: str) -> str:
    return f"https://www.okooo.com/livecenter/danchang/?date={issue}"


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_bundle(path: Path) -> dict[str, Any]:
    root = path.expanduser().resolve()
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        raise OkoooParseError(f"SHA256SUMS missing: {root}")
    entries: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise OkoooParseError(f"invalid SHA256SUMS line: {line!r}") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or Path(name).is_absolute() or ".." in Path(name).parts:
            raise OkoooParseError(f"invalid SHA256SUMS entry: {line!r}")
        target = root / name
        if not target.is_file() or sha256_file(target) != digest:
            raise OkoooParseError(f"checksum mismatch: {target}")
        entries[name] = digest
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "okooo_prekick_sp_bundle_v1":
        raise OkoooParseError("unsupported Okooo bundle schema")
    return {"status": "valid", "files": len(entries), "sha256s_sha256": sha256_file(sums)}


def publish_bundle(
    *,
    issue: str,
    fetched_at_utc: str,
    raw_pages: Mapping[str, bytes],
    matches: Sequence[IssueMatch],
    history: Sequence[Mapping[str, Any]],
    selected: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
    output_root: Path = DEFAULT_ROOT,
    provider_code: str = "14",
    authentication_mode: str = "anonymous",
) -> dict[str, Any]:
    fetched = datetime.fromisoformat(fetched_at_utc.replace("Z", "+00:00"))
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    raw_digest = hashlib.sha256()
    for name, payload in sorted(raw_pages.items()):
        raw_digest.update(name.encode("utf-8"))
        raw_digest.update(payload)
    identity = f"{issue}|{fetched.astimezone(timezone.utc).isoformat()}|{raw_digest.hexdigest()}"
    run_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    final = output_root.expanduser().resolve() / str(issue) / run_id
    manifest = {
        "schema_version": "okooo_prekick_sp_bundle_v1",
        "issue": str(issue),
        "run_id": run_id,
        "fetched_at_utc": fetched.astimezone(timezone.utc).isoformat(),
        "provider_code": provider_code,
        "provider_name": PROVIDER_NAMES.get(provider_code, "unknown"),
        "provider_label": PROVIDER_LABELS.get(provider_code, "未知公司"),
        "market_data_class": "bookmaker_odds_history",
        "official_beidan_sp": False,
        "authentication_mode": authentication_mode,
        "match_rows": len(matches),
        "history_rows": len(history),
        "selected_10h_rows": len(selected),
        "failure_rows": len(failures),
        "status": "complete" if not failures else "partial_blocked",
        "research_policy": {
            "execution_enabled": False,
            "roi_authorized": False,
            "static_or_terminal_backfill_allowed": False,
            "selected_rule": "minimum minutes_before_kickoff >= 600",
        },
    }
    if final.exists():
        verification = verify_bundle(final)
        return {**manifest, "output_dir": str(final), "verification": verification}
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{run_id}.tmp-", dir=final.parent))
    try:
        raw_root = stage / "raw"
        raw_root.mkdir()
        for name, payload in raw_pages.items():
            target = raw_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        match_rows = [asdict(item) for item in matches]
        _write_csv(
            stage / "matches.csv",
            match_rows,
            ("issue", "match_idx", "match_id", "league", "kickoff_text", "home", "away"),
        )
        history_fields = (
            "issue", "match_idx", "match_id", "market", "source_url", "row_order",
            "relative_label", "minutes_before_kickoff", "field_index", "outcome_label", "raw_value", "sp",
        )
        _write_csv(stage / "history.csv", history, history_fields)
        _write_csv(stage / "selected_10h.csv", selected, history_fields)
        failure_fields = ("issue", "match_idx", "match_id", "market", "source_url", "reason")
        _write_csv(stage / "failures.csv", failures, failure_fields)
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        payloads = sorted(path for path in stage.rglob("*") if path.is_file())
        (stage / "SHA256SUMS").write_text(
            "".join(f"{sha256_file(path)}  {path.relative_to(stage).as_posix()}\n" for path in payloads),
            encoding="utf-8",
        )
        stage.rename(final)
        parent_fd = os.open(final.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    verification = verify_bundle(final)
    return {**manifest, "output_dir": str(final), "verification": verification}
