# PDLP primal weight 对照实验小结

## 待评估改动

论文原始初始化：

```text
omega0 = ||c|| / ||q||,  if ||c|| > eps_zero and ||q|| > eps_zero
omega0 = 1,             otherwise
```

新初始化：

```text
a = ||c - K^T y0||
b = ||q - K x0||
omega0 = a / b,  if a > eps_zero and b > eps_zero
omega0 = 1,      otherwise
```

截断 update：

```text
log omega_new = log omega_old
  + truncate(theta * (log(Delta_y / Delta_x) - log omega_old), -a_trunc, a_trunc)
```

本实验取 `a_trunc = log 2`。

## benchmark 适配性

`qap15.mps` 已重新尝试，但不纳入正式结论。原因是它的 RHS 全零，`||q||=0`，论文初始化和新初始化都会回退到 `omega0=1`；同时目标系数非负、变量默认下界为 0，因此 `x=0,y=0` 在当前连续松弛实验中就是平凡固定点。固定周期 restart、高频 restart 和 adaptive restart 三种模式下，四组结果均为 `objective=0, primal_rel=0, dual_fp_rel=0, omega=1`，无法检验 primal weight 初始化或截断行为。

`rmine15.mps` 纳入正式对照。它规模适中，只有 `L` 约束，RHS 非零但很稀疏，适合补充一个和 `brazil3/physiciansched3-3` 不同结构的样本。不过它的有效初始点仍是零，因此只能测试截断 update C，不能测试新初始化 B。

## 初始化说明

如果使用严格零初始点 `x0=0,y0=0`，新初始化与论文原始初始化完全相同：

```text
||c - K^T y0|| / ||q - Kx0|| = ||c|| / ||q||
```

因此，`ex10.mps`、`brazil3.mps` 和 `rmine15.mps` 上的新初始化 B 与论文原始初始化完全一致。

`physiciansched3-3.mps` 有 901 个非零固定变量。按脚本的初始化方式 `x0=project_box(0,lb,ub), y0=0`，有效初始点不是严格原点，因此 B 会产生轻微差异：

| benchmark | 论文原始 omega0 | 新初始化 omega0 |
|---|---:|---:|
| `ex10.mps` | 9.40213 | 9.40213 |
| `brazil3.mps` | 0.000120496 | 0.000120496 |
| `rmine15.mps` | 0.00138881 | 0.00138881 |
| `physiciansched3-3.mps` | 2.27042e-05 | 2.29971e-05 |

## 实验设置

## 代码与论文算法的一致性

当前脚本不是论文完整 PDLP 的严格复现，而是用于比较 primal weight 初始化和截断 update 的简化 PDHG 对照实验。

与论文截图中简化 PDHG 公式一致的部分：

- primal update 使用 `x^+ = proj_X(x - eta / omega * (c - K^T y))`。
- dual update 使用 `y^+ = proj_Y(y + eta * omega * (q - K(2x^+ - x)))`。
- 论文原始初始化实现为 `omega0 = ||c|| / ||q||`，零范数时回退到 `1`。
- 论文原始 primal weight update 实现为 log smoothing：`log omega_new = theta log(Delta_y/Delta_x) + (1-theta) log omega_old`。
- 截断 update 只是在上述 log smoothing 的单次变化量上加上下界和上界。
- 迭代控制流使用显式外循环和内循环：外循环对应 restart epoch，内循环对应两个 restart 之间的 PDHG steps。

与论文完整 PDLP 不一致或简化的部分：

- 当前脚本同时支持两种 restart：固定周期 `restart_every`，以及按论文三条 criteria 触发的 adaptive restart。
- 没有实现论文完整的 presolve、scaling、termination、infeasibility detection 和 primal-dual gap 评估。
- 步长 `eta` 使用 power iteration 估计的 `0.9 / ||A||_2`，不是精确谱范数，也没有额外自适应步长逻辑。
- residual 指标是实验用指标，尤其 `dual_fp_rel` 是 box 投影 fixed-point 指标，不等同于论文完整 KKT residual/gap。
- MPS 读取器只支持本实验需要的常见段，不支持 `RANGES`，也没有完整处理所有 MPS 扩展格式。
- 整数/二进制变量只按 bounds 做连续 LP 松弛处理，这符合 LP 实验目的，但不是 MIP 求解。
- 非有限数保护是实验工程保护，不是论文算法的一部分。
- normalized duality gap 的局部最大化子问题使用 Python/NumPy 中的 KKT + 一维二分实现，目的是复现实验逻辑；它不是论文工程实现中的高性能版本。

