#!/usr/bin/env python3
"""
ES-EKF 离线参数搜索调优工具。

系统性地搜索 EKF 噪声参数和初始协方差，在给定数据集上评估性能，
找到最优参数组合，并生成调优报告。

用法:
  python3 tools/es_ekf_param_tuner.py \
    --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output-dir ./tuning_results
"""

from __future__ import annotations

import argparse
import copy
import itertools
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
    innovation_stats: dict


def build_config(sigma_acc=None, sigma_gyro=None, sigma_dvl=None,
                 sigma_depth=None, sigma_ba=None, sigma_bg=None,
                 p_scale=1.0) -> dict:
    cfg = copy.deepcopy(BASE_CONFIG)
    if sigma_acc is not None:
        cfg["sigma_acc"] = sigma_acc
    if sigma_gyro is not None:
        cfg["sigma_gyro"] = sigma_gyro
    if sigma_dvl is not None:
        cfg["sigma_dvl"] = sigma_dvl
    if sigma_depth is not None:
        cfg["sigma_depth"] = sigma_depth
    if sigma_ba is not None:
        cfg["sigma_ba"] = sigma_ba
    if sigma_bg is not None:
        cfg["sigma_bg"] = sigma_bg
    if p_scale != 1.0:
        cfg["init_P_diag"] = [v * p_scale for v in cfg["init_P_diag"]]
    return cfg


def get_p_scale(cfg: dict) -> float:
    base = BASE_CONFIG["init_P_diag"][0]
    if base == 0:
        return 1.0
    return cfg["init_P_diag"][0] / base


def run_single_eval(cfg: dict, imu_samples, dvl_samples, depth_samples,
                    truth_samples) -> TuningResult:
    import importlib
    import offline_ekf_benchmark as bm
    importlib.reload(bm)
    bm.ensure_runtime_dependencies()

    engine = bm.EseKfEngine(cfg)

    imu_timestamps_ns = [s.ts_ns for s in imu_samples]
    dvl_timestamps_ns = [s.ts_ns for s in dvl_samples]
    depth_timestamps_ns = [s.ts_ns for s in depth_samples]
    truth_timestamps_ns = [s.ts_ns for s in truth_samples]

    all_event_ts = sorted(set(
        imu_timestamps_ns + dvl_timestamps_ns + depth_timestamps_ns + truth_timestamps_ns
    ))

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

        if event_ts in truth_timestamps_ns:
            engine.record_state(event_ts)

    elapsed = time.perf_counter() - t_start
    est_ts = np.array(engine.history_ts, dtype=np.int64)
    est_p = np.array(engine.history_p, dtype=float) if engine.history_p else np.empty((0, 3))

    if est_p.ndim != 2 or est_p.shape[0] < 2:
        return TuningResult(
            params=cfg, rmse_xy=float("nan"), rmse_z=float("nan"),
            rmse_3d=float("nan"), cep50=float("nan"), max_drift=float("nan"),
            latency_us=np.mean(perf_times)*1e6 if perf_times else float("nan"),
            elapsed_s=elapsed, innovation_stats={},
        )

    truth_ts_arr = np.array([s.ts_ns for s in truth_samples], dtype=np.int64)
    truth_pos = np.array([s.pos for s in truth_samples], dtype=float)
    truth_at_est = bm._resample_to_truth(est_ts, truth_ts_arr, truth_pos)

    if truth_at_est.shape[0] < 2:
        return TuningResult(
            params=cfg, rmse_xy=float("nan"), rmse_z=float("nan"),
            rmse_3d=float("nan"), cep50=float("nan"), max_drift=float("nan"),
            latency_us=np.mean(perf_times)*1e6 if perf_times else float("nan"),
            elapsed_s=elapsed, innovation_stats={},
        )

    rmse_xy = bm.compute_rmse_xy(est_p, truth_at_est)
    rmse_z = bm.compute_rmse_z(est_p, truth_at_est)
    rmse_3d = bm.compute_rmse(est_p, truth_at_est)
    cep50 = bm.compute_cep(est_p, truth_at_est)
    max_drift = bm.compute_max_drift(est_p, truth_at_est)
    latency_us = np.mean(perf_times) * 1e6 if perf_times else float("nan")

    innov = np.array(engine.innovation_history, dtype=float)
    innov_stats = {}
    if innov.size > 0:
        gate = 3.0 * cfg.get("sigma_dvl", 0.03)
        innov_stats = {
            "mean": float(np.mean(innov)),
            "std": float(np.std(innov)),
            "max": float(np.max(innov)),
            "min": float(np.min(innov)),
            "within_3sigma_pct": float(np.mean(innov < gate) * 100),
        }

    return TuningResult(
        params=cfg, rmse_xy=rmse_xy, rmse_z=rmse_z, rmse_3d=rmse_3d,
        cep50=cep50, max_drift=max_drift, latency_us=latency_us,
        elapsed_s=elapsed, innovation_stats=innov_stats,
    )


