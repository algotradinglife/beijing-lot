"""北单挂盘页（nowscore cp.nowscore.com）的市场数据抽取：欧赔 1X2 与 大小球。

数据面
------
本期整期（IsCurrentIssue）走静态文件，一次拿到全部场次：

* 欧赔   /data/op5.xml
* 大小球 /data/dx5.xml

历史期次走按公司查询：

* 欧赔   /handle/1x2.aspx?issuenum={issue}&typeid=5&companyid={company}
* 大小球 /handle/OverUnder.aspx?issuenum={issue}&typeid=5&companyid={company}

响应是 UTF-8 XML，根为 <odds issueNum="...">，每条记录一个 <i> 元素，
逗号分隔、无表头：

    市场        字段
    1x2         公司, 场次, matchid, 初胜, 初平, 初负, 即胜, 即平, 即负
    overunder   公司, 场次, matchid, 大赔, 盘口, 小赔

赔率是香港盘（净赔率），十进制赔率 = 港赔 + 1，隐含概率 = 1 / (1 + 港赔)。
这里的隐含概率未去水；去水属于分析步骤，由 R 侧负责。

公司代号（来自挂盘页 #oddsSelect）：

    "0" 平均欧*   "1" 澳M   "3" 皇G   "4" 立B   "8" 36*   "9" WL   "14" 伟D

模块只做「取数 -> 解析 -> 契约校验 -> 落盘」，不做任何拟合或概率去水。
导入本模块不会发起任何网络请求。
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

BASE_URL = "https://cp.nowscore.com"
USER_AGENT = "Mozilla/5.0 (compatible; beijing-lot/danchang-odds)"
DANCHANG_TYPE_ID = 5

#: 公司代号 -> 挂盘页显示名
COMPANY_NAMES: Mapping[str, str] = {
    "0": "平均欧*", "1": "澳M", "3": "皇G", "4": "立B",
    "8": "36*", "9": "WL", "14": "伟D",
}

MARKET_1X2 = "1x2"
MARKET_OVERUNDER = "overunder"
#: 平均胜率：各家「已去水」概率的均值，三者和为 1（companyid=-1）
MARKET_WINRATE = "winrate"
#: 平均返还率：各家赔付率的均值（companyid=-2）
MARKET_PAYOUT = "payout"
MARKETS = (MARKET_1X2, MARKET_OVERUNDER, MARKET_WINRATE, MARKET_PAYOUT)

_FIELDS: Mapping[str, tuple[str, ...]] = {
    MARKET_1X2: ("company", "slot", "match_id", "init_home", "init_draw", "init_away",
                 "curr_home", "curr_draw", "curr_away"),
    MARKET_OVERUNDER: ("company", "slot", "match_id", "over_hk", "line", "under_hk"),
    # 平均胜率/返还率没有公司列：<i>场次, 主胜%, 平%, 客胜%</i>
    MARKET_WINRATE: ("slot", "home_pct", "draw_pct", "away_pct"),
    # 返还率的首尾字段为空：<i>场次, , 返还率%, </i>
    MARKET_PAYOUT: ("slot", "pad_head", "payout_pct", "pad_tail"),
}
#: 每个市场的数值列（其余列按整数解析）
_ODDS_COLUMNS: Mapping[str, tuple[str, ...]] = {
    MARKET_1X2: ("init_home", "init_draw", "init_away", "curr_home", "curr_draw", "curr_away"),
    MARKET_OVERUNDER: ("over_hk", "line", "under_hk"),
    MARKET_WINRATE: ("home_pct", "draw_pct", "away_pct"),
    MARKET_PAYOUT: ("payout_pct",),
}
#: 以百分数存储、需要除以 100 的列
_PERCENT_COLUMNS: frozenset = frozenset({
    "home_pct", "draw_pct", "away_pct", "payout_pct",
})
#: 其中必须带百分号结尾的列（返还率在源数据里没有百分号）
_PERCENT_SIGN_REQUIRED: frozenset = frozenset({"home_pct", "draw_pct", "away_pct"})
#: 允许（且要求）为空串的列（源数据的占位字段）
_EMPTY_COLUMNS: frozenset = frozenset({"pad_head", "pad_tail"})
#: companyid 为负数时没有公司列
_COMPANYLESS_MARKETS = (MARKET_WINRATE, MARKET_PAYOUT)
#: 公司代号 -> companyid 查询参数
QUERY_COMPANY_IDS: Mapping[str, str] = {MARKET_WINRATE: "-1", MARKET_PAYOUT: "-2"}

_RECORD_RE = re.compile(r"<i>([^<]*)</i>")
_ISSUE_RE = re.compile(r'issueNum="([^"]*)"')


class MarketDataError(RuntimeError):
    """市场数据在取数、解析或契约校验阶段失败。"""


@dataclass(frozen=True)
class RawResponse:
    """一次原始响应；与抽取出的记录一起保留，以便离线重放。"""

    url: str
    status: int
    text: str
    fetched_at: str
    issue: str
    market: str
    company: str


@dataclass(frozen=True)
class MarketRecord:
    """一条已通过契约校验的市场记录。"""

    issue: str
    market: str
    company: str
    slot: int
    match_id: int
    values: Mapping[str, float]

    def as_row(self) -> dict:
        row = {
            "issue": self.issue, "market": self.market, "company": self.company,
            "slot": self.slot, "match_id": self.match_id,
        }
        row.update({k: self.values[k] for k in sorted(self.values)})
        return row


def hk_to_prob(hk: float) -> float:
    """香港盘净赔率 -> 未去水的隐含概率 1 / (1 + hk)。"""
    if hk <= 0:
        raise MarketDataError("香港赔率必须为正，收到 %r" % (hk,))
    return 1.0 / (1.0 + hk)


def market_url(issue: str, market: str, company: str, *, current_issue: bool) -> str:
    """构造一次请求的 URL。

    current_issue=True 时本期走整期静态文件（忽略 company，文件内含多家公司）。
    """
    if market not in MARKETS:
        raise MarketDataError("未知市场 %r，应为 %r" % (market, MARKETS))
    # 平均胜率/返还率没有整期静态文件，任何期次都走按期次查询
    if market in _COMPANYLESS_MARKETS:
        return "%s/handle/1x2.aspx?issuenum=%s&typeid=%d&companyid=%s" % (
            BASE_URL, issue, DANCHANG_TYPE_ID, QUERY_COMPANY_IDS[market])
    if current_issue:
        stem = "op5" if market == MARKET_1X2 else "dx5"
        return "%s/data/%s.xml" % (BASE_URL, stem)
    page = "1x2.aspx" if market == MARKET_1X2 else "OverUnder.aspx"
    return "%s/handle/%s?issuenum=%s&typeid=%d&companyid=%s" % (
        BASE_URL, page, issue, DANCHANG_TYPE_ID, company)


def fetch(url: str, *, issue: str, market: str, company: str, timeout: float = 40.0,
          retries: int = 2, opener: Callable | None = None) -> RawResponse:
    """取一次原始响应；瞬时失败最多重试 retries 次，仍失败则抛错（不静默成空）。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    open_fn = opener or urllib.request.urlopen
    last = None
    for attempt in range(retries + 1):
        try:
            response = open_fn(request, timeout=timeout)
            payload = response.read()
            return RawResponse(url=url, status=int(getattr(response, "status", 200)),
                               text=payload.decode("utf-8", "strict"),
                               fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                               issue=issue, market=market, company=company)
        except Exception as exc:  # noqa: BLE001 - 逐次记录，耗尽后抛出
            last = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise MarketDataError("取数失败 %s: %s" % (url, last)) from last


