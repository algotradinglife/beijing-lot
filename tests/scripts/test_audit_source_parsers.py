"""Contract examples for the source-parser audit. No network."""
import json
from pathlib import Path

from scripts.audit_source_parsers import audit, evidence_nature, parser_modules, related_tests


def test_classifies_inline_samples_and_committed_bytes_differently() -> None:
    """A test that names an inline constant is not evidence of the source's bytes."""
    assert evidence_nature("blob = '<html>...</html>'\nPAGE = \"\"\"<td>x</td>\"\"\"") == (
        "no committed bytes; inline samples only")
    assert evidence_nature("payload = (root / 'fixtures/x.html').read_bytes()") == (
        "committed source bytes")
    assert evidence_nature("payload = gzip.open('fixtures/a.html.gz', 'rb').read()") == (
        "committed source bytes")
    assert evidence_nature("view = data['x'].html") == "no committed bytes, no named sample"


def test_a_mention_of_html_is_not_evidence() -> None:
    """The earlier heuristic accepted the string '.html' anywhere and mis-reported parsers."""
    assert evidence_nature("assert doc.html == 'x'") == (
        "no committed bytes, no named sample")
    assert evidence_nature("assert 'a.html' in names") == "no committed bytes, no named sample"


def test_finds_parsers_and_their_tests(tmp_path: Path) -> None:
    """Every module that parses markup is listed, with the tests that name it."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "page_reader.py").write_text(
        "from bs4 import BeautifulSoup\n\ndef parse_page(payload):\n    return None\n",
        encoding="utf-8")
    (tmp_path / "src" / "unrelated.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_page_reader.py").write_text(
        "from src.page_reader import parse_page\n\n\ndef test_it(tmp_path):\n"
        "    assert parse_page((tmp_path / 'fixtures/a.html').read_bytes()) is None\n",
        encoding="utf-8")
    found = parser_modules(tmp_path)
    assert [path.name for path in found] == ["page_reader.py"]
    tests = {path: path.read_text(encoding="utf-8")
             for path in (tmp_path / "tests").rglob("test_*.py")}
    assert [path.name for path in related_tests(found[0], tests)] == ["test_page_reader.py"]


def test_audit_reports_the_repository_it_is_given(tmp_path: Path) -> None:
    """The report is a pure function of the tree: schema, rows and the fixture inventory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "sample.html.gz").write_bytes(b"")
    (tmp_path / "src" / "reader.py").write_text(
        "from bs4 import BeautifulSoup\n", encoding="utf-8")
    report = audit(tmp_path)
    assert report["schema"] == "source_parser_audit_v1"
    assert report["parsers"] == [
        {"parser": "src/reader.py", "tests": [], "page_bytes": "untested"}]
    assert report["real_page_fixtures"] == ["tests/fixtures/sample.html.gz"]
    # a parser with no test at all is still on the risk list
    assert report["without_source_bytes"] == ["src/reader.py"]
    json.dumps(report)