def load_dataset(mcap_path, truth_topics):
    import importlib
    import offline_ekf_benchmark as bm
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


def run_round1_coarse_search(imu, dvl, depth, truth) -> list[TuningResult]:
    sigma_dvl_vals = [0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
    sigma_acc_vals = [0.02, 0.04, 0.08, 0.12, 0.20]
    sigma_gyro_vals = [0.001, 0.005, 0.01, 0.02, 0.05]

    combos = list(itertools.product(sigma_dvl_vals, sigma_acc_vals, sigma_gyro_vals))
    print(f"  Round 1: Coarse grid search, {len(combos)} combinations")

    results = []
    for i, (sd, sa, sg) in enumerate(combos):
        cfg = build_config(sigma_acc=sa, sigma_gyro=sg, sigma_dvl=sd)
        r = run_single_eval(cfg, imu, dvl, depth, truth)
        r.params["_round"] = 1
        r.params["_combo"] = i
        results.append(r)
        if (i + 1) % 20 == 0:
            best_so_far = min((res.rmse_3d for res in results if not math.isnan(res.rmse_3d)), default=float("inf"))
            print(f"    [{i + 1}/{len(combos)}] Best RMSE so far: {best_so_far:.4f}")

    return results


def run_round2_fine_search(imu, dvl, depth, truth, best_prev) -> list[TuningResult]:
    p1 = best_prev.params
    sd0 = p1["sigma_dvl"]
    sa0 = p1["sigma_acc"]
    sg0 = p1["sigma_gyro"]
    sp0 = p1["sigma_depth"]

    sigma_dvl_vals = sorted(set(max(0.005, sd0 * f) for f in [0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0, 3.0]))
    sigma_acc_vals = sorted(set(max(0.005, sa0 * f) for f in [0.3, 0.5, 0.7, 0.85, 1.0, 1.3, 1.5, 2.0]))
    sigma_gyro_vals = sorted(set(max(0.0005, sg0 * f) for f in [0.1, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0]))
    sigma_depth_vals = sorted(set(max(0.005, sp0 * f) for f in [0.1, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0]))
    p_scales = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0]

    combos = list(itertools.product(sigma_dvl_vals, sigma_acc_vals, sigma_gyro_vals, p_scales))
    print(f"  Round 2: Fine search around best, {len(combos)} combinations")

    results = []
    for i, (sd, sa, sg, ps) in enumerate(combos):
        cfg = build_config(sigma_acc=sa, sigma_gyro=sg, sigma_dvl=sd, p_scale=ps)
        r = run_single_eval(cfg, imu, dvl, depth, truth)
        r.params["_round"] = 2
        r.params["_combo"] = i
        results.append(r)
        if (i + 1) % 20 == 0:
            best_so_far = min((res.rmse_3d for res in results if not math.isnan(res.rmse_3d)), default=float("inf"))
            print(f"    [{i + 1}/{len(combos)}] Best RMSE so far: {best_so_far:.4f}")

    return results


