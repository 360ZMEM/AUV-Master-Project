#!/usr/bin/env python3
"""AUV Mock AMD 协议的独立攻击站脚本。

该脚本用于模拟一个竞争同一 Mock AMD 端点的第二控制方：持续发送
共享协议的 $CKTH 控制包、等待 $AUV 回包，并记录延迟统计与 CSV 轨迹。
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import signal
import socket
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from common.enums import ControlModeByte, WorkInstruction
from common.protocol import (
    DEFAULT_MAIN_MOTOR_RPM_SCALE,
    KEY_BOTTOM,
    KEY_CONTROL_MODE_BYTE,
    KEY_FRAME_NUMBER,
    KEY_LEFT,
    KEY_OBJ_ADDRESS,
    KEY_ORIENTATION_DEG,
    KEY_PARAMETERS,
    KEY_RIGHT,
    KEY_SIDE_MOTOR_RPM,
    KEY_THRUST,
    KEY_TOP,
    KEY_WORK_INSTRUCTION,
    build_downlink_packet_from_payload,
    parse_uplink_packet,
)


PROFILE_CHOICES = ("conflict", "sweep", "heartbeat")
SWEEP_CASES: tuple[dict[str, Any], ...] = (
    {
        "label": "zero",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.SEND_ONLY),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
        KEY_RIGHT: 0.0,
        KEY_LEFT: 0.0,
        KEY_TOP: 0.0,
        KEY_BOTTOM: 0.0,
        KEY_THRUST: 0.0,
        KEY_SIDE_MOTOR_RPM: 0,
        KEY_ORIENTATION_DEG: 0.0,
    },
    {
        "label": "balanced",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.REMOTE_CONTROL),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.TASK_START),
        KEY_RIGHT: 35.0,
        KEY_LEFT: -35.0,
        KEY_TOP: 15.0,
        KEY_BOTTOM: -15.0,
        KEY_THRUST: 25.0,
        KEY_SIDE_MOTOR_RPM: 80,
        KEY_ORIENTATION_DEG: 45.0,
    },
    {
        "label": "max_positive",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.AUTO_FIXED_POINT),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.AUTONOMOUS_CONTROL),
        KEY_RIGHT: 100.0,
        KEY_LEFT: -100.0,
        KEY_TOP: 100.0,
        KEY_BOTTOM: -100.0,
        KEY_THRUST: 100.0,
        KEY_SIDE_MOTOR_RPM: 120,
        KEY_ORIENTATION_DEG: 90.0,
    },
    {
        "label": "overrange",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.AUTO_DIRECTION),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.HOLD_DEBUG),
        KEY_RIGHT: 120.0,
        KEY_LEFT: -120.0,
        KEY_TOP: 120.0,
        KEY_BOTTOM: -120.0,
        KEY_THRUST: 150.0,
        KEY_SIDE_MOTOR_RPM: 240,
        KEY_ORIENTATION_DEG: 180.0,
    },
    {
        "label": "reverse",
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.RETURN_HOME),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.TASK_CANCEL),
        KEY_RIGHT: -50.0,
        KEY_LEFT: 50.0,
        KEY_TOP: -40.0,
        KEY_BOTTOM: 40.0,
        KEY_THRUST: -60.0,
        KEY_SIDE_MOTOR_RPM: -90,
        KEY_ORIENTATION_DEG: 270.0,
    },
)


@dataclass(frozen=True)
class AttackerStationConfig:
    """攻击站运行参数集合。

    该配置类聚合网络端点、运行时长、发送速率、CSV 输出和随机种子等参数，
    便于命令行参数解析后一次性注入运行逻辑。
    """

    mock_amd_host: str = "127.0.0.1"
    mock_amd_port: int = 52364
    listen_host: str = "0.0.0.0"
    listen_port: int = 52367
    profile: str = "conflict"
    duration_s: float = 10.0
    rate_hz: float | None = None
    response_timeout_s: float = 1.0
    report_interval_s: float = 10.0
    enable_csv: bool = True
    enable_live_report: bool = True
    obj_address: int = 1
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE
    side_motor_rpm: int = 0
    seed: int | None = None
    csv_path: Path | None = None


@dataclass
class AttackSample:
    """一次攻击请求与响应样本。

    该结构用于记录每次发送的请求包、收到的回包、往返时延和部分解码字段，
    便于后续分析竞争链路的稳定性和协议行为。
    """

    timestamp_s: float
    profile: str
    sequence_index: int
    request_packet: bytes
    response_packet: bytes | None
    response_addr: tuple[str, int] | None
    rtt_ms: float | None
    response_received: bool
    request_payload: dict[str, Any]
    request_label: str | None = None
    response_frame_number: int | None = None
    response_main_motor_rpm: int | None = None
    response_depth_m: float | None = None


@dataclass
class StationStats:
    """攻击站运行统计信息。"""

    sent: int = 0
    received: int = 0
    rtts_ms: list[float] = field(default_factory=list)

    @property
    def lost(self) -> int:
        """返回未收到响应的请求数量。"""
        return self.sent - self.received

    def record(self, sample: AttackSample) -> None:
        """记录一次样本并更新统计值。"""
        self.sent += 1
        if sample.response_received:
            self.received += 1
        if sample.rtt_ms is not None:
            self.rtts_ms.append(float(sample.rtt_ms))


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    该函数为攻击站脚本提供完整命令行接口，支持配置网络端点（Mock AMD 主机/端口）、
    运行参数（时长、发送频率、响应超时）、输出选项（CSV 记录、实时报告）和测试配置（攻击模式、seed）。

    @return：解析后的命令行参数命名空间，包含以下属性：
        - mock_amd_host: Mock AMD 目标主机（默认 127.0.0.1）
        - mock_amd_port: Mock AMD 目标 UDP 端口（默认 52364）
        - listen_host: 本地监听主机（默认 0.0.0.0）
        - listen_port: 本地监听端口（默认 52367）
        - profile: 攻击模式（'conflict'/'sweep'/'heartbeat'）
        - duration: 运行时长秒数（0 表示持续运行到 Ctrl-C）
        - rate_hz: 发送频率Hz（None 表示根据 profile 自动选择）
        - response_timeout_s: 等待单次 $AUV 响应的超时秒数
        - report_interval_s: 控制台摘要打印间隔秒数
        - csv: 是否启用 CSV 跟踪输出
        - live_report: 是否启用实时统计打印
        - obj_address: 协议对象地址
        - main_motor_rpm_scale: 推力转RPM缩放系数
        - side_motor_rpm: 侧推电机嵌入转速
        - seed: RNG 种子（None 表示非确定性）
        - csv_path: CSV 输出路径（None 表示自动生成）
    @throws SystemExit: 参数解析失败或请求帮助时
    """
    parser = argparse.ArgumentParser(description="Attacker station for Mock AMD traffic")
    parser.add_argument("--mock-amd-host", default="127.0.0.1", help="Mock AMD host")
    parser.add_argument("--mock-amd-port", type=int, default=52364, help="Mock AMD UDP port")
    parser.add_argument("--listen-host", default="0.0.0.0", help="Local host to bind for responses")
    parser.add_argument("--listen-port", type=int, default=52367, help="Local UDP port to bind")
    parser.add_argument("--profile", choices=PROFILE_CHOICES, default="conflict", help="Traffic profile")
    parser.add_argument("--duration", type=float, default=10.0, help="Run duration in seconds; 0 means until Ctrl-C")
    parser.add_argument("--rate-hz", type=float, default=None, help="Send rate in Hz; defaults depend on profile")
    parser.add_argument("--response-timeout-s", type=float, default=1.0, help="Wait time for each $AUV response")
    parser.add_argument("--report-interval-s", type=float, default=10.0, help="How often to print live summary")
    parser.add_argument(
        "--csv",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable CSV trace output",
    )
    parser.add_argument(
        "--live-report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable periodic live summary output",
    )
    parser.add_argument("--obj-address", type=int, default=1, help="Protocol object address")
    parser.add_argument("--main-motor-rpm-scale", type=float, default=DEFAULT_MAIN_MOTOR_RPM_SCALE, help="Thrust to RPM scale")
    parser.add_argument("--side-motor-rpm", type=int, default=0, help="Side motor RPM to embed in outgoing frames")
    parser.add_argument("--seed", type=int, default=None, help="Seed for the conflict profile RNG")
    parser.add_argument("--csv-path", type=Path, default=None, help="CSV report path; defaults to log/attacker_station_<ts>.csv")
    return parser.parse_args()


