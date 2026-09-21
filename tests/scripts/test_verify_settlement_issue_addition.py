"""Contract examples for replaying an issue addition. No network.

The replay is the verification: it takes the bundle's raw bytes and the pre-addition
backup from its own arguments and re-derives every expected value, so these examples check
that a mutated release or a mutated bundle is caught rather than trusted.
"""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in (str(ROOT), str(ROOT / "tests")):
    if path not in sys.path:
        sys.path.insert(0, path)

from scripts.verify_settlement_issue_addition import build_report, main  # noqa: E402
from src.settlement_issue_addition import add_issues  # noqa: E402
from test_settlement_issue_addition import (  # noqa: E402
    bundle,
    release,
    replace_play,
    rows,
)


@pytest.fixture()
def applied(tmp_path: Path):
    """A release with one appended issue, plus the bundle and backup that prove it."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    backup = tmp_path / "before.sqlite"
    add_issues(db, root, backup, approval_note="已批准：新增期次 26093")
    return db, root, backup


def test_replay_reproduces_an_appended_issue(applied) -> None:
    """Every re-derived value matches, so the addition verifies."""
    db, root, backup = applied
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is True
    assert report["issues_owed"] == ["26093"]
    assert report["issues_already_present"] == []
    assert report["mismatches"] == []
    assert report["checked_observations"] == 5


def test_replay_proves_the_issue_was_absent_from_the_backup(applied) -> None:
    """The backup is the anchor for 'this issue is new'."""
    db, root, backup = applied
    con = sqlite3.connect(backup)
    try:
        assert con.execute("SELECT COUNT(*) FROM observation WHERE issue='26093'").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM observation WHERE issue='26092'").fetchone()[0] > 0
    finally:
        con.close()


def test_replay_catches_a_changed_score(applied) -> None:
    """A silently edited score must fail the replay."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET score='9-9' WHERE issue='26093'")
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert report["mismatches"]


def test_replay_catches_a_changed_option_vector(applied) -> None:
    """The options are evidence too: rewriting an SP must fail."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("UPDATE option_sp SET sp=99.9, raw_sp='99.9' WHERE observation_id="
                "(SELECT observation_id FROM observation WHERE issue='26093' AND play='spf')")
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert any("database_options" in mismatch for mismatch in report["mismatches"])


def test_replay_catches_a_deleted_row(applied) -> None:
    """A deleted observation must be noticed, not silently skipped."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("DELETE FROM observation WHERE issue='26093' AND play='spf'")
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert any(mismatch.get("reason") == "the bundle's fixture is missing"
               for mismatch in report["mismatches"])


def test_replay_catches_a_duplicated_row(applied) -> None:
    """A duplicate at an added key must be a multiset violation, not a hidden twin."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("""INSERT INTO observation SELECT observation_id+100000, issue, slot, play,
                   native_match_id, status, score, halftime_score, expected_option,
                   source_sha256, source_url, received_at, payload_json FROM observation
                   WHERE issue='26093' AND play='spf'""")
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert any("observations_at_key" in mismatch for mismatch in report["mismatches"])


def test_replay_catches_a_changed_capture_record(applied) -> None:
    """The capture row is the page's provenance; rebinding it must fail."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("UPDATE capture SET sha256=? WHERE issue='26093' AND typeid=5",
                ("b" * 64,))
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert any("capture record" in mismatch.get("reason", "")
               for mismatch in report["mismatches"])


def test_replay_catches_a_changed_content_hash(applied) -> None:
    """The batch's canonical-order claim must match the release's actual content."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("UPDATE issue_addition_batch SET content_sha256=?", ("c" * 64,))
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert any("canonical content hash" in mismatch.get("reason", "")
               for mismatch in report["mismatches"])


def test_replay_catches_a_missing_issue(applied) -> None:
    """Deleting a whole added issue must fail, not empty the check."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("DELETE FROM observation WHERE issue='26093'")
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert any(mismatch.get("reason") == "issue is missing entirely"
               for mismatch in report["mismatches"])


def test_replay_catches_a_bundle_whose_bytes_changed(applied) -> None:
    """The bundle is the anchor: a changed page must stop the replay."""
    db, root, backup = applied
    target = next((root / "raw").iterdir())
    target.write_bytes(target.read_bytes().replace(b"5.50", b"9.90"))
    with pytest.raises(ValueError, match="bytes changed"):
        build_report(db, root, backup)


def test_replay_reports_nothing_owed_when_the_backup_already_carried_the_issue(
        tmp_path: Path) -> None:
    """With the issue in the backup, the owed set is empty and the report says so."""
    db = release(tmp_path, issues=("26092", "26093"))
    root = bundle(tmp_path)
    backup = tmp_path / "before.sqlite"
    con = sqlite3.connect(db)
    con.backup(sqlite3.connect(backup))
    con.close()
    report = build_report(db, root, backup)
    assert report["issues_owed"] == []
    assert report["conclusion"]["void"] is True
    assert report["conclusion"]["verified"] is False
    assert "nothing was added" in report["conclusion"]["note"]


