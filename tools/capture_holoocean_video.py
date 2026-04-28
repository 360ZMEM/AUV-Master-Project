#!/usr/bin/env python3
"""
HoloOcean 实时视频捕获工具 - 记录仿真运行为 GIF/MP4。

该工具复用现有的 AUV 导引和 PID 控制栈，启动全新的 HoloOcean 环境，
从中采样相机帧并拼接成回放视频。

两种捕获模式：
  - agent：捕获 AUV 附带的 RGBCamera 视角
  - viewport：捕获活动视口（ViewportCapture），自动启用 HoloOcean 视口

使用示例：
  # 使用默认设置捕获 GIF（存储在 log/ 目录）
  python tools/capture_holoocean_video.py

  # 指定配置文件和输出路径
  python tools/capture_holoocean_video.py --config path/to/sim_params.yaml --output demo.gif

  # 捕获 MP4 格式，调整分辨率和帧率
  python tools/capture_holoocean_video.py --format mp4 --fps 30 --capture-width 1920 --capture-height 1080

  # 捕获视口模式（显示完整 HoloOcean UI）
  python tools/capture_holoocean_video.py --capture-mode viewport --show-viewport

功能：
  - 复用完整控制栈（导引 + PID + 安全护栏）
  - 支持指定最大步数（录制固定长度）
  - 自动处理 RGBA → RGB 转换
  - 支持同时显示视口（用于调试）
"""

from __future__ import annotations

import argparse
import copy
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIM_ROOT = PROJECT_ROOT / "sim_holoocean"
for folder_path in [
    PROJECT_ROOT,
    PROJECT_ROOT / "common",
    PROJECT_ROOT / "algorithm",
    SIM_ROOT / "behavior",
    SIM_ROOT / "interfaces",
    SIM_ROOT / "experiments",
]:
    folder_text = str(folder_path)
    if folder_text not in sys.path:
        sys.path.insert(0, folder_text)

from auv_pid_controller import AUVPIDController
from guidance import clamp_reference, compute_los_target, find_nearest_index
from safety_monitor import apply_safety
from sim_wrapper import (
    build_scenario,
    create_sim_wrapper,
    extract_body_velocity,
    extract_depth,
    extract_gyro,
    get_agent_state,
    rotation_matrix_to_euler,
)
from trajectory_generator import TrajectoryGenerator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "sim_params.yaml", help="Path to the YAML config used for the control loop.")
    parser.add_argument("--output", type=Path, default=None, help="Output video path. Defaults to log/holoocean_capture_<timestamp>.<format>.")
    parser.add_argument("--format", choices=("gif", "mp4"), default="gif", help="Output container format.")
    parser.add_argument("--fps", type=int, default=15, help="Camera sampling rate and output video frame rate.")
    parser.add_argument("--capture-mode", choices=("auto", "agent", "viewport"), default="auto", help="Capture the agent camera or the active viewport.")
    parser.add_argument("--show-viewport", action="store_true", help="Show the HoloOcean viewport while recording.")
    parser.add_argument("--capture-width", type=int, default=None, help="Camera capture width. Defaults to 960 for agent mode or 1280 for viewport mode.")
    parser.add_argument("--capture-height", type=int, default=None, help="Camera capture height. Defaults to 540 for agent mode or 720 for viewport mode.")
    parser.add_argument("--max-steps", type=int, default=None, help="Maximum control-loop steps to execute. Defaults to the value from the YAML config.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose HoloOcean engine logs.")
    return parser.parse_args()


def resolve_config_path(config_path: Path) -> Path:
    if config_path.is_absolute():
        return config_path
    return (PROJECT_ROOT / config_path).resolve()


def resolve_output_path(output_path: Path | None, output_format: str) -> Path:
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return PROJECT_ROOT / "log" / f"holoocean_capture_{timestamp}.{output_format}"

    resolved = output_path.expanduser()
    if resolved.suffix.lower() not in {".gif", ".mp4"}:
        resolved = resolved.with_suffix(f".{output_format}")
    return resolved


