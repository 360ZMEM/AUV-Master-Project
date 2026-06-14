"""
HoloOcean 物理仿真 + Zenoh 桥接器 - 仿真侧的完整传感和通信系统。

该模块是仿真侧的核心集成层，负责：
  1. 驱动 HoloOcean 物理仿真（推进参加环境、传感器数据采集）
  2. 应用感知算法（Biot-Savart 磁场、声纳电缆检测、噪声注入）
  3. 生成数字孪生可视化（海床、电缆标记、历史轨迹）
  4. 通过 Zenoh 发布遥测数据到决策侧

通信模型（方向）：
  ╔═════════════════════════════════════════════════════════╗
  ║          仿真侧（HoloOcean）                            ║
  ║   ┌──────────────────────────────────────────────────┐ ║
  ║   │ HoloOceanPhysicsZenohBridge（本模块）            │ ║
  ║   │  │                                               │ ║
  ║   │  ├─ 接收下行：get_latest_cmd() from Zenoh      │ ║
  ║   │  │                                               │ ║
  ║   │  ├─ 驱动物理：wrapper.step(cmd)                │ ║
  ║   │  │                                               │ ║
  ║   │  ├─ 感知处理：_build_sensor_packet()           │ ║
  ║   │  │  ├─ 坐标转换（UE4 → NED）                   │ ║
  ║   │  │  ├─ 传感器提取（IMU、DVL、深度等）         │ ║
  ║   │  │  ├─ 模型应用（Biot-Savart、声纳）          │ ║
  ║   │  │  └─ 噪声注入                                │ ║
  ║   │  │                                               │ ║
  ║   │  └─ 发布上行：publish() to Zenoh               │ ║
  ║   │     ├─ rt/auv/sensors/ground_truth              │ ║
  ║   │     ├─ rt/auv/sensors/imu                       │ ║
  ║   │     ├─ rt/auv/sensors/dvl                       │ ║
  ║   │     ├─ rt/auv/sensors/depth                     │ ║
  ║   │     ├─ rt/auv/sensors/magnetic                  │ ║
  ║   │     ├─ rt/auv/perception/sonar                  │ ║
  ║   │     └─ (可视化 topics)                          │ ║
  ║   │                                                  │ ║
  ║   └──────────────────────────────────────────────────┘ ║
  ╚═════════════════════════════════════════════════════════╝
             ↕ Zenoh PubSub
  ╔═════════════════════════════════════════════════════════╗
  ║          决策侧（ROS2 Humble）                          ║
  ║ ... auv_bridge -> auv_localization -> auv_controller ..║
  ╚═════════════════════════════════════════════════════════╝
"""

import math
import time
import numpy as np
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder in [PROJECT_ROOT, PROJECT_ROOT / "common"]:
    folder = str(folder)
    if folder not in sys.path:
        sys.path.insert(0, folder)

from common.protocol import (
    KEY_ACCEL_NED,
    KEY_B_NED,
    KEY_B_NORM,
    KEY_CABLE_CLOSEST_NED,
    KEY_CABLE_DISTANCE_M,
    KEY_DEPTH_M,
    KEY_GYRO_NED,
    KEY_POSITION_NED,
    KEY_RPY_NED,
    KEY_SONAR_BINS,
    KEY_VEL_NED,
    enrich_meta,
    validate_sensor_payload,
    Z_PATH_CABLE_MARKER,
    Z_PATH_HISTORY_TRAIL,
    Z_PATH_SEABED_CLOUD,
    Z_PATH_TRUTH_POSE,
    Z_PATH_VIEW_RANGE,
)

from frame_transform import body_vector_ue_to_ned, pose_matrix_ue_to_ned
from perception_engine import (
    CablePath,
    compute_biot_savart_hvdc,
    inject_gaussian_noise,
    inject_sonar_cable_peak,
)
from synthetic_sensors import VirtualEnvironment
from sim_wrapper import create_sim_wrapper, build_scenario, extract_body_velocity, extract_depth, extract_gyro, get_agent_state
from zenoh_bridge import ZenohBridge


