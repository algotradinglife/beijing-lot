"""Deterministic, read-only audit of XLSM historical score-price provenance.

This module deliberately audits only workbook structure and price-vector
coverage.  It never queries outcomes, settlement, performance, prediction, or
return fields.  Local source paths and source bytes are never included in the
public artifacts it writes.
"""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
import hashlib
import json
import math
import posixpath
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZipFile

from src.research_freeze_protocol import ResearchFreezeError, create_freeze_package, verify_freeze_package


AUDIT_ID = "SCORE-PRICE-HIST-AUDIT-001"
AUDIT_SCHEMA = "score_price_hist_audit_v1"
PUBLIC_ARTIFACTS = (
    "source_inventory.json",
    "workbook_layout.json",
    "database_coverage.json",
    "outcome_schema_comparison.json",
    "timestamp_evidence.json",
    "audit_report.json",
    "classification.json",
    "audit_config.json",
    "reproducibility_receipt.json",
)

SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CELL_REF_RE = re.compile(r"^([A-Z]+)([0-9]+)$")
LOGICAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
FULL_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\"'\s])(?:/[A-Za-z0-9_.~/-]+|[A-Za-z]:[\\/][^\"'\s]*)")

# These are the explicit column contracts in the converter, expressed here so
# a header drift is rejected rather than silently remapped.
GOAL_OUTCOMES = ("0~1", "2~3", "4~6", "7+")
HALF_FULL_OUTCOMES = ("主主", "主和", "主客", "和主", "和和", "和负", "客主", "客和", "客客")
HISTORICAL_SCORE_OUTCOMES = (
    "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "4:3",
    "0:0", "1:1", "2:2", "3:3", "4:4", "其他", "0:1", "0:2", "1:2", "0:3",
    "1:3", "2:3", "0:4", "1:4", "2:4", "3:4",
)
CURRENT_P42_OUTCOMES = (
    "home_other", "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2",
    "draw_other", "0:0", "1:1", "2:2", "3:3", "away_other", "0:1", "0:2", "1:2",
    "0:3", "1:3", "2:3", "0:4", "1:4", "2:4",
)
TAIL_GROUPS: tuple[tuple[str, int, tuple[str, ...], str], ...] = (
    ("sclassid", 814, (), "sclassid"),
    ("goals", 815, GOAL_OUTCOMES, "入球数"),
    ("half_full", 819, HALF_FULL_OUTCOMES, "半全场"),
    ("score", 828, HISTORICAL_SCORE_OUTCOMES, "比分"),
)
TS_10H_COLUMN_INDEX = 16
SCORE_START_COLUMN = 828
SCORE_END_COLUMN = SCORE_START_COLUMN + len(HISTORICAL_SCORE_OUTCOMES) - 1
SENSITIVE_KEYS = frozenset({
    "absolute_path", "raw_vba", "vba_source", "source_bytes", "credential", "credentials", "password",
    "secret", "raw_payload", "raw_formula",
})
PROHIBITED_PUBLIC_FIELD_TOKENS = frozenset({
    "winning_sp", "result_code", "profit", "payout", "roi", "ev", "kelly", "ticket", "prediction",
    "hit_rate", "stake",
})


class ScorePriceAuditError(ValueError):
    """Raised when the fail-closed historical price audit cannot proceed."""


@dataclass(frozen=True)
class AuditInput:
    """A runtime-supplied source referred to publicly by a logical ID only."""

    logical_id: str
    kind: str
    path: Path


def canonical_json(value: Any) -> str:
    """Return stable public JSON text."""

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a regular source file without retaining source bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_logical_id(value: str) -> str:
    if not LOGICAL_ID_RE.fullmatch(value):
        raise ScorePriceAuditError("input logical ID must be a short safe identifier")
    return value


def parse_input_spec(value: str, *, kind: str) -> AuditInput:
    """Parse ``logical_id=runtime_path`` without ever publishing the path."""

    logical_id, separator, raw_path = value.partition("=")
    if separator != "=" or not raw_path:
        raise ScorePriceAuditError("runtime input must use logical_id=path")
    source = Path(raw_path).expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise ScorePriceAuditError("runtime input must be a readable regular file")
    return AuditInput(logical_id=_safe_logical_id(logical_id), kind=kind, path=source)