def profile_default_rate_hz(profile: str) -> float:
    """根据攻击模式返回默认发送频率。

    该函数为不同的测试模式提供合理的发送速率默认值。heartbeat 和 sweep
    模式采用低频率（1.0 Hz）以便观察完整循环，conflict 模式采用高频率
    以加速竞争条件检验。

    @param profile: 攻击模式标识符（'conflict'/'sweep'/'heartbeat'）
    @return: 推荐发送频率（Hz）。heartbeat/sweep 返回 1.0 Hz，conflict 返回 2.0 Hz
    @note: 返回值仅为默认推荐，命令行 --rate-hz 可覆盖此值
    """
    if profile == "heartbeat":
        return 1.0
    if profile == "sweep":
        return 1.0
    return 2.0


def _make_parameters(sequence_index: int) -> tuple[int, ...]:
    """构造协议参数组，首位携带当前 Unix 微秒时间戳。

    该辅助函数生成 12 个参数值的元组，供协议下行包（$CKTH）的 Para1-Para12 字段使用。
    首参数位用于嵌入发包时刻的微秒时间戳，便于末端分析延迟；其余位预留给测试扩展。

    @param sequence_index: 序列号（循环递增）
    @return: 长度为 12 的整数元组，Para[0]=current_us_timestamp，Para[1]=sequence_index，
            Para[2-11]=0
    @note: Unix 微秒时间戳可支持约 285 年的无重复覆盖
    """
    timestamp_us = int(time.time() * 1_000_000)
    return (timestamp_us, sequence_index, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def build_profile_payload(profile: str, sequence_index: int, rng: random.Random, config: AttackerStationConfig) -> dict[str, Any]:
    """根据攻击配置生成一条控制负载。

    该函数为三种攻击模式生成不同的协议负载：
    - heartbeat: 周期性发送无操作包（SEND_ONLY 模式），验证连接活性
    - sweep: 循环遍历 5 个预定义档位（zero/balanced/max_positive/overrange/reverse），
            覆盖控制指令的极限范围
    - conflict: 随机生成控制模式、姿态指令和工作指令的组合，模拟真实竞争场景

    @param profile: 攻击模式（'heartbeat'/'sweep'/'conflict'）
    @param sequence_index: 当前序列号，用于分派 sweep 档位或参数构造
    @param rng: 随机数生成器（用于 conflict 模式的随机值）
    @param config: 攻击站配置对象，含有电机参数缩放等信息
    @return: 协议负载字典，包含 KEY_CONTROL_MODE_BYTE/KEY_WORK_INSTRUCTION/
            KEY_RIGHT/KEY_LEFT/KEY_TOP/KEY_BOTTOM/KEY_THRUST 等
    @note: heartbeat 模式下所有舵面和推力置 0；sweep 覆盖 overrange（±120%）以检验饱和；
          conflict 模式舵面用均匀分布模拟竞争的多样性
    """
    frame_number = sequence_index % 256
    payload: dict[str, Any] = {
        KEY_FRAME_NUMBER: frame_number,
        KEY_OBJ_ADDRESS: config.obj_address,
        KEY_PARAMETERS: _make_parameters(sequence_index),
        KEY_SIDE_MOTOR_RPM: config.side_motor_rpm,
    }

    if profile == "heartbeat":
        payload.update(
            {
                KEY_CONTROL_MODE_BYTE: int(ControlModeByte.SEND_ONLY),
                KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
                KEY_RIGHT: 0.0,
                KEY_LEFT: 0.0,
                KEY_TOP: 0.0,
                KEY_BOTTOM: 0.0,
                KEY_THRUST: 0.0,
                KEY_ORIENTATION_DEG: 0.0,
            }
        )
        return payload

    if profile == "sweep":
        case = SWEEP_CASES[sequence_index % len(SWEEP_CASES)]
        payload.update({key: value for key, value in case.items() if key != "label"})
        payload[KEY_ORIENTATION_DEG] = float(case[KEY_ORIENTATION_DEG])
        payload[KEY_SIDE_MOTOR_RPM] = int(case[KEY_SIDE_MOTOR_RPM])
        payload[KEY_PARAMETERS] = (sequence_index, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        return payload

    control_mode_byte = rng.choice(
        [
            int(ControlModeByte.REMOTE_CONTROL),
            int(ControlModeByte.AUTO_FIXED_POINT),
            int(ControlModeByte.AUTO_DIRECTION),
            int(ControlModeByte.JETSON_PROTOCOL),
        ]
    )
    right = rng.uniform(-85.0, 85.0)
    left = -right + rng.uniform(-5.0, 5.0)
    top = rng.uniform(-60.0, 60.0)
    bottom = -top + rng.uniform(-4.0, 4.0)
    thrust = rng.uniform(-100.0, 100.0)
    work_instruction = rng.choice(
        [int(WorkInstruction.NONE), int(WorkInstruction.AUTONOMOUS_CONTROL), int(WorkInstruction.TASK_START)]
    )
    payload.update(
        {
            KEY_CONTROL_MODE_BYTE: control_mode_byte,
            KEY_WORK_INSTRUCTION: work_instruction,
            KEY_RIGHT: right,
            KEY_LEFT: left,
            KEY_TOP: top,
            KEY_BOTTOM: bottom,
            KEY_THRUST: thrust,
            KEY_ORIENTATION_DEG: rng.uniform(0.0, 360.0),
            KEY_SIDE_MOTOR_RPM: int(rng.uniform(-180.0, 180.0)),
        }
    )
    return payload


def format_p99(values_ms: list[float]) -> float | None:
    """计算 P99 往返时延。

    该函数基于收集的 RTT 样本计算 99 百分位延迟数值，用于评估控制链路的极端延迟性能。
    P99 反映了 99% 的包在该延迟以内收到，1% 可能超过此值。

    @param values_ms: 往返时延列表（毫秒）
    @return: P99 延迟值（毫秒）；若列表为空则返回 None
    @throws: 无异常抛出，空列表时返回 None
    """
    if not values_ms:
        return None
    ordered = sorted(values_ms)
    index = int(math.ceil((len(ordered) - 1) * 0.99))
    index = min(max(index, 0), len(ordered) - 1)
    return ordered[index]


def format_summary(stats: StationStats, *, profile: str, elapsed_s: float) -> str:
    """格式化当前运行摘要，供终端实时打印。

    该函数将运行统计（发送数、接收数、损失数、RTT 分布）整合为单行摘要字符串，
    便于在控制台实时观察攻击站的链路质量与负载特征。

    @param stats: 包含发送/接收计数和 RTT 样本列表的统计对象
    @param profile: 攻击模式标签（用于摘要识别）
    @param elapsed_s: 已运行时长秒数
    @return: 格式化摘要字符串，含 Sent/Received/Lost/Avg RTT/P99 RTT 等信息
    @note: 若无 RTT 样本则用 'n/a' 表示不可用
    """
    avg_rtt = statistics.fmean(stats.rtts_ms) if stats.rtts_ms else None
    p99_rtt = format_p99(stats.rtts_ms)
    avg_text = f"{avg_rtt:.1f}ms" if avg_rtt is not None else "n/a"
    p99_text = f"{p99_rtt:.1f}ms" if p99_rtt is not None else "n/a"
    return (
        f"[AttackerStation] Profile: {profile} | Elapsed: {elapsed_s:.1f}s | "
        f"Sent: {stats.sent} | Received: {stats.received} | Lost: {stats.lost} | "
        f"Avg RTT: {avg_text} | P99 RTT: {p99_text}"
    )


class AttackerStation:
    """攻击站运行器，负责发包、收包、统计与日志落盘。"""

    def __init__(self, config: AttackerStationConfig, sock: socket.socket, csv_path: Path | None = None) -> None:
        """初始化 socket、统计对象、随机数和 CSV 输出状态。"""
        self.config = config
        self.sock = sock
        self.stats = StationStats()
        self.rng = random.Random(config.seed)
        self.csv_path = csv_path if csv_path is not None else config.csv_path
        self._csv_file: Any | None = None
        self._csv_writer: Any | None = None
        self._start_monotonic_s = time.monotonic()
        self._last_report_monotonic_s = self._start_monotonic_s
        self._send_started_perf_counter = self._start_monotonic_s

    def close(self) -> None:
        """关闭 CSV 文件句柄。"""
        if self._csv_file is not None:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None

    def _ensure_csv_writer(self) -> Any | None:
        """按需创建 CSV 写入器。"""
        if not self.config.enable_csv or self.csv_path is None:
            return None
        if self._csv_writer is not None:
            return self._csv_writer

        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.csv_path.exists()
        self._csv_file = self.csv_path.open("a", newline="", encoding="utf-8")
        fieldnames = [
            "timestamp_s",
            "profile",
            "sequence_index",
            "request_label",
            "control_mode_byte",
            "work_instruction",
            "right_deg",
            "left_deg",
            "top_deg",
            "bottom_deg",
            "thrust_percent",
            "rtt_ms",
            "response_received",
            "response_addr",
            "response_frame_number",
            "response_main_motor_rpm",
            "response_depth_m",
        ]
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=fieldnames)
        if not file_exists:
            self._csv_writer.writeheader()
        return self._csv_writer

    def _await_response(self) -> tuple[bytes | None, tuple[str, int] | None, float | None]:
        """等待一条 $AUV 响应并计算 RTT。"""
        self.sock.settimeout(self.config.response_timeout_s)
        try:
            response_packet, response_addr = self.sock.recvfrom(4096)
        except socket.timeout:
            return None, None, None
        rtt_ms = (time.perf_counter() - self._send_started_perf_counter) * 1000.0
        return response_packet, response_addr, rtt_ms

    def _log_sample(self, sample: AttackSample) -> None:
        """将单次样本写入 CSV。"""
        csv_writer = self._ensure_csv_writer()
        if csv_writer is None:
            return
        csv_writer.writerow(
            {
                "timestamp_s": f"{sample.timestamp_s:.6f}",
                "profile": sample.profile,
                "sequence_index": sample.sequence_index,
                "request_label": sample.request_label or "",
                "control_mode_byte": sample.request_payload[KEY_CONTROL_MODE_BYTE],
                "work_instruction": sample.request_payload[KEY_WORK_INSTRUCTION],
                "right_deg": f"{float(sample.request_payload[KEY_RIGHT]):.3f}",
                "left_deg": f"{float(sample.request_payload[KEY_LEFT]):.3f}",
                "top_deg": f"{float(sample.request_payload[KEY_TOP]):.3f}",
                "bottom_deg": f"{float(sample.request_payload[KEY_BOTTOM]):.3f}",
                "thrust_percent": f"{float(sample.request_payload[KEY_THRUST]):.3f}",
                "rtt_ms": "timeout" if sample.rtt_ms is None else f"{sample.rtt_ms:.3f}",
                "response_received": str(sample.response_received).lower(),
                "response_addr": "" if sample.response_addr is None else f"{sample.response_addr[0]}:{sample.response_addr[1]}",
                "response_frame_number": "" if sample.response_frame_number is None else sample.response_frame_number,
                "response_main_motor_rpm": "" if sample.response_main_motor_rpm is None else sample.response_main_motor_rpm,
                "response_depth_m": "" if sample.response_depth_m is None else f"{sample.response_depth_m:.3f}",
            }
        )
        self._csv_file.flush()

    def _maybe_print_report(self, *, force: bool = False) -> None:
        """按配置周期打印实时摘要。"""
        if not self.config.enable_live_report:
            return
        now_monotonic_s = time.monotonic()
        elapsed_s = now_monotonic_s - self._start_monotonic_s
        if not force and (now_monotonic_s - self._last_report_monotonic_s) < self.config.report_interval_s:
            return
        self._last_report_monotonic_s = now_monotonic_s
        print(format_summary(self.stats, profile=self.config.profile, elapsed_s=elapsed_s))

    def send_one(self, sequence_index: int) -> AttackSample:
        """发送一次控制包并收集响应样本。

        该方法支撑一次收派周期：根据 profile 模式构造负载、发送 $CKTH 控制包、
        等待响应、计算 RTT 并字段提取。即使接收失败也会清空样本中的响应字段。

        @param sequence_index: 序列号，用作 frame_number 余数
        @return: AttackSample 样本对象，已写入 CSV 跟踪和统计计数器
        @throws IOError: CSV 跟踪失败时不投出，仅记录该样本
        @note: 该方法是线程不安全的，仅供主循环单线程调用
        """
        payload = build_profile_payload(self.config.profile, sequence_index, self.rng, self.config)
        request_packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=self.config.main_motor_rpm_scale)
        self._send_started_perf_counter = time.perf_counter()
        self.sock.sendto(request_packet, (self.config.mock_amd_host, self.config.mock_amd_port))
        response_packet, response_addr, rtt_ms = self._await_response()

        response_frame_number: int | None = None
        response_main_motor_rpm: int | None = None
        response_depth_m: float | None = None
        if response_packet is not None:
            try:
                telemetry = parse_uplink_packet(response_packet)
            except Exception:
                telemetry = None
            if telemetry is not None:
                response_frame_number = telemetry.frame_number
                response_main_motor_rpm = telemetry.main_motor_rpm
                response_depth_m = telemetry.depth_m

        sample = AttackSample(
            timestamp_s=time.time(),
            profile=self.config.profile,
            sequence_index=sequence_index,
            request_packet=request_packet,
            response_packet=response_packet,
            response_addr=response_addr,
            rtt_ms=rtt_ms,
            response_received=response_packet is not None,
            request_payload=payload,
            request_label=payload.get("label"),
            response_frame_number=response_frame_number,
            response_main_motor_rpm=response_main_motor_rpm,
            response_depth_m=response_depth_m,
        )
        self.stats.record(sample)
        self._log_sample(sample)
        return sample

    def run(self) -> StationStats:
        """运行攻击站主循环，直到超时或收到停止信号。

        该方法执行完整的运行会话：根据 config.duration_s 设置截止时间线（0 表示永远运行），
        注册 SIGINT/SIGTERM 信号处理、发包主循环、实时摘要打印、清资源、返回统计。
        发送间隔由 config.rate_hz 控制；如超过此频率则调用 time.sleep() 补偿。
        run_forever 模式下会一直循环直到收到停止信号。

        @return: 返回整个运行过程的月 StationStats 对象，包含发送数、接收数、损失数、RTT 列表
        @note: 该方法捕获 KeyboardInterrupt 并正常中断（finally 块会清资源）。
               SIGINT/SIGTERM 不会直接异常，仅设置内部 stop_requested 标志;
               发包结束前强制打印一次摘要（_maybe_print_report(force=True)）。
        """
        rate_hz = self.config.rate_hz if self.config.rate_hz is not None else profile_default_rate_hz(self.config.profile)
        interval_s = 0.0 if rate_hz <= 0 else 1.0 / rate_hz
        stop_requested = {"value": False}

        def _request_stop(signum, frame) -> None:
            stop_requested["value"] = True

        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)

        sequence_index = 0
        run_forever = self.config.duration_s <= 0.0
        deadline_s = self._start_monotonic_s + self.config.duration_s

        try:
            while not stop_requested["value"]:
                if not run_forever and time.monotonic() >= deadline_s:
                    break
                loop_started_s = time.monotonic()
                self.send_one(sequence_index)
                sequence_index += 1
                self._maybe_print_report()
                elapsed_s = time.monotonic() - loop_started_s
                sleep_s = interval_s - elapsed_s
                if sleep_s > 0:
                    time.sleep(sleep_s)
        finally:
            self._maybe_print_report(force=True)
            self.close()
        return self.stats