def run_round3_extended(imu, dvl, depth, truth, best_prev) -> list[TuningResult]:
    """Round 3: Extended search with all 6 noise parameters + P scale."""
    p = best_prev.params
    results = []

    # Search sigma_ba and sigma_bg
    ba_vals = [0.00005, 0.0001, 0.0005, p["sigma_ba"], 0.002, 0.005, 0.01, 0.02]
    bg_vals = [0.00001, 0.00005, 0.0001, p["sigma_bg"], 0.001, 0.002, 0.005, 0.01]
    p_scales = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0]

    combos = list(itertools.product(ba_vals, bg_vals, p_scales))
    print(f"  Round 3: Bias noise + P scale search, {len(combos)} combinations")

    for i, (ba, bg, ps) in enumerate(combos):
        cfg = build_config(
            sigma_acc=p["sigma_acc"], sigma_gyro=p["sigma_gyro"],
            sigma_dvl=p["sigma_dvl"], sigma_depth=p["sigma_depth"],
            sigma_ba=ba, sigma_bg=bg, p_scale=ps,
        )
        r = run_single_eval(cfg, imu, dvl, depth, truth)
        r.params["_round"] = 3
        r.params["_combo"] = i
        results.append(r)
        if (i + 1) % 20 == 0:
            best_so_far = min((res.rmse_3d for res in results if not math.isnan(res.rmse_3d)), default=float("inf"))
            print(f"    [{i + 1}/{len(combos)}] Best RMSE so far: {best_so_far:.4f}")

    return results


def run_round4_sensitivity(imu, dvl, depth, truth, best_prev) -> list[TuningResult]:
    """Round 4: One-parameter-at-a-time sensitivity analysis."""
    p = best_prev.params
    results = []

    param_ranges = {
        "sigma_dvl": [p["sigma_dvl"] * f for f in [0.1, 0.25, 0.5, 0.75, 0.85, 1.0, 1.15, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0]],
        "sigma_acc": [p["sigma_acc"] * f for f in [0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0]],
        "sigma_gyro": [p["sigma_gyro"] * f for f in [0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 20.0]],
        "sigma_depth": [p["sigma_depth"] * f for f in [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 5.0, 10.0]],
        "sigma_ba": [p["sigma_ba"] * f for f in [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]],
        "sigma_bg": [p["sigma_bg"] * f for f in [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]],
    }

    combos = []
    for param_name, values in param_ranges.items():
        for val in values:
            combos.append((param_name, val))

    print(f"  Round 4: Sensitivity analysis, {len(combos)} evaluations")

    for i, (pname, pval) in enumerate(combos):
        cfg = build_config(**{pname: pval})
        r = run_single_eval(cfg, imu, dvl, depth, truth)
        r.params["_round"] = 4
        r.params["_param_changed"] = pname
        r.params["_param_value"] = pval
        results.append(r)

    return results


def get_top_results(results, n=10, key="rmse_3d"):
    valid = [r for r in results if not math.isnan(r.rmse_3d)]
    return sorted(valid, key=lambda r: getattr(r, key))[:n]


def summarize_top(results, show_round=False):
    lines = []
    header = f"{'Rank':>4} | {'RMSE_3D':>8} | {'RMSE_XY':>8} | {'RMSE_Z':>8} | {'CEP50':>8} | {'MaxDrift':>8}"
    if show_round:
        header += f" | {'R':>2} | sigma_dvl | sigma_acc | sigma_gyro | P_scale"
    else:
        header += f" | sigma_dvl | sigma_acc | sigma_gyro | P_scale"
    lines.append(header)
    lines.append("-" * (len(header) + 10))
    for i, r in enumerate(results):
        p = r.params
        sd = p.get("sigma_dvl", "?")
        sa = p.get("sigma_acc", "?")
        sg = p.get("sigma_gyro", "?")
        ps = get_p_scale(p)
        rnd = p.get("_round", "?")
        row = (
            f"{i + 1:4d} | {r.rmse_3d:8.3f} | {r.rmse_xy:8.3f} | {r.rmse_z:8.3f} "
            f"| {r.cep50:8.3f} | {r.max_drift:8.3f}"
        )
        if show_round:
            row += f" | {rnd:2d}"
        row += f" | {sd:9.4f} | {sa:9.4f} | {sg:10.4f} | {ps:.2f}"
        lines.append(row)
    return "\n".join(lines)


