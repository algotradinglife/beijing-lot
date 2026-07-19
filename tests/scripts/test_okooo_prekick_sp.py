from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import okooo_prekick_sp as okooo  # noqa: E402


ISSUE_HTML = """
<html><head><title>单场比分直播</title></head><body><table>
<tr matchid="2002"><td class="graytx"><span>2</span></td><td class="ls"><a class="ssname">乙联</a></td>
<td class="graytx">07-18 01:00</td><td></td><td><a class="ctrl_homename">主二</a></td><td></td><td><a class="ctrl_awayname">客二</a></td></tr>
<tr matchid="2001"><td class="graytx"><span>1</span></td><td class="ls"><a class="ssname">甲联</a></td>
<td class="graytx">07-17 23:00</td><td></td><td><a class="ctrl_homename">主一</a></td><td></td><td><a class="ctrl_awayname">客一</a></td></tr>
</table></body></html>
""".encode()

HISTORY_HTML = """
<html><head><title>赔率变化列表</title></head><body><table id="change">
<thead><tr><th>时间</th><th>更新</th><th>1:0</th><th>1:1</th><th>其他</th></tr></thead>
<tbody>
<tr><td>2026-07-17 12:05</td><td>赛前09时55分</td><td>6.0</td><td>7.2↓</td><td>30</td></tr>
<tr><td>2026-07-17 11:48</td><td>赛前10时12分</td><td>6.2</td><td>7.1</td><td>31</td></tr>
<tr><td>2026-07-17 10:00</td><td>赛前12小时</td><td>6.5</td><td>7.0</td><td>32</td></tr>
</tbody></table></body></html>
""".encode()


def test_parses_issue_matches_in_match_index_order() -> None:
    rows = okooo.parse_issue_page(ISSUE_HTML, "26075")
    assert [(row.match_idx, row.match_id, row.home, row.away) for row in rows] == [
        (1, "2001", "主一", "客一"),
        (2, "2002", "主二", "客二"),
    ]


def test_strict_10h_selects_nearest_row_without_future_leakage() -> None:
    rows = okooo.parse_history_page(HISTORY_HTML, "https://example.test/change/14/")
    assert [row.minutes_before_kickoff for row in rows] == [595, 612, 720]
    selected = okooo.select_asof_10h(rows)
    assert selected.minutes_before_kickoff == 612
    values = okooo.outcome_values(selected)
    assert [(item["outcome_label"], item["sp"]) for item in values] == [
        ("1:0", 6.2),
        ("1:1", 7.1),
        ("其他", 31.0),
    ]


def test_rejects_waf_and_missing_10h() -> None:
    blocked = "<html><title>405</title><body>访问的URL有可能对网站造成安全威胁</body></html>".encode()
    with pytest.raises(okooo.OkoooParseError, match="auth_required_or_waf_blocked"):
        okooo.parse_history_page(blocked, "https://example.test")
    login = "<html><title>登录注册</title><body>密码登录 手机登录</body></html>".encode()
    with pytest.raises(okooo.OkoooParseError, match="login_required"):
        okooo.parse_history_page(login, "https://example.test")
    late_only = HISTORY_HTML.replace(b"10\xe6\x97\xb612\xe5\x88\x86", b"09\xe6\x97\xb650\xe5\x88\x86").replace(
        b"12\xe5\xb0\x8f\xe6\x97\xb6", b"09\xe5\xb0\x8f\xe6\x97\xb6"
    )
    with pytest.raises(okooo.OkoooParseError, match="no_history_row"):
        okooo.select_asof_10h(okooo.parse_history_page(late_only))


def test_publishes_hash_verified_non_executable_bundle(tmp_path: Path) -> None:
    match = okooo.parse_issue_page(ISSUE_HTML, "26075")[0]
    rows = okooo.parse_history_page(HISTORY_HTML)
    selected = okooo.select_asof_10h(rows)
    flat = []
    for value in okooo.outcome_values(selected):
        flat.append(
            {
                "issue": match.issue,
                "match_idx": match.match_idx,
                "match_id": match.match_id,
                "market": "correct_score",
                "source_url": okooo.history_url(match.match_id, "correct_score"),
                "row_order": selected.row_order,
                "relative_label": selected.relative_label,
                "minutes_before_kickoff": selected.minutes_before_kickoff,
                **value,
            }
        )
    result = okooo.publish_bundle(
        issue="26075",
        fetched_at_utc="2026-07-16T15:00:00+00:00",
        raw_pages={"issue.html": ISSUE_HTML, "history/001.html": HISTORY_HTML},
        matches=[match],
        history=flat,
        selected=flat,
        failures=[],
        output_root=tmp_path,
    )
    bundle = Path(result["output_dir"])
    assert result["status"] == "complete"
    assert result["verification"]["status"] == "valid"
    assert okooo.verify_bundle(bundle)["status"] == "valid"
    with (bundle / "selected_10h.csv").open(encoding="utf-8", newline="") as handle:
        output = list(csv.DictReader(handle))
    assert {row["minutes_before_kickoff"] for row in output} == {"612"}
    manifest = (bundle / "manifest.json").read_text(encoding="utf-8")
    assert '"execution_enabled": false' in manifest
    assert '"provider_name": "william_hill"' in manifest
    assert '"official_beidan_sp": false' in manifest
    assert '"authentication_mode": "anonymous"' in manifest
    with (bundle / "raw/issue.html").open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(okooo.OkoooParseError, match="checksum mismatch"):
        okooo.verify_bundle(bundle)
