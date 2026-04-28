"""
ES-EKF 参数调优脚本 - 批量运行实验并比较结果。

该脚本用于自动化调优 ES-EKF 滤波器参数，运行多个候选配置并排序输出结果。

调优目标：
  - DVL 坐标系选择（world vs body）
  - 传感器噪声参数（sigma_dvl）
  - 其他可扩展参数

使用方式：
  python sim_holoocean/experiments/tune_es_ekf.py

输出示例：
  === ES-EKF tuning summary ===
  body_dvl    rmse_all=0.423 rmse_gps_on=0.512 rmse_gps_off=0.234 final_error=0.189
  world_dvl   rmse_all=0.567 rmse_gps_on=0.678 rmse_gps_off=0.345 final_error=0.234
"""

from copy import deepcopy
from pathlib import Path
import sys

import yaml

STACK_ROOT = Path(__file__).resolve().parents[1]
for folder in ["5_experiment"]:
    p = str(STACK_ROOT / folder)
    if p not in sys.path:
        sys.path.insert(0, p)

from es_ekf import run_experiment


def load_config(path):
    """从 YAML 文件加载配置。"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(config_path=None):
    """
    运行 ES-EKF 参数调优实验。

    流程：
      1. 加载基础配置
      2. 定义候选参数集
      3. 对每个候选：
         - 修改配置中的参数
         - 运行实验
         - 收集误差指标
      4. 按 rmse_all 排序并输出结果

    参数：
        config_path (str or None)：配置文件路径，默认使用 config/sim_params.yaml
    """
    if config_path is None:
        config_path = str(STACK_ROOT / "config" / "sim_params.yaml")
    base = load_config(config_path)

    # ────────────────────────────────────────────────
    # 定义候选参数集
    # ────────────────────────────────────────────────
    candidates = [
        {"name": "world_dvl", "dvl_frame": "world", "sigma_dvl": 0.03},
        {"name": "body_dvl", "dvl_frame": "body", "sigma_dvl": 0.03},
    ]

    results = []
    for c in candidates:
        # ────────────────────────────────────────────────
        # 修改配置
        # ────────────────────────────────────────────────
        cfg = deepcopy(base)
        cfg.setdefault("es_ekf_experiment", {})
        cfg["es_ekf_experiment"]["dvl_frame"] = c["dvl_frame"]
        cfg["es_ekf_experiment"]["sigma_dvl"] = c["sigma_dvl"]
        cfg["es_ekf_experiment"]["save_plot"] = f"es_ekf_xy_map_{c['name']}.png"
        cfg["es_ekf_experiment"]["save_results"] = f"es_ekf_results_{c['name']}.npz"

        # ────────────────────────────────────────────────
        # 运行实验
        # ────────────────────────────────────────────────
        metrics = run_experiment(cfg, enable_plot=False, max_steps_override=260)
        results.append((c["name"], metrics))

    # ────────────────────────────────────────────────
    # 排序并输出结果
    # ────────────────────────────────────────────────
    results.sort(key=lambda x: x[1]["rmse_all"])
    print("\n=== ES-EKF tuning summary ===")
    for name, m in results:
        print(f"{name:12s} rmse_all={m['rmse_all']:.3f} rmse_gps_on={m['rmse_gps_on']:.3f} rmse_gps_off={m['rmse_gps_off']:.3f} final_error={m['final_error']:.3f}")


if __name__ == "__main__":
    main()
