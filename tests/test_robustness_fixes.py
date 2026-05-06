"""鲁棒性加固修复验证测试脚本。

验证5项修复：
1. NaN/Inf 拦截
2. 饱和度日志
3. 状态机切换原子性
4. DVL 延迟补偿
5. 链路自愈回调注册
"""
from __future__ import annotations

import math
import sys
import time

sys.path.insert(0, "/home/auv_user/auv_ws/AUV-Master-Project")
sys.path.insert(0, "/home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_bridge")
sys.path.insert(0, "/home/auv_user/auv_ws/AUV-Master-Project/algorithm")

from common.protocol import build_downlink_packet, parse_downlink_packet, KEY_THRUST, KEY_RIGHT, KEY_LEFT, KEY_TOP, KEY_BOTTOM
from common.physics import clamp_rudder_deg, clamp_thrust_percent, get_saturation_log, clear_saturation_log
from common.enums import ArbiterMode, ControlModeByte, WorkInstruction, DenyReason

def test_sanitize_float_nan():
    """验证 NaN 值被拦截并替换为 0.0"""
    print("[TEST 1] NaN 拦截测试...")
    packet = build_downlink_packet(
        {KEY_THRUST: float('nan'), KEY_RIGHT: 0.0, KEY_LEFT: 0.0, KEY_TOP: 0.0, KEY_BOTTOM: 0.0}
    )
    assert len(packet) == 72, f"Packet size mismatch: {len(packet)}"
    decoded = parse_downlink_packet(packet)
    assert decoded.thrust_percent == 0.0, f"NaN not sanitized: {decoded.thrust_percent}"
    print("  ✅ NaN 被成功拦截，推力=0.0")

def test_sanitize_float_inf():
    """验证 Inf 值被拦截"""
    print("[TEST 2] Inf 拦截测试...")
    packet = build_downlink_packet(
        {KEY_THRUST: float('inf'), KEY_RIGHT: float('-inf'), KEY_LEFT: 0.0, KEY_TOP: 0.0, KEY_BOTTOM: 0.0}
    )
    decoded = parse_downlink_packet(packet)
    assert decoded.thrust_percent == 0.0, f"Inf not sanitized: {decoded.thrust_percent}"
    assert decoded.right_fin_deg == 0.0, f"-Inf not sanitized: {decoded.right_fin_deg}"
    print("  ✅ Inf/-Inf 被成功拦截")

def test_saturation_logging():
    """验证饱和度日志功能"""
    print("[TEST 3] 饱和度日志测试...")
    clear_saturation_log()
    clamp_rudder_deg(50.0)  # 超出 45° 限制
    clamp_thrust_percent(150.0)  # 超出 100% 限制
    
    log = get_saturation_log()
    assert len(log) == 2, f"Expected 2 saturation records, got {len(log)}"
    assert log[0].name == "rudder_deg", f"Wrong name: {log[0].name}"
    assert log[0].raw_value == 50.0, f"Wrong raw_value: {log[0].raw_value}"
    assert log[0].clamped_value == 45.0, f"Wrong clamped_value: {log[0].clamped_value}"
    assert log[1].name == "thrust_percent", f"Wrong name: {log[1].name}"
    assert log[1].clamped_value == 100.0, f"Wrong clamped_value: {log[1].clamped_value}"
    print(f"  ✅ 饱和度日志记录正常：{log[0].name} {log[0].raw_value}->{log[0].clamped_value}, {log[1].name} {log[1].raw_value}->{log[1].clamped_value}")

def test_arbiter_mode_switch_reset():
    """验证模式切换时 buffer 重置"""
    print("[TEST 4] 状态机切换原子性测试...")
    from auv_bridge.arbiter import CommandArbiter
    
    arbiter = CommandArbiter(mpc_timeout_s=0.5)
    
    # 模拟自主模式
    arbiter.update_pc_raw_command({
        'control_mode_byte': int(ControlModeByte.JETSON_PROTOCOL),
        'work_instruction': int(WorkInstruction.NONE),
        KEY_THRUST: 50.0, KEY_RIGHT: 0.0, KEY_LEFT: 0.0, KEY_TOP: 0.0, KEY_BOTTOM: 0.0,
    }, now=10.0)
    
    arbiter.update_mpc_command({
        'thrust_percent': 80.0, 'right_fin_deg': 5.0,
        'top_fin_deg': 0.0, 'left_fin_deg': 0.0, 'bottom_fin_deg': 0.0,
        'valid': True, 'healthy': True,
    }, now=10.1)
    
    assert arbiter._last_mpc is not None, "MPC should be cached"
    assert arbiter._last_mpc_ts == 10.1, f"MPC timestamp mismatch: {arbiter._last_mpc_ts}"
    
    # 强制切换到 REMOTE
    decision = arbiter.force_remote(now=11.0)
    
    assert arbiter._last_mpc is None, f"MPC buffer not cleared after force_remote: {arbiter._last_mpc}"
    assert arbiter._last_mpc_ts == 0.0, f"MPC timestamp not cleared: {arbiter._last_mpc_ts}"
    assert decision.active_arbiter == ArbiterMode.REMOTE, f"Mode not switched: {decision.active_arbiter}"
    print("  ✅ 模式切换时 MPC buffer 成功清空")