class HoloOceanPhysicsZenohBridge:
    """
    HoloOcean 物理仿真 + Zenoh 桥接器 - 仿真侧完整系统的编排者。

    职责划分：
      1. HoloOcean wrapper：管理虚拟 AUV 的物理步进
      2. Perception engine：计算磁场、声纳等高级传感器读数
      3. Zenoh bridge：发布遥测数据到决策侧
      4. Virtual environment：生成数字孪生的可视化数据

    核心流程（每帧 dt 秒）：
      1. zbridge.get_latest_cmd()：从 Zenoh 取下行命令（非阻塞）
      2. command_guard.sanitize()：应用安全护栏
      3. wrapper.step(cmd)：推进 HoloOcean 仿真
      4. _build_sensor_packet()：从仿真状态提取并处理传感器数据
         ├─ 坐标系转换（UE4 → NED）
         ├─ 传感器数据提取
         ├─ 应用物理模型（磁场计算、声纳）
         ├─ 注入测量噪声
         └─ 打包成标准化数据包
      5. zbridge.publish()：发布各传感器数据包到 Zenoh
      6. 速率控制：维持目标采样率（rate_hz）
    """

    def __init__(self, config, command_guard):
        """
        初始化桥接器。

        参数：
          config: dict
              全局配置，包含以下键：
                - simulation: 仿真参数
                - bridge: 通信配置
                - cable_path: 电缆路径定义（用于磁场/距离计算）
                - digital_twin: 可视化配置
                - perception: 感知算法参数（噪声、模型常数等）
                - zenoh: Zenoh 会话配置
          command_guard: CommandGuard
              控制命令的安全检查和限幅
        """
        self.config = config
        self.command_guard = command_guard
        self.agent_name = config["simulation"]["agent_name"]

        # ────────────────────────────────────────
        # 仿真主循环参数
        # ────────────────────────────────────────
        self.rate_hz = float(config["bridge"]["rate_hz"])
        self.dt = 1.0 / max(1e-6, self.rate_hz)  # 单帧时间（秒）

        # ────────────────────────────────────────
        # 电缆和环境模拟
        # ────────────────────────────────────────
        # 电缆路径：用于磁场计算和距离测量
        cable_points = config["cable_path"]["points_ned"]
        self.cable = CablePath(cable_points)

        # 数字孪生：生成海床、可视化标记等
        digital_twin_cfg = config.get("digital_twin", {})
        self.virtual_env = VirtualEnvironment(digital_twin_cfg)
        self.terrain_publish_hz = float(digital_twin_cfg.get("terrain_publish_hz", 3.0))
        self._last_terrain_publish_ts = -1e9  # 上一次发布地形的时间

        # ────────────────────────────────────────
        # DVL 降采样机制（还原声学真实性）
        # ────────────────────────────────────────
        # 真实声学 DVL 物理极限频率 5-10 Hz（水深 15m 时声波往返约 20ms）
        self.dvl_update_rate_hz = float(config.get("perception", {}).get("dvl_update_rate_hz", 5.0))
        self.dvl_update_interval = 1.0 / max(self.dvl_update_rate_hz, 1e-6)
        self._last_dvl_publish_sim_time = -1e9  # 上一次发布 DVL 的仿真时间

        # ────────────────────────────────────────
        # 运行时状态
        # ────────────────────────────────────────
        self.wrapper = None  # HoloOcean 环境包装器
        self.zbridge = None  # Zenoh 桥接层
        self.last_cmd = np.array(config["bridge"].get("default_command", [0, 0, 0, 0, 0]), dtype=float)

    def open(self):
        """
        启动仿真和 Zenoh 通信。

        返回值：
            self，支持链式调用
        """
        scenario = build_scenario(self.config)
        sim_cfg = self.config["simulation"]
        self.wrapper = create_sim_wrapper(
            self.config,
            scenario_cfg=scenario,
            agent_name=self.agent_name,
            show_viewport=bool(sim_cfg.get("show_viewport", False)),
            verbose=bool(sim_cfg.get("verbose", False)),
        ).open()
        self.zbridge = ZenohBridge(self.config["zenoh"]).open()
        return self

    def close(self):
        """关闭仿真和 Zenoh 连接，释放资源。"""
        if self.zbridge is not None:
            self.zbridge.close()
            self.zbridge = None
        if self.wrapper is not None:
            self.wrapper.close()
            self.wrapper = None

    def _build_sensor_packet(self, raw_state, step, sim_time):
        """
        从仿真状态构造传感器数据包。

        处理步骤：
          1️⃣ 坐标变换：从 HoloOcean（UE4）转换到 NED
          2️⃣ 基础提取：位姿、加速度、角速度、速度、深度
          3️⃣ 高级处理：电缆距离、Biot-Savart 磁场、声纳
          4️⃣ 噪声注入：模拟测量噪声
          5️⃣ 打包：组织成标准数据包
          6️⃣ 验证：检查数据包合法性

        参数：
          raw_state: dict
              HoloOcean 返回的原始仿真状态
          step: int
              步数计数器
          sim_time: float
              仿真时间（秒，= step * dt）

        返回值：
          dict：多个传感器数据包，键为通道名，值为数据字典
              示例：
              {
                  "ground_truth": {meta..., position, rpy, cable_info},
                  "imu": {meta..., accel, gyro},
                  "dvl": {meta..., velocity},
                  "depth": {meta..., depth},
                  "magnetic": {meta..., B_ned, B_norm},
                  "sonar": {meta..., sonar_bins},
                  "cable_marker": {...visual...},
                  "truth_pose": {...visual...},
                  "history_trail": {...visual...},
                  "view_range": {...visual...}
              }
        """
        # ────────────────────────────────────────
        # 步骤 1️⃣：坐标变换和位姿解包
        # ────────────────────────────────────────
        state = get_agent_state(raw_state, self.agent_name)
        pose = state["PoseSensor"]  # 4x4 变换矩阵
        tf = pose_matrix_ue_to_ned(pose)  # 转换到 NED

        # ────────────────────────────────────────
        # 步骤 2️⃣：基础传感器提取
        # ────────────────────────────────────────
        imu_sensor = np.asarray(state.get("IMUSensor", np.zeros(6)), dtype=float).reshape(-1)
        gyro_ue = extract_gyro(state.get("IMUSensor", np.zeros(3)))
        dvl_ue = extract_body_velocity(state.get("DVLSensor", np.zeros(3)))
        depth_raw = extract_depth(state.get("DepthSensor", np.array([-pose[2, 3]])), pose[2, 3])
        dvl_frame = str(state.get("DVLFrame", "body")).strip().lower()

        # 坐标转换：身体轴向量 UE4 → NED
        gyro_ned = body_vector_ue_to_ned(gyro_ue)
        dvl_ned = dvl_ue.astype(float) if dvl_frame == "world" else body_vector_ue_to_ned(dvl_ue)

        # 加速度：IMU 的前 3 个分量
        accel_ue = imu_sensor[:3] if imu_sensor.size >= 3 else np.zeros(3, dtype=float)
        accel_ned = body_vector_ue_to_ned(accel_ue)

        # ────────────────────────────────────────
        # 步骤 3️⃣：高级物理计算
        # ────────────────────────────────────────
        pos_ned = tf["position_ned"]

        # 电缆几何：最近点和距离
        cable_p, cable_dist = self.cable.closest_point_and_distance(pos_ned)

        # Biot-Savart 磁场：HVDC 电缆的磁场贡献
        p_cfg = self.config["perception"]
        b_vec = compute_biot_savart_hvdc(
            auv_pos_ned=pos_ned,
            cable=self.cable,
            current_amp=float(p_cfg["hvdc_current_amp"]),
        )

        # ────────────────────────────────────────
        # 步骤 4️⃣：噪声注入（含洋流自适应 DVL 噪声）
        # ────────────────────────────────────────
        b_noisy = inject_gaussian_noise(b_vec, p_cfg["noise"]["magnetic_sigma"])

        # 获取洋流速度用于自适应噪声
        current_vel_ned = None
        if hasattr(self.wrapper, 'ocean_current') and self.wrapper.ocean_current is not None:
            current_vel_ned = self.wrapper.ocean_current.get_current_world(sim_time)

        # 自适应 DVL 噪声: 洋流越大，方差越大 (模拟气泡干扰)
        base_dvl_sigma = p_cfg["noise"]["dvl_sigma"]
        if current_vel_ned is not None:
            current_magnitude = np.linalg.norm(current_vel_ned)
            adaptive_dvl_sigma = base_dvl_sigma + 0.01 * current_magnitude
        else:
            adaptive_dvl_sigma = base_dvl_sigma

        # DVL 降采样：只有当仿真时间跨过发布间隔边界时才计算噪声并标记为可发布
        should_publish_dvl = (sim_time - self._last_dvl_publish_sim_time) >= self.dvl_update_interval
        if should_publish_dvl:
            dvl_noisy = inject_gaussian_noise(dvl_ned, adaptive_dvl_sigma)
            self._last_dvl_publish_sim_time = sim_time
        else:
            dvl_noisy = None  # 不发布 DVL 数据

        # 深度处理和噪声
        depth_ned = float(-depth_raw if depth_raw < 0.0 else depth_raw)
        depth_noisy = float(inject_gaussian_noise(np.array([depth_ned]), p_cfg["noise"]["depth_sigma"])[0])

        # 声纳：电缆检测
        sonar_cfg = p_cfg["sonar"]
        sonar = inject_sonar_cable_peak(
            n_bins=int(sonar_cfg["n_bins"]),
            max_range_m=float(sonar_cfg["max_range_m"]),
            cable_distance_m=float(cable_dist),
            base_noise_sigma=float(sonar_cfg["base_noise_sigma"]),
            peak_gain=float(sonar_cfg["peak_gain"]),
            peak_width_bins=float(sonar_cfg["peak_width_bins"]),
        )

        # ────────────────────────────────────────
        # 步骤 5️⃣：打包所有传感器数据
        # ────────────────────────────────────────
        # 元数据：步号、仿真时间（所有时间戳严格使用 sim_time，杜绝墙上时钟滑移）
        base = enrich_meta({}, step=int(step), sim_time=float(sim_time), ts=float(sim_time))

        # 计算对水速度 (用于 spare_params 透传)
        vel_water_ned = None
        current_magnitude = 0.0
        if current_vel_ned is not None and dvl_noisy is not None:
            vel_water_ned = (dvl_noisy - current_vel_ned).tolist()
            current_magnitude = float(np.linalg.norm(current_vel_ned))

        packets = {
            # 地面真值：位置、姿态和电缆信息
            "ground_truth": {
                **base,
                KEY_POSITION_NED: pos_ned.tolist(),
                KEY_RPY_NED: tf["rpy_ned"].tolist(),
                KEY_CABLE_CLOSEST_NED: cable_p.tolist(),
                KEY_CABLE_DISTANCE_M: float(cable_dist),
            },
            # IMU：加速度和角速度
            "imu": {
                **base,
                KEY_ACCEL_NED: accel_ned.tolist(),
                KEY_GYRO_NED: gyro_ned.tolist(),
            },
        }

        # DVL：对地速度 (Bottom Track) — 降采样至 5Hz 以还原声学真实性
        if dvl_noisy is not None:
            packets["dvl"] = {
                **base,
                KEY_VEL_NED: dvl_noisy.tolist(),
                "measurement_frame": dvl_frame,
                "vel_water_ned": vel_water_ned,
                "current_magnitude": current_magnitude,
            }

        # 深度传感器
        packets["depth"] = {
            **base,
            KEY_DEPTH_M: depth_noisy,
        }

        # 离底高度（基于动态地形模型）
        terrain_z = self.virtual_env.terrain_height_at(pos_ned[0], pos_ned[1])
        altitude_m = max(0.0, float(terrain_z) - float(pos_ned[2]))
        packets["altitude"] = {
            **base,
            "altitude_m": altitude_m,
        }

        # 前视声呐仿真：查询AUV前方地形斜率
        heading_rad = tf["rpy_ned"][2]
        lookahead_m = 5.0
        x_fwd = float(pos_ned[0]) + lookahead_m * math.cos(heading_rad)
        y_fwd = float(pos_ned[1]) + lookahead_m * math.sin(heading_rad)
        terrain_z_fwd = self.virtual_env.terrain_height_at(x_fwd, y_fwd)
        forward_terrain_slope = (float(terrain_z_fwd) - float(terrain_z)) / lookahead_m
        packets["forward_sonar"] = {
            **base,
            "slope": forward_terrain_slope,
            "lookahead_m": lookahead_m,
        }

        # 磁力计：HVDC 电缆产生的磁场
        packets["magnetic"] = {
            **base,
            KEY_B_NED: b_noisy.tolist(),
            KEY_B_NORM: float(np.linalg.norm(b_noisy)),
        }

        # 声纳：电缆检测
        packets["sonar"] = {
            **base,
            KEY_SONAR_BINS: sonar.tolist(),
        }

        # ────────────────────────────────────────
        # 步骤 6️⃣：可视化数据（Foxglove）
        # ────────────────────────────────────────
        # 决定是否发布地形数据（降采样以减少流量）
        should_publish_terrain = (sim_time - self._last_terrain_publish_ts) >= max(1.0 / max(self.terrain_publish_hz, 1e-6), self.dt)

        visual_payloads = self.virtual_env.build_visual_payloads(
            position_ned=pos_ned,
            rpy_ned=tf["rpy_ned"],
            publish_terrain=should_publish_terrain,
        )

        # 记录地形发布时间
        if Z_PATH_SEABED_CLOUD in visual_payloads:
            self._last_terrain_publish_ts = sim_time

        # 组织可视化包
        if Z_PATH_SEABED_CLOUD in visual_payloads:
            packets["seabed_cloud"] = {**base, **visual_payloads[Z_PATH_SEABED_CLOUD]}
        packets.update({
            "cable_marker": {**base, **visual_payloads[Z_PATH_CABLE_MARKER]},
            "truth_pose": {**base, **visual_payloads[Z_PATH_TRUTH_POSE]},
            "history_trail": {**base, **visual_payloads[Z_PATH_HISTORY_TRAIL]},
            "view_range": {**base, **visual_payloads[Z_PATH_VIEW_RANGE]},
        })

        return packets

    def run_forever(self):
        """
        启动主仿真循环 - 持续驱动物理和通信。

        核心循环流程：
          1. 等待并接收下行命令（非阻塞）
          2. 应用安全护栏
          3. 推进仿真一步
          4. 构造传感器数据包（含坐标变换、感知处理）
          5. 验证和发布上行数据包到 Zenoh
          6. 速率控制：维持 rate_hz

        监视输出：
          每帧打印深度和磁场强度，用于实时监控仿真状态
        """
        state = self.wrapper.reset_and_tick()
        step = 0
        start_wall = time.time()

        while True:
            loop_start = time.time()
            sim_time = step * self.dt

            # ────────────────────────────────────────
            # 接收下行命令
            # ────────────────────────────────────────
            cmd_msg, cmd_ts = self.zbridge.get_latest_cmd()
            cmd = self.command_guard.sanitize(cmd_msg, self.last_cmd, cmd_ts)
            self.last_cmd = cmd

            # ────────────────────────────────────────
            # 推进仿真并构造传感器包
            # ────────────────────────────────────────
            state = self.wrapper.step(cmd)
            packets = self._build_sensor_packet(state, step, sim_time)

            # ────────────────────────────────────────
            # 验证和发布所有包
            # ────────────────────────────────────────
            for ch_name, payload in packets.items():
                topic = self.zbridge.get_uplink_topic(ch_name)
                ok, errors = validate_sensor_payload(topic, payload)
                if not ok:
                    print(f"[bridge][warn] invalid payload for {ch_name} ({topic}): {errors}")
                    continue
                self.zbridge.publish(ch_name, payload)

            # ────────────────────────────────────────
            # 日志输出（监视）
            # ────────────────────────────────────────
            print(
                f"step={step:06d} depth={packets['depth'][KEY_DEPTH_M]:.3f}m "
                f"|B|={packets['magnetic'][KEY_B_NORM]:.6e}T"
            )

            # ────────────────────────────────────────
            # 速率控制
            # ────────────────────────────────────────
            step += 1
            elapsed = time.time() - loop_start
            sleep_t = self.dt - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

            # ────────────────────────────────────────
            # 终止条件
            # ────────────────────────────────────────
            if self.config["bridge"].get("max_steps", 0) > 0 and step >= int(self.config["bridge"]["max_steps"]):
                break

        print(f"bridge done, wall_time={time.time() - start_wall:.2f}s")