def build_default_csv_path() -> Path:
    """生成默认 CSV 路径，落在项目 log 目录下。

    该函数为未指定 --csv-path 时的备选方案：在项目根目录下创建 log 子目录（若不存在），
    并以 attacker_station_YYYYMMDD_HHMMSS.csv 格式生成时间戳文件名。

    @return: Path 对象，指向 PROJECT_ROOT/log/attacker_station_*.csv 文件
    @note: 若 log 目录不存在会自动创建（parents=True）；时间戳基于本地时区
    """
    log_dir = PROJECT_ROOT / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return log_dir / f"attacker_station_{timestamp}.csv"


def main() -> int:
    """脚本入口，解析参数后启动攻击站。

    该函数是攻击站脚本的主进路：解析命令行参数、构造 AttackerStationConfig 对象、
    绑定本地 socket 监听地址、创建 AttackerStation 实例并运行、报告最终统计。
    命令行参数支持覆盖配置类中的所有字段，包括网络端点、运行时长、发送频率、CSV 输出等。

    @return: 返回进程退出码（0 表示成功，1 表示异常及缺失参数）
    @throws SystemExit: 参数解析失败时由 argparse 投出
    @note: 脚本启动时若 listen_port 已被占用则 socket.bind() 会报错并导致异常；
           CSV 路径支持自动生成（若未指定则使用 build_default_csv_path()）；
           攻击站运行后会打印最终统计摘要到控制台。
    """
    args = parse_args()
    config = AttackerStationConfig(
        mock_amd_host=args.mock_amd_host,
        mock_amd_port=args.mock_amd_port,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        profile=args.profile,
        duration_s=args.duration,
        rate_hz=args.rate_hz,
        response_timeout_s=args.response_timeout_s,
        report_interval_s=args.report_interval_s,
        enable_csv=args.csv,
        enable_live_report=args.live_report,
        obj_address=args.obj_address,
        main_motor_rpm_scale=args.main_motor_rpm_scale,
        side_motor_rpm=args.side_motor_rpm,
        seed=args.seed,
        csv_path=None if not args.csv else (args.csv_path or build_default_csv_path()),
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((config.listen_host, config.listen_port))
    print(
        f"[AttackerStation] listening on udp://{config.listen_host}:{config.listen_port}, "
        f"target udp://{config.mock_amd_host}:{config.mock_amd_port}, profile={config.profile}"
    )

    station = AttackerStation(config=config, sock=sock)
    try:
        station.run()
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())