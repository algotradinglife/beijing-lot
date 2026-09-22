"""Contract examples for the source-parser audit. No network."""
import json
import subprocess
from pathlib import Path

import pytest

from scripts.audit_source_parsers import (
    audit,
    evidence_nature,
    parser_modules,
    related_tests,
    revision_files,
)


def test_classifies_inline_samples_and_fixture_reads_differently() -> None:
    """A test that names an inline constant is not evidence of the source's bytes."""
    assert evidence_nature("blob = '<html>...</html>'\nPAGE = \"\"\"<td>x</td>\"\"\"") == (
        "inline samples only")
    assert evidence_nature("payload = (root / 'fixtures/x.html').read_bytes()") == "reads fixtures"
    assert evidence_nature("payload = gzip.open('fixtures/a.html.gz', 'rb').read()") == (
        "reads fixtures")
    assert evidence_nature("view = data['x'].html") == (
        "no fixture reference in the tests that name it")


def test_a_mention_of_html_is_not_evidence() -> None:
    """The earlier heuristic accepted the string '.html' anywhere and mis-reported parsers."""
    assert evidence_nature("assert doc.html == 'x'") == (
        "no fixture reference in the tests that name it")
    assert evidence_nature("assert 'a.html' in names") == (
        "no fixture reference in the tests that name it")


def test_a_joined_fixtures_path_with_gzip_counts_as_committed_bytes() -> None:
    """The second version only matched a literal "fixtures/x.html" and missed this shape.

    src/settlement_halftime_evidence.py stayed flagged after a test was added that reads a
    preserved page this way.
    """
    joined = (
        '_FIXTURES = Path(__file__).parent / "fixtures" / "halftime_evidence"\n'
        'path = (_FIXTURES / case["page"]).resolve()\n'
        'payload = gzip.open(path, "rb").read()\n')
    assert evidence_nature(joined) == "reads fixtures"
    assert evidence_nature('text = (ROOT / "tests" / "fixtures" / "a.json").read_text()') == (
        "reads fixtures")


def test_a_fixtures_reference_without_a_read_is_not_evidence() -> None:
    """Naming the folder is not evidence; the bytes have to be read."""
    assert evidence_nature('assert "fixtures" in str(path)') == (
        "no fixture reference in the tests that name it")


def test_finds_parsers_and_their_tests() -> None:
    """Every module that parses markup is listed, with the tests that name it."""
    files = {
        "src/page_reader.py": "from bs4 import BeautifulSoup\n\ndef parse_page(payload):\n    return None\n",
        "src/unrelated.py": "VALUE = 1\n",
        "scripts/tool.py": "from bs4 import BeautifulSoup\n",
        "tests/test_page_reader.py": "from src.page_reader import parse_page\n",
        "tests/test_other.py": "def test_nothing():\n    assert True\n",
    }
    assert parser_modules(Path("."), files) == ["scripts/tool.py", "src/page_reader.py"]
    tests = {name: text for name, text in files.items() if Path(name).name.startswith("test_")}
    assert related_tests("src/page_reader.py", tests) == ["tests/test_page_reader.py"]
    assert related_tests("src/unrelated.py", tests) == []


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True).stdout.decode("utf-8")


@pytest.fixture
def committed(tmp_path: Path) -> Path:
    """A repository whose working tree differs from its committed revision."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "src" / "reader.py").write_text("from bs4 import BeautifulSoup\n", encoding="utf-8")
    (tmp_path / "tests" / "test_reader.py").write_text(
        "import gzip\nfrom pathlib import Path\n\nfrom src.reader import parse_page\n\n\n"
        "def test_it():\n"
        "    payload = gzip.open(Path(__file__).parent / 'fixtures' / 'a.html.gz', 'rb').read()\n"
        "    assert payload\n", encoding="utf-8")
    (tmp_path / "tests" / "fixtures" / "a.html.gz").write_bytes(b"")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    # an untracked module and a staged one: neither belongs to the revision
    (tmp_path / "src" / "in_flight.py").write_text(
        "from bs4 import BeautifulSoup\n", encoding="utf-8")
    (tmp_path / "scripts" / "staged.py").write_text(
        "from bs4 import BeautifulSoup\n", encoding="utf-8")
    _git(tmp_path, "add", "scripts/staged.py")
    return tmp_path


def test_the_report_comes_from_the_revision_not_the_working_tree(committed: Path) -> None:
    """A report built from whatever is on disk cannot be reproduced from a clean checkout.

    The first version scanned the working tree and counted a module another agent had left
    untracked, so the committed report did not describe the revision it claimed to.
    """
    report = audit(committed, "HEAD")
    assert [row["parser"] for row in report["parsers"]] == ["src/reader.py"]
    assert report["parsers"][0]["tests"] == ["tests/test_reader.py"]
    assert report["parsers"][0]["page_bytes"] == "reads fixtures"
    assert report["revision"] == _git(committed, "rev-parse", "HEAD").strip()
    assert report["real_page_fixtures"] == ["tests/fixtures/a.html.gz"]
    json.dumps(report)


def test_the_report_binds_what_it_read(committed: Path) -> None:
    """Same revision, same digest; a different revision changes it."""
    first = audit(committed, "HEAD")
    assert audit(committed, "HEAD")["scanned_sha256"] == first["scanned_sha256"]
    (committed / "src" / "reader.py").write_text(
        "from bs4 import BeautifulSoup\n\n# a new comment\n", encoding="utf-8")
    _git(committed, "add", "-A")
    _git(committed, "commit", "-qm", "change")
    second = audit(committed, "HEAD")
    assert second["scanned_sha256"] != first["scanned_sha256"]
    assert second["revision"] != first["revision"]


def test_rejects_a_revision_with_no_python(committed: Path) -> None:
    """Fail closed rather than reporting an empty scan as a clean result."""
    empty = _git(committed, "commit-tree", "-m", "empty",
                 _git(committed, "mktree").strip()).strip()
    with pytest.raises(SystemExit):
        revision_files(committed, empty)


def test_every_registered_gap_is_a_tracked_parser() -> None:
    """A gap list may only name parsers the repository tracks.

    One entry in the delivery's gap list named a script that existed only on one machine's disk:
    it had no history and no guard test, so "add a preserved page for it" was not actionable. The
    register is checked as data here, against the scan of this checkout.
    """
    from scripts.audit_source_parsers import GAP_REGISTER

    root = Path(__file__).resolve().parents[2]
    assert (root / "src").is_dir(), "the project checkout"
    scanned = {row["parser"] for row in audit(root, "HEAD")["parsers"]}
    assert GAP_REGISTER, "the register should not be empty"
    for gap, entry in GAP_REGISTER.items():
        assert entry["status"] in {"open", "resolved", "blocked", "owned-elsewhere",
                                   "deprecated-line", "source-retired"}, gap
        assert entry.get("why"), gap
        assert gap in scanned, f"{gap} is registered but is not a tracked parser"


def test_a_registered_reusable_input_exists() -> None:
    """If the register names an input that is already preserved, it has to be there.

    The first version of this entry claimed no copy of either input existed; the context pages
    were already committed under tests/fixtures/fundamentals_census, so the claim was too strong
    and the reusable inputs are now named.
    """
    from scripts.audit_source_parsers import GAP_REGISTER

    root = Path(__file__).resolve().parents[2]
    named = [name for entry in GAP_REGISTER.values() for name in entry.get("reusable_inputs", [])]
    assert named, "the blocked entry should name what is already usable"
    for name in named:
        assert (root / name).is_file(), f"{name} is registered as reusable but is not committed"
