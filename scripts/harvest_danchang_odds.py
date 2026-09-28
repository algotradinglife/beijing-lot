"""命令行入口：抓取北单期次的欧赔（1X2）与大小球市场数据并落盘。

用法::

    ./.venv/bin/python scripts/harvest_danchang_odds.py --issues 26087-26097

输出：

* inputs/nowscore_raw/{issue}_{market}_c{company}.xml  原始响应
* inputs/danchang_1x2.csv                              欧赔记录
* inputs/danchang_overunder.csv                        大小球记录

本期（列表最后一个期次）走整期静态文件，其余走按期次查询。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.nowscore_danchang_odds import (  # noqa: E402
    COMPANY_NAMES, MARKET_1X2, MARKET_OVERUNDER, MARKET_PAYOUT, MARKET_WINRATE,
    QUERY_COMPANY_IDS, MarketDataError, collect, write_raw, write_records,
)

RAW_DIR = REPO_ROOT / "inputs" / "nowscore_raw"
#: 需要抓取的市场及其公司；平均胜率/返还率无公司维度
COMPANIES = {
    MARKET_1X2: ("0", "1", "3"),
    MARKET_OVERUNDER: ("1", "3"),
    MARKET_WINRATE: (QUERY_COMPANY_IDS[MARKET_WINRATE],),
    MARKET_PAYOUT: (QUERY_COMPANY_IDS[MARKET_PAYOUT],),
}


def parse_issues(spec: str) -> list:
    out = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            start, end = (int(x) for x in chunk.split("-"))
            out.extend(str(i) for i in range(start, end + 1))
        elif chunk:
            out.append(chunk)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues", required=True, help="如 26087-26097 或 26097")
    parser.add_argument("--current", help="视为本期的期次（走整期静态文件），默认最后一个")
    args = parser.parse_args(argv)

    issues = parse_issues(args.issues)
    current = args.current or issues[-1]
    failures = []
    for market in (MARKET_1X2, MARKET_OVERUNDER, MARKET_WINRATE, MARKET_PAYOUT):
        rows = []
        for issue in issues:
            is_current = issue == current and market in (MARKET_1X2, MARKET_OVERUNDER)
            companies = ("0",) if is_current else COMPANIES[market]
            for company in companies:
                try:
                    raw, records = collect(issue, market, company, current_issue=is_current)
                except MarketDataError as exc:
                    failures.append("%s/%s/c%s: %s" % (issue, market, company, exc))
                    print("  失败 %s/%s/c%s: %s" % (issue, market, company, exc))
                    continue
                write_raw(raw, RAW_DIR)
                rows.extend(records)
                print("  %s %s c%-2s -> %4d 条 (%s)" % (
                    issue, market, company, len(records), COMPANY_NAMES.get(company, company)))
        path = REPO_ROOT / "inputs" / ("danchang_%s.csv" % market)
        write_records(rows, path, market)
        print("%s: %d 条 -> %s" % (market, len(rows), path.relative_to(REPO_ROOT)))
    if failures:
        print("\n%d 个请求失败" % len(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
