from auv_decision_ros.sensor_runtime import SensorWatch, build_runtime_status_snapshot


def test_magnetic_loss_only_degrades_cable_inspection():
    watches = {
        "navigation": SensorWatch(
            name="navigation",
            topic="/auv/state/filtered",
            msg_type="nav_msgs/msg/Odometry",
            timeout_s=0.5,
            required=True,
            last_rx_monotonic_s=10.0,
            message_count=5,
        ),
        "magnetic": SensorWatch(
            name="magnetic",
            topic="/auv/sensors/magnetic",
            msg_type="sensor_msgs/msg/MagneticField",
            timeout_s=0.5,
            required=False,
            last_rx_monotonic_s=1.0,
            message_count=5,
        ),
    }

    snapshot = build_runtime_status_snapshot(
        watches,
        {
            "autonomy_core": ["navigation"],
            "cable_inspection": ["navigation", "magnetic"],
        },
        now_s=10.2,
    )

    assert snapshot["healthy"] is True
    assert snapshot["capabilities"]["autonomy_core"]["available"] is True
    assert snapshot["capabilities"]["cable_inspection"]["available"] is False
    assert snapshot["capabilities"]["cable_inspection"]["missing_sensors"] == ["magnetic"]
    assert snapshot["degraded_capabilities"] == ["cable_inspection"]


def test_navigation_loss_degrades_core_autonomy():
    watches = {
        "navigation": SensorWatch(
            name="navigation",
            topic="/auv/state/filtered",
            msg_type="nav_msgs/msg/Odometry",
            timeout_s=0.5,
            required=True,
            last_rx_monotonic_s=1.0,
            message_count=5,
        ),
        "magnetic": SensorWatch(
            name="magnetic",
            topic="/auv/sensors/magnetic",
            msg_type="sensor_msgs/msg/MagneticField",
            timeout_s=0.5,
            required=False,
            last_rx_monotonic_s=10.0,
            message_count=5,
        ),
    }

    snapshot = build_runtime_status_snapshot(
        watches,
        {
            "autonomy_core": ["navigation"],
            "cable_inspection": ["navigation", "magnetic"],
        },
        now_s=10.2,
    )

    assert snapshot["healthy"] is False
    assert snapshot["missing_required_sensors"] == ["navigation"]
    assert snapshot["capabilities"]["autonomy_core"]["available"] is False
    assert snapshot["capabilities"]["cable_inspection"]["available"] is False
