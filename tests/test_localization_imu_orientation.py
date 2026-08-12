from types import SimpleNamespace

import numpy as np

from auv_localization.auv_localization_node import AUVLocalizationNode


class _FakeFilter:
    def __init__(self) -> None:
        self.quat = None

    def initialize_from_observation(self, *, quat=None, **_kwargs) -> None:
        self.quat = np.asarray(quat, dtype=float)


def _imu_msg(quat):
    return SimpleNamespace(
        linear_acceleration=SimpleNamespace(x=0.0, y=0.0, z=0.0),
        angular_velocity=SimpleNamespace(x=0.0, y=0.0, z=0.0),
        orientation=SimpleNamespace(
            w=float(quat[0]),
            x=float(quat[1]),
            y=float(quat[2]),
            z=float(quat[3]),
        ),
        header=SimpleNamespace(stamp=SimpleNamespace(sec=10, nanosec=200)),
    )


def test_imu_orientation_measurement_updates_filter_quaternion() -> None:
    node = AUVLocalizationNode.__new__(AUVLocalizationNode)
    node.use_imu_orientation_measurement = True
    node.filter = _FakeFilter()

    quat = np.array([0.5, 0.0, 0.0, 0.5], dtype=float)
    AUVLocalizationNode._on_imu(node, _imu_msg(quat))

    expected = quat / np.linalg.norm(quat)
    np.testing.assert_allclose(node._last_imu_orientation, expected)
    np.testing.assert_allclose(node.filter.quat, expected)


def test_imu_orientation_measurement_can_remain_output_only() -> None:
    node = AUVLocalizationNode.__new__(AUVLocalizationNode)
    node.use_imu_orientation_measurement = False
    node.filter = _FakeFilter()

    AUVLocalizationNode._on_imu(node, _imu_msg([1.0, 0.0, 0.0, 0.0]))

    assert node.filter.quat is None