adaptive restart 实现说明：

- 每 40 次迭代检查一次 restart criteria，对应论文中实际实现的检查频率。
- 使用论文参数 `beta_sufficient=0.9`、`beta_necessary=0.1`、`beta_artificial=0.5`。
- restart candidate 在当前 iterate 和 weighted average iterate 中选择 normalized duality gap 更小的点。
- normalized duality gap 按论文定义实现为局部 saddle gap，并用一维二分求解 box/cone 与 weighted ball 交集上的线性最大化。
- 论文伪代码第一轮会涉及 `z^{-1,0}`，但未显式给出该点。本脚本采用工程约定：第一轮 reference gap 视为无穷大，因此第一次 criteria 检查允许触发 restart；后续 outer loop 使用相邻两个 restart 点计算 reference gap。

因此，当前 adaptive restart 比固定周期实验更接近论文，但仍然不是完整 PDLP solver，因为 presolve、scaling、termination、infeasibility detection 和完整 primal-dual gap 体系仍未实现。

| benchmark | 约束数 | 变量数 | 非零元数 | 行类型 | `||c||_2` | `||b||_2` |
|---|---:|---:|---:|---|---:|---:|
| `ex10.mps` | 69608 | 17680 | 1162000 | E: 200, L: 69408 | 132.9662 | 14.1421 |
| `brazil3.mps` | 14646 | 23968 | 133184 | E: 9486, G: 1371, L: 3789 | 1.0000 | 8299.0360 |
| `rmine15.mps` | 358395 | 42438 | 879732 | L: 358395 | 85.5766 | 61618.7877 |
| `physiciansched3-3.mps` | 266227 | 79555 | 1062479 | E: 319, G: 6567, L: 259341 | 1.0000 | 44044.6760 |

固定 restart 周期：

| 实验设置 | max_iter | restart_every | theta | 截断倍数 |
|---|---:|---:|---:|---:|
| 主实验 | 5000 | 100 | 0.5 | 2 |
| 高频 restart 实验 | 1000 | 10 | 0.5 | 2 |

这里的 `restart_every=100` 和 `restart_every=10` 是为了隔离 primal weight 规则而采用的固定 restart 周期。论文说明 primal weight 只在 restart 时更新，但没有把 restart 简化为固定周期。实际 PDLP 通常会使用自适应 restart 规则。

## 主实验结果

`max_iter=5000`, `restart_every=100`

| benchmark | 组别 | 初始 omega | 目标值 | primal_rel | dual_fp_rel | 最终 omega | 最大 log-step |
|---|---|---:|---:|---:|---:|---:|---:|
| `ex10.mps` | 论文原始版本 | 9.40213 | 100.003 | 0.006442 | 1.3186 | 12.7601 | 0.4592 |
| `ex10.mps` | 截断 update | 9.40213 | 100.003 | 0.006442 | 1.3186 | 12.7601 | 0.4592 |
| `brazil3.mps` | 论文原始版本 | 0.000120496 | 0.200076 | 1.363e-05 | 6.2395 | 18555.5 | 1.7107 |
| `brazil3.mps` | 截断 update | 0.000120496 | 0 | 1.527e-05 | 0.000803 | 30.1773 | 0.6931 |
| `rmine15.mps` | 论文原始版本 | 0.00138881 | -8367.69 | 0.004290 | 1.2777 | 4.786e+28 | 2.3113 |
| `rmine15.mps` | 截断 update | 0.00138881 | -8309.46 | 0.004213 | 1.2759 | 7.940e+08 | 0.6931 |
| `physiciansched3-3.mps` | 论文原始版本 | 2.27042e-05 | -1.490e+69 | 3.382e+64 | 0 | 6.985e-74 | 3.2662 |
| `physiciansched3-3.mps` | 仅新初始化 | 2.29971e-05 | -1.415e+69 | 3.213e+64 | 0 | 7.354e-74 | 3.2662 |
| `physiciansched3-3.mps` | 截断 update | 2.27042e-05 | -1.301e+17 | 2.952e+12 | 1.100e-34 | 2.017e-20 | 0.6931 |
| `physiciansched3-3.mps` | 新初始化 + 截断 update | 2.29971e-05 | -1.284e+17 | 2.915e+12 | 1.114e-34 | 2.043e-20 | 0.6931 |

