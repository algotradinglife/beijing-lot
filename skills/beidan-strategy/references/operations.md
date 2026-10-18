# 发布与自动结算

## 新轮次发布步骤

先读betting-strategy-version.md，分别记录概率模型与下注策略版本；当前搭配为FM-1.7.1＋BS-0.1.0。以下流程复用包和现有更新器，不把某一期activate.py当通用安装器：

1. 绑定用户授权范围、窗口、概率模型、策略参数与配置SHA256。只检查场次时停在可行性报告；用户已允许发布同一冻结方案后继续完成后续步骤。新期必须重建来源/截止/目标全期排除，不复制旧期概率或修改旧receipt的cutoff。
2. 完成模型与准入核验，保存逐层排除、原始响应和独立重放；先冻结概率，再构造准确购票方案。按BS-0.1.0调用权威混合分池入口并验证每轮8组/1000注/2000元，以及组间共享、复用、零重复与完整432排名支持；不能只检查摘要金额。
3. 使用RenderBettingSheet生成HTML、CSV、完整support和只含实购场次的schedule。按实际概率模型/策略版本显示版本，复解析HTML，将每张七场赛果签名、原排名和CSV/冻结purchases逐项比较。排名仍是30–154，不重编号为完整空间1–125；冻结三项赛前SP不能在更新时漂移。
4. 为新批次建立唯一output、独立hot runtime、新sheets/config和完整SHA256绑定，保留旧活跃配置及历史。preflight先通过load_sheet_bindings，集中collect_result_snapshot保存本地observations，再run_results_stage离线结算、render_result_sheet渲染；此时不改公开页。核验未来场次的初始8组待定、收益NA，保存预检回执和registry当前哈希。
5. 干净QMD验收及codex review通过后，复核预检/审查哈希与registry未变化，再检查所有实购比赛仍未开赛。锁定相关runtime及active-rounds.lock，用现有publish_result_pages的备份/回滚事务发布页面、配置、state/publication回执与追加的dashboard批次；不能以手工覆盖HTML绕过绑定。原生异常/身份冲突/接口失败保持显式缺口。
6. 安装独立systemd service/timer：WorkingDirectory、显式R库/项目Python/HOT/NAS根、新config一致；ExecStartPre执行--check，ExecStart执行更新器，ExecStartPost重建完整面板；每小时第15分钟，保留旧服务。daemon-reload、enable --now timer后，实际start一次service，等待完成。
7. 不能只看Result=success或进程退出0：更新器BUSY也可能正常退出。检查last-check.json真实status=UPDATED、queried=true，并确认as_of比预检更晚；BUSY时先等运行/锁释放再重试，不声称已更新。随后核验timer为active、下次触发时间、单页/首页/面板HTTP200及远程字节、版本标记、1000张准确票、旧轮次与历史合计都保留。避免同时手工运行面板重建与首次service导致锁竞争。
8. 交付下注单链接、首页链接、两个版本、组数/注数/金额、截止/首场时间、初始状态、自动更新与终止条件。保留部署回执、备份恢复清单与准确测试结果；旧26102登记脚本依赖旧r_lib的失败不能称通过，也不能据此假定新独立路径失败。修理旧路径与当前登记验证分开说明，任何本次所需路径的失败必须解决。

最新实例：`quarto/fm171_publication_20261019.qmd`及`results/fm171-check-20261019/`。其文件名、日期、原始计数、scope、输出和runtime均绑定该次，使用时只参考合同，不能对旧单原地换日期/概率。新增策略JSON目前是显式参数定义，现有R API不会自动读取它；版本元数据必须由生成客户端写入，面板活跃行读取label，历史算法列读取algorithm，两者均应同时包含FM与BS两个号；仅增加版本元数据字段不会自动改变现有显示。

## HTML

