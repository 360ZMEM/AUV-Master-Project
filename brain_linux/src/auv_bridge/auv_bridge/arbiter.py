'''
本文件定义了 AUV 桥接节点的命令仲裁核心，负责根据来自 PC 的原始控制命令和来自 Jetson 的 MPC 输出进行模式切换和命令选择，输出最终的控制指令供下游传输模块使用。
具体来说核心步骤和过程：
- 接收并规范化来自 PC 的原始控制命令，提取关键字段（如工作指令、控制模式字节等）以判断当前的控制模式和优先级。
- 接收并规范化来自 Jetson 的 MPC 输出，检查其有效性和健康状态以决定是否可以作为自动控制的来源。
- 根据当前模式（远程或自动）和命令来源的状态，进行仲裁决策：如果处于自动模式且MPC输出新鲜且有效，则使用MPC命令；如果MPC输出过期或无效，则使用安全回退命令；如果处于远程模式，则使用PC原始命令（如果存在）或默认远程命令。
- 提供一个统一的决策结果数据类 ArbiterDecision，包含当前有效的控制模式、命令来源、最终的命令负载以及一些状态标志（如MPC命令是否有效、是否处于手动覆盖等），供下游模块消费。
- 支持外部强制切换回远程模式的接口，以便在安全检查失败或手动接管时快速恢复到远程控制状态。
- 内部实现细节包括命令规范化、过期检查、命令构建等，确保仲裁逻辑的清晰和健壮。
其中，接收PC指令的条件：当接收到的命令包含有效的工作指令和控制模式字节时，且工作指令为任务取消或清除故障时，仲裁器将切换到远程模式。
在代码逻辑上，即当 update_pc_raw_command() 方法被调用时，仲裁器会检查 payload 中的 KEY_WORK_INSTRUCTION 和 KEY_CONTROL_MODE_BYTE 字段：
- 如果 KEY_WORK_INSTRUCTION 的值对应于 WorkInstruction.TASK_CANCEL 或 WorkInstruction.CLEAR_FAULT，则将 self._mode 设置为 ArbiterMode.REMOTE。
- 否则，如果 KEY_CONTROL_MODE_BYTE 的值对应于 ControlModeByte.JETSON_PROTOCOL，则将 self._mode 设置为 ArbiterMode.AUTONOMOUS。
- 否则，默认将 self._mode 设置为 ArbiterMode.REMOTE。
因此，PC 指令中的特定工作指令（任务取消或清除故障）会直接触发仲裁器切换回远程模式，而控制模式字节则决定了是否进入自动模式。仲裁器的决策逻辑会根据当前模式和命令状态输出最终的控制指令负载。
'''

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from common.enums import ArbiterMode, ArbiterSource, ControlModeByte, WorkInstruction
from common.protocol import (
    KEY_BOTTOM, # 下鳍指令值，范围 -100~100，表示下鳍的偏转程度（负值向左偏转，正值向右偏转）
    KEY_BOTTOM_PROTECT_PARAMS,
    KEY_CONTROL_MODE_BYTE,
    KEY_DEPTH_PROTECT_PARAMS,
    KEY_FRAME_NUMBER,
    KEY_HEALTHY,
    KEY_LEFT,
    KEY_NOTE,
    KEY_OBJ_ADDRESS,
    KEY_ORIENTATION_DEG,
    KEY_PARAMETERS,
    KEY_PRESET_TIME_TENTHS_MIN,
    KEY_RIGHT,
    KEY_SIDE_MOTOR_RPM,
    KEY_SOURCE,
    KEY_SPARE_PARAMS,
    KEY_THRUST,
    KEY_TOP,
    KEY_TS,
    KEY_VALID,
    KEY_WORK_INSTRUCTION,
    KEY_TARGET_DEPTH_M,
    normalize_control_command,
)

_MPC_FIELD_MAP = {
    "right_fin_deg": KEY_RIGHT,
    "top_fin_deg": KEY_TOP,
    "left_fin_deg": KEY_LEFT,
    "bottom_fin_deg": KEY_BOTTOM,
    "thrust_percent": KEY_THRUST,
}


@dataclass(frozen=True)
class ArbiterDecision:
    """Arbiter output snapshot for downstream transport code."""

    active_arbiter: ArbiterMode
    arbiter_source: ArbiterSource
    command_payload: dict[str, Any]
    mpc_command_valid: bool
    manual_override_active: bool