def parse_records(text: str) -> tuple:
    """解析 XML 文本，返回 (issueNum, 原始字段列表)。"""
    issue_match = _ISSUE_RE.search(text)
    if issue_match is None:
        raise MarketDataError("响应中没有 <odds issueNum=...> 根元素")
    records = [chunk.split(",") for chunk in _RECORD_RE.findall(text)]
    return issue_match.group(1), records


def validate_records(issue: str, market: str, raw: Sequence[Sequence[str]],
                     *, company: str | None = None) -> list:
    """按市场契约校验字段数、类型与取值域；异常一律抛出，不转成缺失值。"""
    expected = _FIELDS[market]
    out = []
    for index, fields in enumerate(raw):
        if len(fields) != len(expected):
            raise MarketDataError("%s/%s 第 %d 条字段数为 %d，应为 %d: %r" % (
                issue, market, index, len(fields), len(expected), fields))
        values = {}
        for name, text in zip(expected, fields):
            text = text.strip()
            if name in _EMPTY_COLUMNS:
                if text != "":
                    raise MarketDataError("%s/%s 第 %d 条占位列 %s 应为空，实为 %r" % (
                        issue, market, index, name, text))
                continue
            if name == "company":
                if not text:
                    raise MarketDataError("%s/%s 第 %d 条公司代号为空" % (issue, market, index))
                if company is not None and text != company:
                    raise MarketDataError("%s/%s 请求公司 %s，响应含公司 %s" % (
                        issue, market, company, text))
            elif name == "match_id" and "match_id" not in expected:
                raise MarketDataError("内部错误：%s 无 match_id 列" % market)
            elif name in ("slot", "match_id"):
                try:
                    values[name] = float(int(text))
                except ValueError as exc:
                    raise MarketDataError("%s/%s 第 %d 条 %s=%r 不是整数" % (
                        issue, market, index, name, text)) from exc
            else:
                body = text[:-1] if name in _PERCENT_COLUMNS and text.endswith("%") else text
                if name in _PERCENT_SIGN_REQUIRED and not text.endswith("%"):
                    raise MarketDataError("%s/%s 第 %d 条 %s=%r 缺少百分号" % (
                        issue, market, index, name, text))
                try:
                    values[name] = float(body)
                except ValueError as exc:
                    raise MarketDataError("%s/%s 第 %d 条 %s=%r 不是数值" % (
                        issue, market, index, name, text)) from exc
                if name in _PERCENT_COLUMNS:
                    values[name] = values[name] / 100.0
                if values[name] <= 0:
                    raise MarketDataError("%s/%s 第 %d 条 %s=%r 非正" % (
                        issue, market, index, name, text))
        if values["slot"] < 1:
            raise MarketDataError("%s/%s 第 %d 条场次号 %s < 1" % (
                issue, market, index, values["slot"]))
        # 注意：不要复用参数名 company，否则下一条记录的校验会拿到这一条的值
        record_company = QUERY_COMPANY_IDS.get(market, fields[0].strip())
        out.append(MarketRecord(issue=issue, market=market, company=record_company,
                                slot=int(values["slot"]),
                                match_id=int(values.get("match_id", 0)),
                                values={k: values[k] for k in _ODDS_COLUMNS[market]}))
    if not out:
        raise MarketDataError("%s/%s 响应为空（0 条记录）" % (issue, market))
    if market == MARKET_WINRATE:
        # 平均胜率必须三者和为 1，否则说明口径理解有误
        for rec in out:
            total = sum(rec.values.values())
            if abs(total - 1.0) > 0.005:
                raise MarketDataError("%s/%s 场次 %d 胜率之和 %.4f 偏离 1" % (
                    issue, market, rec.slot, total))
    return out


