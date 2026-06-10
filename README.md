# PDLP primal weight 实验

这个仓库用于比较 PDLP/PDHG 中 primal weight 的初始化和更新策略。当前代码是一个实验脚本，不是完整 PDLP 求解器复现。

## 文件说明

- `pdlp_weight_experiment.py`：MPS 读取、简化 PDHG/PDLP 迭代、固定周期 restart 和 adaptive restart 实验。
- `experiment_summary.md`：实验总结、benchmark 说明、结果表格和结论。
- `results/`：实验输出，包括 CSV 历史记录和 JSON 元信息。
- `PDLP.pdf`：参考论文。

## 主要想法

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

代码求解这个 max 子问题时，使用的是 **KKT 条件 + 一维二分** 的思路：先对 weighted ball 约束引入拉格朗日乘子 `lambda`。当 `lambda` 固定时，`Delta_x` 和 `Delta_y` 的最优解可以写成对 box/cone 约束的逐坐标投影；同时 weighted ball 半径关于 `lambda` 单调变化。因此可以对 `lambda` 做二分，找到使

```text
omega ||Delta_x||^2 + (1 / omega) ||Delta_y||^2 = r^2
```

成立的乘子。这样就不用直接处理原始 saddle function 的差值最大化，而是求一个结构更简单的投影型线性最大化问题。

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
