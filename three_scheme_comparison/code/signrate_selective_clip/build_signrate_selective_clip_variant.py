#!/usr/bin/env python3
"""Build a sign-rate selective clipping variant without persistent edits.

This experiment keeps the original cuPDLPx movement/PID primal-weight update.
It only enables log(2) clipping after the observed raw Delta log omega sequence
shows both:

  1. a large update, max |Delta log omega| >= log(10), and
  2. frequent sign changes, sign-change rate >= 0.45.

The rule is motivated by the previous benchmark data: fixed log2 clipping
helped the cases with large oscillatory updates, while it hurt cases where the
weight moved mostly in one direction. The script patches cuPDLPx temporarily,
builds a separate runner, and restores the source file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MSVC_ROOT = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207")
MSVC_CL = MSVC_ROOT / "bin" / "Hostx64" / "x64" / "cl.exe"
SOLVER = Path("cuPDLPx-main/src/solver.cu")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build sign-rate selective clipping cuPDLPx runner.")
    parser.add_argument("--build-dir", default="cuPDLPx-main/build-ninja-release-sm120-dynamic-copy")
    parser.add_argument("--output-dir", default="tools/bin/signrate_selective_clip")
    parser.add_argument("--runner-name", default="cupdlpx_mps_runner_sm120_signrate_selective_clip.exe")
    parser.add_argument("--dry-run", action="store_true", help="Patch and restore without building.")
    return parser.parse_args()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Patch anchor not found: {label}")
    return text.replace(old, new, 1)


def patch_solver(text: str) -> str:
    old_block = """#if defined(CUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE) && CUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE
        const double max_log_weight_delta = clip_threshold;
        log_weight_delta = fmin(fmax(log_weight_delta, -max_log_weight_delta), max_log_weight_delta);
#elif defined(CUPDLPX_DYNAMIC_CLIP_PRIMAL_WEIGHT_UPDATE) && CUPDLPX_DYNAMIC_CLIP_PRIMAL_WEIGHT_UPDATE
        const int upper_hit = log_weight_delta > clip_threshold;
        const int lower_hit = log_weight_delta < -clip_threshold;
        state->dynamic_clip_upper_hit_mask = ((state->dynamic_clip_upper_hit_mask << 1) | upper_hit) & 0x7;
        state->dynamic_clip_lower_hit_mask = ((state->dynamic_clip_lower_hit_mask << 1) | lower_hit) & 0x7;

        double current_merit = fmax(state->relative_primal_residual, state->relative_dual_residual);
        current_merit = fmax(current_merit, state->relative_objective_gap);
        const bool has_current_merit = isfinite(current_merit) && current_merit > 0.0;

        if (state->dynamic_clip_observe_remaining > 0)
        {
            state->dynamic_clip_observe_remaining -= 1;
            if (state->dynamic_clip_observe_remaining == 0 && has_current_merit &&
                isfinite(state->dynamic_clip_observe_start_merit) &&
                state->dynamic_clip_observe_start_merit > 0.0)
            {
                const double progress =
                    (state->dynamic_clip_observe_start_merit - current_merit) /
                    state->dynamic_clip_observe_start_merit;
                if (progress >= 0.10)
                {
                    state->dynamic_clip_radius =
                        fmin(1.25 * state->dynamic_clip_radius, state->dynamic_clip_max_radius);
                    state->dynamic_clip_bad_streak = 0;
                    state->dynamic_clip_expand_count += 1;
                }
                else if (progress < 0.01)
                {
                    state->dynamic_clip_radius =
                        fmax(0.5 * state->dynamic_clip_radius, state->dynamic_clip_min_radius);
                    state->dynamic_clip_bad_streak += 1;
                    state->dynamic_clip_shrink_count += 1;
                    if (state->dynamic_clip_bad_streak >= 2)
                    {
                        state->dynamic_clip_cooldown = 3;
                        state->dynamic_clip_bad_streak = 0;
                        state->dynamic_clip_cooldown_count += 1;
                    }
                }
            }
        }
        if (state->dynamic_clip_cooldown > 0)
        {
            state->dynamic_clip_cooldown -= 1;
        }

        const bool has_merit_history = isfinite(state->dynamic_clip_last_merit) &&
            state->dynamic_clip_last_merit > 0.0 && has_current_merit;
        const bool poor_progress = has_merit_history && current_merit / state->dynamic_clip_last_merit > 0.9;
        const bool oscillating_large_update =
            state->dynamic_clip_upper_hit_mask != 0 && state->dynamic_clip_lower_hit_mask != 0;

        if (oscillating_large_update && poor_progress && state->dynamic_clip_cooldown == 0)
        {
            log_weight_delta =
                fmin(fmax(log_weight_delta, -state->dynamic_clip_radius), state->dynamic_clip_radius);
            state->dynamic_clip_applied_count += 1;
            if (state->dynamic_clip_observe_remaining == 0 && has_current_merit)
            {
                state->dynamic_clip_observe_start_merit = current_merit;
                state->dynamic_clip_observe_remaining = 2;
            }
        }
        state->dynamic_clip_last_merit = current_merit;