def normalize_frame(frame: np.ndarray) -> np.ndarray:
    image = np.asarray(frame)
    if image.ndim == 2:
        image = np.repeat(image[..., None], 3, axis=2)
    if image.ndim == 3 and image.shape[2] >= 4:
        image = image[..., :3]
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(image)


def annotate_frame(frame_bgr: np.ndarray, lines: list[str], font_scale: float = 0.55) -> np.ndarray:
    if not lines:
        return frame_bgr

    canvas = frame_bgr.copy()
    margin_x = 12
    margin_y = 12
    line_gap = 8
    line_height = max(16, int(22 * font_scale))
    widths = []
    heights = []
    for line in lines:
        (text_width, text_height), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        widths.append(text_width)
        heights.append(text_height)

    box_width = max(widths) + margin_x * 2
    box_height = sum(heights) + line_gap * max(0, len(lines) - 1) + margin_y * 2
    cv2.rectangle(canvas, (8, 8), (8 + box_width, 8 + box_height), (0, 0, 0), thickness=-1)

    y = 8 + margin_y + line_height
    for line in lines:
        cv2.putText(canvas, line, (8 + margin_x, y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)
        y += line_height + line_gap
    return canvas


def write_gif(frames_bgr: list[np.ndarray], output_path: Path, fps: int) -> None:
    rgb_frames = [Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) for frame in frames_bgr]
    duration_ms = max(1, int(round(1000.0 / max(1, fps))))
    rgb_frames[0].save(
        output_path,
        save_all=True,
        append_images=rgb_frames[1:],
        duration=duration_ms,
        loop=0,
        disposal=2,
    )


def write_mp4(frames_bgr: list[np.ndarray], output_path: Path, fps: int) -> None:
    first_frame = frames_bgr[0]
    height, width = first_frame.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, float(max(1, fps)), (width, height))
    if not writer.isOpened():
        raise SystemExit("Failed to open MP4 writer. Check whether OpenCV has video codec support in this environment.")

    try:
        for frame in frames_bgr:
            if frame.shape[:2] != (height, width):
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            writer.write(frame)
    finally:
        writer.release()


def build_capture_sensor(capture_mode: str, capture_width: int, capture_height: int, fps: int) -> dict[str, object]:
    sensor_type = "ViewportCapture" if capture_mode == "viewport" else "RGBCamera"
    socket_name = "Viewport" if capture_mode == "viewport" else "CameraSocket"
    return {
        "sensor_name": "ReplayViewport" if capture_mode == "viewport" else "ReplayCamera",
        "sensor_type": sensor_type,
        "socket": socket_name,
        "Hz": fps,
        "configuration": {
            "CaptureWidth": capture_width,
            "CaptureHeight": capture_height,
        },
    }


