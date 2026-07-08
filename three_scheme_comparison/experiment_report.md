# 三方案 primal weight 更新实验报告

本报告只比较三个方案：`baseline`、`fixed_log2`、`signrate_selective`。所有数据来自当前工作目录内 26 个 benchmark 的 30 秒限制实验。

## 方案定义

- `baseline`：cuPDLPx 原始 primal weight 更新，保留论文/源码中的 movement/PID 更新。
- `fixed_log2`：保留原始更新方向，但对每次 `Delta log omega` 做固定截断：`clip(Delta, -log(2), log(2))`。该版本通过 `CUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE=1` 编译。
- `signrate_selective`：保留原始更新方向；只有当 `max |Delta log omega| >= log(10)` 且 `Delta log omega` 的符号翻转率 `>= 0.45` 时，才启用 `log2` 截断。

## 实验设置

- benchmark 数量：26
- time limit：30 秒
- eval frequency：200
- iter limit：100000000
- 评价不只看单一指标：优先看终止状态，其次看迭代数和运行时间，同时观察 residual/gap 是否保持在可接受范围。

## 总体统计

| 方案 | OPTIMAL 数 | TIME_LIMIT 数 | ITERATION_LIMIT 数 | 总迭代数 | 总运行时间(s) | 中位运行时间(s) | 平均 relative gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 19 | 7 | 0 | 878200 | 271.824 | 4.2980 | 0.0617137 |
| fixed_log2 | 19 | 5 | 2 | 1087200 | 286.998 | 5.0110 | 0.0436296 |
| signrate_selective | 19 | 7 | 0 | 870600 | 270.512 | 3.9200 | 0.0432901 |

## 两两胜负统计

| 对比 | 迭代数 胜/负/平 | 运行时间 胜/负/平 |
|---|---:|---:|
| fixed_log2 vs baseline | 8/9/9 | 8/12/6 |
| signrate_selective vs baseline | 4/0/22 | 10/2/14 |
| signrate_selective vs fixed_log2 | 10/5/11 | 15/6/5 |

## 逐 benchmark 对比