def test_main_writes_the_report_and_exits_nonzero_when_it_rejects(applied, tmp_path) -> None:
    """The exit code is the acceptance signal a pipeline can read."""
    db, root, backup = applied
    out = tmp_path / "ok.json"
    assert main(["--database", str(db), "--bundle", str(root), "--backup", str(backup),
                 "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["conclusion"]["verified"] is True
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET score='9-9' WHERE issue='26093'")
    con.commit()
    con.close()
    rejected = tmp_path / "rejected.json"
    assert main(["--database", str(db), "--bundle", str(root), "--backup", str(backup),
                 "--out", str(rejected)]) == 1
    assert json.loads(rejected.read_text(encoding="utf-8"))["conclusion"]["verified"] is False
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='26093'")[0][0] == len(
        {"spf", "jq", "ds", "bf", "bq"})


def test_replay_catches_a_changed_live_page_in_the_bundle(applied, tmp_path: Path) -> None:
    """A rebuilt bundle with a different settlement must not match the release."""
    db, root, backup = applied
    other = bundle(tmp_path / "other", issue="26093")
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET score='4-4' WHERE issue='26093'")
    con.commit()
    con.close()
    report = build_report(db, other, backup)
    assert report["conclusion"]["verified"] is False
    assert report["mismatches"]


def test_replay_catches_a_changed_source_url(applied) -> None:
    """Provenance is observable through the R query interface, so it is verified too."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET source_url='https://example.invalid/x' "
                "WHERE issue='26093' AND play='spf'")
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert report["mismatches"]


def test_replay_catches_a_changed_received_at(applied) -> None:
    """A falsified collection time must not pass as verified."""
    db, root, backup = applied
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET received_at='2020-01-01T00:00:00+00:00' "
                "WHERE issue='26093' AND play='jq'")
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert report["mismatches"]


def test_replay_reconciles_a_mixed_bundle_with_the_added_set(tmp_path: Path) -> None:
    """A bundle may hold one settled issue and one that is not ready.

    The applier adds only the eligible one, so the replay must derive the same eligible set
    from the bundle's own bytes and must not report the skipped issue as missing.
    """
    db = release(tmp_path)
    settled = bundle(tmp_path / "a", issue="26093")
    unstarted = bundle(tmp_path / "b", issue="26094", status="未开赛", ft="", ht="",
                       settle=False)
    # one bundle carrying both issues, as a capture batch would
    merged = tmp_path / "a" / "bundle-26093"
    manifest = json.loads((merged / "manifest.json").read_text(encoding="utf-8"))
    other = json.loads((unstarted / "manifest.json").read_text(encoding="utf-8"))
    import shutil
    for entry in other["captures"]:
        shutil.copy(unstarted / "raw" / (entry["sha256"] + ".html"), merged / "raw")
    manifest["captures"].extend(other["captures"])
    manifest["requested_issues"] = ["26093", "26094"]
    (merged / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    backup = tmp_path / "before.sqlite"
    committed = add_issues(db, merged, backup, approval_note="n")
    assert committed["status"] == "added"
    assert committed["added_issues"] == ["26093"]
    assert committed["skipped"][0]["issue"] == "26094"
    report = build_report(db, merged, backup)
    assert report["issues_owed"] == ["26093"]
    assert [item["issue"] for item in report["issues_ineligible"]] == ["26094"]
    assert report["conclusion"]["verified"] is True
    assert report["mismatches"] == []


def test_replay_rejects_a_batch_that_added_an_ineligible_issue(tmp_path: Path) -> None:
    """The recorded added set must equal the eligible set the bytes imply."""
    db = release(tmp_path)
    root = bundle(tmp_path)
    backup = tmp_path / "before.sqlite"
    add_issues(db, root, backup, approval_note="n")
    con = sqlite3.connect(db)
    con.execute("UPDATE issue_addition_batch SET added_issues='[]'")
    con.commit()
    con.close()
    report = build_report(db, root, backup)
    assert report["conclusion"]["verified"] is False
    assert any("did not add exactly the eligible set" in item.get("reason", "")
               for item in report["mismatches"])


def test_replay_catches_an_ineligible_issue_that_was_added_anyway(tmp_path: Path) -> None:
    """Excluding the rejected issue from the checks must not excuse it being present.

    The batch can claim it added only the eligible issue; the release is compared against
    the backup independently, so a rejected issue that leaked in is caught.
    """
    db = release(tmp_path)
    settled = bundle(tmp_path / "a", issue="26093")
    unstarted = bundle(tmp_path / "b", issue="26094", status="未开赛", ft="", ht="",
                       settle=False)
    merged = tmp_path / "a" / "bundle-26093"
    manifest = json.loads((merged / "manifest.json").read_text(encoding="utf-8"))
    other = json.loads((unstarted / "manifest.json").read_text(encoding="utf-8"))
    import shutil
    for entry in other["captures"]:
        shutil.copy(unstarted / "raw" / (entry["sha256"] + ".html"), merged / "raw")
    manifest["captures"].extend(other["captures"])
    manifest["requested_issues"] = ["26093", "26094"]
    (merged / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    backup = tmp_path / "before.sqlite"
    add_issues(db, merged, backup, approval_note="n")
    # Smuggle the ineligible issue in, as a bad batch would.
    con = sqlite3.connect(db)
    con.execute("""INSERT INTO observation SELECT observation_id+900000, '26094', slot, play,
                   native_match_id, status, score, halftime_score, expected_option,
                   source_sha256, source_url, received_at, payload_json FROM observation
                   WHERE issue='26093'""")
    con.commit()
    con.close()
    report = build_report(db, merged, backup)
    assert report["conclusion"]["verified"] is False
    assert any("the contract rejects" in item.get("reason", "")
               for item in report["mismatches"])


def test_replay_rejects_a_bundle_with_an_empty_page(applied, tmp_path: Path) -> None:
    """The applier's parsed-domain validation is reused, so replay rejects the same bundle."""
    db, _, backup = applied
    root = bundle(tmp_path / "hollow")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["captures"] if item["typeid"] == 7)
    (root / "raw" / (entry["sha256"] + ".html")).unlink()
    import hashlib as _hashlib
    empty = _hashlib.sha256(b"").hexdigest()
    (root / "raw" / (empty + ".html")).write_bytes(b"")
    entry["sha256"] = empty
    entry["classification"] = "source_empty"
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="miss a play"):
        build_report(db, root, backup)
