# 待核查初稿：MPR-1.1＋1200元原动态散选


本 Markdown
仅提交2026年10月27日下注单对应的12场审核记录，不含历史54轮研究。本初稿供用户核查，未发布、未购买、未登记定时更新。窗口：香港时间10月26日22:00至27日22:00。采用MPR-1.1人工审查三分类直接选票，不再叠加GLOBAL；原生和市场比分网格只是参考，不能当作已被MPR校正的比分预测。策略使用1200元原DYNAMIC_SET动态散选、8组七串一、每组75注，不做保护票换入；参考BS-0.2.1-alpha的动态选择实现，本稿按当前窗口和新截止分组，不冒称完全复现其历史UTC日界线/T−24h规则，SP门槛按本次用户要求改为三项最低值严格\>2；属于明确标识的草稿搭配。

决策截止UTC： 2026-10-26 13:31:19
。原基本面/盘口来源截止与专家审查生成时间分别保留，不将旧对象改写为新截止。

| fixtures | groups | tickets | budget_cny | replacement_tickets | model_union_coverage |
|---------:|-------:|--------:|-----------:|--------------------:|---------------------:|
|       12 |      8 |     600 |       1200 |                   0 |              0.39556 |

联合覆盖率仅为专家概率及比赛独立假设下的模型值，非实际命中率。预算全部用于原动态散选，无800元参考单、无保护票置换。

| group_id | slots                       | new_ticket_count | new_cost_cny |
|:---------|:----------------------------|-----------------:|-------------:|
| g01      | 386,387,388,389,390,392,394 |               75 |          150 |
| g02      | 387,388,389,390,392,394,396 |               75 |          150 |
| g03      | 388,389,390,392,394,396,397 |               75 |          150 |
| g04      | 389,390,392,394,396,397,398 |               75 |          150 |
| g05      | 390,392,394,396,397,398,399 |               75 |          150 |
| g06      | 392,394,396,397,398,399,400 |               75 |          150 |
| g07      | 386,394,396,397,398,399,400 |               75 |          150 |
| g08      | 386,387,396,397,398,399,400 |               75 |          150 |

**实际用于本初稿的概率（0–1）**：

| fixture_key | slot | home_name | away_name | handicap | kickoff_at | min_sp | W | D | L |
|:---|---:|:---|:---|---:|:---|---:|---:|---:|---:|
| 26107:386 | 386 | 哥本哈根 | 欧登塞 | -1 | 2026-10-27 02:00:00 | 2.24 | 0.4300 | 0.2700 | 0.3000 |
| 26107:387 | 387 | 塞普西 | CS克拉约瓦大学 | 1 | 2026-10-27 02:00:00 | 2.36 | 0.3700 | 0.3000 | 0.3300 |
| 26107:388 | 388 | 厄勒布鲁 | 法尔肯贝里 | 0 | 2026-10-27 02:05:00 | 2.08 | 0.2900 | 0.3100 | 0.4000 |
| 26107:389 | 389 | 圣塔克 | 本菲卡 | 1 | 2026-10-27 02:45:00 | 2.26 | 0.3400 | 0.2700 | 0.3900 |
| 26107:390 | 390 | FC安道尔 | 布尔戈斯 | 0 | 2026-10-27 03:30:00 | 2.67 | 0.3800 | 0.3300 | 0.2900 |
| 26107:392 | 392 | 蒙彼利埃 | 圣旺红星 | 0 | 2026-10-27 03:40:00 | 2.18 | 0.3400 | 0.3500 | 0.3100 |
| 26107:394 | 394 | 沃尔索尔 | 索尔福德城 | 0 | 2026-10-27 04:00:00 | 2.19 | 0.2800 | 0.3200 | 0.4000 |
| 26107:396 | 396 | 智利大学 | 比尼亚德尔马埃弗顿 | -1 | 2026-10-27 05:00:00 | 2.77 | 0.2800 | 0.3200 | 0.4000 |
| 26107:397 | 397 | 圣菲联合 | 拉普拉塔大学生 | 0 | 2026-10-27 06:00:00 | 2.87 | 0.3515 | 0.3057 | 0.3428 |
| 26107:398 | 398 | 科里蒂巴 | 格雷米奥 | 0 | 2026-10-27 06:30:00 | 2.84 | 0.4000 | 0.3200 | 0.2800 |
| 26107:399 | 399 | 弗拉门戈 | 米内罗竞技 | -1 | 2026-10-27 07:00:00 | 2.18 | 0.4800 | 0.2800 | 0.2400 |
| 26107:400 | 400 | 尤文图德 | 累西腓航海 | -1 | 2026-10-27 07:30:00 | 2.77 | 0.3400 | 0.3400 | 0.3200 |

## \#386 哥本哈根 — 欧登塞

**基本面与定性落点**：
第2对第7；主队本季主场4胜1平、11进4失，近6轮12进3失；客队客场1胜3平2负、5进6失。主胜方向较强，客队客场防守限制大胜。上次0:5不重复放大。

**平局/让平审查**：
普通平局不主动上调；让平为主胜1球，单档22.4%高于赢2球19.9%，适度加强让平保护。

**差距解释**：
让胜领先让负13点：主队进攻和-1.25亚盘支持，但不能把普通主胜65.2%当让胜。
让负与让平仅3点差；0球和1球档接近，保护不稳，保留三选属性。

