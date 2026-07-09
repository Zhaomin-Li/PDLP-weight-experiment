# Three Scheme Comparison Package

本文件夹归档三个方案的代码入口、runner 和 all26 实验结果：

- `baseline`：cuPDLPx 原始 primal weight 更新。
- `fixed_log2`：固定 `[-log2, log2]` 截断。
- `signrate_selective`：当前选择性截断方案。

## 实验想法

cuPDLPx 的原始 primal weight update 会在 restart 时根据 primal/dual movement 的不平衡程度更新 `omega`。这个更新有时会给出很大的 `Delta log omega`，也就是希望 `omega` 在一次 restart 后放大或缩小很多。

我们最初测试过固定 `log2` 截断：

```text
Delta_used = clip(Delta_raw, -log(2), log(2))
```

它等价于限制每次 restart 后：

```text
omega_new / omega_old in [1/2, 2]
```

这个限制可以抑制 `omega` 的剧烈跳动，但实验中也看到：无条件截断会伤害某些需要单向大幅重平衡 `omega` 的 benchmark。因此这一版 `signrate_selective` 不直接替代原始更新，而是在固定 `log2` 截断前面加一个选择器。

选择器判断的是：当前问题的 `omega` 更新是否更像“大幅震荡”，而不是必要的单向调节。具体使用累计历史统计：

```text
max |Delta log omega| >= log(10)
sign_change_rate >= 0.45
```

其中：

```text
sign_change_rate =
    delta_log_omega_sign_change_count / (weight_update_count - 1)
```

- `weight_update_count`：已经发生的 primal weight update 次数，也就是累计记录到的 `Delta log omega` 个数。
- `weight_update_count - 1`：相邻两次 `Delta log omega` 可以比较符号的次数。
- `delta_log_omega_sign_change_count`：相邻两次 `Delta log omega` 符号发生反转的次数。

只有当历史上出现过至少一次很大的 `Delta log omega`，并且相邻更新方向经常正负反转时，才启用固定 `log2` 截断：

```text
Delta_used = clip(Delta_raw, -log(2), log(2))
```

否则保留 cuPDLPx 原始更新：

```text
Delta_used = Delta_raw
```

因此这一版的定位是一个选择性 safeguard：尽量在 `omega` 更新表现出过冲/震荡时介入，同时避免在需要大幅单向调整的情况下过早限制原始算法。

## 目录

- `code/`：三种方案相关源码、构建脚本和运行脚本。
- `runners/`：本次实验使用的可执行文件和 DLL。
- `results/raw/`：三种方案的原始 all26 `runs.csv/json`。
- `results/derived/`：生成的对比表和汇总表。
- `experiment_report.md`：中文实验报告。

## 关键文件

- `results/derived/comparison_all26.csv`：逐 benchmark 三方案对比。
- `results/derived/summary_metrics.csv`：总体统计。
- `results/derived/pairwise_counts.csv`：两两胜负统计。
