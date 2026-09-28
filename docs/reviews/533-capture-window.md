# #533 补充：完整赛程的采集窗口

根因：原QMD把 `market_slots` 固定为20场、最高78。窗口函数本身并未排除明天79–120；被采集子集提前丢弃，随后又只把该子集传入准备函数，造成“整个窗口只剩7场”的误解。此前验收只验证有限快照链路，未检查完整赛程到采集入口的覆盖关系。

修正：新增 `match_market_schedule(schedule, reference_at)`，复用现有 `match_decision_window` 的 [参考时点+4小时, +28小时)；返回完整窗口赛程、明确排除及时间边界，不按slot截断。选择本身不认定状态合格或盘口可用，第6块保留正式时点后的独立准入。完整赛程送入 `match_inputs_from_capture`，没有报价的场次由正式准备环节明确排除；第5块先列出未采集场次。

测试：package `test-market-schedule.R` 18条断言；repository `test-26098-walkthrough.R` 20条断言，全部通过，无warning。覆盖79/120跨日、下界包含上界排除、顺序/时区一致、空表/未知时间、非法输入；实际QMD代码块验证旧缓存只含78时79/120仍留在待采集列表与完整下游赛程，历史回放不发新请求。

命令（仓库根目录，R_LIBS=$PWD/r_lib、TMPDIR=$PWD/.run-control/tmp）：

```r
devtools::load_all("packages/beidan", quiet=TRUE)
testthat::test_file("packages/beidan/tests/testthat/test-market-schedule.R", reporter="summary", stop_on_failure=TRUE)
testthat::test_file("tests/testthat/test-26098-walkthrough.R", reporter="summary", stop_on_failure=TRUE)
```

干净会话执行 `.run-control/533-capture-validation.qmd`（原QMD仅关闭两项采集、显式回放2026-09-26 19:28:00北京时间；末尾验收文字后补，执行块未变），`quarto render ... --to html --execute --no-cache`；使用显式BEIDAN_PROJECT_DIR、R_LIBS、TMPDIR、XDG_CACHE_HOME、DENO_DIR和项目RETICULATE_PYTHON。HTML无执行错误；完整赛程146场，采集窗口52场（其中42场slot>78），旧快照尚缺45场，正式准入仍7场，未把缺报价误报为已完成。

`codex review` 针对上述新增函数、导出、函数测试、实际QMD Block5/进度与其回归完成只读审阅，结论 No actionable defects found within the requested scope。完整命令/源码与输入哈希见 `533-capture-window-hashes.json`；日志 `.run-control/533-capture-review.log`。没有重复全仓测试、没有CI或新联网采集。

已用pak更新本地安装版，独立加载确认选择52场且原生ID完整唯一。用户重跑第2块后将 refresh_markets=TRUE、replay_decision_at=NULL，再执行第5–8块才会补采新盘口；仅重跑构组不会获得新报价。此前913条断言属于前一轮交付，本次新增窗口38条专项不冒充全仓验收。
