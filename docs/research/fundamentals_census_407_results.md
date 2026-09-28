# #407 基本面数据普查结果

完成了 100 场分层样本、独立的 3 场历史回归样本，以及原始响应、字段矩阵和独立来源核验。这里的完成范围是采集能力与数据风险普查，不是生产特征或结算数据准入。

证据目录：`data/derived/fundamentals_census/20260905_full/`。
完整报告：`quarto/_output/quarto/06_fundamentals_census.html`。
数据合同见 [fundamentals_census_data_contract.md](fundamentals_census_data_contract.md)，助手函数清单见 [fundamentals_helper_governance_407.md](fundamentals_helper_governance_407.md)。

## 样本与访问

主样本来自 Nowscore 原生期号 25053、25075、26092，配额为 35、35、30，共 70 场历史与 30 场在诊断抽样时尚未开始的比赛，覆盖英甲、英乙、荷乙、日职联、日职乙、巴西甲、巴西乙、美职业。候选分母为 1082：100 入选、99 合格未选、14 在当前期抽样时已开始、869 不在比赛类别范围内。这是分层诊断样本，不能据此估计整体来源错误率。

名单的分组日期是彩票日，不能直接和凌晨时刻拼成自然日。初版因此有 58 个入选时间被提前一天。v2 保留原始分组日期和完整截止时间，使用声明的诊断转换规则，并再次与分析页核对。重算替换了 5 个样本；v1、v2、旧/新哈希和实际修订时间全部保留。修订不是当时已经冻结的可交易选择。

主样本 200/200 个分析文档解析成功，另需 100 份 Nowscore 外部 JS 才能读取历史数组。历史样本每来源 70 份为 `HISTORICAL_PROXY`；当前样本每来源 30 份的全部所需响应均早于诊断开球时间，记为 `OBSERVED`，但不自动授权任何模型或结算使用。

使用正常 Chrome 会话捕获原始响应；分析请求采用 20 秒超时、10 MiB 上限，每来源相邻顶层采集至少约 5.3 秒，没有无界重试。先前 Titan 普通 HTTP 442、Nowscore 简化请求重置、官方站点维护和 DNS/406 失败均保留在各自的证据记录中，不能将 HTTP 200 等同于可用数据。完整原始语料还保留了修订移出的 5 场，主矩阵分母始终为最终入选的 100 场。

## 字段矩阵

以下为成功提取到非空内容的场数，每来源分母均为 100；空值与未识别字段另列在 `main/fields.csv`。两个来源的记录深度和阵容范围并不相同。

| 字段 | Nowscore | Titan |
| --- | ---: | ---: |
| 主队近期历史 | 100 | 100 |
| 客队近期历史 | 100 | 100 |
| 历史交锋 | 95 | 95 |
| 积分统计总计 | 100 | 100 |
| 伤停条目 | 59 | 59 |
| 上一场阵容/出场球员 | 100 | 68 |
| 未来赛程 | 93 | 93 |
| 场地 | 0 | 69 |
| 天气 | 0 | 89 |
| 温度原文 | 0 | 89 |

上一场阵容不是本场确认首发；Titan 独立出场评分表和 Nowscore 首发/替补名单也不能默认覆盖相同球员。伤停保留球员与原因原文，不推断严重程度。天气字段的零表示本次提取器没有识别到内容，不代表全站所有页面都不提供天气；旧版页面的布局限制已单独记录。

## 差异与独立核验

主样本历史记录为 Nowscore 7732 条、Titan 11825 条。4093 条比较结果属于历史范围/深度差异；在可比的同一历史比赛日期、方向、进球数及积分统计总计中，未发现数值冲突。该结果不是所有基本面事实都正确或独立的证明。

另有 4 场名单与分析页的时间不一致，共 8 条来源观察：

- 2741446 明尼苏达—圣路易斯、2741602 新英格兰—蒙特利尔、2741612 芝加哥—纽约红牛：官方公布的 7:30 与分析页一致，但名单时刻晚 10 分钟。没有取得足以确认实际开球的原始证据，保留 `TIME_SEMANTICS_UNRESOLVED`，不直接改值。
- 2741604 休斯顿—洛杉矶银河：原俱乐部公告明确说明从 7 月 25 日延期至 9 月 6 日。当前分析页各有 16 条历史记录的日期晚于原期号名单日期，不能挂接到原始决策时点。

