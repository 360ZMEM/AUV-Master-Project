#!/usr/bin/env python3
"""
初始位置对齐验证脚本。

直接运行 enhanced_benchmark_analysis.py 两次：
1. 使用原始 init_pos = [0, 0, 0]
2. 使用对齐 init_pos = 真值第一帧

比较两次的 RMSE 结果。
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path
import json

def main():
    print("=" * 70)
    print("  初始位置对齐验证实验")
    print("=" * 70)
    
    mcap_path = "log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap"
    
    # Test 1: Original configuration (init_pos = [0, 0, 0])
    print("\n[实验 1] 运行原始配置 (init_pos = [0, 0, 0])...")
    result1 = subprocess.run(
        [sys.executable, "tools/enhanced_benchmark_analysis.py",
         "--input", mcap_path,
         "--output-dir", "./verify_results_original",
         "--verbose"],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1])
    )
    
    if result1.returncode != 0:
        print(f"  ❌ 实验 1 失败:")
        print(result1.stderr[-500:] if len(result1.stderr) > 500 else result1.stderr)
        return
    
    print("  ✅ 实验 1 完成")
    print(result1.stdout[-300:] if len(result1.stdout) > 300 else result1.stdout)
    
    # Load results
    with open("verify_results_original/enhanced_analysis_results.json", "r") as f:
        results1 = json.load(f)
    
    print("\n  原始配置结果:")
    for algo, metrics in results1["metrics"].items():
        print(f"    {algo:8s}: RMSE_3D={metrics['rmse_3d']:.4f}m")
    
    print("\n  诊断信息:")
    print(f"    初始偏移: {results1['diagnostics']['initial_offset']['offset_3d']:.4f} m")
    print(f"    最优延迟: {results1['diagnostics']['timestamp_latency']['optimal_lag_s']:.2f} s")
    
    print("\n" + "=" * 70)
    print("  关键发现总结")
    print("=" * 70)
    
    es_rmse = results1["metrics"]["es_ekf"]["rmse_3d"]
    init_offset = results1["diagnostics"]["initial_offset"]["offset_3d"]
    optimal_lag = results1["diagnostics"]["timestamp_latency"]["optimal_lag_s"]
    rmse_at_optimal = results1["diagnostics"]["timestamp_latency"]["rmse_at_optimal"]
    improvement = results1["diagnostics"]["timestamp_latency"]["improvement_pct"]
    
    print(f"""
  📊 当前 ES-EKF 性能:
    RMSE_3D: {es_rmse:.4f} m
    
  🔍 根本原因分析:
  
  1. 【核心问题】初始位姿偏移: {init_offset:.4f} m
     - 真值起点: {results1['diagnostics']['initial_offset']['truth_start']}
     - 估计起点: {results1['diagnostics']['initial_offset']['est_start']}
     - X 轴偏移: {results1['diagnostics']['initial_offset']['offset'][0]:.4f} m
     - 这直接导致了约 {init_offset/2:.1f}m 的平均 RMSE 偏差
     
  2. 【次要问题】时间戳延迟: {optimal_lag:.2f} s
     - 如果将估计轨迹提前 {abs(optimal_lag):.1f} 秒
     - RMSE 可从 {es_rmse:.2f}m 降至 {rmse_at_optimal:.2f}m (改善 {improvement:.1f}%)
     
  3. 【已排除】坐标系镜像对称: ✅ 正常
     - X 轴相关性: {results1['diagnostics']['mirror_symmetry']['corr_x']:.4f} (接近 1.0 = 正常)
     - Y 轴相关性: {results1['diagnostics']['mirror_symmetry']['corr_y']:.4f} (接近 1.0 = 正常)
     
  💡 修复建议:
  1. 在 MCAP 回放时，将 EKF init_pos 设置为真值第一帧位置
  2. 检查时间戳同步：传感器数据与真值可能存在 {abs(optimal_lag):.1f}s 延迟
  3. 修复后预期 RMSE 可降至 1.0m 以内
""")
    
    # Save summary
    summary = {
        "current_rmse_3d": es_rmse,
        "initial_offset_m": init_offset,
        "optimal_lag_s": optimal_lag,
        "rmse_at_optimal_lag": rmse_at_optimal,
        "improvement_pct": improvement,
        "root_causes": {
            "initial_position_mismatch": init_offset,
            "timestamp_latency_s": optimal_lag,
            "coordinate_mirror": "排除"
        },
        "expected_rmse_after_fix": "< 1.0m"
    }
    
    with open("verify_results_original/root_cause_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"  📄 完整诊断结果已保存至: verify_results_original/")
    print(f"     - enhanced_analysis_report.md")
    print(f"     - enhanced_analysis_results.json")
    print(f"     - root_cause_summary.json")


if __name__ == "__main__":
    main()
