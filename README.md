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

## 运行示例

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
