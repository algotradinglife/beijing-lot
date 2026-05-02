# 北单 (北京单场) 历史数据源调研

**Scope:** 让球胜平负 (3 / 1 / 0) 玩法的历史回测数据可获得性。
**Date:** 2026-05-02
**Methodology:** Each candidate source was actually fetched (curl), parsed, and verified against multiple historical issues (期). All findings below are from real responses, not documentation claims.

---

## TL;DR (verdict)

| What we need | Achievable? | Source | Notes |
|---|---|---|---|
| Full list of matches sold per 期 (home/away/league/kickoff) | YES — clean | `zx.500.com/zqdc/kaijiang.php?playid=1&expect=YYNNN` | back to ~2007 |
| 让球数 (handicap) per match | YES — clean | same | sign convention: `-N` = home gives, `+N` = away gives, `0` = level |
| Settlement SP for the **winning outcome only** | YES — clean | same | only one SP is preserved (the one that paid) |
| Settlement SP for **all three** outcomes (3 / 1 / 0) — even losing legs | **NO for past matches** | — | Losing-side SPs are not archived anywhere we found. They are visible only **before kickoff** as 参考SP (real-time) and disappear after settlement. |
| 销量分布 (% stake on 3 / 1 / 0 per match) | **NO for past matches** | — | The bet page shows a `投注比例` column, but values are blank (`--`) for already-settled matches and per-issue 全国销量 has been zeroed out everywhere we checked. Only live-capture during the betting window will get this. |
| Final score / settlement result code | YES — clean | same | result codes evolved: pre-2025-ish issues use `胜/平/负`; recent issues use `3/1/0` |
| Average European odds (1 X 2) at kickoff | YES — bonus | same | three numbers per match (主胜 / 平 / 客胜) — useful as a pricing-fair baseline |

**Bottom line for the strategy:** post-game backtest on the **winning-outcome SP** plus average European 1x2 odds is fully feasible from one source (500.com). But the original **3-way SP vector** and the **public stake split** can only be captured **forward in time, in real-time** (during the betting window). If the strategy depends on either of those, you must build a live data collector now and start banking observations going forward — they cannot be backfilled.

---

## A. 500.com (PRIMARY RECOMMENDATION)

**Status:** Works. Clean HTML, GB2312-encoded, no JS rendering required, no anti-bot. Effort: **LOW**.

### Two key URLs

1. **Issue list (deep history):**
   `https://trade.500.com/pages/comm/projectlist.php?lotid=9&playid=34&needleft=1&type=2`
   — Contains a `<select>` with **2,115 distinct 期号** spanning 2007-05 to today. Format changed once:
   - 2007–2019: `YYMMNN` 6-digit (e.g. `070502`, `141231`)
   - 2020–now: `YYNNN` 5-digit (e.g. `20011`, `25125`, `26051`)
   - Year-by-year count from the dropdown (sample): 2007:128, 2010:214, 2014:140, 2018:59, 2022:58, 2024:59, 2025:57, 2026:34 (YTD).
   - The reduction from ~200/yr in 2010-2013 to ~58/yr from 2015 reflects the change to a continuous-ish numbering scheme (each issue contains many matches now vs. one match per old issue).

2. **Per-issue let-goal (让球胜平负) results page:**
   `https://zx.500.com/zqdc/kaijiang.php?playid=1&expect=<EXPECT>`
   — `playid=1` is 让球胜平负. `expect` must be a real issue from the list above. Returns ~30–250 KB GB2312 HTML containing one row per match.

### Sample row HTML

```html
<tr>
  <td>1</td>
  <td><a class="league" title="挪超">挪超</a></td>
  <td class="eng">05-01 01:00</td>                     <!-- kickoff (no year) -->
  <td class="text_r"><a title="博德闪耀">博德闪耀</a></td>  <!-- home -->
  <td class="eng"><span class="green">-2</span></td>    <!-- handicap -->
  <td class="text_l"><a title="斯达">斯达</a></td>        <!-- away -->
  <td class="eng">5:0</td>                              <!-- final score -->
  <td>3</td>                                            <!-- result code: 3/1/0 -->
  <td>&nbsp;</td>
  <td class="eng red">1.76</td>                         <!-- winning-side SP -->
  <td>&nbsp;</td>
  <td>1.11</td>                                         <!-- 平均欧赔 主胜 -->
  <td>9.16</td>                                         <!-- 平均欧赔 平 -->
  <td>17.31</td>                                        <!-- 平均欧赔 主负 -->
</tr>
```

### Scraper hints