class CommandArbiter:
    """Pure arbitration core independent from ROS2 and transport details.

    实现“带透明路由功能的条件拦截器”（Conditional Interceptor with Transparent Routing）：
    - 手动模式 (REMOTE)：原封不动转发 PC 原始指令（透明路由）
    - 自主模式 (AUTONOMOUS)：使用 MPC 输出，丢弃 PC 推力字段
    """

    def __init__(self, *, mpc_timeout_s: float = 0.5, default_obj_address: int = 1,
                 pc_timeout_s: float = 1.5, pc_soft_warning_s: float = 1.0,
                 default_depth_protect_params: tuple[int, int] = (0, 0),
                 default_bottom_protect_params: tuple[int, int] = (0, 0),
                 default_preset_time_tenths_min: int = 0) -> None:
        self.mpc_timeout_s = float(mpc_timeout_s)
        self.default_obj_address = int(default_obj_address)
        # /**
        #  * @brief PC104 空板实物联调可配置默认 remote 保护参数，避免 idle 包清零安全阈值。
        #  * @date 2026-07-11
        #  * @author 清华 AUV 课题组
        #  */
        self.default_depth_protect_params = self._coerce_u16_pair(default_depth_protect_params)
        self.default_bottom_protect_params = self._coerce_u16_pair(default_bottom_protect_params)
        self.default_preset_time_tenths_min = max(0, min(65535, int(default_preset_time_tenths_min)))
        # 新增：分层超时机制（Tiered Watchdog）
        self.pc_timeout_s = float(pc_timeout_s)            # 1.5s Hard ESTOP
        self.pc_soft_warning_s = float(pc_soft_warning_s)  # 1.0s Soft Warning

        self._mode = ArbiterMode.REMOTE
        self._last_pc_raw: dict[str, Any] | None = None
        self._last_pc_ts = 0.0
        self._last_mpc: dict[str, Any] | None = None
        self._last_mpc_ts = 0.0
        self._last_decision_mode = ArbiterMode.REMOTE
        self.pc_link_status = "OK"  # "OK" / "WEAK" / "LOST"

    @property
    def active_mode(self) -> ArbiterMode:
        return self._mode

    def reset_all_buffers(self) -> None:
        """在模式切换时清空所有历史指令缓存，防止旧指令残留。"""
        self._last_mpc = None
        self._last_mpc_ts = 0.0

    def check_pc_link_health(self, *, now: float | None = None) -> str:
        """检查上位机链路健康状态：OK / WEAK / LOST"""
        stamp = time.time() if now is None else float(now)
        if self._last_pc_ts <= 0:
            return "OK"
        dt = stamp - self._last_pc_ts
        if dt > self.pc_timeout_s:
            return "LOST"
        if dt > self.pc_soft_warning_s:
            return "WEAK"
        return "OK"

    def update_pc_raw_command(self, payload: Any, *, now: float | None = None) -> ArbiterDecision:
        stamp = time.time() if now is None else float(now)
        normalized = self._normalize_pc_raw_command(payload, ts=stamp)
        self._last_pc_raw = normalized
        self._last_pc_ts = stamp

        work_instruction = int(normalized[KEY_WORK_INSTRUCTION])
        control_mode_byte = int(normalized[KEY_CONTROL_MODE_BYTE])

        if work_instruction in {int(WorkInstruction.TASK_CANCEL), int(WorkInstruction.CLEAR_FAULT)}:
            self._mode = ArbiterMode.REMOTE
            self.reset_all_buffers()
        elif control_mode_byte == int(ControlModeByte.JETSON_PROTOCOL):
            self._mode = ArbiterMode.AUTONOMOUS
        else:
            if self._mode == ArbiterMode.AUTONOMOUS:
                self.reset_all_buffers()
            self._mode = ArbiterMode.REMOTE

        return self.decide(now=stamp)

    def update_mpc_command(self, payload: dict[str, Any], *, now: float | None = None) -> ArbiterDecision:
        stamp = time.time() if now is None else float(now)
        self._last_mpc = self._normalize_mpc_command(payload, ts=stamp)
        self._last_mpc_ts = stamp
        return self.decide(now=stamp)

    def force_remote(
        self,
        payload: dict[str, Any] | None = None,
        *,
        now: float | None = None,
        refresh_pc_timestamp: bool = True,
    ) -> ArbiterDecision:
        """Force the arbiter back to remote mode after guard rejection or manual takeover."""
        stamp = time.time() if now is None else float(now)
        old_mode = self._mode
        self._mode = ArbiterMode.REMOTE
        self.reset_all_buffers()

        if payload is not None:
            self._last_pc_raw = self._normalize_pc_raw_command(self._coerce_remote_payload(payload), ts=stamp)
            if refresh_pc_timestamp:
                self._last_pc_ts = stamp
        elif self._last_pc_raw is not None:
            self._last_pc_raw = self._normalize_pc_raw_command(self._coerce_remote_payload(self._last_pc_raw), ts=stamp)
            if refresh_pc_timestamp:
                self._last_pc_ts = stamp
        else:
            self._last_pc_raw = self._default_remote_payload(ts=stamp)
            if refresh_pc_timestamp:
                self._last_pc_ts = stamp

        return self.decide(now=stamp)

    def decide(self, *, now: float | None = None) -> ArbiterDecision:
        stamp = time.time() if now is None else float(now)
        self.pc_link_status = self.check_pc_link_health(now=stamp)

        if self._last_decision_mode != self._mode:
            self.reset_all_buffers()
            self._last_decision_mode = self._mode

        if self._mode == ArbiterMode.AUTONOMOUS:
            if self._has_fresh_valid_mpc(stamp):
                return ArbiterDecision(
                    active_arbiter=ArbiterMode.AUTONOMOUS,
                    arbiter_source=ArbiterSource.JETSON_MPC,
                    command_payload=self._build_autonomous_payload(),
                    mpc_command_valid=True,
                    manual_override_active=False,
                )
            return ArbiterDecision(
                active_arbiter=ArbiterMode.AUTONOMOUS,
                arbiter_source=ArbiterSource.SAFETY_FALLBACK,
                command_payload=self._build_safety_fallback_payload(ts=stamp),
                mpc_command_valid=False,
                manual_override_active=False,
            )

        # REMOTE 模式：透明路由 PC 原始指令
        if self._last_pc_raw is not None:
            # 透明路由：原封不动转发 PC 包的执行器字段
            passthrough = {
                KEY_FRAME_NUMBER: self._last_pc_raw.get(KEY_FRAME_NUMBER, 0),
                KEY_OBJ_ADDRESS: self._last_pc_raw.get(KEY_OBJ_ADDRESS, self.default_obj_address),
                KEY_CONTROL_MODE_BYTE: int(self._last_pc_raw.get(KEY_CONTROL_MODE_BYTE, 0x01)),
                KEY_WORK_INSTRUCTION: self._last_pc_raw.get(KEY_WORK_INSTRUCTION, 0),
                KEY_THRUST: float(self._last_pc_raw.get(KEY_THRUST, 0.0)),
                KEY_LEFT: float(self._last_pc_raw.get(KEY_LEFT, 0.0)),
                KEY_RIGHT: float(self._last_pc_raw.get(KEY_RIGHT, 0.0)),
                KEY_TOP: float(self._last_pc_raw.get(KEY_TOP, 0.0)),
                KEY_BOTTOM: float(self._last_pc_raw.get(KEY_BOTTOM, 0.0)),
                KEY_SIDE_MOTOR_RPM: int(self._last_pc_raw.get(KEY_SIDE_MOTOR_RPM, 0)),
                KEY_ORIENTATION_DEG: float(self._last_pc_raw.get(KEY_ORIENTATION_DEG, 0.0)),
                KEY_DEPTH_PROTECT_PARAMS: self._last_pc_raw.get(
                    KEY_DEPTH_PROTECT_PARAMS, self.default_depth_protect_params
                ),
                KEY_BOTTOM_PROTECT_PARAMS: self._last_pc_raw.get(
                    KEY_BOTTOM_PROTECT_PARAMS, self.default_bottom_protect_params
                ),
                KEY_PRESET_TIME_TENTHS_MIN: self._last_pc_raw.get(
                    KEY_PRESET_TIME_TENTHS_MIN, self.default_preset_time_tenths_min
                ),
                KEY_SPARE_PARAMS: self._last_pc_raw.get(KEY_SPARE_PARAMS, (0, 0)),
                KEY_PARAMETERS: self._last_pc_raw.get(KEY_PARAMETERS, (0,) * 12),
                KEY_TS: self._last_pc_raw.get(KEY_TS, stamp),
            }
            return ArbiterDecision(
                active_arbiter=ArbiterMode.REMOTE,
                arbiter_source=ArbiterSource.PC_RAW,
                command_payload=passthrough,
                mpc_command_valid=False,
                manual_override_active=self._is_manual_override(self._last_pc_raw),
            )

        return ArbiterDecision(
            active_arbiter=ArbiterMode.REMOTE,
            arbiter_source=ArbiterSource.NONE,
            command_payload=self._default_remote_payload(ts=stamp),
            mpc_command_valid=False,
            manual_override_active=False,
        )

    def _has_fresh_valid_mpc(self, now: float) -> bool:
        if self._last_mpc is None:
            return False
        if now - self._last_mpc_ts > self.mpc_timeout_s:
            return False
        return bool(self._last_mpc.get(KEY_VALID, False)) and bool(self._last_mpc.get(KEY_HEALTHY, False))

    def _build_autonomous_payload(self) -> dict[str, Any]:
        base = self._base_payload_for_autonomy()
        assert self._last_mpc is not None
        merged = dict(base)
        merged[KEY_RIGHT] = float(self._last_mpc[KEY_RIGHT])
        merged[KEY_TOP] = float(self._last_mpc[KEY_TOP])
        merged[KEY_LEFT] = float(self._last_mpc[KEY_LEFT])
        merged[KEY_BOTTOM] = float(self._last_mpc[KEY_BOTTOM])
        merged[KEY_THRUST] = float(self._last_mpc[KEY_THRUST])
        if KEY_TARGET_DEPTH_M in self._last_mpc:
            merged[KEY_TARGET_DEPTH_M] = float(self._last_mpc[KEY_TARGET_DEPTH_M])
        if KEY_WORK_INSTRUCTION in self._last_mpc and self._last_mpc[KEY_WORK_INSTRUCTION] != 0:
            merged[KEY_WORK_INSTRUCTION] = int(self._last_mpc[KEY_WORK_INSTRUCTION])
        else:
            merged[KEY_WORK_INSTRUCTION] = int(WorkInstruction.AUTONOMOUS_CONTROL)
        merged[KEY_CONTROL_MODE_BYTE] = int(ControlModeByte.JETSON_PROTOCOL)
        return merged

    def _build_safety_fallback_payload(self, *, ts: float) -> dict[str, Any]:
        base = self._base_payload_for_autonomy()
        base[KEY_RIGHT] = 0.0
        base[KEY_TOP] = 0.0
        base[KEY_LEFT] = 0.0
        base[KEY_BOTTOM] = 0.0
        base[KEY_THRUST] = 0.0
        base[KEY_WORK_INSTRUCTION] = int(WorkInstruction.AUTONOMOUS_CONTROL)
        base[KEY_CONTROL_MODE_BYTE] = int(ControlModeByte.JETSON_PROTOCOL)
        base[KEY_TS] = float(ts)
        return base

    def _base_payload_for_autonomy(self) -> dict[str, Any]:
        if self._last_pc_raw is not None:
            return dict(self._last_pc_raw)
        return self._default_remote_payload()

    def _default_remote_payload(self, *, ts: float | None = None) -> dict[str, Any]:
        payload_ts = time.time() if ts is None else float(ts)
        return {
            KEY_FRAME_NUMBER: 0,
            KEY_OBJ_ADDRESS: self.default_obj_address,
            KEY_CONTROL_MODE_BYTE: int(ControlModeByte.REMOTE_CONTROL),
            KEY_WORK_INSTRUCTION: int(WorkInstruction.NONE),
            KEY_RIGHT: 0.0,
            KEY_TOP: 0.0,
            KEY_LEFT: 0.0,
            KEY_BOTTOM: 0.0,
            KEY_THRUST: 0.0,
            KEY_SIDE_MOTOR_RPM: 0,
            KEY_ORIENTATION_DEG: 0.0,
            KEY_DEPTH_PROTECT_PARAMS: self.default_depth_protect_params,
            KEY_BOTTOM_PROTECT_PARAMS: self.default_bottom_protect_params,
            KEY_PRESET_TIME_TENTHS_MIN: self.default_preset_time_tenths_min,
            KEY_SPARE_PARAMS: (0, 0),
            KEY_PARAMETERS: (0,) * 12,
            KEY_TS: payload_ts,
        }

    @staticmethod
    def _coerce_u16_pair(value: Any) -> tuple[int, int]:
        try:
            first, second = value
        except (TypeError, ValueError):
            first, second = 0, 0
        return (
            max(0, min(65535, int(first))),
            max(0, min(65535, int(second))),
        )

    @staticmethod
    def _coerce_remote_payload(payload: dict[str, Any]) -> dict[str, Any]:
        remote_payload = dict(payload)
        remote_payload[KEY_CONTROL_MODE_BYTE] = int(ControlModeByte.REMOTE_CONTROL)
        if int(remote_payload.get(KEY_WORK_INSTRUCTION, int(WorkInstruction.NONE))) == int(WorkInstruction.AUTONOMOUS_CONTROL):
            remote_payload[KEY_WORK_INSTRUCTION] = int(WorkInstruction.NONE)
        return remote_payload

    @staticmethod
    def _is_manual_override(payload: dict[str, Any]) -> bool:
        work_instruction = int(payload.get(KEY_WORK_INSTRUCTION, int(WorkInstruction.NONE)))
        return work_instruction in {int(WorkInstruction.TASK_CANCEL), int(WorkInstruction.CLEAR_FAULT)}

    def _normalize_pc_raw_command(self, payload: Any, *, ts: float) -> dict[str, Any]:
        if isinstance(payload, dict):
            command_payload = dict(payload)
        else:
            command_payload = {}

        normalized_command = normalize_control_command(payload)
        normalized = self._default_remote_payload(ts=ts)
        normalized.update(command_payload)
        normalized.update(normalized_command)
        normalized[KEY_FRAME_NUMBER] = int(normalized.get(KEY_FRAME_NUMBER, 0))
        normalized[KEY_OBJ_ADDRESS] = int(normalized.get(KEY_OBJ_ADDRESS, self.default_obj_address))
        normalized[KEY_CONTROL_MODE_BYTE] = int(
            normalized.get(KEY_CONTROL_MODE_BYTE, int(ControlModeByte.REMOTE_CONTROL))
        )
        normalized[KEY_WORK_INSTRUCTION] = int(normalized.get(KEY_WORK_INSTRUCTION, int(WorkInstruction.NONE)))
        normalized[KEY_SIDE_MOTOR_RPM] = int(normalized.get(KEY_SIDE_MOTOR_RPM, 0))
        normalized[KEY_ORIENTATION_DEG] = float(normalized.get(KEY_ORIENTATION_DEG, 0.0))
        normalized[KEY_DEPTH_PROTECT_PARAMS] = tuple(normalized.get(KEY_DEPTH_PROTECT_PARAMS, (0, 0)))
        normalized[KEY_BOTTOM_PROTECT_PARAMS] = tuple(normalized.get(KEY_BOTTOM_PROTECT_PARAMS, (0, 0)))
        normalized[KEY_PRESET_TIME_TENTHS_MIN] = int(normalized.get(KEY_PRESET_TIME_TENTHS_MIN, 0))
        normalized[KEY_SPARE_PARAMS] = tuple(normalized.get(KEY_SPARE_PARAMS, (0, 0)))
        normalized[KEY_PARAMETERS] = tuple(normalized.get(KEY_PARAMETERS, (0,) * 12))
        normalized[KEY_TS] = ts
        return normalized

    def _normalize_mpc_command(self, payload: dict[str, Any], *, ts: float) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("mpc payload must be a dict")

        canonical_payload = dict(payload)
        for src_key, dst_key in _MPC_FIELD_MAP.items():
            if src_key in canonical_payload and dst_key not in canonical_payload:
                canonical_payload[dst_key] = canonical_payload[src_key]

        normalized_command = normalize_control_command(canonical_payload)
        normalized = dict(normalized_command)
        normalized[KEY_SOURCE] = str(canonical_payload.get(KEY_SOURCE, canonical_payload.get("source", "JETSON_MPC")))
        normalized[KEY_VALID] = bool(canonical_payload.get(KEY_VALID, canonical_payload.get("valid", True)))
        normalized[KEY_HEALTHY] = bool(canonical_payload.get(KEY_HEALTHY, canonical_payload.get("healthy", True)))
        normalized[KEY_NOTE] = str(canonical_payload.get(KEY_NOTE, canonical_payload.get("note", "")))
        if KEY_TARGET_DEPTH_M in canonical_payload:
            normalized[KEY_TARGET_DEPTH_M] = float(canonical_payload[KEY_TARGET_DEPTH_M])
        normalized[KEY_TS] = ts
        return normalized
