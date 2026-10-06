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
import os
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


def write_parquet_atomically(table, path: Path, *, compression: str = "snappy") -> dict:
    """Write ``table`` to ``path`` atomically, verifying it reads back first.

    An in-place overwrite of an existing file on the CIFS persistent mount
    produced a truncated Parquet file (zero footer, unreadable by pyarrow) that
    reproduced on every run. The file is therefore written to a sibling
    temporary name, read back and row-counted, and only renamed over the
    destination once it verifies.

    @return ``{"path", "rows", "sha256"}`` for the published file.
    @raises BackfillError when the written file cannot be read back or its row
        count differs; the previous destination is left untouched either way.
    """
    import pyarrow.parquet as pq

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    try:
        pq.write_table(table, temporary, compression=compression)
        reread = pq.read_table(temporary)
    except Exception as error:  # noqa: BLE001 - report the cause, then fail closed
        temporary.unlink(missing_ok=True)
        raise BackfillError(f"written parquet failed verification: {error}") from error
    if reread.num_rows != table.num_rows:
        temporary.unlink(missing_ok=True)
        raise BackfillError(
            f"written parquet row count {reread.num_rows} != {table.num_rows}")
    os.replace(temporary, path)
    return {"path": str(path), "rows": table.num_rows, "sha256": sha256_file(path)}


def write_json_atomically(value, path: Path) -> None:
    """Write ``value`` as JSON to ``path`` atomically (temp file, then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


# --------------------------------------------------------------------------- #
# Versioned publication
# --------------------------------------------------------------------------- #
#
# A derived artifact is archived per cutoff/date rather than overwritten in
# place: each publication lands in its own immutable directory under
# ``<base>/versions/<label_version>/`` and ``<base>/current.json`` points at the
# newest one. Re-running with the same inputs and the same label version is a
# no-op; re-running with different content under an already-published label
# version fails, because a published cutoff must not be rewritten.

VERSIONS_DIR = "versions"
CURRENT_FILE = "current.json"
VERSION_SCHEMA = "beijing_lot_derived_version_v1"


def version_directory(base: Path, label_version: str) -> Path:
    """``<base>/versions/<label_version>`` for a derived artifact."""
    if not label_version or "/" in label_version or label_version in {".", ".."}:
        raise BackfillError(f"invalid label version: {label_version!r}")
    return Path(base) / VERSIONS_DIR / label_version


def list_versions(base: Path) -> list[str]:
    """Published label versions, oldest name first (lexicographic)."""
    directory = Path(base) / VERSIONS_DIR
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.is_dir())


def read_current(base: Path) -> dict | None:
    """The ``current.json`` pointer, or ``None`` when nothing is published."""
    path = Path(base) / CURRENT_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BackfillError(f"current pointer is unreadable: {path}: {error}") from error


def publish_version(base: Path, label_version: str, table, receipt: dict, *,
                    artifact_name: str = "labels.parquet") -> dict:
    """Publish ``table`` + ``receipt`` as one immutable label version.

    @return A record with ``label_version``, ``artifact`` (path, rows, sha256),
    ``receipt`` path, ``status`` of ``"published"`` or ``"unchanged"``, and the
    ``versions`` list after the call.
    @raises BackfillError when the label version is already published with
        different content: a finalized cutoff is never rewritten.
    """
    base = Path(base)
    directory = version_directory(base, label_version)
    artifact = directory / artifact_name
    existing = list_versions(base)

    if label_version in existing:
        if not artifact.is_file():
            raise BackfillError(
                f"label version {label_version!r} exists but has no artifact: {artifact}")
        # Compare content by hash, not by receipt: the stored receipt carries
        # fields that are added at publish time, so a receipt comparison would
        # never match. Writing to a temporary name and hashing it answers the
        # real question - is this the same bytes?
        incoming = write_parquet_atomically(
            table, directory / f".{artifact_name}.incoming")
        prior_sha = sha256_file(artifact)
        same = incoming["sha256"] == prior_sha and incoming["rows"] == table.num_rows
        (directory / f".{artifact_name}.incoming").unlink(missing_ok=True)
        if same:
            record = {
                "label_version": label_version,
                "status": "unchanged",
                "artifact": {"path": str(artifact), "rows": incoming["rows"],
                             "sha256": prior_sha},
                "receipt": str(directory / "receipt.json"),
                "versions": existing,
            }
            # Refreshing an older label must not move the pointer backwards:
            # `current` always means the newest published label.
            _point_current_at_newest(base)
            return record
        raise BackfillError(
            f"label version {label_version!r} is already published with different content "
            f"(recorded {prior_sha[:12]}, incoming {incoming['sha256'][:12]}); "
            f"publish under a new label version instead of rewriting a finalized cutoff")

    published = write_parquet_atomically(table, artifact)
    receipt = {**receipt, "label_version": label_version,
               "version_schema": VERSION_SCHEMA,
               "artifact": artifact_name,
               "output": {"path": str(artifact), "rows": published["rows"],
                          "sha256": published["sha256"]}}
    write_json_atomically(receipt, directory / "receipt.json")
    record = {
        "label_version": label_version,
        "status": "published",
        "artifact": {"path": str(artifact), "rows": published["rows"],
                     "sha256": published["sha256"]},
        "receipt": str(directory / "receipt.json"),
        "versions": list_versions(base),
    }
    _point_current_at_newest(base)
    return record


def _point_current_at_newest(base: Path) -> None:
    """Point ``current.json`` at the newest published label version.

    Label versions are ISO dates, so lexicographic order is chronological.
    """
    base = Path(base)
    versions = list_versions(base)
    if not versions:
        return
    newest = versions[-1]
    directory = version_directory(base, newest)
    artifact = directory / "labels.parquet"
    if not artifact.is_file():
        raise BackfillError(f"newest label version {newest!r} has no artifact: {artifact}")
    receipt_path = directory / "receipt.json"
    rows = None
    if receipt_path.is_file():
        try:
            rows = json.loads(receipt_path.read_text(encoding="utf-8")).get("output", {}).get("rows")
        except (OSError, json.JSONDecodeError):
            rows = None
    write_json_atomically({
        "schema": VERSION_SCHEMA,
        "label_version": newest,
        "artifact": {"path": str(artifact), "rows": rows,
                     "sha256": sha256_file(artifact)},
    }, base / CURRENT_FILE)


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
        # Two different questions, deliberately reported separately:
        #   `counts.*`            rows that yielded a label (handicap resolved
        #                         AND the score parsed), i.e. usability;
        #   `handicap_source_rows` rows whose handicap came from each source,
        #                         including rows whose score did not parse.
        # The derived table's `handicap_source` column matches the latter.
        "counts": {
            "total_spf": sum(1 for r in rows if r.get("play") == "spf"),
            "handicap_from_archive": from_archive,
            "handicap_from_cross_source": from_cross,
            "unresolved": unresolved,
        },
        "handicap_source_rows": {
            "note": "rows carrying each handicap_source value, including rows with an unparsable score",
            "archive": sum(1 for r in derived if r.get("handicap_source") == "archive"),
            "cross_source": sum(1 for r in derived if r.get("handicap_source") == "cross_source"),
            "none": sum(1 for r in derived if r.get("handicap_source") is None),
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