#endif
"""
    new_block = """#if defined(CUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE) && CUPDLPX_CLIP_PRIMAL_WEIGHT_UPDATE
        const double max_log_weight_delta = clip_threshold;
        log_weight_delta = fmin(fmax(log_weight_delta, -max_log_weight_delta), max_log_weight_delta);
#elif defined(CUPDLPX_DYNAMIC_CLIP_PRIMAL_WEIGHT_UPDATE) && CUPDLPX_DYNAMIC_CLIP_PRIMAL_WEIGHT_UPDATE
        const double raw_log_weight_delta = log_weight_delta;
        const double large_update_threshold = log(10.0);
        const double sign_rate_threshold = 0.45;
        const double sign_change_rate =
            state->weight_update_count > 1
                ? (double)state->delta_log_omega_sign_change_count /
                      (double)(state->weight_update_count - 1)
                : 0.0;

        if (state->dynamic_clip_observe_remaining == 0 &&
            state->weight_update_count >= 3 &&
            state->max_abs_delta_log_omega >= large_update_threshold &&
            sign_change_rate >= sign_rate_threshold)
        {
            state->dynamic_clip_observe_remaining = 1;
            state->dynamic_clip_expand_count += 1;
        }

        state->dynamic_clip_radius = clip_threshold;
        if (state->dynamic_clip_observe_remaining > 0 &&
            fabs(raw_log_weight_delta) > clip_threshold)
        {
            log_weight_delta = fmin(fmax(raw_log_weight_delta, -clip_threshold), clip_threshold);
            state->dynamic_clip_applied_count += 1;
        }
#endif
"""
    return replace_once(text, old_block, new_block, "dynamic clipping branch")


def make_build_env() -> dict[str, str]:
    env = os.environ.copy()
    sdk = Path(r"C:\Program Files (x86)\Windows Kits\10")
    sdk_version = "10.0.26100.0"
    cuda = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3")
    anaconda = Path(r"D:\anaconda\Library")

    prepend_path = [
        MSVC_ROOT / "bin" / "Hostx64" / "x64",
        cuda / "bin",
        cuda / "bin/x64",
    ]
    env["PATH"] = ";".join(str(path) for path in prepend_path) + ";" + env.get("PATH", "")
    env["INCLUDE"] = ";".join(
        [
            str(MSVC_ROOT / "include"),
            str(sdk / "Include" / sdk_version / "ucrt"),
            str(sdk / "Include" / sdk_version / "um"),
            str(sdk / "Include" / sdk_version / "shared"),
            str(sdk / "Include" / sdk_version / "winrt"),
            str(sdk / "Include" / sdk_version / "cppwinrt"),
        ]
    )
    env["LIB"] = ";".join(
        [
            str(MSVC_ROOT / "lib/x64"),
            str(sdk / "Lib" / sdk_version / "um/x64"),
            str(sdk / "Lib" / sdk_version / "ucrt/x64"),
            str(cuda / "lib/x64"),
            str(anaconda / "lib"),
        ]
    )
    return env


def run(command: list[str], env: dict[str, str]) -> None:
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def build_runner(args: argparse.Namespace, env: dict[str, str]) -> None:
    build_dir = Path(args.build_dir)
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run(["cmake", "--build", str(build_dir), "--config", "Release"], env)

    include_pslp = ROOT / "cuPDLPx-main/build-ninja-release-legacy-spmv/_deps/pslp-src/include"
    include_pslp_nested = include_pslp / "PSLP"
    runner_exe = output_dir / args.runner_name
    if not MSVC_CL.exists():
        raise FileNotFoundError(f"MSVC compiler not found: {MSVC_CL}")
    cl_command = [
        str(MSVC_CL),
        "/nologo",
        "/O2",
        "/MD",
        "/I",
        "cuPDLPx-main/include",
        "/I",
        "cuPDLPx-main/internal",
        "/I",
        str(include_pslp_nested),
        "/I",
        str(include_pslp),
        "tools/cupdlpx_mps_runner.c",
        "/link",
        f"/LIBPATH:{build_dir}",
        "cupdlpx.lib",
        f"/OUT:{runner_exe}",
    ]
    run(cl_command, env)

    shutil.copy2(ROOT / build_dir / "cupdlpx.dll", output_dir / "cupdlpx.dll")
    pslp_dll = ROOT / build_dir / "_deps/pslp-build/PSLP.dll"
    if not pslp_dll.exists():
        pslp_dll = ROOT / "tools/bin/dynamic/PSLP.dll"
    shutil.copy2(pslp_dll, output_dir / "PSLP.dll")
    zlib_dll = ROOT / "tools/bin/dynamic/zlib.dll"
    if zlib_dll.exists():
        shutil.copy2(zlib_dll, output_dir / "zlib.dll")


def main() -> int:
    args = parse_args()
    solver_path = ROOT / SOLVER
    original = solver_path.read_text(encoding="utf-8")
    try:
        solver_path.write_text(patch_solver(original), encoding="utf-8")
        if args.dry_run:
            print("Dry run succeeded; patches were applicable.")
            return 0
        build_runner(args, make_build_env())
        print(f"Sign-rate selective clipping runner written to {Path(args.output_dir) / args.runner_name}")
        return 0
    finally:
        solver_path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
