"""Contract examples for appending newly settled issues. No network, no fixtures on disk.

The page builder mirrors the live board's markup (``dropIssueNum`` selector, labelled SP
cells, ``row_N`` fixtures) because the appended rows must come from the same parser the
release build uses.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.nowscore_settlement import PLAYS, TITLE, TYPEID_LABELS, source_url
from src.settlement_issue_addition import add_issues, canonical_content_sha256, read_bundle

# One settled result per play for a 3-1 home win (1-0 at half time, level line).
RESULT = {5: "胜", 6: "4球", 7: "上+双", 8: "3:1", 9: "胜-胜"}


def live_page(*, issue: str, typeid: int, slot: int = 1, status: str = "完场",
              ft: str = "3-1", ht: str = "1-0", settle: bool = True,
              reference: bool = False, handicap: str = "0") -> bytes:
    """One live-board page for one play.

    ``settle`` publishes the settlement SP on the winning option; ``reference`` publishes
    pre-match odds on every option, which is what the board serves while a fixture is
    unplayed and what the applier must not mistake for a settlement.
    """
    labels = TYPEID_LABELS[typeid]
    winner = RESULT.get(typeid)
    values = {}
    if reference:
        values = {label: "2.10" for label in labels}
    elif settle:
        values = {winner: "5.50"}
    cells = []
    for index, label in enumerate(reversed(labels), 1):
        title = {"胜": "主胜", "平": "平局", "负": "客胜"}.get(label, label)
        prefix = f'<b>{label.replace("其他", "其它")}</b><br>' if typeid == 8 else ""
        cells.append(f'<td title="{title}">{prefix}'
                     f'<span id="sp_1_{index}">{values.get(label, "")}</span></td>')
    odds = "".join(cells)
    line = f"<td>{handicap}</td>" if typeid == 5 else ""
    row = f'''<tr id="row_{slot}" matchid="{slot}" polygoal="0" cansale="false" name="2025-05-13" gamename="测试联赛">
      <td>{slot}</td><td>测试联赛</td><td>23:30</td><td title="截止时间：2025-05-13 23:25">{status}</td>
      <td><a id="HomeTeam_{slot}" onmouseover="getMyHTML2('/temp/{slot}_1.htm')">主队{slot}</a></td>{line}<td>{ft}</td><td><a id="GuestTeam_{slot}" onmouseover="getMyHTML2('/temp/{slot}_2.htm')">客队{slot}</a></td><td>{ht}</td>
      <td><a href="/sp/danchang/{issue}_{slot}_{typeid}.html">SP</a></td>{odds if typeid != 8 else ''}</tr>'''
    extra = f'<tr id="tr_{slot}"><td><table><tr>{odds}</tr></table></td></tr>' if typeid == 8 else ""
    return (f'<html><title>{TITLE[typeid]}</title><script>M[{slot}][0]={slot};</script>'
            f'<select id="dropIssueNum"><option selected value="{issue}">{issue}</option>'
            f'</select><table>{row}{extra}</table></html>').encode()


def bundle(tmp: Path, *, issue: str = "26093", typeids=None, **kwargs) -> Path:
    """Write a capture bundle the way the capture entry point does, and return its root."""
    import hashlib
    root = tmp / f"bundle-{issue}"
    (root / "raw").mkdir(parents=True, exist_ok=True)
    captures = []
    for typeid in sorted(typeids or PLAYS):
        payload = live_page(issue=issue, typeid=typeid, **kwargs)
        sha = hashlib.sha256(payload).hexdigest()
        (root / "raw" / (sha + ".html")).write_bytes(payload)
        captures.append({"issue": issue, "typeid": typeid, "url": source_url(issue, typeid),
                         "received_at": "2026-09-21T12:00:00+00:00", "sha256": sha})
    manifest = {"schema": "nowscore_history_batch_v1", "source": "nowscore",
                "batch": {"batch_id": "plays-9001", "issues": [issue]},
                "controls": [], "captures": captures, "requested_issues": [issue]}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def replace_play(root: Path, issue: str, typeid: int, payload: bytes) -> None:
    """Swap one play's page in a bundle, keeping its manifest and raw files consistent."""
    import hashlib
    con = None
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    captures = [entry for entry in manifest["captures"]
                if not (entry["issue"] == issue and entry["typeid"] == typeid)]
    old = [entry for entry in manifest["captures"]
           if entry["issue"] == issue and entry["typeid"] == typeid]
    for entry in old:
        (root / "raw" / (entry["sha256"] + ".html")).unlink(missing_ok=True)
    sha = hashlib.sha256(payload).hexdigest()
    (root / "raw" / (sha + ".html")).write_bytes(payload)
    captures.append({"issue": issue, "typeid": typeid, "url": source_url(issue, typeid),
                     "received_at": "2026-09-21T12:00:00+00:00", "sha256": sha})
    manifest["captures"] = sorted(captures, key=lambda entry: (entry["issue"], entry["typeid"]))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    del con


