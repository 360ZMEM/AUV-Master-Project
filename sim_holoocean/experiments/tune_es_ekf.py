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
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(config_path=None):
    if config_path is None:
        config_path = str(STACK_ROOT / "config" / "sim_params.yaml")
    base = load_config(config_path)

    candidates = [
        {"name": "world_dvl", "dvl_frame": "world", "sigma_dvl": 0.03},
        {"name": "body_dvl", "dvl_frame": "body", "sigma_dvl": 0.03},
    ]

    results = []
    for c in candidates:
        cfg = deepcopy(base)
        cfg.setdefault("es_ekf_experiment", {})
        cfg["es_ekf_experiment"]["dvl_frame"] = c["dvl_frame"]
        cfg["es_ekf_experiment"]["sigma_dvl"] = c["sigma_dvl"]
        cfg["es_ekf_experiment"]["save_plot"] = f"es_ekf_xy_map_{c['name']}.png"
        cfg["es_ekf_experiment"]["save_results"] = f"es_ekf_results_{c['name']}.npz"
        metrics = run_experiment(cfg, enable_plot=False, max_steps_override=260)
        results.append((c["name"], metrics))

    results.sort(key=lambda x: x[1]["rmse_all"])
    print("\n=== ES-EKF tuning summary ===")
    for name, m in results:
        print(f"{name:12s} rmse_all={m['rmse_all']:.3f} rmse_gps_on={m['rmse_gps_on']:.3f} rmse_gps_off={m['rmse_gps_off']:.3f} final_error={m['final_error']:.3f}")


if __name__ == "__main__":
    main()
