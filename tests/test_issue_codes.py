"""The issue code is the authority for the year, checked against the retired registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.issue_codes import IssueCodeError, issue_year

FIXTURE = Path(__file__).parent / "fixtures" / "issue_codes" / "registry_years.json"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("090918", 2009),      # six-digit form, 2009-2019
        ("191205", 2019),
        ("26092", 2026),       # five-digit form, 2020 onward
        ("20011", 2020),       # first five-digit year
        ("26096", 2026),
    ],
)
def test_issue_year_reads_the_year_the_code_names(code: str, expected: int) -> None:
    assert issue_year(code) == expected


@pytest.mark.parametrize(
    "code",
    ["", "2", "26", "1234567", "26a92", "abcdef", " 26O92 ", "26.92", None, "０２６０９２"],
)
def test_a_code_that_does_not_match_the_format_has_no_year(code) -> None:
    """Raising matters: deriving a year from a malformed code dates rows by whatever it starts with."""
    with pytest.raises(IssueCodeError):
        issue_year(code)


def test_the_five_digit_range_starts_at_2020() -> None:
    assert issue_year("20011") == 2020
    with pytest.raises(IssueCodeError):
        issue_year("19011")     # five digits below 20 predates the range


def test_every_year_the_retired_registry_held_is_derivable_from_the_code() -> None:
    """The table the census used to consult carried nothing the code does not already say.

    The fixture is the retired store's own `issues` table, so this is the claim that made dropping
    the registry read safe: if any row disagreed, the year would have had to come from somewhere
    other than the code.
    """
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = fixture["rows"]
    assert len(rows) > 2000, "the fixture should carry the full registry"

    disagreed = [
        (code, recorded, issue_year(code))
        for code, recorded in rows
        if issue_year(code) != recorded
    ]
    assert disagreed == [], f"{len(disagreed)} row(s) disagree: {disagreed[:5]}"


def test_the_fixture_records_where_it_came_from() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["source"].endswith("500_bjdc.sqlite.bak")
    assert fixture["source_table"] == "issues"
    codes = [code for code, _ in fixture["rows"]]
    assert len(set(codes)) == len(codes), "issue codes are unique in the registry"
    assert {len(code) for code in codes} <= {5, 6}


def test_the_producer_emits_the_contract_label(tmp_path) -> None:
    """The label pipelines assert on must be the one the producer writes.

    They compare against the name as a string, so nothing but this example keeps the producer's
    value and the contract's value the same word.
    """
    import sqlite3

    from src.divergence_materializer.data import load_issue_roles
    from src.issue_codes import SOURCE_ISSUE_DATE_SOURCE

    candidate = tmp_path / "candidate.sqlite"
    codes = [f"14{n:04d}" for n in range(1, 405)] + [f"26{n:03d}" for n in range(1, 405)]
    with sqlite3.connect(candidate) as connection:
        connection.execute(
            "CREATE TABLE inventory (issue_code TEXT, match_idx INTEGER, kickoff_ts TEXT)"
        )
        connection.executemany(
            "INSERT INTO inventory VALUES (?, ?, ?)",
            [(code, 1, "2026-01-01 12:00:00") for code in codes],
        )

    roles = load_issue_roles(candidate)
    assert roles["issue_date_source"].eq(SOURCE_ISSUE_DATE_SOURCE).all()
    assert roles["issue_year"].notna().all()
    assert roles["issue_year"].eq(roles["issue_code"].map(issue_year)).all()
    assert set(roles["issue_year"]) == {2014, 2026}
