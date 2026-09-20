from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import analyse_settlement_quarantine_rendered as rendered  # noqa: E402


STATIC_MISSING = """<html><body>
<script>M[1][0] = 111; M[5][0] = 555;</script>
<tr id="row_1"><td>a</td></tr>
</body></html>
"""

STATIC_AND_RENDERED_MISSING = """<html><body>
<script>M[1][0] = 111; M[5][0] = 555;</script>
<tr id="row_1"><td>a</td></tr>
</body></html>
"""

RENDERED_BRINGS_BACK_THE_ROW = """<html><body>
<script>M[1][0] = 111; M[5][0] = 555;</script>
<tr id="row_1"><td>a</td></tr>
<tr id="row_5"><td>e</td></tr>
</body></html>
"""


def _entry(issue: str, typeid: int, filename: str, embedded_only, visible_only=None) -> dict:
    return {
        "issue": issue,
        "typeid": typeid,
        "sha256": "a" * 64,
        "url": f"https://example.invalid/{issue}/{typeid}",
        "file": f"pages/{filename}",
        "embedded_only": embedded_only,
        "visible_only": visible_only or [],
    }


def _stage(tmp_path: Path, pages: dict[str, str], doms: dict[str, str]) -> tuple[Path, Path, Path]:
    page_dir, dom_dir = tmp_path / "pages", tmp_path / "rendered"
    page_dir.mkdir(parents=True, exist_ok=True)
    dom_dir.mkdir(parents=True, exist_ok=True)
    for name, text in pages.items():
        (page_dir / name).write_text(text, encoding="utf-8")
    for name, text in doms.items():
        (dom_dir / name).write_text(text, encoding="utf-8")
    return tmp_path / "manifest.json", page_dir, dom_dir


def test_analyse_page_classifies_a_source_side_omission(tmp_path: Path) -> None:
    manifest, pages, doms = _stage(
        tmp_path,
        {"p.html": STATIC_AND_RENDERED_MISSING},
        {"p.dom.html": STATIC_AND_RENDERED_MISSING},
    )
    entry = _entry("20082", 5, "p.html", [[5, "555", 1]])
    row = rendered.analyse_page(entry, pages, doms)
    assert row["status"] == "ok"
    assert row["missing_in_static"] == [5]
    assert row["missing_in_rendered"] == [5]
    assert row["static_equals_rendered"] is True
    assert row["source_omission"] is True
    assert row["parser_defect"] is False
    assert row["receipt_embedded_only"] == [5]


def test_analyse_page_classifies_a_parser_defect_when_rendering_restores_the_row(
    tmp_path: Path,
) -> None:
    _, pages, doms = _stage(
        tmp_path,
        {"p.html": STATIC_MISSING},
        {"p.dom.html": RENDERED_BRINGS_BACK_THE_ROW},
    )
    row = rendered.analyse_page(_entry("20082", 5, "p.html", [[5, "555", 1]]), pages, doms)
    assert row["missing_in_static"] == [5]
    assert row["missing_in_rendered"] == []
    assert row["static_equals_rendered"] is False
    assert row["parser_defect"] is True
    assert row["source_omission"] is False


def test_analyse_page_reports_a_missing_dom_dump(tmp_path: Path) -> None:
    _, pages, doms = _stage(tmp_path, {"p.html": STATIC_MISSING}, {})
    row = rendered.analyse_page(_entry("20082", 5, "p.html", [[5, "555", 1]]), pages, doms)
    assert row["status"] == "dom_missing"
    assert "missing_in_rendered" not in row


def test_analyse_page_fails_closed_when_the_staged_page_is_absent(tmp_path: Path) -> None:
    _, pages, doms = _stage(tmp_path, {}, {"p.dom.html": STATIC_MISSING})
    with pytest.raises(SystemExit, match="staged page missing"):
        rendered.analyse_page(_entry("20082", 5, "p.html", [[5, "555", 1]]), pages, doms)


def test_analyse_page_resolves_the_page_by_basename_not_by_cwd(tmp_path: Path) -> None:
    _, pages, doms = _stage(
        tmp_path,
        {"p.html": STATIC_AND_RENDERED_MISSING},
        {"p.dom.html": STATIC_AND_RENDERED_MISSING},
    )
    entry = _entry("20082", 5, "p.html", [[5, "555", 1]])
    entry["file"] = ".tmpwork/q480/pages/p.html"
    row = rendered.analyse_page(entry, pages, doms)
    assert row["status"] == "ok"
    assert row["missing_in_rendered"] == [5]


def test_summarise_counts_omissions_defects_and_missing_doms(tmp_path: Path) -> None:
    _, pages, doms = _stage(
        tmp_path,
        {"a.html": STATIC_AND_RENDERED_MISSING, "b.html": STATIC_MISSING},
        {"a.dom.html": STATIC_AND_RENDERED_MISSING, "b.dom.html": RENDERED_BRINGS_BACK_THE_ROW},
    )
    rows = [
        rendered.analyse_page(_entry("20082", 5, "a.html", [[5, "555", 1]]), pages, doms),
        rendered.analyse_page(_entry("20123", 6, "b.html", [[5, "555", 1]]), pages, doms),
        {"status": "dom_missing", "issue": "23075", "typeid": 7},
    ]
    summary = rendered.summarise(rows)
    assert summary["schema"] == "bj480_rendered_dom_check_v1"
    assert summary["pages"] == 3
    assert summary["pages_ok"] == 2
    assert summary["pages_dom_missing"] == 1
    assert summary["parser_defect_any"] is True
    assert summary["source_omission_all"] is False
    assert summary["static_equals_rendered_all"] is False
    # A parser defect makes the rendered missing set disagree with the receipt's
    # recorded embedded_only slots by construction.
    assert summary["receipt_matches_rendered"] is False
    assert summary["issues"] == ["20082", "20123"]
    assert summary["per_issue_missing"] == {"20082": [5], "20123": []}


def test_main_writes_the_report_from_declared_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, pages, doms = _stage(
        tmp_path,
        {"p.html": STATIC_AND_RENDERED_MISSING},
        {"p.dom.html": STATIC_AND_RENDERED_MISSING},
    )
    manifest_path.write_text(
        json.dumps([_entry("20082", 5, "p.html", [[5, "555", 1]])]), encoding="utf-8"
    )
    out = tmp_path / "out.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["analyse_settlement_quarantine_rendered.py", "--manifest", str(manifest_path),
         "--pages", str(pages), "--rendered", str(doms), "--output", str(out)],
    )
    assert rendered.main() == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["summary"]["schema"] == "bj480_rendered_dom_check_v1"
    assert report["summary"]["pages"] == 1
    assert report["summary"]["source_omission_all"] is True
    assert report["summary"]["parser_defect_any"] is False
    assert report["pages"][0]["issue"] == "20082"