def _column_name(index: int) -> str:
    if index <= 0:
        raise ValueError("spreadsheet columns are one-indexed")
    letters: list[str] = []
    remaining = index
    while remaining:
        remaining, remainder = divmod(remaining - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def _column_index(value: str) -> int:
    result = 0
    for character in value:
        result = result * 26 + ord(character) - 64
    return result


def _source_stat(path: Path) -> dict[str, Any]:
    details = path.stat()
    return {
        "bytes": details.st_size,
        "observed_mtime_utc": datetime.fromtimestamp(details.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
        "sha256": sha256_file(path),
    }


def build_input_inventory(inputs: Iterable[AuditInput]) -> dict[str, Any]:
    """Freeze a redacted G0 identity before inspecting layout or coverage."""

    inventory: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in sorted(inputs, key=lambda candidate: (candidate.kind, candidate.logical_id)):
        key = (item.kind, item.logical_id)
        if key in seen:
            raise ScorePriceAuditError("duplicate runtime input logical ID")
        seen.add(key)
        inventory.append({
            "logical_id": item.logical_id,
            "kind": item.kind,
            "filename": item.path.name,
            **_source_stat(item.path),
        })
    if not inventory:
        raise ScorePriceAuditError("at least one runtime input is required")
    return {"schema_version": AUDIT_SCHEMA, "phase": "G0_PRE_COVERAGE", "inputs": inventory}


def _inventory_identity(inventory: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    raw_inputs = inventory.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ScorePriceAuditError("invalid source inventory")
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in raw_inputs:
        if not isinstance(item, Mapping):
            raise ScorePriceAuditError("invalid source inventory entry")
        kind = item.get("kind")
        logical_id = item.get("logical_id")
        if not isinstance(kind, str) or not isinstance(logical_id, str):
            raise ScorePriceAuditError("invalid source inventory identity")
        key = (kind, logical_id)
        if key in result:
            raise ScorePriceAuditError("duplicate source inventory identity")
        result[key] = item
    return result


def verify_runtime_inventory(inputs: Iterable[AuditInput], frozen_inventory: Mapping[str, Any]) -> None:
    """Fail closed when runtime source bytes differ from the frozen inventory."""

    expected = _inventory_identity(frozen_inventory)
    current = _inventory_identity(build_input_inventory(inputs))
    if set(expected) != set(current):
        raise ScorePriceAuditError("runtime source logical IDs do not match the frozen inventory")
    for key in sorted(expected):
        before = expected[key]
        after = current[key]
        if before.get("bytes") != after.get("bytes") or before.get("sha256") != after.get("sha256"):
            raise ScorePriceAuditError(f"runtime source hash mismatch for {key[0]}:{key[1]}")


def _assert_sources_unchanged(inputs: Iterable[AuditInput], inventory: Mapping[str, Any]) -> None:
    """Reject source mutation observed during this read-only audit run."""

    expected = _inventory_identity(inventory)
    for item in inputs:
        current = _source_stat(item.path)
        prior = expected[(item.kind, item.logical_id)]
        if current["bytes"] != prior.get("bytes") or current["sha256"] != prior.get("sha256"):
            raise ScorePriceAuditError(f"source changed while audit was reading {item.kind}:{item.logical_id}")


def _read_shared_strings(workbook: ZipFile) -> list[str]:
    name = "xl/sharedStrings.xml"
    if name not in workbook.namelist():
        return []
    try:
        root = ET.fromstring(workbook.read(name))
    except ET.ParseError as exc:
        raise ScorePriceAuditError("workbook shared-string metadata is malformed") from exc
    values: list[str] = []
    for item in root.findall(SPREADSHEET_NS + "si"):
        values.append("".join(node.text or "" for node in item.iter(SPREADSHEET_NS + "t")))
    return values


def _cell_value(cell: ET.Element, shared_strings: Sequence[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    raw = cell.findtext(SPREADSHEET_NS + "v")
    if cell_type == "s":
        if raw is None:
            return None
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError) as exc:
            raise ScorePriceAuditError("workbook shared-string index is invalid") from exc
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(SPREADSHEET_NS + "t"))
    return raw


def _cell_snapshot(cell: ET.Element | None, shared_strings: Sequence[str], *, index: int) -> dict[str, Any]:
    formula = cell.findtext(SPREADSHEET_NS + "f") if cell is not None else None
    return {
        "column": _column_name(index),
        "column_index": index,
        "value": _cell_value(cell, shared_strings) if cell is not None else None,
        "data_type": cell.attrib.get("t", "numeric_or_general") if cell is not None else "missing",
        "has_formula": formula is not None,
        "formula_sha256": sha256_bytes(formula.encode("utf-8")) if formula is not None else None,
    }


def _normalize_sheet_target(value: str) -> str:
    candidate = value.lstrip("/")
    if not candidate.startswith("xl/"):
        candidate = posixpath.join("xl", candidate)
    normalized = posixpath.normpath(candidate)
    if normalized.startswith("../") or not normalized.startswith("xl/"):
        raise ScorePriceAuditError("workbook sheet relationship has an unsafe target")
    return normalized


def _resolve_sheets(workbook: ZipFile) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(workbook.read("xl/workbook.xml"))
        relations = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ET.ParseError) as exc:
        raise ScorePriceAuditError("workbook sheet metadata is unavailable") from exc
    targets = {
        item.attrib.get("Id", ""): _normalize_sheet_target(item.attrib.get("Target", ""))
        for item in relations.findall(PACKAGE_REL_NS + "Relationship")
        if item.attrib.get("Type", "").endswith("/worksheet")
    }
    sheets: list[dict[str, str]] = []
    for index, sheet in enumerate(root.findall(f"{SPREADSHEET_NS}sheets/{SPREADSHEET_NS}sheet"), start=1):
        relationship = sheet.attrib.get(OFFICE_REL_NS + "id", "")
        target = targets.get(relationship)
        if target is None:
            raise ScorePriceAuditError("workbook sheet has no resolvable XML target")
        sheets.append({"sheet_index": str(index), "sheet_name": sheet.attrib.get("name", ""), "xml_path": target})
    if not sheets:
        raise ScorePriceAuditError("workbook contains no worksheets")
    return sheets


def _header_rows(workbook: ZipFile, sheet_path: str, shared_strings: Sequence[str]) -> dict[int, dict[int, ET.Element]]:
    rows: dict[int, dict[int, ET.Element]] = {}
    try:
        handle = workbook.open(sheet_path)
    except KeyError as exc:
        raise ScorePriceAuditError("converter data-sheet XML is missing") from exc
    with handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != SPREADSHEET_NS + "row":
                continue
            try:
                row_number = int(element.attrib.get("r", "0"))
            except ValueError as exc:
                raise ScorePriceAuditError("workbook row identifier is invalid") from exc
            if row_number > 2:
                break
            if row_number in {1, 2}:
                cells: dict[int, ET.Element] = {}
                for cell in element.findall(SPREADSHEET_NS + "c"):
                    match = CELL_REF_RE.match(cell.attrib.get("r", ""))
                    if not match:
                        continue
                    cells[_column_index(match.group(1))] = cell
                rows[row_number] = cells
            element.clear()
    if set(rows) != {1, 2}:
        raise ScorePriceAuditError("workbook must expose the two expected header rows")
    return rows


def _intersects_tail(reference: str) -> bool:
    parts = reference.split(":")
    endpoints: list[int] = []
    for part in parts:
        match = CELL_REF_RE.match(part)
        if not match:
            return False
        endpoints.append(_column_index(match.group(1)))
    return min(endpoints) <= SCORE_END_COLUMN and max(endpoints) >= 814


def _tail_merge_ranges(workbook: ZipFile, sheet_path: str) -> list[str]:
    """Stream merge metadata without retaining worksheet data cells."""

    pattern = re.compile(rb"<mergeCell\b[^>]*\bref=\"([^\"]+)\"")
    found: set[str] = set()
    try:
        handle = workbook.open(sheet_path)
    except KeyError as exc:
        raise ScorePriceAuditError("converter data-sheet XML is missing") from exc
    with handle:
        remainder = b""
        while True:
            chunk = handle.read(4 * 1024 * 1024)
            if not chunk:
                break
            payload = remainder + chunk
            cut = payload.rfind(b">")
            if cut < 0:
                remainder = payload[-512:]
                continue
            complete, remainder = payload[: cut + 1], payload[cut + 1 :]
            for match in pattern.finditer(complete):
                reference = match.group(1).decode("ascii", errors="ignore")
                if _intersects_tail(reference):
                    found.add(reference)
    return sorted(found)


def _tail_structural_sample(
    workbook: ZipFile,
    sheet_path: str,
    shared_strings: Sequence[str],
    *,
    sample_rows: int,
) -> dict[str, Any]:
    """Collect only safe type/formula summaries from an early deterministic sample."""

    if sample_rows <= 0:
        raise ScorePriceAuditError("structural sample row count must be positive")
    tail_types: dict[str, int] = {}
    ts_types: dict[str, int] = {}
    tail_formula_hashes: set[str] = set()
    ts_formula_hashes: set[str] = set()
    tail_formula_references_ts_10h = False
    observed = 0
    with workbook.open(sheet_path) as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != SPREADSHEET_NS + "row":
                continue
            row_number = int(element.attrib.get("r", "0"))
            if row_number <= 2:
                element.clear()
                continue
            tail_seen = False
            for cell in element.findall(SPREADSHEET_NS + "c"):
                match = CELL_REF_RE.match(cell.attrib.get("r", ""))
                if not match:
                    continue
                column_index = _column_index(match.group(1))
                if column_index != TS_10H_COLUMN_INDEX and not (SCORE_START_COLUMN <= column_index <= SCORE_END_COLUMN):
                    continue
                value = _cell_value(cell, shared_strings)
                data_type = cell.attrib.get("t", "numeric_or_general") if value is not None else "blank_or_cached_missing"
                formula = cell.findtext(SPREADSHEET_NS + "f")
                if SCORE_START_COLUMN <= column_index <= SCORE_END_COLUMN:
                    tail_seen = tail_seen or value is not None or formula is not None
                    tail_types[data_type] = tail_types.get(data_type, 0) + 1
                    if formula is not None:
                        tail_formula_hashes.add(sha256_bytes(formula.encode("utf-8")))
                        if re.search(r"(?<![A-Z])\$?P\$?\d+", formula.upper()):
                            tail_formula_references_ts_10h = True
                else:
                    ts_types[data_type] = ts_types.get(data_type, 0) + 1
                    if formula is not None:
                        ts_formula_hashes.add(sha256_bytes(formula.encode("utf-8")))
            if tail_seen:
                observed += 1
            element.clear()
            if observed >= sample_rows:
                break
    return {
        "scope": "first_nonempty_score_tail_rows",
        "requested_rows": sample_rows,
        "observed_rows": observed,
        "score_tail_data_type_counts": dict(sorted(tail_types.items())),
        "score_tail_formula_sha256": sorted(tail_formula_hashes),
        "ts_10h_data_type_counts": dict(sorted(ts_types.items())),
        "ts_10h_formula_sha256": sorted(ts_formula_hashes),
        "sampled_score_formula_references_ts_10h_column": tail_formula_references_ts_10h,
        "notice": "This bounded structural sample is not treated as proof that a timestamp applies to all score-price cells.",
    }


def _defined_name_evidence(workbook: ZipFile) -> dict[str, Any]:
    root = ET.fromstring(workbook.read("xl/workbook.xml"))
    values = [item.text or "" for item in root.findall(f"{SPREADSHEET_NS}definedNames/{SPREADSHEET_NS}definedName")]
    return {
        "defined_name_count": len(values),
        "defined_name_formula_sha256": sorted(sha256_bytes(value.encode("utf-8")) for value in values),
        "defined_name_external_reference_count": sum("[" in value or "://" in value for value in values),
        "defined_name_timestamp_token_count": sum("10" in value.casefold() and "hour" in value.casefold() for value in values),
        "values_disclosed": False,
    }


def _vba_evidence(workbook: ZipFile) -> dict[str, Any]:
    name = "xl/vbaProject.bin"
    if name not in workbook.namelist():
        return {"vba_project_present": False, "static_scan_performed": False, "content_disclosed": False}
    payload = workbook.read(name)
    lowered = payload.lower()
    # The scan is deliberately semantic and one-way: it emits no source text,
    # URLs, provider names, credentials, or macro payload.
    def present(token: bytes) -> bool:
        return token in lowered or token.decode("ascii").encode("utf-16le") in lowered

    return {
        "vba_project_present": True,
        "static_scan_performed": True,
        "content_disclosed": False,
        "semantic_markers": {
            "url_marker_present": present(b"http"),
            "timestamp_marker_present": any(present(token) for token in (b"timestamp", b"time", b"10h")),
            "score_market_marker_present": any(present(token) for token in (b"score", b"odds", b"sp")),
            "authentication_material_marker_present": any(present(token) for token in (b"password", b"token", b"secret")),
        },
        "provider_identity_from_vba": "UNRESOLVED",
    }


def _converter_contract() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    source = root / "scripts" / "convert_beidan_xlsm_to_sqlite.py"
    if not source.is_file():
        raise ScorePriceAuditError("converter source is unavailable")
    text = source.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
        assigned = next(
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "SCORE_OUTCOMES" for target in node.targets)
        )
        converter_outcomes = tuple(ast.literal_eval(assigned))
    except (StopIteration, SyntaxError, ValueError) as exc:
        raise ScorePriceAuditError("converter score outcome mapping is unreadable") from exc
    return {
        "source_file": "scripts/convert_beidan_xlsm_to_sqlite.py",
        "source_sha256": sha256_file(source),
        "ts_10h_source_column_index": TS_10H_COLUMN_INDEX,
        "score_tail_column_start": SCORE_START_COLUMN,
        "score_tail_column_end": SCORE_END_COLUMN,
        "converter_score_outcomes": list(converter_outcomes),
        "converter_score_outcomes_match_audit_contract": list(converter_outcomes) == list(HISTORICAL_SCORE_OUTCOMES),
        "exotic_odds_columns_written": ["match_id", "market", "outcome", "odds"],
        "exotic_odds_carries_snapshot_or_timestamp": False,
    }


def inspect_workbook(workbook_input: AuditInput, *, sample_rows: int = 64) -> dict[str, Any]:
    """Return redacted structural workbook evidence and reject header drift."""

    try:
        with ZipFile(workbook_input.path) as workbook:
            members = set(workbook.namelist())
            sheets = _resolve_sheets(workbook)
            converter_sheet = "xl/worksheets/sheet1.xml"
            if converter_sheet not in members:
                raise ScorePriceAuditError("converter data-sheet XML is absent from workbook")
            shared_strings = _read_shared_strings(workbook)
            headers = _header_rows(workbook, converter_sheet, shared_strings)
            groups: list[dict[str, Any]] = []
            mismatch_messages: list[str] = []
            for name, start, expected_outcomes, expected_group_header in TAIL_GROUPS:
                end = start + max(len(expected_outcomes), 1) - 1
                row_one = [_cell_snapshot(headers[1].get(column), shared_strings, index=column) for column in range(start, end + 1)]
                row_two = [_cell_snapshot(headers[2].get(column), shared_strings, index=column) for column in range(start, end + 1)]
                actual_group = row_one[0]["value"]
                actual_outcomes = [item["value"] for item in row_two]
                group_matched = actual_group == expected_group_header
                outcomes_matched = not expected_outcomes or actual_outcomes == list(expected_outcomes)
                if not group_matched:
                    mismatch_messages.append(f"{name}: group header does not match converter contract")
                if not outcomes_matched:
                    mismatch_messages.append(f"{name}: outcome headers do not match converter contract")
                groups.append({
                    "group": name,
                    "start_column": start,
                    "end_column": end,
                    "expected_group_header": expected_group_header,
                    "expected_outcomes": list(expected_outcomes),
                    "header_row_1": row_one,
                    "header_row_2": row_two,
                    "group_header_matches": group_matched,
                    "outcome_headers_match": outcomes_matched,
                })
            if mismatch_messages:
                raise ScorePriceAuditError("workbook tail header layout drift: " + "; ".join(mismatch_messages))
            ts_headers = [
                _cell_snapshot(headers[row].get(TS_10H_COLUMN_INDEX), shared_strings, index=TS_10H_COLUMN_INDEX)
                for row in (1, 2)
            ]
            relationship_sheet = next((item for item in sheets if item["xml_path"] == converter_sheet), None)
            return {
                "schema_version": AUDIT_SCHEMA,
                "workbook_logical_id": workbook_input.logical_id,
                "converter_data_sheet_xml": converter_sheet,
                "converter_data_sheet_declared": relationship_sheet,
                "worksheets": sheets,
                "tail_groups": groups,
                "tail_merge_ranges": _tail_merge_ranges(workbook, converter_sheet),
                "ts_10h_column": {
                    "column": _column_name(TS_10H_COLUMN_INDEX),
                    "column_index": TS_10H_COLUMN_INDEX,
                    "header_rows": ts_headers,
                },
                "score_tail_columns": {
                    "start": SCORE_START_COLUMN,
                    "end": SCORE_END_COLUMN,
                    "start_column": _column_name(SCORE_START_COLUMN),
                    "end_column": _column_name(SCORE_END_COLUMN),
                },
                "structural_sample": _tail_structural_sample(
                    workbook, converter_sheet, shared_strings, sample_rows=sample_rows
                ),
                "defined_names": _defined_name_evidence(workbook),
                "external_link_member_count": sum(name.startswith("xl/externalLinks/") for name in members),
                "connection_member_present": "xl/connections.xml" in members,
                "query_table_member_count": sum(name.startswith("xl/queryTables/") for name in members),
                "vba": _vba_evidence(workbook),
                "provider_identity": "UNRESOLVED",
                "market_identity": "UNRESOLVED",
                "source_observation_time": "UNVERIFIED",
                "provenance_notice": (
                    "Header labels and numeric cells establish neither provider identity nor a source observation time. "
                    "No VBA or connection payload is disclosed."
                ),
            }
    except (OSError, ET.ParseError) as exc:
        raise ScorePriceAuditError("workbook cannot be read as a safe XLSM ZIP/XML source") from exc


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    # Coverage is intentionally streamed below.  Keep any unavoidable planner
    # spill on disk rather than allowing a multi-million-row source table to
    # consume process memory.
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute("PRAGMA cache_size=-16384")
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> list[dict[str, str]]:
    return [
        {"name": str(row["name"]), "type": str(row["type"])}
        for row in connection.execute(f"PRAGMA table_info({table})")
    ]


def _source_meta(connection: sqlite3.Connection, tables: set[str]) -> dict[str, Any]:
    if "source_meta" not in tables:
        return {"table_present": False, "no_exotic": "UNKNOWN", "source_location_metadata_present": False}
    values = {
        str(row["key"]): row["value"]
        for row in connection.execute("SELECT key, value FROM source_meta WHERE key IN ('no_exotic', 'source_path')")
    }
    no_exotic = str(values.get("no_exotic", "UNKNOWN"))
    return {
        "table_present": True,
        "no_exotic": no_exotic if no_exotic in {"0", "1"} else "UNKNOWN",
        "source_location_metadata_present": "source_path" in values,
    }


def _coverage_unavailable(source_meta: Mapping[str, Any], reason: str) -> dict[str, Any]:
    presence = "CONVERSION_SKIPPED" if source_meta.get("no_exotic") == "1" else "UNKNOWN"
    return {
        "presence": presence,
        "reason": reason,
        "score_price_rows": 0,
        "non_null_prices": 0,
        "valid_prices": 0,
        "distinct_matches_with_any_score_price": 0,
        "complete_vector_matches": 0,
        "duplicate_key_groups": 0,
        "duplicate_key_extra_rows": 0,
        "invalid_price_counts": {},
        "outcome_counts": [],
        "outcome_schemas": [],
        "coverage_by_calendar_year": [],
        "coverage_by_issue": [],
        "join_coverage": {"status": "UNAVAILABLE"},
        "header_to_database_mapping": {"status": "UNAVAILABLE"},
    }


def _price_status(value: object) -> str:
    """Classify a price without converting or emitting its value."""

    if value is None:
        return "null"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "non_numeric"
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 1.0:
        return "non_finite_or_lte_one"
    return "valid"


def _audit_score_table(connection: sqlite3.Connection, source_meta: Mapping[str, Any], tables: set[str]) -> dict[str, Any]:
    if "exotic_odds" not in tables:
        return _coverage_unavailable(source_meta, "exotic_odds_table_absent")
    columns = {item["name"] for item in _table_columns(connection, "exotic_odds")}
    required = {"match_id", "market", "outcome", "odds"}
    if not required.issubset(columns):
        return _coverage_unavailable(source_meta, "exotic_odds_schema_missing_required_columns")
    has_matches = "matches" in tables
    match_columns = {item["name"] for item in _table_columns(connection, "matches")} if has_matches else set()
    required_match_columns = {"match_id", "kickoff_ts", "ts_10h", "issue"}
    chronology_join_available = required_match_columns.issubset(match_columns)
    if chronology_join_available:
        query = """
            SELECT e.match_id, e.outcome, e.odds, m.match_id AS joined_match_id,
                   m.issue AS issue, m.kickoff_ts AS kickoff_ts, m.ts_10h AS ts_10h
            FROM exotic_odds AS e LEFT JOIN matches AS m ON m.match_id = e.match_id
            WHERE e.market = 'score' ORDER BY e.match_id
        """
    else:
        query = """
            SELECT e.match_id, e.outcome, e.odds, NULL AS joined_match_id,
                   NULL AS issue, NULL AS kickoff_ts, NULL AS ts_10h
            FROM exotic_odds AS e WHERE e.market = 'score' ORDER BY e.match_id
        """
    expected_outcomes = set(HISTORICAL_SCORE_OUTCOMES)
    rows = 0
    non_null_prices = 0
    valid_prices = 0
    invalid_price_counts: Counter[str] = Counter()
    outcome_rows: Counter[str] = Counter()
    outcome_valid_rows: Counter[str] = Counter()
    schema_counts: Counter[tuple[str, ...]] = Counter()
    year_coverage: dict[str, Counter[str]] = defaultdict(Counter)
    issue_coverage: dict[str, Counter[str]] = defaultdict(Counter)
    match_count = 0
    complete_matches = 0
    duplicate_key_groups = 0
    duplicate_key_extra_rows = 0
    joined_matches = 0
    joined_with_kickoff = 0
    joined_with_ts_10h = 0
    joined_with_both = 0
    current_match_id: object | None = None
    current_metadata: tuple[object, object, object, object] | None = None
    current_outcomes: Counter[str] = Counter()
    current_rows = 0
    current_valid = 0

    def finish_match() -> None:
        nonlocal match_count, complete_matches, duplicate_key_groups, duplicate_key_extra_rows
        nonlocal joined_matches, joined_with_kickoff, joined_with_ts_10h, joined_with_both
        if current_match_id is None or current_metadata is None:
            return
        match_count += 1
        outcome_set = set(current_outcomes)
        is_complete = (
            current_rows == len(HISTORICAL_SCORE_OUTCOMES)
            and current_valid == len(HISTORICAL_SCORE_OUTCOMES)
            and outcome_set == expected_outcomes
            and all(value == 1 for value in current_outcomes.values())
        )
        if is_complete:
            complete_matches += 1
        duplicate_key_groups += sum(value > 1 for value in current_outcomes.values())
        duplicate_key_extra_rows += sum(value - 1 for value in current_outcomes.values() if value > 1)
        schema_counts[tuple(sorted(outcome_set))] += 1
        joined_match_id, issue, kickoff_ts, ts_10h = current_metadata
        if joined_match_id is not None:
            joined_matches += 1
            kickoff_present = kickoff_ts is not None and str(kickoff_ts).strip() != ""
            ts_present = ts_10h is not None and str(ts_10h).strip() != ""
            joined_with_kickoff += int(kickoff_present)
            joined_with_ts_10h += int(ts_present)
            joined_with_both += int(kickoff_present and ts_present)
            year = str(kickoff_ts)[:4] if kickoff_present and re.fullmatch(r"\d{4}", str(kickoff_ts)[:4]) else "UNKNOWN"
            issue_key = str(issue).strip() if issue is not None and str(issue).strip() else "UNKNOWN"
            year_coverage[year]["matches"] += 1
            issue_coverage[issue_key]["matches"] += 1
            if is_complete:
                year_coverage[year]["complete_vectors"] += 1
                issue_coverage[issue_key]["complete_vectors"] += 1

    for row in connection.execute(query):
        match_id = row["match_id"]
        if current_match_id is not None and match_id != current_match_id:
            finish_match()
            current_outcomes = Counter()
            current_rows = 0
            current_valid = 0
        if current_match_id != match_id:
            current_match_id = match_id
            current_metadata = (row["joined_match_id"], row["issue"], row["kickoff_ts"], row["ts_10h"])
        outcome = str(row["outcome"] if row["outcome"] is not None else "<NULL>")
        status = _price_status(row["odds"])
        rows += 1
        current_rows += 1
        current_outcomes[outcome] += 1
        outcome_rows[outcome] += 1
        if status == "valid":
            non_null_prices += 1
            valid_prices += 1
            current_valid += 1
            outcome_valid_rows[outcome] += 1
        else:
            if status != "null":
                non_null_prices += 1
            invalid_price_counts[status] += 1
    finish_match()

    outcome_counts = [
        {"outcome": outcome, "rows": outcome_rows[outcome], "valid_prices": outcome_valid_rows[outcome]}
        for outcome in sorted(outcome_rows)
    ]
    outcome_schemas = [
        {"outcomes": list(schema), "matches": matches}
        for schema, matches in sorted(schema_counts.items())
    ]
    if chronology_join_available:
        coverage_by_year = [
            {"calendar_year": year, "matches": values["matches"], "complete_vectors": values["complete_vectors"]}
            for year, values in sorted(year_coverage.items())
        ]
        coverage_by_issue = [
            {"issue": issue, "matches": values["matches"], "complete_vectors": values["complete_vectors"]}
            for issue, values in sorted(issue_coverage.items())
        ]
        join_coverage = {
            "status": "AVAILABLE",
            "score_matches": match_count,
            "joined_matches": joined_matches,
            "joined_with_kickoff": joined_with_kickoff,
            "joined_with_ts_10h": joined_with_ts_10h,
            "joined_with_both": joined_with_both,
        }
    else:
        coverage_by_year, coverage_by_issue = [], []
        join_coverage = {"status": "MATCHES_SCHEMA_MISSING_CHRONOLOGY_COLUMNS" if has_matches else "MATCHES_TABLE_ABSENT"}
    observed_outcomes = list(outcome_rows)
    expected_set = set(HISTORICAL_SCORE_OUTCOMES)
    observed_set = set(observed_outcomes)
    if rows == 0:
        presence = "CONVERSION_SKIPPED" if source_meta.get("no_exotic") == "1" else "EMPTY"
    else:
        presence = "POPULATED"
    return {
        "presence": presence,
        "reason": None,
        "score_price_rows": rows,
        "non_null_prices": non_null_prices,
        "valid_prices": valid_prices,
        "distinct_matches_with_any_score_price": match_count,
        "complete_vector_matches": complete_matches,
        "duplicate_key_groups": duplicate_key_groups,
        "duplicate_key_extra_rows": duplicate_key_extra_rows,
        "invalid_price_counts": {
            "null": invalid_price_counts["null"],
            "non_numeric": invalid_price_counts["non_numeric"],
            "non_finite_or_lte_one": invalid_price_counts["non_finite_or_lte_one"],
        },
        "outcome_counts": outcome_counts,
        "outcome_schemas": outcome_schemas,
        "coverage_by_calendar_year": coverage_by_year,
        "coverage_by_issue": coverage_by_issue,
        "join_coverage": join_coverage,
        "header_to_database_mapping": {
            "status": "MATCHED" if observed_set == expected_set else "MISMATCH",
            "expected_outcomes": list(HISTORICAL_SCORE_OUTCOMES),
            "database_only_outcomes": sorted(observed_set - expected_set),
            "missing_database_outcomes": sorted(expected_set - observed_set),
        },
    }


def audit_database(database_input: AuditInput) -> dict[str, Any]:
    """Read coverage metadata without querying any outcome/performance fields."""

    try:
        with _connect_read_only(database_input.path) as connection:
            tables = {str(row["name"]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            source_meta = _source_meta(connection, tables)
            coverage = _audit_score_table(connection, source_meta, tables)
            relevant_schema = {
                table: _table_columns(connection, table)
                for table in ("source_meta", "matches", "exotic_odds")
                if table in tables
            }
    except sqlite3.Error as exc:
        raise ScorePriceAuditError(f"database audit failed for logical ID {database_input.logical_id}") from exc
    return {
        "logical_id": database_input.logical_id,
        "schema": {
            "relevant_tables": relevant_schema,
            "relevant_table_presence": {name: name in tables for name in ("source_meta", "matches", "exotic_odds")},
        },
        "source_meta": source_meta,
        "coverage": coverage,
    }


def compare_outcome_schemas(workbook_layout: Mapping[str, Any], database_coverage: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Document why the 26-column historical schema is not current 25-way p42."""

    historical_set = set(HISTORICAL_SCORE_OUTCOMES)
    current_set = set(CURRENT_P42_OUTCOMES)
    return {
        "schema_version": AUDIT_SCHEMA,
        "historical_xlsm_score_outcomes": list(HISTORICAL_SCORE_OUTCOMES),
        "historical_xlsm_outcome_count": len(HISTORICAL_SCORE_OUTCOMES),
        "current_beijing_p42_outcomes": list(CURRENT_P42_OUTCOMES),
        "current_beijing_p42_outcome_count": len(CURRENT_P42_OUTCOMES),
        "shared_exact_outcomes": [item for item in HISTORICAL_SCORE_OUTCOMES if item in current_set],
        "historical_only_outcomes": [item for item in HISTORICAL_SCORE_OUTCOMES if item not in current_set],
        "current_only_outcomes": [item for item in CURRENT_P42_OUTCOMES if item not in historical_set],
        "non_bijective_mapping_reasons": [
            "Historical 4:3, 4:4, and 3:4 are explicit cells while current p42 groups those scorelines into directional other categories.",
            "Historical 其他 is one undifferentiated category and cannot be split mechanically into home_other, draw_other, and away_other.",
        ],
        "mechanically_equivalent": False,
        "workbook_tail_layout_verified": all(
            group["group_header_matches"] and group["outcome_headers_match"]
            for group in workbook_layout["tail_groups"]
        ),
        "database_schema_status": [
            {
                "logical_id": item["logical_id"],
                "presence": item["coverage"]["presence"],
                "header_to_database_mapping_status": item["coverage"]["header_to_database_mapping"]["status"],
            }
            for item in sorted(database_coverage, key=lambda candidate: str(candidate["logical_id"]))
        ],
    }


def timestamp_evidence(
    workbook_layout: Mapping[str, Any],
    database_coverage: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Fail closed on the unproven relation between ``ts_10h`` and score cells."""

    contract = _converter_contract()
    db_schema = []
    for database in sorted(database_coverage, key=lambda candidate: str(candidate["logical_id"])):
        tables = database["schema"]["relevant_tables"]
        exotic_columns = [item["name"] for item in tables.get("exotic_odds", [])]
        matches_columns = [item["name"] for item in tables.get("matches", [])]
        db_schema.append({
            "logical_id": database["logical_id"],
            "exotic_odds_has_timestamp_column": any("time" in name.casefold() or "ts" in name.casefold() for name in exotic_columns),
            "exotic_odds_has_snapshot_column": any("snapshot" in name.casefold() for name in exotic_columns),
            "matches_has_ts_10h": "ts_10h" in matches_columns,
            "same_match_join_to_ts_10h_possible": database["coverage"]["join_coverage"].get("status") == "AVAILABLE",
        })
    return {
        "schema_version": AUDIT_SCHEMA,
        "converter_contract": contract,
        "workbook_ts_10h_header_rows": workbook_layout["ts_10h_column"]["header_rows"],
        "workbook_score_tail": workbook_layout["score_tail_columns"],
        "workbook_structural_sample": workbook_layout["structural_sample"],
        "database_timestamp_schema": db_schema,
        "positive_evidence": [],
        "failure_reasons": [
            "The score-tail group has outcome labels but no named snapshot/time header of its own.",
            "The converter writes exotic_odds(match_id, market, outcome, odds) without a snapshot or timestamp field.",
            "A same-match join from exotic_odds to matches.ts_10h is row coexistence, not evidence that ts_10h applies to score cells.",
            "No source-observation timestamp/provenance binding was established by the audited workbook layout, safe metadata, or converter contract.",
        ],
        "timestamp_grade": "UNVERIFIED",
        "strict_asof_authorized": False,
    }


def classify_audit(database_coverage: Sequence[Mapping[str, Any]], timestamp: Mapping[str, Any]) -> dict[str, Any]:
    populated = [item["logical_id"] for item in database_coverage if item["coverage"]["presence"] == "POPULATED"]
    return {
        "schema_version": AUDIT_SCHEMA,
        "audit_id": AUDIT_ID,
        "verdict": "PRICE_VECTOR_PRESENCE_AND_TIME_SEMANTICS_UNVERIFIED",
        "presence": "POPULATED" if populated else "UNKNOWN",
        "populated_database_logical_ids": sorted(populated),
        "provider_identity": "UNRESOLVED",
        "market_identity": "UNRESOLVED",
        "timestamp_grade": timestamp["timestamp_grade"],
        "replay_eligibility": "PROHIBITED",
        "evidence_level": "D",
        "reason_codes": [
            "numeric_score_price_rows_do_not_establish_provider_identity",
            "numeric_score_price_rows_do_not_establish_beijing_p42_market_identity",
            "ts_10h_binding_to_score_price_vector_not_proven",
            "historical_26_outcome_schema_is_not_mechanically_equivalent_to_current_25_outcome_p42",
        ],
        "scope_boundary": "Existence/provenance only; no model, strategy, backtest, EV, q, ROI, ticket, or performance conclusion.",
    }


def _audit_config() -> dict[str, Any]:
    return {
        "schema_version": AUDIT_SCHEMA,
        "audit_id": AUDIT_ID,
        "read_only": True,
        "execution_enabled": False,
        "frontend_selectable": False,
        "roi_authorized": False,
        "model_or_backtest_enabled": False,
        "source_data_published": False,
        "source_paths_published": False,
        "source_vba_published": False,
        "historical_score_outcome_count": len(HISTORICAL_SCORE_OUTCOMES),
        "current_p42_outcome_count": len(CURRENT_P42_OUTCOMES),
    }


def _full_git_commit(value: str) -> str:
    """Accept only an unambiguous full Git object identifier for evidence binding."""

    if not FULL_GIT_COMMIT_RE.fullmatch(value):
        raise ScorePriceAuditError("audit evidence requires a full 40-character lowercase git commit")
    return value


def _receipt(
    artifacts: Mapping[str, Any],
    inventory: Mapping[str, Any],
    *,
    git_commit: str | None,
) -> dict[str, Any]:
    receipt = {
        "schema_version": AUDIT_SCHEMA,
        "audit_id": AUDIT_ID,
        "command_template": (
            "python scripts/run_score_price_hist_audit.py audit --workbook <logical_id>=<runtime_workbook> "
            "--database <logical_id>=<runtime_database> [--database ...] --output-dir <audit_output> --freeze-dir <freeze_output>"
        ),
        "runtime_inputs": [
            {key: value for key, value in item.items() if key != "observed_mtime_utc"}
            for item in inventory["inputs"]
        ],
        "artifact_sha256": {
            name: sha256_bytes(canonical_bytes(value))
            for name, value in sorted(artifacts.items())
            if name not in {"reproducibility_receipt.json"}
        },
        "no_outcome_or_performance_fields_read": True,
        "public_redaction_verified": True,
    }
    if git_commit is not None:
        receipt["git_commit"] = _full_git_commit(git_commit)
    return receipt


def _walk_public(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key), child
            yield from _walk_public(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from _walk_public(child)


def assert_public_redaction(artifacts: Mapping[str, Any], inputs: Iterable[AuditInput]) -> None:
    """Ensure generated evidence has neither local paths nor sensitive payloads."""

    rendered = canonical_json(artifacts)
    for item in inputs:
        if str(item.path) in rendered:
            raise ScorePriceAuditError("public audit artifact leaks a local source path")
    if ABSOLUTE_PATH_RE.search(rendered):
        raise ScorePriceAuditError("public audit artifact appears to contain an absolute path")
    for key, _ in _walk_public(artifacts):
        if key is not None and key.casefold() in SENSITIVE_KEYS:
            raise ScorePriceAuditError("public audit artifact contains a sensitive source field")
        if key is not None and key.casefold() in PROHIBITED_PUBLIC_FIELD_TOKENS:
            raise ScorePriceAuditError("public audit artifact contains a prohibited outcome/performance field")


def audit_inputs(
    workbook_input: AuditInput,
    database_inputs: Sequence[AuditInput],
    *,
    sample_rows: int = 64,
    expected_inventory: Mapping[str, Any] | None = None,
    git_commit: str | None = None,
) -> dict[str, Any]:
    """Run G0--G4 and return public, deterministic artifacts in memory."""

    if workbook_input.kind != "workbook":
        raise ScorePriceAuditError("workbook input must use kind=workbook")
    if not database_inputs or any(item.kind != "database" for item in database_inputs):
        raise ScorePriceAuditError("at least one database input is required")
    all_inputs = [workbook_input, *database_inputs]
    observed_inventory = build_input_inventory(all_inputs)
    if expected_inventory is not None:
        verify_runtime_inventory(all_inputs, expected_inventory)
        inventory = dict(expected_inventory)
    else:
        inventory = observed_inventory
    layout = inspect_workbook(workbook_input, sample_rows=sample_rows)
    databases = [audit_database(item) for item in sorted(database_inputs, key=lambda candidate: candidate.logical_id)]
    schema_comparison = compare_outcome_schemas(layout, databases)
    timestamps = timestamp_evidence(layout, databases)
    classification = classify_audit(databases, timestamps)
    _assert_sources_unchanged(all_inputs, observed_inventory)
    report = {
        "schema_version": AUDIT_SCHEMA,
        "audit_id": AUDIT_ID,
        "source_inventory_sha256": sha256_bytes(canonical_bytes(inventory)),
        "workbook_layout_sha256": sha256_bytes(canonical_bytes(layout)),
        "database_coverage_sha256": sha256_bytes(canonical_bytes(databases)),
        "outcome_schema_comparison_sha256": sha256_bytes(canonical_bytes(schema_comparison)),
        "timestamp_evidence_sha256": sha256_bytes(canonical_bytes(timestamps)),
        "classification_sha256": sha256_bytes(canonical_bytes(classification)),
        "verdict": classification["verdict"],
        "scope_boundary": classification["scope_boundary"],
    }
    config = _audit_config()
    artifacts: dict[str, Any] = {
        "source_inventory.json": inventory,
        "workbook_layout.json": layout,
        "database_coverage.json": databases,
        "outcome_schema_comparison.json": schema_comparison,
        "timestamp_evidence.json": timestamps,
        "audit_report.json": report,
        "classification.json": classification,
        "audit_config.json": config,
    }
    artifacts["reproducibility_receipt.json"] = _receipt(
        artifacts,
        inventory,
        git_commit=_full_git_commit(git_commit) if git_commit is not None else None,
    )
    assert_public_redaction(artifacts, all_inputs)
    return artifacts


def write_audit_artifacts(output_dir: Path, artifacts: Mapping[str, Any]) -> dict[str, Path]:
    """Atomically write public evidence files, rejecting an existing output root."""

    final = output_dir.expanduser().resolve()
    if final.exists():
        raise FileExistsError("audit output directory already exists")
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.tmp-", dir=final.parent))
    try:
        paths: dict[str, Path] = {}
        for name in PUBLIC_ARTIFACTS:
            if name not in artifacts:
                raise ScorePriceAuditError("audit artifact set is incomplete")
            target = staging / name
            target.write_bytes(canonical_bytes(artifacts[name]))
            paths[name] = target
        staging.rename(final)
        return {name: final / name for name in PUBLIC_ARTIFACTS}
    except Exception:
        if staging.exists():
            for item in sorted(staging.rglob("*"), reverse=True):
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    item.rmdir()
            staging.rmdir()
        raise


def create_audit_package(
    artifact_paths: Mapping[str, Path],
    *,
    output_dir: Path,
    git_commit: str,
    frozen_at_utc: str,
) -> dict[str, Any]:
    """Wrap redacted artifacts in the repository's immutable freeze protocol."""

    commit = _full_git_commit(git_commit)
    try:
        receipt = json.loads(artifact_paths["reproducibility_receipt.json"].read_text(encoding="utf-8"))
    except (KeyError, OSError, json.JSONDecodeError) as exc:
        raise ScorePriceAuditError("audit package requires a valid reproducibility receipt") from exc
    if receipt.get("git_commit") != commit:
        raise ScorePriceAuditError("reproducibility receipt must bind the exact full git commit")

    inputs = [
        artifact_paths[name]
        for name in (
            "source_inventory.json",
            "workbook_layout.json",
            "database_coverage.json",
            "outcome_schema_comparison.json",
            "timestamp_evidence.json",
            "audit_report.json",
        )
    ]
    return create_freeze_package(
        output_dir,
        experiment_id=AUDIT_ID,
        research_question="What evidence establishes historical score-price vector existence, market identity, and time semantics?",
        model_version="score-price-hist-audit-v1",
        input_files=inputs,
        decision_files=[artifact_paths["classification.json"]],
        config_file=artifact_paths["audit_config.json"],
        metadata_files=[artifact_paths["reproducibility_receipt.json"]],
        # Do not use input_datasets: the generic protocol serializes local paths
        # there.  Source hashes are instead bound by source_inventory.json.
        input_datasets=[],
        git_commit=commit,
        frozen_at_utc=frozen_at_utc,
    )


def _package_artifact_path(package: Path, name: str) -> Path:
    candidates = list((package / "inputs").glob(name)) + list((package / "decision").glob(name))
    candidates += list((package / "metadata" / "config").glob(name)) + list((package / "metadata" / "files").glob(name))
    if len(candidates) != 1:
        raise ScorePriceAuditError("audit package is missing a required public artifact")
    return candidates[0]


def _load_public_json(package: Path, name: str) -> Any:
    try:
        return json.loads(_package_artifact_path(package, name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScorePriceAuditError("audit package contains invalid JSON evidence") from exc


def verify_audit_package(
    package_dir: Path,
    *,
    workbook_input: AuditInput,
    database_inputs: Sequence[AuditInput],
    sample_rows: int = 64,
) -> dict[str, Any]:
    """Verify package checksums and reproduce evidence against supplied sources."""

    package = package_dir.expanduser().resolve()
    try:
        protocol = verify_freeze_package(package)
    except ResearchFreezeError as exc:
        raise ScorePriceAuditError("immutable audit package checksum verification failed") from exc
    try:
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScorePriceAuditError("audit package contains an invalid manifest") from exc
    commit = _full_git_commit(str(manifest.get("git_commit", "")))
    receipt = _load_public_json(package, "reproducibility_receipt.json")
    if receipt.get("git_commit") != commit:
        raise ScorePriceAuditError("audit reproducibility receipt does not bind the exact full git commit")
    inventory = _load_public_json(package, "source_inventory.json")
    verify_runtime_inventory([workbook_input, *database_inputs], inventory)
    regenerated = audit_inputs(
        workbook_input,
        database_inputs,
        sample_rows=sample_rows,
        expected_inventory=inventory,
        git_commit=commit,
    )
    for name in PUBLIC_ARTIFACTS:
        stored = _load_public_json(package, name)
        if canonical_bytes(stored) != canonical_bytes(regenerated[name]):
            raise ScorePriceAuditError(f"clean-checkout reproduction mismatch for {name}")
    assert_public_redaction(regenerated, [workbook_input, *database_inputs])
    return {
        "status": "valid",
        "audit_id": AUDIT_ID,
        "git_commit": commit,
        "freeze_id": protocol["freeze_id"],
        "sha256s_sha256": protocol["sha256s_sha256"],
        "runtime_source_hashes_verified": True,
        "clean_checkout_reproduction": "matched",
        "public_redaction_verified": True,
    }
