# 每日模拟单的持久化目录

`config/persistent_data_layout.json` 登记两个独立域：每日模拟分析的 `runtime/daily-paper-handicap-wdl`，以及当前已发布下注单的结果更新 `runtime/betting-sheet-results-handicap-wdl`。数据根统一使用NAS `/mnt/nas/Data/beijing-lot`，挂载点为 `/mnt/nas/Data`；Sandisk已退役，不再作为运行输入或输出。不引用或修改历史数据注册表、SQLite、归档或历史采集断点。

写入前运行 `.venv/bin/python scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json`。入口复用 `src/settlement_storage.py::validate_settlement_storage` 检查挂载和路径逃逸；缺盘直接失败，不回退工作区。叶目录可在检查通过后创建。

每日目录按本地生成日期命名；一次准备及每次结算使用各自独立目录。生成单冻结后不可覆盖；重新运行只重放同一冻结单。结算版本可以推进，原始响应及旧结算快照保留。网页只发布渲染后的HTML，不公开输入或原始文件树。

当前下注单结果更新由 `config/betting-sheet-results.json` 及 `config/public-site/sheets.json` 显式指定三份已冻结方案。每小时只对尚未完成的方案查询一次共用赛果来源，记录实际观测时间。`runs/` 下保留原始响应、结算 RDS、渲染 HTML、执行日志和替换前网页备份；`state.json` 只在全部新网页发布成功后推进，`last-check.json` 记录失败或已完成。所有方案完成后停止联网查询。缺盘、冻结输入哈希变化、赛果或 SP 冲突均直接失败，保留上次成功网页。

## 2026-10-18：NAS为唯一长期保留位置

用户确认Sandisk已经移除，后续需要长期保留的分析数据、采集成果与验收报告统一归档到NAS。分析数据继续使用catalog登记、不可变版本及包读取接口；派生报告使用共享versioning.publish_version发布至frozen层，不另建持久化数据根。既有hot层只表示短期工作缓存，在完成NAS发布和核验之前必须单列为“未持久化”，不得把本地存在当作长期保留完成。运行缓存的归档或迁移按现有一致性备份和停写验收流程执行；历史凭证里的原始路径保留用于溯源，不作为现行运行配置。不得直接将运行中SQLite文件复制到CIFS作为迁移完成。
