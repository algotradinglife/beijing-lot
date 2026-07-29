# 比分预测 V7.7.1 参考资料

本目录保存用户于 2026-07-29 提供的“比分预测 V7.7.1”材料及其可审计代码实现。它是研究参考，不属于当前生产决策链，也不代表仓库对材料中历史命中率声明的背书。

## 原始材料

- `original/比分预测V7.7.1.zip`
- 原始 ZIP SHA-256：`444ee894c3b80f243b2d1bc4330b07bc05d1dfce7908b5ef00152f4d6cd392a9`

ZIP 内含：

| 文件 | SHA-256 |
|---|---|
| `1.模型（发给AI）.docx` | `b332e07697a2db3f21038a05fabead9715d6c7d5d7f8cc1bf04a496ecb8ebe4a` |
| `2.AI调教（发完模型发这个）.docx` | `f1d6c7dc6a56f47b5473acc87f365b24c695be11b0145a7dd1b884f694257c50` |
| `V7.71标准计算手册.pdf` | `7047c09c819ef81e87d95d3b20b5bf76adeb289693bf9dac64b43c74ac2a8402` |
| `使用说明.docx` | `e765536486bf3439f3aa209753aa1c3d4a83fb5a908ef496b508b2ed271fca6a` |
| `最新版本测试数据（未测试完）.pdf` | `ddd9e91592c6d3d80992e61682e00b0b90d547de8d65f443b1e45729e116eea9` |

## 代码

- 实现：`src/score_prediction/v771.py`
- 测试：`tests/score_prediction/test_v771.py`

实现以单场比赛为输入，接收五类赔率：

1. 1X2；
2. 让球 1X2（显式保留让球方向，但按手册始终使用“让球主胜概率”，不做反转）；
3. 半全场的胜胜、平平、负负；
4. 总进球 0–7+；
5. 比分赔率和胜/平/负其它。

输出完整 45 个内部比分概率、核心中间量、候选 TOP15、主榜 TOP3 和副榜 2 个比分。

## 明确的解释性选择

原手册有两处没有定义到可唯一编码的程度。本实现没有隐藏猜测，而是固定如下：

1. “胜其它/平其它/负其它”的市场概率，按尾部修正后模型在对应内部比分桶中的概率比例分摊；桶内模型质量为零时才均匀分摊。
2. 当大球概率位于 10%–20% 时，以两比分组合的 Bayes_Score 总和比较大球方案和小球方案。

此外，排序同概率时按 `(主队进球, 客队进球)` 升序稳定打破平手；副榜永不与主榜重复。

这些选择只为保证参考实现确定、可测试。以后若取得作者的更精确定义，应先新增对照测试，再修改实现。

## 材料中的历史测试页

测试 PDF 记录了 13 场：

- 主榜 TOP3 命中 8 场（61.5%）；
- 副榜补充命中 3 场；
- 合计命中 11 场（84.6%）；
- 完全未命中 2 场。

该页没有附五类输入赔率、采集时间或逐场中间量，因此只能保存为作者提供的结果摘要，不能独立复算，也不能当作防泄漏回测证据。

## 最小调用示例

```python
from src.score_prediction import MatchOdds, ThreeWayOdds, predict

result = predict(
    MatchOdds(
        one_x_two=ThreeWayOdds(2.15, 3.30, 3.50),
        handicap=ThreeWayOdds(3.20, 3.55, 2.05),
        handicap_line=-1,
        half_full=ThreeWayOdds(4.80, 5.30, 5.10),
        total_goals=(12.0, 5.4, 3.2, 3.5, 5.5, 10.0, 18.0, 30.0),
        score_odds={
            "1:0": 7.5,
            "1:1": 6.2,
            "0:1": 9.0,
            "胜其它": 50.0,
            "平其它": 80.0,
            "负其它": 55.0,
        },
    )
)

print([candidate.label for candidate in result.main])
print([candidate.label for candidate in result.auxiliary])
print(result.diagnostics)
```
