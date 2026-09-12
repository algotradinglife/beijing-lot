"""Independent contract examples; no network and no 500 fixtures."""
import copy
import json
import sqlite3

import pytest

from src.nowscore_settlement import (
    PLAYS, TYPEID_LABELS, TITLE, audit_rows, build_database, canonical,
    digest, expected_option, parse_page, source_url, hash_json_texts,
)


def page(typeid=6, status="完场", ft="3-1", ht="1-0", values=None):
    labels = TYPEID_LABELS[typeid]
    if values is None:
        values = {labels[0]: "2.5"}
    cells = []
    # BF cell numbers deliberately differ from domain order: labels are authoritative.
    for i, label in enumerate(reversed(labels), 1):
        title = {"胜": "主胜", "平": "平局", "负": "客胜"}.get(label, label)
        prefix = f'<b>{label.replace("其他", "其它")}</b><br>' if typeid == 8 else ""
        cells.append(f'<td title="{title}">{prefix}<span id="sp_1_{i}">{values.get(label, "")}</span></td>')
    odds = "".join(cells)
    handicap = "<td>0</td>" if typeid == 5 else ""
    row = f'''<tr id="row_1" matchid="1" polygoal="0" cansale="false" name="2025-05-13" gamename="测试">
      <td>1</td><td>测试</td><td>23:30</td><td title="截止时间：2025-05-13 23:25">{status}</td>
      <td><a id="HomeTeam_123" onmouseover="getMyHTML2('/temp/123_456.htm')">主队</a></td>{handicap}<td>{ft}</td><td><a id="GuestTeam_123" onmouseover="getMyHTML2('/temp/123_789.htm')">客队</a></td><td>{ht}</td>
      <td><a href="/sp/danchang/25053_1_{typeid}.html">SP</a></td>{odds if typeid != 8 else ''}</tr>'''
    extra = f'<tr id="tr_1"><td><table><tr>{odds}</tr></table></td></tr>' if typeid == 8 else ""
    return f'<html><title>{TITLE[typeid]}</title><script>M[1][0]=123;</script><select id="dropIssueNum"><option selected value="25053">25053</option></select><table>{row}{extra}</table></html>'.encode()


def codes(row):
    return {f["code"] for f in audit_rows([row])} - {"missing_play_coverage"}


@pytest.mark.parametrize("typeid,option", [(5,"胜"),(6,"4球"),(7,"上+双"),(8,"3:1"),(9,"胜-胜")])
def test_all_five_label_mapping(typeid, option):
    row = parse_page(page(typeid, values={option:"3.753"}), "25053", typeid)[0]
    assert row["parse_errors"] == []
    assert expected_option(row) == option
    assert len(row["options"]) == len(TYPEID_LABELS[typeid])
    assert codes(row) == set()
    assert next(o for o in row["options"] if o["sp"] is not None)["option"] == option


@pytest.mark.parametrize("status", ["取消","推迟","中断","腰斩"])
def test_abnormal_not_finished_and_full_one_not_unique(status):
    row = parse_page(page(6,status=status,ft="-",ht="-",values={x:"1.00" for x in TYPEID_LABELS[6]}),"25053",6)[0]
    assert row["status"] == status
    assert codes(row) == {"full_domain_all_one"}
    assert all(x["sp"] == 1 for x in row["options"])
    row["options"][0]["sp"] = 2
    assert codes(row) == {"abnormal_without_all_one"}


def test_unique_one_and_mismatch_do_not_mutate_source():
    row = parse_page(page(6,values={"3球":"1.00"}),"25053",6)[0]
    original = copy.deepcopy(row)
    assert codes(row) == {"single_option_sp_one","option_score_mismatch"}
    assert row == original


@pytest.mark.parametrize("bad", ["NaN","Infinity","0","0.99","not-a-number"])
def test_invalid_sp(bad):
    row = parse_page(page(6,values={"4球":bad}),"25053",6)[0]
    assert "invalid_sp" in codes(row)
    assert all(o["sp"] is None for o in row["options"])


def test_domain_missing_and_duplicate_fail_closed():
    p = page(6).replace(b'title="7+', b'title="6')
    row = parse_page(p,"25053",6)[0]
    assert "option_domain_mismatch" in codes(row)
    assert "duplicate_issue_slot_play" in {f["code"] for f in audit_rows([row,row])}


