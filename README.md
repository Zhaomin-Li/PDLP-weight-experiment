# PDLP primal weight 实验

这个仓库用于比较 PDLP/PDHG 中 primal weight 的初始化和更新策略。当前代码是一个实验脚本，不是完整 PDLP 求解器复现。

## 文件说明

- `pdlp_weight_experiment.py`：MPS 读取、简化 PDHG/PDLP 迭代、固定周期 restart 和 adaptive restart 实验。
- `experiment_summary.md`：实验总结、benchmark 说明、结果表格和结论。
- `results/`：实验输出，包括 CSV 历史记录和 JSON 元信息。
- `PDLP.pdf`：参考论文。
- `three_scheme_comparison/`：基于 cuPDLPx 的三方案全量对比实验，包含 `baseline`、固定 `log2` 截断和当前 `signrate_selective` 选择性截断的代码、runner、all26 原始结果和实验报告。

## 最新 cuPDLPx 实验

当前更接近真实求解器的实验放在 `three_scheme_comparison/`。这一版只比较三个方案：

- `baseline`：cuPDLPx 原始 primal weight 更新。
- `fixed_log2`：对每次 `Delta log omega` 无条件做 `[-log2, log2]` 截断。
- `signrate_selective`：先用“大幅更新 + 高频符号翻转”判断是否存在 omega 震荡，只有触发时才启用固定 `log2` 截断。

这一版的核心想法是：固定 `log2` 截断本身有价值，但不应该对所有 benchmark 无条件开启。无条件截断能抑制 `omega` 的剧烈来回跳动，却可能伤害那些确实需要单向大幅调整 `omega` 的问题。因此我们把固定截断改成一个选择性 safeguard：先保留 cuPDLPx 原始 primal weight update，统计历史 `Delta log omega` 是否同时满足“大幅更新”和“频繁正负反转”；只有当这两个信号都出现时，才认为 `omega` 更新更像震荡/过冲，并启用 `[-log2, log2]` 截断。

当前选择器使用的是累计统计，而不是滑动窗口统计：

```text
max |Delta log omega| >= log(10)
sign_change_rate = sign_change_count / (weight_update_count - 1) >= 0.45
```

其中 `weight_update_count` 是已经发生的 primal weight update 次数，`sign_change_count` 是相邻两次 `Delta log omega` 符号发生反转的次数。

主要结果见 `three_scheme_comparison/experiment_report.md`；逐 benchmark 数据见 `three_scheme_comparison/results/derived/comparison_all26.csv`。

## 主要想法

### B：初始化从数据尺度改成初始点附近的更新尺度

论文原始 primal weight 初始化只看数据本身的尺度：

```text
omega0 = ||c|| / ||q||,  if ||c|| > eps_zero and ||q|| > eps_zero
omega0 = 1,             otherwise
```

我们测试的新初始化改成看初始点 `x0, y0` 附近真正推动 primal/dual 更新的两个向量：

```text
a = ||c - K^T y0||
b = ||q - K x0||

omega0_new = a / b,  if a > eps_zero and b > eps_zero
omega0_new = 1,      otherwise
```

这个差别的直觉是：论文初始化衡量的是原始数据尺度；新初始化衡量的是第一步附近 x 方向和 y 方向的实际更新驱动力。也就是说，它更像是从当前初始点出发估计 primal/dual movement 是否平衡。

需要注意的是，如果使用严格零初始点 `x0 = 0, y0 = 0`，那么新初始化会退化成论文原始初始化：

```text
||c - K^T y0|| / ||q - Kx0|| = ||c|| / ||q||
```

因此 B 的优势主要应该在非零 warm start，或者存在非零固定变量导致 `project_box(0, lb, ub)` 不等于 0 的 benchmark 上观察。当前实验中，`physiciansched3-3.mps` 就属于这类会让 B 产生差异的例子。

### C：在 log-space 中截断 primal weight update

论文原始 primal weight update 使用 log smoothing。我们测试的改动是在 log-space 中对单次更新量做截断：

```text
log omega_new = log omega_old
  + truncate(theta * (log(Delta_y / Delta_x) - log omega_old), -a_trunc, a_trunc)
```

默认取：

```text
a_trunc = log 2
```

这等价于每次 restart 后：

```text
omega_new / omega_old in [1/2, 2]
```

也就是说，primal weight 每次最多翻倍或减半。这个选择的直觉是给 primal weight update 加一个 trust-region 风格的限制，避免一次噪声较大的 `Delta_y / Delta_x` 估计把 `omega` 推到几个数量级之外。

需要注意：`2` 只是第一轮实验中容易解释的默认截断倍数，不是理论最优常数。更严谨的后续实验应该比较：

```text
--truncate-factor 1.5
--truncate-factor 2
--truncate-factor 4
无截断
```