def capture_frame_from_state(state: dict[str, object], sensor_name: str) -> np.ndarray | None:
    if sensor_name not in state:
        return None
    frame = state[sensor_name]
    if frame is None:
        return None
    return normalize_frame(frame)


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    sim_cfg = dict(cfg["simulation"])
    ctrl_cfg = cfg["control"]
    guide_cfg = cfg["guidance"]
    lim_cfg = cfg["limits"]
    traj_cfg = cfg["trajectory"]

    ticks_per_sec = int(sim_cfg["ticks_per_sec"])
    fps = int(args.fps)
    if fps < 1:
        raise SystemExit("--fps must be >= 1")
    if ticks_per_sec % fps != 0:
        raise SystemExit(f"HoloOcean camera rate must divide ticks_per_sec exactly: ticks_per_sec={ticks_per_sec}, fps={fps}")

    capture_mode = str(args.capture_mode)
    if capture_mode == "auto":
        capture_mode = "viewport" if args.show_viewport else "agent"

    show_viewport = bool(args.show_viewport or capture_mode == "viewport")
    capture_width = int(args.capture_width or (1280 if capture_mode == "viewport" else 960))
    capture_height = int(args.capture_height or (720 if capture_mode == "viewport" else 540))

    scenario = build_scenario(cfg)
    capture_sensor = build_capture_sensor(capture_mode, capture_width, capture_height, fps)
    capture_sensor_name = str(capture_sensor["sensor_name"])
    scenario["agents"][0]["sensors"].append(capture_sensor)

    local_cfg = copy.deepcopy(cfg)
    local_cfg["simulation"]["backend"] = "holoocean"
    local_cfg["simulation"]["show_viewport"] = show_viewport
    if show_viewport:
        local_cfg["simulation"]["frames_per_sec"] = fps

    controller = AUVPIDController(ctrl_cfg, lim_cfg)
    traj_gen = TrajectoryGenerator(traj_cfg)
    ref_bundle = traj_gen.generate()
    radius_check = traj_gen.validate_turn_radius(ref_bundle["turn_radius"])
    points = ref_bundle["points"]
    points_xy = points[:, :2]

    max_steps = int(args.max_steps if args.max_steps is not None else sim_cfg["max_steps"])
    agent_name = str(sim_cfg["agent_name"])
    print_every = int(cfg["debug"]["print_every_n_steps"])

    print("=" * 72)
    print("HoloOcean live capture")
    print(f"config={config_path}")
    print(f"capture_mode={capture_mode}")
    print(f"show_viewport={show_viewport}")
    print(f"capture_resolution={capture_width}x{capture_height}")
    print(f"fps={fps}")
    print(
        f"turn_radius_check: min_actual={radius_check['min_radius_actual']:.3f}, "
        f"required={radius_check['min_radius_required']:.3f}, pass={radius_check['passed']}"
    )
    print("=" * 72)

    history = {
        "t": [],
        "pos": [],
        "ref": [],
        "cmd": [],
        "u": [],
        "target_u": [],
        "saturated_any": [],
        "safety_event_count": 0,
    }

    nearest_idx = 0
    output_path = resolve_output_path(args.output, args.format)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frames_bgr: list[np.ndarray] = []
    sim_wall_start = time.time()

    wrapper = create_sim_wrapper(
        local_cfg,
        scenario_cfg=scenario,
        agent_name=agent_name,
        show_viewport=show_viewport,
        verbose=bool(args.verbose or sim_cfg.get("verbose", False)),
        window_res=(capture_height, capture_width) if capture_mode == "viewport" else None,
    ).open()

    try:
        state_raw = wrapper.reset_and_tick()

        def append_frame(step_index: int, state_dict: dict[str, object], position: np.ndarray, rpy: np.ndarray, body_vel: np.ndarray) -> None:
            frame = capture_frame_from_state(state_dict, capture_sensor_name)
            if frame is None:
                return
            annotated = annotate_frame(
                frame,
                [
                    f"step={step_index:04d}  t={step_index * (1.0 / ticks_per_sec):6.2f}s",
                    f"pos=({position[0]:6.2f}, {position[1]:6.2f}, {position[2]:6.2f})",
                    f"rpy=({np.degrees(rpy[0]):6.1f}, {np.degrees(rpy[1]):6.1f}, {np.degrees(rpy[2]):6.1f})deg",
                    f"u={body_vel[0]:5.2f}m/s",
                ],
            )
            frames_bgr.append(annotated)

        current_state = get_agent_state(state_raw, agent_name)
        pose = current_state["PoseSensor"]
        position = pose[:3, 3].astype(float)
        rpy = rotation_matrix_to_euler(pose[:3, :3])
        body_vel = extract_body_velocity(current_state.get("DVLSensor", np.zeros(3)))
        append_frame(0, current_state, position, rpy, body_vel)

        for step in range(max_steps):
            t_sec = step * float(sim_cfg["dt"])
            depth_from_sensor = extract_depth(current_state.get("DepthSensor", np.array([-position[2]])), position[2])
            gyro = extract_gyro(current_state.get("IMUSensor", np.zeros(3)))

            nearest_idx = find_nearest_index(
                points_xy=points_xy,
                current_xy=position[:2],
                last_index=nearest_idx,
                search_window=int(guide_cfg["nearest_search_window"]),
            )
            los_point, los_idx = compute_los_target(
                points=points,
                nearest_index=nearest_idx,
                lookahead_distance=float(guide_cfg["lookahead_distance"]),
            )
            los_yaw = float(np.arctan2(los_point[1] - position[1], los_point[0] - position[0]))

            nearest_point = points[nearest_idx]
            nearest_ref = clamp_reference(nearest_point, lim_cfg)
            tangential = np.array([np.cos(los_yaw), np.sin(los_yaw)], dtype=float)
            normal_left = np.array([-tangential[1], tangential[0]], dtype=float)
            cross_track = float(np.dot(position[:2] - nearest_point[:2], normal_left))
            yaw_correction = -float(guide_cfg["cross_track_gain"]) * np.arctan2(cross_track, float(guide_cfg["lookahead_distance"]))
            target_yaw = los_yaw + yaw_correction

            target_ref = clamp_reference(los_point, lim_cfg)
            control_state = {
                "roll": rpy[0],
                "pitch": rpy[1],
                "yaw": rpy[2],
                "x": position[0],
                "y": position[1],
                "z": position[2],
                "depth": -position[2],
                "depth_sensor": depth_from_sensor,
                "u": body_vel[0],
                "v": body_vel[1],
                "w": body_vel[2],
                "p": gyro[0],
                "q": gyro[1],
                "r": gyro[2],
            }
            target = {
                "dt": float(sim_cfg["dt"]),
                "target_depth": -target_ref[2],
                "target_yaw": target_yaw,
                "target_u": float(ctrl_cfg["target_u"]),
            }

            command, debug = controller.compute(control_state, target)
            command, safety_events = apply_safety(command, position, lim_cfg)
            state_raw = wrapper.step(command)
            current_state = get_agent_state(state_raw, agent_name)

            pose = current_state["PoseSensor"]
            position = pose[:3, 3].astype(float)
            rpy = rotation_matrix_to_euler(pose[:3, :3])
            body_vel = extract_body_velocity(current_state.get("DVLSensor", np.zeros(3)))

            history["t"].append(t_sec)
            history["pos"].append(position.copy())
            history["ref"].append(nearest_ref.copy())
            history["cmd"].append(command.copy())
            history["u"].append(float(body_vel[0]))
            history["target_u"].append(float(ctrl_cfg["target_u"]))
            history["saturated_any"].append(bool(debug["pitch_saturated"] or debug["yaw_saturated"] or debug["thrust_saturated"]))
            if safety_events:
                history["safety_event_count"] += len(safety_events)

            append_frame(step + 1, current_state, position, rpy, body_vel)

            if step % print_every == 0:
                pos_txt = f"pos=({position[0]:6.2f},{position[1]:6.2f},{position[2]:6.2f})"
                ref_txt = f"ref=({target_ref[0]:6.2f},{target_ref[1]:6.2f},{target_ref[2]:6.2f})"
                rpy_txt = f"rpy=({np.degrees(rpy[0]):6.1f},{np.degrees(rpy[1]):6.1f},{np.degrees(rpy[2]):6.1f})deg"
                cmd_txt = f"cmd=[{command[0]:6.2f},{command[1]:6.2f},{command[2]:6.2f},{command[3]:6.2f},{command[4]:6.2f}]"
                aux_txt = f"u={body_vel[0]:5.2f} gain_scale={debug['gain_scale']:5.2f} yaw_err={np.degrees(debug['yaw_error']):6.2f}deg"
                evt_txt = (" | events=" + ",".join(safety_events)) if safety_events else ""
                print(f"step={step:04d} t={t_sec:6.2f}s {pos_txt} {ref_txt} {rpy_txt} {aux_txt} {cmd_txt}{evt_txt}")

            if los_idx >= len(points) - 1:
                print(f"Reached end of reference path at step={step}, stopping capture.")
                break

    finally:
        wrapper.close()

    if not frames_bgr:
        raise SystemExit("No frames were captured from the HoloOcean environment.")

    if args.format == "gif":
        write_gif(frames_bgr, output_path, fps)
    else:
        write_mp4(frames_bgr, output_path, fps)

    elapsed = time.time() - sim_wall_start
    print("=" * 72)
    print(f"Saved video to: {output_path}")
    print(f"captured_frames={len(frames_bgr)} elapsed_wall_time={elapsed:.2f}s")
    print("=" * 72)


if __name__ == "__main__":
    main()