**调整幅度**： 保持让胜43%，从让负向让平转移约4.6点，幅度为专家假设。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[丹麦超-2\]哥本哈根**](https://info.nowscore.com/team/227.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 11 8 1 2 25 11 14 25 2 72.7% 主 5
4 1 0 11 4 7 13 2 80.0% 客 6 4 0 2 14 7 7 12 1 66.7% 近6 6 4 1 1 12 3 9
13 66.7%[**\[丹麦超-7\]欧登塞**](https://info.nowscore.com/team/229.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 11 3 4 4 10 15-5 13 7 27.3%
主 5 2 1 2 5 9-4 7 10 40.0% 客 6 1 3 2 5 6-1 6 7 16.7% 近6 6 2 3 1 6 9-3
9 33.3% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 11 7 1 3 14 8 6 22 2
63.6% 主 5 4 0 1 7 3 4 12 2 80.0% 客 6 3 1 2 7 5 2 10 2 50.0% 近6 6 4 1
1 6 1 5 13 66.7%半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 11 3 6 2 6 6
0 15 6 27.3% 主 5 1 2 2 3 5-2 5 12 20.0% 客 6 2 4 0 3 1 2 10 3 33.3% 近6
6 2 2 2 3 4-1 8 33.3%

### 对战往绩

近场 主客相同 丹麦超 球会友谊 丹麦杯 类型 日期 主场 比分(半场)角球 客场
主 让球 客 主 和 客 胜负 让球 进球数
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2026-09-06[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)[0-5](https://live.nowscore.com/detail/2998239cn.html)(0-2)6-2[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)0.97[受半球](https://live.nowscore.com/odds/match/2998239.htm)0.91
3.72[3.76](https://live.nowscore.com/1x2/2998239.htm)1.86 胜 赢 大
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2026-04-23[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)[2-1](https://live.nowscore.com/detail/2956512cn.html)(2-0)6-11[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)1.06[一球](https://live.nowscore.com/odds/match/2956512.htm)0.82
1.60[4.17](https://live.nowscore.com/1x2/2956512.htm)4.89 胜 走 走
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2026-03-15[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)[2-1](https://live.nowscore.com/detail/2956498cn.html)(0-1)9-4[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)0.82[受平/半](https://live.nowscore.com/odds/match/2956498.htm)1.06
3.07[3.62](https://live.nowscore.com/1x2/2956498.htm)2.14 负 输 走
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2026-02-21[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)[2-2](https://live.nowscore.com/detail/2785262cn.html)(1-0)4-4[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)0.94[受半球](https://live.nowscore.com/odds/match/2785262.htm)0.94
3.77[3.78](https://live.nowscore.com/1x2/2785262.htm)1.85 平 输 大
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2025-08-24[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)[1-1](https://live.nowscore.com/detail/2785169cn.html)(0-1)7-1[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)1.04[球半](https://live.nowscore.com/odds/match/2785169.htm)0.85
1.37[4.96](https://live.nowscore.com/1x2/2785169.htm)7.15 平 输 小
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2024-03-17[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)[0-2](https://live.nowscore.com/detail/2400129cn.html)(0-1)11-7[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)1.05[受半/一](https://live.nowscore.com/odds/match/2400129.htm)0.85
5.02[3.90](https://live.nowscore.com/1x2/2400129.htm)1.62 胜 赢 小
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2023-08-12[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)[2-1](https://live.nowscore.com/detail/2400016cn.html)(0-0)9-3[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)0.90[一/球半](https://live.nowscore.com/odds/match/2400016.htm)0.99
1.39[4.86](https://live.nowscore.com/1x2/2400016.htm)6.64 胜 输 小
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2023-03-06[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)[7-0](https://live.nowscore.com/detail/2209407cn.html)(2-0)10-0[欧登塞
2](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)0.90[一/球半](https://live.nowscore.com/odds/match/2209407.htm)0.99
1.39[4.66](https://live.nowscore.com/1x2/2209407.htm)7.26 胜 赢 大
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2022-09-11[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)[2-1](https://live.nowscore.com/detail/2209336cn.html)(1-1)4-4[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)0.96[受半/一](https://live.nowscore.com/odds/match/2209336.htm)0.93
4.74[3.83](https://live.nowscore.com/1x2/2209336.htm)1.67 负 输 大
[丹麦超](https://info.nowscore.com/cupmatch_vs/cupmatch_7.htm)2022-02-21[哥本哈根](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=227)[2-0](https://live.nowscore.com/detail/2024721cn.html)(1-0)5-9[欧登塞](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=229)0.97[一球](https://live.nowscore.com/odds/match/2024721.htm)0.92
1.53[4.18](https://live.nowscore.com/1x2/2024721.htm)5.72 胜 赢 小 近 10
场, 胜出 6 场,平局 2 场,输 2 场, 胜率：60% 让胜率：40% 大率：40%
单率：60%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.8215 |      0.9877 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 16 | 8 | 2.1875 | 0.9375 | 2.625 | 0.625 | 2.4062 | 0.7812 | 12.8000 |
| away | 19 | 8 | 1.2632 | 1.4737 | 1.125 | 1.000 | 1.1941 | 1.2368 | 14.1395 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      2.2186 |      0.9408 |     3.1594 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    1.3950 |     0.6516 |
| 平局    |    4.5325 |     0.2005 |
| 客胜    |    6.1750 |     0.1479 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:386  | 2026-10-26 12:13:07 |    -1.25 |         1.95 |         1.85 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:386  | 2026-10-26 10:19:10 |    3 |          1.9 |           1.9 |

**冻结前同公司盘口记录**：

euro 115 2026-10-25 01:43:00 1.44/4.5/5.5 → 2026-10-26 17:22:00
1.4/4.6/6 同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-25 03:41:00 1.42/4.5/6.5 → 2026-10-26 20:11:00
1.45/4.5/6.5 同公司48h记录首末；不能等同完整初盘\
euro 432 2026-10-26 14:16:00 1.31/4.65/6.4 → 2026-10-26 20:07:00
1.29/4.7/6.7 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-25 03:34:00 1.44/4.2/5.5 → 2026-10-26 16:05:00
1.44/4.33/5.5 同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-25 03:29:26 -1.25/2/1.8 → 2026-10-26 20:13:07
-1.25/1.95/1.85 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-25 03:26:57 3/1.85/1.95 → 2026-10-26 18:19:10 3/1.9/1.9
同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      1 |      0.2244 |     0.2244 | TRUE  |
|      0 |      0.2073 |     0.4317 | TRUE  |
|      2 |      0.1990 |     0.6307 | TRUE  |
|      3 |      0.1271 |     0.7577 | TRUE  |
|     -1 |      0.0901 |     0.8478 | TRUE  |
|      4 |      0.0642 |     0.9120 | TRUE  |
|     -2 |      0.0358 |     0.9478 | FALSE |
|      5 |      0.0267 |     0.9745 | FALSE |
|     -3 |      0.0097 |     0.9842 | FALSE |
|      6 |      0.0094 |     0.9936 | FALSE |
|      7 |      0.0029 |     0.9965 | FALSE |
|     -4 |      0.0021 |     0.9986 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.4303 |           0.4279 | 0.4287 |         0.43 |
| D       |      0.2244 |           0.2461 | 0.2392 |         0.27 |
| L       |      0.3453 |           0.3260 | 0.3322 |         0.30 |

核心保留 91.2 %；主正/负侧剔除 4 / 4.8 %。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#387 塞普西 — CS克拉约瓦大学

**基本面与定性落点**：
第12对第3，客队近6轮5胜1平14进1失；但其客场仅2胜2平1负5进7失，主队主场2胜2平1负5进4失。客队总体优势不能直接等同客场大胜。交锋主要2024年，参考降权。

**平局/让平审查**：
让平是客胜1球，净胜-1档24.3%最高，适度上调；普通平局由主队场地防守支持，不机械混用。

**差距解释**：
让胜37%对让负33%仅4点：基本面场地反证削弱盘口客队大胜方向。
让负与让平3点；三路盘口支持客队，反证未消失，不定可靠双选。

**调整幅度**：
从让负转约5.3点至让平；数值为专家假设，原生λ差仅-0.18对市场-1.11是重点分歧。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[罗甲-12\]圣格奥尔基塞普西**](https://info.nowscore.com/team/23525.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 12 3 5 4 8 13-5 14 12 25.0%
主 5 2 2 1 5 4 1 8 13 40.0% 客 7 1 3 3 3 9-6 6 7 14.3% 近6 6 2 1 3 5
10-5 7
33.3%[**\[罗甲-3\]克拉约瓦大学**](https://info.nowscore.com/team/14945.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 12 8 2 2 27 9 18 26 3 66.7%
主 7 6 0 1 22 2 20 18 1 85.7% 客 5 2 2 1 5 7-2 8 5 40.0% 近6 6 5 1 0 14
1 13 16 83.3% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 12 1 8 3 3 9-6
11 15 8.3% 主 5 1 2 2 1 3-2 5 15 20.0% 客 7 0 6 1 2 6-4 6 11 0.0% 近6 6
0 3 3 1 8-7 3 0.0%半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 12 5 5 2 7
3 4 20 5 41.7% 主 7 4 2 1 6 1 5 14 4 57.1% 客 5 1 3 1 1 2-1 6 9 20.0%
近6 6 3 3 0 4 0 4 12 50.0%

### 对战往绩

近场 主客相同 罗甲 罗杯 类型 日期 主场 比分(半场)角球 客场 主 让球 客 主
和 客 胜负 让球 进球数
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2024-12-14[克拉约瓦大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)[2-1](https://live.nowscore.com/detail/2606317cn.html)(1-1)5-3[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)0.90[半/一](https://live.nowscore.com/odds/match/2606317.htm)0.98
1.75[3.55](https://live.nowscore.com/1x2/2606317.htm)4.24 负 输 大
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2024-08-11[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)[1-2](https://live.nowscore.com/detail/2606196cn.html)(0-1)9-1[克拉约瓦大学
1](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)0.94[平手](https://live.nowscore.com/odds/match/2606196.htm)0.94
2.55[3.25](https://live.nowscore.com/1x2/2606196.htm)2.57 负 输 大
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2024-05-19[克拉约瓦大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)[3-2](https://live.nowscore.com/detail/2554000cn.html)(0-1)9-8[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)0.80[一球](https://live.nowscore.com/odds/match/2554000.htm)1.08
1.49[4.43](https://live.nowscore.com/1x2/2554000.htm)5.21 负 走 大
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2024-04-21[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)[1-3](https://live.nowscore.com/detail/2553985cn.html)(1-2)1-9[克拉约瓦大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)0.81[平手](https://live.nowscore.com/odds/match/2553985.htm)1.07
2.49[3.11](https://live.nowscore.com/1x2/2553985.htm)2.71 负 输 大
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2024-02-04[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)[1-3](https://live.nowscore.com/detail/2408831cn.html)(1-1)5-6[克拉约瓦大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)0.94[平/半](https://live.nowscore.com/odds/match/2408831.htm)0.94
2.22[3.06](https://live.nowscore.com/1x2/2408831.htm)3.21 负 输 大
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2023-09-17[1
克拉约瓦大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)[2-1](https://live.nowscore.com/detail/2408712cn.html)(2-1)6-6[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)0.80[平/半](https://live.nowscore.com/odds/match/2408712.htm)1.08
1.91[3.40](https://live.nowscore.com/1x2/2408712.htm)3.77 负 输 大
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2023-05-29[克拉约瓦大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)[0-1](https://live.nowscore.com/detail/2367781cn.html)(0-0)3-5[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)0.85[一/球半](https://live.nowscore.com/odds/match/2367781.htm)1.03
1.41[4.33](https://live.nowscore.com/1x2/2367781.htm)6.95 胜 赢 小
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2023-04-22[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)[1-2](https://live.nowscore.com/detail/2367766cn.html)(0-0)5-5[克拉约瓦大学
1](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)1.02[平手](https://live.nowscore.com/odds/match/2367766.htm)0.86
2.75[3.15](https://live.nowscore.com/1x2/2367766.htm)2.47 负 输 大
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2022-10-30[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)[0-1](https://live.nowscore.com/detail/2231933cn.html)(0-0)2-6[克拉约瓦大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)1.06[平/半](https://live.nowscore.com/odds/match/2231933.htm)0.81
2.33[3.04](https://live.nowscore.com/1x2/2231933.htm)3.03 负 输 小
[罗甲](https://info.nowscore.com/cupmatch_vs/cupmatch_124.htm)2022-07-16[1
克拉约瓦大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=14945)[2-2](https://live.nowscore.com/detail/2231813cn.html)(1-0)3-3[圣格奥尔基塞普西](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=23525)0.87[平/半](https://live.nowscore.com/odds/match/2231813.htm)1.01
2.08[3.15](https://live.nowscore.com/1x2/2231813.htm)3.48 平 赢 大 近 10
场, 胜出 1 场,平局 1 场,输 8 场, 胜率：10% 让胜率：20% 大率：80%
单率：70%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      0.9866 |      1.1622 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 14 | 8 | 1.0714 | 1.3571 | 1.00 | 1.375 | 1.0357 | 1.3661 | 11.7895 |
| away | 18 | 8 | 1.1667 | 1.0000 | 0.75 | 0.875 | 0.9583 | 0.9375 | 13.7143 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      0.7951 |      1.9056 |     2.7008 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    5.6667 |     0.1601 |
| 平局    |    3.9333 |     0.2304 |
| 客胜    |    1.4867 |     0.6095 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:387  | 2026-10-26 12:11:13 |        1 |         1.95 |         1.85 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:387  | 2026-10-26 08:22:18 |  2.5 |         1.88 |          1.93 |

**冻结前同公司盘口记录**：

euro 115 2026-10-26 12:19:00 6/4/1.5 → 2026-10-26 12:19:00 6/4/1.5
仅冻结水平，无法判断走势\
euro 281 2026-10-25 15:45:00 5.25/4/1.48 → 2026-10-26 15:13:00
5.5/4/1.48 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-26 12:11:00 5.5/3.8/1.48 → 2026-10-26 12:11:00
5.5/3.8/1.48 仅冻结水平，无法判断走势\
asian 8 2026-10-25 15:00:36 1/1.93/1.88 → 2026-10-26 20:11:13
1/1.95/1.85 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-26 16:22:18 2.5/1.88/1.93 → 2026-10-26 16:22:18
2.5/1.88/1.93 仅冻结水平，无法判断走势

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|     -1 |      0.2426 |     0.2426 | TRUE  |
|      0 |      0.2349 |     0.4775 | TRUE  |
|     -2 |      0.1964 |     0.6740 | TRUE  |
|     -3 |      0.1116 |     0.7856 | TRUE  |
|      1 |      0.0953 |     0.8809 | TRUE  |
|     -4 |      0.0496 |     0.9305 | TRUE  |
|      2 |      0.0342 |     0.9647 | FALSE |
|     -5 |      0.0180 |     0.9827 | FALSE |
|      3 |      0.0081 |     0.9908 | FALSE |
|     -6 |      0.0055 |     0.9963 | FALSE |
|      4 |      0.0015 |     0.9978 | FALSE |
|     -7 |      0.0015 |     0.9993 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.3743 |           0.3549 |  0.361 |         0.37 |
| D       |      0.2426 |           0.2607 |  0.255 |         0.30 |
| L       |      0.3831 |           0.3844 |  0.384 |         0.33 |

核心保留 93.05 %；主正/负侧剔除 4.41 / 2.54
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#388 厄勒布鲁 — 法尔肯贝里

**基本面与定性落点**：
第15对第2，客队近6轮4胜1平1负，客场7胜2平4负28进21失；主队主场3胜5平5负11进16失。客胜方向成立，但客队防守并不稳，主队多平有实际场地支持。最新同季交锋1:1，不能独立重复加成。

**平局/让平审查**：
平局31%排第二；0档26.9%最高，两边1球相近，总λ2.91并非极低，不抬成强平局。

**差距解释**： 客胜领先平9点：排名近期客场一致支持，防守反证限制幅度。
平与主胜仅2点，第二第三不稳定。

**调整幅度**： 主要从主胜转移至平局约3.7点，客胜保持约40%；专家幅度。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[瑞典甲-15\]奥雷布洛**](https://info.nowscore.com/team/419.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 27 5 11 11 30 42-12 26 15 18.5%
主 13 3 5 5 11 16-5 14 14 23.1% 客 14 2 6 6 19 26-7 12 13 14.3% 近6 6 1
3 2 9 9 0 6
16.7%[**\[瑞典甲-2\]法尔肯堡**](https://info.nowscore.com/team/1527.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 27 15 6 6 52 37 15 51 2
55.6% 主 14 8 4 2 24 16 8 28 3 57.1% 客 13 7 2 4 28 21 7 23 2 53.8% 近6
6 4 1 1 11 7 4 13 66.7% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 27 8
14 5 16 14 2 38 6 29.6% 主 13 2 9 2 5 5 0 15 11 15.4% 客 14 6 5 3 11 9 2
23 2 42.9% 近6 6 3 3 0 4 1 3 12 50.0%半场 赛 胜 平 负 得 失 净 得分 排名
胜率 总 27 9 11 7 25 20 5 38 5 33.3% 主 14 6 6 2 13 5 8 24 4 42.9% 客 13
3 5 5 12 15-3 14 12 23.1% 近6 6 2 4 0 7 3 4 10 33.3%

### 对战往绩

近场 主客相同 瑞典甲 球会友谊 瑞典超 瑞典杯 类型 日期 主场
比分(半场)角球 客场 主 让球 客 主 和 客 胜负 让球 进球数
[瑞典甲](https://info.nowscore.com/cupmatch_vs/cupmatch_122.htm)2026-06-14[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)[1-1](https://live.nowscore.com/detail/2914599cn.html)(0-1)4-11[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)0.92[半球](https://live.nowscore.com/odds/match/2914599.htm)0.95
1.81[3.54](https://live.nowscore.com/1x2/2914599.htm)4.02 平 赢 小
[瑞典甲](https://info.nowscore.com/cupmatch_vs/cupmatch_122.htm)2025-10-05[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)[4-1](https://live.nowscore.com/detail/2703404cn.html)(3-1)10-3[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)1.05[平/半](https://live.nowscore.com/odds/match/2703404.htm)0.83
2.30[3.51](https://live.nowscore.com/1x2/2703404.htm)2.74 胜 赢 大
[瑞典甲](https://info.nowscore.com/cupmatch_vs/cupmatch_122.htm)2025-04-30[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)[2-1](https://live.nowscore.com/detail/2703233cn.html)(1-1)3-4[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)0.96[半球](https://live.nowscore.com/odds/match/2703233.htm)0.93
1.90[3.34](https://live.nowscore.com/1x2/2703233.htm)3.85 负 输 大
[球会友谊](https://info.nowscore.com/cupmatch_vs/cupmatch_41.htm)2021-03-12[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)[3-1](https://live.nowscore.com/detail/1989409cn.html)(0-1)[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)0.77[半/一](https://live.nowscore.com/odds/match/1989409.htm)0.93
1.70[3.69](https://live.nowscore.com/1x2/1989409.htm)3.77 胜 赢 大
[瑞典超](https://info.nowscore.com/cupmatch_vs/cupmatch_26.htm)2020-10-17[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)[2-1](https://live.nowscore.com/detail/1876520cn.html)(0-0)6-1[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)1.11[平/半](https://live.nowscore.com/odds/match/1876520.htm)0.80
2.42[3.50](https://live.nowscore.com/1x2/1876520.htm)2.67 负 输 大
[瑞典超](https://info.nowscore.com/cupmatch_vs/cupmatch_26.htm)2020-08-01[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)[1-2](https://live.nowscore.com/detail/1876428cn.html)(0-0)5-5[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)0.92[平/半](https://live.nowscore.com/odds/match/1876428.htm)0.97
2.17[3.43](https://live.nowscore.com/1x2/1876428.htm)3.13 负 输 大
[瑞典超](https://info.nowscore.com/cupmatch_vs/cupmatch_26.htm)2019-07-20[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)[4-0](https://live.nowscore.com/detail/1650540cn.html)(3-0)6-1[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)1.12[平/半](https://live.nowscore.com/odds/match/1650540.htm)0.79
2.25[3.41](https://live.nowscore.com/1x2/1650540.htm)2.98 胜 赢 大
[瑞典超](https://info.nowscore.com/cupmatch_vs/cupmatch_26.htm)2019-03-31[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)[1-0](https://live.nowscore.com/detail/1649199cn.html)(0-0)2-4[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)0.96[平手](https://live.nowscore.com/odds/match/1649199.htm)0.94
2.87[3.19](https://live.nowscore.com/1x2/1649199.htm)2.41 负 输 小
[瑞典超](https://info.nowscore.com/cupmatch_vs/cupmatch_26.htm)2016-08-28[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)[3-2](https://live.nowscore.com/detail/1211489cn.html)(1-1)12-2[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)0.97[一/球半](https://live.nowscore.com/odds/match/1211489.htm)0.93
1.43[4.48](https://live.nowscore.com/1x2/1211489.htm)6.36 胜 输 大
[瑞典超](https://info.nowscore.com/cupmatch_vs/cupmatch_26.htm)2016-07-23[法尔肯堡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1527)[1-3](https://live.nowscore.com/detail/1211444cn.html)(0-2)6-5[奥雷布洛](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=419)1.00[受平/半](https://live.nowscore.com/odds/match/1211444.htm)0.90
3.45[3.62](https://live.nowscore.com/1x2/1211444.htm)1.96 胜 赢 大 近 10
场, 胜出 5 场,平局 1 场,输 4 场, 胜率：50% 让胜率：50% 大率：80%
单率：60%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.2083 |      1.5208 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 24 | 8 | 1.0833 | 1.1667 | 0.75 | 1.125 | 0.9167 | 1.1458 | 16 |
| away | 24 | 8 | 1.7917 | 1.6250 | 2.00 | 1.375 | 1.8958 | 1.5000 | 16 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      1.3618 |      1.5463 |     2.9082 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    2.6933 |     0.3313 |
| 平局    |    3.3167 |     0.2691 |
| 客胜    |    2.2333 |     0.3995 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:388  | 2026-10-26 09:56:49 |     0.25 |          1.8 |            2 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:388  | 2026-10-26 10:07:43 | 2.75 |          1.9 |           1.9 |

**冻结前同公司盘口记录**：

euro 115 2026-10-26 08:01:00 2.5/3.25/2.4 → 2026-10-26 18:05:00
2.63/3.4/2.2 同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-26 02:53:00 2.5/3.25/2.5 → 2026-10-26 20:02:00
2.75/3.25/2.25 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-26 02:49:00 2.45/3.3/2.45 → 2026-10-26 18:06:00
2.7/3.3/2.25 同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-26 02:48:58 0/1.9/1.9 → 2026-10-26 17:56:49 0.25/1.8/2
同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-26 08:20:27 2.75/1.98/1.83 → 2026-10-26 18:07:43
2.75/1.9/1.9 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      0 |      0.2692 |     0.2692 | TRUE  |
|     -1 |      0.1990 |     0.4682 | TRUE  |
|      1 |      0.1739 |     0.6421 | TRUE  |
|     -2 |      0.1250 |     0.7671 | TRUE  |
|      2 |      0.0969 |     0.8640 | TRUE  |
|     -3 |      0.0555 |     0.9195 | TRUE  |
|      3 |      0.0379 |     0.9575 | FALSE |
|     -4 |      0.0195 |     0.9770 | FALSE |
|      4 |      0.0118 |     0.9888 | FALSE |
|     -5 |      0.0057 |     0.9944 | FALSE |
|      5 |      0.0030 |     0.9974 | FALSE |
|     -6 |      0.0014 |     0.9988 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.3243 |           0.2945 | 0.3040 |         0.29 |
| D       |      0.2692 |           0.2927 | 0.2852 |         0.31 |
| L       |      0.4065 |           0.4127 | 0.4108 |         0.40 |

核心保留 91.95 %；主正/负侧剔除 5.35 / 2.7
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#389 圣塔克 — 本菲卡

**基本面与定性落点**：
第4对第2，仅差1分；主队8轮不败、主场7进2失，近6轮9进2失；客队客场15进3失、近6轮5胜1负。客胜有支持，但两球以上优势与主队防守明显冲突。

**平局/让平审查**：
让平为客胜1球，-1档22.6%与-2档21.6%接近；适度增保护，普通平局也应保留。

**差距解释**：
让负领先让胜仅5点，市场客让1.5与主队强防守分歧大，不保留原约21点优势。
让胜与让平7点；主队不败防守是支持，客队客场火力是反证。

**调整幅度**：
将让负约49.2%收窄至39%，主要移向让胜并兼顾让平；本批调整较大，必须提示幅度敏感，不能伪称市场错误。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[葡超-4\]圣克拉拉**](https://info.nowscore.com/team/1002.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 8 5 3 0 12 4 8 18 4 62.5% 主 4 2
2 0 7 2 5 8 6 50.0% 客 4 3 1 0 5 2 3 10 3 75.0% 近6 6 4 2 0 9 2 7 14
66.7%[**\[葡超-2\]本菲卡**](https://info.nowscore.com/team/463.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 8 6 1 1 24 7 17 19 2 75.0% 主 4 3
1 0 9 4 5 10 2 75.0% 客 4 3 0 1 15 3 12 9 4 75.0% 近6 6 5 0 1 15 5 10 15
83.3% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 8 4 4 0 7 2 5 16 4
50.0% 主 4 2 2 0 4 2 2 8 5 50.0% 客 4 2 2 0 3 0 3 8 5 50.0% 近6 6 3 3 0
4 0 4 12 50.0%半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 8 6 1 1 8 2 6
19 1 75.0% 主 4 3 1 0 4 1 3 10 2 75.0% 客 4 3 0 1 4 1 3 9 4 75.0% 近6 6
4 1 1 5 2 3 13 66.7%

### 杯赛积分

### 对战往绩

近 场 - \[x\] 主客相同 - \[x\] 葡超 - \[x\] 葡联杯 - \[x\] 球会友谊 类型
日期 主场 比分(半场)角球 客场 主 让球 客 主 和 客 胜负 让球 进球数
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2026-02-14[1
圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)[1-2](https://live.nowscore.com/detail/2814917cn.html)(0-2)1-7[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)0.75[受一球](https://live.nowscore.com/odds/match/2814917.htm)1.14
6.73[3.90](https://live.nowscore.com/1x2/2814917.htm)1.52 负 走 大
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2025-09-13[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)[1-1](https://live.nowscore.com/detail/2814761cn.html)(0-0)4-5[圣克拉拉
1](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)1.01[球半](https://live.nowscore.com/odds/match/2814761.htm)0.88
1.29[5.05](https://live.nowscore.com/1x2/2814761.htm)10.92 平 赢 小
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2025-02-16[1
圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)[0-1](https://live.nowscore.com/detail/2611850cn.html)(0-0)2-5[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)0.92[受半球](https://live.nowscore.com/odds/match/2611850.htm)0.97
4.40[3.33](https://live.nowscore.com/1x2/2611850.htm)1.87 负 输 小
[葡联杯](https://info.nowscore.com/cupmatch_vs/cupmatch_505.htm)2024-10-31[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)[3-0](https://live.nowscore.com/detail/2610338cn.html)(0-0)7-1[圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)1.11[两球](https://live.nowscore.com/odds/match/2610338.htm)0.79
1.19[6.24](https://live.nowscore.com/1x2/2610338.htm)13.27 负 输 走
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2024-09-15[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)[4-1](https://live.nowscore.com/detail/2611699cn.html)(2-1)5-1[圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)0.87[球半](https://live.nowscore.com/odds/match/2611699.htm)1.02
1.27[5.55](https://live.nowscore.com/1x2/2611699.htm)10.09 负 输 大
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2023-05-28[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)[3-0](https://live.nowscore.com/detail/2237227cn.html)(2-0)4-4[圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)1.05[三球](https://live.nowscore.com/odds/match/2237227.htm)0.85
1.06[12.04](https://live.nowscore.com/1x2/2237227.htm)29.61 负 走 小
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2023-01-22[圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)[0-3](https://live.nowscore.com/detail/2237067cn.html)(0-2)8-9[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)0.91[受球半/两](https://live.nowscore.com/odds/match/2237067.htm)0.98
11.01[5.60](https://live.nowscore.com/1x2/2237067.htm)1.26 负 输 走
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2022-02-13[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)[2-1](https://live.nowscore.com/detail/2046689cn.html)(0-1)7-2[圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)0.98[球半](https://live.nowscore.com/odds/match/2046689.htm)0.91
1.29[5.38](https://live.nowscore.com/1x2/2046689.htm)9.56 负 赢 走
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2021-09-12[圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)[0-5](https://live.nowscore.com/detail/2046539cn.html)(0-1)7-2[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)0.88[受一球](https://live.nowscore.com/odds/match/2046539.htm)1.02
5.68[4.00](https://live.nowscore.com/1x2/2046539.htm)1.57 负 输 大
[葡超](https://info.nowscore.com/cupmatch_vs/cupmatch_23.htm)2021-04-27[本菲卡](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=463)[2-1](https://live.nowscore.com/detail/1918152cn.html)(1-0)5-4[圣克拉拉](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1002)1.08[球半](https://live.nowscore.com/odds/match/1918152.htm)0.82
1.32[5.03](https://live.nowscore.com/1x2/1918152.htm)9.18 负 赢 大 近 10
场, 胜出 0 场,平局 1 场,输 9 场, 胜率：0% 让胜率：30% 大率：40%
单率：90%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.1166 |      1.7188 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 21 | 8 | 1.1429 | 0.9048 | 1.500 | 0.625 | 1.3214 | 0.7649 | 14.9333 |
| away | 17 | 8 | 2.4706 | 0.8235 | 2.875 | 1.000 | 2.6728 | 0.9118 | 13.2683 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      0.7362 |      2.2999 |      3.036 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    9.0000 |     0.1022 |
| 平局    |    5.0125 |     0.1829 |
| 客胜    |    1.2825 |     0.7149 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:389  | 2026-10-26 12:10:46 |      1.5 |          1.9 |         1.95 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:389  | 2026-10-26 12:08:38 | 2.75 |          1.8 |          2.05 |

**冻结前同公司盘口记录**：

euro 115 2026-10-25 13:22:00 7.5/4.5/1.36 → 2026-10-26 20:08:00
8.5/4.8/1.3 同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-25 13:32:00 8.5/4.33/1.37 → 2026-10-26 20:11:00
9.5/5/1.3 同公司48h记录首末；不能等同完整初盘\
euro 432 2026-10-25 19:50:00 8.5/4.75/1.24 → 2026-10-26 19:49:00
9.5/5/1.2 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-24 23:11:00 8.5/5/1.35 → 2026-10-26 20:12:00
8.5/5.25/1.33 同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-24 20:26:58 1.25/1.98/1.88 → 2026-10-26 20:10:46
1.5/1.9/1.95 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-25 07:01:49 2.5/1.85/1.95 → 2026-10-26 20:08:38
2.75/1.8/2.05 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|     -1 |      0.2263 |     0.2263 | TRUE  |
|     -2 |      0.2157 |     0.4420 | TRUE  |
|      0 |      0.1872 |     0.6292 | TRUE  |
|     -3 |      0.1463 |     0.7754 | TRUE  |
|     -4 |      0.0778 |     0.8533 | TRUE  |
|      1 |      0.0669 |     0.9202 | TRUE  |
|     -5 |      0.0340 |     0.9541 | FALSE |
|      2 |      0.0221 |     0.9762 | FALSE |
|     -6 |      0.0125 |     0.9888 | FALSE |
|      3 |      0.0048 |     0.9936 | FALSE |
|     -7 |      0.0040 |     0.9976 | FALSE |
|     -8 |      0.0011 |     0.9987 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.2820 |           0.2762 | 0.2780 |         0.34 |
| D       |      0.2263 |           0.2459 | 0.2397 |         0.27 |
| L       |      0.4918 |           0.4780 | 0.4823 |         0.39 |

核心保留 92.02 %；主正/负侧剔除 2.78 / 5.2
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#390 FC安道尔 — 布尔戈斯

**基本面与定性落点**：
第19对第9；客队近6轮4胜2负优于主队2胜1平3负，但客场1胜1平2负仅3进4失，主队主场2胜3负8进8失。总体状态偏客、主客场抵消，市场主让0.25不应形成过宽主胜差距。近期交锋各自主胜。

**平局/让平审查**：
平局33%第二：0档28.7%最高、大小2.25支持低比分，但本季双方少平为反证，不升第一。

**差距解释**： 主胜对平5点，市场主场优势与客队近期优势相冲。
平与客胜4点，两种保护均有依据。

**调整幅度**：
收窄主胜约7.5点，向平和客胜分配；专家假设，不与前场照搬三元组。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[西乙-19\]安道尔FC**](https://info.nowscore.com/team/17830.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 10 3 1 6 13 17-4 10 19 30.0% 主 5
2 0 3 8 8 0 6 19 40.0% 客 5 1 1 3 5 9-4 4 17 20.0% 近6 6 2 1 3 6 10-4 7
33.3%[**\[西乙-9\]布尔戈斯**](https://info.nowscore.com/team/976.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 10 5 2 3 13 10 3 17 9 50.0%
主 6 4 1 1 10 6 4 13 3 66.7% 客 4 1 1 2 3 4-1 4 16 25.0% 近6 6 4 0 2 8 5
3 12 66.7% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 10 3 3 4 4 7-3 12
14 30.0% 主 5 2 1 2 2 4-2 7 18 40.0% 客 5 1 2 2 2 3-1 5 11 20.0% 近6 6 2
1 3 3 6-3 7 33.3%半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 10 2 5 3 6
7-1 11 17 20.0% 主 6 1 4 1 5 5 0 7 16 16.7% 客 4 1 1 2 1 2-1 4 16 25.0%
近6 6 2 2 2 3 3 0 8 33.3%

### 对战往绩

近场 主客相同 西乙 西杯 类型 日期 主场 比分(半场)角球 客场 主 让球 客 主
和 客 胜负 让球 进球数
[西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_33.htm)2026-06-01[布尔戈斯](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=976)[1-0](https://live.nowscore.com/detail/2808073cn.html)(1-0)2-2[安道尔FC](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=17830)1.06[一球](https://live.nowscore.com/odds/match/2808073.htm)0.81
1.54[3.88](https://live.nowscore.com/1x2/2808073.htm)6.01 负 走 小
[西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_33.htm)2025-08-31[安道尔FC](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=17830)[2-1](https://live.nowscore.com/detail/2807643cn.html)(1-0)5-4[布尔戈斯](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=976)1.01[平/半](https://live.nowscore.com/odds/match/2807643.htm)0.88
2.28[3.06](https://live.nowscore.com/1x2/2807643.htm)3.22 胜 赢 大
[西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_33.htm)2024-05-18[安道尔FC](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=17830)[1-0](https://live.nowscore.com/detail/2409312cn.html)(0-0)7-1[布尔戈斯](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=976)1.03[平/半](https://live.nowscore.com/odds/match/2409312.htm)0.85
2.29[3.16](https://live.nowscore.com/1x2/2409312.htm)3.06 胜 赢 小
[西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_33.htm)2023-11-25[布尔戈斯](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=976)[0-0](https://live.nowscore.com/detail/2409059cn.html)(0-0)3-3[安道尔FC](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=17830)0.99[平/半](https://live.nowscore.com/odds/match/2409059.htm)0.90
2.18[3.11](https://live.nowscore.com/1x2/2409059.htm)3.33 平 赢 小
[西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_33.htm)2023-01-15[布尔戈斯](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=976)[2-1](https://live.nowscore.com/detail/2226610cn.html)(0-1)3-11[安道尔FC](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=17830)1.21[平手](https://live.nowscore.com/odds/match/2226610.htm)0.72
2.95[2.73](https://live.nowscore.com/1x2/2226610.htm)2.68 负 输 大
[西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_33.htm)2022-10-12[安道尔FC](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=17830)[0-1](https://live.nowscore.com/detail/2226467cn.html)(0-0)12-4[布尔戈斯](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=976)1.08[半球](https://live.nowscore.com/odds/match/2226467.htm)0.82
2.11[2.88](https://live.nowscore.com/1x2/2226467.htm)3.95 负 输 小
[西杯](https://info.nowscore.com/cupmatch_vs/cupmatch_81.htm)2020-12-16[布尔戈斯](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=976)[2-0](https://live.nowscore.com/detail/1958136cn.html)(0-0)8-3[安道尔FC](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=17830)0.83[半/一](https://live.nowscore.com/odds/match/1958136.htm)0.99
1.64[3.56](https://live.nowscore.com/1x2/1958136.htm)5.15 负 输 小 近 7
场, 胜出 2 场,平局 1 场,输 4 场, 胜率：28.6% 让胜率：42.9% 大率：28.6%
单率：71.4%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.2692 |      1.1611 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 26 | 8 | 1.5 | 1.2692 | 1.625 | 1.500 | 1.5625 | 1.3846 | 16.64 |
| away | 26 | 8 | 1.0 | 1.0769 | 0.875 | 0.875 | 0.9375 | 0.9760 | 16.64 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      1.4681 |      1.0525 |     2.5205 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |     2.000 |     0.4516 |
| 平局    |     3.175 |     0.2846 |
| 客胜    |     3.425 |     0.2638 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:390  | 2026-10-26 10:12:36 |    -0.25 |         1.78 |         2.03 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:390  | 2026-10-26 10:13:36 | 2.25 |         1.78 |          2.03 |

**冻结前同公司盘口记录**：

euro 115 2026-10-24 20:20:00 1.95/3.3/3.5 → 2026-10-26 18:05:00
2/3.1/3.5 同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-24 22:32:00 2.05/3.5/3.3 → 2026-10-26 19:32:00
2.05/3.4/3.4 同公司48h记录首末；不能等同完整初盘\
euro 432 2026-10-25 00:58:00 1.86/3.15/3.6 → 2026-10-26 14:17:00
1.9/3.1/3.5 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-24 20:31:00 2/3.1/3.3 → 2026-10-26 12:25:00 2.05/3.1/3.3
同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-24 20:21:22 -0.5/2.03/1.78 → 2026-10-26 18:12:36
-0.25/1.78/2.03 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-25 13:18:44 2.25/1.8/2 → 2026-10-26 18:13:36
2.25/1.78/2.03 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      0 |      0.2866 |     0.2866 | TRUE  |
|      1 |      0.2236 |     0.5102 | TRUE  |
|     -1 |      0.1568 |     0.6670 | TRUE  |
|      2 |      0.1409 |     0.8078 | TRUE  |
|     -2 |      0.0724 |     0.8802 | TRUE  |
|      3 |      0.0615 |     0.9418 | TRUE  |
|     -3 |      0.0227 |     0.9644 | FALSE |
|      4 |      0.0210 |     0.9855 | FALSE |
|      5 |      0.0059 |     0.9914 | FALSE |
|     -4 |      0.0056 |     0.9969 | FALSE |
|      6 |      0.0014 |     0.9983 | FALSE |
|     -5 |      0.0011 |     0.9994 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.4547 |           0.4523 | 0.4531 |         0.38 |
| D       |      0.2866 |           0.3043 | 0.2988 |         0.33 |
| L       |      0.2587 |           0.2433 | 0.2482 |         0.29 |

核心保留 94.18 %；主正/负侧剔除 2.87 / 2.96
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#392 蒙彼利埃 — 圣旺红星

**基本面与定性落点**：
法乙第3对第6，仅差1分。蒙彼利埃主场2胜2平0负、4进1失；红星客场4胜1平0负、10进5失。双方对应场地均不败，主队防守好但进攻低，客队客场进攻更强。原生λ1.22/1.35微偏客，联合市场1.52/1.29偏主，差异要充分反映。

**平局/让平审查**：
平局35%略排第一：主队场地低失球、两队场地不败和两次同赛事交锋1:1支持；交锋样本仅2次、大小球2.75和总λ2.81是反证，不能强推平局。

**差距解释**：
平35%与主胜34%仅1点，市场主场支持和基本面客场优势冲突；无可靠唯一主选。
主胜34%与客胜31%仅3点，客队客场4胜1平要求保留反向，三选属性。

**调整幅度**：
从市场主胜约41.4%向平局转移约7.6点；方向有依据，幅度是待用户核查的专家假设。比分网格未重加权。

北单03:40、分析页及盘口03:45，原生ID/赛事/主客一致，相差5分钟按用户约定接受；准入按更早03:40及独立停售检查。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[法乙-3\]蒙彼利埃**](https://info.nowscore.com/team/351.htm) 全场 赛
胜 平 负 得 失 净 得分 排名 胜率 总 9 5 3 1 11 5 6 18 3 55.6% 主 4 2 2 0
4 1 3 8 6 50.0% 客 5 3 1 1 7 4 3 10 4 60.0% 近6 6 3 2 1 8 4 4 11
50.0%[**\[法乙-6\]红星**](https://info.nowscore.com/team/12220.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 9 5 2 2 12 10 2 17 6 55.6% 主 4 1
1 2 2 5-3 4 15 25.0% 客 5 4 1 0 10 5 5 13 1 80.0% 近6 6 4 0 2 10 9 1 12
66.7% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 9 1 8 0 3 2 1 11 10
11.1% 主 4 1 3 0 1 0 1 6 6 25.0% 客 5 0 5 0 2 2 0 5 11 0.0% 近6 6 1 5 0
3 2 1 8 16.7%半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 9 3 4 2 7 4 3
13 7 33.3% 主 4 0 2 2 1 3-2 2 17 0.0% 客 5 3 2 0 6 1 5 11 2 60.0% 近6 6
2 2 2 6 4 2 8 33.3%

### 对战往绩

近场 主客相同 法乙 类型 日期 主场 比分(半场)角球 客场 主 让球 客 主 和
客 胜负 让球 进球数
[法乙](https://info.nowscore.com/cupmatch_vs/cupmatch_12.htm)2026-05-10[红星](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=12220)[1-1](https://live.nowscore.com/detail/2847560cn.html)(1-0)3-3[蒙彼利埃](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=351)0.77[半球](https://live.nowscore.com/odds/match/2847560.htm)1.12
1.78[3.66](https://live.nowscore.com/1x2/2847560.htm)4.18 平 赢 小
[法乙](https://info.nowscore.com/cupmatch_vs/cupmatch_12.htm)2025-08-10[蒙彼利埃](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=351)[1-1](https://live.nowscore.com/detail/2801604cn.html)(1-1)1-2[红星](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=12220)0.82[半球](https://live.nowscore.com/odds/match/2801604.htm)1.06
1.80[3.48](https://live.nowscore.com/1x2/2801604.htm)4.23 平 输 小 近 2
场, 胜出 0 场,平局 2 场,输 0 场, 胜率：0% 让胜率：50% 大率：0% 单率：0%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.2213 |      1.3466 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 21 | 8 | 1.4762 | 1.0000 | 1.375 | 0.750 | 1.4256 | 0.875 | 14.9333 |
| away | 22 | 8 | 1.6364 | 0.9091 | 2.000 | 1.125 | 1.8182 | 1.017 | 15.3043 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      1.5173 |      1.2899 |     2.8072 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    2.1825 |     0.4125 |
| 平局    |    3.2375 |     0.2774 |
| 客胜    |    2.9000 |     0.3101 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:392  | 2026-10-26 12:13:33 |    -0.25 |         1.98 |         1.83 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:392  | 2026-10-26 12:17:02 | 2.75 |            2 |           1.8 |

**冻结前同公司盘口记录**：

euro 115 2026-10-25 17:38:00 2.38/3.2/2.8 → 2026-10-26 18:55:00
2.3/3.25/2.9 同公司48h首末记录，非完整初盘\
euro 281 2026-10-26 12:52:00 2.2/3.2/3 → 2026-10-26 18:19:00 2.2/3.2/2.9
同公司48h首末记录，非完整初盘\
euro 432 2026-10-26 20:00:00 1.98/3.3/3.05 → 2026-10-26 20:00:00
1.98/3.3/3.05 单快照不能判断走势\
euro 82 2026-10-26 00:01:00 2.3/3.25/2.7 → 2026-10-26 16:20:00
2.25/3.2/2.75 同公司48h首末记录，非完整初盘\
asian 8 2026-10-25 00:01:48 0/1.78/2.03 → 2026-10-26 20:13:33
-0.25/1.98/1.83 同公司48h首末记录，非完整初盘\
totals 8 2026-10-26 00:00:52 2.5/1.88/1.93 → 2026-10-26 20:17:02
2.75/2/1.8 同公司48h首末记录，非完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      0 |      0.2742 |     0.2742 | TRUE  |
|      1 |      0.2039 |     0.4782 | TRUE  |
|     -1 |      0.1716 |     0.6498 | TRUE  |
|      2 |      0.1275 |     0.7773 | TRUE  |
|     -2 |      0.0922 |     0.8694 | TRUE  |
|      3 |      0.0561 |     0.9255 | TRUE  |
|     -3 |      0.0345 |     0.9600 | FALSE |
|      4 |      0.0195 |     0.9795 | FALSE |
|     -4 |      0.0102 |     0.9897 | FALSE |
|      5 |      0.0056 |     0.9952 | FALSE |
|     -5 |      0.0025 |     0.9977 | FALSE |
|      6 |      0.0013 |     0.9990 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.4143 |           0.4187 | 0.4173 |         0.34 |
| D       |      0.2742 |           0.2963 | 0.2893 |         0.35 |
| L       |      0.3115 |           0.2850 | 0.2934 |         0.31 |

核心保留 92.55 %；主正/负侧剔除 2.67 / 4.77
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#394 沃尔索尔 — 索尔福德城

**基本面与定性落点**：
第6对榜首；主队11轮不败4胜7平，但主场仅2/5平，不能照搬7/11；其主场8进2失有防守支持。客队近6轮全胜12进3失，客场12进9失，客胜仍优先。

**平局/让平审查**：
普通平局32%第二，0档27.1%最高；总λ2.83不属极低，用主队场地防守而非平局频率机械加成。

**差距解释**： 客胜领先平8点，近期强势支持，主队不败限制。
平领先主胜4点，场地防守支持，榜首强攻是反证。

**调整幅度**： 主要将客胜约3.7点及少量主胜转平，专家候选。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[英乙-6\]沃尔索尔**](https://info.nowscore.com/team/339.htm) 全场 赛
胜 平 负 得 失 净 得分 排名 胜率 总 11 4 7 0 16 7 9 19 6 36.4% 主 5 3 2
0 8 2 6 11 10 60.0% 客 6 1 5 0 8 5 3 8 4 16.7% 近6 6 2 4 0 8 3 5 10
33.3%[**\[英乙-1\]索尔福德市**](https://info.nowscore.com/team/11444.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 12 8 1 3 19 12 7 25 1 66.7%
主 6 5 0 1 7 3 4 15 4 83.3% 客 6 3 1 2 12 9 3 10 2 50.0% 近6 6 6 0 0 12
3 9 18 100.0% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 11 4 6 1 6 2 4
18 5 36.4% 主 5 3 2 0 5 1 4 11 6 60.0% 客 6 1 4 1 1 1 0 7 8 16.7% 近6 6
2 3 1 3 1 2 9 33.3%半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 12 3 7 2
7 6 1 16 10 25.0% 主 6 1 4 1 1 1 0 7 21 16.7% 客 6 2 3 1 6 5 1 9 2 33.3%
近6 6 3 3 0 5 1 4 12 50.0%

### 对战往绩

近场 主客相同 英乙 类型 日期 主场 比分(半场)角球 客场 主 让球 客 主 和
客 胜负 让球 进球数
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2026-03-11[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)[1-0](https://live.nowscore.com/detail/2798939cn.html)(0-0)11-2[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)1.06[半球](https://live.nowscore.com/odds/match/2798939.htm)0.82
1.95[3.33](https://live.nowscore.com/1x2/2798939.htm)3.76 负 输 小
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2025-08-23[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)[1-0](https://live.nowscore.com/detail/2798617cn.html)(1-0)5-2[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)0.98[平/半](https://live.nowscore.com/odds/match/2798617.htm)0.90
2.21[3.28](https://live.nowscore.com/1x2/2798617.htm)3.10 胜 赢 小
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2025-02-01[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)[2-2](https://live.nowscore.com/detail/2599627cn.html)(0-1)15-1[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)1.05[半/一](https://live.nowscore.com/odds/match/2599627.htm)0.83
1.74[3.54](https://live.nowscore.com/1x2/2599627.htm)4.49 平 输 大
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2024-09-21[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)[0-2](https://live.nowscore.com/detail/2599350cn.html)(0-0)6-5[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)0.80[受平/半](https://live.nowscore.com/odds/match/2599350.htm)1.08
2.83[3.28](https://live.nowscore.com/1x2/2599350.htm)2.36 胜 赢 小
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2024-04-01[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)[2-1](https://live.nowscore.com/detail/2404233cn.html)(1-0)4-5[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)0.90[平/半](https://live.nowscore.com/odds/match/2404233.htm)0.98
2.06[3.52](https://live.nowscore.com/1x2/2404233.htm)3.23 胜 赢 大
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2023-09-09[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)[1-2](https://live.nowscore.com/detail/2403811cn.html)(1-0)12-1[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)1.02[平/半](https://live.nowscore.com/odds/match/2403811.htm)0.86
2.20[3.37](https://live.nowscore.com/1x2/2403811.htm)3.04 胜 赢 大
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2023-04-22[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)[2-3](https://live.nowscore.com/detail/2224067cn.html)(0-1)2-4[索尔福德市
1](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)0.90[受半球](https://live.nowscore.com/odds/match/2224067.htm)0.98
3.71[3.45](https://live.nowscore.com/1x2/2224067.htm)1.93 负 输 大
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2023-02-01[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)[1-0](https://live.nowscore.com/detail/2223788cn.html)(1-0)2-4[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)1.09[平/半](https://live.nowscore.com/odds/match/2223788.htm)0.79
2.46[3.01](https://live.nowscore.com/1x2/2223788.htm)2.94 负 输 小
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2022-03-26[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)[2-1](https://live.nowscore.com/detail/2037385cn.html)(1-1)5-7[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)1.03[半球](https://live.nowscore.com/odds/match/2037385.htm)0.85
2.10[3.13](https://live.nowscore.com/1x2/2037385.htm)3.53 负 输 大
[英乙](https://info.nowscore.com/cupmatch_vs/cupmatch_35.htm)2021-10-09[沃尔索尔](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=339)[2-1](https://live.nowscore.com/detail/2037051cn.html)(1-0)2-4[索尔福德市](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=11444)0.86[受平/半](https://live.nowscore.com/odds/match/2037051.htm)1.02
3.26[3.15](https://live.nowscore.com/1x2/2037051.htm)2.24 胜 赢 大 近 10
场, 胜出 5 场,平局 1 场,输 4 场, 胜率：50% 让胜率：50% 大率：60%
单率：80%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|       1.195 |      1.3943 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 23 | 8 | 1.00 | 1.2174 | 1.25 | 1.25 | 1.125 | 1.2337 | 15.6596 |
| away | 25 | 8 | 1.36 | 1.2800 | 1.75 | 1.25 | 1.555 | 1.2650 | 16.3265 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      1.2553 |      1.5779 |     2.8332 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    3.1500 |     0.2963 |
| 平局    |    3.5000 |     0.2666 |
| 客胜    |    2.1333 |     0.4372 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:394  | 2026-10-26 10:11:18 |     0.25 |         1.95 |          1.9 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:394  | 2026-10-26 11:53:07 | 2.75 |            2 |          1.85 |

**冻结前同公司盘口记录**：

euro 115 2026-10-26 12:05:00 3.1/3.5/2.1 → 2026-10-26 17:48:00
3/3.5/2.15 同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-26 12:04:00 3.25/3.4/2.15 → 2026-10-26 19:41:00
3.25/3.4/2.15 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-26 12:06:00 3.2/3.6/2.1 → 2026-10-26 12:06:00
3.2/3.6/2.1 仅冻结水平，无法判断走势\
asian 8 2026-10-26 10:55:04 0.25/2/1.85 → 2026-10-26 18:11:18
0.25/1.95/1.9 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-26 04:05:39 2.75/1.93/1.93 → 2026-10-26 19:53:07
2.75/2/1.85 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      0 |      0.2707 |     0.2707 | TRUE  |
|     -1 |      0.2090 |     0.4797 | TRUE  |
|      1 |      0.1639 |     0.6436 | TRUE  |
|     -2 |      0.1353 |     0.7789 | TRUE  |
|      2 |      0.0856 |     0.8645 | TRUE  |
|     -3 |      0.0618 |     0.9263 | TRUE  |
|      3 |      0.0311 |     0.9574 | FALSE |
|     -4 |      0.0223 |     0.9797 | FALSE |
|      4 |      0.0089 |     0.9886 | FALSE |
|     -5 |      0.0066 |     0.9953 | FALSE |
|      5 |      0.0021 |     0.9974 | FALSE |
|     -6 |      0.0017 |     0.9990 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.2922 |           0.2693 | 0.2766 |         0.28 |
| D       |      0.2707 |           0.2923 | 0.2855 |         0.32 |
| L       |      0.4371 |           0.4384 | 0.4380 |         0.40 |

核心保留 92.63 %；主正/负侧剔除 4.27 / 3.1
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#396 智利大学 — 比尼亚德尔马埃弗顿

**基本面与定性落点**：
第2对第4；主队主场8胜3平1负27进9失，客队客场6胜2平3负21进11失，两队近6轮均4胜。支持主队占优而非明显大胜。同季杯赛1:1和主队客胜1:0、联赛0:0，赛事不同需降权。

**平局/让平审查**：
让平为主胜1球，22.3%接近0档23.3%且高于赢2球17.7%；加强一球保护，不能把杯赛平局直接加到让平。

**差距解释**： 让负对让平8点，客队相应客场战力抵消主队大胜预期。
让平比让胜4点，一球中心支持，但主队近期18球保留大胜反证。

**调整幅度**：
从让胜约35%收窄至28%，部分让负转至让平32%，幅度为专家假设。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[智利甲-2\]智利大学**](https://info.nowscore.com/team/1429.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 24 13 6 5 41 19 22 45 2 54.2% 主
12 8 3 1 27 9 18 27 1 66.7% 客 12 5 3 4 14 10 4 18 4 41.7% 近6 6 4 0 2
18 7 11 12
66.7%[**\[智利甲-4\]维尼亚德马埃弗顿**](https://info.nowscore.com/team/1061.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 24 11 6 7 40 27 13 39 4
45.8% 主 13 5 4 4 19 16 3 19 9 38.5% 客 11 6 2 3 21 11 10 20 3 54.5% 近6
6 4 1 1 13 6 7 13 66.7% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 24 7
15 2 14 8 6 36 7 29.2% 主 12 5 6 1 9 3 6 21 4 41.7% 客 12 2 9 1 5 5 0 15
7 16.7% 近6 6 1 4 1 4 4 0 7 16.7%半场 赛 胜 平 负 得 失 净 得分 排名
胜率 总 24 8 12 4 20 13 7 36 6 33.3% 主 13 2 8 3 8 9-1 14 13 15.4% 客 11
6 4 1 12 4 8 22 1 54.5% 近6 6 3 1 2 7 4 3 10 50.0%

### 对战往绩

近场 主客相同 智利杯 智利甲 类型 日期 主场 比分(半场)角球 客场 主 让球
客 主 和 客 胜负 让球 进球数
[智利杯](https://info.nowscore.com/cupmatch_vs/cupmatch_714.htm)2026-09-28[智利大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)[1-1](https://live.nowscore.com/detail/3086933cn.html)(1-0)7-3[维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)0.88[平/半](https://live.nowscore.com/odds/match/3086933.htm)1.00
1.96[3.66](https://live.nowscore.com/1x2/3086933.htm)3.30 平 输 小
[智利杯](https://info.nowscore.com/cupmatch_vs/cupmatch_714.htm)2026-09-25[维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)[0-1](https://live.nowscore.com/detail/3086927cn.html)(0-0)5-6[智利大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)0.86[受平/半](https://live.nowscore.com/odds/match/3086927.htm)1.00
2.96[3.47](https://live.nowscore.com/1x2/3086927.htm)2.15 胜 赢 小
[智利甲](https://info.nowscore.com/cupmatch_vs/cupmatch_415.htm)2026-04-19[维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)[0-0](https://live.nowscore.com/detail/2921142cn.html)(0-0)4-8[智利大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)0.94[受平/半](https://live.nowscore.com/odds/match/2921142.htm)0.94
3.34[3.10](https://live.nowscore.com/1x2/2921142.htm)2.16 平 输 小
[智利甲](https://info.nowscore.com/cupmatch_vs/cupmatch_415.htm)2025-11-06[智利大学(中)](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)[2-0](https://live.nowscore.com/detail/2722857cn.html)(0-0)7-0[维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)0.97[一/球半](https://live.nowscore.com/odds/match/2722857.htm)0.91
1.43[4.34](https://live.nowscore.com/1x2/2722857.htm)6.47 胜 赢 小
[智利甲](https://info.nowscore.com/cupmatch_vs/cupmatch_415.htm)2025-03-28[1
维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)[2-0](https://live.nowscore.com/detail/2722732cn.html)(1-0)3-5[智利大学
1](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)1.04[受半球](https://live.nowscore.com/odds/match/2722732.htm)0.85
3.85[3.59](https://live.nowscore.com/1x2/2722732.htm)1.83 负 输 小
[智利甲](https://info.nowscore.com/cupmatch_vs/cupmatch_415.htm)2024-11-11[智利大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)[1-1](https://live.nowscore.com/detail/2521052cn.html)(1-0)9-9[维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)0.74[一球](https://live.nowscore.com/odds/match/2521052.htm)1.17
1.49[4.14](https://live.nowscore.com/1x2/2521052.htm)5.80 平 输 小
[智利杯](https://info.nowscore.com/cupmatch_vs/cupmatch_714.htm)2024-07-15[智利大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)[1-0](https://live.nowscore.com/detail/2606509cn.html)(0-0)2-4[维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)0.69[半/一](https://live.nowscore.com/odds/match/2606509.htm)1.14
1.53[4.23](https://live.nowscore.com/1x2/2606509.htm)4.92 胜 赢 小
[智利杯](https://info.nowscore.com/cupmatch_vs/cupmatch_714.htm)2024-07-08[1
维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)[2-1](https://live.nowscore.com/detail/2606501cn.html)(2-0)3-5[智利大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)0.79[受平/半](https://live.nowscore.com/odds/match/2606501.htm)0.91
2.88[3.48](https://live.nowscore.com/1x2/2606501.htm)2.18 负 输 大
[智利甲](https://info.nowscore.com/cupmatch_vs/cupmatch_415.htm)2024-06-03[维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)[1-2](https://live.nowscore.com/detail/2520931cn.html)(1-1)4-3[智利大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)0.90[受平/半](https://live.nowscore.com/odds/match/2520931.htm)0.98
2.90[3.48](https://live.nowscore.com/1x2/2520931.htm)2.20 胜 赢 走
[智利甲](https://info.nowscore.com/cupmatch_vs/cupmatch_415.htm)2023-11-07[2
智利大学](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1429)[1-2](https://live.nowscore.com/detail/2324528cn.html)(1-1)8-3[维尼亚德马埃弗顿](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1061)0.86[平/半](https://live.nowscore.com/odds/match/2324528.htm)1.04
2.11[3.28](https://live.nowscore.com/1x2/2324528.htm)3.25 负 输 大 近 10
场, 胜出 4 场,平局 3 场,输 3 场, 胜率：40% 让胜率：40% 大率：20%
单率：50%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.6656 |      1.3594 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 16 | 8 | 2.0625 | 0.9375 | 2.50 | 0.75 | 2.2812 | 0.8438 | 12.8000 |
| away | 20 | 8 | 1.5000 | 1.1000 | 2.25 | 1.00 | 1.8750 | 1.0500 | 14.5455 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      2.0074 |      1.1053 |     3.1127 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    1.6267 |     0.5573 |
| 平局    |    3.8000 |     0.2386 |
| 客胜    |    4.4500 |     0.2041 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:396  | 2026-10-26 08:56:26 |    -0.75 |          1.8 |            2 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:396  | 2026-10-26 11:41:27 |    3 |         1.95 |          1.85 |

**冻结前同公司盘口记录**：

euro 115 2026-10-26 14:03:00 1.62/3.8/4.4 → 2026-10-26 14:03:00
1.62/3.8/4.4 仅冻结水平，无法判断走势\
euro 281 2026-10-26 05:30:00 1.65/3.8/4.75 → 2026-10-26 05:30:00
1.65/3.8/4.75 仅冻结水平，无法判断走势\
euro 82 2026-10-26 08:11:00 1.61/3.8/4.2 → 2026-10-26 16:24:00
1.61/3.8/4.2 同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-25 00:16:16 -0.75/1.83/1.98 → 2026-10-26 16:56:26
-0.75/1.8/2 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-25 14:55:41 2.75/1.83/1.98 → 2026-10-26 19:41:27
3/1.95/1.85 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      0 |      0.2332 |     0.2332 | TRUE  |
|      1 |      0.2227 |     0.4559 | TRUE  |
|      2 |      0.1773 |     0.6332 | TRUE  |
|     -1 |      0.1182 |     0.7514 | TRUE  |
|      3 |      0.1016 |     0.8530 | TRUE  |
|     -2 |      0.0537 |     0.9067 | TRUE  |
|      4 |      0.0462 |     0.9529 | FALSE |
|      5 |      0.0173 |     0.9702 | FALSE |
|     -3 |      0.0170 |     0.9872 | FALSE |
|      6 |      0.0055 |     0.9927 | FALSE |
|     -4 |      0.0042 |     0.9969 | FALSE |
|      7 |      0.0015 |     0.9985 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.3499 |           0.3076 | 0.3211 |         0.28 |
| D       |      0.2227 |           0.2456 | 0.2383 |         0.32 |
| L       |      0.4274 |           0.4468 | 0.4406 |         0.40 |

核心保留 90.67 %；主正/负侧剔除 7.1 / 2.23
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#397 圣菲联合 — 拉普拉塔大学生

**基本面与定性落点**：
第21对第20同为14分；主队主场3胜3负11进10失，客队客场0胜1平5负3进10失，支持主队场地优势；主队近6轮1胜1平4负抵消。两队本季均仅2/13平，不足以凭低总量强推平局第一。

**平局/让平审查**：
维持原完整分布平局约30.6%，0档本来已充分支持；不另做GLOBAL平局抬升。

**差距解释**：
原市场主胜与客胜不足1点，场地证据支持主而近况支持客，三向接近。
第二第三仅约3.7点，保留三选，不包装成稳定主客双选。

**调整幅度**： 不改概率；低总量已入大小球和DC，避免重复校正。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[阿甲-21\]圣塔菲联**](https://info.nowscore.com/team/5096.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 13 4 2 7 18 22-4 14 21 30.8% 主 6
3 0 3 11 10 1 9 19 50.0% 客 7 1 2 4 7 12-5 5 22 14.3% 近6 6 1 1 4 6 12-6
4
16.7%[**\[阿甲-20\]拉普拉塔大学生**](https://info.nowscore.com/team/269.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 13 4 2 7 16 15 1 14 20 30.8%
主 7 4 1 2 13 5 8 13 10 57.1% 客 6 0 1 5 3 10-7 1 30 0.0% 近6 6 2 1 3 9
8 1 7 33.3% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 13 2 5 6 3 8-5
11 27 15.4% 主 6 2 3 1 3 3 0 9 17 33.3% 客 7 0 2 5 0 5-5 2 29 0.0% 近6 6
0 3 3 1 5-4 3 0.0%半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 13 2 6 5 8
9-1 12 25 15.4% 主 7 2 5 0 6 2 4 11 12 28.6% 客 6 0 1 5 2 7-5 1 30 0.0%
近6 6 0 4 2 4 6-2 4 0.0%

### 对战往绩

近场 主客相同 阿甲 阿根廷杯 类型 日期 主场 比分(半场)角球 客场 主 让球
客 主 和 客 胜负 让球 进球数
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2026-04-12[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)[2-1](https://live.nowscore.com/detail/2910254cn.html)(0-1)4-6[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)0.77[平手](https://live.nowscore.com/odds/match/2910254.htm)1.12
2.49[2.76](https://live.nowscore.com/1x2/2910254.htm)3.31 负 输 大
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2025-07-15[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)[1-0](https://live.nowscore.com/detail/2776075cn.html)(1-0)4-1[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)0.76[平手](https://live.nowscore.com/odds/match/2776075.htm)1.14
2.61[2.85](https://live.nowscore.com/1x2/2776075.htm)2.90 胜 赢 小
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2025-01-26[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)[3-1](https://live.nowscore.com/detail/2704789cn.html)(3-0)5-3[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)1.06[半/一](https://live.nowscore.com/odds/match/2704789.htm)0.83
1.75[3.25](https://live.nowscore.com/1x2/2704789.htm)5.09 负 输 大
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2024-07-22[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)[0-0](https://live.nowscore.com/detail/2513489cn.html)(0-0)5-3[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)1.06[半球](https://live.nowscore.com/odds/match/2513489.htm)0.84
2.03[2.92](https://live.nowscore.com/1x2/2513489.htm)4.17 平 赢 小
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2024-02-02[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)[0-1](https://live.nowscore.com/detail/2513243cn.html)(0-0)10-2[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)0.83[平手](https://live.nowscore.com/odds/match/2513243.htm)1.07
2.63[2.84](https://live.nowscore.com/1x2/2513243.htm)2.87 负 输 小
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2023-08-27[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)[1-3](https://live.nowscore.com/detail/2458669cn.html)(1-0)0-6[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)0.96[平/半](https://live.nowscore.com/odds/match/2458669.htm)0.93
2.19[3.00](https://live.nowscore.com/1x2/2458669.htm)3.61 胜 赢 大
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2023-03-04[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)[2-0](https://live.nowscore.com/detail/2321792cn.html)(0-0)4-5[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)1.12[平/半](https://live.nowscore.com/odds/match/2321792.htm)0.79
2.44[2.98](https://live.nowscore.com/1x2/2321792.htm)3.05 胜 赢 走
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2022-08-23[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)[1-0](https://live.nowscore.com/detail/2220095cn.html)(0-0)2-1[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)1.05[半球](https://live.nowscore.com/odds/match/2220095.htm)0.85
2.04[3.29](https://live.nowscore.com/1x2/2220095.htm)3.55 负 输 小
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2021-09-16[圣塔菲联](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)[0-2](https://live.nowscore.com/detail/2080945cn.html)(0-2)2-1[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)0.99[受平/半](https://live.nowscore.com/odds/match/2080945.htm)0.90
3.27[3.00](https://live.nowscore.com/1x2/2080945.htm)2.30 负 输 小
[阿甲](https://info.nowscore.com/cupmatch_vs/cupmatch_2.htm)2020-02-02[拉普拉塔大学生](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=269)[3-1](https://live.nowscore.com/detail/1753217cn.html)(1-0)2-1[圣塔菲联
1](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=5096)0.82[半球](https://live.nowscore.com/odds/match/1753217.htm)1.08
1.84[3.11](https://live.nowscore.com/1x2/1753217.htm)4.66 负 输 大 近 10
场, 胜出 3 场,平局 1 场,输 6 场, 胜率：30% 让胜率：40% 大率：40%
单率：40%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.2893 |      1.0655 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 23 | 8 | 1.3478 | 1.0000 | 1.75 | 1.75 | 1.5489 | 1.3750 | 15.6596 |
| away | 21 | 8 | 0.7619 | 0.8095 | 0.75 | 1.25 | 0.7560 | 1.0298 | 14.9333 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      1.1886 |      1.1707 |     2.3593 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    2.6250 |     0.3523 |
| 平局    |    3.0550 |     0.3028 |
| 客胜    |    2.6825 |     0.3448 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:397  | 2026-10-26 11:02:14 |        0 |         1.88 |         1.93 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:397  | 2026-10-26 04:28:43 | 2.25 |         1.95 |          1.85 |

**冻结前同公司盘口记录**：

euro 115 2026-10-25 10:55:00 2.38/3/2.9 → 2026-10-26 19:02:00 2.6/3/2.7
同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-25 08:37:00 2.45/3.1/3.1 → 2026-10-26 19:02:00
2.75/3.1/2.8 同公司48h记录首末；不能等同完整初盘\
euro 432 2026-10-26 12:05:00 2.32/2.93/2.78 → 2026-10-26 12:51:00
2.53/2.92/2.53 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-26 12:49:00 2.5/3.2/2.8 → 2026-10-26 13:05:00
2.62/3.2/2.7 同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-25 08:40:54 -0.25/2.05/1.75 → 2026-10-26 19:02:14
0/1.88/1.93 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-26 12:09:19 2.25/1.93/1.88 → 2026-10-26 12:28:43
2.25/1.95/1.85 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      0 |      0.3057 |     0.3057 | TRUE  |
|      1 |      0.1977 |     0.5034 | TRUE  |
|     -1 |      0.1945 |     0.6979 | TRUE  |
|      2 |      0.1036 |     0.8015 | TRUE  |
|     -2 |      0.1005 |     0.9020 | TRUE  |
|      3 |      0.0370 |     0.9390 | FALSE |
|     -3 |      0.0354 |     0.9744 | FALSE |
|      4 |      0.0103 |     0.9847 | FALSE |
|     -4 |      0.0097 |     0.9945 | FALSE |
|      5 |      0.0023 |     0.9968 | FALSE |
|     -5 |      0.0022 |     0.9990 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.3515 |           0.3340 | 0.3396 |       0.3515 |
| D       |      0.3057 |           0.3389 | 0.3282 |       0.3057 |
| L       |      0.3428 |           0.3271 | 0.3321 |       0.3428 |

核心保留 90.2 %；主正/负侧剔除 5.02 / 4.78
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#398 科里蒂巴 — 格雷米奥

**基本面与定性落点**：
第12对第18；主队主场5胜5平5负20进20失、近6轮0胜2平4负5进16失；客队客场0胜5平10负9进23失、近6轮也不胜。客队客场很弱支持主，但主队崩盘状态限制优势。

**平局/让平审查**：
平局32%第二，0档29%最高；双方不胜不等于打法保守，防守差是平局反证，故仅温和提升。

**差距解释**： 主胜领先平8点，主客场差支持，近期状态显著制约。
平领先客胜4点，客队客场零胜支持，但主队失球多保留反向。

**调整幅度**： 从主胜转约3点至平局，客胜近维持；专家假设。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[巴西甲-12\]科里蒂巴**](https://info.nowscore.com/team/350.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 31 10 9 12 38 49-11 39 12 32.3%
主 15 5 5 5 20 20 0 20 17 33.3% 客 16 5 4 7 18 29-11 19 7 31.3% 近6 6 0
2 4 5 16-11 2
0.0%[**\[巴西甲-18\]格雷米奥**](https://info.nowscore.com/team/364.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 31 7 10 14 34 44-10 31 18
22.6% 主 16 7 5 4 25 21 4 26 12 43.8% 客 15 0 5 10 9 23-14 5 20 0.0% 近6
6 0 3 3 7 11-4 3 0.0% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 31 8
12 11 15 18-3 36 16 25.8% 主 15 5 6 4 7 7 0 21 16 33.3% 客 16 3 6 7 8
11-3 15 10 18.8% 近6 6 0 3 3 2 6-4 3 0.0%半场 赛 胜 平 负 得 失 净 得分
排名 胜率 总 31 7 16 8 15 17-2 37 15 22.6% 主 16 6 7 3 11 8 3 25 10
37.5% 客 15 1 9 5 4 9-5 12 16 6.7% 近6 6 3 2 1 5 3 2 11 50.0%

### 对战往绩

近场 主客相同 巴西甲 巴超联杯 巴西杯 南美杯 球会友谊 类型 日期 主场
比分(半场)角球 客场 主 让球 客 主 和 客 胜负 让球 进球数
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2026-04-27[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)[1-0](https://live.nowscore.com/detail/2910754cn.html)(1-0)5-2[科里蒂巴
2](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)0.95[半球](https://live.nowscore.com/odds/match/2910754.htm)0.93
1.91[3.30](https://live.nowscore.com/1x2/2910754.htm)4.15 负 输 小
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2023-11-02[1
科里蒂巴](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)[1-2](https://live.nowscore.com/detail/2352463cn.html)(0-1)6-11[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)0.95[受平/半](https://live.nowscore.com/odds/match/2352463.htm)0.94
2.95[3.52](https://live.nowscore.com/1x2/2352463.htm)2.21 负 输 大
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2023-06-26[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)[5-1](https://live.nowscore.com/detail/2352275cn.html)(1-1)8-5[科里蒂巴
1](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)0.94[一球](https://live.nowscore.com/odds/match/2352275.htm)0.95
1.47[4.31](https://live.nowscore.com/1x2/2352275.htm)6.49 负 输 大
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2021-02-01[科里蒂巴](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)[1-1](https://live.nowscore.com/detail/1858897cn.html)(0-1)2-3[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)0.89[受半球](https://live.nowscore.com/odds/match/1858897.htm)1.01
3.94[3.17](https://live.nowscore.com/1x2/1858897.htm)1.97 平 赢 小
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2020-10-08[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)[2-1](https://live.nowscore.com/detail/1858712cn.html)(2-0)6-6[科里蒂巴](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)0.96[一球](https://live.nowscore.com/odds/match/1858712.htm)0.93
1.44[4.02](https://live.nowscore.com/1x2/1858712.htm)7.61 负 走 大
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2017-10-16[科里蒂巴](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)[0-1](https://live.nowscore.com/detail/1365377cn.html)(0-0)2-11[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)0.87[受平/半](https://live.nowscore.com/odds/match/1365377.htm)1.03
3.05[2.97](https://live.nowscore.com/1x2/1365377.htm)2.39 负 输 小
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2017-06-23[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)[2-0](https://live.nowscore.com/detail/1365192cn.html)(1-0)6-3[科里蒂巴](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)0.98[一球](https://live.nowscore.com/odds/match/1365192.htm)0.92
1.54[3.80](https://live.nowscore.com/1x2/1365192.htm)5.98 负 输 小
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2016-09-08[科里蒂巴](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)[4-0](https://live.nowscore.com/detail/1232593cn.html)(4-0)5-2[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)1.19[平/半](https://live.nowscore.com/odds/match/1232593.htm)0.74
2.37[3.05](https://live.nowscore.com/1x2/1232593.htm)3.03 胜 赢 大
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2016-05-30[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)[2-0](https://live.nowscore.com/detail/1232402cn.html)(1-0)4-2[科里蒂巴](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)0.80[半/一](https://live.nowscore.com/odds/match/1232402.htm)1.11
1.56[3.68](https://live.nowscore.com/1x2/1232402.htm)5.91 负 输 小
[巴超联杯](https://info.nowscore.com/cupmatch_vs/cupmatch_1441.htm)2016-02-08[格雷米奥](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=364)[1-0](https://live.nowscore.com/detail/1210847cn.html)(1-0)4-5[科里蒂巴](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=350)1.05[一球](https://live.nowscore.com/odds/match/1210847.htm)0.83
1.62[3.52](https://live.nowscore.com/1x2/1210847.htm)5.15 负 走 小 近 10
场, 胜出 1 场,平局 1 场,输 8 场, 胜率：10% 让胜率：20% 大率：40%
单率：50%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.4969 |      1.1477 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 15 | 8 | 1.3333 | 1.3333 | 1.625 | 1.75 | 1.4792 | 1.5417 | 12.3077 |
| away | 17 | 8 | 0.8824 | 1.5294 | 0.625 | 1.50 | 0.7537 | 1.5147 | 13.2683 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      1.4173 |      1.1019 |     2.5192 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    2.1675 |     0.4250 |
| 平局    |    3.2500 |     0.2836 |
| 客胜    |    3.1650 |     0.2915 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:398  | 2026-10-26 11:18:09 |    -0.25 |          1.9 |         1.95 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:398  | 2026-10-26 11:53:14 | 2.25 |          1.8 |          2.05 |

**冻结前同公司盘口记录**：

euro 115 2026-10-25 00:08:00 2.1/3.2/3.3 → 2026-10-26 16:50:00
2.15/3.2/3.2 同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-25 00:01:00 2.05/3.4/3.8 → 2026-10-26 16:30:00
2.2/3.3/3.4 同公司48h记录首末；不能等同完整初盘\
euro 432 2026-10-25 05:59:00 1.95/3.2/3.25 → 2026-10-26 18:21:00
2.12/3.1/2.96 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-25 05:59:00 2.05/3.5/3.5 → 2026-10-26 08:34:00
2.2/3.4/3.1 同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-24 23:58:17 -0.5/2.05/1.8 → 2026-10-26 19:18:09
-0.25/1.9/1.95 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-24 20:20:46 2.5/1.9/1.9 → 2026-10-26 19:53:14
2.25/1.8/2.05 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      0 |      0.2899 |     0.2899 | TRUE  |
|      1 |      0.2171 |     0.5071 | TRUE  |
|     -1 |      0.1660 |     0.6731 | TRUE  |
|      2 |      0.1321 |     0.8052 | TRUE  |
|     -2 |      0.0799 |     0.8850 | TRUE  |
|      3 |      0.0557 |     0.9407 | TRUE  |
|     -3 |      0.0262 |     0.9669 | FALSE |
|      4 |      0.0184 |     0.9852 | FALSE |
|     -4 |      0.0067 |     0.9919 | FALSE |
|      5 |      0.0050 |     0.9969 | FALSE |
|     -5 |      0.0014 |     0.9983 | FALSE |
|      6 |      0.0011 |     0.9994 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.4296 |           0.4304 | 0.4302 |         0.40 |
| D       |      0.2899 |           0.3082 | 0.3025 |         0.32 |
| L       |      0.2804 |           0.2614 | 0.2673 |         0.28 |

核心保留 94.07 %；主正/负侧剔除 2.47 / 3.46
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#399 弗拉门戈 — 米内罗竞技

**基本面与定性落点**：
第2对第6；主队主场11胜3平1负29进10失、近6轮5胜1平；客队客场4胜3平8负15进18失，但近6轮4胜2平不败。支持主队赢球，客队近期回升限制大胜幅度；同季0:4不作重复强证据。

**平局/让平审查**：
让平为主胜1球，21.7%几乎等于赢2球21.9%，应是重要保护，不把普通平局17%混为让平。

**差距解释**：
让胜领先让平20点，主场攻防和-1.75亚盘支持；客队近况是反证。
让平比让负4点，+1/+2共同中心支持，外围仍保留24%。

**调整幅度**：
将让胜约53.1%收窄至48%，部分质量转让平28%；候选无条件三分类，比分网格未执行重加权。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[巴西甲-2\]弗拉门戈**](https://info.nowscore.com/team/356.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 31 20 7 4 61 25 36 67 2 64.5% 主
15 11 3 1 29 10 19 36 2 73.3% 客 16 9 4 3 32 15 17 31 1 56.3% 近6 6 5 1
0 11 4 7 16
83.3%[**\[巴西甲-6\]米内罗竞技**](https://info.nowscore.com/team/343.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 31 14 8 9 42 35 7 50 6 45.2%
主 16 10 5 1 27 17 10 35 4 62.5% 客 15 4 3 8 15 18-3 15 9 26.7% 近6 6 4
2 0 10 5 5 14 66.7% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 31 17 9
5 25 7 18 60 2 54.8% 主 15 9 4 2 10 2 8 31 2 60.0% 客 16 8 5 3 15 5 10
29 2 50.0% 近6 6 2 4 0 3 0 3 10 33.3%半场 赛 胜 平 负 得 失 净 得分 排名
胜率 总 31 11 14 6 19 13 6 47 5 35.5% 主 16 7 7 2 10 7 3 28 6 43.8% 客
15 4 7 4 9 6 3 19 7 26.7% 近6 6 1 4 1 2 2 0 7 16.7%

### 杯赛积分

### 对战往绩

近 场 - \[x\] 主客相同 - \[x\] 巴西甲 - \[x\] 巴西杯 - \[x\] 巴超杯 -
\[x\] 巴超联杯 类型 日期 主场 比分(半场)角球 客场 主 让球 客 主 和 客
胜负 让球 进球数
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2026-04-27[米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)[0-4](https://live.nowscore.com/detail/2910748cn.html)(0-3)8-1[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)0.87[受半/一](https://live.nowscore.com/odds/match/2910748.htm)1.01
4.17[3.41](https://live.nowscore.com/1x2/2910748.htm)1.89 胜 赢 大
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2025-11-26[1
米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)[1-1](https://live.nowscore.com/detail/2735055cn.html)(1-0)2-4[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)0.78[受半球](https://live.nowscore.com/odds/match/2735055.htm)1.11
3.91[3.16](https://live.nowscore.com/1x2/2735055.htm)2.02 平 输 走
[巴西杯](https://info.nowscore.com/cupmatch_vs/cupmatch_186.htm)2025-08-07[米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)[0-1](https://live.nowscore.com/detail/2782718cn.html)(0-1)3-5[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)0.84[受平/半](https://live.nowscore.com/odds/match/2782718.htm)1.04
3.47[2.97](https://live.nowscore.com/1x2/2782718.htm)2.18 胜 赢 小
[巴西杯](https://info.nowscore.com/cupmatch_vs/cupmatch_186.htm)2025-08-01[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)[0-1](https://live.nowscore.com/detail/2782726cn.html)(0-0)4-3[米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)0.89[半/一](https://live.nowscore.com/odds/match/2782726.htm)0.99
1.63[3.32](https://live.nowscore.com/1x2/2782726.htm)5.83 负 输 小
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2025-07-28[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)[1-0](https://live.nowscore.com/detail/2734868cn.html)(0-0)5-7[米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)1.09[一/球半](https://live.nowscore.com/odds/match/2734868.htm)0.79
1.41[4.15](https://live.nowscore.com/1x2/2734868.htm)8.14 胜 输 小
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2024-11-14[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)[0-0](https://live.nowscore.com/detail/2548265cn.html)(0-0)7-4[米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)1.04[半球](https://live.nowscore.com/odds/match/2548265.htm)0.84
1.93[3.30](https://live.nowscore.com/1x2/2548265.htm)3.98 平 输 小
[巴西杯](https://info.nowscore.com/cupmatch_vs/cupmatch_186.htm)2024-11-11[1
米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)[0-1](https://live.nowscore.com/detail/2684042cn.html)(0-0)11-5[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)0.91[平/半](https://live.nowscore.com/odds/match/2684042.htm)0.98
2.20[3.18](https://live.nowscore.com/1x2/2684042.htm)3.35 胜 赢 小
[巴西杯](https://info.nowscore.com/cupmatch_vs/cupmatch_186.htm)2024-11-04[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)[3-1](https://live.nowscore.com/detail/2684043cn.html)(2-0)2-6[米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)0.92[半/一](https://live.nowscore.com/odds/match/2684043.htm)0.96
1.69[3.37](https://live.nowscore.com/1x2/2684043.htm)5.26 胜 赢 大
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2024-07-04[1
米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)[2-4](https://live.nowscore.com/detail/2548073cn.html)(0-2)4-4[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)0.93[平手](https://live.nowscore.com/odds/match/2548073.htm)0.95
2.72[3.07](https://live.nowscore.com/1x2/2548073.htm)2.65 胜 赢 大
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2023-11-30[弗拉门戈](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=356)[0-3](https://live.nowscore.com/detail/2352514cn.html)(0-1)10-1[米内罗竞技](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=343)0.95[半/一](https://live.nowscore.com/odds/match/2352514.htm)0.94
1.77[3.44](https://live.nowscore.com/1x2/2352514.htm)4.65 负 输 大 近 10
场, 胜出 6 场,平局 2 场,输 2 场, 胜率：60% 让胜率：50% 大率：40%
单率：50%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.5646 |      0.8229 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 15 | 8 | 1.9333 | 0.6667 | 2.00 | 0.375 | 1.9667 | 0.5208 | 12.3077 |
| away | 15 | 8 | 1.0000 | 1.2000 | 1.25 | 1.125 | 1.1250 | 1.1625 | 12.3077 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      2.4482 |      0.7112 |     3.1594 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    1.2575 |     0.7318 |
| 平局    |    5.2000 |     0.1772 |
| 客胜    |   10.1250 |     0.0910 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:399  | 2026-10-26 12:01:13 |    -1.75 |            2 |         1.85 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:399  | 2026-10-26 10:51:55 |    3 |         1.93 |          1.93 |

**冻结前同公司盘口记录**：

euro 115 2026-10-26 13:06:00 1.29/5/9.5 → 2026-10-26 18:34:00 1.25/5/10
同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-26 12:36:00 1.3/5/11 → 2026-10-26 18:40:00 1.29/5/11
同公司48h记录首末；不能等同完整初盘\
euro 432 2026-10-26 14:23:00 1.21/5.2/8.75 → 2026-10-26 15:54:00
1.19/5.3/9.5 同公司48h记录首末；不能等同完整初盘\
euro 82 2026-10-26 04:52:00 1.33/5/8.5 → 2026-10-26 15:53:00 1.3/5.5/10
同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-26 12:06:32 -1.5/1.9/1.95 → 2026-10-26 20:01:13
-1.75/2/1.85 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-26 05:50:15 3/1.95/1.9 → 2026-10-26 18:51:55
3/1.93/1.93 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      2 |      0.2191 |     0.2191 | TRUE  |
|      1 |      0.2174 |     0.4366 | TRUE  |
|      0 |      0.1703 |     0.6068 | TRUE  |
|      3 |      0.1577 |     0.7645 | TRUE  |
|      4 |      0.0892 |     0.8537 | TRUE  |
|     -1 |      0.0579 |     0.9116 | TRUE  |
|      5 |      0.0414 |     0.9530 | FALSE |
|     -2 |      0.0185 |     0.9715 | FALSE |
|      6 |      0.0162 |     0.9877 | FALSE |
|      7 |      0.0055 |     0.9932 | FALSE |
|     -3 |      0.0039 |     0.9970 | FALSE |
|      8 |      0.0016 |     0.9987 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.5313 |           0.5112 | 0.5176 |         0.48 |
| D       |      0.2174 |           0.2385 | 0.2318 |         0.28 |
| L       |      0.2513 |           0.2503 | 0.2506 |         0.24 |

核心保留 91.16 %；主正/负侧剔除 6.53 / 2.31
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

## \#400 尤文图德 — 累西腓航海

**基本面与定性落点**：
第3对第15；主队主场10胜5平2负24进8失、近6轮3胜2平1负，客队客场3胜7平7负20进25失、近6轮1胜2平3负。主胜有依据，但总λ2.57和客队客场多平不支持轻率断言大胜。

**平局/让平审查**：
让平为主胜1球，24.9%最高，0档24.1%、+2档19.8%都较大；三向接近，和让胜并列主选。

**差距解释**： 让胜/让平并列34%，明确无唯一Top1。
与让负仅2点，不是可靠双选，三选属性。

**调整幅度**：
压低两侧聚合各约4点，向中心让平转约9点；主观幅度较大，半幅下排序可能变化，不能据此强制双选。

排名、近期和攻防来自重叠样本，市场也可能已吸收，不按证据条数重复加成。首发、伤停、轮换、打法与战意未独立核验；不猜测其影响。

<details>

<summary>

展开冻结积分与交战原文（旧交锋不等权）
</summary>

\### 联赛积分
[**\[巴西乙-3\]尤文图德**](https://info.nowscore.com/team/371.htm) 全场
赛 胜 平 负 得 失 净 得分 排名 胜率 总 34 17 10 7 41 23 18 61 3 50.0% 主
17 10 5 2 24 8 16 35 2 58.8% 客 17 7 5 5 17 15 2 26 4 41.2% 近6 6 3 2 1
11 6 5 11
50.0%[**\[巴西乙-15\]累西腓航海**](https://info.nowscore.com/team/1944.htm)
全场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 34 11 10 13 39 42-3 43 15
32.4% 主 17 8 3 6 19 17 2 27 13 47.1% 客 17 3 7 7 20 25-5 16 15 17.6%
近6 6 1 2 3 4 9-5 5 16.7% 半场 赛 胜 平 负 得 失 净 得分 排名 胜率 总 34
11 17 6 17 11 6 50 7 32.4% 主 17 9 7 1 14 3 11 34 2 52.9% 客 17 2 10 5 3
8-5 16 13 11.8% 近6 6 2 4 0 5 2 3 10 33.3%半场 赛 胜 平 负 得 失 净 得分
排名 胜率 总 34 7 12 15 12 24-12 33 16 20.6% 主 17 5 6 6 7 9-2 21 17
29.4% 客 17 2 6 9 5 15-10 12 17 11.8% 近6 6 1 2 3 2 6-4 5 16.7%

### 对战往绩

近场 主客相同 巴西乙 巴丙 巴西甲 类型 日期 主场 比分(半场)角球 客场 主
让球 客 主 和 客 胜负 让球 进球数
[巴西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_358.htm)2026-07-06[累西腓航海](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)[0-0](https://live.nowscore.com/detail/2940062cn.html)(0-0)6-2[尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)0.98[平/半](https://live.nowscore.com/odds/match/2940062.htm)0.89
2.35[2.93](https://live.nowscore.com/1x2/2940062.htm)3.23 平 赢 小
[巴西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_358.htm)2020-11-29[尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)[1-0](https://live.nowscore.com/detail/1859190cn.html)(0-0)2-8[累西腓航海](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)0.93[半球](https://live.nowscore.com/odds/match/1859190.htm)0.96
1.79[3.45](https://live.nowscore.com/1x2/1859190.htm)4.16 胜 赢 小
[巴西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_358.htm)2020-08-23[1
累西腓航海](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)[3-3](https://live.nowscore.com/detail/1859006cn.html)(2-2)6-8[尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)1.05[半球](https://live.nowscore.com/odds/match/1859006.htm)0.85
2.03[2.94](https://live.nowscore.com/1x2/1859006.htm)3.86 平 赢 大
[巴丙](https://info.nowscore.com/cupmatch_vs/cupmatch_1347.htm)2019-09-23[累西腓航海](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)[2-1](https://live.nowscore.com/detail/1796610cn.html)(2-0)8-7[尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)0.97[半球](https://live.nowscore.com/odds/match/1796610.htm)0.87
1.93[3.15](https://live.nowscore.com/1x2/1796610.htm)3.80 负 输 大
[巴丙](https://info.nowscore.com/cupmatch_vs/cupmatch_1347.htm)2019-09-16[尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)[2-1](https://live.nowscore.com/detail/1796608cn.html)(0-1)3-8[累西腓航海](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)0.80[平/半](https://live.nowscore.com/odds/match/1796608.htm)1.04
2.12[3.11](https://live.nowscore.com/1x2/1796608.htm)3.27 胜 赢 大
[巴西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_358.htm)2017-10-25[尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)[0-0](https://live.nowscore.com/detail/1374367cn.html)(0-0)10-1[累西腓航海](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)0.85[半球](https://live.nowscore.com/odds/match/1374367.htm)1.05
1.76[3.18](https://live.nowscore.com/1x2/1374367.htm)4.78 平 输 小
[巴西乙](https://info.nowscore.com/cupmatch_vs/cupmatch_358.htm)2017-07-12[累西腓航海](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)[1-1](https://live.nowscore.com/detail/1374178cn.html)(1-0)3-4[尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)1.04[平/半](https://live.nowscore.com/odds/match/1374178.htm)0.86
2.47[3.06](https://live.nowscore.com/1x2/1374178.htm)2.78 平 赢 小
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2007-10-07[累西腓航海](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)[4-1](https://live.nowscore.com/detail/117687cn.html)(2-0)[尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)0.94[一球](https://live.nowscore.com/odds/match/117687.htm)0.96
1.56[3.56](https://live.nowscore.com/1x2/117687.htm)5.30 负 输 大
[巴西甲](https://info.nowscore.com/cupmatch_vs/cupmatch_4.htm)2007-07-13[1
尤文图德](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=371)[1-1](https://live.nowscore.com/detail/117495cn.html)(0-0)[累西腓航海
1](https://info.nowscore.com/cn/team/Summary.aspx?TeamID=1944)0.47[平手](https://live.nowscore.com/odds/match/117495.htm)1.41
1.51[3.57](https://live.nowscore.com/1x2/117495.htm)5.66 平 走 小 近 9
场, 胜出 2 场,平局 5 场,输 2 场, 胜率：22.2% 让胜率：55.6% 大率：44.4%
单率：44.4%

</details>

**原生λ与实际取样**：同赛事同场地，长期/近期8场各0.5，不冒称本季60%；ρ=-0.1为未标定专家值。

| lambda_home | lambda_away |
|------------:|------------:|
|      1.4081 |      0.7868 |

| role | matches | recent_matches | long_for | long_against | recent_for | recent_against | goals_for | goals_against | ess |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| home | 17 | 8 | 1.4118 | 0.4706 | 1.500 | 0.875 | 1.4559 | 0.6728 | 13.2683 |
| away | 17 | 8 | 1.1765 | 1.4706 | 0.625 | 1.250 | 0.9007 | 1.3603 | 13.2683 |

**联合市场λ**：

| lambda_home | lambda_away | total_mean |  rho |
|------------:|------------:|-----------:|-----:|
|      1.8366 |      0.7321 |     2.5687 | -0.1 |

**欧赔均价与逐公司去水后均值**：

| outcome | mean_odds | devig_mean |
|:--------|----------:|-----------:|
| 主胜    |    1.4675 |     0.6196 |
| 平局    |    3.8750 |     0.2346 |
| 客胜    |    6.2750 |     0.1458 |

| company_id | fixture_id | quote_at            | handicap | home_decimal | away_decimal |
|:-----------|:-----------|:--------------------|---------:|-------------:|-------------:|
| 8          | 26107:400  | 2026-10-26 10:40:41 |       -1 |         1.88 |         1.93 |

| company_id | fixture_id | quote_at            | line | over_decimal | under_decimal |
|:-----------|:-----------|:--------------------|-----:|-------------:|--------------:|
| 8          | 26107:400  | 2026-10-26 10:40:41 |  2.5 |            2 |           1.8 |

**冻结前同公司盘口记录**：

euro 115 2026-10-26 08:10:00 1.44/4/6 → 2026-10-26 15:49:00 1.5/3.9/6
同公司48h记录首末；不能等同完整初盘\
euro 281 2026-10-26 17:46:00 1.53/3.8/7 → 2026-10-26 20:09:00 1.53/3.8/7
同公司48h记录首末；不能等同完整初盘\
euro 432 2026-10-26 19:12:00 1.36/4/6.6 → 2026-10-26 19:12:00 1.36/4/6.6
仅冻结水平，无法判断走势\
euro 82 2026-10-26 08:12:00 1.48/3.9/5.5 → 2026-10-26 15:49:00
1.48/3.8/5.5 同公司48h记录首末；不能等同完整初盘\
asian 8 2026-10-26 08:09:52 -1/1.85/1.95 → 2026-10-26 18:40:41
-1/1.88/1.93 同公司48h记录首末；不能等同完整初盘\
totals 8 2026-10-26 08:09:52 2.5/1.93/1.88 → 2026-10-26 18:40:41
2.5/2/1.8 同公司48h记录首末；不能等同完整初盘

**主队净胜球完整参考分布**：下列为原市场网格，未随MPR三分类改写。

| margin | probability | cumulative | core  |
|-------:|------------:|-----------:|:------|
|      1 |      0.2488 |     0.2488 | TRUE  |
|      0 |      0.2405 |     0.4894 | TRUE  |
|      2 |      0.1978 |     0.6872 | TRUE  |
|      3 |      0.1096 |     0.7968 | TRUE  |
|     -1 |      0.0930 |     0.8898 | TRUE  |
|      4 |      0.0473 |     0.9370 | TRUE  |
|     -2 |      0.0314 |     0.9685 | FALSE |
|      5 |      0.0166 |     0.9851 | FALSE |
|     -3 |      0.0069 |     0.9921 | FALSE |
|      6 |      0.0049 |     0.9970 | FALSE |
|      7 |      0.0013 |     0.9983 | FALSE |
|     -4 |      0.0012 |     0.9995 | FALSE |

**完整→核心条件参考→外围0.3参考→本稿实际概率**：

| outcome | market_full | core_conditional | soft90 | draft_ticket |
|:--------|------------:|-----------------:|-------:|-------------:|
| W       |      0.3779 |           0.3785 | 0.3783 |         0.34 |
| D       |      0.2488 |           0.2655 | 0.2603 |         0.34 |
| L       |      0.3733 |           0.3559 | 0.3614 |         0.32 |

核心保留 93.7 %；主正/负侧剔除 2.32 / 3.98
%。条件核心不能冒充无条件概率。

**审核定位**：
分析者MPR候选直接用于本草稿三分类；尚待用户核查，并非已采用的正式FM升级。

实际赛果及吻合程度：待赛后独立叠加，本稿为空。

北单SP仅用于门槛和展示，不参与MPR概率校正。取消场次#372排除；#392仅在数值身份、双源和≤10分钟时间差及其他质控均通过后纳入。下一期26108未列出的限制仍保留，本稿不是整个窗口完整采集或n8n整期验收。历史公开全场比分的90分钟口径未独立认证；不同比赛独立和主观概率幅度均有限制。没有收益保证，未读取本轮目标结算。本稿不计算800元参考单，不执行票单换入；原带保护版本已另存为未交付的被替代草稿。

复现入口：`r/mpr_draft_20261026.R`的inputs/freeze/replay/render阶段。冻结后票单不因报告渲染而改变；用户核查前不启动发布或自动更新。验收命令、收据和代码审查见docs/reviews/mpr-draft-20261026-1200/acceptance.json。本次没有修改包函数，不配置或触发CI。

W/D/L分别表示实际北单让球后的让胜/让平/让负，均以主队为基准。所有概率沿用已冻结初稿，本次仅转换展示格式；没有重估或读取赛果。文中“未发布”指未发布为生效下注单，GitHub审核稿可公开查看。

本QMD复现需要原工作区已冻结的 inputs.rds、selection.rds
及其源快照；这些二进制未随本审核文档提交，不宣称仅克隆本分支即可完整重建模型。