## normalized duality gap 的转化

adaptive restart criteria 里需要计算 normalized duality gap。代码中的 saddle function 对应：

```text
L(x, y) = c^T x + y^T(q - Kx)
```

其中代码里使用符号变换统一处理 `<=` 和 `>=` 约束：

```python
k_x(x) = sign * (A @ x)
kt_y(y) = A.T @ (sign * y)
q = sign * b
```

因此可以把代码里的 `k_x(x)` 理解为数学上的 `Kx`，把 `kt_y(y)` 理解为 `K^T y`。

normalized duality gap 需要看局部 saddle gap。令：

```text
x_hat = x + Delta_x
y_hat = y + Delta_y
```

则有：

```text
L(x, y_hat) - L(x_hat, y)
  = (K^T y - c)^T Delta_x + (q - Kx)^T Delta_y
```

所以原本关于 saddle function 的最大化，可以转成关于 `Delta_x, Delta_y` 的线性最大化：

```text
max  (K^T y - c)^T Delta_x + (q - Kx)^T Delta_y
```

约束为：

```text
x + Delta_x in X
y + Delta_y in Y
omega ||Delta_x||^2 + (1 / omega) ||Delta_y||^2 <= r^2
```

这正是代码里 `_bounded_ball_linear_max` 求解的问题。这样转化的好处是：目标函数变成线性的，约束是 box/cone 与 weighted ball 的交集。

代码求解这个 max 子问题时，使用的是 **KKT 条件 + 一维二分** 的思路。先对 weighted ball 约束引入拉格朗日乘子 `lambda`。KKT 条件给出：

```text
lambda >= 0
omega ||Delta_x(lambda)||^2 + (1 / omega) ||Delta_y(lambda)||^2 <= r^2
lambda * (omega ||Delta_x(lambda)||^2 + (1 / omega) ||Delta_y(lambda)||^2 - r^2) = 0
```

如果 ball 约束不活跃，则 `lambda=0`，最优解主要由 box/cone 约束决定；如果 ball 约束活跃，则 `lambda>0`，并且必须有：

```text
omega ||Delta_x||^2 + (1 / omega) ||Delta_y||^2 = r^2
```

当 `lambda` 固定时，`Delta_x` 和 `Delta_y` 的最优解可以写成对 box/cone 约束的逐坐标投影。定义：

```text
phi(lambda) = omega ||Delta_x(lambda)||^2 + (1 / omega) ||Delta_y(lambda)||^2
```

随着 `lambda` 变大，投影步长会变小，因此 `phi(lambda)` 单调下降。代码先找一个足够大的 `high`，使得 `phi(high) <= r^2`；然后对 `lambda` 做二分：

- 如果 `phi(mid) > r^2`，说明步子太大，`lambda` 太小，于是增大下界 `low = mid`；
- 如果 `phi(mid) <= r^2`，说明步子已经在球内，可以尝试更小的 `lambda`，于是令 `high = mid`。

最后得到的 `high` 就是近似的 KKT 乘子。这样就不用直接处理原始 saddle function 的差值最大化，而是求一个结构更简单的投影型线性最大化问题。

## 运行示例

adaptive restart：

```powershell
python .\pdlp_weight_experiment.py `
  --mps "C:\Users\ASUS\Desktop\brazil3.mps" `
  --restart-mode adaptive `
  --max-iter 5000 `
  --truncate-factor 2
```

固定周期 restart：

```powershell
python .\pdlp_weight_experiment.py `
  --mps "C:\Users\ASUS\Desktop\brazil3.mps" `
  --restart-mode fixed `
  --restart-every 100 `
  --max-iter 5000
```

## 重要说明

当前脚本主要用于观察 primal weight 更新规则的数值行为。它没有完整实现论文 PDLP 求解器中的所有模块，例如 presolve、scaling、termination、infeasibility detection 和完整 primal-dual gap 评估。

因此，当前实验更适合支持这样的结论：

```text
截断 update 能让 primal weight 的数值变化更受控，并在部分 benchmark 上改善稳定性。
```

但还不能直接证明：

```text
完整 PDLP 算法在所有问题上都会更快或更好。
```

更详细的实验结果和限制见 `experiment_summary.md`。

## 迭代结构

代码现在使用和论文伪代码更接近的双重循环：

```text
while 总迭代数未达到 max_iter:
    开始一个 restart epoch
    while 当前 epoch 未触发 restart:
        做一次 PDHG 更新
        更新 weighted average
        检查 fixed/adaptive restart 条件
    restart 后更新 primal weight，并进入下一个 epoch
```

外循环对应 restart epoch，内循环对应两个 restart 之间的 PDHG 迭代。这样写比单循环更贴近论文结构，也让 `inner_iteration`、weighted average、restart candidate 和 primal weight update 的关系更清楚。
