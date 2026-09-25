# #520 Nowscore 明确比赛状态证据

同一个 DanChang.aspx?all=1 页面不仅有“截止/HH:mm”的销售显示，也有 `M[slot][4]` 比赛状态码。来源脚本 https://cp.nowscore.com/js/buy/bdLive.js?2019 的 `MatchState()` 定义0为未开赛；refresh明确把D[1]写入M[id][4]并调用MatchState。原始JS保存于包测试fixtures/nowscore.bdLive.js，URL、采集时间与SHA256见520-status-source.json。

修复现有parser读取状态码并绑定M[slot][0]原生比赛ID，ID和HTML行不一致、重复或非法literal报错。正常明确状态码优先于销售显示；与明确比赛状态文本冲突报错。未知代码/待定保持unknown。码原文保留match_status_raw，raw_display_nowscore继续保留销售显示，不改schema或公开API。

0 scheduled；1/2/3/5 live；4/-1 finished；-10/-99 cancelled；-14 postponed；-12/-13按既有中断/腰斩映射abandoned；-11及未知码unknown。没有状态码时仍只认明确比赛状态文本，不根据未来kickoff、可售或截止推状态。

原26098快照实际检查：81:85、87、90、91、96、98全部code0；1:5为-1。slot6显示截止但明确code0，修正旧unknown断言。状态可用时间沿用原页面received/observed时间，不改成解析时或未来决策时间。原快照只证明当时状态，正式未来epoch应重新采集最近快照。

验证：125 Python测试（包括整期146行原始快照回放）与74条R赛程断言通过。解析helper、ID错配、非法/重复、全部状态码、混合销售显示、状态冲突均有回归。QMD集成由#520主代理统一在原walkthrough完成，本子任务不创建第二QMD、不改市场/结算模块。

最终codex review复审结论：无可操作缺陷；独立复跑125 Python与74 R断言通过，核对源JS hash。首轮P2为带空格/空值赋值绕过校验，已修复正则候选识别并补回归。审阅命令：`codex review 'Re-review full staged diff origin/main for #520 explicit Nowscore state mapping and raw evidence, tests, docs. Previous P2 malformed/whitespace state assignment bypass fixed with expanded candidate regex and regressions. Verify no actionable defects; do not edit. No network/CI. Python=/home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python; R_LIBS=/home/drwho1985/workspace/algotradinglife/beijing-lot/r_lib; TMPDIR=/home/drwho1985/workspace/algotradinglife/beijing-lot-identity/.identity-control/tmp. Parent integrates QMD separately.'`。主任务须在其QMD记录集成后的复核和正式交付。
