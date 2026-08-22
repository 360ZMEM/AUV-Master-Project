#!/usr/bin/env python3
"""Run a synchronized, zero-actuator PC104 -> ROS2 -> BT fault experiment.

The runner owns the container-side fan-out, bridge, decision node, rosbag, a
healthy SensorStatus publisher, and the zero-command PC authorization stream.
It uses telnetd only for reversible runtime injection and always restores the
captured board state in ``finally``.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402
from tools.probe_pc104_fault_injection import (  # noqa: E402
    Offsets,
    VxShell,
    resolve_symbols,
)
from common.protocol import build_downlink_packet, parse_downlink_packet  # noqa: E402


BIT5 = 1 << 5
BIT13 = 1 << 13
BIT14 = 1 << 14
FAULT_MASK = BIT5 | BIT13 | BIT14
REMOTE_MODE = 0x01
JETSON_MODE = 0xEE


def utc_now() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--telnet-host", default="192.168.0.101")
    parser.add_argument("--telnet-port", type=int, default=23)
    parser.add_argument("--telnet-user", default="target")
    parser.add_argument("--telnet-password", default="password")
    parser.add_argument("--relay-host", default="192.168.65.254")
    parser.add_argument("--relay-port", type=int, default=10022)
    parser.add_argument("--uplink-source", default="172.18.0.1")
    parser.add_argument(
        "--params-file",
        type=Path,
        default=REPO_ROOT
        / "brain_linux/config/params.protocol_udp_pc104_fanout_relay.yaml",
    )
    parser.add_argument("--bag-storage", default="mcap")
    parser.add_argument("--soak-duration-s", type=float, default=0.0)
    parser.add_argument("--soak-progress-s", type=float, default=60.0)
    return parser.parse_args()


class RecorderNode:
    """Small ROS2 observer and healthy-state publisher."""

    def __init__(self, output_rows: list[dict[str, Any]], start: float) -> None:
        import rclpy
        from auv_interfaces.msg import ArbiterStatus, ControlGoal, SensorStatus, Setpoint
        from rclpy.node import Node
        from std_msgs.msg import String

        class _Node(Node):
            pass

        self.rclpy = rclpy
        self.SensorStatus = SensorStatus
        self.rows = output_rows
        self.start = start
        self.phase = "startup"
        self.latest_arbiter = None
        self.latest_goal = None
        self.latest_setpoint = None
        self.latest_bt = ""
        self.node = _Node("pc104_cross_layer_fault_recorder")
        self.sensor_pub = self.node.create_publisher(
            SensorStatus, "/auv/sensors/status", 10
        )
        self.node.create_subscription(
            ArbiterStatus, "/auv/arbiter/status", self._on_arbiter, 50
        )
        self.node.create_subscription(
            ControlGoal, "/auv/control/goal", self._on_goal, 50
        )
        self.node.create_subscription(
            Setpoint, "/auv/control/setpoint", self._on_setpoint, 50
        )
        self.node.create_subscription(
            String, "/auv/bt_status", self._on_bt, 20
        )
        self.node.create_subscription(
            String,
            "/auv/bridge/shadow_cmd",
            lambda msg: self._append(
                "shadow_cmd", payload_json=str(msg.data)
            ),
            20,
        )
        self.node.create_subscription(
            String,
            "/auv/bridge/shadow_telemetry",
            lambda msg: self._append(
                "shadow_telemetry", payload_json=str(msg.data)
            ),
            20,
        )

    def _append(self, event_type: str, **values: Any) -> None:
        row = {
            "event_type": event_type,
            "elapsed_s": time.monotonic() - self.start,
            "wall_time_utc": utc_now(),
            "phase": self.phase,
        }
        row.update(values)
        self.rows.append(row)

    def marker(self, name: str, note: str = "") -> None:
        self.phase = name
        self._append("phase_start", note=note)

    def _on_arbiter(self, msg) -> None:
        self.latest_arbiter = msg
        self._append(
            "arbiter_status",
            active_arbiter=str(msg.active_arbiter),
            arbiter_source=str(msg.arbiter_source),
            auto_state=str(msg.auto_state),
            deny_reason=str(msg.deny_reason),
            effective_control_mode_byte=int(msg.effective_control_mode_byte),
            effective_work_instruction=int(msg.effective_work_instruction),
            autonomy_allowed=int(bool(msg.autonomy_allowed)),
            mpc_command_valid=int(bool(msg.mpc_command_valid)),
            telemetry_freshness_ms=float(msg.telemetry_freshness_ms),
            sys_abnorm_info=int(msg.pc104_sys_abnorm_info),
            bit5_system_communication=int(bool(msg.pc104_system_comm_fault)),
            bit13_dvl_lost=int(bool(msg.pc104_dvl_lost)),
            bit14_jetson_timeout=int(bool(msg.pc104_jetson_timeout)),
        )

    def _on_goal(self, msg) -> None:
        self.latest_goal = msg
        self._append(
            "control_goal",
            goal_mode=str(msg.mode),
            goal_speed_mps=float(msg.target_speed_mps),
            goal_depth_m=float(msg.target_depth_m),
            goal_high_priority=int(bool(msg.high_priority)),
            note=str(msg.note),
        )

    def _on_setpoint(self, msg) -> None:
        self.latest_setpoint = msg
        self._append(
            "control_setpoint",
            goal_mode=str(msg.mode),
            goal_speed_mps=float(msg.target_speed_mps),
            goal_depth_m=float(msg.target_depth_m),
            goal_high_priority=int(bool(msg.high_priority)),
            note=str(msg.note),
        )

    def _on_bt(self, msg) -> None:
        self.latest_bt = str(msg.data)
        self._append("bt_status", note=self.latest_bt)

    def publish_healthy_sensor_status(self) -> None:
        msg = self.SensorStatus()
        msg.confidence = 0.9
        msg.leak_level = int(self.SensorStatus.LEAK_NONE)
        msg.battery_low = False
        msg.total_voltage_v = 50.0
        msg.anomaly_detected = False
        msg.depth_m = 4.0
        msg.speed_mps = 0.0
        msg.seabed_depth_m = 9.0
        msg.seabed_clearance_m = 5.0
        msg.seabed_proximity_warning = False
        msg.seabed_penetration_warning = False
        msg.heading_rad = 0.0
        msg.mock_amd_timestamp_us = 0
        msg.debug_level = int(self.SensorStatus.DEBUG_AUTO)
        self.sensor_pub.publish(msg)

    def spin_once(self, timeout_s: float = 0.01) -> None:
        self.rclpy.spin_once(self.node, timeout_sec=timeout_s)

    def close(self) -> None:
        self.node.destroy_node()


class ZeroAuthorization:
    """Publish only zero-actuator authorization or Remote packets over Zenoh."""

    def __init__(
        self,
        rows: list[dict[str, Any]],
        start: float,
        phase: Callable[[], str],
    ) -> None:
        import zenoh

        self.rows = rows
        self.start = start
        self.phase = phase
        self.frame = 0
        self._lock = threading.Lock()
        self._mode: int | None = None
        self._stop = threading.Event()
        self.session = zenoh.open(zenoh.Config())
        self.publisher = self.session.declare_publisher("rt/pc/cmd_raw")
        self.telemetry_sub = self.session.declare_subscriber(
            "rt/auv/telemetry", self._on_telemetry
        )
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name="pc104-zero-authorization",
            daemon=True,
        )
        self._thread.start()

    def send(self, control_mode: int) -> None:
        payload = {
            "frame_number": self.frame & 0xFFFF,
            "obj_address": 1,
            "control_mode_byte": int(control_mode),
            "work_instruction": 0,
            "thrust": 0.0,
            "left": 0.0,
            "right": 0.0,
            "top": 0.0,
            "bottom": 0.0,
            "side_motor_rpm": 0,
            "orientation_deg": 0.0,
            "depth_protect_params": [500, 29],
            "bottom_protect_params": [300, 200],
            "preset_time_tenths_min": 10,
            "spare_params": [0, 0],
            "parameters": [0] * 12,
            "ts": time.time(),
        }
        self.publisher.put(json.dumps(payload).encode("utf-8"))
        self.frame += 1

    def set_mode(self, control_mode: int | None) -> None:
        with self._lock:
            self._mode = control_mode

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                mode = self._mode
            if mode is not None:
                self.send(mode)
            self._stop.wait(0.1)

    def _on_telemetry(self, sample) -> None:
        try:
            raw = (
                sample.payload.to_bytes()
                if hasattr(sample.payload, "to_bytes")
                else bytes(sample.payload)
            )
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return
        row = {
            "event_type": "bridge_telemetry",
            "elapsed_s": time.monotonic() - self.start,
            "wall_time_utc": utc_now(),
            "phase": self.phase(),
            "sys_abnorm_info": int(payload.get("sys_abnorm_info", 0)),
            "bit5_system_communication": int(
                bool(payload.get("pc104_system_comm_fault", False))
            ),
            "bit13_dvl_lost": int(
                bool(payload.get("pc104_dvl_lost", False))
            ),
            "bit14_jetson_timeout": int(
                bool(payload.get("pc104_jetson_timeout", False))
            ),
            "uplink_main_motor_rpm": float(payload.get("main_motor_rpm", 0.0)),
            "uplink_side_motor_rpm": float(payload.get("side_motor_rpm", 0.0)),
        }
        with self._lock:
            self.rows.append(row)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        try:
            self.telemetry_sub.undeclare()
        except Exception:
            pass
        try:
            self.publisher.undeclare()
        except Exception:
            pass
        self.session.close()


def start_process(
    command: list[str],
    log_path: Path,
    handles: list[Any],
) -> subprocess.Popen:
    handle = log_path.open("w", encoding="utf-8")
    handles.append(handle)
    return subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


def stop_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGINT)
        proc.wait(timeout=8.0)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=2.0)


def set_bridge_passive(enabled: bool) -> None:
    proc = subprocess.run(
        [
            "ros2",
            "param",
            "set",
            "/protocol_udp_bridge_node",
            "passive_mode",
            "true" if enabled else "false",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=10.0,
        check=False,
    )
    if proc.returncode != 0 or "successful" not in proc.stdout.lower():
        raise RuntimeError(
            f"cannot set bridge passive_mode={enabled}: "
            f"{proc.stdout.strip()} {proc.stderr.strip()}"
        )


def send_safe_remote_recovery() -> None:
    packet = build_downlink_packet(
        [0.0, 0.0, 0.0, 0.0, 0.0],
        control_mode_byte=REMOTE_MODE,
        work_instruction=0,
        depth_protect_params=(500, 29),
        bottom_protect_params=(300, 200),
        preset_time_tenths_min=10,
        side_motor_rpm=0,
    )
    decoded = parse_downlink_packet(packet)
    actuators = (
        decoded.main_motor_rpm,
        decoded.side_motor_rpm,
        decoded.left_fin_deg,
        decoded.right_fin_deg,
        decoded.top_fin_deg,
        decoded.bottom_fin_deg,
    )
    if any(abs(float(value)) > 1.0e-9 for value in actuators):
        raise RuntimeError(f"non-zero recovery packet generated: {actuators}")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 52366))
        for _ in range(5):
            sock.sendto(packet, ("127.0.0.1", 52364))
            time.sleep(0.1)


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "event_type",
        "elapsed_s",
        "wall_time_utc",
        "phase",
    ]
    seen = set(fields)
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def process_alive(proc: subprocess.Popen | None, name: str) -> None:
    if proc is None or proc.poll() is not None:
        code = None if proc is None else proc.returncode
        raise RuntimeError(f"{name} exited before experiment, returncode={code}")


def process_tree_rss_kib_from_pid(
    root_pid: int,
    *,
    proc_root: Path = Path("/proc"),
    page_size_kib: int | None = None,
) -> int:
    """Sum RSS for a Linux process and all descendants."""
    if page_size_kib is None:
        page_size_kib = os.sysconf("SC_PAGE_SIZE") // 1024
    pending = [int(root_pid)]
    seen: set[int] = set()
    total_kib = 0
    found = False
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        process_dir = proc_root / str(pid)
        try:
            fields = (process_dir / "statm").read_text(
                encoding="ascii"
            ).split()
            total_kib += int(fields[1]) * page_size_kib
            found = True
        except (OSError, ValueError, IndexError):
            continue
        try:
            children = (
                process_dir / "task" / str(pid) / "children"
            ).read_text(encoding="ascii")
            pending.extend(int(value) for value in children.split())
        except (OSError, ValueError):
            continue
    return total_kib if found else -1


def process_rss_kib(proc: subprocess.Popen | None) -> int:
    if proc is None or proc.poll() is not None:
        return -1
    return process_tree_rss_kib_from_pid(proc.pid)


def has_row(
    rows: list[dict[str, Any]],
    phase: str,
    event_type: str,
    predicate: Callable[[dict[str, Any]], bool],
) -> bool:
    return any(
        row.get("phase") == phase
        and row.get("event_type") == event_type
        and predicate(row)
        for row in rows
    )


def latency_ms(
    rows: list[dict[str, Any]],
    phase: str,
    event_type: str,
    predicate: Callable[[dict[str, Any]], bool],
) -> float:
    start = next(
        (
            float(row["elapsed_s"])
            for row in rows
            if row.get("phase") == phase
            and row.get("event_type") == "phase_start"
        ),
        float("nan"),
    )
    match = next(
        (
            float(row["elapsed_s"])
            for row in rows
            if row.get("phase") == phase
            and row.get("event_type") == event_type
            and predicate(row)
        ),
        float("nan"),
    )
    return (match - start) * 1000.0


def parse_fanout_log(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    statuses = re.findall(
        r"status uplink=(\d+) downlink=(\d+) blocked=(\d+)", text
    )
    latest = tuple(map(int, statuses[-1])) if statuses else (0, 0, 0)
    return {
        "fanout_uplink_count": latest[0],
        "fanout_downlink_count": latest[1],
        "fanout_blocked_count": latest[2],
        "fanout_nonzero_block_count": text.count("non-zero actuator blocked"),
    }


def main() -> int:
    args = parse_args()
    shell = VxShell(
        args.telnet_host,
        args.telnet_port,
        args.telnet_user,
        args.telnet_password,
        5.0,
    )
    shell.connect()
    symbols = resolve_symbols(shell)
    offsets = Offsets()
    initial = shell.read_snapshot(symbols, offsets)
    print(
        "[cross-layer] preflight "
        f"mode=0x{int(initial['telnet_current_mode']):02x} "
        f"sys=0x{int(initial['telnet_sys_abnorm']):08x} "
        f"motors={initial['telnet_instruction_motor1']}/"
        f"{initial['telnet_instruction_motor2']}",
        flush=True,
    )
    if not args.execute:
        shell.close()
        print("[cross-layer] read-only preflight complete; pass --execute to run")
        return 0

    initial_zero_fields = (
        "telnet_ui_motor1",
        "telnet_ui_motor2",
        "telnet_ui_fin_lh",
        "telnet_ui_fin_rh",
        "telnet_ui_fin_uv",
        "telnet_ui_fin_lv",
        "telnet_instruction_motor1",
        "telnet_instruction_motor2",
    )
    if any(int(initial[key]) != 0 for key in initial_zero_fields):
        shell.close()
        raise SystemExit(f"refuse to run: initial actuator command is non-zero: {initial}")
    if int(initial["telnet_sys_abnorm"]) & FAULT_MASK:
        shell.close()
        raise SystemExit(
            "refuse to run: one of Bit5/Bit13/Bit14 is already active: "
            f"0x{int(initial['telnet_sys_abnorm']):08x}"
        )

    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else REPO_ROOT
        / "results/control"
        / f"pc104_cross_layer_fault_sync_{stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    sanitized_argv = [
        "***" if previous == "--telnet-password" else value
        for previous, value in zip(["", *sys.argv[:-1]], sys.argv)
    ]
    initialize_bundle(
        output_dir,
        experiment_id=f"pc104_cross_layer_fault_sync_{stamp}",
        runner="tools/run_pc104_cross_layer_fault_sync.py",
        argv=sanitized_argv,
        data_layer="physical_pc104_ros2_behavior_tree_synchronized",
        matrix={
            "fault_bits": [5, 13, 14],
            "sensor_status_confidence": 0.9,
            "authorization_rate_hz": 10.0,
            "dvl_isolation_status": 2.0,
            "dvl_isolation_height_m": 5.0,
        },
        duration_s=float(args.soak_duration_s) + 15.0,
        config_paths=[
            Path(__file__),
            args.params_file,
            REPO_ROOT / "common/protocol.py",
            REPO_ROOT
            / "brain_linux/src/auv_interfaces/msg/ArbiterStatus.msg",
            REPO_ROOT
            / "brain_linux/src/auv_bridge/auv_bridge/autonomy_guard.py",
            REPO_ROOT
            / "brain_linux/src/auv_bridge/auv_bridge/bridge_node.py",
            REPO_ROOT
            / "brain_linux/src/auv_control/auv_decision_ros/decision_node.py",
            REPO_ROOT
            / "brain_linux/src/auv_decision/auv_decision_core/behaviors.py",
            REPO_ROOT / "csd_vx6.8_lastest/SecurityEmergencyManage.c",
        ],
        extra_manifest={
            "hardware_required": True,
            "telnetd_runtime_injection": True,
            "fanout_nonzero_actuator_gate": True,
            "physical_one_way_latency_claim": False,
            "voltage_guard_override_v": -1.0,
            "voltage_guard_override_reason": (
                "Current PC104 bench telemetry exports total_voltage_v=0.0; "
                "this run isolates the communication-fault chain and is not "
                "a power-system acceptance test."
            ),
            "bit13_boundary": (
                "DVL data is held at BD_Check=2 and BD_Height=5 m; Bit13 is "
                "injected through the FMCU fault word to avoid the firmware "
                "DVL-loss self-rescue actuator branch."
            ),
            "soak_duration_s": float(args.soak_duration_s),
            "rss_sampling_scope": "root_process_plus_descendants",
        },
    )

    original = {
        "watchdog": shell.read_u16(symbols.watchdog),
        "sys_abnorm": shell.read_u32(symbols.sys_abnorm),
        "fmcu_sys_abnorm": shell.read_u32(
            symbols.fmcu_feedback + offsets.fmcu_sys_abnorm
        ),
        "dvl_check_bits": shell.read_u32(
            symbols.dvl_data + offsets.dvl_bd_check
        ),
        "dvl_height_bits": shell.read_u32(
            symbols.dvl_data + offsets.dvl_bd_height
        ),
    }
    rows: list[dict[str, Any]] = []
    board_snapshots: dict[str, Any] = {"initial": initial, "original_raw": original}
    start = time.monotonic()
    handles: list[Any] = []
    processes: dict[str, subprocess.Popen | None] = {
        "fanout": None,
        "bridge": None,
        "decision": None,
        "rosbag": None,
    }
    recorder: RecorderNode | None = None
    authorization: ZeroAuthorization | None = None
    run_error = ""

    def append(event_type: str, phase: str, **values: Any) -> None:
        row = {
            "event_type": event_type,
            "elapsed_s": time.monotonic() - start,
            "wall_time_utc": utc_now(),
            "phase": phase,
        }
        row.update(values)
        rows.append(row)

    def board_snapshot(name: str) -> dict[str, Any]:
        snapshot = shell.read_snapshot(symbols, offsets)
        board_snapshots[name] = snapshot
        append("board_snapshot", name, **snapshot)
        return snapshot

    def drive(
        phase: str,
        duration_s: float,
        *,
        auth_mode: int | None,
        note: str = "",
        hold_fault_mask: int = 0,
        progress_period_s: float = 0.0,
    ) -> None:
        assert recorder is not None
        assert authorization is not None
        recorder.marker(phase, note)
        authorization.set_mode(auth_mode)
        deadline = time.monotonic() + duration_s
        next_publish = 0.0
        next_fault_assert = 0.0
        next_progress = time.monotonic()
        while time.monotonic() < deadline:
            now = time.monotonic()
            if hold_fault_mask and now >= next_fault_assert:
                shell.command(
                    f"*(unsigned int*)0x{symbols.sys_abnorm:x}="
                    f"*(unsigned int*)0x{symbols.sys_abnorm:x}|"
                    f"0x{hold_fault_mask:08x}"
                )
                next_fault_assert = now + 0.1
            if now >= next_publish:
                recorder.publish_healthy_sensor_status()
                next_publish = now + 0.1
            if progress_period_s > 0.0 and now >= next_progress:
                for process_name, process in processes.items():
                    if process_name != "rosbag":
                        process_alive(process, process_name)
                elapsed = now - start
                remaining = max(0.0, deadline - now)
                append(
                    "runtime_sample",
                    phase,
                    fanout_rss_kib=process_rss_kib(processes["fanout"]),
                    bridge_rss_kib=process_rss_kib(processes["bridge"]),
                    decision_rss_kib=process_rss_kib(processes["decision"]),
                    rosbag_rss_kib=process_rss_kib(processes["rosbag"]),
                    loadavg_1m=os.getloadavg()[0],
                )
                print(
                    f"[cross-layer] {phase} elapsed={elapsed:.1f}s "
                    f"remaining={remaining:.1f}s",
                    flush=True,
                )
                next_progress = now + progress_period_s
            recorder.spin_once(0.02)

    def inject_fmcu_fault(mask: int, enabled: bool) -> None:
        current_fmcu = shell.read_u32(
            symbols.fmcu_feedback + offsets.fmcu_sys_abnorm
        )
        current_sys = shell.read_u32(symbols.sys_abnorm)
        if enabled:
            shell.write_u32(
                symbols.fmcu_feedback + offsets.fmcu_sys_abnorm,
                current_fmcu | mask,
            )
            shell.write_u32(symbols.sys_abnorm, current_sys | mask)
        else:
            shell.write_u32(
                symbols.fmcu_feedback + offsets.fmcu_sys_abnorm,
                current_fmcu & ~mask,
            )
            shell.write_u32(symbols.sys_abnorm, current_sys & ~mask)

    import rclpy

    try:
        shell.write_u8(
            symbols.ui_instruction + offsets.ui_ctrl_mode, REMOTE_MODE
        )
        for address in (
            symbols.ui_instruction + offsets.ui_motor1,
            symbols.ui_instruction + offsets.ui_motor2,
            symbols.ui_instruction + offsets.ui_fin_lh,
            symbols.ui_instruction + offsets.ui_fin_rh,
            symbols.ui_instruction + offsets.ui_fin_uv,
            symbols.ui_instruction + offsets.ui_fin_lv,
            symbols.fmcu_instruction + offsets.instruction_motor1,
            symbols.fmcu_instruction + offsets.instruction_motor2,
        ):
            shell.write_s16(address, 0)
        shell.write_float(
            symbols.dvl_data + offsets.dvl_bd_check, 2.0
        )
        shell.write_float(
            symbols.dvl_data + offsets.dvl_bd_height, 5.0
        )
        inject_fmcu_fault(FAULT_MASK, False)
        board_snapshot("isolated_pre_start")

        fanout_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts/pc104_udp_fanout.py"),
            "--listen-host",
            "0.0.0.0",
            "--listen-port",
            "21",
            "--pc104-host",
            args.relay_host,
            "--pc104-port",
            str(args.relay_port),
            "--accept-uplink-source",
            args.uplink_source,
            "--cmd-host",
            "127.0.0.1",
            "--cmd-port",
            "52364",
            "--subscriber",
            "ros2=127.0.0.1:52365",
            "--ros-source-port",
            "52365",
            "--status-period-s",
            "1",
        ]
        processes["fanout"] = start_process(
            fanout_cmd, output_dir / "fanout.log", handles
        )
        time.sleep(1.0)
        process_alive(processes["fanout"], "fanout")

        bridge_cmd = [
            "ros2",
            "run",
            "auv_bridge",
            "protocol_udp_bridge_node",
            "--ros-args",
            "-p",
            f"params_file:={args.params_file.resolve()}",
            "-p",
            "bridge_backend:=protocol_udp",
            "-p",
            "passive_mode:=false",
            "-p",
            "command_publish_hz:=10.0",
            "-p",
            "guard_min_total_voltage_v:=-1.0",
        ]
        processes["bridge"] = start_process(
            bridge_cmd, output_dir / "bridge.log", handles
        )
        time.sleep(2.0)
        process_alive(processes["bridge"], "bridge")

        decision_cmd = [
            "ros2",
            "run",
            "auv_decision_ros",
            "decision_node",
            "--ros-args",
            "-p",
            "bridge_backend:=protocol_udp",
            "-p",
            "mock_amd_timeout_s:=0.5",
            "-p",
            "bt_status_publish_period:=0.2",
            "-p",
            "summary_log_period:=2.0",
            "-p",
            "tree_print_period:=5.0",
        ]
        processes["decision"] = start_process(
            decision_cmd, output_dir / "decision.log", handles
        )

        rclpy.init()
        recorder = RecorderNode(rows, start)
        authorization = ZeroAuthorization(
            rows, start, lambda: recorder.phase if recorder else "shutdown"
        )
        time.sleep(1.0)

        bag_topics = [
            "/auv/arbiter/status",
            "/auv/bt_status",
            "/auv/control/goal",
            "/auv/control/setpoint",
            "/auv/bridge/shadow_cmd",
            "/auv/bridge/shadow_telemetry",
            "/auv/sensors/status",
            "/auv/sensors/depth",
            "/auv/sensors/dvl",
            "/auv/sensors/imu",
            "/rosout",
        ]
        bag_cmd = [
            "ros2",
            "bag",
            "record",
            "-s",
            args.bag_storage,
            "-o",
            str(output_dir / "rosbag"),
            *bag_topics,
        ]
        processes["rosbag"] = start_process(
            bag_cmd, output_dir / "rosbag.log", handles
        )
        time.sleep(1.0)
        process_alive(processes["rosbag"], "rosbag")

        drive("remote_baseline", 1.0, auth_mode=REMOTE_MODE)
        drive("active_baseline", 1.5, auth_mode=JETSON_MODE)
        if recorder.latest_arbiter is None or str(
            recorder.latest_arbiter.auto_state
        ) != "ACTIVE":
            raise RuntimeError("healthy baseline did not reach ACTIVE")
        board_snapshot("active_baseline")

        if args.soak_duration_s > 0.0:
            drive(
                "active_soak",
                float(args.soak_duration_s),
                auth_mode=JETSON_MODE,
                note="zero-actuator full-stack stability interval",
                progress_period_s=max(1.0, float(args.soak_progress_s)),
            )
            board_snapshot("active_soak")

        inject_fmcu_fault(BIT13, True)
        drive(
            "bit13_dvl_loss",
            1.5,
            auth_mode=JETSON_MODE,
            note="FMCU fault-word injection with DVL safe isolation",
            hold_fault_mask=BIT13,
        )
        board_snapshot("bit13_dvl_loss")
        inject_fmcu_fault(BIT13, False)
        drive("bit13_clear", 0.8, auth_mode=JETSON_MODE)

        inject_fmcu_fault(BIT5, True)
        drive(
            "bit5_system_comm",
            0.3,
            auth_mode=JETSON_MODE,
            note="FMCU/system communication fault injection",
            hold_fault_mask=BIT5,
        )
        drive(
            "bit5_system_comm",
            0.3,
            auth_mode=None,
            note="authorization withheld after DENIED",
            hold_fault_mask=BIT5,
        )
        board_snapshot("bit5_system_comm")
        inject_fmcu_fault(BIT5, False)
        drive(
            "bit5_clear_hold",
            0.4,
            auth_mode=None,
            note="fault cleared; no authorization heartbeat",
        )
        drive(
            "bit5_reauthorize",
            1.0,
            auth_mode=JETSON_MODE,
            note="explicit zero-command authorization resumes",
        )

        set_bridge_passive(True)
        drive(
            "bit14_watchdog_outage",
            2.2,
            auth_mode=JETSON_MODE,
            note="bridge downlink paused; PC104 watchdog runs naturally",
        )
        board_snapshot("bit14_watchdog_outage")
        authorization.set_mode(None)
        send_safe_remote_recovery()
        drive(
            "bit14_clear_hold",
            0.3,
            auth_mode=None,
            note="zero Remote downlink restored; authorization withheld",
        )
        drive(
            "bit14_reauthorize",
            1.0,
            auth_mode=JETSON_MODE,
            note="explicit zero-command authorization resumes",
        )
        set_bridge_passive(False)

        drive("remote_cleanup", 0.8, auth_mode=REMOTE_MODE)
        inject_fmcu_fault(FAULT_MASK, False)
        board_snapshot("pre_restore")
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
        append("runner_error", recorder.phase if recorder else "startup", note=run_error)
    finally:
        try:
            try:
                set_bridge_passive(False)
            except Exception:
                pass
            if recorder is not None and authorization is not None:
                try:
                    drive("finally_remote_cleanup", 0.5, auth_mode=REMOTE_MODE)
                except Exception:
                    pass
        finally:
            stop_process(processes["rosbag"])
            stop_process(processes["decision"])
            stop_process(processes["bridge"])
            stop_process(processes["fanout"])
        try:
            shell.write_u8(
                symbols.ui_instruction + offsets.ui_ctrl_mode, REMOTE_MODE
            )
            for address in (
                symbols.ui_instruction + offsets.ui_motor1,
                symbols.ui_instruction + offsets.ui_motor2,
                symbols.ui_instruction + offsets.ui_fin_lh,
                symbols.ui_instruction + offsets.ui_fin_rh,
                symbols.ui_instruction + offsets.ui_fin_uv,
                symbols.ui_instruction + offsets.ui_fin_lv,
                symbols.fmcu_instruction + offsets.instruction_motor1,
                symbols.fmcu_instruction + offsets.instruction_motor2,
            ):
                shell.write_s16(address, 0)
            shell.write_u16(symbols.watchdog, original["watchdog"])
            shell.write_u32(
                symbols.fmcu_feedback + offsets.fmcu_sys_abnorm,
                original["fmcu_sys_abnorm"],
            )
            shell.write_u32(symbols.sys_abnorm, original["sys_abnorm"])
            shell.write_u32(
                symbols.dvl_data + offsets.dvl_bd_check,
                original["dvl_check_bits"],
            )
            shell.write_u32(
                symbols.dvl_data + offsets.dvl_bd_height,
                original["dvl_height_bits"],
            )
            time.sleep(0.5)
            board_snapshots["post_cleanup"] = shell.read_snapshot(
                symbols, offsets
            )
        finally:
            if authorization is not None:
                authorization.close()
            if recorder is not None:
                recorder.close()
            if rclpy.ok():
                rclpy.shutdown()
            shell.close()
            for handle in handles:
                handle.close()

    write_rows(output_dir / "cross_layer_timeline.csv", rows)
    (output_dir / "board_state.json").write_text(
        json.dumps(board_snapshots, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    fanout = parse_fanout_log(output_dir / "fanout.log")
    bag_files = list((output_dir / "rosbag").glob("*.mcap"))
    rosbag_bytes = sum(path.stat().st_size for path in bag_files)
    board_rows = [
        row for row in rows if row.get("event_type") == "board_snapshot"
    ]
    board_nonzero = sum(
        1
        for row in board_rows
        if any(
            int(row.get(key, 0)) != 0
            for key in initial_zero_fields
        )
    )
    uplink_motor_nonzero = sum(
        1
        for row in rows
        if row.get("event_type") == "bridge_telemetry"
        and (
            abs(float(row.get("uplink_main_motor_rpm", 0.0))) > 1.0e-9
            or abs(float(row.get("uplink_side_motor_rpm", 0.0))) > 1.0e-9
        )
    )
    soak_status_rows = [
        row
        for row in rows
        if row.get("phase") == "active_soak"
        and row.get("event_type") == "arbiter_status"
    ]
    soak_active_count = sum(
        row.get("auto_state") == "ACTIVE" for row in soak_status_rows
    )
    soak_fault_count = sum(
        int(row.get("sys_abnorm_info", 0)) & FAULT_MASK != 0
        for row in soak_status_rows
    )
    soak_active_ratio = (
        soak_active_count / len(soak_status_rows)
        if soak_status_rows
        else (1.0 if args.soak_duration_s <= 0.0 else 0.0)
    )
    soak_runtime_samples = sum(
        row.get("phase") == "active_soak"
        and row.get("event_type") == "runtime_sample"
        for row in rows
    )

    checks = {
        "baseline_active": has_row(
            rows,
            "active_baseline",
            "arbiter_status",
            lambda row: row.get("auto_state") == "ACTIVE"
            and int(row.get("sys_abnorm_info", -1)) == 0,
        ),
        "bit13_observed": has_row(
            rows,
            "bit13_dvl_loss",
            "arbiter_status",
            lambda row: int(row.get("bit13_dvl_lost", 0)) == 1,
        ),
        "bit13_retains_autonomy": has_row(
            rows,
            "bit13_dvl_loss",
            "arbiter_status",
            lambda row: int(row.get("bit13_dvl_lost", 0)) == 1
            and row.get("auto_state") == "ACTIVE",
        ),
        "bit13_routes_to_relocalization": has_row(
            rows,
            "bit13_dvl_loss",
            "control_goal",
            lambda row: row.get("goal_mode") == "ZIGZAG_SEARCH",
        ),
        "bit5_denies_autonomy": has_row(
            rows,
            "bit5_system_comm",
            "arbiter_status",
            lambda row: int(row.get("bit5_system_communication", 0)) == 1
            and row.get("auto_state") == "DENIED"
            and row.get("deny_reason") == "COMM_LINK_FAILURE"
            and row.get("active_arbiter") == "REMOTE",
        ),
        "bit5_bt_idle_zero": has_row(
            rows,
            "bit5_system_comm",
            "control_goal",
            lambda row: row.get("goal_mode") == "IDLE"
            and abs(float(row.get("goal_speed_mps", 1.0))) <= 1.0e-9,
        ),
        "bit5_requires_reauthorization": has_row(
            rows,
            "bit5_clear_hold",
            "arbiter_status",
            lambda row: int(row.get("bit5_system_communication", 1)) == 0
            and row.get("auto_state") == "DENIED",
        ),
        "bit5_reauthorized": has_row(
            rows,
            "bit5_reauthorize",
            "arbiter_status",
            lambda row: row.get("auto_state") == "ACTIVE",
        ),
        "bit14_denies_autonomy": has_row(
            rows,
            "bit14_watchdog_outage",
            "arbiter_status",
            lambda row: int(row.get("bit14_jetson_timeout", 0)) == 1
            and row.get("auto_state") == "DENIED"
            and row.get("deny_reason") == "COMM_LINK_FAILURE"
            and row.get("active_arbiter") == "REMOTE",
        ),
        "bit14_shadow_zero": has_row(
            rows,
            "bit14_watchdog_outage",
            "shadow_cmd",
            lambda row: all(
                abs(float(json.loads(str(row.get("payload_json", "{}")))
                          .get("payload", {}).get(key, 0.0))) <= 1.0e-9
                for key in ("thrust", "left", "right", "top", "bottom")
            ),
        ),
        "bit14_requires_reauthorization": has_row(
            rows,
            "bit14_clear_hold",
            "arbiter_status",
            lambda row: int(row.get("bit14_jetson_timeout", 1)) == 0
            and row.get("auto_state") == "DENIED",
        ),
        "bit14_reauthorized": has_row(
            rows,
            "bit14_reauthorize",
            "arbiter_status",
            lambda row: row.get("auto_state") == "ACTIVE",
        ),
        "fanout_forwarded_zero_only": (
            fanout["fanout_downlink_count"] > 0
            and fanout["fanout_blocked_count"] == 0
            and fanout["fanout_nonzero_block_count"] == 0
        ),
        "rosbag_recorded": bool(bag_files) and rosbag_bytes > 0,
        "active_soak_stable": (
            args.soak_duration_s <= 0.0
            or (
                bool(soak_status_rows)
                and soak_active_ratio >= 0.999
                and soak_fault_count == 0
                and soak_runtime_samples
                >= max(
                    1,
                    int(
                        float(args.soak_duration_s)
                        / max(1.0, float(args.soak_progress_s))
                    ),
                )
            )
        ),
        "board_command_snapshots_zero": board_nonzero == 0,
        "uplink_motor_feedback_zero": uplink_motor_nonzero == 0,
        "cleanup_remote_zero": (
            int(board_snapshots["post_cleanup"]["telnet_current_mode"])
            == REMOTE_MODE
            and int(board_snapshots["post_cleanup"]["telnet_ui_mode"])
            == REMOTE_MODE
            and all(
                int(board_snapshots["post_cleanup"][key]) == 0
                for key in initial_zero_fields
            )
        ),
    }
    passed = not run_error and all(checks.values())
    summary: dict[str, Any] = {
        "scenario": "pc104_ros2_bt_cross_layer_fault_sync",
        "status": "ok" if passed else "failed_acceptance",
        "error": run_error or (
            ""
            if passed
            else "one or more synchronized cross-layer checks failed"
        ),
        **checks,
        **fanout,
        "board_snapshot_count": len(board_rows),
        "board_nonzero_command_snapshot_count": board_nonzero,
        "uplink_motor_nonzero_frame_count": uplink_motor_nonzero,
        "rosbag_file_count": len(bag_files),
        "rosbag_bytes": rosbag_bytes,
        "soak_duration_requested_s": float(args.soak_duration_s),
        "soak_arbiter_sample_count": len(soak_status_rows),
        "soak_active_ratio": soak_active_ratio,
        "soak_fault_status_count": soak_fault_count,
        "soak_runtime_sample_count": soak_runtime_samples,
        "bit13_to_arbiter_latency_ms": latency_ms(
            rows,
            "bit13_dvl_loss",
            "arbiter_status",
            lambda row: int(row.get("bit13_dvl_lost", 0)) == 1,
        ),
        "bit13_to_bt_latency_ms": latency_ms(
            rows,
            "bit13_dvl_loss",
            "control_goal",
            lambda row: row.get("goal_mode") == "ZIGZAG_SEARCH",
        ),
        "bit5_to_denied_latency_ms": latency_ms(
            rows,
            "bit5_system_comm",
            "arbiter_status",
            lambda row: row.get("deny_reason") == "COMM_LINK_FAILURE",
        ),
        "bit5_to_idle_latency_ms": latency_ms(
            rows,
            "bit5_system_comm",
            "control_goal",
            lambda row: row.get("goal_mode") == "IDLE",
        ),
        "bit14_to_denied_latency_ms": latency_ms(
            rows,
            "bit14_watchdog_outage",
            "arbiter_status",
            lambda row: int(row.get("bit14_jetson_timeout", 0)) == 1
            and row.get("deny_reason") == "COMM_LINK_FAILURE",
        ),
        "effective_sample_count": sum(
            row.get("event_type") == "arbiter_status" for row in rows
        ),
        "failure_event_count": 0 if passed else 1,
        "capability_gate_status": "passed" if passed else "failed",
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "pc104_remote_zero_and_bt_idle",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    finalize_bundle(output_dir, [summary])
    report = [
        "# PC104 -> ROS2 -> Behavior Tree Synchronized Fault Report",
        "",
        "## Result",
        "",
        f"- Status: `{summary['status']}`",
        f"- Bit13 -> arbiter / BT latency: `{summary['bit13_to_arbiter_latency_ms']:.3f} / {summary['bit13_to_bt_latency_ms']:.3f} ms`",
        f"- Bit5 -> DENIED / IDLE latency: `{summary['bit5_to_denied_latency_ms']:.3f} / {summary['bit5_to_idle_latency_ms']:.3f} ms`",
        f"- Natural Bit14 watchdog -> DENIED latency: `{summary['bit14_to_denied_latency_ms']:.3f} ms`",
        f"- Fan-out uplink/downlink/blocked: `{fanout['fanout_uplink_count']}/{fanout['fanout_downlink_count']}/{fanout['fanout_blocked_count']}`",
        f"- Active soak requested/status samples/ACTIVE ratio/fault samples: "
        f"`{summary['soak_duration_requested_s']:.1f} s / "
        f"{summary['soak_arbiter_sample_count']} / "
        f"{summary['soak_active_ratio']:.6f} / "
        f"{summary['soak_fault_status_count']}`",
        f"- Non-zero board command snapshots: `{board_nonzero}`",
        f"- Non-zero uplink motor feedback frames: `{uplink_motor_nonzero}`",
        f"- Cleanup Remote+zero: `{checks['cleanup_remote_zero']}`",
        "",
        "## Acceptance checks",
        "",
        *[f"- {name}: `{value}`" for name, value in checks.items()],
        "",
        "## Boundary",
        "",
        "- Bit5 and Bit13 are reversible telnetd injections into the live FMCU fault word.",
        "- Bit14 is generated by the real PC104 watchdog while bridge downlink is paused.",
        "- DVL is held at a safe synthetic lock state during the run to isolate Bit13 mapping from the firmware self-rescue actuator branch.",
        "- The 47 V guard is disabled only because this bench stream exports 0.0 V; this run does not validate power health.",
        "- No non-zero actuator command is authorized. The fan-out rejects such packets independently of ROS2 logic.",
        "",
    ]
    (output_dir / "report.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    print(
        f"[cross-layer] status={summary['status']} "
        f"checks={sum(checks.values())}/{len(checks)} -> {output_dir}",
        flush=True,
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