包入口：BuildEvaluationBettingSheetView(evaluation,fixtures,observation=NULL)或BuildBettingSheetView，随后RenderBettingSheet(view,output_file,quarto,title)。模板packages/beidan/inst/quarto/betting_sheet.qmd。准确票单、分组赛果与无损复式CSV必须一致；选项联合仅展示，不能把展示复式全包误作实际购买。RenderBettingSheet拒绝覆盖现有输出。

每注显示序号与全空间排名分开；HTML的data-support-rank保留150–300，不重置1–151。各组命中深度分母是结构理论注数，分子是实际赛果组合完整排名；结构未覆盖为0，未出结果为NA。只有购票HTML无法恢复未买组合排名时显示未知，不伪造0或票序号。命中统计和结构/深度诊断分别展示。

当前远程站点：https://parlay.drwhospaper.site/handicap-wdl/ 。实际发布根从config/betting-sheet-results.json的public_root读取；模板config/public-site/handicap-wdl/index.html同步更新，否则小时任务会覆盖首页修改。把新轮次、已结算实际冻结单和事后诊断分开，不替换旧账本。

读取results/remaining26102-20261007/register-publication.py及quarto/live_sheet_publication_20261007.qmd作为已验收登记范例，**不可原样执行新一期**：旧客户端绑定26102、固定目录/预算/哈希，且仅允许退役已完成runtime。新轮次登记需要新的hot runtime，source.html/schedule.rds与各自sha256；输出名唯一、cutoff原始UTC、期号、结构、组数、实际tickets_per_group、unit_cny/payout_factor。检查src/betting_sheet_results.load_sheet_bindings的当前契约：当前active specs同一期，按唯一output文件名区分独立单，pattern仅表示结构；同结构多个活动单各自结算。生成发布默认接入小时更新。

有未完成旧轮次时不能覆盖现有登记或停掉它。当前服务若不能容纳新旧轮次，先实现/验证独立配置与runtime更新路径或必要扩展，保留旧服务；未完成时不可声称新单已自动更新。

登记/发布配置、首页模板、公开页和验收状态需在相关runtime operation.lock及可回滚事务中处理。备份每次使用唯一目录、库存路径/sha256；恢复不覆盖原备份。所有验证通过才原子替换，失败恢复原配置/页面/状态。NAS禁止原地覆盖，使用现有原子写API。无关页面更改从最新公开首页开始合并，保留实时状态。

## 小时更新

权威入口：scripts/update_betting_sheet_results.py → src/betting_sheet_results.py；集中采集scripts/collect_betting_sheet_results.R → 本地observations.rds/manifest.json → 离线结算scripts/refresh_betting_sheet_results.R；共用边界r/betting_sheet_results.R；购票HTML解析为包ReadBettingSheetHTML及beidan_backend.betting_sheet_html。不运行历史采集/重训代替赛果更新。

仓库根目录执行（根值取当前配置，不搬用旧冻结版本）：

```sh
BEIDAN_HOT_ROOT="$PWD/results" BEIDAN_PARQUET_ROOT=/mnt/nas/Data/beijing-lot \
  .venv/bin/python scripts/update_betting_sheet_results.py --config config/betting-sheet-results.json --check
BEIDAN_HOT_ROOT="$PWD/results" BEIDAN_PARQUET_ROOT=/mnt/nas/Data/beijing-lot \
  .venv/bin/python scripts/update_betting_sheet_results.py --config config/betting-sheet-results.json
systemctl --user status beidan-betting-sheet-results.timer
systemctl --user list-timers beidan-betting-sheet-results.timer
```

--check只校验根与不可变HTML/赛程绑定，不联网。首次单次实际更新通过后，用户已授权自动更新则执行systemctl --user enable --now beidan-betting-sheet-results.timer；若配置改变需先核对systemctl --user cat service/timer并按实际修改daemon-reload。当前已部署timer每小时HKT第15分钟，service的WorkingDirectory/Environment/ExecStart必须匹配当前仓库和根。不创建Codex任务代替现有systemd；不只是声称“每小时”，要给真实active状态及下次触发。

