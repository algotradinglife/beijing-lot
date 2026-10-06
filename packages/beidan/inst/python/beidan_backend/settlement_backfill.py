"""Cross-source backfill of the old-era SPF handicap (let-ball).

The 2009-2019 settlement archive renders the handicap cell only for some
fixtures: about 57% of old-era SPF rows carry no let-ball at all, so
``expected_option`` cannot be derived from the archive alone. This module fills
that field from an **independent source** rather than inferring it from the
archive's own rendering: ``settlement_500`` (the 500.com settlement table) keys
the same ``(issue, slot)`` and states ``handicap_line`` explicitly, including 0.

Provenance is mandatory: the receipt binds the cross-source file hash, the
counts of rows taken from the archive, from the cross source, and left
unresolved, and the exact rule.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

EMPTY = {"", "--", "-"}


class BackfillError(RuntimeError):
    """The cross source is missing or cannot be trusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CrossSource:
    """A ``(issue_code, issue_slot) -> handicap_line`` cross source with a hash."""

    path: Path
    sha256: str
    values: dict[tuple[str, int], int]

    def handicap(self, issue: str, slot: int) -> int | None:
        return self.values.get((str(issue), int(slot)))


def load_cross_source(path: Path) -> CrossSource:
    """Load the exported 500.com settlement handicap table.

    @raises BackfillError when the file is absent, malformed or empty.
    """
    path = Path(path)
    if not path.is_file():
        raise BackfillError(f"cross source is absent: {path}")
    values: dict[tuple[str, int], int] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"issue_code", "issue_slot", "handicap_line"}
        if not required.issubset(reader.fieldnames or ()):
            raise BackfillError(f"cross source lacks columns {sorted(required)}")
        for row in reader:
            raw = (row["handicap_line"] or "").strip()
            if raw in EMPTY:
                continue
            try:
                line = int(float(raw))
            except ValueError as error:
                raise BackfillError(f"invalid handicap_line {raw!r} for {row['issue_code']}") from error
            values[(str(row["issue_code"]), int(row["issue_slot"]))] = line
    if not values:
        raise BackfillError(f"cross source yielded no rows: {path}")
    return CrossSource(path=path, sha256=sha256_file(path), values=values)


def outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "胜"
    if home_goals < away_goals:
        return "负"
    return "平"


def parse_score(score: str) -> tuple[int, int] | None:
    import re

    match = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", str(score))
    return (int(match.group(1)), int(match.group(2))) if match else None


def backfill_spf(rows: list[dict], cross: CrossSource) -> tuple[list[dict], dict]:
    """Derive SPF ``expected_option`` from the 500.com handicap, archive fallback.

    @param rows Observation rows (dicts) with ``issue``, ``slot``, ``play``,
        ``score``, ``handicap`` and ``archive_result_raw``.
    @param cross The 500.com ``(issue, slot) -> handicap_line`` source, used
        first because it states the handicap explicitly (including 0); the
        archive's rendered handicap is the fallback.
    @return ``(derived_rows, receipt)``; a row keeps ``source=None`` when neither
        source states a handicap, so it is never guessed. Fixtures where both
        sources state a handicap but disagree are listed under
        ``known_disagreements`` — the 500 value is applied and the archive's is
        recorded.
    """
    derived: list[dict] = []
    from_archive = from_cross = unresolved = 0
    contradicted: list[dict] = []
    disagreements: list[dict] = []
    for row in rows:
        if row.get("play") != "spf":
            continue
        # 500.com is the preferred source: it states the handicap explicitly,
        # including 0, while the archive renders it only for some fixtures and
        # leaves the rest blank. The archive is the fallback, never a silent
        # override of an explicit 500 statement.
        cross_line = cross.handicap(row["issue"], row["slot"])
        archive_line = row.get("handicap")
        # Both sources state a handicap for this fixture and they differ. This
        # is a source disagreement in its own right, independent of whether the
        # score parses or whether the derived outcome matches the archive's
        # labelled result, so it is recorded before either check.
        if cross_line is not None and archive_line is not None and cross_line != archive_line:
            disagreements.append({
                "issue": str(row["issue"]), "slot": int(row["slot"]),
                "score": row.get("score"),
                "archive_handicap": archive_line, "cross_handicap": cross_line,
                "applied": cross_line, "applied_source": "cross_source",
                "archive_result": row.get("archive_result_raw"),
            })

        parsed = parse_score(row.get("score"))
        if cross_line is not None:
            line, source = cross_line, "cross_source"
        elif archive_line is not None:
            line, source = archive_line, "archive"
        else:
            line = source = None
        if parsed is None or line is None:
            unresolved += 1
            derived.append({**row, "expected_option_backfilled": None,
                            "handicap_source": source})
            continue
        home, away = parsed
        if source == "archive":
            from_archive += 1
        else:
            from_cross += 1
        expected = outcome(home + line, away)
        archive_result = row.get("archive_result_raw")
        record = {
            **row,
            "handicap_backfilled": line,
            "handicap_source": source,
            "expected_option_backfilled": expected,
        }
        if archive_result in {"胜", "平", "负"} and expected != archive_result:
            contradicted.append({
                "issue": str(row["issue"]), "slot": int(row["slot"]),
                "score": row.get("score"), "handicap": line,
                "archive_result": archive_result, "derived": expected,
                "resolved_by": source,
            })
        derived.append(record)

    receipt = {
        "schema": "beijing_lot_spf_backfill_receipt_v1",
        "rule": ("expected_option = outcome(home_goals + handicap, away_goals); the handicap "
                 "comes from the 500.com settlement table first (an explicit statement, "
                 "including 0), falling back to the archive's rendered handicap when 500 has "
                 "no row; never inferred from the archive's own rendering"),
        "cross_source": {"path": str(cross.path), "sha256": cross.sha256,
                         "rows": len(cross.values)},
        "counts": {
            "total_spf": sum(1 for r in rows if r.get("play") == "spf"),
            "handicap_from_archive": from_archive,
            "handicap_from_cross_source": from_cross,
            "unresolved": unresolved,
        },
        "cross_check": {
            "compared": from_archive + from_cross,
            "contradictions": len(contradicted),
            "examples": contradicted[:10],
        },
        # Explicitly recorded source disagreements: both sources state a
        # handicap for the same fixture and they differ. 500 is used as the data
        # source by policy; the archive's value is recorded, not applied, and no
        # third source in this repository covers these fixtures.
        "known_disagreements": {
            "policy": "500.com is the data source; the archive's differing handicap is recorded, not applied",
            "resolution": "unresolved_pending_third_source",
            "definition": "both sources state a handicap for the fixture and the two values differ",
            "count": len(disagreements),
            "rows": disagreements,
        },
    }
    return derived, receipt
