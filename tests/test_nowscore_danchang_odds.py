"""src/nowscore_danchang_odds.py 的契约与失败路径测试（不发起真实网络请求）。"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.nowscore_danchang_odds import (  # noqa: E402
    MARKET_1X2, MARKET_OVERUNDER, MARKET_PAYOUT, MARKET_WINRATE, MarketDataError,
    hk_to_prob, market_url, parse_records, validate_records, write_records,
)

XML_1X2 = ('<?xml version="1.0" encoding="utf-8"?><odds issueNum="26097">'
           '<i>0,21,0,1.78,3.84,4.13,1.86,3.79,3.72</i>'
           '<i>1,16,0,2.15,3.45,2.87,2.06,3.48,3.08</i></odds>')
XML_OU = ('<?xml version="1.0" encoding="utf-8"?><odds issueNum="26097">'
          '<i>1,21,20476107,0.91,3,0.81</i><i>3,21,20471756,0.98,3,0.89</i></odds>')
XML_WR = ('<?xml version="1.0" encoding="utf-8"?><odds issueNum="26097">'
          '<i>21,49.3%,24.9%,25.8%</i><i>16,43.8%,26.2%,30.0%</i></odds>')
XML_PO = ('<?xml version="1.0" encoding="utf-8"?><odds issueNum="26097">'
          '<i>21,,92.71,</i><i>16,,90.55,</i></odds>')


class TestHkToProb:
    def test_standard(self):
        assert hk_to_prob(0.9) == pytest.approx(1 / 1.9)

    @pytest.mark.parametrize("bad", [0.0, -0.5])
    def test_rejects_non_positive(self, bad):
        with pytest.raises(MarketDataError, match="必须为正"):
            hk_to_prob(bad)


class TestMarketUrl:
    def test_current_issue_uses_static_files(self):
        assert market_url("26097", MARKET_1X2, "0", current_issue=True).endswith("/data/op5.xml")
        assert market_url("26097", MARKET_OVERUNDER, "1", current_issue=True).endswith("/data/dx5.xml")

    def test_historical_issue_uses_company_query(self):
        url = market_url("26087", MARKET_1X2, "1", current_issue=False)
        assert "companyid=1" in url and "issuenum=26087" in url and "typeid=5" in url
        assert "OverUnder.aspx" in market_url("26087", MARKET_OVERUNDER, "3", current_issue=False)

    @pytest.mark.parametrize("market,cid", [(MARKET_WINRATE, "-1"), (MARKET_PAYOUT, "-2")])
    def test_companyless_markets_always_use_query(self, market, cid):
        # 即使本期也没有整期静态文件
        url = market_url("26097", market, cid, current_issue=True)
        assert url.endswith("companyid=" + cid)
        assert "/data/" not in url

    def test_unknown_market(self):
        with pytest.raises(MarketDataError, match="未知市场"):
            market_url("26097", "asian", "1", current_issue=False)


class TestParseRecords:
    def test_reads_issue_and_records(self):
        issue, recs = parse_records(XML_1X2)
        assert issue == "26097"
        assert len(recs) == 2
        assert recs[0][0] == "0" and len(recs[0]) == 9

    def test_missing_root(self):
        with pytest.raises(MarketDataError, match="issueNum"):
            parse_records("<html></html>")


class TestValidate1x2:
    def test_ok(self):
        _, raw = parse_records(XML_1X2)
        recs = validate_records("26097", MARKET_1X2, raw)
        assert [r.slot for r in recs] == [21, 16]
        assert recs[0].values["curr_home"] == pytest.approx(1.86)
        assert recs[0].match_id == 0

    def test_current_issue_accepts_mixed_companies(self):
        _, raw = parse_records(XML_1X2)
        recs = validate_records("26097", MARKET_1X2, raw, company=None)
        assert sorted(r.company for r in recs) == ["0", "1"]

    def test_company_mismatch_rejected(self):
        _, raw = parse_records(XML_1X2)
        with pytest.raises(MarketDataError, match="请求公司"):
            validate_records("26097", MARKET_1X2, raw, company="9")

    def test_second_record_checked_with_its_own_company(self):
        # 回归：参数 company 不能被循环内的局部变量覆盖
        _, raw = parse_records(XML_1X2)
        with pytest.raises(MarketDataError, match="响应含公司 1"):
            validate_records("26097", MARKET_1X2, raw, company="0")

    def test_wrong_field_count(self):
        with pytest.raises(MarketDataError, match="字段数"):
            validate_records("26097", MARKET_1X2, [["0", "1", "0", "1.5"]])

    def test_non_numeric_odds(self):
        with pytest.raises(MarketDataError, match="不是数值"):
            validate_records("26097", MARKET_1X2, [["0", "1", "0", "x", "3", "3", "2", "3", "3"]])

    def test_non_positive_odds(self):
        with pytest.raises(MarketDataError, match="非正"):
            validate_records("26097", MARKET_1X2, [["0", "1", "0", "0", "3", "3", "2", "3", "3"]])

    def test_slot_must_be_positive(self):
        with pytest.raises(MarketDataError, match="场次号"):
            validate_records("26097", MARKET_1X2, [["0", "0", "0", "2", "3", "3", "2", "3", "3"]])

    def test_empty_payload(self):
        with pytest.raises(MarketDataError, match="为空"):
            validate_records("26097", MARKET_1X2, [])


class TestValidateOverUnder:
    def test_ok(self):
        _, raw = parse_records(XML_OU)
        recs = validate_records("26097", MARKET_OVERUNDER, raw)
        assert recs[0].values["line"] == pytest.approx(3.0)
        assert recs[0].values["over_hk"] == pytest.approx(0.91)

    def test_line_zero_rejected(self):
        with pytest.raises(MarketDataError, match="非正"):
            validate_records("26097", MARKET_OVERUNDER, [["1", "21", "123", "0.9", "0", "0.8"]])


class TestValidateWinrate:
    def test_ok_percent_is_fraction(self):
        _, raw = parse_records(XML_WR)
        recs = validate_records("26097", MARKET_WINRATE, raw)
        assert recs[0].values["home_pct"] == pytest.approx(0.493)
        assert recs[0].values["draw_pct"] == pytest.approx(0.249)
        assert sum(recs[0].values.values()) == pytest.approx(1.0)

    def test_missing_percent_sign(self):
        with pytest.raises(MarketDataError, match="缺少百分号"):
            validate_records("26097", MARKET_WINRATE, [["21", "49.3", "24.9", "25.8"]])

    def test_sum_must_be_one(self):
        with pytest.raises(MarketDataError, match="偏离 1"):
            validate_records("26097", MARKET_WINRATE, [["21", "49.3%", "24.9%", "20.0%"]])

    def test_company_is_negative_one(self):
        _, raw = parse_records(XML_WR)
        assert validate_records("26097", MARKET_WINRATE, raw)[0].company == "-1"


class TestValidatePayout:
    def test_ok_has_no_percent_sign(self):
        _, raw = parse_records(XML_PO)
        recs = validate_records("26097", MARKET_PAYOUT, raw)
        assert recs[0].values["payout_pct"] == pytest.approx(0.9271)
        assert recs[0].company == "-2"

    def test_pads_must_be_empty(self):
        with pytest.raises(MarketDataError, match="占位列"):
            validate_records("26097", MARKET_PAYOUT, [["21", "x", "92.71", ""]])


class TestWriteRecords:
    def test_round_trip(self, tmp_path):
        _, raw = parse_records(XML_OU)
        recs = validate_records("26097", MARKET_OVERUNDER, raw)
        path = tmp_path / "ou.csv"
        assert write_records(recs, path, MARKET_OVERUNDER) == 2
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert [r["slot"] for r in rows] == ["21", "21"]
        assert rows[0]["company"] == "1" and rows[1]["company"] == "3"
        assert rows[0]["line"] == "3.0"

    def test_empty_records_writes_header_only(self, tmp_path):
        path = tmp_path / "empty.csv"
        assert write_records([], path, MARKET_WINRATE) == 0
        assert path.read_text(encoding="utf-8").strip() == "issue,market,company,slot,match_id,home_pct,draw_pct,away_pct"