def release(tmp: Path, *, issues=("26092",), fixtures=2) -> Path:
    """A minimal sealed release: the tables the applier and the replay read."""
    path = tmp / "release.sqlite"
    con = sqlite3.connect(path)
    con.executescript('''
      CREATE TABLE capture (issue TEXT, typeid INTEGER, source_url TEXT, received_at TEXT,
                            sha256 TEXT, PRIMARY KEY(issue,typeid));
      CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT, slot INTEGER,
                            play TEXT, native_match_id TEXT, status TEXT, score TEXT,
                            halftime_score TEXT, expected_option TEXT, source_sha256 TEXT,
                            source_url TEXT, received_at TEXT, payload_json TEXT);
      CREATE TABLE option_sp (observation_id INTEGER, option TEXT, raw_sp TEXT, sp REAL,
                            cell_id TEXT, FOREIGN KEY(observation_id) REFERENCES observation(observation_id));
      CREATE TABLE finding (issue TEXT, slot INTEGER, play TEXT, code TEXT, detail TEXT,
                            source_sha256 TEXT);
      CREATE TABLE receipt (payload_json TEXT);
    ''')
    observation_id = 0
    for issue in issues:
        for slot in range(1, fixtures + 1):
            for play in PLAYS.values():
                observation_id += 1
                con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (observation_id, issue, slot, play, f"9{slot}", "完场", "2-0",
                             "1-0", "胜", "a" * 64, "https://example/old", "2026-09-20T00:00:00+00:00",
                             '{"handicap": 0}'))
                con.execute("INSERT INTO option_sp VALUES (?,?,?,?,?)",
                            (observation_id, "胜", "3.10", 3.1, "old"))
    con.execute("INSERT INTO receipt VALUES (?)", (json.dumps({"schema": "nowscore_audit_v1"}),))
    con.commit()
    con.close()
    return path