只查询准确购票场次的并集，赛果/结算标签按观察时间记录并校验冲突。更新不能拟合、更改概率、选组、掩码、排名或本金；每次检查原始HTML与schedule sha256。PENDING/WON/LOST与收益待结算分别显示。死票也继续补全所购比赛标签；COMPLETED要求结果与收益统计完整，完成后timer可继续存在，但任务不再联网。失败保留上一成功页面/账本，记录last-check并在下个小时重试，超时和重试有界。

展示投入、命中组/总组、中奖票/实购票、已结算回款、未结算状态、净收益/ROI及最后成功观察时间。任何待结算SP不得拿赛前SP估作实结收益或默认为0。前瞻、历史代理诊断及不可用轮次不混计。

相关回归：packages/beidan/tests/testthat/test-render-betting-sheet.R（如当前路径变动用rg定位）、packages/beidan/tests/python/test_betting_sheet_html.py、tests/testthat/test-betting-sheet-results.R、tests/testthat/test-live-sheet-publication.R、tests/test_live_sheet_registration.py。R库用安装包验证，Python用项目.venv和PYTHONPATH=packages/beidan/inst/python:$PWD。QMD渲染显式声明仓库根，避免依执行目录推断错根。

26103多轮登记实例：results/multiround-hourly-20261009/register.py；新runtime隔离旧已完成账本。原生V球ID与冻结队名/让球/时间逐项校验。集中采集全体购票场次并集，所有单离线读取同一份封存快照，不在单张结算流程联网。Nowscore仅通过完全核验的冻结身份桥或逐场明确核验的译名绑定，独立接纳完场比分和唯一开奖SP；不再以V球有最终彩果作为外部比分的前置条件。来源冲突失败关闭，身份未核验的场次保持待确认。禁止按场号直接接纳身份冲突的彩果。快照保留原始响应、观测时间、来源回执与文件hash清单，即使发布失败也保留。密钥由用户私有EnvironmentFile注入，不进入仓库、报告或回执。详见docs/operations/betting_result_snapshots.md。

## 首页活跃批次登记

首页通过 `active-rounds.html` 展示 `config/active-rounds-dashboard.json` 中明确登记的所有批次。追加轮次时，在新冻结批次首次结算发布成功后，将有辨识度的 `label` 及其结果配置 `config` 加入 `batches`，保留已有登记；新批次必须有独立runtime、唯一output，所有批次共享同一public_root。不能只发布单页而漏掉面板登记。每个新增批次的小时service都须设置 `ExecStartPost=<项目Python> scripts/publish_active_rounds.py --registry config/active-rounds-dashboard.json`，使任何一批更新后都重建完整面板。使用现有runtime操作锁及备份事务更新登记和service，不改旧冻结输入。

命令会锁定全部已登记runtime，核对冻结绑定及stage，再独立重放权威HTML并匹配封存发布页SHA256，最后原子更新面板。批次标签、期号、各轮北京时间观察时间、命中和最终收益分别保留；已结算批次也不会因为新批加入而消失。最后一个批次完整结算后展示最终成绩。登记错误、重复config/runtime/output、不同public_root或快照不一致时失败并保留旧面板。单页和面板仍共用本地集中观察，面板不另抓数据。完成后验证远程首页、面板中所有批次及各自时间戳、service成功和timer启用。

首页已精简为实时表＋历史收益表；registry每批必须提供label、algorithm、config，algorithm使用真实版本号或已登记策略名，不编造FM号。新批次完整结算后自动进入历史表及赛前合计。旧历史台账由 `results/homepage-history-20261017/build-history.R` 从封存审计来源重建，registry绑定 `config/handicap-wdl-history.json` 的SHA256。新增旧历史证据需保持来源哈希、output唯一及金额恒等式，不能与当前登记批次重复。赛中调整单列小计，缺失结算不记零，事后回测仅报告链接，不计入赛前主合计。原逐轮板块已移至history-index-20261017.html归档，不要重新插回首页；保留动态高度iframe。旧共享配置publish_index=false，只有面板命令更新动态统计。