```python
# request
r = requests.get(
    f"https://zx.500.com/zqdc/kaijiang.php?playid=1&expect={expect}",
    headers={"User-Agent": "Mozilla/5.0 ..."}, timeout=15,
).content.decode("gb18030")  # GB2312 = subset, GB18030 is safer

# extract
import re
ROW = re.compile(
    r'<tr>\s*<td>(?P<idx>\d+)</td>'
    r'(?P<body>.*?)</tr>', re.S)
LEAGUE  = re.compile(r'class="league"[^>]*title="([^"]+)"')
TIME    = re.compile(r'<td class="eng">([0-9]{2}-[0-9]{2}\s+[0-9]{2}:[0-9]{2}[^<]*)</td>')
HOME    = re.compile(r'<td class="text_r"><a[^>]*title="([^"]+)"')
HANDI   = re.compile(r'<td class="eng"><span class="(?:green|black|red)">([^<]+)</span>')
AWAY    = re.compile(r'<td class="text_l"><a[^>]*title="([^"]+)"')
SCORE   = re.compile(r'<td class="eng">(\(?[0-9]+:[0-9]+[^<]*)</td>')
SP      = re.compile(r'<td class="eng red">([0-9]+\.[0-9]+)</td>')
RESULT  = re.compile(r'<td>(\d|胜|平|负)</td>\s*<td>&nbsp;</td>\s*<td class="eng red">')
EU      = re.compile(r'<td>([0-9]+\.[0-9]+)</td>')          # take last 3 hits
```

A single requests-only Python scraper (~80 lines) covers the whole dataset. **Confirmed: no captcha, no JS, no rate-limit triggered** at ~1 req/sec across ~10 test fetches.

### Validated sample data (5+ historical issues)

> Note: 全国销量 (national sales total) and per-outcome stake distribution have been **zeroed out / stripped** by 500.com on the historical results page (every issue we checked across 2024-2026 reports `0 元`). 平均SP值 (avg SP per playtype across the issue) is preserved.

#### Issue 26051 (2026-05-01) — 14 matches, 平均SP 0.10 (only 1 settled at fetch time)
| # | 联赛 | Kickoff | Home | RQ | Away | Score | Result | winSP | 欧赔 主/平/客 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 挪超 | 05-01 01:00 | 博德闪耀 | -2 | 斯达 | 5:0 | 3 | 1.76 | 1.11 / 9.16 / 17.31 |
| 2 | 丹甲 | 05-01 01:00 | 埃斯比约 | 0 | 霍森斯 | 0:1 | 0 | 2.25 | 2.71 / 3.18 / 2.44 |
| 3 | 欧罗巴联赛 | 05-01 03:00 | 布拉加 | 0 | 弗赖堡 | 2:1 | 3 | 2.71 | 2.40 / 3.06 / 3.20 |
| 4 | 欧罗巴联赛 | 05-01 03:00 | 诺丁汉森林 | 0 | 阿斯顿维拉 | 1:0 | 3 | 4.24 | 2.86 / 3.23 / 2.53 |
| 5 | 欧协联赛 | 05-01 03:00 | 巴列卡诺 | 0 | 斯特拉斯堡 | 1:0 | 3 | 2.11 | 2.05 / 3.35 / 3.61 |

#### Issue 26049 (2026-04-29) — 52 matches, 平均SP 3.07
| # | 联赛 | Kickoff | Home | RQ | Away | Score | Result | winSP | 欧赔 主/平/客 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 荷乙 | 04-29 00:45 | 罗达JC | 0 | 瓦尔韦克 | 1:1 | 平 | 3.66 | 2.32 / 3.46 / 2.78 |
| 2 | 葡甲 | 04-29 01:00 | 费伦斯 | 0 | 托伦斯 | 0:0 | 平 | 3.35 | 3.32 / 3.13 / 2.12 |
| 3 | 瑞典甲 | 04-29 01:00 | 北雪平 | -1 | 兰斯科罗纳 | 1:3 | 负 | 3.09 | 1.60 / 3.89 / 4.88 |
| 4 | 英冠 | 04-29 02:45 | 南安普顿 | 0 | 伊普斯维奇 | 2:2 | 平 | 2.93 | 2.17 / 3.51 / 3.12 |
| 5 | 英甲 | 04-29 02:45 | 北安普顿 | 0 | 巴恩斯利 | 0:1 | 负 | 2.84 | 2.96 / 3.77 / 2.10 |