def collect(issue: str, market: str, company: str, *, current_issue: bool, **fetch_kwargs):
    """取数 + 解析 + 校验；返回 (原始响应, 记录)，落盘由调用方负责。"""
    url = market_url(issue, market, company, current_issue=current_issue)
    raw = fetch(url, issue=issue, market=market, company=company, **fetch_kwargs)
    declared, fields = parse_records(raw.text)
    if declared != issue:
        raise MarketDataError("请求期次 %s，响应声明 %s" % (issue, declared))
    records = validate_records(
        issue, market, fields,
        company=None if (current_issue or market in _COMPANYLESS_MARKETS) else company)
    return raw, records


def write_raw(raw: RawResponse, directory: Path) -> Path:
    """原样保存响应文本，文件名可追溯到来源。"""
    directory.mkdir(parents=True, exist_ok=True)
    company = raw.company if not raw.url.startswith(BASE_URL + "/data/") else "all"
    path = directory / ("%s_%s_c%s.xml" % (raw.issue, raw.market, company))
    path.write_text(raw.text, encoding="utf-8")
    return path


def write_records(records: Iterable, path: Path, market: str) -> int:
    """把记录写成 CSV（表头固定、列序稳定）。"""
    columns = ["issue", "market", "company", "slot", "match_id", *_ODDS_COLUMNS[market]]
    rows = [r.as_row() for r in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row[c] for c in columns})
    return len(rows)