def rows(db: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_appends_a_new_issue_from_its_captured_bundle(tmp_path: Path) -> None:
    """A settled issue absent from the release is appended from its raw bytes."""
    db = release(tmp_path)
    before = rows(db, "SELECT COUNT(*) FROM observation")[0][0]
    result = add_issues(db, bundle(tmp_path), tmp_path / "backup.sqlite",
                        approval_note="已批准：新增期次 26093")
    assert result["status"] == "added"
    assert result["added_issues"] == ["26093"]
    assert result["added_fixtures"] == 1
    assert result["added_observations"] == len(PLAYS)
    assert rows(db, "SELECT COUNT(*) FROM observation")[0][0] == before + len(PLAYS)
    assert len(rows(db,
                    "SELECT 1 FROM observation WHERE issue='26093'")) == len(PLAYS)
    # ids continue from the release maximum, so the release stays internally consistent
    ids = [r[0] for r in rows(db, "SELECT observation_id FROM observation ORDER BY observation_id")]
    assert ids == list(range(1, len(ids) + 1))
    assert rows(db, "SELECT COUNT(*) FROM capture WHERE issue='26093'")[0][0] == len(PLAYS)


def test_the_content_hash_ignores_the_order_issues_were_added(tmp_path: Path) -> None:
    """The batch binds content, so appending A then B equals B then A."""
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    db_a, db_b = release(first), release(second)
    add_issues(db_a, bundle(first, issue="26093"), first / "b1.sqlite", approval_note="n")
    add_issues(db_a, bundle(first, issue="26094"), first / "b2.sqlite", approval_note="n")
    add_issues(db_b, bundle(second, issue="26094"), second / "b1.sqlite", approval_note="n")
    add_issues(db_b, bundle(second, issue="26093"), second / "b2.sqlite", approval_note="n")
    issues = ["26093", "26094"]
    con_a, con_b = sqlite3.connect(db_a), sqlite3.connect(db_b)
    try:
        assert canonical_content_sha256(con_a, issues) == canonical_content_sha256(con_b, issues)
    finally:
        con_a.close()
        con_b.close()


def test_refuses_an_issue_whose_fixture_is_not_settled(tmp_path: Path) -> None:
    """Pre-match reference odds are not a settlement, so an unplayed fixture is skipped."""
    db = release(tmp_path)
    root = bundle(tmp_path, reference=True, status="未开赛", ft="", ht="")
    result = add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")
    assert result["status"] == "nothing_to_add"
    assert result["skipped"][0]["reason"].startswith("not a completed settlement")
    assert result["skipped"][0]["problems"]
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='26093'")[0][0] == 0


def test_accepts_a_cancelled_fixture_with_no_options(tmp_path: Path) -> None:
    """A cancelled fixture reports no result and is legitimately option-less."""
    db = release(tmp_path)
    root = bundle(tmp_path, settle=False, status="取消", ft="-", ht="-")
    result = add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")
    assert result["status"] == "added"
    assert result["added_observations"] == len(PLAYS)


def test_accepts_a_bucket_the_source_never_prices(tmp_path: Path) -> None:
    """The real release carries settled 单场比分 rows whose bucket has no SP at all.

    A score that pools into 胜其他 is settled even though no option is priced; a rule that
    demanded exactly one SP would reject rows the build itself wrote.
    """
    db = release(tmp_path)
    root = bundle(tmp_path)
    replace_play(root, "26093", 8, live_page(issue="26093", typeid=8, ft="5-2", ht="2-1",
                                             settle=False))
    result = add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")
    assert result["status"] == "added"
    assert result["resolved_fixtures"] == len(PLAYS)
    assert rows(db, "SELECT expected_option FROM observation "
                    "WHERE issue='26093' AND play='bf'")[0][0] == "胜其他"


def test_refuses_an_issue_with_a_fixture_that_is_still_playing(tmp_path: Path) -> None:
    """A running fixture must never be frozen as final, and nothing may be added.

    The live board reports a play status such as 下 while a match runs and a running score.
    Adding it would freeze a transient value, and a later run would skip the issue because
    the release already carries it, so the whole issue is refused instead.
    """
    db = release(tmp_path)
    root = bundle(tmp_path)
    replace_play(root, "26093", 9, live_page(issue="26093", typeid=9, status="下",
                                             ft="3-1", ht="1-0", settle=False))
    result = add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")
    assert result["status"] == "nothing_to_add"
    assert "not a completed settlement" in result["skipped"][0]["problems"][0]
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='26093'")[0][0] == 0
    assert not (tmp_path / "backup.sqlite").exists()


def test_refuses_an_abnormal_fixture_that_carries_a_result(tmp_path: Path) -> None:
    """The release holds abnormal rows with score '-' and no derived result; a score is a contradiction."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    replace_play(root, "26093", 9, live_page(issue="26093", typeid=9, status="中断",
                                             ft="2-1", ht="1-0", settle=False))
    result = add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")
    assert result["status"] == "nothing_to_add"
    assert "abnormal status carries a result" in result["skipped"][0]["problems"][0]


def test_refuses_a_bundle_whose_page_carries_no_rows(tmp_path: Path) -> None:
    """A source_empty page passes the manifest check but leaves a play missing."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    entry = next(e for e in manifest["captures"] if e["typeid"] == 7)
    (root / "raw" / (entry["sha256"] + ".html")).write_bytes(b"")
    entry["classification"] = "source_empty"
    entry["sha256"] = hashlib.sha256(b"").hexdigest()
    (root / "raw" / (entry["sha256"] + ".html")).write_bytes(b"")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="miss a play"):
        add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")
    assert not (tmp_path / "backup.sqlite").exists()


def test_refuses_a_capture_url_that_is_not_the_source(tmp_path: Path) -> None:
    """The build validates capture identity; a weaker boundary here would let it drift."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["captures"][0]["url"] = "https://example.invalid/anything"
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Capture URL"):
        add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")


def test_refuses_a_capture_time_without_a_timezone(tmp_path: Path) -> None:
    """Collection time is evidence, so it must be an explicit instant."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["captures"][0]["received_at"] = "2026-09-21T12:00:00"
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="timezone"):
        add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")