## 高频 restart 实验结果

`max_iter=1000`, `restart_every=10`

| benchmark | 组别 | 结束迭代 | 初始 omega | 目标值 | primal_rel | dual_fp_rel | 最终 omega | 最大 log-step |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `ex10.mps` | 论文原始版本 | 1000 | 9.40213 | 101.575 | 0.068678 | 8.7409 | 94.0468 | 0.7224 |
| `ex10.mps` | 截断 update | 1000 | 9.40213 | 101.713 | 0.072343 | 8.3610 | 92.4036 | 0.6931 |
| `brazil3.mps` | 论文原始版本 | 1000 | 0.000120496 | 9.31513 | 0.000619 | 32.6280 | 14416.1 | 1.0698 |
| `brazil3.mps` | 截断 update | 1000 | 0.000120496 | 7.81291 | 0.000569 | 8.7476 | 3506.27 | 0.6931 |
| `rmine15.mps` | 论文原始版本 | 1000 | 0.00138881 | -8478.76 | 0.018132 | 0.033818 | 0.004159 | 1.1519 |
| `rmine15.mps` | 截断 update | 1000 | 0.00138881 | -8211.82 | 0.023487 | 0.121356 | 0.003489 | 0.6931 |
| `physiciansched3-3.mps` | 论文原始版本 | 860 | 2.27042e-05 | -7.576e+154 | inf | 0 | 3.511e-159 | 4.3279 |
| `physiciansched3-3.mps` | 仅新初始化 | 860 | 2.29971e-05 | -6.861e+154 | inf | 0 | 3.876e-159 | 4.3279 |
| `physiciansched3-3.mps` | 截断 update | 1000 | 2.27042e-05 | -1.465e+31 | 3.327e+26 | 0 | 1.791e-35 | 0.6931 |
| `physiciansched3-3.mps` | 新初始化 + 截断 update | 1000 | 2.29971e-05 | -1.447e+31 | 3.285e+26 | 0 | 1.814e-35 | 0.6931 |

## 论文 adaptive restart criteria 实验结果

`ex10.mps` 和 `brazil3.mps` 跑 5000 次迭代；`rmine15.mps` 和 `physiciansched3-3.mps` 因 normalized duality gap 检查在 Python 中开销较大，先跑 1000 次迭代。`rmine15.mps` 的 5000 次 adaptive 实验超过 10 分钟未完成。

下表结果已使用显式外循环 + 内循环版本重新生成；数值与重构前保持一致。

