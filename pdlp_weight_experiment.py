from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy import sparse


@dataclass
class MpsLp:
    name: str
    A: sparse.csr_matrix
    b: np.ndarray
    c: np.ndarray
    lb: np.ndarray
    ub: np.ndarray
    row_types: np.ndarray
    row_names: list[str]
    col_names: list[str]


def _pairs(tokens: list[str]) -> Iterable[tuple[str, float]]:
    for i in range(0, len(tokens), 2):
        yield tokens[i], float(tokens[i + 1])


def read_mps(path: Path) -> MpsLp:
    """Read the subset of free-format MPS needed by the experiment benchmark."""
    name = path.stem
    section = None
    objective_row = None
    row_names: list[str] = []
    row_types: list[str] = []
    row_index: dict[str, int] = {}
    col_names: list[str] = []
    col_index: dict[str, int] = {}
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    c_values: dict[int, float] = {}
    rhs_values: dict[int, float] = {}
    bound_records: list[tuple[str, str, float | None]] = []

    def get_col(var_name: str) -> int:
        idx = col_index.get(var_name)
        if idx is None:
            idx = len(col_names)
            col_index[var_name] = idx
            col_names.append(var_name)
        return idx

    with path.open("r", errors="ignore") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped or stripped.startswith("*"):
                continue
            tokens = stripped.split()
            head = tokens[0]
            if head == "NAME":
                name = tokens[1] if len(tokens) > 1 else name
                section = "NAME"
                continue
            if head in {"ROWS", "COLUMNS", "RHS", "RANGES", "BOUNDS", "ENDATA"}:
                section = head
                continue

            if section == "ROWS":
                row_type, row_name = tokens[0], tokens[1]
                if row_type == "N":
                    objective_row = row_name
                    continue
                row_index[row_name] = len(row_names)
                row_names.append(row_name)
                row_types.append(row_type)
            elif section == "COLUMNS":
                col = get_col(tokens[0])
                for row_name, value in _pairs(tokens[1:]):
                    if row_name == objective_row:
                        c_values[col] = c_values.get(col, 0.0) + value
                    else:
                        r = row_index[row_name]
                        rows.append(r)
                        cols.append(col)
                        data.append(value)
            elif section == "RHS":
                for row_name, value in _pairs(tokens[1:]):
                    if row_name != objective_row:
                        rhs_values[row_index[row_name]] = value
            elif section == "RANGES":
                raise ValueError("RANGES section is not supported by this experiment parser.")
            elif section == "BOUNDS":
                kind = tokens[0]
                var_name = tokens[2]
                value = float(tokens[3]) if len(tokens) > 3 else None
                get_col(var_name)
                bound_records.append((kind, var_name, value))

    m = len(row_names)
    n = len(col_names)
    c = np.zeros(n)
    for j, value in c_values.items():
        c[j] = value
    b = np.zeros(m)
    for i, value in rhs_values.items():
        b[i] = value

    lb = np.zeros(n)
    ub = np.full(n, np.inf)
    for kind, var_name, value in bound_records:
        j = col_index[var_name]
        if kind == "LO":
            lb[j] = float(value)
        elif kind == "UP":
            ub[j] = float(value)
        elif kind == "FX":
            lb[j] = ub[j] = float(value)
        elif kind == "FR":
            lb[j] = -np.inf
            ub[j] = np.inf
        elif kind == "MI":
            lb[j] = -np.inf
        elif kind == "PL":
            ub[j] = np.inf
        elif kind == "BV":
            lb[j] = 0.0
            ub[j] = 1.0
        else:
            raise ValueError(f"Unsupported bound kind {kind!r}")

    A = sparse.coo_matrix((data, (rows, cols)), shape=(m, n)).tocsr()
    return MpsLp(
        name=name,
        A=A,
        b=b,
        c=c,
        lb=lb,
        ub=ub,
        row_types=np.asarray(row_types),
        row_names=row_names,
        col_names=col_names,
    )


def project_box(x: np.ndarray, lb: np.ndarray, ub: np.ndarray) -> np.ndarray:
    return np.minimum(np.maximum(x, lb), ub)


def estimate_operator_norm(A: sparse.csr_matrix, seed: int, iterations: int) -> float:# 估计矩阵范数
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(A.shape[1])
    v /= np.linalg.norm(v)
    sigma = 0.0
    for _ in range(iterations):
        Av = A @ v
        sigma = float(np.linalg.norm(Av))
        if sigma == 0.0:
            return 0.0
        v = A.T @ Av
        norm_v = np.linalg.norm(v)
        if norm_v == 0.0:
            return 0.0
        v /= norm_v
    return sigma


@dataclass(frozen=True)
class Variant:
    name: str
    pilot_init: bool
    truncated_update: bool


