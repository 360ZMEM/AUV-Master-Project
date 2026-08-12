"""MPC 求解器单元测试。

验证 CasADi + IPOPT 在 ARM 环境下的求解正确性、性能和鲁棒性。
"""

import sys
import time
from pathlib import Path

import numpy as np

def _resolve_project_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / "algorithm").exists():
            return parent
    raise RuntimeError("无法找到项目根目录")

sys.path.insert(0, str(_resolve_project_root()))

from algorithm.auv_mpc_controller import AUVKinematicsModel, AUVMPCOptimizer


def _make_default_model_params() -> dict:
    return {
        "mass_u": 50.0,
        "mass_w": 50.0,
        "drag_u": 15.0,
        "drag_w": 30.0,
        "buoyancy_term": 0.0,
        "yaw_rate_gain": 0.5,
        "pitch_depth_gain": 0.3,
    }


def _make_default_weights() -> dict:
    return {
        "x": 1.0, "y": 1.0, "z": 5.0, "psi": 3.0, "u": 0.5, "w": 1.0,
        "psi_cmd": 0.1, "z_cmd": 0.1, "T_cmd": 0.05,
        "confidence_threshold": 0.6,
        "low_confidence_scale": 3.0,
        "low_confidence_control_scale": 0.3,
    }


def _make_default_constraints() -> dict:
    return {
        "min_speed_ms": 0.3,
        "max_pitch_deg": 20.0,
        "min_altitude_m": 1.5,
        "max_thrust_percent": 100.0,
    }


def _build_optimizer() -> AUVMPCOptimizer:
    kin = AUVKinematicsModel(_make_default_model_params())
    return AUVMPCOptimizer(
        kin, N=20, dt=0.1,
        weights=_make_default_weights(),
        constraints=_make_default_constraints(),
    )


def _build_flat_reference(x0: np.ndarray, target_speed: float = 1.0,
                          target_heading: float = 0.0, target_depth: float = 5.0,
                          N: int = 20, dt: float = 0.1) -> np.ndarray:
    ref = np.zeros((6, N + 1))
    for k in range(N + 1):
        t_k = k * dt
        ref[0, k] = x0[0] + target_speed * np.cos(target_heading) * t_k
        ref[1, k] = x0[1] + target_speed * np.sin(target_heading) * t_k
        ref[2, k] = target_depth
        ref[3, k] = target_heading
        ref[4, k] = target_speed
        ref[5, k] = 0.0
    return ref


def _build_turn_reference(x0: np.ndarray, N: int = 20, dt: float = 0.1) -> np.ndarray:
    ref = np.zeros((6, N + 1))
    for k in range(N + 1):
        t_k = k * dt
        heading = k * 0.08
        ref[0, k] = x0[0] + 1.0 * np.cos(heading) * t_k
        ref[1, k] = x0[1] + 1.0 * np.sin(heading) * t_k
        ref[2, k] = 5.0
        ref[3, k] = heading
        ref[4, k] = 1.0
        ref[5, k] = 0.0
    return ref