| benchmark | 组别 | 迭代数 | restart 次数 | 初始 omega | 目标值 | primal_rel | dual_fp_rel | 最终 omega |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `ex10.mps` | 论文原始版本 | 5000 | 51 | 9.40213 | 99.997 | 0.001127 | 0.090824 | 6.6278 |
| `ex10.mps` | 截断 update | 5000 | 51 | 9.40213 | 100.000 | 0.000115 | 0.035031 | 8.38845 |
| `brazil3.mps` | 论文原始版本 | 5000 | 32 | 0.000120496 | 0 | 1.575e-05 | 1.599e-06 | 0.00199998 |
| `brazil3.mps` | 截断 update | 5000 | 38 | 0.000120496 | 0 | 1.639e-05 | 8.540e-07 | 0.000751954 |
| `rmine15.mps` | 论文原始版本 | 1000 | 13 | 0.00138881 | -8438.32 | 0.004430 | 0.000151 | 0.000170765 |
| `rmine15.mps` | 截断 update | 1000 | 13 | 0.00138881 | -8439.05 | 0.004458 | 0.000121 | 0.000178299 |
| `physiciansched3-3.mps` | 论文原始版本 | 1000 | 5 | 2.27042e-05 | -7.181e+06 | 163.032 | 1.392e-07 | 1.349e-09 |
| `physiciansched3-3.mps` | 仅新初始化 | 1000 | 5 | 2.29971e-05 | -6.818e+06 | 154.789 | 1.467e-07 | 1.421e-09 |
| `physiciansched3-3.mps` | 截断 update | 1000 | 5 | 2.27042e-05 | -17470.5 | 0.418717 | 5.723e-05 | 7.095e-07 |
| `physiciansched3-3.mps` | 新初始化 + 截断 update | 1000 | 5 | 2.29971e-05 | -17248.0 | 0.413936 | 5.797e-05 | 7.187e-07 |

## 结论

新初始化 B：

- 在 `ex10.mps`、`brazil3.mps` 和 `rmine15.mps` 上与论文原初始化完全相同，因为有效初始点为零。
- 在 `physiciansched3-3.mps` 上产生约 1.29% 的初始 omega 差异，因为存在非零固定变量。
- 这个差异带来了一点数值改善，但不足以说明 B 本身能显著改善算法。要评价 B，仍需要更明确的非零 warm-start 实验。

截断 update C 的改进：

- 在 `brazil3.mps` 上明显改善 dual_fp_rel，并把最终 omega 从 `18555.5` 压到 `30.1773`。
- 在 `physiciansched3-3.mps` 上显著抑制数值爆炸。主实验中 primal_rel 从 `3.382e+64` 降到 `2.952e+12`，高频 restart 下原 update 在第 860 次迭代出现非有限残差，而截断 update 跑满 1000 次。
- 在 `rmine15.mps` 主实验中，C 把最终 omega 从 `4.786e+28` 压到 `7.940e+08`，primal_rel 略优，dual_fp_rel 基本持平。
- 在论文 adaptive restart criteria 下，`ex10.mps` 的 primal_rel 从 `0.001127` 降到 `0.000115`，dual_fp_rel 从 `0.090824` 降到 `0.035031`。
- 在论文 adaptive restart criteria 下，`physiciansched3-3.mps` 的 primal_rel 从 `163.032` 降到 `0.418717`，说明截断对极端 weight 变化仍有明显稳定作用。

截断 update C 的恶化或风险：

- 在 `ex10.mps` 高频 restart 下，C 的 primal_rel 略差。
- 在 `rmine15.mps` 高频 restart 下，C 明显变差：primal_rel 从 `0.018132` 升到 `0.023487`，dual_fp_rel 从 `0.033818` 升到 `0.121356`。
- 在论文 adaptive restart criteria 下，`brazil3.mps` 和 `rmine15.mps` 的 primal_rel 也略有变差，但 dual_fp_rel 变好。
- 这说明截断是稳定器，不是单调加速器。过强或过频繁的截断可能延迟 omega 调整，导致某些指标变差。

## 是否让整个算法变得更好

当前证据支持较稳妥的结论：**截断 update C 会让 primal weight 的数值变化更受控，并在部分 benchmark 上显著改善稳定性。**

但还不能直接说“整个算法一定更好”。原因有三点：

1. 本实验已经加入论文 adaptive restart criteria，但仍没有完整复现 presolve、scaling、termination 和 infeasibility detection。
2. C 改善了 omega 稳定性，但在 `rmine15.mps` 高频 restart 下 residual 反而变差；adaptive restart 下也存在 primal_rel 略差、dual_fp_rel 略好的 trade-off。
3. B 的效果目前证据较弱，需要非零 warm start 设计后再评价。

更准确的表述是：**C 是一个有实验支持的稳定性改进，但需要调参和更多 benchmark 才能判断它是否提升完整算法的总体性能；B 是理论合理的 warm-start 初始化推广，目前证据不足。**