#### Issue 26045 (2026-04-14/15) — 71 matches, 平均SP 3.06
| # | 联赛 | Kickoff | Home | RQ | Away | Score | Result | winSP | 欧赔 主/平/客 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 芬兰杯 | 04-14 23:00 | 基柏 | -2 | MP米克力 | 1:2 | 负 | 1.68 | 1.70 / 3.73 / 4.39 |
| 2 | 意乙 | 04-15 01:00 | 卡坦扎罗 | 0 | 摩德纳 | 2:2 | 平 | 3.18 | 2.44 / 3.20 / 2.78 |
| 3 | 瑞典甲 | 04-15 01:00 | IFK瓦纳默 | -1 | 松兹瓦尔 | 3:0 | 胜 | 5.20 | 1.84 / 3.46 / 3.90 |
| 4 | 英甲 | 04-15 02:45 | 维尔港 | 0 | 巴恩斯利 | 0:0 | 平 | 3.52 | 2.67 / 3.27 / 2.51 |
| 5 | 英甲 | 04-15 02:45 | 莱顿东方 | 0 | 曼斯菲尔德 | 0:0 | 平 | 3.24 | 2.01 / 3.40 / 3.47 |

#### Issue 26019 (2026-01-28) — 89 matches, 平均SP 3.09
| # | 联赛 | Kickoff | Home | RQ | Away | Score | Result | winSP | 欧赔 主/平/客 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 比乙 | 01-28 03:10 | 亨克B队 | 0 | 莫伦贝克 | 0:2 | 0 | 2.52 | 2.76 / 3.55 / 2.22 |
| 2 | 比乙 | 01-28 03:00 | 布鲁日B队 | +1 | 科特赖克 | 2:0 | 3 | 2.54 | 4.81 / 3.94 / 1.58 |
| 3 | 比乙 | 01-28 03:00 | 艾斯登 | -1 | ROC沙勒罗瓦 | 1:0 | 1 | 3.97 | 1.40 / 4.27 / 6.86 |
| 4 | 比乙 | 01-28 03:00 | 欧本 | 0 | SC洛克伦 | 1:1 | 1 | 3.56 | 2.55 / 3.30 / 2.49 |
| 5 | 比乙 | 01-28 03:00 | 比肖特VA | -1 | 瑟兰联 | 0:0 | 0 | 3.12 | 1.44 / 4.27 / 5.98 |

#### Issue 25125 (2025-12-23/24) — 131 matches, 平均SP 3.12
| # | 联赛 | Kickoff | Home | RQ | Away | Score | Result | winSP | 欧赔 主/平/客 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 澳超 | 12-23 16:15 | 墨尔本城 | -1 | 麦克阿瑟FC | 1:1 | 0 | 2.45 | 1.51 / 4.24 / 5.78 |
| 2 | 非洲杯 | 12-23 23:00 | 塞内加尔 | -2 | 博茨瓦纳 | 3:0 | 3 | 2.04 | 1.11 / 8.33 / 22.65 |
| 3 | 非洲杯 | 12-24 01:30 | 尼日利亚 | -1 | 坦桑尼亚 | 2:1 | 1 | 3.59 | 1.37 / 4.36 / 9.16 |
| 4 | 非洲杯 | 12-24 04:00 | 突尼斯 | -1 | 乌干达 | 3:1 | 3 | 3.20 | 1.68 / 3.23 / 6.01 |
| 5 | 英联杯 | 12-24 04:00 | 阿森纳 | -1 | 水晶宫 | 1:1 | 0 | 3.41 | 1.50 / 4.27 / 6.28 |

#### Issue 24011 (2024-12-29/30) — 112 matches, 平均SP 3.05
| # | 联赛 | Kickoff | Home | RQ | Away | Score | Result | winSP | 欧赔 主/平/客 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 澳超 | 12-29 16:45 | 悉尼 | 0 | 惠灵顿 | 3:1 | 3 | 2.09 | 1.73 / 4.04 / 4.00 |
| 2 | 意甲 | 12-30 01:30 | 佛罗伦 | 0 | 都灵 | 1:0 | 3 | 2.10 | 2.14 / 3.12 / 3.69 |
| 3 | 意甲 | 12-30 01:30 | 那不勒 | -1 | 蒙扎 | 0:0 | 0 | 2.88 | 1.57 / 4.13 / 5.56 |
| 5 | 英冠 | 12-30 02:00 | 南安普 | -2 | 普利茅 | 2:1 | 0 | 2.07 | 1.29 / 5.78 / 8.41 |
| 6 | 葡超 | 12-30 02:45 | 本菲卡 | -2 | 法马利 | 3:0 | 3 | 4.50 | 1.25 / 5.78 / 10.41 |

### Coverage estimate