def weighted_distance( # 论文中带权距离
    x_a: np.ndarray,
    y_a: np.ndarray,
    x_b: np.ndarray,
    y_b: np.ndarray,
    omega: float,
) -> float:
    dx = x_a - x_b
    dy = y_a - y_b
    return math.sqrt(omega * float(dx @ dx) + (1.0 / omega) * float(dy @ dy))


def _bounded_ball_linear_max( # 解duality gap中的最大化问题，KKT+二分近似求解（见README)
    blocks: list[tuple[np.ndarray, np.ndarray, np.ndarray, float]],
    radius: float,
    iterations: int = 50, #默认迭代50次
) -> float:
    """Maximize a linear form over box constraints and a weighted Euclidean ball."""
    if radius <= 0.0 or not math.isfinite(radius):
        return 0.0

    def norm_sq(lambda_value: float) -> float:
        total = 0.0
        for gradient, lower, upper, weight in blocks:
            step = gradient / (2.0 * lambda_value * weight)
            step = np.minimum(np.maximum(step, lower), upper)
            total += weight * float(step @ step)
        return total

    high = 1.0
    radius_sq = radius * radius
    while norm_sq(high) > radius_sq:
        high *= 2.0
        if high > 1e300:
            break

    low = 0.0
    for _ in range(iterations):
        mid = 0.5 * (low + high)
        if mid == 0.0 or norm_sq(mid) > radius_sq:
            low = mid
        else:
            high = mid

    value = 0.0
    for gradient, lower, upper, weight in blocks:
        step = gradient / (2.0 * high * weight)
        step = np.minimum(np.maximum(step, lower), upper)
        value += float(gradient @ step)
    return value


