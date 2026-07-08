#!/usr/bin/env python3
"""Generate comparison tables and report for the three-scheme experiment."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"
DERIVED = ROOT / "results" / "derived"


def read_csv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["benchmark"]: row for row in csv.DictReader(handle)}


SCHEMES = {
    "baseline": read_csv(RAW / "baseline_all26_runs.csv"),
    "fixed_log2": read_csv(RAW / "fixed_log2_all26_runs.csv"),
    "signrate_selective": read_csv(RAW / "signrate_selective_clip_all26_runs.csv"),
}
ORDER = list(SCHEMES["baseline"].keys())


def num(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, ""))
    except Exception:
        return math.nan


def term(row: dict[str, str]) -> str:
    return row.get("summary:Termination Reason", "")


def fnum(value: float) -> str:
    if math.isnan(value):
        return ""
    if abs(value) >= 1000:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.3f}"
    if abs(value) >= 1:
        return f"{value:.4f}"
    return f"{value:.6g}"


def better_status(a: dict[str, str], b: dict[str, str]) -> int:
    ta, tb = term(a), term(b)
    if ta == tb:
        return 0
    if ta == "OPTIMAL" and tb != "OPTIMAL":
        return 1
    if ta != "OPTIMAL" and tb == "OPTIMAL":
        return -1
    return 0


def compare(a: dict[str, str], b: dict[str, str], metric: str) -> int:
    status = better_status(a, b)
    if status != 0:
        return status
    av = num(a, metric)
    bv = num(b, metric)
    if math.isnan(av) or math.isnan(bv):
        return 0
    if av < 0.995 * bv:
        return 1
    if av > 1.005 * bv:
        return -1
    return 0


def label(cmp_value: int) -> str:
    if cmp_value > 0:
        return "更好"
    if cmp_value < 0:
        return "更差"
    return "基本相同"


def pair_counts(a_name: str, b_name: str, metric: str) -> tuple[int, int, int]:
    wins = losses = ties = 0
    for benchmark in ORDER:
        cmp_value = compare(SCHEMES[a_name][benchmark], SCHEMES[b_name][benchmark], metric)
        if cmp_value > 0:
            wins += 1
        elif cmp_value < 0:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties


def generate_comparison_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for benchmark in ORDER:
        baseline = SCHEMES["baseline"][benchmark]
        fixed = SCHEMES["fixed_log2"][benchmark]
        signrate = SCHEMES["signrate_selective"][benchmark]
        rows.append(
            {
                "benchmark": benchmark,
                "baseline_status": term(baseline),
                "baseline_iterations": fnum(num(baseline, "summary:Iterations Count")),
                "baseline_runtime_sec": fnum(num(baseline, "summary:Runtime (sec)")),
                "baseline_primal_rel": fnum(num(baseline, "summary:Relative Primal Residual")),
                "baseline_dual_rel": fnum(num(baseline, "summary:Relative Dual Residual")),
                "baseline_gap_rel": fnum(num(baseline, "summary:Relative Objective Gap")),
                "fixed_log2_status": term(fixed),
                "fixed_log2_iterations": fnum(num(fixed, "summary:Iterations Count")),
                "fixed_log2_runtime_sec": fnum(num(fixed, "summary:Runtime (sec)")),
                "fixed_log2_primal_rel": fnum(num(fixed, "summary:Relative Primal Residual")),
                "fixed_log2_dual_rel": fnum(num(fixed, "summary:Relative Dual Residual")),
                "fixed_log2_gap_rel": fnum(num(fixed, "summary:Relative Objective Gap")),
                "signrate_status": term(signrate),
                "signrate_iterations": fnum(num(signrate, "summary:Iterations Count")),
                "signrate_runtime_sec": fnum(num(signrate, "summary:Runtime (sec)")),
                "signrate_primal_rel": fnum(num(signrate, "summary:Relative Primal Residual")),
                "signrate_dual_rel": fnum(num(signrate, "summary:Relative Dual Residual")),
                "signrate_gap_rel": fnum(num(signrate, "summary:Relative Objective Gap")),
                "signrate_applied_count": fnum(num(signrate, "summary:Dynamic Clip Applied Count")),
                "signrate_activation_count": fnum(num(signrate, "summary:Dynamic Clip Expand Count")),
                "signrate_max_abs_delta_log_omega": fnum(
                    num(signrate, "summary:Maximum Absolute Delta Log Omega")
                ),
                "signrate_delta_sign_change_rate": fnum(
                    num(signrate, "summary:Delta Log Omega Sign Change Rate")
                ),
                "fixed_vs_baseline_by_iterations": label(
                    compare(fixed, baseline, "summary:Iterations Count")
                ),
                "signrate_vs_baseline_by_iterations": label(
                    compare(signrate, baseline, "summary:Iterations Count")
                ),
                "signrate_vs_fixed_by_iterations": label(
                    compare(signrate, fixed, "summary:Iterations Count")
                ),
                "fixed_vs_baseline_by_runtime": label(compare(fixed, baseline, "summary:Runtime (sec)")),
                "signrate_vs_baseline_by_runtime": label(
                    compare(signrate, baseline, "summary:Runtime (sec)")
                ),
                "signrate_vs_fixed_by_runtime": label(compare(signrate, fixed, "summary:Runtime (sec)")),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate_summary_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name, data in SCHEMES.items():
        runtimes = [num(data[benchmark], "summary:Runtime (sec)") for benchmark in ORDER]
        gaps = [num(data[benchmark], "summary:Relative Objective Gap") for benchmark in ORDER]
        rows.append(
            {
                "scheme": name,
                "optimal_count": str(sum(1 for benchmark in ORDER if term(data[benchmark]) == "OPTIMAL")),
                "time_limit_count": str(
                    sum(1 for benchmark in ORDER if term(data[benchmark]) == "TIME_LIMIT")
                ),
                "iteration_limit_count": str(
                    sum(1 for benchmark in ORDER if term(data[benchmark]) == "ITERATION_LIMIT")
                ),
                "total_iterations": fnum(
                    sum(num(data[benchmark], "summary:Iterations Count") for benchmark in ORDER)
                ),
                "total_runtime_sec": fnum(sum(runtimes)),
                "median_runtime_sec": fnum(median(runtimes)),
                "mean_runtime_sec": fnum(mean(runtimes)),
                "mean_relative_gap": fnum(mean(gaps)),
            }
        )
    return rows


def generate_pair_rows() -> list[dict[str, str]]:
    pairs = [
        ("fixed_log2", "baseline"),
        ("signrate_selective", "baseline"),
        ("signrate_selective", "fixed_log2"),
    ]
    rows: list[dict[str, str]] = []
    for a_name, b_name in pairs:
        iw, il, it = pair_counts(a_name, b_name, "summary:Iterations Count")
        rw, rl, rt = pair_counts(a_name, b_name, "summary:Runtime (sec)")
        rows.append(
            {
                "scheme_a": a_name,
                "scheme_b": b_name,
                "iteration_wins": str(iw),
                "iteration_losses": str(il),
                "iteration_ties": str(it),
                "runtime_wins": str(rw),
                "runtime_losses": str(rl),
                "runtime_ties": str(rt),
            }
        )
    return rows


def write_report(
    comparison_rows: list[dict[str, str]],
    summary_rows: list[dict[str, str]],
    pair_rows: list[dict[str, str]],
) -> None:
    lines: list[str] = [
        "# 三方案 primal weight 更新实验报告",
        "",
        f"本报告只比较三个方案：`baseline`、`fixed_log2`、`signrate_selective`。所有数据来自当前工作目录内 {len(ORDER)} 个 benchmark 的 30 秒限制实验。",
        "",
        "## 方案定义",
        "",
        "- `baseline`：cuPDLPx 原始 primal weight 更新，保留论文/源码中的 movement/PID 更新。",
        "- `fixed_log2`：保留原始更新方向，但对每次 `Delta log omega` 做固定截断：`clip(Delta, -log(2), log(2))`。该版本通过 `CUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE=1` 编译。",
        "- `signrate_selective`：保留原始更新方向；只有当 `max |Delta log omega| >= log(10)` 且 `Delta log omega` 的符号翻转率 `>= 0.45` 时，才启用 `log2` 截断。",
        "",
        "## 实验设置",
        "",
        f"- benchmark 数量：{len(ORDER)}",
        "- time limit：30 秒",
        "- eval frequency：200",
        "- iter limit：100000000",
        "- 评价不只看单一指标：优先看终止状态，其次看迭代数和运行时间，同时观察 residual/gap 是否保持在可接受范围。",
        "",
        "## 总体统计",
        "",
        "| 方案 | OPTIMAL 数 | TIME_LIMIT 数 | ITERATION_LIMIT 数 | 总迭代数 | 总运行时间(s) | 中位运行时间(s) | 平均 relative gap |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['scheme']} | {row['optimal_count']} | {row['time_limit_count']} | "
            f"{row['iteration_limit_count']} | {row['total_iterations']} | {row['total_runtime_sec']} | {row['median_runtime_sec']} | "
            f"{row['mean_relative_gap']} |"
        )

    lines.extend(
        [
            "",
            "## 两两胜负统计",
            "",
            "| 对比 | 迭代数 胜/负/平 | 运行时间 胜/负/平 |",
            "|---|---:|---:|",
        ]
    )
    for row in pair_rows:
        lines.append(
            f"| {row['scheme_a']} vs {row['scheme_b']} | "
            f"{row['iteration_wins']}/{row['iteration_losses']}/{row['iteration_ties']} | "
            f"{row['runtime_wins']}/{row['runtime_losses']}/{row['runtime_ties']} |"
        )

    lines.extend(
        [
            "",
            "## 逐 benchmark 对比",
            "",
            "| benchmark | baseline 状态/迭代/时间 | fixed_log2 状态/迭代/时间 | signrate 状态/迭代/时间 | signrate applied | 主要观察 |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in comparison_rows:
        observations: list[str] = []
        if row["fixed_log2_status"] != "OPTIMAL" and row["signrate_status"] == "OPTIMAL":
            observations.append("signrate 避免 fixed_log2 未收敛")
        if row["signrate_vs_baseline_by_iterations"] == "更好":
            observations.append("signrate 迭代少于 baseline")
        if row["signrate_vs_fixed_by_iterations"] == "更好":
            observations.append("signrate 迭代少于 fixed_log2")
        if row["signrate_vs_fixed_by_iterations"] == "更差":
            observations.append("fixed_log2 迭代更少")
        if not observations:
            observations.append("整体接近 baseline")
        lines.append(
            f"| {row['benchmark']} | "
            f"{row['baseline_status']} / {row['baseline_iterations']} / {row['baseline_runtime_sec']} | "
            f"{row['fixed_log2_status']} / {row['fixed_log2_iterations']} / {row['fixed_log2_runtime_sec']} | "
            f"{row['signrate_status']} / {row['signrate_iterations']} / {row['signrate_runtime_sec']} | "
            f"{row['signrate_applied_count']} | {'；'.join(observations)} |"
        )

    lines.extend(
        [
            "",
            "## 结论",
            "",
            "在当前全量 benchmark 上，`signrate_selective` 是目前三者里更稳的方案。它比无条件 `fixed_log2` 更少出现大幅退化，同时保留了一部分固定截断带来的加速收益。",
            "",
            "固定 `log2` 截断说明“限制 omega 单次变化”确实有价值，但无条件截断会伤害需要单向大幅重平衡的 benchmark。`signrate_selective` 的优势在于只在大更新伴随高频正负翻转时介入，因此更像一个针对过冲/震荡的 safeguard，而不是全局替代原始权重更新。",
            "",
            "当前不足是该选择器仍偏保守：有些 fixed_log2 明显有收益的样例不会被充分激活。后续如果继续优化，建议只微调 `log(10)` 和 `0.45` 两个阈值，不建议改变整体算法结构。",
            "",
        ]
    )
    (ROOT / "experiment_report.md").write_text("\n".join(lines), encoding="utf-8")


def write_notes() -> None:
    readme = """# Three Scheme Comparison Package

