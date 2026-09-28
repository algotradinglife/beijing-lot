"""Offline parsing and evidence reconstruction for the #493 Nowscore 3in1 probe.

These functions read already-saved raw bytes, so they cost no HTTP attempts.
Importing this module performs no I/O.

Two rules drive the design:

* a reconstructed ledger must label every field by how it was obtained, and must
  leave unrecoverable fields unknown rather than filling them in;
* a diagnostic timestamp carries its assumptions (year, timezone) in the field
  name itself, so no consumer can read it as verified UTC.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARKETS = ("asian_handicap", "over_under", "euro_1x2")
YEAR_ASSUMED = 2026
TZ_ASSUMED = "UTC+8"
CST = timezone(timedelta(hours=8))
UNKNOWN = None


# --- HTML parsing -------------------------------------------------------------

def parse_market_tables(html: str) -> dict[str, list[list[str]]]:
    """Return the three market tables as header-included cell rows."""
    tables = re.findall(r"<table.*?</table>", html, re.S | re.I)
    parsed: dict[str, list[list[str]]] = {}
    for name, table in zip(MARKETS, tables):
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I):
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                     for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
            if cells and any(cells):
                rows.append(cells)
        parsed[name] = rows
    return parsed


def parse_company_links(html: str) -> list[tuple[str, str]]:
    """Return (company_id, masked_label) for the page's company selector."""
    block = re.search(r'<ul class="tg3" id="ulcompany">(.*?)</ul>', html, re.S)
    if not block:
        return []
    return re.findall(r'companyid=(\d+)&id=\d+" id="net\d+"><span>(.*?)</span>',
                      block.group(1), re.S)


def selected_company_id(html: str) -> str | None:
    """The page anchors its default selection by assigning the selected class."""
    match = re.search(
        r'getElementById\("net(\d+)"\)\.className\s*=\s*"selected"', html)
    return match.group(1) if match else None


def parse_change_stamp(cells: list[str], assumed_year: int = YEAR_ASSUMED) -> str | None:
    """The change column is 'MM-DD HH:MM' with no year and no timezone.

    The returned string is therefore an ASSUMED local time, never a verified UTC
    instant; the caller must keep that qualification.
    """
    for cell in cells:
        match = re.search(r"(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", cell)
        if match:
            return (f"{assumed_year}-{match.group(1)}-{match.group(2)} "
                    f"{match.group(3)}:{match.group(4)}")
    return None


# --- diagnostics --------------------------------------------------------------

def last_before(rows: list[list[str]], cutoff: str) -> tuple[str | None, list[str] | None]:
    """Latest pre-match row strictly before the cutoff, in assumed local time."""
    prematch = [(parse_change_stamp(r), r) for r in rows[1:]]
    prematch = [(t, r) for t, r in prematch if t and "滚" not in r and t < cutoff]
    if not prematch:
        return None, None
    stamp, row = max(prematch, key=lambda x: x[0])
    return stamp, row


def build_diagnostic_rows(views: dict[str, tuple[str, str]], raw_dir: Path,
                          epoch_local: str) -> list[dict]:
    """One diagnostic row per (view, market). Assumptions live in field names."""
    rows = []
    for raw_name, (view, note) in views.items():
        html = (raw_dir / f"{raw_name}.html").read_text("utf-8", "replace")
        tables = parse_market_tables(html)
        links = parse_company_links(html)
        for market in MARKETS:
            market_rows = tables.get(market, [])
            stamp, row = last_before(market_rows, epoch_local)
            prematch = [t for t, r in
                        ((parse_change_stamp(r), r) for r in market_rows[1:])
                        if t and "滚" not in r]
            rows.append({
                "view": view,
                "view_note": note,
                "market": market,
                "raw_file": f"raw/{raw_name}.html",
                "rows_total": max(0, len(market_rows) - 1),  # exclude the header row
                "rows_prematch": len(prematch),
                f"rows_strictly_before_epoch_ASSUMED_{TZ_ASSUMED}_YEAR_{YEAR_ASSUMED}":
                    sum(1 for t in prematch if t < epoch_local),
                f"last_before_epoch_ASSUMED_{TZ_ASSUMED}_YEAR_{YEAR_ASSUMED}":
                    stamp or "",
                "last_before_epoch_values": " | ".join(row[2:5]) if row else "",
                "companies_listed": len(links),
                "average_label_present": int("平均" in html),
                "tz_status": "TZ_UNDECIDED_DIAGNOSTIC_ONLY",
                f"year_status_ASSUMED_{YEAR_ASSUMED}_DIAGNOSTIC_ONLY": True,
                "availability_evidence": "NOT_PROVEN",
            })
    return rows


def write_diagnostics_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# --- ledger reconstruction ----------------------------------------------------

