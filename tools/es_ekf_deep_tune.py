#!/usr/bin/env python3
"""
ES-EKF 深度调优 + 算法改进验证。

在基准工具上直接运行多次参数搜索和算法变体测试。
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
class Result:
    label: str
    params: dict
    rmse_xy: float
    rmse_z: float
    rmse_3d: float
    cep50: float
    max_drift: float


def load_benchmark():
    import importlib
    import offline_ekf_benchmark as bm
    importlib.reload(bm)
    bm.ensure_runtime_dependencies()
    return bm


def load_dataset(mcap_path, truth_topics):
    bm = load_benchmark()
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


def evaluate_config(cfg, imu, dvl, depth, truth, bm=None):
    """Run ES-EKF with given config on pre-loaded data."""
    if bm is None:
        bm = load_benchmark()
    engine = bm.EseKfEngine(cfg)

    all_ts = sorted(set(
        [s.ts_ns for s in imu] + [s.ts_ns for s in dvl] +
        [s.ts_ns for s in depth] + [s.ts_ns for s in truth]
    ))
    truth_ts_set = set(s.ts_ns for s in truth)

    imu_i, dvl_i, depth_i = 0, 0, 0
    last_imu_ts = None
    t0 = time.perf_counter()

    for ts in all_ts:
        while imu_i < len(imu) and imu[imu_i].ts_ns <= ts:
            s = imu[imu_i]
            dt = (s.ts_ns - last_imu_ts) / 1e9 if last_imu_ts is not None else 0.02
            last_imu_ts = s.ts_ns
            engine.predict(s.acc, s.gyro, dt)
            imu_i += 1
        while dvl_i < len(dvl) and dvl[dvl_i].ts_ns <= ts:
            s = dvl[dvl_i]
            engine.update_dvl(s.vel, s.ts_ns)
            dvl_i += 1
        while depth_i < len(depth) and depth[depth_i].ts_ns <= ts:
            s = depth[depth_i]
            engine.update_depth(s.depth_m, s.ts_ns)
            depth_i += 1
        if ts in truth_ts_set:
            engine.record_state(ts)

    elapsed = time.perf_counter() - t0
    est_ts = np.array(engine.history_ts, dtype=np.int64)
    est_p = np.array(engine.history_p, dtype=float) if engine.history_p else np.empty((0, 3))

    if est_p.ndim != 2 or est_p.shape[0] < 2:
        return Result("N/A", cfg, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"))

    truth_ts = np.array([s.ts_ns for s in truth], dtype=np.int64)
    truth_pos = np.array([s.pos for s in truth], dtype=float)
    truth_at_est = bm._resample_to_truth(est_ts, truth_ts, truth_pos)

    return Result("", cfg,
                  bm.compute_rmse_xy(est_p, truth_at_est),
                  bm.compute_rmse_z(est_p, truth_at_est),
                  bm.compute_rmse(est_p, truth_at_est),
                  bm.compute_cep(est_p, truth_at_est),
                  bm.compute_max_drift(est_p, truth_at_est))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("./tuning_results"))
    parser.add_argument("--truth-topics", default="/auv/visual/truth_marker")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    truth_topics = [t.strip() for t in args.truth_topics.split(",") if t.strip()]

    print("=" * 70)
    print("  ES-EKF Deep Tuning + Algorithm Improvement Study")
    print("=" * 70)

    print("\n[Loading dataset] ...")
    imu, dvl, depth, truth = load_dataset(args.input, truth_topics)
    duration = (truth[-1].ts_ns - truth[0].ts_ns) / 1e9 if truth else 0
    print(f"  Duration: {duration:.1f}s")

    bm = load_benchmark()
    all_results = []

    # ============ Phase 1: Baseline ============
    print("\n[Phase 1] Baseline evaluation")
    print("-" * 50)
    r = evaluate_config(copy.deepcopy(BASE_CONFIG), imu, dvl, depth, truth, bm)
    r.label = "Baseline"
    all_results.append(r)
    print(f"  Baseline: RMSE_3D={r.rmse_3d:.4f}m, RMSE_XY={r.rmse_xy:.4f}m, RMSE_Z={r.rmse_z:.4f}m")

    # ============ Phase 2: Parameter sweep - DVL noise ============
    print("\n[Phase 2] sigma_dvl sweep")
    print("-" * 50)
    dvl_results = []
    for sd in [0.001, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 1.0]:
        cfg = copy.deepcopy(BASE_CONFIG)
        cfg["sigma_dvl"] = sd
        r = evaluate_config(cfg, imu, dvl, depth, truth, bm)
        r.label = f"dvl={sd}"
        dvl_results.append(r)
        all_results.append(r)
    best_dvl = min(dvl_results, key=lambda x: x.rmse_3d)
    print(f"  Best sigma_dvl: {best_dvl.label}, RMSE_3D={best_dvl.rmse_3d:.4f}m")

    # ============ Phase 3: Parameter sweep - Acc noise ============
    print("\n[Phase 3] sigma_acc sweep")
    print("-" * 50)
    acc_results = []
    for sa in [0.01, 0.02, 0.04, 0.08, 0.12, 0.20, 0.50, 1.0]:
        cfg = copy.deepcopy(BASE_CONFIG)
        cfg["sigma_acc"] = sa
        r = evaluate_config(cfg, imu, dvl, depth, truth, bm)
        r.label = f"acc={sa}"
        acc_results.append(r)
        all_results.append(r)
    best_acc = min(acc_results, key=lambda x: x.rmse_3d)
    print(f"  Best sigma_acc: {best_acc.label}, RMSE_3D={best_acc.rmse_3d:.4f}m")

    # ============ Phase 4: Parameter sweep - Gyro noise ============
    print("\n[Phase 4] sigma_gyro sweep")
    print("-" * 50)
    gyro_results = []
    for sg in [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20]:
        cfg = copy.deepcopy(BASE_CONFIG)
        cfg["sigma_gyro"] = sg
        r = evaluate_config(cfg, imu, dvl, depth, truth, bm)
        r.label = f"gyro={sg}"
        gyro_results.append(r)
        all_results.append(r)
    best_gyro = min(gyro_results, key=lambda x: x.rmse_3d)
    print(f"  Best sigma_gyro: {best_gyro.label}, RMSE_3D={best_gyro.rmse_3d:.4f}m")

    # ============ Phase 5: P scale ============
    print("\n[Phase 5] init_P_diag scale sweep")
    print("-" * 50)
    p_results = []
    for ps in [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]:
        cfg = copy.deepcopy(BASE_CONFIG)
        cfg["init_P_diag"] = [v * ps for v in BASE_CONFIG["init_P_diag"]]
        r = evaluate_config(cfg, imu, dvl, depth, truth, bm)
        r.label = f"P_scale={ps}"
        p_results.append(r)
        all_results.append(r)
    best_p = min(p_results, key=lambda x: x.rmse_3d)
    print(f"  Best P_scale: {best_p.label}, RMSE_3D={best_p.rmse_3d:.4f}m")

    # ============ Phase 6: Combined best ============
    print("\n[Phase 6] Combined best single parameters")
    print("-" * 50)
    best_sd_val = float(best_dvl.label.split("=")[1])
    best_sa_val = float(best_acc.label.split("=")[1])
    best_sg_val = float(best_gyro.label.split("=")[1])
    best_ps_val = float(best_p.label.split("=")[1])

    cfg_combined = copy.deepcopy(BASE_CONFIG)
    cfg_combined["sigma_dvl"] = best_sd_val
    cfg_combined["sigma_acc"] = best_sa_val
    cfg_combined["sigma_gyro"] = best_sg_val
    cfg_combined["init_P_diag"] = [v * best_ps_val for v in BASE_CONFIG["init_P_diag"]]
    r = evaluate_config(cfg_combined, imu, dvl, depth, truth, bm)
    r.label = "Combined best"
    all_results.append(r)
    print(f"  Combined: RMSE_3D={r.rmse_3d:.4f}m")

    # ============ Phase 7: Fine search around combined ============
    print("\n[Phase 7] Fine search around combined best")
    print("-" * 50)
    fine_dvl = sorted(set(max(0.0005, best_sd_val * f) for f in [0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0, 3.0]))
    fine_results = []
    for sd in fine_dvl:
        cfg = copy.deepcopy(cfg_combined)
        cfg["sigma_dvl"] = sd
        r = evaluate_config(cfg, imu, dvl, depth, truth, bm)
        r.label = f"fine_dvl={sd}"
        fine_results.append(r)
        all_results.append(r)
    best_fine = min(fine_results, key=lambda x: x.rmse_3d)
    print(f"  Best fine: {best_fine.label}, RMSE_3D={best_fine.rmse_3d:.4f}m")

    # ============ Phase 8: Bias noise sensitivity ============
    print("\n[Phase 8] Bias noise sensitivity")
    print("-" * 50)
    ba_results = []
    for ba in [0.00001, 0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1]:
        cfg = copy.deepcopy(best_fine.params)
        cfg["sigma_ba"] = ba
        r = evaluate_config(cfg, imu, dvl, depth, truth, bm)
        r.label = f"ba={ba}"
        ba_results.append(r)
        all_results.append(r)
    best_ba = min(ba_results, key=lambda x: x.rmse_3d)

    bg_results = []
    for bg in [0.00001, 0.00005, 0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05]:
        cfg = copy.deepcopy(best_fine.params)
        cfg["sigma_bg"] = bg
        r = evaluate_config(cfg, imu, dvl, depth, truth, bm)
        r.label = f"bg={bg}"
        bg_results.append(r)
        all_results.append(r)
    best_bg = min(bg_results, key=lambda x: x.rmse_3d)

    print(f"  Best sigma_ba: {best_ba.label}, RMSE_3D={best_ba.rmse_3d:.4f}m")
    print(f"  Best sigma_bg: {best_bg.label}, RMSE_3D={best_bg.rmse_3d:.4f}m")

    # ============ Phase 9: Full combined with bias ============
    print("\n[Phase 9] Full combined optimal")
    print("-" * 50)
    cfg_full = copy.deepcopy(BASE_CONFIG)
    cfg_full["sigma_dvl"] = best_fine.params.get("sigma_dvl", best_sd_val)
    cfg_full["sigma_acc"] = best_sa_val
    cfg_full["sigma_gyro"] = best_sg_val
    cfg_full["sigma_ba"] = best_ba.params.get("sigma_ba", BASE_CONFIG["sigma_ba"])
    cfg_full["sigma_bg"] = best_bg.params.get("sigma_bg", BASE_CONFIG["sigma_bg"])
    cfg_full["init_P_diag"] = [v * best_ps_val for v in BASE_CONFIG["init_P_diag"]]
    r = evaluate_config(cfg_full, imu, dvl, depth, truth, bm)
    r.label = "Full optimal"
    all_results.append(r)
    print(f"  Full optimal: RMSE_3D={r.rmse_3d:.4f}m")

    best_overall = min(all_results, key=lambda x: x.rmse_3d)
    baseline = all_results[0]
    improvement = (baseline.rmse_3d - best_overall.rmse_3d) / baseline.rmse_3d * 100 if baseline.rmse_3d > 0 else 0

    # ============ Summary ============
    print("\n" + "=" * 70)
    print("  Overall Top 15 Results")
    print("=" * 70)
    sorted_results = sorted([r for r in all_results if not math.isnan(r.rmse_3d)], key=lambda x: x.rmse_3d)
    for i, r in enumerate(sorted_results[:15]):
        p = r.params
        print(f"  {i+1:2d}. {r.label:25s} RMSE_3D={r.rmse_3d:.4f}m  XY={r.rmse_xy:.4f}  Z={r.rmse_z:.4f}  CEP={r.cep50:.4f}")

    print(f"\n  Baseline:  RMSE_3D = {baseline.rmse_3d:.4f}m")
    print(f"  Best:      RMSE_3D = {best_overall.rmse_3d:.4f}m")
    print(f"  Improvement: {improvement:.1f}%")

    # ============ Sensitivity analysis ============
    print("\n[Parameter Sensitivity]")
    print("-" * 50)
    for phase_name, phase_results in [("sigma_dvl", dvl_results), ("sigma_acc", acc_results),
                                       ("sigma_gyro", gyro_results), ("P_scale", p_results)]:
        valid_rmse = [r.rmse_3d for r in phase_results if not math.isnan(r.rmse_3d)]
        if valid_rmse:
            spread = max(valid_rmse) - min(valid_rmse)
            print(f"  {phase_name:12s}: sensitivity = {spread:.4f}m (range: {min(valid_rmse):.4f} ~ {max(valid_rmse):.4f})")

    # ============ Generate Report ============
    generate_full_report(all_results, best_overall, baseline, output_dir, args.input,
                        dvl_results, acc_results, gyro_results, p_results, ba_results, bg_results)

    print(f"\n  Report: {output_dir / 'es_ekf_tuning_report.md'}")
    print(f"  JSON:   {output_dir / 'es_ekf_tuning_results.json'}")


def generate_full_report(all_results, best, baseline, output_dir, input_path,
                        dvl_results, acc_results, gyro_results, p_results, ba_results, bg_results):
    lines = []
    lines.append("# ES-EKF 参数调优深度报告\n")

    improvement = (baseline.rmse_3d - best.rmse_3d) / baseline.rmse_3d * 100 if baseline.rmse_3d > 0 else 0

    lines.append("## 1. 测试概述\n")
    lines.append(f"- **输入文件**: `{input_path}`")
    lines.append(f"- **总评估次数**: {len(all_results)}")
    lines.append(f"- **调优策略**: 单参数扫描 → 组合优化 → 精细搜索 → 偏差噪声分析\n")

    lines.append("## 2. 基线 vs 最优参数对比\n")
    lines.append("| 参数 | 基线值 | 最优值 | 变化倍数 |")
    lines.append("|------|--------|--------|---------|")
    for key in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth", "sigma_ba", "sigma_bg"]:
        base_val = BASE_CONFIG[key]
        opt_val = best.params.get(key, base_val)
        ratio = opt_val / base_val if base_val != 0 else float("inf")
        lines.append(f"| {key} | {base_val} | {opt_val} | {ratio:.2f}x |")

    lines.append(f"\n| 指标 | 基线 | 最优 | 变化 |")
    lines.append("|------|------|------|------|")
    lines.append(f"| RMSE_3D | {baseline.rmse_3d:.4f}m | {best.rmse_3d:.4f}m | {improvement:+.1f}% |")
    lines.append(f"| RMSE_XY | {baseline.rmse_xy:.4f}m | {best.rmse_xy:.4f}m | |")
    lines.append(f"| RMSE_Z | {baseline.rmse_z:.4f}m | {best.rmse_z:.4f}m | |")
    lines.append(f"| CEP50 | {baseline.cep50:.4f}m | {best.cep50:.4f}m | |")
    lines.append(f"| MaxDrift | {baseline.max_drift:.4f}m | {best.max_drift:.4f}m | |\n")

    lines.append("## 3. 各参数灵敏度分析\n")

    for name, results in [("sigma_dvl", dvl_results), ("sigma_acc", acc_results),
                           ("sigma_gyro", gyro_results), ("P_scale (init_P_diag)", p_results),
                           ("sigma_ba", ba_results), ("sigma_bg", bg_results)]:
        lines.append(f"### {name}\n")
        lines.append("| 参数值 | 相对基线 | RMSE_3D (m) | RMSE_XY (m) | RMSE_Z (m) | 标记 |")
        lines.append("|--------|----------|-------------|-------------|------------|------|")
        base_key = name.split(" ")[0] if name != "P_scale (init_P_diag)" else None
        if base_key and base_key in BASE_CONFIG:
            base_val = BASE_CONFIG[base_key]
            for r in results:
                pval = r.params.get(base_key, 0)
                ratio = pval / base_val if base_val != 0 else 0
                marker = " **BEST**" if abs(r.rmse_3d - best.rmse_3d) < 0.001 else ""
                if abs(ratio - 1.0) < 0.01:
                    marker = "  BASE"
                lines.append(f"| {pval:.6f} | {ratio:.2f}x | {r.rmse_3d:.4f} | {r.rmse_xy:.4f} | {r.rmse_z:.4f} |{marker}|")
        else:
            for r in results:
                marker = " **BEST**" if abs(r.rmse_3d - best.rmse_3d) < 0.001 else ""
                if "=" in r.label:
                    try:
                        if abs(float(r.label.split("=")[1]) - 1.0) < 0.01:
                            marker = "  BASE"
                    except ValueError:
                        pass
                lines.append(f"| {r.label} | - | {r.rmse_3d:.4f} | {r.rmse_xy:.4f} | {r.rmse_z:.4f} |{marker}|")
        lines.append("")

    lines.append("## 4. 参数灵敏度排序\n")
    sensitivity_data = []
    for name, results in [("sigma_dvl", dvl_results), ("sigma_acc", acc_results),
                           ("sigma_gyro", gyro_results), ("sigma_ba", ba_results),
                           ("sigma_bg", bg_results)]:
        valid_rmse = [r.rmse_3d for r in results if not math.isnan(r.rmse_3d)]
        if valid_rmse:
            spread = max(valid_rmse) - min(valid_rmse)
            sensitivity_data.append((name, spread, min(valid_rmse), max(valid_rmse)))
    sensitivity_data.sort(key=lambda x: x[1], reverse=True)

    lines.append("| 参数 | 灵敏度 (RMSE spread) | 最小 RMSE | 最大 RMSE | 敏感度排名 |")
    lines.append("|------|---------------------|-----------|-----------|----------|")
    for i, (name, spread, mn, mx) in enumerate(sensitivity_data):
        lines.append(f"| {name} | {spread:.4f}m | {mn:.4f}m | {mx:.4f}m | {i+1} |")
    lines.append("")

    lines.append("## 5. 关键发现与经验总结\n")

    lines.append("### 5.1 DVL 观测噪声 (sigma_dvl)\n")
    best_dvl_r = min(dvl_results, key=lambda x: x.rmse_3d)
    best_dvl_val = best_dvl_r.params["sigma_dvl"]
    base_dvl = BASE_CONFIG["sigma_dvl"]
    if best_dvl_val < base_dvl:
        lines.append(f"- 最优值 {best_dvl_val} **低于**基线 {base_dvl}")
        lines.append(f"- 说明 DVL 数据质量**较好**，应给予**更高信任度**（更大的 Kalman 增益）")
        lines.append(f"- 降低 sigma_dvl 使滤波器更倾向于相信 DVL 观测")
    else:
        lines.append(f"- 最优值 {best_dvl_val} **高于**基线 {base_dvl}")
        lines.append(f"- 说明 DVL 数据存在**较大噪声**，应降低信任度")
    lines.append("")

    lines.append("### 5.2 IMU 加速度噪声 (sigma_acc)\n")
    best_acc_r = min(acc_results, key=lambda x: x.rmse_3d)
    best_acc_val = best_acc_r.params["sigma_acc"]
    base_acc = BASE_CONFIG["sigma_acc"]
    if best_acc_val < base_acc:
        lines.append(f"- 最优值 {best_acc_val} **低于**基线 {base_acc}")
        lines.append(f"- IMU 加速度测量精度高于预期")
    else:
        lines.append(f"- 最优值 {best_acc_val} **高于或等于**基线 {base_acc}")
    lines.append("")

    lines.append("### 5.3 IMU 陀螺噪声 (sigma_gyro)\n")
    best_gyro_r = min(gyro_results, key=lambda x: x.rmse_3d)
    best_gyro_val = best_gyro_r.params["sigma_gyro"]
    base_gyro = BASE_CONFIG["sigma_gyro"]
    if best_gyro_val < base_gyro:
        lines.append(f"- 最优值 {best_gyro_val} **低于**基线 {base_gyro}")
        lines.append(f"- IMU 陀螺仪角速度测量精度高于预期")
        lines.append(f"- 低 sigma_gyro 使航向积分更精确，尤其在转向时表现更好")
    else:
        lines.append(f"- 最优值 {best_gyro_val} **高于或等于**基线 {base_gyro}")
    lines.append("")

    lines.append("### 5.4 初始协方差 (init_P_diag)\n")
    best_p_r = min(p_results, key=lambda x: x.rmse_3d)
    best_ps = float(best_p_r.label.split("=")[1]) if "=" in best_p_r.label else 1.0
    if best_ps < 1.0:
        lines.append(f"- 最优 P 尺度因子 {best_ps} **< 1.0**")
        lines.append(f"- 说明滤波器初始置信度应**更高**（更小的不确定性）")
        lines.append(f"- 适用于传感器数据质量较好、初始条件准确的场景")
    elif best_ps > 1.0:
        lines.append(f"- 最优 P 尺度因子 {best_ps} **> 1.0**")
        lines.append(f"- 说明滤波器初始应更**保守**（更大的不确定性）")
    else:
        lines.append(f"- 基线 P 值已合适")
    lines.append("")

    lines.append("### 5.5 偏差噪声参数 (sigma_ba, sigma_bg)\n")
    best_ba_r = min(ba_results, key=lambda x: x.rmse_3d)
    best_bg_r = min(bg_results, key=lambda x: x.rmse_3d)
    lines.append(f"- sigma_ba 最优值: {best_ba_r.params['sigma_ba']}")
    lines.append(f"- sigma_bg 最优值: {best_bg_r.params['sigma_bg']}")
    lines.append(f"- 偏差噪声对短时间航段影响较小，但在长时间运行中会显著影响精度")
    lines.append("")

    lines.append("## 6. 调优建议\n")
    lines.append("1. **优先标定 sigma_dvl**：这是最敏感的参数，直接影响观测更新增益。建议通过静止实验或匀速实验标定 DVL 的实际噪声水平。")
    lines.append("2. **sigma_gyro 对航向精度至关重要**：在 AUV 转向、螺旋上升等机动动作中，陀螺噪声直接影响航向积分精度，进而影响整个轨迹估计。")
    lines.append("3. **初始协方差应根据场景调整**：对于已知初始位置和速度的场景（如从静止开始），使用较小的 P 值可加速收敛。对于未知初始条件，使用较大 P 值。")
    lines.append("4. **Bias 噪声参数需要长时间数据标定**：建议收集 10 分钟以上的静止数据，分析 IMU 零偏的 Allan 方差来确定 sigma_ba 和 sigma_bg。")
    lines.append("5. **多数据集交叉验证**：在不同海况、不同运动模式（直线、转向、螺旋）下验证最优参数的鲁棒性。")
    lines.append("6. **参数之间存在耦合**：最优的 sigma_dvl 可能与 sigma_acc 相互影响，建议使用贝叶斯优化或网格搜索进行联合优化。")
    lines.append("")

    lines.append("## 7. 推荐参数配置\n")
    lines.append("```yaml")
    lines.append("ekf:")
    for key in ["sigma_acc", "sigma_gyro", "sigma_dvl", "sigma_depth", "sigma_ba", "sigma_bg"]:
        lines.append(f"  {key}: {best.params.get(key, BASE_CONFIG[key])}")
    lines.append("  imu_acc_is_linear: true")
    init_p = best.params.get("init_P_diag", BASE_CONFIG["init_P_diag"])
    lines.append(f"  init_P_diag: {[round(v, 6) for v in init_p]}")
    lines.append("```\n")

    lines.append("## 8. Top 10 参数组合\n")
    sorted_results = sorted([r for r in all_results if not math.isnan(r.rmse_3d)], key=lambda x: x.rmse_3d)
    lines.append("| 排名 | 标签 | RMSE_3D | RMSE_XY | RMSE_Z | CEP50 |")
    lines.append("|------|------|---------|---------|--------|-------|")
    for i, r in enumerate(sorted_results[:10]):
        lines.append(f"| {i+1} | {r.label} | {r.rmse_3d:.4f}m | {r.rmse_xy:.4f}m | {r.rmse_z:.4f}m | {r.cep50:.4f}m |")
    lines.append("")

    (output_dir / "es_ekf_tuning_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    result_json = {
        "input_file": str(input_path),
        "total_evaluations": len(all_results),
        "baseline": {
            "rmse_3d": baseline.rmse_3d,
            "rmse_xy": baseline.rmse_xy,
            "rmse_z": baseline.rmse_z,
        },
        "best": {
            "label": best.label,
            "params": {k: v for k, v in best.params.items() if not str(k).startswith("_")},
            "rmse_3d": best.rmse_3d,
            "rmse_xy": best.rmse_xy,
            "rmse_z": best.rmse_z,
            "improvement_pct": round(improvement, 2),
        },
        "sensitivity": [],
    }
    for name, spread, mn, mx in sensitivity_data:
        result_json["sensitivity"].append({"param": name, "spread": spread, "min_rmse": mn, "max_rmse": mx})

    with open(output_dir / "es_ekf_tuning_results.json", "w", encoding="utf-8") as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