本文件夹归档三个方案的代码入口、runner 和 all26 实验结果：

- `baseline`：cuPDLPx 原始 primal weight 更新。
- `fixed_log2`：固定 `[-log2, log2]` 截断。
- `signrate_selective`：当前选择性截断方案。

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
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")

    fixed_note = """# fixed_log2 构建说明

fixed_log2 使用 cuPDLPx 原始 `solver.cu` 中已有的条件编译分支：

```c
#if defined(CUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE) && CUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE
    const double max_log_weight_delta = clip_threshold;
    log_weight_delta = fmin(fmax(log_weight_delta, -max_log_weight_delta), max_log_weight_delta);
#endif
```

本次实验的 clipped build 通过 CUDA 编译参数启用：

```text
-DCUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE=1
```

完整 CMake 配置见本目录下的 `CMakeCache.txt`。
"""
    (ROOT / "code" / "fixed_log2" / "README.md").write_text(fixed_note, encoding="utf-8")


def main() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)
    comparison_rows = generate_comparison_rows()
    summary_rows = generate_summary_rows()
    pair_rows = generate_pair_rows()

    write_csv(DERIVED / "comparison_all26.csv", comparison_rows, list(comparison_rows[0].keys()))
    write_csv(DERIVED / "summary_metrics.csv", summary_rows, list(summary_rows[0].keys()))
    write_csv(DERIVED / "pairwise_counts.csv", pair_rows, list(pair_rows[0].keys()))
    write_report(comparison_rows, summary_rows, pair_rows)
    write_notes()


if __name__ == "__main__":
    main()