def test_wrong_issue_or_play_rejected():
    with pytest.raises(ValueError, match="selected issue"):
        parse_page(page(),"25054",6)
    with pytest.raises(ValueError, match="title"):
        parse_page(page(),"25053",7)
    with pytest.raises(ValueError, match="identity"):
        parse_page(page().replace(b'25053_1_6.html',b'25053_2_6.html'),"25053",6)
    with pytest.raises(ValueError, match="roster"):
        parse_page(page().replace(b'M[1][0]=123;',b'M[1][0]=123; M[2][0]=999;'),"25053",6)


def test_missing_handicap_not_zero_and_bq_missing_half():
    r = parse_page(page(5).replace(b'polygoal="0"',b'polygoal=""'),"25053",5)[0]
    assert expected_option(r) is None
    assert "missing_or_invalid_handicap" in codes(r)
    r = parse_page(page(9,ht="-"),"25053",9)[0]
    assert expected_option(r) is None
    assert "missing_score_or_handicap_for_result" in codes(r)


def test_other_score_and_goals_cap():
    for tid, exp in [(8,"胜其他"),(6,"7+球"),(7,"上+双")]:
        r = parse_page(page(tid,ft="6-2"),"25053",tid)[0]
        assert expected_option(r) == exp


def test_cross_play_checks_and_missing_coverage():
    rows = [parse_page(page(t),"25053",t)[0] for t in PLAYS]
    f = audit_rows(rows)
    assert not any(x["code"].startswith("cross_play_") for x in f)
    rows[0]["native_match_id"] = "999"
    rows[1]["status"] = "取消"
    cs = {x["code"] for x in audit_rows(rows)}
    assert {"cross_play_native_match_id","cross_play_status"} <= cs
    assert "missing_play_coverage" in {x["code"] for x in audit_rows(rows[:1])}


def test_replay_hashes_sqlite_options_and_no_overwrite(tmp_path, capsys, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    captures = []
    for t in PLAYS:
        b = page(t)
        sha = digest(b)
        (raw / f"{sha}.html").write_bytes(b)
        captures.append(dict(issue="25053",typeid=t,url=source_url("25053",t),sha256=sha,received_at="2026-09-05T00:00:00+00:00"))
    manifest = dict(schema="nowscore_capture_v1",source="nowscore",requested_issues=["25053"],captures=captures)
    (tmp_path / "manifest.json").write_text(canonical(manifest))
    receipt = build_database(tmp_path,tmp_path / "first.sqlite")
    assert receipt == build_database(tmp_path,tmp_path / "replay.sqlite")
    from scripts.rebuild_nowscore_settlement import main
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("offline build attempted networking"))
    main(["build", "--data-root", str(tmp_path), "--run-root", str(tmp_path), "--output", str(tmp_path / "cli.sqlite")])
    assert json.loads(capsys.readouterr().out) == receipt
    with pytest.raises(FileExistsError):
        main(["build", "--data-root", str(tmp_path), "--run-root", str(tmp_path), "--output", str(tmp_path / "cli.sqlite")])
    with pytest.raises(SystemExit):
        main(["capture", "--run-root", str(tmp_path), "--output", str(tmp_path / "unused.sqlite")])
    with pytest.raises(SystemExit):
        main(["build", "--run-root", str(tmp_path)])
    assert not (tmp_path / "unused.sqlite").exists()
    assert receipt["options"] == 49
    assert receipt["observations"] == 5
    assert receipt["capture_failures"] == []
    with sqlite3.connect(tmp_path / "first.sqlite") as con:
        assert con.execute("SELECT COUNT(*) FROM option_sp").fetchone()[0] == 49
        assert json.loads(con.execute("SELECT payload_json FROM receipt").fetchone()[0]) == receipt
    with pytest.raises(FileExistsError):
        build_database(tmp_path,tmp_path / "first.sqlite")
    (raw / f'{captures[0]["sha256"]}.html').write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_database(tmp_path,tmp_path / "bad.sqlite")