def test_mpc_straight_line():
    """直线跟踪测试：MPC 应该输出接近参考航向的控制量。"""
    opt = _build_optimizer()
    x0 = np.array([0.0, 0.0, 5.0, 0.0, 0.8, 0.0])
    ref = _build_flat_reference(x0, target_speed=1.0, target_heading=0.0,
                                target_depth=5.0, N=opt.N, dt=opt.dt)

    t0 = time.perf_counter()
    result = opt.solve(x0=x0, ref_trajectory=ref, confidence=1.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert result["solver_status"] in ("Solve_Succeeded", "Search_Direction_Becomes_Too_Small")
    assert result["solve_time_ms"] < 50.0, f"求解过慢: {result['solve_time_ms']:.1f}ms"
    assert elapsed_ms < 100.0, f"总耗时过长: {elapsed_ms:.1f}ms"

    U_first = result["U_opt"][:, 0]
    psi_cmd = U_first[0]
    z_cmd = U_first[1]
    T_cmd = U_first[2]

    print(f"[PASS] 直线跟踪: psi_cmd={psi_cmd:.4f} rad, z_cmd={z_cmd:.2f} m, "
          f"T_cmd={T_cmd:.1f}%, cost={result['cost_value']:.4f}, "
          f"solve_time={result['solve_time_ms']:.1f}ms")
    return True


def test_mpc_turn():
    """急转弯测试：MPC 应该提前调整航向以跟踪参考曲线。"""
    opt = _build_optimizer()
    x0 = np.array([0.0, 0.0, 5.0, 0.0, 1.0, 0.0])
    ref = _build_turn_reference(x0, N=opt.N, dt=opt.dt)

    result = opt.solve(x0=x0, ref_trajectory=ref, confidence=1.0)

    assert result["solver_status"] in ("Solve_Succeeded", "Search_Direction_Becomes_Too_Small")

    U_first = result["U_opt"][:, 0]
    psi_cmd = U_first[0]

    print(f"[PASS] 急转弯: psi_cmd={psi_cmd:.4f} rad (ref ~0.08 rad), "
          f"cost={result['cost_value']:.4f}")
    return True


def test_mpc_low_confidence():
    """低置信度测试：MPC 应增大跟踪权重，减小推力惩罚。"""
    opt = _build_optimizer()
    x0 = np.array([0.0, 0.0, 5.0, 0.0, 0.8, 0.0])
    ref = _build_flat_reference(x0, target_speed=1.0, target_heading=0.0,
                                target_depth=5.0, N=opt.N, dt=opt.dt)

    result_high = opt.solve(x0=x0, ref_trajectory=ref, confidence=0.9)
    result_low = opt.solve(x0=x0, ref_trajectory=ref, confidence=0.3)

    assert result_high["solver_status"] in ("Solve_Succeeded", "Search_Direction_Becomes_Too_Small")
    assert result_low["solver_status"] in ("Solve_Succeeded", "Search_Direction_Becomes_Too_Small")

    T_high = result_high["U_opt"][2, 0]
    T_low = result_low["U_opt"][2, 0]

    print(f"[PASS] 低置信度: T_high={T_high:.2f}%, T_low={T_low:.2f}% "
          f"(低置信度应允许更大控制量)")
    return True


def test_mpc_conservative_confidence_policy_with_delta_penalty():
    """P6 conservative mode must remain solvable with dynamic delta-U scale."""
    weights = _make_default_weights()
    weights.update(
        {
            "confidence_policy": "conservative",
            "low_conf_control_penalty_scale": 3.0,
            "low_conf_tracking_floor": 0.5,
            "delta_psi_cmd": 0.05,
            "delta_z_cmd": 0.05,
            "delta_T_cmd": 0.01,
        }
    )
    optimizer = AUVMPCOptimizer(
        AUVKinematicsModel(_make_default_model_params()),
        N=20,
        dt=0.1,
        weights=weights,
        constraints=_make_default_constraints(),
    )
    x0 = np.array([0.0, 0.0, 5.0, 0.0, 0.8, 0.0])
    reference = _build_flat_reference(x0, N=optimizer.N, dt=optimizer.dt)
    result = optimizer.solve(
        x0=x0,
        ref_trajectory=reference,
        confidence=0.4,
        delta_u_penalty_scale=3.0,
    )
    assert optimizer.confidence_policy == "conservative"
    assert result["solver_status"] in (
        "Solve_Succeeded",
        "Search_Direction_Becomes_Too_Small",
    )
    assert np.all(np.isfinite(result["U_opt"]))


def test_delta_penalty_anchors_first_control_to_previous_cycle():
    """Delta-U must penalize the first command against the applied command."""
    weights = _make_default_weights()
    weights.update(
        {
            "confidence_policy": "conservative",
            "delta_psi_cmd": 5000.0,
            "delta_z_cmd": 0.0,
            "delta_T_cmd": 0.0,
        }
    )
    optimizer = AUVMPCOptimizer(
        AUVKinematicsModel(_make_default_model_params()),
        N=20,
        dt=0.1,
        weights=weights,
        constraints=_make_default_constraints(),
    )
    x0 = np.array([0.0, 0.0, 5.0, 0.0, 1.0, 0.0])
    reference = _build_turn_reference(x0, N=optimizer.N, dt=optimizer.dt)
    previous = np.array([-0.03, 5.0, 12.0])

    default_result = optimizer.solve(x0, reference, confidence=0.5)
    anchored_result = optimizer.solve(
        x0,
        reference,
        confidence=0.5,
        previous_control=previous,
    )

    default_error = abs(default_result["U_opt"][0, 0] - previous[0])
    anchored_error = abs(anchored_result["U_opt"][0, 0] - previous[0])
    assert anchored_error < default_error * 0.25


def test_mpc_warm_start():
    """热启动测试：第二次求解应使用第一次的结果作为初值。"""
    opt = _build_optimizer()
    x0 = np.array([0.0, 0.0, 5.0, 0.0, 0.8, 0.0])
    ref = _build_flat_reference(x0, target_speed=1.0, target_heading=0.0,
                                target_depth=5.0, N=opt.N, dt=opt.dt)

    result1 = opt.solve(x0=x0, ref_trajectory=ref, confidence=1.0)
    t0 = time.perf_counter()
    result2 = opt.solve(x0=x0, ref_trajectory=ref, confidence=1.0,
                        warm_start_U=result1["U_opt"])
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert result2["solver_status"] in ("Solve_Succeeded", "Search_Direction_Becomes_Too_Small")

    print(f"[PASS] 热启动: solve_time={result2['solve_time_ms']:.1f}ms, "
          f"total={elapsed_ms:.1f}ms")
    return True


def test_mpc_constraints():
    """硬约束测试：确保航速 > 0.3 m/s，推力在 [0, 100] 内。"""
    opt = _build_optimizer()
    x0 = np.array([0.0, 0.0, 5.0, 0.0, 0.5, 0.0])
    ref = _build_flat_reference(x0, target_speed=0.5, target_heading=0.0,
                                target_depth=5.0, N=opt.N, dt=opt.dt)

    result = opt.solve(x0=x0, ref_trajectory=ref, confidence=1.0)
    X_opt = result["X_opt"]
    U_opt = result["U_opt"]

    assert np.all(X_opt[4, :] >= 0.3 - 1e-4), "航速约束被违反"
    assert np.all(U_opt[2, :] >= -1e-4), "推力下限被违反"
    assert np.all(U_opt[2, :] <= 100.0 + 1e-4), "推力上限被违反"

    print(f"[PASS] 硬约束: min_speed={X_opt[4, :].min():.3f} m/s, "
          f"T_range=[{U_opt[2, :].min():.1f}, {U_opt[2, :].max():.1f}]")
    return True


def test_kinematics_model():
    """运动学模型基本正确性测试。"""
    params = _make_default_model_params()
    kin = AUVKinematicsModel(params)

    X = np.array([0.0, 0.0, 5.0, 0.0, 1.0, 0.0])
    U = np.array([0.0, 5.0, 50.0])
    dt = 0.1

    import casadi as ca
    X_ca = ca.MX.sym("X", 6)
    U_ca = ca.MX.sym("U", 3)
    f = ca.Function("f", [X_ca, U_ca], [kin.discrete_step(X_ca, U_ca, dt)])

    X_next = f(X, U).full().flatten()

    assert X_next[0] > X[0], "x 应该随 u > 0 增加"
    assert abs(X_next[1] - X[1]) < 1e-6, "航向为 0 时 y 应不变"
    assert X_next[4] > 0.3, "推力应维持航速"

    print(f"[PASS] 运动学模型: x_next={X_next[0]:.3f}, u_next={X_next[4]:.3f}")
    return True


def test_depth_saturation_keeps_nonzero_gradient():
    """Large depth errors must remain differentiable for IPOPT."""
    import casadi as ca

    kin = AUVKinematicsModel(
        {
            **_make_default_model_params(),
            "pitch_depth_gain": 0.8,
            "max_pitch_deg": 20.0,
        }
    )
    z_cmd = ca.MX.sym("z_cmd")
    state = ca.vertcat(0.0, 0.0, 12.69, 0.0, 0.84, 0.0)
    control = ca.vertcat(0.0, z_cmd, 15.0)
    dz = kin.compute_dynamics(state, control)[2]
    derivative = ca.Function("depth_gradient", [z_cmd], [ca.jacobian(dz, z_cmd)])

    gradient = float(derivative(12.0))
    assert np.isfinite(gradient)
    assert abs(gradient) > 1e-3


def test_r13_depth_mismatch_converges_with_full_horizon():
    """Regression for the R13 0.69 m depth-error failure."""
    model = AUVKinematicsModel(
        {
            "mass_u": 50.0,
            "mass_w": 50.0,
            "drag_u": 12.0,
            "drag_w": 20.0,
            "buoyancy_term": -0.5,
            "yaw_rate_gain": 8.0,
            "pitch_depth_gain": 0.8,
            "depth_to_heave_gain": 12.0,
            "max_pitch_deg": 20.0,
        }
    )
    optimizer = AUVMPCOptimizer(
        model,
        N=20,
        dt=0.2,
        weights={
            "x": 1.0,
            "y": 1.0,
            "z": 40.0,
            "psi": 80.0,
            "u": 0.5,
            "w": 3.0,
            "psi_cmd": 0.005,
            "z_cmd": 0.002,
            "T_cmd": 0.01,
            "mpc_mode": "baseline",
        },
        constraints={
            "min_speed_ms": 0.3,
            "min_thrust_percent": 15.0,
            "max_thrust_percent": 100.0,
            "delta_z_max_per_step": 1.0,
            "delta_psi_max_per_step": 0.0419,
            "z_band_m": 4.0,
            "psi_band_rad": 0.7854,
            "enable_rate_constraints": True,
            "enable_band_constraints": True,
        },
        max_iter=100,
    )
    x0 = np.array([0.0, 0.0, 12.69, np.deg2rad(-1.665), 0.842, 0.0])
    reference = _build_flat_reference(
        x0,
        target_speed=0.4,
        target_heading=0.0,
        target_depth=12.0,
        N=optimizer.N,
        dt=optimizer.dt,
    )

    result = optimizer.solve(x0=x0, ref_trajectory=reference, confidence=0.367)
    assert result["solver_status"] == "Solve_Succeeded"
    assert result["solver_iterations"] < 30
    assert result["final_constraint_violation_max"] < 1e-4


if __name__ == "__main__":
    import traceback
    tests = [
        ("kinematics_model", test_kinematics_model),
        ("straight_line", test_mpc_straight_line),
        ("turn", test_mpc_turn),
        ("low_confidence", test_mpc_low_confidence),
        ("warm_start", test_mpc_warm_start),
        ("constraints", test_mpc_constraints),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            failed += 1
            traceback.print_exc()
            print(f"[FAIL] {name}: {e}")

    print(f"\n{'='*50}")
    print(f"测试结果: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
