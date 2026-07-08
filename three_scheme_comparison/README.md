# Three Scheme Comparison Package

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
