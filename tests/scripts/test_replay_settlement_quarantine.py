from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import replay_settlement_quarantine as replay  # noqa: E402


PAGE = """<html><body>
<script>M[1][0] = 111; M[3][0] = 333; M[4][0] = 444;</script>
<table>
<tr id="row_1"><td>a</td></tr>
<tr id="row_3"><td>b</td></tr>
</table>
</body></html>
"""

OTHER_PAGE = """<html><body>
<script>M[1][0] = 111; M[7][0] = 777;</script>
<table>
<tr id="row_1"><td>a</td></tr>
</table>
</body></html>
"""


def _write_page(root: Path, text: str) -> tuple[str, Path]:
    """Stage one raw page under its own sha256, mirroring the sealed archive layout."""
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = root / f"{sha}.html"
    path.write_text(text, encoding="utf-8")
    return sha, path


def _failure(sha: str, typeid: int, embedded_only, visible_only=None) -> dict:
    return {
        "issue": "20082",
        "typeid": typeid,
        "sha256": sha,
        "classification": "quarantined",
        "quarantine_reason": "embedded roster and visible all=1 rows differ",
        "quarantine_detail": {
            "embedded_only": embedded_only,
            "visible_only": visible_only or [],
        },
    }


def _db_with_receipt(path: Path, payload: dict, rows: int = 1) -> Path:
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE receipt (payload_json TEXT)")
        for _ in range(rows):
            con.execute("INSERT INTO receipt VALUES (?)", (json.dumps(payload),))
        con.commit()
    finally:
        con.close()
    return path


def test_load_receipt_returns_the_single_sealed_payload(tmp_path: Path) -> None:
    db = _db_with_receipt(tmp_path / "r.sqlite", {"schema": "nowscore_audit_v1"})
    assert replay.load_receipt(db) == {"schema": "nowscore_audit_v1"}


@pytest.mark.parametrize("rows", [0, 2])
def test_load_receipt_rejects_any_row_count_but_one(tmp_path: Path, rows: int) -> None:
    db = _db_with_receipt(tmp_path / "r.sqlite", {"schema": "nowscore_audit_v1"}, rows=rows)
    with pytest.raises(SystemExit):
        replay.load_receipt(db)


def test_index_raw_pages_keys_pages_by_content_hash(tmp_path: Path) -> None:
    sha, path = _write_page(tmp_path, PAGE)
    assert replay.index_raw_pages(tmp_path) == {sha: path}


def test_analyse_issue_recomputes_the_recorded_embedded_only_slots(tmp_path: Path) -> None:
    sha, _ = _write_page(tmp_path, PAGE)
    result = replay.analyse_issue(
        tmp_path, replay.index_raw_pages(tmp_path), "20082", [_failure(sha, 5, [[4, "444", 1]])]
    )
    assert result["missing_slots"] == [4]
    assert result["typeids"] == [5]
    assert result["per_typeid"][5]["embedded_count"] == 3
    assert result["per_typeid"][5]["visible_count"] == 2
    assert result["per_typeid"][5]["embedded_max_slot"] == 4
    assert result["per_typeid"][5]["visible_max_slot"] == 3


def test_analyse_issue_accepts_agreeing_typeids(tmp_path: Path) -> None:
    sha, _ = _write_page(tmp_path, PAGE)
    result = replay.analyse_issue(
        tmp_path,
        replay.index_raw_pages(tmp_path),
        "20082",
        [_failure(sha, 5, [[4, "444", 1]]), _failure(sha, 6, [[4, "444", 1]])],
    )
    assert result["typeids"] == [5, 6]
    assert result["missing_slots"] == [4]


def test_analyse_issue_fails_closed_when_the_receipt_disagrees(tmp_path: Path) -> None:
    sha, _ = _write_page(tmp_path, PAGE)
    with pytest.raises(SystemExit, match="receipt not reproducible"):
        replay.analyse_issue(
            tmp_path, replay.index_raw_pages(tmp_path), "20082", [_failure(sha, 5, [[5, "x", 1]])]
        )


def test_analyse_issue_fails_closed_on_visible_only(tmp_path: Path) -> None:
    sha, _ = _write_page(tmp_path, PAGE)
    with pytest.raises(SystemExit, match="unexpected visible_only"):
        replay.analyse_issue(
            tmp_path,
            replay.index_raw_pages(tmp_path),
            "20082",
            [_failure(sha, 5, [[4, "444", 1]], visible_only=[[9, "y", 1]])],
        )


def test_analyse_issue_fails_closed_when_typeids_disagree(tmp_path: Path) -> None:
    sha_a, _ = _write_page(tmp_path, PAGE)
    sha_b, _ = _write_page(tmp_path, OTHER_PAGE)
    with pytest.raises(SystemExit, match="typeids disagree"):
        replay.analyse_issue(
            tmp_path,
            replay.index_raw_pages(tmp_path),
            "20082",
            [_failure(sha_a, 5, [[4, "444", 1]]), _failure(sha_b, 6, [[7, "777", 1]])],
        )


def test_analyse_issue_fails_closed_when_the_page_bytes_do_not_match(tmp_path: Path) -> None:
    (tmp_path / f"{'f' * 64}.html").write_text(PAGE, encoding="utf-8")
    with pytest.raises(SystemExit, match="raw page hash mismatch"):
        replay.analyse_issue(
            tmp_path,
            replay.index_raw_pages(tmp_path),
            "20082",
            [_failure("f" * 64, 5, [[4, "444", 1]])],
        )


def test_analyse_issue_fails_closed_when_the_page_is_absent(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="not found under"):
        replay.analyse_issue(
            tmp_path,
            replay.index_raw_pages(tmp_path),
            "20082",
            [_failure("f" * 64, 5, [[4, "444", 1]])],
        )


def test_main_writes_a_receipt_reproduced_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    sha_20082, _ = _write_page(raw, PAGE)
    sha_20123, _ = _write_page(raw, OTHER_PAGE)

    receipt = {
        "data_sha256": "e" * 64,
        "capture_failures": [
            _failure(sha_20082, 5, [[4, "444", 1]]),
            dict(_failure(sha_20123, 6, [[7, "777", 1]]), issue="20123"),
        ],
    }
    db = _db_with_receipt(tmp_path / "r.sqlite", receipt)
    out = tmp_path / "out.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["replay_settlement_quarantine.py", "--replay-db", str(db), "--raw-root", str(raw),
         "--output", str(out)],
    )
    assert replay.main() == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema"] == "bj480_quarantine_replay_v1"
    assert report["receipt_sha256_source"] == "e" * 64
    assert report["failure_count"] == 2
    assert report["quarantined_issue_count"] == 2
    assert report["missing_slot_total"] == 2
    assert report["classification_counts"] == {"quarantined": 2}
    assert report["typeids_per_issue"] == {"20082": [5], "20123": [6]}
    assert report["conclusion"]["verdict"] == "source_response_missing_rendered_rows"
    assert report["conclusion"]["parser_defect"] is False
    assert report["conclusion"]["parser_relaxation_required"] is False
    assert report["conclusion"]["receipt_reproduced"] is True
