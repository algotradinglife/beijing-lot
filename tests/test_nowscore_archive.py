"""Sanitized archive markup contracts; reference odds are not settlement SP."""
import pytest
import json
import sqlite3

from src.nowscore_settlement import ARCHIVE_SLUGS, TITLE, audit_rows, parse_archive_page, parse_page, source_url


def archive_page():
    return '''<title>单场让球胜平负开奖信息</title>
    <ul id="mymenu"><li class="myons"><a href="/beijingdanchang/rangqiushengpingfu/kaijiang_dc_5_090919.html">让球胜平负</a></li></ul>
    <table><tr class="ttis"><td>场次</td><td>赛事</td><td>开赛时间</td><td>主队(让球)</td><td>比分</td><td>客队</td><td>半场</td><td>彩果</td><td>开奖SP</td><td colspan="3">平均欧*</td><td>Crow*</td><td>数据</td></tr>
    <tr id="row_1"><td>1</td><td>测试赛事</td><td>09-29 22:00</td><td>测试主队 (<b>+2</b>)</td><td>1-1</td><td>测试客队</td><td>0-1</td><td><span class="spitems">胜</span></td><td title="开奖SP"><a href="/sp/danchang/090919_1_5.html"><u>2.40285</u></a></td><td>8.65</td><td>4.67</td><td>1.28</td><td>平手</td><td><a href="//live.nowscore.com/analysis/123cn.html">析</a></td></tr></table>'''


def test_archive_partial_result_and_unobserved_fields():
    row = parse_archive_page(archive_page().encode(), "090919", 5)[0]
    assert row["issue"] == "090919" and row["native_match_id"] == "123"
    assert row["home"] == "测试主队" and row["handicap"] == 2
    assert row["status"] == row["schedule_date"] == row["can_sale"] == ""
    assert [(o["option"], o["sp"]) for o in row["options"]] == [("胜", 2.40285)]
    assert row["summary_sp_raw"] == "2.40285"
    assert "archive_partial_option_coverage" in row["parse_errors"]
    assert parse_page(archive_page().encode(), "090919", 5) == [row]


@pytest.mark.parametrize("old,new", [
    ("开奖SP</td>", "未知列</td>"), ("row_1", "row_0"),
    ("090919_1_5", "090919_2_5"), ("analysis/123cn.html", "analysis/badcn.html"),
    ('class="myons"', 'class="wrong"'), ('class="spitems"', 'class="wrong"'),
])
def test_archive_identity_and_layout_fail_closed(old, new):
    with pytest.raises(ValueError):
        parse_archive_page(archive_page().replace(old, new).encode(), "090919", 5)


def test_absent_handicap_is_not_invented_zero():
    row = parse_archive_page(archive_page().replace(" (<b>+2</b>)", "").encode(), "090919", 5)[0]
    assert row["handicap"] is None and row["handicap_raw"] == ""
    assert "missing_or_invalid_handicap" in row["parse_errors"]


def test_archive_blank_result_preserves_unassigned_summary_sp():
    html = archive_page().replace('<span class="spitems">胜</span>', ' ').replace("2.40285", "1")
    row = parse_page(html.encode(), "090919", 5)[0]
    assert row["archive_result_raw"] == "" and row["options"] == []
    assert row["summary_sp_raw"] == "1" and row["summary_sp"] == 1
    assert "unrecognized_archive_result" in row["parse_errors"]


def test_archive_duplicate_result_containers_still_rejected():
    html = archive_page().replace('<span class="spitems">胜</span>',
                                  '<span class="spitems">胜</span><span class="spitems">负</span>')
    with pytest.raises(ValueError, match="result label container"):
        parse_page(html.encode(), "090919", 5)


def test_archive_missing_native_id_sentinel_preserved_and_audited():
    html = archive_page().replace("analysis/123cn.html", "analysis/-1cn.html")
    row = parse_page(html.encode(), "090919", 5)[0]
    assert row["native_match_id"] == "-1"
    assert row["issue"] == "090919" and row["slot"] == 1
    assert "missing_native_match_id" in row["parse_errors"]
    assert "missing_native_match_id" in [f["code"] for f in audit_rows([row])]


@pytest.mark.parametrize("identity", ["-2", "bad", ""])
def test_archive_unrecognized_native_id_still_rejected(identity):
    html = archive_page().replace("analysis/123cn.html", f"analysis/{identity}cn.html")
    with pytest.raises(ValueError, match="native match identity"):
        parse_page(html.encode(), "090919", 5)


def test_archive_duplicate_sentinel_links_still_rejected():
    html = archive_page().replace('<a href="//live.nowscore.com/analysis/123cn.html">析</a>',
                                  '<a href="//live.nowscore.com/analysis/-1cn.html">析</a>' * 2)
    with pytest.raises(ValueError, match="native match identity"):
        parse_page(html.encode(), "090919", 5)


@pytest.mark.parametrize("raw", ["0", "NaN", "bad"])
def test_archive_invalid_settlement_keeps_original(raw):
    row = parse_archive_page(archive_page().replace("2.40285", raw).encode(), "090919", 5)[0]
    assert row["summary_sp_raw"] == raw and row["summary_sp"] is None
    assert "invalid_sp" in row["parse_errors"]


