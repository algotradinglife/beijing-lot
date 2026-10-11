# 发布与自动结算

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
