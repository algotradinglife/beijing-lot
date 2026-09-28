#!/usr/bin/env python3
"""Capture one strict 500 issue-slot to Nowscore provider-ID mapping receipt."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scrape_500_bjdc import DEFAULT_UA as UA_500, TRADE_URL, decode_html, parse_issue_rows  # noqa: E402
from scripts.scrape_nowscore_bjdc import DEFAULT_UA as UA_NOWSCORE, NOWSCORE_URL  # noqa: E402
from src.titan_clean.historical_id_map import HistoricalIdMapError, HistoricalIdMapStore, nowscore_void_slots, parse_nowscore_provider_ids  # noqa: E402

PARSER_VERSION = "historical_id_map_v1"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, user_agent: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def nowscore_team_pairs(payload: bytes) -> dict[int, tuple[str, str, str]]:
    """Return Nowscore slot -> (home, away, deadline_iso) from the matrix."""
    text = payload.decode("utf-8", errors="replace")
    matrix: dict[int, dict[int, str]] = {}
    for row, field, value in re.findall(r"M\[(\d+)\]\[(\d+)\]\s*=\s*(.*?);", text, flags=re.S):
        matrix.setdefault(int(row), {})[int(field)] = value.strip()
    pairs: dict[int, tuple[str, str, str]] = {}
    for fields in matrix.values():
        if 16 in fields and 17 in fields and 20 in fields:
            deadline = ""
            match = re.search(
                r"new\s+Date\((\d{4}),(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2})\)",
                fields.get(3, ""),
            )
            if match:
                year, month, day, hour, minute, _ = map(int, match.groups())
                deadline = f"{year}-{month + 1:02d}-{day:02d} {hour:02d}:{minute:02d}"
            pairs[int(fields[16])] = (
                fields[17].strip('"'),
                fields[20].strip('"'),
                deadline,
            )
    return pairs


def _row_date(value: object) -> str:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else ""


def resolve_alignment(rows_500: list[dict[str, object]], ns_pairs: dict[int, tuple[str, str, str]]) -> dict[int, int]:
    """Return a 500-slot to Nowscore-slot map, verified by team names.

    Same-slot alignment is preferred. When the same team pair appears more than
    once in the issue (e.g. same clubs on different dates), each duplicate pair
    must also agree on the deadline date, otherwise alignment fails closed.
    """
    by_slot = {int(row["match_idx"]): row for row in rows_500 if row["match_idx"]}
    exact_lookup: dict[tuple[str, str], list[int]] = {}
    for ns_slot, (home, away, _) in ns_pairs.items():
        exact_lookup.setdefault((home, away), []).append(ns_slot)

    def same_slot_ok() -> bool:
        for slot, row in by_slot.items():
            if slot not in ns_pairs:
                return False
            home, away, _ = ns_pairs[slot]
            if row["home"] == home and row["away"] == away:
                continue
            # Translation difference: the 500 team pair has no verbatim match
            # anywhere else in Nowscore, so the same slot is the same fixture
            # under a different translation. A verbatim match elsewhere means
            # the row is misaligned (reschedule/compression) and fails closed.
            elsewhere = [s for s in exact_lookup.get((row["home"], row["away"]), []) if s != slot]
            if elsewhere:
                return False
        return True

    if not same_slot_ok():
        # Exact-remap pass: a slot whose 500 team pair exists verbatim at a
        # single other Nowscore slot is a compressed/renumbered row; remap it.
        remapped: dict[int, int] = {}
        for slot, row in by_slot.items():
            elsewhere = [s for s in exact_lookup.get((row["home"], row["away"]), []) if s != slot]
            if len(elsewhere) == 1:
                remapped[slot] = elsewhere[0]
            elif len(elsewhere) > 1:
                raise HistoricalIdMapError(f"ambiguous exact match for 500 slot {slot}")
            else:
                remapped[slot] = slot
        if len(set(remapped.values())) != len(remapped):
            raise HistoricalIdMapError("exact-remap targets collide")
        if all(
            slot in ns_pairs
            and (ns_pairs[remapped[slot]][0] == row["home"] and ns_pairs[remapped[slot]][1] == row["away"]
                 or (remapped[slot] == slot and exact_lookup.get((row["home"], row["away"]), [slot]) == [slot]))
            for slot, row in by_slot.items()
        ):
            return remapped
        ns_items = sorted(ns_pairs.items())
        mapping: dict[int, int] = {}
        idx = 0
        for slot in sorted(by_slot):
            row = by_slot[slot]
            found = False
            while idx < len(ns_items):
                ns_slot, (home, away, _) = ns_items[idx]
                idx += 1
                if row["home"] == home and row["away"] == away:
                    mapping[slot] = ns_slot
                    found = True
                    break
            if not found:
                raise HistoricalIdMapError(f"no ordered team-name match for 500 slot {slot}")
        return mapping

    team_count: dict[tuple[str, str], int] = {}
    for row in by_slot.values():
        key = (row["home"], row["away"])
        team_count[key] = team_count.get(key, 0) + 1
    duplicate_teams = {key for key, count in team_count.items() if count > 1}
    if duplicate_teams:
        # Nowscore matrix field 3 (deadline) is unreliable on legacy 6-digit
        # issues (it may hold a previous match date), so no date gate is used.
        # A recurring team pair is mapped by same slot plus translation
        # tolerance (no verbatim match elsewhere).
        for slot, row in by_slot.items():
            if (row["home"], row["away"]) not in duplicate_teams:
                continue
            home, away, _ = ns_pairs[slot]
            if row["home"] != home or row["away"] != away:
                elsewhere = [s for s in exact_lookup.get((row["home"], row["away"]), []) if s != slot]
                if elsewhere:
                    raise HistoricalIdMapError(f"duplicate-team slot mismatch at {slot}")
    return {slot: slot for slot in by_slot}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--capture-key", required=True)
    parser.add_argument(
        "--resolve-conflict", action="append", default=[],
        metavar="PROVIDER=SLOT",
        help="Titan-verified provider-to-slot resolution for a duplicate-provider group (repeatable)",
    )
    args = parser.parse_args()
    resolution: dict[str, int] = {}
    for item in args.resolve_conflict:
        provider, _, slot = item.partition("=")
        if not provider.isdecimal() or not slot.isdecimal():
            parser.error(f"invalid --resolve-conflict value: {item}")
        resolution[provider] = int(slot)

    issue = args.issue
    url_500 = f"{TRADE_URL}?expect={issue}"
    raw_500 = fetch(url_500, UA_500)
    rows_500 = parse_issue_rows(issue, decode_html(raw_500), fetched_at=now_utc())
    candidates_500 = tuple((int(row["match_idx"]), int(row["fid"])) for row in rows_500 if row["match_idx"] and row["fid"])

    url_nowscore = NOWSCORE_URL.format(issue=issue)
    raw_nowscore = fetch(url_nowscore, UA_NOWSCORE)
    candidates_nowscore = parse_nowscore_provider_ids(raw_nowscore, issue_code=issue)
    void_slots = nowscore_void_slots(raw_nowscore, issue_code=issue)
    slot_map = resolve_alignment(rows_500, nowscore_team_pairs(raw_nowscore))

    store = HistoricalIdMapStore.open(args.data_root)
    try:
        coverage_batch = f"{args.capture_key}:500:{issue}"
        nowscore_batch = f"{args.capture_key}:nowscore:{issue}"
        store.record_500_coverage(
            batch_id=coverage_batch, issue_code=issue, source_url=url_500, payload=raw_500,
            trusted_received_at_utc=now_utc(), parser_version=PARSER_VERSION, rows=candidates_500,
        )
        store.record_nowscore_mapping(
            coverage_500_batch_id=coverage_batch, batch_id=nowscore_batch, issue_code=issue,
            source_url=url_nowscore, payload=raw_nowscore, trusted_received_at_utc=now_utc(),
            parser_version=PARSER_VERSION, rows=candidates_nowscore, conflict_resolution=resolution,
            slot_map=slot_map, void_nowscore_slots=void_slots,
        )
        isolated = [row[:2] for row in store.conflicts() if row[0] == issue]
        print({"issue": issue, "mapped_slots": len(candidates_500), "mapping_count": len(store.mappings()), "isolated_slots": isolated})
    finally:
        store.close()


if __name__ == "__main__":
    main()