def test_unknown_result_never_uses_reference_odds_or_score():
    row = parse_archive_page(archive_page().replace('spitems">胜', 'spitems">未知').encode(), "090919", 5)[0]
    assert row["options"] == [] and row["archive_result_raw"] == "未知"
    assert row["summary_sp"] == 2.40285


@pytest.mark.parametrize("typeid,label,expected", [
    (6,"0","0球"),(6,"7+","7+球"),(7,"上单","上+单"),(7,"下双","下+双"),
    (8,"1:1","1:1"),(8,"胜其它","胜其他"),(9,"负-平","负-平"),
])
def test_other_archive_plays_preserve_label_with_unobserved_sp(typeid,label,expected):
    title = "单场进球数" if typeid == 6 else TITLE[typeid]
    html = archive_page().replace("单场让球胜平负开奖信息", title + "开奖信息")
    html = html.replace(ARCHIVE_SLUGS[5], ARCHIVE_SLUGS[typeid]).replace("kaijiang_dc_5_",f"kaijiang_dc_{typeid}_")
    html = html.replace("090919_1_5",f"090919_1_{typeid}").replace("主队(让球)","主队")
    html = html.replace(" (<b>+2</b>)","").replace('spitems">胜',f'spitems">{label}').replace("2.40285","")
    row = parse_archive_page(html.encode(),"090919",typeid)[0]
    assert row["archive_result_raw"] == label
    assert [(o["option"],o["raw_sp"],o["sp"]) for o in row["options"]] == [(expected,"",None)]
    assert "missing_or_invalid_handicap" not in row["parse_errors"]


@pytest.mark.parametrize("typeid", range(5,10))
def test_source_url_routes_native_issue_formats(typeid):
    assert source_url("090919",typeid) == f"https://cp.nowscore.com/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/kaijiang_dc_{typeid}_090919.html"
    assert source_url("26089",typeid) == f"https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID={typeid}&issueNum=26089"


@pytest.mark.parametrize("sp", ["", "0", "2.40285"])
def test_archive_result_audit_independent_of_sp_presence(sp):
    html = archive_page().replace("2.40285",sp).replace('spitems">胜','spitems">负')
    row = parse_page(html.encode(),"090919",5)[0]
    findings = [f["code"] for f in audit_rows([row])]
    assert findings.count("option_score_mismatch") == 1
    assert ("archive_result_missing_sp" in findings) == (sp != "2.40285")
    assert "unobserved_status" in findings
    assert "unrecognized_status" not in findings and "single_option_nonfinished" not in findings


def test_archive_capture_classification_database_and_independent_replay(tmp_path):
    from src.nowscore_history_capture import classify_play
    from src.nowscore_settlement import build_database, canonical, digest
    from src.nowscore_replay import compare_nowscore_databases

    payload = archive_page().encode()
    assert classify_play(payload,"090919",5)["match_count"] == 1
    raw = tmp_path / "raw"
    raw.mkdir()
    sha = digest(payload)
    (raw / f"{sha}.html").write_bytes(payload)
    manifest = {"schema":"nowscore_capture_v1","source":"nowscore","requested_issues":["090919"],
                "captures":[{"issue":"090919","typeid":5,"url":source_url("090919",5),
                             "sha256":sha,"received_at":"2026-09-05T00:00:00+00:00"}]}
    manifest["captures"].extend({"issue":"090919","typeid":tid,"url":source_url("090919",tid),
                                 "error":"not captured in single-play fixture"} for tid in range(6,10))
    (tmp_path / "manifest.json").write_text(canonical(manifest))
    first, second = tmp_path / "first.sqlite", tmp_path / "second.sqlite"
    receipt = build_database(tmp_path,first)
    assert receipt == build_database(tmp_path,second)
    assert len(receipt["capture_failures"]) == 4 and receipt["options"] == 1
    assert compare_nowscore_databases(first,second)["equal"]
    with sqlite3.connect(first) as con:
        assert con.execute("SELECT option,raw_sp,sp FROM option_sp").fetchall() == [("胜","2.40285",2.40285)]
        row = json.loads(con.execute("SELECT payload_json FROM observation").fetchone()[0])
        assert row["source_layout"] == "archive_result_v1" and row["status"] == ""


@pytest.mark.parametrize('typeid', [5,6,7,8,9])
def test_validated_header_only_play_pages(typeid):
    from bs4 import BeautifulSoup
    from src.nowscore_history_capture import classify_play
    soup=BeautifulSoup(archive_page(),'html.parser')
    soup.select_one('#row_1').decompose()
    soup.table['class']='socai'
    soup.title.string=('单场进球数' if typeid==6 else TITLE[typeid])+'开奖信息'
    soup.select_one('#mymenu a')['href']=f'/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/kaijiang_dc_{typeid}_090919.html'
    if typeid!=5:soup.select('tr.ttis td')[3].string='主队'
    assert classify_play(str(soup).encode(),'090919',typeid)['classification']=='source_empty'
    soup.select('tr.ttis td')[0].string='错误'
    with pytest.raises(ValueError):classify_play(str(soup).encode(),'090919',typeid)
