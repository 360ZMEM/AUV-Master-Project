#!/usr/bin/env python3
"""
MCAP -> HoloOcean 位姿驱动回放器。

功能：
  - 从 MCAP 读取位姿/速度序列（默认 `/auv/state/filtered`）。
  - 在 HoloOcean 中通过 `set_physics_state()` 逐帧写入状态。
  - 采集 agent 或 viewport 画面并导出 GIF/MP4。

典型用法：
  python tools/replay_mcap_holoocean.py \
      /path/to/rosbag_0.mcap \
      --capture-mode agent \
      --output log/replay_agent_from_mcap.mp4 \
      --format mp4
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIM_INTERFACES = PROJECT_ROOT / "sim_holoocean" / "interfaces"
if str(SIM_INTERFACES) not in sys.path:
    sys.path.insert(0, str(SIM_INTERFACES))

from mcap_ros2.reader import read_ros2_messages

from sim_wrapper import build_scenario, get_agent_state


@dataclass
class PoseSample:
    t_ns: int
    position_xyz: np.ndarray
    rpy_deg: np.ndarray
    linear_vel_xyz: np.ndarray
    angular_vel_deg_xyz: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to .mcap file.")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "sim_params.yaml", help="Simulation config YAML.")
    parser.add_argument("--pose-topic", type=str, default="/auv/state/filtered", help="Pose topic (Odometry-like).")
    parser.add_argument("--capture-mode", choices=("agent", "viewport"), default="agent", help="Render camera mode.")
    parser.add_argument("--show-viewport", action="store_true", help="Force viewport display.")
    parser.add_argument("--fps", type=int, default=15, help="Output video fps.")
    parser.add_argument("--format", choices=("gif", "mp4"), default="mp4", help="Output format.")
    parser.add_argument("--output", type=Path, default=None, help="Output video path.")
    parser.add_argument("--capture-width", type=int, default=None, help="Capture width.")
    parser.add_argument("--capture-height", type=int, default=None, help="Capture height.")
    parser.add_argument("--max-samples", type=int, default=None, help="Limit consumed pose samples.")
    parser.add_argument("--sample-step", type=int, default=1, help="Take one sample every N samples.")
    parser.add_argument("--pose-frame", choices=("as-is", "ned-to-ue"), default="as-is", help="Transform MCAP pose frame before replay.")
    parser.add_argument("--verbose", action="store_true", help="Verbose logs.")
    return parser.parse_args()


def resolve_config_path(config_path: Path) -> Path:
    if config_path.is_absolute():
        return config_path
    return (PROJECT_ROOT / config_path).resolve()


def resolve_output_path(output_path: Path | None, output_format: str, capture_mode: str) -> Path:
    if output_path is not None:
        resolved = output_path.expanduser()
        if resolved.suffix.lower() not in {".gif", ".mp4"}:
            resolved = resolved.with_suffix(f".{output_format}")
        return resolved
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "log" / f"holoocean_mcap_replay_{capture_mode}_{ts}.{output_format}"


def quaternion_to_euler_radians(x: float, y: float, z: float, w: float) -> np.ndarray:
    # Intrinsic XYZ (roll, pitch, yaw)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return np.array([roll, pitch, yaw], dtype=float)


def normalize_frame(frame: np.ndarray) -> np.ndarray:
    image = np.asarray(frame)
    if image.ndim == 2:
        image = np.repeat(image[..., None], 3, axis=2)
    if image.ndim == 3 and image.shape[2] >= 4:
        image = image[..., :3]
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(image)


def annotate_frame(frame_bgr: np.ndarray, lines: list[str]) -> np.ndarray:
    if not lines:
        return frame_bgr
    canvas = frame_bgr.copy()
    font_scale = 0.55
    margin_x = 12
    margin_y = 12
    line_gap = 8
    line_height = max(16, int(22 * font_scale))
    widths = []
    heights = []
    for line in lines:
        (w, h), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        widths.append(w)
        heights.append(h)

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
    first = frames_bgr[0]
    height, width = first.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, float(max(1, fps)), (width, height))
    if not writer.isOpened():
        raise SystemExit("Failed to open MP4 writer. Check OpenCV codec support.")
    try:
        for frame in frames_bgr:
            if frame.shape[:2] != (height, width):
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            writer.write(frame)
    finally:
        writer.release()


def build_capture_sensor(capture_mode: str, capture_width: int, capture_height: int, sensor_hz: int) -> dict[str, object]:
    sensor_type = "ViewportCapture" if capture_mode == "viewport" else "RGBCamera"
    socket_name = "Viewport" if capture_mode == "viewport" else "CameraSocket"
    return {
        "sensor_name": "ReplayViewport" if capture_mode == "viewport" else "ReplayCamera",
        "sensor_type": sensor_type,
        "socket": socket_name,
        "Hz": int(sensor_hz),
        "configuration": {
            "CaptureWidth": capture_width,
            "CaptureHeight": capture_height,
        },
    }


def extract_odom_sample(wrapper, pose_topic: str) -> PoseSample | None:
    channel = getattr(wrapper, "channel", None)
    if channel is None:
        return None
    topic = getattr(channel, "topic", None)
    if topic != pose_topic:
        return None

    msg = getattr(wrapper, "ros_msg", None)
    if msg is None:
        return None
    if not hasattr(msg, "pose") or not hasattr(msg.pose, "pose"):
        return None

    t_ns = int(getattr(wrapper, "publish_time_ns", 0) or getattr(wrapper, "log_time_ns", 0))
    position = msg.pose.pose.position
    quat = msg.pose.pose.orientation
    linear = msg.twist.twist.linear if hasattr(msg, "twist") and hasattr(msg.twist, "twist") else None
    angular = msg.twist.twist.angular if hasattr(msg, "twist") and hasattr(msg.twist, "twist") else None

    rpy_rad = quaternion_to_euler_radians(float(quat.x), float(quat.y), float(quat.z), float(quat.w))
    rpy_deg = np.degrees(rpy_rad)

    linear_vel = np.array([
        float(getattr(linear, "x", 0.0)),
        float(getattr(linear, "y", 0.0)),
        float(getattr(linear, "z", 0.0)),
    ], dtype=float)
    angular_vel_deg = np.degrees(np.array([
        float(getattr(angular, "x", 0.0)),
        float(getattr(angular, "y", 0.0)),
        float(getattr(angular, "z", 0.0)),
    ], dtype=float))

    return PoseSample(
        t_ns=t_ns,
        position_xyz=np.array([float(position.x), float(position.y), float(position.z)], dtype=float),
        rpy_deg=rpy_deg,
        linear_vel_xyz=linear_vel,
        angular_vel_deg_xyz=angular_vel_deg,
    )


def transform_pose_frame(sample: PoseSample, mode: str) -> PoseSample:
    if mode == "as-is":
        return sample
    # NED -> UE4 近似映射。
    return PoseSample(
        t_ns=sample.t_ns,
        position_xyz=np.array([sample.position_xyz[0], sample.position_xyz[1], -sample.position_xyz[2]], dtype=float),
        rpy_deg=np.array([sample.rpy_deg[0], -sample.rpy_deg[1], -sample.rpy_deg[2]], dtype=float),
        linear_vel_xyz=np.array([sample.linear_vel_xyz[0], sample.linear_vel_xyz[1], -sample.linear_vel_xyz[2]], dtype=float),
        angular_vel_deg_xyz=np.array([sample.angular_vel_deg_xyz[0], -sample.angular_vel_deg_xyz[1], -sample.angular_vel_deg_xyz[2]], dtype=float),
    )


def load_pose_samples(input_mcap: Path, pose_topic: str, max_samples: int | None, sample_step: int, pose_frame: str) -> list[PoseSample]:
    samples: list[PoseSample] = []
    if sample_step < 1:
        raise SystemExit("--sample-step must be >= 1")

    matched = 0
    for wrapper in read_ros2_messages(str(input_mcap)):
        sample = extract_odom_sample(wrapper, pose_topic)
        if sample is None:
            continue
        if matched % sample_step == 0:
            samples.append(transform_pose_frame(sample, pose_frame))
            if max_samples is not None and len(samples) >= max_samples:
                break
        matched += 1
    return samples


def capture_frame_from_state(state: dict[str, object], sensor_name: str) -> np.ndarray | None:
    frame = state.get(sensor_name)
    if frame is None:
        return None
    return normalize_frame(frame)


def main() -> None:
    args = parse_args()
    input_mcap = args.input.expanduser().resolve()
    if not input_mcap.exists():
        raise SystemExit(f"MCAP not found: {input_mcap}")

    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    samples = load_pose_samples(
        input_mcap=input_mcap,
        pose_topic=str(args.pose_topic),
        max_samples=args.max_samples,
        sample_step=int(args.sample_step),
        pose_frame=str(args.pose_frame),
    )
    if not samples:
        raise SystemExit(f"No usable pose samples found on topic: {args.pose_topic}")

    fps = int(args.fps)
    if fps < 1:
        raise SystemExit("--fps must be >= 1")

    capture_mode = str(args.capture_mode)
    show_viewport = bool(args.show_viewport or capture_mode == "viewport")
    capture_width = int(args.capture_width or (1280 if capture_mode == "viewport" else 960))
    capture_height = int(args.capture_height or (720 if capture_mode == "viewport" else 540))

    scenario = build_scenario(cfg)
    ticks_per_sec = int(cfg["simulation"]["ticks_per_sec"])
    capture_sensor = build_capture_sensor(capture_mode, capture_width, capture_height, ticks_per_sec)
    capture_sensor_name = str(capture_sensor["sensor_name"])
    scenario["agents"][0]["sensors"].append(capture_sensor)

    import holoocean

    agent_name = str(cfg["simulation"]["agent_name"])
    env = holoocean.make(
        scenario_cfg=scenario,
        show_viewport=show_viewport,
        verbose=bool(args.verbose),
        window_res=(capture_height, capture_width) if capture_mode == "viewport" else None,
    )

    output_path = resolve_output_path(args.output, str(args.format), capture_mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("MCAP -> HoloOcean pose replay")
    print(f"mcap={input_mcap}")
    print(f"pose_topic={args.pose_topic}")
    print(f"capture_mode={capture_mode}")
    print(f"pose_frame={args.pose_frame}")
    print(f"samples={len(samples)}")
    print(f"output={output_path}")
    print("=" * 72)

    frames_bgr: list[np.ndarray] = []

    try:
        env.reset()
        state_raw = env.tick()
        _ = get_agent_state(state_raw, agent_name)

        agent = env.agents[agent_name]
        t0_ns = samples[0].t_ns
        for idx, sample in enumerate(samples):
            agent.set_physics_state(
                sample.position_xyz,
                sample.rpy_deg,
                sample.linear_vel_xyz,
                sample.angular_vel_deg_xyz,
            )
            state_raw = env.tick()
            agent_state = get_agent_state(state_raw, agent_name)
            frame = capture_frame_from_state(agent_state, capture_sensor_name)
            if frame is None:
                continue

            elapsed_sec = max(0.0, (sample.t_ns - t0_ns) / 1e9)
            frame = annotate_frame(
                frame,
                [
                    f"frame={idx:04d}  t={elapsed_sec:7.2f}s",
                    f"pos=({sample.position_xyz[0]:7.2f}, {sample.position_xyz[1]:7.2f}, {sample.position_xyz[2]:7.2f})",
                    f"rpy=({sample.rpy_deg[0]:6.1f}, {sample.rpy_deg[1]:6.1f}, {sample.rpy_deg[2]:6.1f})deg",
                ],
            )
            frames_bgr.append(frame)

            if args.verbose and idx % 50 == 0:
                print(
                    f"replay idx={idx:04d} t={elapsed_sec:7.2f}s "
                    f"pos=({sample.position_xyz[0]:.2f},{sample.position_xyz[1]:.2f},{sample.position_xyz[2]:.2f})"
                )
    finally:
        # HoloOceanEnvironment 没有统一 close()，但支持上下文退出。
        if hasattr(env, "__exit__"):
            try:
                env.__exit__(None, None, None)
            except Exception:
                pass

    if not frames_bgr:
        raise SystemExit("No frames were captured while replaying MCAP poses.")

    if args.format == "gif":
        write_gif(frames_bgr, output_path, fps)
    else:
        write_mp4(frames_bgr, output_path, fps)

    print("=" * 72)
    print(f"Saved replay video to: {output_path}")
    print(f"captured_frames={len(frames_bgr)}")
    print("=" * 72)


if __name__ == "__main__":
    main()