| benchmark | baseline 状态/迭代/时间 | fixed_log2 状态/迭代/时间 | signrate 状态/迭代/时间 | signrate applied | 主要观察 |
|---|---:|---:|---:|---:|---|
| Primal2_1000 | OPTIMAL / 10800 / 5.4620 | OPTIMAL / 4000 / 2.0240 | OPTIMAL / 10800 / 5.4550 | 0 | fixed_log2 迭代更少 |
| bharat | TIME_LIMIT / 49000 / 30.091 | TIME_LIMIT / 49000 / 30.103 | TIME_LIMIT / 49200 / 30.082 | 0 | 整体接近 baseline |
| brazil3 | OPTIMAL / 2200 / 0.083 | OPTIMAL / 2800 / 0.097 | OPTIMAL / 2200 / 0.075 | 0 | signrate 迭代少于 fixed_log2 |
| chromaticindex1024-7 | OPTIMAL / 1200 / 0.089 | OPTIMAL / 800.000 / 0.074 | OPTIMAL / 800.000 / 0.066 | 1.0000 | signrate 迭代少于 baseline |
| datt256_lp | OPTIMAL / 400.000 / 0.072 | OPTIMAL / 400.000 / 0.081 | OPTIMAL / 400.000 / 0.072 | 0 | 整体接近 baseline |
| dlr1 | TIME_LIMIT / 60600 / 30.030 | OPTIMAL / 28400 / 14.058 | TIME_LIMIT / 60400 / 30.057 | 0 | fixed_log2 迭代更少 |
| ex10 | OPTIMAL / 600.000 / 0.091 | OPTIMAL / 600.000 / 0.092 | OPTIMAL / 600.000 / 0.087 | 0 | 整体接近 baseline |
| fhnw-binschedule1 | TIME_LIMIT / 28000 / 30.164 | TIME_LIMIT / 27800 / 30.000 | TIME_LIMIT / 27600 / 30.113 | 5.0000 | signrate 迭代少于 baseline；signrate 迭代少于 fixed_log2 |
| graph40-40 | OPTIMAL / 400.000 / 0.098 | OPTIMAL / 400.000 / 0.105 | OPTIMAL / 400.000 / 0.113 | 0 | 整体接近 baseline |
| irish-electricity | OPTIMAL / 39600 / 3.0150 | ITERATION_LIMIT / 200000 / 15.308 | OPTIMAL / 39600 / 3.0340 | 0 | signrate 避免 fixed_log2 未收敛；signrate 迭代少于 fixed_log2 |
| neos-3025225 | OPTIMAL / 19000 / 7.1660 | OPTIMAL / 58200 / 21.888 | OPTIMAL / 19000 / 7.1660 | 0 | signrate 迭代少于 fixed_log2 |
| neos-5052403-cygnet | OPTIMAL / 7600 / 1.5640 | OPTIMAL / 7800 / 1.6140 | OPTIMAL / 7600 / 1.5680 | 0 | signrate 迭代少于 fixed_log2 |
| neos-5251015 | OPTIMAL / 1200 / 0.322 | OPTIMAL / 1000 / 0.274 | OPTIMAL / 1000 / 0.269 | 1.0000 | signrate 迭代少于 baseline |
| physiciansched3-3 | OPTIMAL / 174600 / 15.045 | ITERATION_LIMIT / 200000 / 17.259 | OPTIMAL / 174600 / 14.896 | 0 | signrate 避免 fixed_log2 未收敛；signrate 迭代少于 fixed_log2 |
| qap15 | OPTIMAL / 2800 / 0.092 | OPTIMAL / 2800 / 0.092 | OPTIMAL / 2800 / 0.091 | 0 | 整体接近 baseline |
| rmine15 | OPTIMAL / 22200 / 3.7970 | OPTIMAL / 14800 / 2.5420 | OPTIMAL / 16000 / 2.7420 | 3.0000 | signrate 迭代少于 baseline；fixed_log2 迭代更少 |
| s100 | TIME_LIMIT / 168000 / 30.010 | OPTIMAL / 165000 / 29.488 | TIME_LIMIT / 167800 / 30.017 | 0 | fixed_log2 迭代更少 |
| s250r10 | OPTIMAL / 76200 / 11.757 | OPTIMAL / 92600 / 14.293 | OPTIMAL / 76200 / 11.760 | 0 | signrate 迭代少于 fixed_log2 |
| s82 | TIME_LIMIT / 34800 / 30.093 | TIME_LIMIT / 34800 / 30.070 | TIME_LIMIT / 34800 / 30.169 | 0 | 整体接近 baseline |
| savsched1 | OPTIMAL / 800.000 / 0.228 | OPTIMAL / 800.000 / 0.229 | OPTIMAL / 800.000 / 0.222 | 0 | 整体接近 baseline |
| scpm1 | OPTIMAL / 8000 / 4.7990 | OPTIMAL / 13200 / 7.9380 | OPTIMAL / 8000 / 4.8060 | 0 | signrate 迭代少于 fixed_log2 |
| square41 | TIME_LIMIT / 94600 / 30.004 | TIME_LIMIT / 94800 / 30.056 | TIME_LIMIT / 94400 / 30.003 | 0 | 整体接近 baseline |
| supportcase10 | OPTIMAL / 12800 / 0.919 | OPTIMAL / 22400 / 1.6030 | OPTIMAL / 12800 / 0.886 | 0 | signrate 迭代少于 fixed_log2 |
| supportcase19 | TIME_LIMIT / 47400 / 30.083 | TIME_LIMIT / 47400 / 30.075 | TIME_LIMIT / 47400 / 30.035 | 0 | 整体接近 baseline |
| tpl-tub-ws1617 | OPTIMAL / 14600 / 6.5520 | OPTIMAL / 16800 / 7.4800 | OPTIMAL / 14600 / 6.5330 | 0 | signrate 迭代少于 fixed_log2 |
| woodlands09 | OPTIMAL / 800.000 / 0.198 | OPTIMAL / 600.000 / 0.155 | OPTIMAL / 800.000 / 0.195 | 1.0000 | fixed_log2 迭代更少 |

## 结论

在当前全量 benchmark 上，`signrate_selective` 是目前三者里更稳的方案。它比无条件 `fixed_log2` 更少出现大幅退化，同时保留了一部分固定截断带来的加速收益。

固定 `log2` 截断说明“限制 omega 单次变化”确实有价值，但无条件截断会伤害需要单向大幅重平衡的 benchmark。`signrate_selective` 的优势在于只在大更新伴随高频正负翻转时介入，因此更像一个针对过冲/震荡的 safeguard，而不是全局替代原始权重更新。

当前不足是该选择器仍偏保守：有些 fixed_log2 明显有收益的样例不会被充分激活。后续如果继续优化，建议只微调 `log(10)` 和 `0.45` 两个阈值，不建议改变整体算法结构。
