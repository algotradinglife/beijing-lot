# 市场胜负方向的动态联合校正对照

本轮固定484期36140场（回撤前305期、回撤94期、回撤后85期），同49个更新块，原市场RAW为参照。ABS与SIGNED只改变市场胜负差是否保留符号。两者都按有符号让球数细分，市场让平边界相同。

ABS差值边界0/.1/.2/.3/.4/.5/.6/1；SIGNED镜像到负半轴。每10期更新，累计历史50%+最近三期50%，二维长期/近期收缩100/20，让球子格长期/近期收缩100/20，最低历史ESS100。历史标签采用本期最后比赛后48小时代理，非前瞻可用性证明。不重新调参，不比较投注收益。

`r/draw_refresh.R::draw_refresh_bins`提供唯一R分档；`draw_refresh_fit`及`draw_handicap_fit`新增必需gap_mode参数，旧调用均显式absolute，不设隐式兼容回退。共享Python准入、时间、权重与receipt不变。预测读取sealed参数。已有冻结artifact只能作历史证据，不能用新源码绕过实现hash重新预测。

QMD194通过共享label-free输入读取器获得冻结概率，经共享prior reader逐块读取此前标签；全部预测保存后才读取评估结果。参数、source和代码hash绑定输出。独立重放重算98模型预测公式，并逐场核对ABS与原484期DYNAMIC结果。相关函数测试覆盖absolute/signed及未来标签和伪造时点变动不影响预测与下游选票。

精细分档可能降低支持数，因此保留方向只是可检验假设，不预设改善，也不将让球赛果方向等同于普通主客胜负。

## 结果

|版本|Brier↓|Log loss↓|Top1|Top2|
|---|---:|---:|---:|---:|
|RAW|.645699|1.068456|43.655%|73.655%|
|ABS|.648045|1.072363|43.426%|73.196%|
|SIGNED|.648359|1.072762|43.215%|73.213%|

SIGNED相对ABS，Top2净增6场，但Top1减少76场；Brier/Log loss/让平Brier都更差。三个阶段的Brier与Log loss也全都恶化。Top2回撤前+27、回撤期-4、回撤后-17。不采纳该版本，不把主客信息无效作为结论，也不声称收益改善。

QMD194为完整执行入口，QMD195为冻结结果结论报告。79项R断言及5项Python共享准入回归通过，时序治理PASS，两个QMD干净进程执行；全仓无关测试未运行，远端CI未启用。

验收记录：79项R断言＝draw-refresh25＋draw-handicap-refresh34＋draw-correction-candidates16＋报告入口4；Python `-m pytest tests/test_draw_refresh_context.py -q` 5项PASS。R通过 `testthat::test_file(...,stop_on_failure=TRUE)` 执行上述文件，项目Python执行 `scripts/check_cutoff_governance.py`。独立R重放72280条校正预测PASS，ABS36140场与旧DYNAMIC最大差小于1e-12。全量渲染入口194及结论入口195使用声明参数、`--no-cache`和干净进程。持久盘证据目录 `audits/signed-draw-v1`。
