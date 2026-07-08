#!/usr/bin/env python3
"""Run cuPDLPx-style benchmark experiments without touching solver source.

This script is only an experiment driver:
  1. call an external solver executable/runner;
  2. keep each instance's output in a separate directory;
  3. parse *_summary.txt files when available;
  4. write aggregate CSV/JSON reports.

It does not import cuPDLPx, construct LP data, or modify files under src/include.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


SUMMARY_SUFFIX = "_summary.txt"


@dataclass
class RunRecord:
    benchmark: str
    benchmark_path: str
    output_dir: str
    command: list[str]
    return_code: int | None
    elapsed_seconds: float | None
    status: str
    summary_file: str | None
    summary: dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run benchmark files with an external cuPDLPx executable/runner."
    )
    parser.add_argument(
        "--solver",
        required=True,
        help="Path to the executable/runner, for example build/cupdlpx.exe.",
    )
    parser.add_argument(
        "--benchmarks",
        nargs="+",
        required=True,
        help="Benchmark files or directories. Directories are searched for .mps, .mps.gz, and .mps.bz2.",
    )
    parser.add_argument(
        "--output-root",
        default="outputs/cupdlpx_runs",
        help="Root directory for run outputs. Default: outputs/cupdlpx_runs.",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Optional run tag. Default: timestamp.",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=None,
        help="Optional --time_limit passed to the solver.",
    )
    parser.add_argument(
        "--iter-limit",
        type=int,
        default=None,
        help="Optional --iter_limit passed to the solver.",
    )
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Extra solver argument. Repeat this option for multiple arguments.",
    )
    parser.add_argument(
        "--runtime-path",
        action="append",
        default=[],
        help="Directory prepended to PATH when launching the solver. Repeat for multiple directories.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print and record commands without executing them.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running later benchmarks if one command fails.",
    )
    return parser.parse_args()


def iter_benchmarks(inputs: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        path = Path(item).expanduser()
        if path.is_dir():
            for pattern in ("*.mps", "*.mps.gz", "*.mps.bz2"):
                files.extend(path.rglob(pattern))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"Benchmark path does not exist: {path}")
    return sorted({p.resolve() for p in files})


def benchmark_stem(path: Path) -> str:
    name = path.name
    for suffix in (".mps.gz", ".mps.bz2", ".mps"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def make_command(
    solver: Path,
    benchmark: Path,
    output_dir: Path,
    time_limit: float | None,
    iter_limit: int | None,
    extra_args: list[str],
) -> list[str]:
    command = [str(solver)]
    if time_limit is not None:
        command.extend(["--time_limit", str(time_limit)])
    if iter_limit is not None:
        command.extend(["--iter_limit", str(iter_limit)])
    command.extend(extra_args)
    command.extend([str(benchmark), str(output_dir)])
    return command


def parse_summary(summary_path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not summary_path.exists():
        return data

    for raw_line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for sep in (":", "="):
            if sep in line:
                key, value = line.split(sep, 1)
                key = key.strip()
                value = value.strip()
                if key:
                    data[key] = value
                break
    return data


def find_summary(output_dir: Path) -> Path | None:
    candidates = sorted(output_dir.glob(f"*{SUMMARY_SUFFIX}"))
    return candidates[0] if candidates else None


def write_reports(records: list[RunRecord], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "runs.json"
    csv_path = report_dir / "runs.csv"

    json_path.write_text(
        json.dumps([asdict(record) for record in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary_keys = sorted({key for record in records for key in record.summary})
    fieldnames = [
        "benchmark",
        "benchmark_path",
        "status",
        "return_code",
        "elapsed_seconds",
        "output_dir",
        "summary_file",
    ] + [f"summary:{key}" for key in summary_keys]

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {
                "benchmark": record.benchmark,
                "benchmark_path": record.benchmark_path,
                "status": record.status,
                "return_code": record.return_code,
                "elapsed_seconds": record.elapsed_seconds,
                "output_dir": record.output_dir,
                "summary_file": record.summary_file,
            }
            row.update({f"summary:{key}": value for key, value in record.summary.items()})
            writer.writerow(row)


def make_run_env(solver: Path, runtime_paths: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    path_entries = [str(solver.parent)]
    path_entries.extend(str(Path(item).expanduser().resolve()) for item in runtime_paths)
    path_entries.append(env.get("PATH", ""))
    env["PATH"] = os.pathsep.join(path_entries)
    return env


def main() -> int:
    args = parse_args()
    solver = Path(args.solver).expanduser().resolve()
    if not solver.exists():
        print(f"Solver executable does not exist: {solver}", file=sys.stderr)
        return 2

    benchmarks = iter_benchmarks(args.benchmarks)
    if not benchmarks:
        print("No benchmark files found.", file=sys.stderr)
        return 2

    tag = args.tag or time.strftime("%Y%m%d-%H%M%S")
    run_root = Path(args.output_root).expanduser().resolve() / tag
    run_root.mkdir(parents=True, exist_ok=True)

    records: list[RunRecord] = []
    run_env = make_run_env(solver, args.runtime_path)
    for benchmark in benchmarks:
        name = benchmark_stem(benchmark)
        output_dir = run_root / name
        output_dir.mkdir(parents=True, exist_ok=True)
        command = make_command(
            solver=solver,
            benchmark=benchmark,
            output_dir=output_dir,
            time_limit=args.time_limit,
            iter_limit=args.iter_limit,
            extra_args=args.extra_arg,
        )

        print("Running:", " ".join(command))
        start = time.perf_counter()
        return_code: int | None = None
        status = "dry_run"
        if not args.dry_run:
            completed = subprocess.run(command, cwd=solver.parent, env=run_env)
            return_code = completed.returncode
            status = "ok" if return_code == 0 else "failed"
        elapsed = time.perf_counter() - start

        summary_file = find_summary(output_dir)
        summary = parse_summary(summary_file) if summary_file else {}
        record = RunRecord(
            benchmark=name,
            benchmark_path=str(benchmark),
            output_dir=str(output_dir),
            command=command,
            return_code=return_code,
            elapsed_seconds=round(elapsed, 6),
            status=status,
            summary_file=str(summary_file) if summary_file else None,
            summary=summary,
        )
        records.append(record)
        write_reports(records, run_root)

        if status == "failed" and not args.continue_on_error:
            print(f"Stopping after failed benchmark: {benchmark}", file=sys.stderr)
            return return_code or 1

    print(f"Reports written to: {run_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
