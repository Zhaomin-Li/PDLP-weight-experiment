# PDLP Primal Weight Experiments

This repository contains Python experiments for evaluating primal weight initialization and log-space truncation updates in a simplified PDHG/PDLP setting.

## Contents

- `pdlp_weight_experiment.py`: MPS parser and experiment runner.
- `experiment_summary.md`: Chinese experiment summary, benchmark notes, and conclusions.
- `results/`: CSV and JSON outputs for fixed restart, high-frequency restart, and adaptive restart experiments.

## Main Idea

The tested update limits the per-restart change in the primal weight:

```text
log omega_new = log omega_old
  + truncate(theta * (log(Delta_y / Delta_x) - log omega_old), -a_trunc, a_trunc)
```

The default setting uses `a_trunc = log 2`, so each restart changes `omega` by at most a factor of two.

## Example

```powershell
python .\pdlp_weight_experiment.py `
  --mps "C:\Users\ASUS\Desktop\brazil3.mps" `
  --restart-mode adaptive `
  --max-iter 5000 `
  --truncate-factor 2
```

## Notes

This is an experimental comparison script, not a full reproduction of the complete PDLP solver. See `experiment_summary.md` for details about which parts match the paper and which parts are simplified.

