# fixed_log2 构建说明

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
