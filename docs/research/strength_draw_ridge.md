# 战力让平增量信息：收敛检验

当前旧战力让平版本不进入概率底座。直接混合、联合分箱、连续ridge均未证明改善完整概率质量；停止沿这份旧输入继续调参。

范围100608–101120旧档案100期，前10期预热，后90期6114场。非最近回撤期，非未见数据，不代表新基本面模型无效。

连续校正以市场让平logit为offset，标准化市场让平logit、市场胜负差绝对值、有符号让球；联合版本额外加入战力让平logit。固定ridge惩罚10、截距无惩罚；无目标标签调参。依赖mgcv 1.9.4（R推荐包）；运行版本随artifact记录。共享src/strength_draw_context.py及src/temporal_learning提供每10期冻结、累计历史、ESS100和24小时历史标签代理。所有目标预测保存之后才打开评估标签。

|版本|Brier↓|Log loss↓|让平Brier↓|Top2|
|---|---:|---:|---:|---:|
|RAW|0.646464|1.069335|0.197159|73.978%|
|市场ridge|0.646753|1.069645|0.197254|74.125%|
|市场+战力ridge|0.647247|1.070702|0.197586|74.125%|

联合相对市场ridge三个时间段均恶化Brier和Log loss。两者Top2净增RAW9场，联合没有增加总命中；不等于命中场次完全相同。校正平均让平接近实际发生率，不能替代逐场概率评分。固定惩罚未寻优，因此结论是当前证据不支持升级，不是证明任何校正都不可能成功。

QMD入口quarto/193_strength_draw_ridge.qmd；业务函数r/strength_draw_ridge.R的features/fit/predict均对应tests/testthat/test-strength-draw-ridge.R。参数显式，seal绑定代码、标准化参数、模型系数、共享准入receipt和运行版本。输出audit strength-draw-ridge-v2，v1为增加诊断图前的同参数试运行。独立重放验证准入时间、系数梯度、预测公式及评分。

验收命令（从仓库根目录，预先设置R_LIBS_USER、RETICULATE_PYTHON及PYTHONPATH）：

- `/usr/local/bin/Rscript -e 'testthat::test_file("tests/testthat/test-strength-draw-ridge.R", stop_on_failure=TRUE)'`：19断言PASS。
- 项目Python `-m pytest tests/test_strength_draw_context.py -q`：共享适配器回归PASS。
- 项目Python `scripts/check_cutoff_governance.py`：PASS。
- Quarto `render 193_strength_draw_ridge.qmd --execute-params <声明输入参数JSON> --no-cache`：干净进程执行PASS；根目录入口是指向quarto文件的临时符号链接。
- 独立R脚本重放18模型、12228条校正预测及3模型评分：PASS。

未运行全仓无关旧测试，未启用远端CI；本轮仅限该诊断交付，不合并PR。路径验收不证明数据前瞻可用。
