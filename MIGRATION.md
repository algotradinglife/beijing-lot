# Migration record for beijing-lot

迁移时间：2026-06-07T15:21:31+08:00
档位：D
源：/Volumes/Data Drive/workspace/trading/beijing-lot
目标：/Users/huhan/code/trading/beijing-lot

## 数据路径映射

| 旧路径（仓内） | 新路径（外置盘） |
| --- | --- |
| `data/` | `/Volumes/Data Drive/data/derived/beijing-lot` |

## 改代码（待人手）

请把硬编码的老路径替换为环境变量。嫌疑位置见 plan.yaml 的 hardcoded_path_hits 字段。