def file_mtime_utc(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def rebuild_request_ledger(raw_dir: Path, surviving_manifest: dict | None,
                           urls: dict[str, str],
                           base_run_wall_sec: float = 0.32) -> tuple[list[dict], dict]:
    """Reconstruct the attempt ledger, labelling every field's provenance.

    A field with no surviving evidence is left unknown; it is never filled in
    with a plausible default.
    """
    recorded = {}
    if surviving_manifest:
        for entry in surviving_manifest.get("requests", []):
            recorded[entry["label"]] = entry

    ledger = []
    for label, url in urls.items():
        rel = f"raw/{label}.html"
        path = raw_dir / rel
        body = path.read_bytes()
        ended = file_mtime_utc(path)
        entry = recorded.get(label)
        # Only a surviving manifest entry can attest status, duration or jar.
        ledger.append({
            "label": label,
            "kind": "outcome",
            "attempt_id": f"reconstructed-{label}",
            "url": url,
            "url_provenance": "recorded",
            "http_status": entry["http_status"] if entry else UNKNOWN,
            "http_status_provenance": "recorded" if entry else "missing",
            "hop": UNKNOWN,
            "hop_provenance": "missing_saved_bodies_cannot_prove_no_redirect",
            "redirect_to": UNKNOWN,
            "rejected_redirect": UNKNOWN,
            "started_at": (iso_utc(ended - timedelta(milliseconds=entry["duration_ms"]))
                           if entry else UNKNOWN),
            "started_at_provenance": ("inferred_from_recorded_duration" if entry
                                      else "missing"),
            "ended_at": iso_utc(ended),
            "ended_at_provenance": "observed_file_mtime",
            "duration_ms": entry["duration_ms"] if entry else UNKNOWN,
            "duration_ms_provenance": "recorded" if entry else "missing",
            "body_bytes": len(body),
            "body_bytes_provenance": "observed_file_size",
            "sha256": hashlib.sha256(body).hexdigest(),
            "sha256_provenance": "observed_file_content",
            "raw_file": rel,
            "error": entry.get("error") if entry else UNKNOWN,
            "error_provenance": "recorded" if entry else "missing",
            # Each entry carries its own jar identity; a missing one stays unknown
            # rather than borrowing a neighbour's.
            "cookie_jar_id": (entry.get("cookie_jar_id")
                              if entry and entry.get("cookie_jar_id") else UNKNOWN),
            "cookie_jar_id_provenance": ("recorded"
                                         if entry and entry.get("cookie_jar_id")
                                         else "missing"),
        })

    base_path = raw_dir / "raw/base_no_company.html"
    ends = [file_mtime_utc(raw_dir / r["raw_file"]) for r in ledger]
    base_end, last_end = file_mtime_utc(base_path), max(ends)
    lower_bound = (last_end - base_end).total_seconds()
    inferred = (last_end - (base_end - timedelta(seconds=base_run_wall_sec))).total_seconds()
    provenance = {
        "schema": "n7_493_3in1_probe_ledger_provenance_v1",
        "reason": ("the base invocation's manifest entry was overwritten by the "
                   "follow invocation, so the original per-process manifests are "
                   "incomplete"),
        # Only top-level requests are reconstructed. Redirect occurrence is
        # UNKNOWN, so the per-hop attempt count is unproven and the remaining
        # budget cannot be computed from this ledger; it is reported as such
        # rather than as an authorised remainder.
        "top_level_requests_reconstructed": len(ledger),
        "top_level_requests_authorised_max": 10,
        "hop_attempts_total": "UNVERIFIED",
        "hop_attempts_reason": (
            "redirect_occurrence is UNKNOWN: the saved response bodies cannot prove "
            "no redirect occurred, and one hop or several are both consistent with "
            f"the {len(ledger)} reconstructed top-level records"),
        "remaining_budget": "NOT_COMPUTABLE_TREATED_AS_ZERO",
        "remaining_budget_reason": (
            "the budget is consumed per hop attempt; the numerator is unproven, so "
            "no budget may be treated as still available"),
        "sum_of_recorded_durations_ms": sum(
            r["duration_ms"] for r in ledger if r["duration_ms"] is not UNKNOWN),
        "sum_of_recorded_durations_note": (
            "excludes the base request, whose duration is missing; this is NOT the "
            "wall clock and must not be reported as such"),
        "wall_sec_lower_bound": round(lower_bound, 6),
        "wall_sec_lower_bound_basis": ("base body-write mtime -> last body-write "
                                       "mtime; both observed, no inference. Body-write "
                                       "times are not HTTP completion times."),
        "wall_sec_inferred": round(inferred, 6),
        "wall_sec_inferred_basis": (f"assumes the base attempt started "
                                    f"{base_run_wall_sec}s before its body mtime; "
                                    "INFERRED, not measured"),
        "wall_sec_authorised_max": 300.0,
        "upper_limit_compliance": "UNVERIFIED",
        "upper_limit_compliance_reason": (
            "the first attempt's start is missing, so completion within 300 s cannot "
            "be proven from the surviving evidence; the lower bound does not bound "
            "the start"),
        "serial_interval_authorised_min_sec": 2.0,
        "serial_interval_compliance": "UNVERIFIED",
        "serial_interval_evidence": (
            "the surviving evidence is two body-write mtimes ~1.87 s apart, which "
            "cannot establish a >=2 s completion-to-start interval; the attempts came "
            "from separate invocations and no single budget enforced spacing"),
        "redirect_occurrence": "UNKNOWN",
        "hop_accounting_evidence": (
            "UNKNOWN: saved response bodies cannot prove that no redirect occurred, "
            "and hop accounting was never exercised under the current implementation"),
        "gaps": [
            "base http_status: missing",
            "base duration and start: missing",
            "hop / redirect_to / error for every attempt: missing",
            "base cookie_jar_id: missing",
        ],
    }
    return ledger, provenance


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_ledger(ledger: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in ledger:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