- ~2,115 issues × ~80 matches/issue (post-2014) ≈ **~170,000 historical matches** parseable end-to-end. Pre-2014, issues are smaller (often 1 match/issue) and counts are higher (~200/yr) — total record count back to 2007 is on the order of 200K+.
- One pass at 1 req/sec = **~35 minutes** to download the entire archive. Recommend ~0.5 req/sec to be friendly = ~70 minutes. No anti-bot triggered in ad-hoc testing.

---

## B. 中国足彩网 / 第一彩 — `cp.zgzcw.com` (SECONDARY / VALIDATION)

**Status:** Works. AJAX-driven; raw JSON / HTML fragment endpoints. Effort: **LOW–MEDIUM** (need to discover real drawNo per year/month).

### Endpoints discovered (from `/lottery/jc/js/singleKaijiang.js`)

```text
POST  https://cp.zgzcw.com/lottery/getbdwqissue.action
      data: year=YYYY&month=MM&lottery=200      # returns JSON list of drawNo
                                                # (we got {} in tests — likely needs proper Origin/CSRF; verifiable in browser devtools)

POST  https://cp.zgzcw.com/dc/getSingleKaijiangBody.action
      data: lottery=200&year=YYYY&drawNo=YYNNN   # returns HTML <tr> fragment with 1 row per match
      headers: Referer: https://cp.zgzcw.com/dc/footballSingleKaijiang.action
               X-Requested-With: XMLHttpRequest
```

`lottery=200` = 让球胜平负 (other codes: 230 总进球, 250 比分, 240 半全场, 210 上下单双, 270 胜负).

### Verified response (issue 26051, lottery=200)

252 KB HTML; the per-row structure is much cleaner than 500.com:

```html
<tr id="tr_1" rq="-2" sg="胜">
  <td>1</td>
  <td gameId="1">挪超</td>
  <td>26-05-01 00:55:00</td>           <!-- bet-cutoff time, full date -->
  <td>博德闪耀</td><td>斯达</td>
  <td>-2</td>                           <!-- handicap -->
  <td>5:0</td>                          <!-- final score -->
  <td>胜</td>                           <!-- result -->
  <td>1.76</td>                         <!-- winning-side SP -->
  <td>0</td><td>0</td><td>0</td>        <!-- 中奖注数 / 单注奖金 / 应派奖金 (also zeroed) -->
</tr>
```

Useful **only** as a cross-validation source. Same SP (1.76 here) as 500.com confirms data integrity. Date is `YY-MM-DD` (full date, including year) which is a **plus** vs. 500.com's `MM-DD` (year must be inferred from issue number).

### Bet page (pre-kickoff, all 3 SPs visible)

`https://cp.zgzcw.com/lottery/bdplayvsforJsp.action?lotteryId=200`

Each match row contains a hidden input:

```html
<input type="hidden" id="ht_1" class="spArr" value="-1.76 0 0" />   <!-- settled, 胜 paid 1.76 -->
<input type="hidden" id="ht_2" class="spArr" value="0 0 -2.25" />   <!-- settled, 负 paid 2.25 -->
```

Convention: `value="W D L"`. **Pre-kickoff** all three are positive (e.g. `1.76 3.40 5.20`), and a real-time scrape would capture all three reference SPs. **Post-settlement** only the winning one is preserved (with a `-` prefix flagging it). **This confirms losing-side SPs are not retrievable for past matches.**

The same page exposes 平均欧赔 in `<input id="esp_N" value="1.11 9.02 16.70">`.

---

## C. 官方 北京体彩 — `bjcp.gov.cn` / `bjcp.cn`

**Status:** Both `https://www.bjcp.gov.cn` and `https://www.bjcp.cn` failed TLS/connectivity from this network (curl error 35 / 52 / DNS or cert issue). Even if reachable, the official site historically offers per-issue PDF 开奖公告 only — **PDF parsing**, no SP/handicap, just totals and prize tiers. Effort: **HIGH** for low-value data (no per-match SP). **Skip.**

---

## D. 爱彩网 (`aicai.com`) / 看球网 (`kanqiu.com`) / 7M (`7m.com.cn`)

| Site | Reachable | Has 北单 archive? |
|---|---|---|
| `www.aicai.com` | timeout (curl 28) | n/a |
| `www.kanqiu.com` | TLS fail (curl 35) | n/a |
| `www.7m.com.cn` | YES | only live odds + general match data, no 北单 archive of SPs |

None viable.

---

## E. 第三方 / 体彩 API

| Endpoint | Status |
|---|---|
| `api.api68.com/` | Returns "Hello World!" placeholder — dead. |
| `webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=N` | Live JSON API, returns 大乐透 (gameNo=85), 胜负游戏 (90), 排列3 (35), 6场半全场 (98), 4场进球 (94). **No 北单 game ID** found across gameNo 1–100 brute-force. Reason: 北单 is run by 北京市体彩中心, not the national 体彩中心 (sporttery.cn) — they are separate operators. |
| Paid aggregators (纳米数据, 全速数据, 飞鲸 …) | Likely have 北单 historical packages, but require commercial contracts — no free access verified. |

