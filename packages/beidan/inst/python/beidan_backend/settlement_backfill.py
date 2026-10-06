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

# The five plays, in the repository's canonical order. Every fixture gets one
# row per play so consumers read all five the same way.
PLAYS = ("spf", "jq", "ds", "bf", "bq")


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


def play_label(play: str, score_text: str, halftime_text: str | None,
               handicap: int | None) -> str | None:
    """The label for one observation, for every play.

    Delegates to the settlement parser's authoritative ``expected_option`` so
    the derived table cannot drift from the labels the collector would compute;
    only the handicap is supplied from the cross source first. Returns ``None``
    when the play's inputs are not stated, never a guess.
    """
    from .settlement.parser import expected_option

    return expected_option({
        "play": play, "score": score_text,
        "halftime_score": halftime_text, "handicap": handicap,
    })


def _resolve_handicap(row: dict, cross: CrossSource):
    """The handicap for one row: 500 first, archive fallback, else unknown.

    Both sources may state one; they are compared so a disagreement is recorded
    even when the score does not parse.
    """
    cross_line = cross.handicap(row["issue"], row["slot"])
    archive_line = row.get("handicap")
    if cross_line is not None:
        return cross_line, "cross_source", archive_line, cross_line
    if archive_line is not None:
        return archive_line, "archive", archive_line, None
    return None, None, archive_line, None


def derive_play_labels(rows: list[dict], cross: CrossSource) -> tuple[list[dict], dict]:
    """Derive one label per (issue, slot, play) for all five plays, uniformly.

    The point of the uniform shape is that a consumer reads every play the same
    way: one row per play per fixture, a single ``option`` column, and an
    explicit ``option_source`` telling whether the label was derived here or
    taken from the archive's own settlement.

    @param rows Observation rows with ``issue``, ``slot``, ``play``, ``score``,
        ``halftime_score``, ``handicap`` and ``archive_result_raw``. A fixture
        absent from ``rows`` for a play is emitted as an unresolved row, so every
        fixture has five rows.
    @param cross The 500.com ``(issue, slot) -> handicap_line`` source, preferred
        for the handicap because it states it explicitly, including 0.
    @return ``(labels, receipt)``. Fixtures where both sources state a handicap
        and the values differ are listed under ``known_disagreements``.
    """
    fixtures: dict[tuple[str, int], dict] = {}
    for row in rows:
        key = (str(row["issue"]), int(row["slot"]))
        fixtures.setdefault(key, {})[row.get("play")] = row

    labels: list[dict] = []
    derived_count = observed_count = unresolved = 0
    from_archive = from_cross = 0
    observed_mismatch: list[dict] = []
    contradicted: list[dict] = []
    disagreements: list[dict] = []
    per_play: dict[str, dict[str, int]] = {}

    for (issue, slot), by_play in fixtures.items():
        reference = by_play.get("spf") or next(iter(by_play.values()))
        cross_line = cross.handicap(issue, slot)
        archive_line = reference.get("handicap")
        if cross_line is not None and archive_line is not None and cross_line != archive_line:
            disagreements.append({
                "issue": issue, "slot": slot, "score": reference.get("score"),
                "archive_handicap": archive_line, "cross_handicap": cross_line,
                "applied": cross_line, "applied_source": "cross_source",
                "archive_result": reference.get("archive_result_raw"),
            })
        for play in PLAYS:
            row = by_play.get(play)
            tally = per_play.setdefault(
                play, {"rows": 0, "derived": 0, "observed": 0, "unresolved": 0})
            tally["rows"] += 1
            if row is None:
                unresolvable = True
                handicap_resolved = None
                handicap_source = None
                score_text = halftime_text = None
                observed = archive_result = None
                mismatch = None
            else:
                handicap_resolved, handicap_source, _, _ = _resolve_handicap(row, cross) \
                    if play == "spf" else (row.get("handicap"), "archive", None, None)
                score_text = row.get("score")
                halftime_text = row.get("halftime_score")
                observed = row.get("observed_option")
                archive_result = row.get("archive_result_raw")
                unresolvable = parse_score(score_text) is None or (
                    play == "spf" and handicap_resolved is None)
                mismatch = None

            option = None if unresolvable else play_label(
                play, score_text, halftime_text, handicap_resolved)

            if option is not None and observed is not None and option != observed:
                mismatch = {"derived": option, "observed": observed}
                observed_mismatch.append({"issue": issue, "slot": slot, "play": play, **mismatch})
            if option is not None and archive_result in {"胜", "平", "负"} and play == "spf" \
                    and option != archive_result:
                contradicted.append({
                    "issue": issue, "slot": slot, "score": score_text,
                    "handicap": handicap_resolved, "archive_result": archive_result,
                    "derived": option, "resolved_by": handicap_source,
                })

            if option is None:
                unresolved += 1
                tally["unresolved"] += 1
            elif observed is not None and option == observed:
                observed_count += 1
                tally["observed"] += 1
            else:
                derived_count += 1
                tally["derived"] += 1
                if play == "spf" and handicap_source == "archive":
                    from_archive += 1
                elif play == "spf":
                    from_cross += 1

            labels.append({
                "issue": issue, "slot": slot, "play": play,
                "handicap": handicap_resolved if play == "spf" else None,
                "option": option,
                "option_source": None if option is None else
                    ("observed" if (observed is not None and option == observed) else "derived"),
                "observed_option": observed,
                "archive_result": archive_result,
            })

    receipt = {
        "schema": "beijing_lot_play_labels_receipt_v1",
        "rule": ("one row per (issue, slot, play) for plays "
                 f"{list(PLAYS)}; `option` is derived by the settlement parser's "
                 "play_label(), with the spf handicap taken from the 500.com "
                 "settlement table first (an explicit statement, including 0) "
                 "and the archive's rendered handicap as fallback; "
                 "`observed_option` records the archive's own settled option. "
                 "`option_source` is 'observed' when the two agree and 'derived' "
                 "otherwise, so a disagreement is visible rather than silently "
                 "resolved"),
        "cross_source": {"path": str(cross.path), "sha256": cross.sha256,
                         "rows": len(cross.values)},
        "counts": {
            "total_labels": len(labels),
            "fixtures": len(fixtures),
            "derived": derived_count,
            "observed": observed_count,
            "unresolved": unresolved,
            "handicap_from_archive": from_archive,
            "handicap_from_cross_source": from_cross,
        },
        "per_play": per_play,
        "observed_agreement": {
            "compared": derived_count + observed_count,
            "mismatches": len(observed_mismatch),
            "examples": observed_mismatch[:10],
        },
        "cross_check": {
            "compared": derived_count + observed_count,
            "contradictions": len(contradicted),
            "examples": contradicted[:10],
        },
        "known_disagreements": {
            "policy": "500.com is the data source; the archive's differing handicap is recorded, not applied",
            "resolution": "unresolved_pending_third_source",
            "definition": "both sources state a handicap for the fixture and the two values differ",
            "count": len(disagreements),
            "rows": disagreements,
        },
    }
    return labels, receipt