独立回归样本：

- 20064/293（1870517）埃克塞特—科尔切斯特：新抓取名单为常规时间 2–1；原俱乐部战报区分加时后的 3–1。该案例检验比分口径，不声称当前 Nowscore 常规比分错误。
- 22041/247（2148390）山形—冈山：原名单为 4 月 3 日，当前双源分析均指向 8 月 31 日。J.League 原公告与重开战报证明了重开实例；每来源有 51 条历史记录晚于原名单日期。双源一致仍不能用于原期号历史特征。
- 161103/91（1326813）南非—塞内加尔：新名单和当前分析页保留 2016 年原赛身份；FIFA 公告要求在 2017 年重赛。原赛和重赛必须分开，公告本身不证明两场的具体比分，也不证明彩票结算。

另外独立抽查了双源共有历史中的浦和—东京 3–2、圣迭戈—科罗拉多 2–0，均有原俱乐部报告支持。核验记录限定到这些具体事实，保留原值、URL、原始字节哈希、审阅者、理由和版本。未知或共享的统计上游没有独立投票权。

主要原始证据：

- [明尼苏达官方赛程](https://www.mnufc.com/news/mnufc-releases-2025-schedule)、[新英格兰比赛指南](https://www.revolutionsoccer.net/news/matchday-guide-revs-vs-cf-montreal-july-25-2025)、[Soldier Field 原活动页](https://www.soldierfield.com/events/detail/chicago-fire-fc-vs-new-york-red-bulls-2)。
- [休斯顿原俱乐部延期说明](https://www.houstondynamofc.com/news/match-preview-houston-dynamo-fc-host-the-la-galaxy-in-continued-playoff-push)。
- [埃克塞特原战报](https://www.exetercityfc.co.uk/news/2020/june/-match-report-exeter-city-3--colchester-united-1)、[J.League 原处理公告](https://www.jleague.jp/news/article/22134/)、[重开战报](https://www.jleague.jp/news/article/23214/)、[FIFA 原重赛公告](https://inside.fifa.com/tournaments/mens/worldcup/2018russia/news/south-africa-vs-senegal-world-cup-qualifier-to-be-replayed-in-november-2907241)。
- [浦和原赛果](https://www.urawa-reds.co.jp/en/topteamtopics/226988/)、[圣迭戈原战报](https://www.sandiegofc.com/news/match-recap-san-diego-fc-secures-third-straight-win-with-2-0-victory-over-colorado-rapids)。

八类比赛的官方来源入口、实际访问状态和独立性边界在 `official-registry.json`。CBF 两个入口本环境 DNS 失败；KNVB 重赛入口返回维护正文，不作为裁决证据。部分 MLS 官方统计页面有已公开的 Opta 集成历史；本次抽查依赖原俱乐部叙述，没有把官方域名自动当成独立统计上游。

## 验证与交接

- `.venv/bin/python -m pytest tests/test_fundamentals_census.py tests/test_nowscore_settlement.py -q`：62 passed。
- `Rscript tests/testthat.R`：通过。既有映射测试需访问外置数据库；沙箱初次失败的原因和重跑结果已记录。
- `.venv/bin/python scripts/check_cutoff_governance.py`：PASS。
- 两套语料均在第二个新进程中回放，完整 receipt 与所有 CSV 哈希完全一致。
- Quarto 1.10.18 从声明输入干净执行，关闭 cache/freeze、执行错误致命；完整报告成功。Chrome 检查确认 7 张结果表、7 条独立核验案例、无执行错误和页面横向溢出，并检查了样本、差异及核验表截图。

工作流 `.github/workflows/fundamentals-census.yml` 定义了离线 Python/R 检查、cutoff 检查和保存响应的 QMD 渲染。这里只报告本地实际执行结果，没有宣称尚未运行的远程 CI 成功。复用的 `src/nowscore_settlement.py` 仍属于工作区内 #405 的未提交成果；代码快照及其测试包含在本次本地证据中，发布 PR 时必须一并处理该依赖，不能遗漏。

#408 应接收当前字段合同、原始证据、三项未决时间语义，以及延期/重开实例隔离要求。生产适配器集成时替换旧的吞错数组解析和截断表格接口；不得把本次历史快照直接变成可用的历史特征。#405 的 Nowscore-only 结算语义、任何数据库结算值及模型均未改变。
