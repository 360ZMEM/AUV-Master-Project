import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUV_CONTROL_SRC = PROJECT_ROOT / "brain_linux" / "src" / "auv_control"
if str(AUV_CONTROL_SRC) not in sys.path:
    sys.path.insert(0, str(AUV_CONTROL_SRC))

from auv_decision_ros.cable_prior_adapter import (  # noqa: E402
    ensure_auv_master_mag_on_path,
    load_cable_map_from_config,
    yaml_points_to_cable_map,
)


def test_yaml_points_to_cable_map_uses_xy_and_z_as_burial():
    ensure_auv_master_mag_on_path(PROJECT_ROOT)

    cable_map = yaml_points_to_cable_map(
        [[0.0, 0.0, -1.5], [10.0, 2.0, -1.6]],
        frame="local_ned",
    )

    assert cable_map.frame == "local_ned"
    assert np.allclose(cable_map.points_xy_m, [[0.0, 0.0], [10.0, 2.0]])
    assert np.allclose(cable_map.burial_depth_m, [1.5, 1.6])


def test_load_cable_map_from_inline_yaml_prior():
    cable_map = load_cable_map_from_config(
        {
            "auv_master_mag_root": "AUV-Master-Mag",
            "prior": {
                "format": "yaml",
                "frame": "inspection_ned",
                "yaml_points_ned": [[0.0, 0.0], [5.0, 0.5], [10.0, 1.0]],
                "burial_depth_m": 1.2,
            },
        },
        project_root=PROJECT_ROOT,
    )

    assert cable_map.frame == "inspection_ned"
    assert np.allclose(cable_map.points_xy_m[:, 0], [0.0, 5.0, 10.0])
    assert cable_map.burial_depth_m == 1.2


def test_load_cable_map_from_csv_prior(tmp_path):
    csv_path = tmp_path / "cable.csv"
    csv_path.write_text("x_m,y_m,burial_depth_m\n0,0,1.0\n10,0,1.1\n", encoding="utf-8")

    cable_map = load_cable_map_from_config(
        {
            "auv_master_mag_root": "AUV-Master-Mag",
            "prior": {
                "format": "auto",
                "path": str(csv_path),
                "frame": "local_ned",
            },
        },
        project_root=PROJECT_ROOT,
    )

    assert np.allclose(cable_map.points_xy_m, [[0.0, 0.0], [10.0, 0.0]])
    assert np.allclose(cable_map.burial_depth_m, [1.0, 1.1])
