from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.score_price_hist_audit.audit import (  # noqa: E402
    AUDIT_ID,
    CURRENT_P42_OUTCOMES,
    GOAL_OUTCOMES,
    HALF_FULL_OUTCOMES,
    HISTORICAL_SCORE_OUTCOMES,
    ScorePriceAuditError,
    audit_inputs,
    canonical_bytes,
    create_audit_package,
    parse_input_spec,
    verify_audit_package,
    write_audit_artifacts,
)


def column_name(index: int) -> str:
    letters: list[str] = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def inline_cell(column: int, row: int, value: str | float) -> str:
    if isinstance(value, str):
        return f'<c r="{column_name(column)}{row}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    return f'<c r="{column_name(column)}{row}"><v>{value}</v></c>'


def make_workbook(path: Path, *, drift: bool = False) -> Path:
    first = [
        inline_cell(16, 1, "时间"),
        inline_cell(16, 2, "赛前10小时"),
        inline_cell(814, 1, "sclassid"),
        inline_cell(815, 1, "入球数"),
        inline_cell(819, 1, "半全场"),
        inline_cell(828, 1, "比分"),
    ]
    for index, outcome in enumerate(GOAL_OUTCOMES, start=815):
        first.append(inline_cell(index, 2, outcome))
    for index, outcome in enumerate(HALF_FULL_OUTCOMES, start=819):
        first.append(inline_cell(index, 2, outcome))
    for index, outcome in enumerate(HISTORICAL_SCORE_OUTCOMES, start=828):
        first.append(inline_cell(index, 2, "错误" if drift and outcome == "1:0" else outcome))
    data = [inline_cell(16, 3, 45000.0)]
    data.extend(inline_cell(index, 3, 2.5 + position / 10) for position, index in enumerate(range(828, 854)))
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>'
        f'<row r="1">{"".join(first[:6])}</row>'
        f'<row r="2">{"".join(first[6:])}</row>'
        f'<row r="3">{"".join(data)}</row>'
        '</sheetData>'
        '<mergeCells count="3"><mergeCell ref="AEI1:AEL1"/><mergeCell ref="AEM1:AEU1"/><mergeCell ref="AEV1:AFU1"/></mergeCells>'
        '</worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="data" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relations = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relations)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