**Conclusion:** No free public JSON API for 北单 history. Scrape 500.com.

---

## F. GitHub repos

GitHub search across `北京单场`, `北单`, `beidan`, `让球胜平负` returned:

- `lotterydemo`, `lottery-ticket`, `wkjw/very`, `hackervip996/demo` — these are commercial-grade lottery-app source code (Java/Android/iOS) that **mention** 北单 in marketing copy but are not historical-data dumps.
- `lottery-code/football-lottery` (3.9 MB), `yinruyu/ball_banker` (2.5 MB) — code for scraping/serving multi-house odds. Worth scanning their codebase for an existing 500.com beidan parser, but no static dataset.
- No repository found that publishes a clean historical 北单 SP / handicap dataset. **The data needs to be scraped fresh.**

---

## Final architecture recommendation

### Backfill (one-shot, retroactive)

```text
Source:    zx.500.com/zqdc/kaijiang.php?playid=1&expect=<EXPECT>
Issues:    Enumerate from trade.500.com/pages/comm/projectlist.php?lotid=9&playid=34&needleft=1&type=2  (2,115 期 dropdown)
Capture:   issue_id, match_idx, league, kickoff (date inferred from issue),
           home, away, handicap, final_score, result_code,
           winning_side_SP, eu_avg_home, eu_avg_draw, eu_avg_away
Storage:   one parquet/csv per year is fine; ~170K rows total
Effort:    ~80 LOC Python + requests + a parser. ~1 day to build & QA.
Throttle:  0.5 req/s. ~70 min full-archive download.
```

### Live capture (must run forward, cannot be backfilled)

For each upcoming 期 (typically released ~14:00 the day before):

```text
Bet page:  trade.500.com/bjdc/index.php           # 500.com - has 投注比例 column populated pre-kickoff
           cp.zgzcw.com/lottery/bdplayvsforJsp.action?lotteryId=200   # zgzcw - has all-3-SP `spArr` populated pre-kickoff
Frequency: every 5–15 minutes from issue release until kickoff of last match
Capture:   reference-SP vector (W, D, L), 投注比例 vector (% on 3 / 1 / 0), 全国销量 (current snapshot),
           timestamp, change deltas vs. previous snapshot
Storage:   append-only time series (parquet partitioned by issue_id)
Effort:    ~150 LOC Python + APScheduler.
```

The **public-bias signal (% stake on each outcome)** and the **complete pre-kickoff SP vector** are both achievable but **only via this live path**. They will accumulate from day-1 of running the collector.

---

## Risks / gaps

1. **Sales distribution by outcome (3 / 1 / 0 %) is not publicly archived.** This is the cleanest "public bias" signal and the strategy hinges on it. **Consequence:** the strategy cannot be **directly** backtested against historical bias unless we proxy it from kept-side SP × 平均欧赔 (an SP/EU-implied-prob ratio is a reasonable proxy for "how heavy did the 北单 pool weight this outcome relative to global market," and is fully backfillable).
2. **Losing-outcome SPs are not archived.** Same root cause as (1). For backtesting, you will only know the SP that paid out. Modeling EV on legs we did not bet (e.g., "what would it have paid if we'd taken the draw") needs the EU-odds-implied-prob proxy.
3. **500.com encoding pitfalls:** GB2312 declared, but content sometimes contains GB18030-only characters (rare team names). Decode with `gb18030` to be safe.
4. **Issue-number format change in 2020.** Parser must handle 5-digit (`YYNNN`) and 6-digit (`YYMMNN`) coexisting in the dropdown.
5. **Year not in row kickoff field.** The match-time cell is `MM-DD HH:MM`. Year must be inferred from the issue number prefix (e.g. `26051` → 2026; `070502` → 2007). Fixture cross-midnight matches are rare but worth handling.
6. **500.com may eventually rate-limit or change the page.** The kaijiang.php URL has been stable for 10+ years per the 2007 issues being reachable, but mirror-down to local storage immediately after first scrape.
7. **No anti-bot defense was triggered** at our test rate, but a User-Agent header is required (default curl UA gets a 404). Cloudflare-style challenge has not appeared in any of ~30 test fetches.
8. **Settled-match same-day fetches:** an issue fetched while it is still in-play shows 0 settlement for unsettled matches. Wait until ≥6 h after the latest kickoff in the issue before treating data as final.