def test_ekf_dvl_timestamp():
    """验证 EKF DVL 延迟补偿"""
    print("[TEST 5] EKF DVL 延迟补偿测试...")
    from es_ekf import ES_EKF
    
    cfg = {
        "gravity": 9.81, "auto_init": False, "use_first_dvl_for_init": False,
        "sigma_dvl": 0.03, "init_P_diag": [1.0] * 15,
        "init_pos": [0.0, 0.0, 0.0], "init_vel": [0.0, 0.0, 0.0],
        "init_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
        "enable_bias_calibration": False,
    }
    
    # 创建两个完全相同的 EKF 实例
    ekf_normal = ES_EKF(cfg)
    ekf_normal._initialized = True
    ekf_normal.p = [0.0, 0.0, 0.0]
    ekf_normal.v = [0.1, 0.0, 0.0]
    ekf_normal.q = [1.0, 0.0, 0.0, 0.0]
    ekf_normal.b_a = [0.0, 0.0, 0.0]
    ekf_normal.b_g = [0.0, 0.0, 0.0]
    
    ekf_delayed = ES_EKF(cfg)
    ekf_delayed._initialized = True
    ekf_delayed.p = [0.0, 0.0, 0.0]
    ekf_delayed.v = [0.1, 0.0, 0.0]
    ekf_delayed.q = [1.0, 0.0, 0.0, 0.0]
    ekf_delayed.b_a = [0.0, 0.0, 0.0]
    ekf_delayed.b_g = [0.0, 0.0, 0.0]
    
    dvl_vel = [0.5, 0.0, 0.0]
    current_time = 100.0
    
    # 正常延迟 (<50ms)
    ekf_normal.correct_dvl_with_timestamp(dvl_vel, dvl_timestamp=99.97, current_timestamp=current_time)
    P_normal = ekf_normal.P.copy()
    
    # 大延迟 (200ms > 50ms 阈值)
    ekf_delayed.correct_dvl_with_timestamp(dvl_vel, dvl_timestamp=99.8, current_timestamp=current_time)
    P_delayed = ekf_delayed.P.copy()
    
    # 验证延迟情况下协方差矩阵增大（因为增加了观测噪声）
    trace_normal = sum(P_normal[i,i] for i in range(15))
    trace_delayed = sum(P_delayed[i,i] for i in range(15))
    print(f"  trace_normal={trace_normal:.4f}, trace_delayed={trace_delayed:.4f}")
    assert trace_delayed > trace_normal, f"Delayed covariance should be larger"
    print("  ✅ DVL 延迟补偿正常：延迟导致协方差膨胀")

def test_deny_reason_enum():
    """验证新增的 COMM_LINK_FAILURE 枚举"""
    print("[TEST 6] DenyReason.COMM_LINK_FAILURE 枚举测试...")
    assert DenyReason.COMM_LINK_FAILURE.value == "COMM_LINK_FAILURE", f"Wrong value: {DenyReason.COMM_LINK_FAILURE.value}"
    print("  ✅ COMM_LINK_FAILURE 枚举正确")

def main():
    print("=" * 60)
    print("AUV 鲁棒性加固修复验证测试")
    print("=" * 60)
    
    tests = [
        test_sanitize_float_nan,
        test_sanitize_float_inf,
        test_saturation_logging,
        test_arbiter_mode_switch_reset,
        test_ekf_dvl_timestamp,
        test_deny_reason_enum,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ 测试失败: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("✅ 所有测试通过！可以启动完整运行链路。")

if __name__ == "__main__":
    main()