def test_missing_score_half_exceeds_and_reference_sp():
    r = parse_page(page(6,ft="-",ht="-",values={}),"25053",6)[0]
    assert {"finished_missing_score","finished_missing_sp"} <= codes(r)
    r = parse_page(page(6,ht="4-0"),"25053",6)[0]
    assert "halftime_exceeds_fulltime" in codes(r)
    r = parse_page(page(6,status="推迟",values={x:"3.1" for x in TYPEID_LABELS[6]}),"25053",6)[0]
    assert codes(r) == {"abnormal_without_all_one"}


def test_bf_summary_does_not_fill_other_option():
    b = page(8, ft="5-2", values={})
    b = b.replace(b'</a></td></tr>', b'</a></td><td><b>43.3629</b></td><td><span id="sp_1"></span></td></tr>', 1)
    r = parse_page(b,"25053",8)[0]
    assert r["summary_sp"] == 43.3629
    assert r["summary_sp_raw"] == "43.3629"
    assert all(o["sp"] is None for o in r["options"])
    assert expected_option(r) == "胜其他"
    assert codes(r) == {"summary_sp_without_option"}


@pytest.mark.parametrize("values", [[], [{"文字": "比分"}, None, 0, "a\nb"], [1, 2, 3]])
def test_streamed_json_hash_matches_canonical_array(values):
    assert hash_json_texts(canonical(value) for value in values) == digest(canonical(values).encode())


def multi_issue_bundle(root, count=12):
    """Synthetic source-pure bundle exercising issue boundaries in one rebuild."""
    (root / "raw").mkdir(parents=True)
    captures, rows = [], []
    issues = [f"25{i:03d}" for i in range(1, count + 1)]
    for issue in issues:
        for typeid in PLAYS:
            payload = page(typeid).replace(b"25053", issue.encode())
            sha = digest(payload)
            (root / "raw" / f"{sha}.html").write_bytes(payload)
            entry = dict(issue=issue, typeid=typeid, url=source_url(issue, typeid),
                         received_at="2026-09-06T00:00:00+00:00", sha256=sha)
            captures.append(entry)
            parsed = parse_page(payload, issue, typeid)
            for row in parsed:
                row.update(source_sha256=sha, source_url=entry["url"], received_at=entry["received_at"])
            rows.extend(parsed)
    manifest = dict(schema="nowscore_capture_v1", source="nowscore",
                    requested_issues=issues, captures=captures)
    (root / "manifest.json").write_text(canonical(manifest))
    return rows


def test_rebuild_audits_one_issue_at_a_time_and_reconciles_hashes(tmp_path, monkeypatch):
    import src.nowscore_settlement as module

    root = tmp_path / "source"
    expected = multi_issue_bundle(root)
    checked = []
    original = module.audit_rows

    def per_issue(rows):
        assert len({row["issue"] for row in rows}) == 1
        assert len(rows) == 5
        checked.append(rows[0]["issue"])
        return original(rows)

    monkeypatch.setattr(module, "audit_rows", per_issue)
    result = build_database(root, tmp_path / "data.sqlite")
    assert len(checked) == 12
    assert result["peak_issue_observations"] == 5
    assert result["observations"] == 60 and result["options"] == 12 * 49
    assert result["data_sha256"] == digest(canonical(expected).encode())
    assert result["audit_sha256"] == digest(canonical(original(expected)).encode())


def test_mid_rebuild_failure_rolls_back_and_releases_connection(tmp_path, monkeypatch):
    import src.nowscore_settlement as module

    root = tmp_path / "source"
    multi_issue_bundle(root, count=2)
    calls = 0
    original = module.audit_rows

    def fail_second(rows):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected audit failure")
        return original(rows)

    monkeypatch.setattr(module, "audit_rows", fail_second)
    output = tmp_path / "unsealed.sqlite"
    with pytest.raises(RuntimeError, match="injected"):
        build_database(root, output)
    with sqlite3.connect(output, timeout=1) as con:
        con.execute("BEGIN EXCLUSIVE")
        for table in ("capture", "observation", "option_sp", "finding", "receipt"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_modern_roster_preserves_team_ids_for_six_digit_issue():
    raw=page().replace(b'25053', b'130511')
    row=parse_page(raw,'130511',6)[0]
    assert (row['home_id'],row['away_id'])==('456','789')
    damaged=raw.replace(b'/temp/123_456.htm',b'/temp/123_789.htm')
    assert 'missing_or_invalid_native_team_identity' in parse_page(damaged,'130511',6)[0]['parse_errors']