def test_a_failure_after_writing_rolls_back_and_releases_the_backup(
        tmp_path: Path, monkeypatch) -> None:
    """Nothing may be half-written, and the reserved backup must not be left behind."""
    db = release(tmp_path)
    before = rows(db, "SELECT COUNT(*) FROM observation")[0][0]
    import src.settlement_issue_addition as module
    monkeypatch.setattr(module, "canonical_content_sha256",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        add_issues(db, bundle(tmp_path), tmp_path / "backup.sqlite", approval_note="n")
    assert rows(db, "SELECT COUNT(*) FROM observation")[0][0] == before
    assert not (tmp_path / "backup.sqlite").exists()
    monkeypatch.undo()
    assert add_issues(db, bundle(tmp_path), tmp_path / "backup.sqlite",
                      approval_note="n")["status"] == "added"


def test_refuses_a_backup_path_that_already_exists(tmp_path: Path) -> None:
    """Refusing an existing path keeps a prior snapshot from being overwritten."""
    db = release(tmp_path)
    (tmp_path / "backup.sqlite").write_bytes(b"occupied")
    with pytest.raises(FileExistsError):
        add_issues(db, bundle(tmp_path), tmp_path / "backup.sqlite", approval_note="n")


def test_leaves_the_build_receipt_untouched(tmp_path: Path) -> None:
    """The addition records its own batch; the build's receipt stays the build's."""
    db = release(tmp_path)
    before = rows(db, "SELECT payload_json FROM receipt")[0][0]
    add_issues(db, bundle(tmp_path), tmp_path / "backup.sqlite", approval_note="n")
    assert rows(db, "SELECT payload_json FROM receipt")[0][0] == before
    assert rows(db, "SELECT COUNT(*) FROM issue_addition_batch")[0][0] == 1


def test_skips_an_issue_the_release_already_carries(tmp_path: Path) -> None:
    """The set to add is derived from the release, so a present issue is skipped."""
    db = release(tmp_path, issues=("26092", "26093"))
    result = add_issues(db, bundle(tmp_path, issue="26093"), tmp_path / "backup.sqlite",
                        approval_note="n")
    assert result["status"] == "nothing_to_add"
    assert result["skipped"] == [{"issue": "26093", "reason": "already in the release"}]


def test_refuses_a_bundle_that_misses_a_play(tmp_path: Path) -> None:
    """A partial bundle would append an issue no later run could complete."""
    db = release(tmp_path)
    root = bundle(tmp_path, typeids=[5, 6])
    with pytest.raises(ValueError, match="issue/play domain"):
        add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")
    assert not (tmp_path / "backup.sqlite").exists()


def test_refuses_a_bundle_whose_bytes_changed(tmp_path: Path) -> None:
    """The raw bytes are the anchor: a changed page must stop the run."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    target = next((root / "raw").iterdir())
    target.write_bytes(target.read_bytes().replace(b"5.50", "9.90".encode()))
    with pytest.raises(ValueError, match="bytes changed"):
        add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")


def test_repeating_the_same_bundle_is_a_verified_no_op(tmp_path: Path) -> None:
    """The guard re-checks the rows it added, then reports already_applied."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    add_issues(db, root, tmp_path / "first.sqlite", approval_note="n")
    again = add_issues(db, root, tmp_path / "second.sqlite", approval_note="n")
    assert again["status"] == "already_applied"
    assert again["mismatches"] == []
    assert not (tmp_path / "second.sqlite").exists()


def test_a_changed_added_row_refuses_the_rerun(tmp_path: Path) -> None:
    """A silently edited value must stop the idempotent rerun."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    add_issues(db, root, tmp_path / "first.sqlite", approval_note="n")
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET score='9-9' WHERE issue='26093'")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="source hash changed|changed"):
        add_issues(db, root, tmp_path / "second.sqlite", approval_note="n")


def test_a_row_replaced_since_it_was_added_refuses_the_rerun(tmp_path: Path) -> None:
    """Swapping the row at an added key must be detectable."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    add_issues(db, root, tmp_path / "first.sqlite", approval_note="n")
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET observation_id=9999 WHERE issue='26093' AND play='spf'")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="changed"):
        add_issues(db, root, tmp_path / "second.sqlite", approval_note="n")


def test_an_empty_bundle_is_refused(tmp_path: Path) -> None:
    """No captures means no evidence; the run must fail closed."""
    db = release(tmp_path)
    root = tmp_path / "empty"
    (root / "raw").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps(
        {"schema": "nowscore_history_batch_v1", "captures": [], "requested_issues": []}),
        encoding="utf-8")
    with pytest.raises(ValueError, match="no captures"):
        add_issues(db, root, tmp_path / "backup.sqlite", approval_note="n")


def test_refuses_a_wrong_bundle_schema(tmp_path: Path) -> None:
    """A foreign document must not be mistaken for a capture bundle."""
    root = tmp_path / "other"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps({"schema": "something_else"}),
                                        encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        read_bundle(root)


def test_refuses_an_approval_note_that_is_blank(tmp_path: Path) -> None:
    """Every write needs a recorded authorisation."""
    db = release(tmp_path)
    with pytest.raises(ValueError, match="approval note"):
        add_issues(db, bundle(tmp_path), tmp_path / "backup.sqlite", approval_note="  ")


def test_refuses_when_the_paths_are_not_distinct(tmp_path: Path) -> None:
    """The backup must not be the release, and the bundle must not be either."""
    db = release(tmp_path)
    with pytest.raises(ValueError, match="distinct"):
        add_issues(db, bundle(tmp_path), db, approval_note="n")
