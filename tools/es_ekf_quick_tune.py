#!/usr/bin/env python3
"""
ES-EKF 快速参数调优 - 针对关键参数进行高效搜索。

用法:
  python3 tools/es_ekf_quick_tune.py \
    --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output-dir ./tuning_results
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
SIM_DIR = PROJECT_ROOT / "sim_holoocean"
ALGO_DIR = PROJECT_ROOT / "algorithm"

for p in (str(TOOLS_DIR), str(SIM_DIR), str(ALGO_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

BASE_CONFIG = {
    "gravity": 9.81,
    "sigma_acc": 0.08,
    "sigma_gyro": 0.01,
    "sigma_ba": 0.001,
    "sigma_bg": 0.0005,
    "sigma_dvl": 0.03,
    "sigma_depth": 0.05,
    "imu_acc_is_linear": True,
    "init_pos": [0.0, 0.0, 0.0],
    "init_vel": [0.0, 0.0, 0.0],
    "init_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
    "init_ba": [0.0, 0.0, 0.0],
    "init_bg": [0.0, 0.0, 0.0],
    "init_P_diag": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.2, 0.2, 0.2, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05],
}


@dataclass
class TuningResult:
    params: dict
    rmse_xy: float
    rmse_z: float
    rmse_3d: float
    cep50: float
    max_drift: float
    latency_us: float
    elapsed_s: float


def build_config(overrides: dict = None) -> dict:
    cfg = copy.deepcopy(BASE_CONFIG)
    if overrides:
        cfg.update(overrides)
    return cfg


def run_single_eval(cfg, imu_samples, dvl_samples, depth_samples, truth_samples):
    import importlib
    import offline_ekf_benchmark as bm
    importlib.reload(bm)
    bm.ensure_runtime_dependencies()

    engine = bm.EseKfEngine(cfg)

    imu_ts = [s.ts_ns for s in imu_samples]
    dvl_ts = [s.ts_ns for s in dvl_samples]
    depth_ts = [s.ts_ns for s in depth_samples]
    truth_ts = [s.ts_ns for s in truth_samples]
    all_event_ts = sorted(set(imu_ts + dvl_ts + depth_ts + truth_ts))

    imu_idx = 0
    dvl_idx = 0
    depth_idx = 0
    last_imu_ts = None
    perf_times = []
    t_start = time.perf_counter()

    for event_ts in all_event_ts:
        while imu_idx < len(imu_samples) and imu_samples[imu_idx].ts_ns <= event_ts:
            imu = imu_samples[imu_idx]
            dt = (imu.ts_ns - last_imu_ts) / 1e9 if last_imu_ts is not None else 0.02
            last_imu_ts = imu.ts_ns
            t0 = time.perf_counter()
            engine.predict(imu.acc, imu.gyro, dt)
            perf_times.append(time.perf_counter() - t0)
            imu_idx += 1

        while dvl_idx < len(dvl_samples) and dvl_samples[dvl_idx].ts_ns <= event_ts:
            dvl = dvl_samples[dvl_idx]
            t0 = time.perf_counter()
            engine.update_dvl(dvl.vel, dvl.ts_ns)
            perf_times.append(time.perf_counter() - t0)
            dvl_idx += 1

        while depth_idx < len(depth_samples) and depth_samples[depth_idx].ts_ns <= event_ts:
            depth = depth_samples[depth_idx]
            t0 = time.perf_counter()
            engine.update_depth(depth.depth_m, depth.ts_ns)
            perf_times.append(time.perf_counter() - t0)
            depth_idx += 1

        if event_ts in truth_ts:
            engine.record_state(event_ts)

    elapsed = time.perf_counter() - t_start
    est_ts = np.array(engine.history_ts, dtype=np.int64)
    est_p = np.array(engine.history_p, dtype=float) if engine.history_p else np.empty((0, 3))

    if est_p.ndim != 2 or est_p.shape[0] < 2:
        return TuningResult(params=cfg, rmse_xy=float("nan"), rmse_z=float("nan"),
                           rmse_3d=float("nan"), cep50=float("nan"), max_drift=float("nan"),
                           latency_us=float("nan"), elapsed_s=elapsed)

    truth_ts_arr = np.array([s.ts_ns for s in truth_samples], dtype=np.int64)
    truth_pos = np.array([s.pos for s in truth_samples], dtype=float)
    truth_at_est = bm._resample_to_truth(est_ts, truth_ts_arr, truth_pos)

    if truth_at_est.shape[0] < 2:
        return TuningResult(params=cfg, rmse_xy=float("nan"), rmse_z=float("nan"),
                           rmse_3d=float("nan"), cep50=float("nan"), max_drift=float("nan"),
                           latency_us=float("nan"), elapsed_s=elapsed)

    return TuningResult(
        params=cfg,
        rmse_xy=bm.compute_rmse_xy(est_p, truth_at_est),
        rmse_z=bm.compute_rmse_z(est_p, truth_at_est),
        rmse_3d=bm.compute_rmse(est_p, truth_at_est),
        cep50=bm.compute_cep(est_p, truth_at_est),
        max_drift=bm.compute_max_drift(est_p, truth_at_est),
        latency_us=np.mean(perf_times) * 1e6 if perf_times else float("nan"),
        elapsed_s=elapsed,
    )


def load_dataset(mcap_path, truth_topics):
    import importlib
    import offline_ekf_benchmark as bm
    importlib.reload(bm)
    bm.ensure_runtime_dependencies()
    return bm.read_mcap_sensor_data(
        mcap_path=mcap_path,
        imu_topic="/auv/sensors/imu",
        dvl_topic="/auv/sensors/dvl",
        depth_topic="/auv/sensors/depth",
        truth_topics=truth_topics,
        dvl_frame="world",
        apply_coord_transform=True,
        verbose=False,
    )


def main():
    parser = argparse.ArgumentParser(description="ES-EKF Quick Parameter Tuning")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("./tuning_results"))
    parser.add_argument("--truth-topics", default="/auv/visual/truth_marker")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    truth_topic_list = [t.strip() for t in args.truth_topics.split(",") if t.strip()]

    print("=" * 70)
    print("  ES-EKF Quick Parameter Tuning")
    print("=" * 70)

    print("\n[Loading dataset] ...")
    imu, dvl, depth, truth = load_dataset(args.input, truth_topic_list)
    duration = (truth[-1].ts_ns - truth[0].ts_ns) / 1e9 if truth else 0
    print(f"  Duration: {duration:.1f}s, IMU: {len(imu)}, DVL: {len(dvl)}, Truth: {len(truth)}")

    all_results = []
    best_overall = None

    key_params = {
        "sigma_dvl": [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 1.0],
        "sigma_acc": [0.01, 0.02, 0.04, 0.08, 0.12, 0.20, 0.50],
        "sigma_gyro": [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10],
        "sigma_depth": [0.01, 0.02, 0.05, 0.10, 0.20, 0.50],
        "sigma_ba": [0.0001, 0.0005, 0.001, 0.005, 0.01],
        "sigma_bg": [0.00005, 0.0001, 0.0005, 0.001, 0.005],
    }

    print("\n[Phase 1] Single-parameter sweep (one at a time)")
    print("-" * 50)
    sweep_results = {}

    for param_name, values in key_params.items():
        print(f"  Sweeping {param_name} ({len(values)} values)...")
        sweep_results[param_name] = []
        for val in values:
            cfg = build_config({param_name: val})
            r = run_single_eval(cfg, imu, dvl, depth, truth)
            sweep_results[param_name].append((val, r))
            all_results.append(r)
            print(f"    {param_name}={val:8.4f} -> RMSE_3D={r.rmse_3d:.4f}m")

        best_in_sweep = min(sweep_results[param_name], key=lambda x: x[1].rmse_3d if not math.isnan(x[1].rmse_3d) else float("inf"))
        print(f"    Best: {param_name}={best_in_sweep[0]:.4f}, RMSE_3D={best_in_sweep[1].rmse_3d:.4f}m")
        if best_overall is None or best_in_sweep[1].rmse_3d < best_overall.rmse_3d:
            best_overall = best_in_sweep[1]

    print("\n[Phase 2] Best single-parameter combinations")
    print("-" * 50)

    best_singles = {}
    for param_name, results in sweep_results.items():
        best_in_sweep = min(results, key=lambda x: x[1].rmse_3d if not math.isnan(x[1].rmse_3d) else float("inf"))
        best_singles[param_name] = best_in_sweep[0]

    print(f"  Best individual values:")
    for k, v in best_singles.items():
        print(f"    {k} = {v}")

    combos_to_test = [
        {**best_singles},
        {k: BASE_CONFIG[k] for k in BASE_CONFIG if not k.startswith("_") and not k.startswith("init_")},
    ]

    for combo in combos_to_test:
        cfg = build_config(combo)
        r = run_single_eval(cfg, imu, dvl, depth, truth)
        all_results.append(r)
        print(f"  Combined best params -> RMSE_3D={r.rmse_3d:.4f}m")
        if r.rmse_3d < best_overall.rmse_3d:
            best_overall = r

    print("\n[Phase 3] Fine search around best sigma_dvl")
    print("-" * 50)
    best_dvl = best_singles.get("sigma_dvl", 0.03)
    fine_dvl_vals = sorted(set(max(0.001, best_dvl * f) for f in [0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0, 3.0]))
    best_acc = best_singles.get("sigma_acc", 0.08)
    best_gyro = best_singles.get("sigma_gyro", 0.01)

    for sd in fine_dvl_vals:
        cfg = build_config({"sigma_dvl": sd, "sigma_acc": best_acc, "sigma_gyro": best_gyro})
        r = run_single_eval(cfg, imu, dvl, depth, truth)
        all_results.append(r)
        print(f"    dvl={sd:.4f}, acc={best_acc}, gyro={best_gyro} -> RMSE_3D={r.rmse_3d:.4f}m")
        if r.rmse_3d < best_overall.rmse_3d:
            best_overall = r

    baseline = run_single_eval(build_config({}), imu, dvl, depth, truth)
    all_results.append(baseline)
    if baseline.rmse_3d < best_overall.rmse_3d:
        best_overall = baseline

    improvement = (baseline.rmse_3d - best_overall.rmse_3d) / baseline.rmse_3d * 100 if baseline.rmse_3d > 0 else 0

    all_results_sorted = sorted(
        [r for r in all_results if not math.isnan(r.rmse_3d)],
        key=lambda r: r.rmse_3d
    )

    print("\n" + "=" * 70)
    print("  Top 10 Results")
    print("=" * 70)
    print(f"{'Rank':>4} | {'RMSE_3D':>8} | {'RMSE_XY':>8} | {'RMSE_Z':>8} | {'CEP50':>8} | sigma_dvl | sigma_acc | sigma_gyro")
    print("-" * 100)
    for i, r in enumerate(all_results_sorted[:10]):
        p = r.params
        print(f"{i+1:4d} | {r.rmse_3d:8.3f} | {r.rmse_xy:8.3f} | {r.rmse_z:8.3f} | {r.cep50:8.3f} | "
              f"{p['sigma_dvl']:9.4f} | {p['sigma_acc']:9.4f} | {p['sigma_gyro']:9.4f}")

    print(f"\n  Baseline RMSE_3D: {baseline.rmse_3d:.4f}m")
    print(f"  Best RMSE_3D:     {best_overall.rmse_3d:.4f}m")
    print(f"  Improvement:      {improvement:.1f}%")

    generate_report(all_results_sorted, best_overall, baseline, sweep_results, output_dir, args.input)


def generate_report(all_sorted, best, baseline, sweep_results, output_dir, input_path):
    lines = []
    lines.append("# ES-EKF 参数调优报告\n")
    lines.append("## 测试信息\n")
    lines.append(f"- **输入文件**: `{input_path}`")
    lines.append(f"- **总评估次数**: {len(all_sorted)}")
    lines.append(f"- **调优策略**: 单参数扫描 -> 组合优化 -> 精细搜索\n")

    improvement = (baseline.rmse_3d - best.rmse_3d) / baseline.rmse_3d * 100 if baseline.rmse_3d > 0 else 0

    lines.append("## 基线 vs 最优参数\n")
    lines.append("| 参数 | 基线值 | 最优值 | 变化倍数 |")
    lines.append("|------|--------|--------|---------|")
    for key in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth", "sigma_ba", "sigma_bg"]:
        base_val = BASE_CONFIG[key]
        opt_val = best.params.get(key, base_val)
        ratio = opt_val / base_val if base_val != 0 else float("inf")
        lines.append(f"| {key} | {base_val} | {opt_val} | {ratio:.2f}x |")

    lines.append(f"\n**基线性能**: RMSE_3D = {baseline.rmse_3d:.4f}m, RMSE_XY = {baseline.rmse_xy:.4f}m, RMSE_Z = {baseline.rmse_z:.4f}m")
    lines.append(f"**最优性能**: RMSE_3D = {best.rmse_3d:.4f}m, RMSE_XY = {best.rmse_xy:.4f}m, RMSE_Z = {best.rmse_z:.4f}m")
    lines.append(f"**性能提升**: {improvement:.1f}%\n")

    lines.append("## 单参数扫描结果\n")
    for param_name, results in sweep_results.items():
        lines.append(f"### {param_name}\n")
        lines.append("| 参数值 | 相对基线 | RMSE_3D (m) | RMSE_XY (m) | RMSE_Z (m) | 标记 |")
        lines.append("|--------|----------|-------------|-------------|------------|------|")
        base_val = BASE_CONFIG[param_name]
        results.sort(key=lambda x: x[0])
        for pval, r in results:
            ratio = pval / base_val if base_val != 0 else 0
            marker = ""
            if abs(r.rmse_3d - best.rmse_3d) < 0.001:
                marker = " **BEST**"
            elif abs(ratio - 1.0) < 0.01:
                marker = "  BASE"
            lines.append(f"| {pval:.6f} | {ratio:.2f}x | {r.rmse_3d:.4f} | {r.rmse_xy:.4f} | {r.rmse_z:.4f} |{marker}|")
        lines.append("")

    lines.append("## 灵敏度分析\n")
    for param_name, results in sweep_results.items():
        valid = [(pval, r.rmse_3d) for pval, r in results if not math.isnan(r.rmse_3d)]
        if len(valid) < 2:
            continue
        rmse_vals = [r for _, r in valid]
        min_rmse = min(rmse_vals)
        max_rmse = max(rmse_vals)
        sensitivity = max_rmse - min_rmse
        lines.append(f"- **{param_name}**: 灵敏度 = {sensitivity:.4f}m (RMSE 范围: {min_rmse:.4f} ~ {max_rmse:.4f})")
    lines.append("")

    lines.append("## 关键发现\n")
    best_dvl = best.params.get("sigma_dvl", 0)
    best_acc = best.params.get("sigma_acc", 0)
    best_gyro = best.params.get("sigma_gyro", 0)
    base_dvl = BASE_CONFIG["sigma_dvl"]
    base_acc = BASE_CONFIG["sigma_acc"]
    base_gyro = BASE_CONFIG["sigma_gyro"]

    if best_dvl < base_dvl:
        lines.append(f"1. **DVL 观测噪声 (sigma_dvl)**: 最优值 {best_dvl} < 基线 {base_dvl}，DVL 数据质量好，应给予更高信任度")
    else:
        lines.append(f"1. **DVL 观测噪声 (sigma_dvl)**: 最优值 {best_dvl} >= 基线 {base_dvl}，DVL 数据噪声较大")

    if best_gyro < base_gyro:
        lines.append(f"2. **陀螺噪声 (sigma_gyro)**: 最优值 {best_gyro} < 基线 {base_gyro}，IMU 角速度测量较精确")
    else:
        lines.append(f"2. **陀螺噪声 (sigma_gyro)**: 最优值 {best_gyro} >= 基线 {base_gyro}")

    if best_acc < base_acc:
        lines.append(f"3. **加速度噪声 (sigma_acc)**: 最优值 {best_acc} < 基线 {base_acc}")
    else:
        lines.append(f"3. **加速度噪声 (sigma_acc)**: 最优值 {best_acc} >= 基线 {base_acc}")

    lines.append("\n## 调优建议\n")
    lines.append("1. **sigma_dvl 是最敏感参数**：直接影响观测更新的增益，应优先根据 DVL 实际性能标定")
    lines.append("2. **sigma_gyro 影响航向积分精度**：在转向/剧烈运动时尤为重要")
    lines.append("3. **参数应协同调整**：单个参数的最优值在其他参数改变后可能不再最优")
    lines.append("4. **使用实际传感器数据标定**：建议通过静止/匀速实验标定 IMU 和 DVL 的噪声特性")
    lines.append("5. **多数据集验证**：在不同运动模式下验证参数鲁棒性\n")

    lines.append("## 推荐参数配置\n")
    lines.append("```yaml")
    lines.append("ekf:")
    for key in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth", "sigma_ba", "sigma_bg"]:
        lines.append(f"  {key}: {best.params.get(key, BASE_CONFIG[key])}")
    lines.append("  imu_acc_is_linear: true")
    lines.append(f"  init_P_diag: {BASE_CONFIG['init_P_diag']}")
    lines.append("```\n")

    (output_dir / "tuning_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    result_data = {
        "input_file": str(input_path),
        "total_evaluations": len(all_sorted),
        "baseline": {
            "rmse_xy": baseline.rmse_xy,
            "rmse_z": baseline.rmse_z,
            "rmse_3d": baseline.rmse_3d,
        },
        "best": {
            "params": {k: v for k, v in best.params.items() if not str(k).startswith("_")},
            "rmse_xy": best.rmse_xy,
            "rmse_z": best.rmse_z,
            "rmse_3d": best.rmse_3d,
            "improvement_pct": round(improvement, 2),
        },
        "top_10": [],
    }
    for r in all_sorted[:10]:
        result_data["top_10"].append({
            "rmse_3d": r.rmse_3d,
            "sigma_dvl": r.params.get("sigma_dvl"),
            "sigma_acc": r.params.get("sigma_acc"),
            "sigma_gyro": r.params.get("sigma_gyro"),
        })

    with open(output_dir / "tuning_results.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
