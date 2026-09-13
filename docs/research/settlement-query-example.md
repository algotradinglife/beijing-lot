# R 读取外置盘结算数据

从仓库根目录运行，先确认 Sandisk 已挂载。

```r
source("r/nowscore_query.R")
data_root <- "/run/media/drwho1985/Sandisk/data/beijing-lot"
reference <- jsonlite::read_json(file.path(data_root, "registry", "settlement-current.json"))
db_path <- file.path(data_root, reference$database)
x <- query_nowscore_settlement(db_path, "100213", play = "bf")
View(x$settlement)
View(x$findings)

# 整期全部玩法
all_plays <- query_nowscore_settlement(db_path, "100213")
# 指定场次
one <- query_nowscore_settlement(db_path, "100213", slot = 1)
```

查询只读，不会修改数据库。旧 dda7 工作区内的 SQLite 已迁移。审计库与查询库位于同一版本的 `settlement/releases/` 目录；更新前备份位于 `settlement/backups/20260907_history_five_play_v2/`，迁移凭证位于 `settlement/manifests/20260907_history_five_play_v2/`。