def make_database(
    path: Path,
    *,
    no_exotic: str = "0",
    outcomes: tuple[str, ...] = HISTORICAL_SCORE_OUTCOMES,
    duplicate: bool = False,
    invalid: bool = False,
) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE source_meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE matches(match_id INTEGER PRIMARY KEY, issue TEXT, kickoff_ts TEXT, ts_10h TEXT);
            CREATE TABLE exotic_odds(match_id INTEGER, market TEXT, outcome TEXT, odds);
            """
        )
        connection.executemany(
            "INSERT INTO source_meta(key, value) VALUES (?, ?)",
            [("no_exotic", no_exotic), ("source_path", "/private/vendor/workbook.xlsm")],
        )
        connection.execute(
            "INSERT INTO matches(match_id, issue, kickoff_ts, ts_10h) VALUES (1, '24001', '2024-02-03 12:00:00', '2024-02-03 02:00:00')"
        )
        if no_exotic == "0":
            connection.executemany(
                "INSERT INTO exotic_odds(match_id, market, outcome, odds) VALUES (1, 'score', ?, ?)",
                [(outcome, 2.4 + index / 10) for index, outcome in enumerate(outcomes)],
            )
        if duplicate and outcomes:
            connection.execute("INSERT INTO exotic_odds(match_id, market, outcome, odds) VALUES (1, 'score', ?, ?)", (outcomes[0], 3.0))
        if invalid and len(outcomes) >= 3:
            connection.execute("UPDATE exotic_odds SET odds = NULL WHERE outcome = ?", (outcomes[1],))
            connection.execute("UPDATE exotic_odds SET odds = 1.0 WHERE outcome = ?", (outcomes[2],))
            connection.execute("INSERT INTO exotic_odds(match_id, market, outcome, odds) VALUES (1, 'score', 'bad-price', 'not-a-number')")
    return path


def audit_fixture(tmp_path: Path, *, database_kwargs: dict[str, object] | None = None) -> tuple[Path, Path, object, object]:
    source_dir = tmp_path / "private" / "vendor"
    source_dir.mkdir(parents=True)
    workbook = make_workbook(source_dir / "history.xlsm")
    database = make_database(source_dir / "history.sqlite", **(database_kwargs or {}))
    return workbook, database, parse_input_spec(f"workbook={workbook}", kind="workbook"), parse_input_spec(f"canonical={database}", kind="database")


def test_header_layout_drift_is_rejected(tmp_path: Path) -> None:
    workbook = make_workbook(tmp_path / "drift.xlsm", drift=True)
    database = make_database(tmp_path / "history.sqlite")
    with pytest.raises(ScorePriceAuditError, match="header layout drift"):
        audit_inputs(
            parse_input_spec(f"workbook={workbook}", kind="workbook"),
            [parse_input_spec(f"canonical={database}", kind="database")],
        )


def test_populated_and_conversion_skipped_are_distinct(tmp_path: Path) -> None:
    workbook, database, workbook_input, database_input = audit_fixture(tmp_path)
    skipped = make_database(tmp_path / "skipped.sqlite", no_exotic="1")
    skipped_input = parse_input_spec(f"skipped={skipped}", kind="database")
    artifacts = audit_inputs(workbook_input, [database_input, skipped_input])
    reports = {item["logical_id"]: item for item in artifacts["database_coverage.json"]}
    assert reports["canonical"]["source_meta"]["no_exotic"] == "0"
    assert reports["canonical"]["coverage"]["presence"] == "POPULATED"
    assert reports["canonical"]["coverage"]["complete_vector_matches"] == 1
    assert reports["skipped"]["coverage"]["presence"] == "CONVERSION_SKIPPED"
    assert str(workbook) not in canonical_bytes(artifacts).decode("utf-8")
    assert str(database) not in canonical_bytes(artifacts).decode("utf-8")


def test_duplicate_incomplete_and_invalid_price_accounting(tmp_path: Path) -> None:
    _, _, workbook_input, database_input = audit_fixture(tmp_path, database_kwargs={"duplicate": True, "invalid": True})
    coverage = audit_inputs(workbook_input, [database_input])["database_coverage.json"][0]["coverage"]
    assert coverage["complete_vector_matches"] == 0
    assert coverage["duplicate_key_groups"] == 1
    assert coverage["duplicate_key_extra_rows"] == 1
    assert coverage["invalid_price_counts"]["null"] == 1
    assert coverage["invalid_price_counts"]["non_finite_or_lte_one"] == 1
    assert coverage["invalid_price_counts"]["non_numeric"] == 1


def test_outcome_schema_mismatch_is_explicit(tmp_path: Path) -> None:
    outcomes = tuple(item for item in HISTORICAL_SCORE_OUTCOMES if item != "3:4") + ("9:9",)
    _, _, workbook_input, database_input = audit_fixture(tmp_path, database_kwargs={"outcomes": outcomes})
    artifacts = audit_inputs(workbook_input, [database_input])
    mapping = artifacts["database_coverage.json"][0]["coverage"]["header_to_database_mapping"]
    assert mapping["status"] == "MISMATCH"
    assert mapping["missing_database_outcomes"] == ["3:4"]
    assert mapping["database_only_outcomes"] == ["9:9"]
    comparison = artifacts["outcome_schema_comparison.json"]
    assert comparison["historical_xlsm_outcome_count"] == 26
    assert comparison["current_beijing_p42_outcome_count"] == 25
    assert comparison["mechanically_equivalent"] is False
    assert set(CURRENT_P42_OUTCOMES) - set(HISTORICAL_SCORE_OUTCOMES) == {"home_other", "draw_other", "away_other"}


def test_timestamp_binding_fails_closed_and_prohibited_fields_are_absent(tmp_path: Path) -> None:
    _, _, workbook_input, database_input = audit_fixture(tmp_path)
    artifacts = audit_inputs(workbook_input, [database_input])
    evidence = artifacts["timestamp_evidence.json"]
    classification = artifacts["classification.json"]
    assert evidence["timestamp_grade"] == "UNVERIFIED"
    assert evidence["strict_asof_authorized"] is False
    assert classification["replay_eligibility"] == "PROHIBITED"
    assert classification["evidence_level"] == "D"
    rendered = canonical_bytes(artifacts).decode("utf-8")
    for field in ("\"winning_sp\"", "\"result_code\"", "\"profit\"", "\"payout\"", "\"ticket\"", "\"prediction\""):
        assert field not in rendered
    for sensitive_token in ("/private/vendor", "credential", "password", "raw_vba", "source_bytes"):
        assert sensitive_token not in rendered


def create_package(tmp_path: Path) -> tuple[Path, Path, Path, object, object]:
    workbook, database, workbook_input, database_input = audit_fixture(tmp_path)
    artifacts = audit_inputs(workbook_input, [database_input])
    artifact_paths = write_audit_artifacts(tmp_path / "audit-output", artifacts)
    create_audit_package(
        artifact_paths,
        output_dir=tmp_path / "freeze" / AUDIT_ID,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-26T00:00:00+00:00",
    )
    return tmp_path / "freeze" / AUDIT_ID, workbook, database, workbook_input, database_input


def test_package_reproduces_and_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    package, _, database, workbook_input, database_input = create_package(tmp_path)
    verified = verify_audit_package(package, workbook_input=workbook_input, database_inputs=[database_input])
    assert verified["status"] == "valid"
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE source_meta SET value = 'changed' WHERE key = 'no_exotic'")
    with pytest.raises(ScorePriceAuditError, match="hash mismatch"):
        verify_audit_package(package, workbook_input=workbook_input, database_inputs=[database_input])


def test_normalized_output_is_stable_when_database_inputs_are_reordered(tmp_path: Path) -> None:
    workbook = make_workbook(tmp_path / "history.xlsm")
    alpha = make_database(tmp_path / "alpha.sqlite")
    beta = make_database(tmp_path / "beta.sqlite")
    workbook_input = parse_input_spec(f"workbook={workbook}", kind="workbook")
    alpha_input = parse_input_spec(f"alpha={alpha}", kind="database")
    beta_input = parse_input_spec(f"beta={beta}", kind="database")
    first = audit_inputs(workbook_input, [beta_input, alpha_input])
    second = audit_inputs(workbook_input, [alpha_input, beta_input])
    assert canonical_bytes(first) == canonical_bytes(second)


def test_package_checksum_tamper_and_public_redaction_are_rejected(tmp_path: Path) -> None:
    package, workbook, database, workbook_input, database_input = create_package(tmp_path)
    source_inventory = package / "inputs" / "source_inventory.json"
    contents = source_inventory.read_text(encoding="utf-8")
    assert str(workbook) not in contents
    assert str(database) not in contents
    assert "/private/vendor" not in contents
    payload = json.loads(contents)
    assert payload["inputs"][0]["logical_id"]
    source_inventory.write_text(contents + "tamper\n", encoding="utf-8")
    with pytest.raises(ScorePriceAuditError, match="checksum"):
        verify_audit_package(package, workbook_input=workbook_input, database_inputs=[database_input])