def generate_tuning_report(all_results, best, baseline, output_dir, input_path):
    lines = []
    lines.append("# ES-EKF 参数调优报告\n")

    lines.append("## 测试信息\n")
    lines.append(f"- **输入文件**: `{input_path}`")
    lines.append(f"- **总评估次数**: {len(all_results)}")
    lines.append(f"- **调优轮次**: 4 轮 (粗搜索 -> 细搜索 -> 偏差噪声搜索 -> 灵敏度分析)\n")

    improvement = (baseline.rmse_3d - best.rmse_3d) / baseline.rmse_3d * 100 if baseline.rmse_3d > 0 else 0

    lines.append("## 基线 vs 最优参数\n")
    lines.append("### 基线配置（原始参数）\n")
    lines.append("| 参数 | 值 |")
    lines.append("|------|-----|")
    for k, v in BASE_CONFIG.items():
        if isinstance(v, list):
            lines.append(f"| {k} | {v} |")
        else:
            lines.append(f"| {k} | {v} |")

    lines.append(f"\n**基线性能**: RMSE_3D = {baseline.rmse_3d:.4f}m, RMSE_XY = {baseline.rmse_xy:.4f}m, RMSE_Z = {baseline.rmse_z:.4f}m\n")

    lines.append("### 最优配置\n")
    lines.append("| 参数 | 基线值 | 最优值 | 变化倍数 |")
    lines.append("|------|--------|--------|---------|")
    for key in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth", "sigma_ba", "sigma_bg"]:
        base_val = BASE_CONFIG[key]
        opt_val = best.params.get(key, base_val)
        ratio = opt_val / base_val if base_val != 0 else float("inf")
        lines.append(f"| {key} | {base_val} | {opt_val} | {ratio:.2f}x |")

    lines.append(f"\n**最优性能**: RMSE_3D = {best.rmse_3d:.4f}m, RMSE_XY = {best.rmse_xy:.4f}m, RMSE_Z = {best.rmse_z:.4f}m")
    lines.append(f"**性能提升**: {improvement:.1f}%\n")

    lines.append("## 各轮搜索结果\n")

    rounds_data = {}
    for r in all_results:
        rnd = r.params.get("_round", "?")
        if rnd not in rounds_data:
            rounds_data[rnd] = []
        rounds_data[rnd].append(r)

    round_names = {
        1: "粗网格搜索 (sigma_dvl, sigma_acc, sigma_gyro)",
        2: "精细搜索 (含 P 尺度因子)",
        3: "偏差噪声搜索 (sigma_ba, sigma_bg + P 尺度)",
        4: "单参数灵敏度分析",
    }

    for rnd in sorted(rounds_data.keys()):
        lines.append(f"### Round {rnd}: {round_names.get(rnd, 'Unknown')}\n")
        top10 = get_top_results(rounds_data[rnd], n=10)
        lines.append(summarize_top(top10, show_round=False))
        lines.append("")

        best_r = top10[0]
        lines.append(f"**Round {rnd} 最佳**: RMSE_3D = {best_r.rmse_3d:.4f}m\n")

    lines.append("## 灵敏度分析\n")
    r4_data = rounds_data.get(4, [])
    if r4_data:
        param_results = {}
        for r in r4_data:
            pname = r.params.get("_param_changed", "unknown")
            pval = r.params.get("_param_value", 0)
            if pname not in param_results:
                param_results[pname] = []
            param_results[pname].append((pval, r.rmse_3d))

        for pname, data in sorted(param_results.items()):
            data.sort(key=lambda x: x[0])
            base_val = BASE_CONFIG[pname]
            lines.append(f"### {pname}\n")
            lines.append("| 参数值 | 相对基线 | RMSE_3D (m) | 标记 |")
            lines.append("|--------|----------|-------------|------|")
            for pval, rmse in data:
                ratio = pval / base_val if base_val != 0 else 0
                marker = " **BEST**" if abs(rmse - best.rmse_3d) < 0.001 else ""
                if abs(ratio - 1.0) < 0.01:
                    marker = "  BASE"
                lines.append(f"| {pval:.6f} | {ratio:.2f}x | {rmse:.4f} |{marker}|")
            lines.append("")

    lines.append("## 经验总结\n")

    lines.append("### 关键发现\n")

    best_sd = best.params.get("sigma_dvl", 0)
    best_sa = best.params.get("sigma_acc", 0)
    best_sg = best.params.get("sigma_gyro", 0)
    base_sd = BASE_CONFIG["sigma_dvl"]
    base_sa = BASE_CONFIG["sigma_acc"]
    base_sg = BASE_CONFIG["sigma_gyro"]

    lines.append("1. **DVL 观测噪声 (sigma_dvl)**:")
    if best_sd < base_sd:
        lines.append(f"   - 最优值 {best_sd} 低于基线 {base_sd}，说明 DVL 数据质量较好，应给予更高信任度")
    elif best_sd > base_sd:
        lines.append(f"   - 最优值 {best_sd} 高于基线 {base_sd}，说明 DVL 数据存在较大噪声，应降低信任度")
    else:
        lines.append(f"   - 最优值 {best_sd} 与基线相同")

    lines.append("2. **IMU 加速度噪声 (sigma_acc)**:")
    lines.append(f"   - 最优值 {best_sa} (基线: {base_sa})")

    lines.append("3. **IMU 陀螺噪声 (sigma_gyro)**:")
    lines.append(f"   - 最优值 {best_sg} (基线: {base_sg})")

    lines.append("4. **初始协方差 (init_P_diag)**:")
    ps = get_p_scale(best.params)
    if ps < 1.0:
        lines.append(f"   - 最优 P 尺度因子 {ps} < 1.0，说明滤波器初始置信度应更高（更小的不确定性）")
    elif ps > 1.0:
        lines.append(f"   - 最优 P 尺度因子 {ps} > 1.0，说明滤波器初始应更保守（更大的不确定性）")
    else:
        lines.append(f"   - 最优 P 尺度因子 = 1.0，基线值已经合适")

    lines.append("\n### 调优建议\n")
    lines.append("1. **优先调整 sigma_dvl**：DVL 观测噪声对定位精度影响最大，是最敏感的参数")
    lines.append("2. **sigma_gyro 对航向精度至关重要**：在转向场景下尤为明显")
    lines.append("3. **初始协方差 P 不宜过大**：过大的 P 会导致初期发散")
    lines.append("4. **Bias 噪声参数 (sigma_ba, sigma_bg)**：对短时间数据影响较小，但长时间运行时会累积")
    lines.append("5. **使用多数据集验证**：在不同海况、不同运动模式下验证最优参数的鲁棒性")

    lines.append("\n### 推荐参数配置\n")
    lines.append("```yaml")
    lines.append("ekf:")
    for key in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth", "sigma_ba", "sigma_bg"]:
        lines.append(f"  {key}: {best.params.get(key, BASE_CONFIG[key])}")
    lines.append("  imu_acc_is_linear: true")
    lines.append("  init_P_diag: " + str([round(v, 6) for v in best.params.get("init_P_diag", BASE_CONFIG["init_P_diag"])]))
    lines.append("```\n")

    output_dir / "tuning_report.md"
    (output_dir / "tuning_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="ES-EKF Parameter Tuning Tool")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results/tuning"))
    parser.add_argument("--truth-topics", default="/auv/visual/truth_marker,/auv/state/truth,/auv/sensors/ground_truth")
    parser.add_argument("--skip-rounds", nargs="+", type=int, default=[])
    args = parser.parse_args()

    import importlib
    import offline_ekf_benchmark as bm
    importlib.reload(bm)
    bm.ensure_runtime_dependencies()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    truth_topic_list = [t.strip() for t in args.truth_topics.split(",") if t.strip()]

    print("=" * 70)
    print("  ES-EKF Parameter Tuning - Multi-Round Optimization")
    print("=" * 70)

    print("\n[Loading dataset] ...")
    imu, dvl, depth, truth = load_dataset(args.input, truth_topic_list)
    duration = (truth[-1].ts_ns - truth[0].ts_ns) / 1e9 if truth else 0
    print(f"  Duration: {duration:.1f}s, IMU: {len(imu)}, DVL: {len(dvl)}, Depth: {len(depth)}, Truth: {len(truth)}")

    all_results = []
    best_overall = None

    if 1 not in args.skip_rounds:
        print("\n[Round 1] Coarse Grid Search")
        print("-" * 50)
        r1 = run_round1_coarse_search(imu, dvl, depth, truth)
        all_results.extend(r1)
        top10 = get_top_results(r1)
        print("\n  Top 10 (Round 1):")
        print(summarize_top(top10))
        best_r1 = top10[0]
        print(f"\n  Best Round 1: RMSE_3D = {best_r1.rmse_3d:.4f}m")
        if best_overall is None or best_r1.rmse_3d < best_overall.rmse_3d:
            best_overall = best_r1

    if 2 not in args.skip_rounds:
        print("\n[Round 2] Fine Search Around Best")
        print("-" * 50)
        r2 = run_round2_fine_search(imu, dvl, depth, truth, best_overall)
        all_results.extend(r2)
        top10 = get_top_results(r2)
        print("\n  Top 10 (Round 2):")
        print(summarize_top(top10))
        best_r2 = top10[0]
        print(f"\n  Best Round 2: RMSE_3D = {best_r2.rmse_3d:.4f}m")
        if best_r2.rmse_3d < best_overall.rmse_3d:
            best_overall = best_r2

    if 3 not in args.skip_rounds:
        print("\n[Round 3] Bias Noise + P Scale Search")
        print("-" * 50)
        r3 = run_round3_extended(imu, dvl, depth, truth, best_overall)
        all_results.extend(r3)
        top10 = get_top_results(r3)
        print("\n  Top 10 (Round 3):")
        print(summarize_top(top10))
        best_r3 = top10[0]
        if best_r3.rmse_3d < best_overall.rmse_3d:
            best_overall = best_r3

    if 4 not in args.skip_rounds:
        print("\n[Round 4] Sensitivity Analysis")
        print("-" * 50)
        r4 = run_round4_sensitivity(imu, dvl, depth, truth, best_overall)
        all_results.extend(r4)
        top10 = get_top_results(r4)
        print("\n  Top 10 (Round 4):")
        print(summarize_top(top10))
        best_r4 = top10[0]
        if best_r4.rmse_3d < best_overall.rmse_3d:
            best_overall = best_r4

    overall_top = get_top_results(all_results, n=20)
    print("\n" + "=" * 70)
    print("  Overall Top 20 Results")
    print("=" * 70)
    print(summarize_top(overall_top))

    baseline_cfg = copy.deepcopy(BASE_CONFIG)
    baseline = run_single_eval(baseline_cfg, imu, dvl, depth, truth)
    improvement = (baseline.rmse_3d - best_overall.rmse_3d) / baseline.rmse_3d * 100 if baseline.rmse_3d > 0 else 0

    print(f"\n  Baseline RMSE_3D: {baseline.rmse_3d:.4f}m")
    print(f"  Best RMSE_3D:     {best_overall.rmse_3d:.4f}m")
    print(f"  Improvement:      {improvement:.1f}%")

    result_data = {
        "input_file": str(args.input),
        "total_evaluations": len(all_results),
        "baseline": {
            "params": {k: v for k, v in baseline.params.items() if not str(k).startswith("_")},
            "rmse_xy": baseline.rmse_xy,
            "rmse_z": baseline.rmse_z,
            "rmse_3d": baseline.rmse_3d,
            "cep50": baseline.cep50,
            "max_drift": baseline.max_drift,
        },
        "best": {
            "params": {k: v for k, v in best_overall.params.items() if not str(k).startswith("_")},
            "rmse_xy": best_overall.rmse_xy,
            "rmse_z": best_overall.rmse_z,
            "rmse_3d": best_overall.rmse_3d,
            "cep50": best_overall.cep50,
            "max_drift": best_overall.max_drift,
            "improvement_pct": round(improvement, 2),
        },
        "top_20": [],
    }

    for r in overall_top:
        result_data["top_20"].append({
            "rmse_xy": r.rmse_xy,
            "rmse_z": r.rmse_z,
            "rmse_3d": r.rmse_3d,
            "cep50": r.cep50,
            "max_drift": r.max_drift,
            "sigma_dvl": r.params.get("sigma_dvl"),
            "sigma_acc": r.params.get("sigma_acc"),
            "sigma_gyro": r.params.get("sigma_gyro"),
            "sigma_ba": r.params.get("sigma_ba"),
            "sigma_bg": r.params.get("sigma_bg"),
            "p_scale": get_p_scale(r.params),
        })

    with open(output_dir / "tuning_results.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)

    generate_tuning_report(all_results, best_overall, baseline, output_dir, args.input)
    print(f"\n  Report saved: {output_dir / 'tuning_report.md'}")
    print(f"  Results saved: {output_dir / 'tuning_results.json'}")

    print("\n" + "=" * 70)
    print("  Tuning complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
