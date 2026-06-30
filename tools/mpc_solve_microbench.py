#!/usr/bin/env python3
"""MPC 求解器微基准 - 台架确定性 solve_time 测量。

直接构造 algorithm/auv_mpc_controller.py 的 AUVMPCOptimizer，对一段典型
setpoint 轨迹反复调用 solve()，用 perf_counter 统计 mean/p50/p95/max，并对比
cold-start（每次重置初值）与 warm-start（携带上一步最优控制序列）两种工况。

这条"台架确定数值"与系统级 analyze_bag 抽取的闭环 solve_time 互为独立佐证，
共同消除论文 05 章"0ms 求解非线性优化"的硬伤。

用法：
  python3 tools/mpc_solve_microbench.py            # 默认 N=200，读 brain_linux/config/params.yaml
  python3 tools/mpc_solve_microbench.py --iters 500 --output-dir ./bench
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))
from common.env_utils import get_output_dir  # noqa: E402

DEFAULT_PARAMS = PROJECT_ROOT / "brain_linux" / "config" / "params.yaml"


def load_mpc_classes():
    """从 algorithm/auv_mpc_controller.py 动态加载求解器类（与 brain 包一致）。"""
    module_path = PROJECT_ROOT / "algorithm" / "auv_mpc_controller.py"
    spec = importlib.util.spec_from_file_location("auv_algorithm_mpc_bench", str(module_path))
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载 MPC 模块: {module_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.AUVMPCOptimizer, mod.AUVKinematicsModel


def load_params(params_path: Path) -> dict:
    if not params_path.exists():
        raise SystemExit(f"params.yaml not found: {params_path}")
    with params_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    if not isinstance(cfg, dict):
        raise SystemExit(f"Unexpected params.yaml structure: {params_path}")
    return cfg


def constant_reference(x0: np.ndarray, heading: float, depth: float, speed: float, n: int, dt: float) -> np.ndarray:
    """复刻 mpc_controller._build_constant_reference_trajectory 的恒定参考。"""
    ref = np.zeros((6, n + 1), dtype=np.float64)
    for k in range(n + 1):
        t_k = k * dt
        ref[0, k] = x0[0] + speed * math.cos(heading) * t_k
        ref[1, k] = x0[1] + speed * math.sin(heading) * t_k
        ref[2, k] = depth
        ref[3, k] = heading
        ref[4, k] = speed
        ref[5, k] = 0.0
    return ref


def build_problem_sequence(
    *,
    iters: int,
    n: int,
    dt: float,
    target_depth: float,
    target_heading: float,
    target_speed: float,
    start_depth: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """生成一段典型下潜+前进轨迹的 (x0, ref) 序列，cold/warm 共用同一序列以公平对比。"""
    problems: list[tuple[np.ndarray, np.ndarray]] = []
    x, y, z = 0.0, 0.0, start_depth
    psi, u, w = target_heading, target_speed, 0.0
    for _ in range(iters):
        x0 = np.array([x, y, z, psi, u, w], dtype=np.float64)
        ref = constant_reference(x0, target_heading, target_depth, target_speed, n, dt)
        problems.append((x0, ref))
        # 一阶推进：位置随航向前移，深度向目标缓慢收敛（典型闭环步进）。
        x += target_speed * math.cos(psi) * dt
        y += target_speed * math.sin(psi) * dt
        z += 0.3 * (target_depth - z) * dt
    return problems


def reset_cold_initial(optimizer, x0: np.ndarray, n: int) -> None:
    """把决策变量初值重置为中性猜测，确保 cold-start 不沿用上一次的解。"""
    optimizer.opti.set_initial(optimizer.X, np.tile(x0.reshape(-1, 1), (1, n + 1)))
    optimizer.opti.set_initial(optimizer.U, np.zeros((optimizer.N_CONTROLS, n)))


def run_mode(
    optimizer,
    problems: list[tuple[np.ndarray, np.ndarray]],
    *,
    confidence: float,
    warm: bool,
    n: int,
) -> dict:
    """运行一种工况，返回每次求解的耗时与状态。"""
    wall_ms: list[float] = []
    ipopt_ms: list[float] = []
    statuses: list[str] = []
    sources: list[str] = []
    prev_U = None

    for x0, ref in problems:
        if not warm:
            reset_cold_initial(optimizer, x0, n)
            warm_start_U = None
        else:
            warm_start_U = prev_U

        t0 = perf_counter()
        try:
            result = optimizer.solve(x0, ref, confidence, warm_start_U=warm_start_U)
        except RuntimeError as exc:
            wall_ms.append((perf_counter() - t0) * 1000.0)
            ipopt_ms.append(float("nan"))
            statuses.append(f"FAILED: {exc}")
            sources.append("failed")
            prev_U = None
            continue
        wall_ms.append((perf_counter() - t0) * 1000.0)
        ipopt_ms.append(float(result.get("solve_time_ms", float("nan"))))
        statuses.append(str(result.get("solver_status", "unknown")))
        sources.append(str(result.get("solve_time_source", "unknown")))
        prev_U = result.get("U_opt") if warm else prev_U

    return {
        "wall_ms": wall_ms,
        "ipopt_ms": ipopt_ms,
        "statuses": statuses,
        "sources": sources,
    }


def stats(values: list[float]) -> dict:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return {"count": 0, "mean": float("nan"), "p50": float("nan"), "p95": float("nan"), "max": float("nan")}
    arr = np.asarray(finite, dtype=float)
    return {
        "count": len(finite),
        "mean": float(arr.mean()),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(arr.max()),
    }


def write_summary_csv(path: Path, summary_rows: list[dict]) -> None:
    fieldnames = [
        "mode",
        "timing_source",
        "sample_count",
        "mean_ms",
        "p50_ms",
        "p95_ms",
        "max_ms",
        "success_ratio",
        "dominant_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)


def write_raw_csv(path: Path, mode: str, result: dict) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["mode", "iter", "wall_ms", "ipopt_ms", "solver_status", "timing_source"])
        for i, (wall, ipopt, status, source) in enumerate(
            zip(result["wall_ms"], result["ipopt_ms"], result["statuses"], result["sources"])
        ):
            writer.writerow([mode, i, f"{wall:.4f}", f"{ipopt:.4f}", status, source])


def plot_histogram(path: Path, cold: dict, warm: dict, *, dpi: int) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cold_wall = [v for v in cold["wall_ms"] if math.isfinite(v)]
    warm_wall = [v for v in warm["wall_ms"] if math.isfinite(v)]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bins = 30
    ax.hist(cold_wall, bins=bins, alpha=0.55, label=f"cold-start (mean {np.mean(cold_wall):.2f} ms)", color="#c0392b")
    ax.hist(warm_wall, bins=bins, alpha=0.55, label=f"warm-start (mean {np.mean(warm_wall):.2f} ms)", color="#2471a3")
    ax.set_xlabel("Solve wall time (ms)")
    ax.set_ylabel("Count")
    ax.set_title("MPC solve-time microbenchmark (perf_counter wall)")
    ax.legend()
    ax.grid(True, alpha=0.35, linestyle="--")
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)


def success_ratio(statuses: list[str]) -> float:
    if not statuses:
        return float("nan")
    ok = sum(1 for s in statuses if s in ("Solve_Succeeded", "Search_Direction_Becomes_Too_Small"))
    return ok / len(statuses)


def dominant_status(statuses: list[str]) -> str:
    if not statuses:
        return "none"
    counts: dict[str, int] = {}
    for s in statuses:
        counts[s] = counts.get(s, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--params", type=Path, default=DEFAULT_PARAMS, help="params.yaml path for MPC config.")
    parser.add_argument("--iters", type=int, default=200, help="Number of solve() calls per mode.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory (default: data_root/results/mpc_solve_microbench/<ts>).")
    parser.add_argument("--target-depth", type=float, default=3.0, help="Target depth setpoint (m, NED +down).")
    parser.add_argument(
        "--start-depth",
        type=float,
        default=3.0,
        help=(
            "Initial depth (m). Default 3.0 = steady cruise at target (feasible, "
            "clean solve-time headline). Set e.g. 8.0 to stress band/rate "
            "constraints and reproduce constraint-driven solver fallback."
        ),
    )
    parser.add_argument("--target-heading", type=float, default=0.0, help="Target heading (rad).")
    parser.add_argument("--target-speed", type=float, default=1.0, help="Target surge speed (m/s).")
    parser.add_argument("--confidence", type=float, default=1.0, help="Sensor confidence [0,1].")
    parser.add_argument("--dpi", type=int, default=200, help="Histogram DPI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    AUVMPCOptimizer, AUVKinematicsModel = load_mpc_classes()
    cfg = load_params(args.params)

    model_cfg = cfg.get("mpc_model", {})
    weights_cfg = cfg.get("mpc_weights", {})
    constraints_cfg = cfg.get("mpc_constraints", {})
    mpc_cfg = cfg.get("mpc", {})
    n = int(mpc_cfg.get("prediction_horizon", 20))
    dt = float(mpc_cfg.get("dt", 0.2))

    print(f"[microbench] N={n} dt={dt} iters={args.iters} params={args.params}")

    kinematics = AUVKinematicsModel(model_cfg)
    optimizer = AUVMPCOptimizer(kinematics, N=n, dt=dt, weights=weights_cfg, constraints=constraints_cfg)

    problems = build_problem_sequence(
        iters=args.iters,
        n=n,
        dt=dt,
        target_depth=args.target_depth,
        target_heading=args.target_heading,
        target_speed=args.target_speed,
        start_depth=args.start_depth,
    )

    # 预热一次（JIT/缓存），不计入统计；首问若不可行不应中断基准。
    try:
        optimizer.solve(problems[0][0], problems[0][1], args.confidence, warm_start_U=None)
    except RuntimeError as exc:
        print(f"[microbench] warm-up solve infeasible (ignored): {exc}")

    print("[microbench] running cold-start ...")
    cold = run_mode(optimizer, problems, confidence=args.confidence, warm=False, n=n)
    print("[microbench] running warm-start ...")
    warm = run_mode(optimizer, problems, confidence=args.confidence, warm=True, n=n)

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = get_output_dir("results/mpc_solve_microbench")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict] = []
    for mode, result in (("cold", cold), ("warm", warm)):
        for src_label, key in (("wall_perf_counter", "wall_ms"), ("solver_internal", "ipopt_ms")):
            s = stats(result[key])
            summary_rows.append(
                {
                    "mode": mode,
                    "timing_source": src_label,
                    "sample_count": s["count"],
                    "mean_ms": f"{s['mean']:.4f}",
                    "p50_ms": f"{s['p50']:.4f}",
                    "p95_ms": f"{s['p95']:.4f}",
                    "max_ms": f"{s['max']:.4f}",
                    "success_ratio": f"{success_ratio(result['statuses']):.4f}",
                    "dominant_status": dominant_status(result["statuses"]),
                }
            )

    summary_path = output_dir / "mpc_solve_microbench_summary.csv"
    write_summary_csv(summary_path, summary_rows)
    write_raw_csv(output_dir / "mpc_solve_microbench_cold_raw.csv", "cold", cold)
    write_raw_csv(output_dir / "mpc_solve_microbench_warm_raw.csv", "warm", warm)
    hist_path = output_dir / "mpc_solve_microbench_hist.png"
    plot_histogram(hist_path, cold, warm, dpi=args.dpi)

    print(f"[microbench] summary -> {summary_path}")
    print(f"[microbench] histogram -> {hist_path}")
    for row in summary_rows:
        print(
            f"  {row['mode']:>4} {row['timing_source']:>16}  "
            f"mean={row['mean_ms']}ms p50={row['p50_ms']}ms p95={row['p95_ms']}ms "
            f"max={row['max_ms']}ms n={row['sample_count']} ok={row['success_ratio']} "
            f"status={row['dominant_status']}"
        )


if __name__ == "__main__":
    main()
