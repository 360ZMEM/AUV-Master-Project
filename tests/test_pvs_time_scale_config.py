import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIM_INTERFACES = PROJECT_ROOT / "sim_holoocean" / "interfaces"
if str(SIM_INTERFACES) not in sys.path:
    sys.path.insert(0, str(SIM_INTERFACES))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from holoocean_physics_bridge import HoloOceanPhysicsZenohBridge  # noqa: E402


class _Guard:
    pass


def _minimal_config(time_scale: float = 5.0):
    return {
        "simulation": {
            "agent_name": "auv0",
            "realtime": True,
            "time_scale": time_scale,
        },
        "bridge": {
            "rate_hz": 50.0,
            "default_command": [0, 0, 0, 0, 0],
        },
        "cable_path": {
            "points_ned": [[0.0, 0.0, 12.0], [10.0, 0.0, 12.0]],
        },
        "digital_twin": {},
    }


def test_bridge_reads_time_scale_without_changing_sim_dt():
    bridge = HoloOceanPhysicsZenohBridge(_minimal_config(time_scale=4.0), _Guard())

    assert bridge.dt == 0.02
    assert bridge.time_scale == 4.0
    assert bridge.realtime is True
    assert bridge.dt / bridge.time_scale == 0.005


def test_bridge_clamps_invalid_time_scale_to_positive_value():
    bridge = HoloOceanPhysicsZenohBridge(_minimal_config(time_scale=0.0), _Guard())

    assert bridge.time_scale > 0.0