def run_variant(
    lp: MpsLp,
    variant: Variant,
    eta: float,
    max_iter: int,
    restart_every: int,
    restart_mode: str,
    restart_check_frequency: int,
    beta_sufficient: float,
    beta_necessary: float,
    beta_artificial: float,
    log_every: int,
    theta: float,
    truncate_log: float,
    eps_zero: float,
) -> list[dict[str, float | int | str]]:
    A = lp.A
    c = lp.c
    b = lp.b
    lb = lp.lb
    ub = lp.ub
    is_less = lp.row_types == "L"
    is_equal = lp.row_types == "E"
    is_greater = lp.row_types == "G"
    sign = np.ones(A.shape[0])
    sign[is_less] = -1.0
    q = sign * b

    def kt_y(y: np.ndarray) -> np.ndarray:
        return A.T @ (sign * y)

    def k_x(x: np.ndarray) -> np.ndarray:
        return sign * (A @ x)

    def project_y(y: np.ndarray) -> np.ndarray:
        y = y.copy()
        y[is_less] = np.maximum(y[is_less], 0.0)
        y[is_greater] = np.maximum(y[is_greater], 0.0)
        return y

    y_lower = np.full(A.shape[0], -np.inf)
    y_lower[is_less] = 0.0
    y_lower[is_greater] = 0.0
    y_upper = np.full(A.shape[0], np.inf)

    def weight_init(x0: np.ndarray, y0: np.ndarray) -> float:
        if variant.pilot_init:
            numerator = np.linalg.norm(c - kt_y(y0))
            denominator = np.linalg.norm(q - k_x(x0))
            if numerator > eps_zero and denominator > eps_zero:
                return numerator / denominator
            return 1.0
        norm_c = np.linalg.norm(c)
        norm_q = np.linalg.norm(q)
        if norm_c > eps_zero and norm_q > eps_zero:
            return norm_c / norm_q
        return 1.0

    x = project_box(np.zeros_like(c), lb, ub)
    y = np.zeros(A.shape[0])
    omega = weight_init(x, y)
    x_restart = x.copy()
    y_restart = y.copy()
    x_previous_restart: np.ndarray | None = None
    y_previous_restart: np.ndarray | None = None
    reference_gap = math.inf
    previous_candidate_gap = math.inf
    restart_count = 0
    average_weight = 0.0
    x_average_sum = np.zeros_like(x)
    y_average_sum = np.zeros_like(y)
    rows_out: list[dict[str, float | int | str]] = []
    t0 = time.perf_counter()

    b_less = b[is_less]
    b_equal = b[is_equal]
    b_greater = b[is_greater]
    b_norm = math.sqrt(float(b_less @ b_less) + float(b_equal @ b_equal) + float(b_greater @ b_greater))

    def record(iteration: int) -> None:
        Ax = A @ x
        less_violation = np.maximum(Ax[is_less] - b_less, 0.0)
        eq_violation = Ax[is_equal] - b_equal
        greater_violation = np.maximum(b_greater - Ax[is_greater], 0.0)
        primal_l2 = math.sqrt(
            float(less_violation @ less_violation)
            + float(eq_violation @ eq_violation)
            + float(greater_violation @ greater_violation)
        )
        grad = c - kt_y(y)
        dual_fixed_point = np.linalg.norm(x - project_box(x - grad, lb, ub))
        rows_out.append(
            {
                "variant": variant.name,
                "iter": iteration,
                "objective": float(c @ x),
                "primal_l2": primal_l2,
                "primal_rel": primal_l2 / (1.0 + b_norm),
                "dual_fp_rel": float(dual_fixed_point / (1.0 + np.linalg.norm(x))),
                "omega": float(omega),
                "restart_count": restart_count,
                "elapsed_sec": time.perf_counter() - t0,
            }
        )

    def normalized_duality_gap(x_gap: np.ndarray, y_gap: np.ndarray, x_ref: np.ndarray, y_ref: np.ndarray) -> float:
        radius = weighted_distance(x_gap, y_gap, x_ref, y_ref, omega)
        if radius <= eps_zero or not math.isfinite(radius):
            return math.inf
        Ax_gap = A @ x_gap
        primal_gradient = kt_y(y_gap) - c
        dual_gradient = q - sign * Ax_gap
        value = _bounded_ball_linear_max(
            [
                (primal_gradient, lb - x_gap, ub - x_gap, omega),
                (dual_gradient, y_lower - y_gap, y_upper - y_gap, 1.0 / omega),
            ],
            radius,
        )
        return value / radius

    def update_weight_from_restart_candidate(x_candidate: np.ndarray, y_candidate: np.ndarray) -> None:
        nonlocal omega
        delta_x = float(np.linalg.norm(x_candidate - x_restart))
        delta_y = float(np.linalg.norm(y_candidate - y_restart))
        if math.isfinite(delta_x) and math.isfinite(delta_y) and delta_x > eps_zero and delta_y > eps_zero:
            ratio = delta_y / delta_x
            if not math.isfinite(ratio) or ratio <= 0.0:
                return
            log_target = math.log(ratio)
            log_omega = math.log(omega)
            raw_delta = theta * (log_target - log_omega)
            if variant.truncated_update:
                raw_delta = min(max(raw_delta, -truncate_log), truncate_log)
            omega = math.exp(log_omega + raw_delta)

    def adaptive_restart_if_needed(iteration: int, inner_iteration: int) -> tuple[bool, int]:
        nonlocal restart_count
        nonlocal x, y, x_restart, y_restart, x_previous_restart, y_previous_restart
        nonlocal reference_gap, previous_candidate_gap, average_weight, x_average_sum, y_average_sum
        if restart_check_frequency <= 0 or iteration % restart_check_frequency != 0 or inner_iteration <= 0:
            return False, inner_iteration

        x_average = x_average_sum / average_weight
        y_average = y_average_sum / average_weight
        current_gap = normalized_duality_gap(x, y, x_restart, y_restart)
        average_gap = normalized_duality_gap(x_average, y_average, x_restart, y_restart)
        if average_gap <= current_gap:
            x_candidate = x_average
            y_candidate = y_average
            candidate_gap = average_gap
        else:
            x_candidate = x
            y_candidate = y
            candidate_gap = current_gap

        sufficient = candidate_gap <= beta_sufficient * reference_gap
        necessary = candidate_gap <= beta_necessary * reference_gap and candidate_gap > previous_candidate_gap
        artificial = inner_iteration >= beta_artificial * iteration
        previous_candidate_gap = candidate_gap

        if not (sufficient or necessary or artificial):
            return False, inner_iteration

        old_x_restart = x_restart
        old_y_restart = y_restart
        update_weight_from_restart_candidate(x_candidate, y_candidate)
        x = x_candidate.copy()
        y = y_candidate.copy()
        x_previous_restart = old_x_restart
        y_previous_restart = old_y_restart
        x_restart = x.copy()
        y_restart = y.copy()
        restart_count += 1
        if x_previous_restart is None or y_previous_restart is None:
            reference_gap = math.inf
        else:
            reference_gap = normalized_duality_gap(x_restart, y_restart, x_previous_restart, y_previous_restart)
        previous_candidate_gap = math.inf
        average_weight = 0.0
        x_average_sum = np.zeros_like(x)
        y_average_sum = np.zeros_like(y)
        return True, 0

    record(0)
    inner_iteration = 0
    for iteration in range(1, max_iter + 1):
        grad_x = c - kt_y(y)
        x_next = project_box(x - (eta / omega) * grad_x, lb, ub)
        extrapolated = 2.0 * x_next - x
        y_next = project_y(y + eta * omega * (q - k_x(extrapolated)))
        x = x_next
        y = y_next
        inner_iteration += 1
        if restart_mode == "adaptive":
            average_weight += eta
            x_average_sum += eta * x
            y_average_sum += eta * y

        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or not math.isfinite(omega):
            record(iteration)
            break

        if restart_mode == "fixed" and restart_every > 0 and iteration % restart_every == 0:
            update_weight_from_restart_candidate(x, y)
            x_restart = x.copy()
            y_restart = y.copy()
            restart_count += 1
        elif restart_mode == "adaptive":
            restarted, inner_iteration = adaptive_restart_if_needed(iteration, inner_iteration)

        if iteration % log_every == 0 or iteration == max_iter:
            record(iteration)
    return rows_out


