#!/usr/bin/env python3
"""Jetson-side magnetic sensor wrapper.

Supports:
- mock publishing for simulation smoke tests
- real FK2301/TMR8637 acquisition through hardware_wrappers/fangkong_adc
"""

from __future__ import annotations

import ast
import math
import threading
import time
from typing import Any

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import MagneticField

from .fangkong_adc_client import (
    DEFAULT_FANGKONG_CONFIG,
    DEFAULT_FANGKONG_ROOT,
    DEFAULT_MAIN_REPO_CALIBRATION,
    DEFAULT_MAIN_REPO_DEVICE_HOST,
    DEFAULT_MAIN_REPO_DEVICE_PORT,
    FangkongAdcMagneticClient,
)


UNIT_TO_TESLA = {
    "tesla": 1.0,
    "microtesla": 1.0e-6,
    "nanotesla": 1.0e-9,
}


class MagneticSensorWrapperNode(Node):
    def __init__(self) -> None:
        super().__init__("magnetic_sensor_wrapper_node")
        self.declare_parameter("output_topic", "/auv/sensors/magnetic")
        self.declare_parameter("frame_id", "mag_link")
        self.declare_parameter("publish_rate_hz", 50.0)
        self.declare_parameter("input_unit", "tesla")
        self.declare_parameter("device_uri", "TODO://configure-device-uri")
        self.declare_parameter("mock_mode", False)
        self.declare_parameter("mock_field_t", [3.0e-5, 0.0, -1.0e-5])
        self.declare_parameter("retry_interval_s", 5.0)
        self.declare_parameter("fangkong_root", DEFAULT_FANGKONG_ROOT)
        self.declare_parameter("fangkong_default_config", DEFAULT_FANGKONG_CONFIG)
        self.declare_parameter("fangkong_user_config", "")
        self.declare_parameter("use_fangkong_user_config", False)
        self.declare_parameter("device_host", DEFAULT_MAIN_REPO_DEVICE_HOST)
        self.declare_parameter("device_port", DEFAULT_MAIN_REPO_DEVICE_PORT)
        self.declare_parameter("connect_timeout_sec", 3.0)
        self.declare_parameter("recv_timeout_sec", 1.0)
        self.declare_parameter("reconnect_interval_sec", 2.0)
        self.declare_parameter("sample_rate_hz", 2000)
        self.declare_parameter("active_channels", [0, 1, 2])
        self.declare_parameter("read_bytes_per_request", 1404)
        self.declare_parameter("sensor_sensitivity_mv_per_ut", [20.02, 19.98, 19.96])
        self.declare_parameter("transport_mode", "poll")
        self.declare_parameter("waveform_y_unit", "magnetic_field")
        self.declare_parameter("calibration_enabled", True)
        self.declare_parameter("calibration_profile_path", DEFAULT_MAIN_REPO_CALIBRATION)
        self.declare_parameter("storage_enabled", False)
        self.declare_parameter("storage_root_dir", "data")
        self.declare_parameter("axis_order", [0, 1, 2])
        self.declare_parameter("axis_signs", [1.0, 1.0, 1.0])

        self.output_topic = str(self.get_parameter("output_topic").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self.input_unit = str(self.get_parameter("input_unit").value).strip().lower()
        self.device_uri = str(self.get_parameter("device_uri").value)
        self.mock_mode = bool(self.get_parameter("mock_mode").value)
        self.mock_field_t = self._parse_vector3(self.get_parameter("mock_field_t").value)
        self.retry_interval_s = float(self.get_parameter("retry_interval_s").value)
        self.fangkong_root = str(self.get_parameter("fangkong_root").value)
        self.fangkong_default_config = str(self.get_parameter("fangkong_default_config").value)
        self.fangkong_user_config = str(self.get_parameter("fangkong_user_config").value).strip()
        self.use_fangkong_user_config = bool(self.get_parameter("use_fangkong_user_config").value)
        self.device_host = str(self.get_parameter("device_host").value)
        self.device_port = int(self.get_parameter("device_port").value)
        self.connect_timeout_sec = float(self.get_parameter("connect_timeout_sec").value)
        self.recv_timeout_sec = float(self.get_parameter("recv_timeout_sec").value)
        self.reconnect_interval_sec = float(self.get_parameter("reconnect_interval_sec").value)
        self.sample_rate_hz = int(self.get_parameter("sample_rate_hz").value)
        self.active_channels = self._parse_int_list(self.get_parameter("active_channels").value)
        self.read_bytes_per_request = int(self.get_parameter("read_bytes_per_request").value)
        self.sensor_sensitivity_mv_per_ut = self._parse_float_list(
            self.get_parameter("sensor_sensitivity_mv_per_ut").value
        )
        self.transport_mode = str(self.get_parameter("transport_mode").value)
        self.waveform_y_unit = str(self.get_parameter("waveform_y_unit").value)
        self.calibration_enabled = bool(self.get_parameter("calibration_enabled").value)
        self.calibration_profile_path = str(self.get_parameter("calibration_profile_path").value)
        self.storage_enabled = bool(self.get_parameter("storage_enabled").value)
        self.storage_root_dir = str(self.get_parameter("storage_root_dir").value)
        self.axis_order = self._parse_int_list(self.get_parameter("axis_order").value)
        self.axis_signs = self._parse_float_list(self.get_parameter("axis_signs").value)

        self.publisher = self.create_publisher(MagneticField, self.output_topic, 10)
        self.timer = self.create_timer(1.0 / max(self.publish_rate_hz, 1.0e-3), self._on_timer)
        self._warn_count = 0
        self._runtime: FangkongAdcMagneticClient | None = None
        self._connect_thread: threading.Thread | None = None
        self._next_retry_monotonic_s = 0.0
        self._last_connect_error = ""
        mode_text = "mock" if self.mock_mode else "fangkong_adc"
        self.get_logger().info(
            f"magnetic wrapper ready mode={mode_text} topic={self.output_topic} frame_id={self.frame_id} "
            f"device_host={self.device_host}"
        )

    @staticmethod
    def _parse_vector3(value: Any) -> list[float]:
        if isinstance(value, str):
            value = ast.literal_eval(value)
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return [float(item) for item in value]
        raise ValueError("mock_field_t must be a 3-element sequence")

    @staticmethod
    def _parse_int_list(value: Any) -> list[int]:
        if isinstance(value, str):
            value = ast.literal_eval(value)
        if isinstance(value, (list, tuple)):
            return [int(item) for item in value]
        raise ValueError("expected a list of integers")

    @staticmethod
    def _parse_float_list(value: Any) -> list[float]:
        if isinstance(value, str):
            value = ast.literal_eval(value)
        if isinstance(value, (list, tuple)):
            return [float(item) for item in value]
        raise ValueError("expected a list of floats")

    def _on_timer(self) -> None:
        if not rclpy.ok():
            return

        sample = self.read_device_sample()
        if sample is None:
            self._warn_count += 1
            if self._warn_count == 1 or self._warn_count % 200 == 0:
                warning = "magnetic wrapper is running without device samples"
                if self._last_connect_error:
                    warning = f"{warning}; last_error={self._last_connect_error}"
                self.get_logger().warning(warning)
            return

        decoded = self.decode_device_sample(sample)
        if decoded is None:
            return

        try:
            bx_t, by_t, bz_t = self._normalize_to_tesla(decoded)
        except (TypeError, ValueError) as exc:
            self.get_logger().warning(f"magnetic wrapper dropped invalid sample: {exc}")
            return

        msg = MagneticField()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.magnetic_field.x = bx_t
        msg.magnetic_field.y = by_t
        msg.magnetic_field.z = bz_t
        try:
            self.publisher.publish(msg)
        except Exception:
            if not rclpy.ok():
                return
            raise

    def read_device_sample(self) -> Any | None:
        if self.mock_mode:
            return {
                "x": self.mock_field_t[0],
                "y": self.mock_field_t[1],
                "z": self.mock_field_t[2],
            }
        if self._runtime is None:
            self._maybe_start_runtime()
            return None
        try:
            field = self._runtime.latest_field()
        except Exception as exc:
            self._last_connect_error = str(exc)
            self.get_logger().error(f"fangkong_adc runtime read failed: {exc}")
            self._teardown_runtime()
            return None
        if field is None:
            return None
        return {"x": field.x_t, "y": field.y_t, "z": field.z_t}

    def _maybe_start_runtime(self) -> None:
        if self.mock_mode:
            return
        if self._connect_thread is not None and self._connect_thread.is_alive():
            return
        now_s = time.monotonic()
        if now_s < self._next_retry_monotonic_s:
            return

        def _worker() -> None:
            runtime = FangkongAdcMagneticClient(
                fangkong_root=self.fangkong_root,
                fangkong_default_config=self.fangkong_default_config,
                fangkong_user_config=self.fangkong_user_config or None,
                use_fangkong_user_config=self.use_fangkong_user_config,
                device_host=self.device_host,
                device_port=self.device_port,
                connect_timeout_sec=self.connect_timeout_sec,
                recv_timeout_sec=self.recv_timeout_sec,
                reconnect_interval_sec=self.reconnect_interval_sec,
                sample_rate_hz=self.sample_rate_hz,
                active_channels=self.active_channels,
                read_bytes_per_request=self.read_bytes_per_request,
                sensor_sensitivity_mv_per_ut=self.sensor_sensitivity_mv_per_ut,
                transport_mode=self.transport_mode,
                waveform_y_unit=self.waveform_y_unit,
                calibration_enabled=self.calibration_enabled,
                calibration_profile_path=self.calibration_profile_path,
                storage_enabled=self.storage_enabled,
                storage_root_dir=self.storage_root_dir,
                axis_order=self.axis_order,
                axis_signs=self.axis_signs,
            )
            try:
                runtime.start()
            except Exception as exc:
                self._last_connect_error = str(exc)
                self._next_retry_monotonic_s = time.monotonic() + max(self.retry_interval_s, 0.5)
                self.get_logger().error(
                    "fangkong_adc runtime start failed "
                    f"host={self.device_host}:{self.device_port}: {exc}"
                )
                runtime.stop()
                return
            self._runtime = runtime
            self._last_connect_error = ""
            self.get_logger().info(
                f"fangkong_adc runtime connected host={self.device_host}:{self.device_port} "
                f"channels={self.active_channels}"
            )

        self._connect_thread = threading.Thread(target=_worker, name="FangkongMagConnect", daemon=True)
        self._connect_thread.start()

    def _teardown_runtime(self) -> None:
        if self._runtime is None:
            self._next_retry_monotonic_s = time.monotonic() + max(self.retry_interval_s, 0.5)
            return
        runtime = self._runtime
        self._runtime = None
        runtime.stop()
        self._next_retry_monotonic_s = time.monotonic() + max(self.retry_interval_s, 0.5)

    def destroy_node(self) -> bool:
        self._teardown_runtime()
        return super().destroy_node()

    def decode_device_sample(self, raw: Any) -> dict[str, Any] | None:
        """Decode the vendor packet.

        Expected output:
            {"x": <float>, "y": <float>, "z": <float>}
        """
        if isinstance(raw, dict):
            return raw
        return None

    def _normalize_to_tesla(self, sample: dict[str, Any]) -> tuple[float, float, float]:
        unit_scale = UNIT_TO_TESLA.get(self.input_unit)
        if unit_scale is None:
            raise ValueError(f"unsupported input_unit={self.input_unit}")
        try:
            x = float(sample.get("x", sample.get("bx")))
            y = float(sample.get("y", sample.get("by")))
            z = float(sample.get("z", sample.get("bz")))
        except (TypeError, ValueError) as exc:
            raise ValueError("sample must provide numeric x/y/z fields") from exc
        values = [x * unit_scale, y * unit_scale, z * unit_scale]
        if not all(math.isfinite(item) for item in values):
            raise ValueError("sample contains non-finite magnetic field values")
        return values[0], values[1], values[2]

##
# @brief Run the magnetic wrapper node until the ROS context stops.
# @param args Optional ROS CLI arguments.
def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = MagneticSensorWrapperNode()
    try:
        rclpy.spin(node)
    except ExternalShutdownException:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