def summarize_problem(lp: MpsLp) -> dict[str, float | int | str]:
    row_types, row_counts = np.unique(lp.row_types, return_counts=True)
    finite_ub = np.isfinite(lp.ub)
    finite_lb = np.isfinite(lp.lb)
    return {
        "name": lp.name,
        "rows": int(lp.A.shape[0]),
        "cols": int(lp.A.shape[1]),
        "nnz": int(lp.A.nnz),
        "row_type_counts": {str(k): int(v) for k, v in zip(row_types, row_counts)},
        "c_norm": float(np.linalg.norm(lp.c)),
        "b_norm": float(np.linalg.norm(lp.b)),
        "rhs_nonzero": int(np.count_nonzero(lp.b)),
        "finite_lower_bounds": int(np.count_nonzero(finite_lb)),
        "finite_upper_bounds": int(np.count_nonzero(finite_ub)),
    }


def safe_problem_id(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mps", type=Path, default=Path(r"C:\Users\ASUS\Desktop\ex10.mps"))
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--max-iter", type=int, default=2000)
    parser.add_argument("--restart-mode", choices=["fixed", "adaptive"], default="fixed")
    parser.add_argument("--restart-every", type=int, default=100)
    parser.add_argument("--restart-check-frequency", type=int, default=40)
    parser.add_argument("--beta-sufficient", type=float, default=0.9)
    parser.add_argument("--beta-necessary", type=float, default=0.1)
    parser.add_argument("--beta-artificial", type=float, default=0.5)
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--theta", type=float, default=0.5)
    parser.add_argument("--truncate-factor", type=float, default=2.0)
    parser.add_argument("--eps-zero", type=float, default=1e-12)
    parser.add_argument("--norm-iters", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    lp = read_mps(args.mps)
    problem_id = safe_problem_id(args.mps)
    sigma = estimate_operator_norm(lp.A, args.seed, args.norm_iters)
    eta = 0.9 / sigma
    variants = [
        Variant("baseline", pilot_init=False, truncated_update=False),
        Variant("B_only", pilot_init=True, truncated_update=False),
        Variant("C_only", pilot_init=False, truncated_update=True),
        Variant("B_plus_C", pilot_init=True, truncated_update=True),
    ]

    all_rows: list[dict[str, float | int | str]] = []
    for variant in variants:
        print(f"running {variant.name} ...", flush=True)
        all_rows.extend(
            run_variant(
                lp=lp,
                variant=variant,
                eta=eta,
                max_iter=args.max_iter,
                restart_every=args.restart_every,
                restart_mode=args.restart_mode,
                restart_check_frequency=args.restart_check_frequency,
                beta_sufficient=args.beta_sufficient,
                beta_necessary=args.beta_necessary,
                beta_artificial=args.beta_artificial,
                log_every=args.log_every,
                theta=args.theta,
                truncate_log=math.log(args.truncate_factor),
                eps_zero=args.eps_zero,
            )
        )

    csv_path = args.out_dir / f"pdlp_weight_{problem_id}_history.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    meta = {
        "problem": summarize_problem(lp),
        "operator_norm_estimate": sigma,
        "eta": eta,
        "max_iter": args.max_iter,
        "restart_mode": args.restart_mode,
        "restart_every": args.restart_every,
        "restart_check_frequency": args.restart_check_frequency,
        "beta_sufficient": args.beta_sufficient,
        "beta_necessary": args.beta_necessary,
        "beta_artificial": args.beta_artificial,
        "log_every": args.log_every,
        "theta": args.theta,
        "truncate_factor": args.truncate_factor,
        "eps_zero": args.eps_zero,
        "norm_iters": args.norm_iters,
        "seed": args.seed,
        "csv": str(csv_path),
    }
    meta_path = args.out_dir / f"pdlp_weight_{problem_id}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))

    final_rows = []
    for variant in variants:
        variant_rows = [row for row in all_rows if row["variant"] == variant.name]
        if variant_rows:
            final_rows.append(variant_rows[-1])
    print("\nfinal:")
    for row in final_rows:
        print(
            f"{row['variant']:10s} obj={row['objective']:.6g} "
            f"prim_rel={row['primal_rel']:.6g} dual_fp_rel={row['dual_fp_rel']:.6g} "
            f"omega={row['omega']:.6g} elapsed={row['elapsed_sec']:.2f}s"
        )


if __name__ == "__main__":
    main()
