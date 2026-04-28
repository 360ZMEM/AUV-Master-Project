"""
仿真环境包装器和辅助函数 - 统一接口以支持多个仿真后端。

该模块提供对 HoloOcean 和 PVS（Python Vehicle Simulator）物理仿真引擎的统一接口，
以及从原始仿真状态（位姿、速度、传感器）中提取和处理数据的辅助函数。

核心概念：
  1. 后端多样性：支持 HoloOcean（基于 UE4）和 PVS 两种仿真器
  2. 数据提取：统一接口提取位姿、速度、角速度、深度等关键传感器信息
  3. 坐标变换：包含 UE4 和 NED 坐标系之间的转换逻辑

关键函数：
  - create_sim_wrapper()：工厂函数，根据配置创建合适的仿真包装器
  - build_scenario()：从全局配置构造 HoloOcean 场景定义
  - extract_body_velocity()、extract_gyro()、extract_depth()：传感器数据提取
"""

try:
    import holoocean
except Exception:  # pragma: no cover - optional when running PVS-only flows
    holoocean = None
import numpy as np


class HoloOceanSimWrapper:
    """
    HoloOcean 仿真环境包装器 - 管理虚拟 AUV 的步进和状态读取。

    功能：
      1. 创建和管理 HoloOcean 虚拟环境实例
      2. 物理步进（执行控制命令并更新位姿、传感器）
      3. 环境重置和观察获取
      4. 资源清理

    生命周期：
      with HoloOceanSimWrapper(...).open() as wrapper:
          state = wrapper.reset_and_tick()
          for step in range(100):
              state = wrapper.step(command_vector)
      # 自动调用 close()

    支持的控制命令：
      5 元向量 [right_fin_deg, top_fin_deg, left_fin_deg, bottom_fin_deg, thrust_percent]
      - 舵面：度数，范围 [-MAX_ANGLE, MAX_ANGLE]（取决于 control_scheme）
      - 推力：百分比，范围 [-100, 100]
    """

    def __init__(self, scenario_cfg, agent_name, show_viewport=False, verbose=False, window_res=None):
        """
        初始化 HoloOcean 包装器。

        参数：
          scenario_cfg: dict
              HoloOcean 场景配置（由 build_scenario() 返回）
          agent_name: str
              在场景中控制的 AUV 代理名称（如 "auv_agent"）
          show_viewport: bool
              是否在 HoloOcean 窗口中显示 3D 渲染（默认否，运行时不显示 UI）
          verbose: bool
              是否启用详细日志输出
          window_res: tuple or None
              窗口分辨率 (width, height)，None 使用默认值
        """
        self.scenario_cfg = scenario_cfg
        self.agent_name = agent_name
        self.show_viewport = bool(show_viewport)
        self.verbose = bool(verbose)
        self.window_res = window_res
        self.env = None  # HoloOcean 环境实例

    def open(self):
        """
        启动 HoloOcean 虚拟环境。

        返回值：
            self，支持链式调用和 with 语句

        异常：
            RuntimeError：holoocean 模块未安装时抛出
        """
        if holoocean is None:
            raise RuntimeError("holoocean package is required for the HoloOcean backend")
        self.env = holoocean.make(
            scenario_cfg=self.scenario_cfg,
            show_viewport=self.show_viewport,
            verbose=self.verbose,
            window_res=self.window_res,
        )
        return self

    def __enter__(self):
        """支持 with 语句进入。"""
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        """支持 with 语句退出（自动清理资源）。"""
        self.close()
        return False

    def reset_and_tick(self):
        """
        重置仿真环境并执行首次时间步。

        返回值：
            dict：仿真状态（包含所有代理的传感器数据和位姿）
        """
        self.env.reset()
        return self.env.tick()

    def step(self, command5):
        """
        执行一个仿真时间步。

        参数：
            command5: array-like，形状 (5,)
                控制命令向量 [right_fin_deg, top_fin_deg, left_fin_deg, bottom_fin_deg, thrust_percent]

        返回值：
            dict：新的仿真状态

        异常：
            ValueError：命令长度不为 5 时抛出
        """
        cmd = np.asarray(command5, dtype=float).reshape(-1)
        if cmd.size != 5:
            raise ValueError("command must be length 5: [right,top,left,bottom,thrust]")
        self.env.act(self.agent_name, cmd)
        return self.env.tick()

    def close(self):
        """清理 HoloOcean 环境资源（关闭窗口、释放内存）。"""
        if self.env is not None:
            if hasattr(self.env, "close"):
                try:
                    self.env.close()
                except Exception:
                    pass
            elif hasattr(self.env, "__exit__"):
                self.env.__exit__(None, None, None)
            self.env = None


# ============================================================================
# 场景和状态构造函数
# ============================================================================

def build_scenario(cfg):
    """
    从全局配置字典构造 HoloOcean 场景定义。

    该函数从多个配置源（simulation、agent、limits、stage）提取相关信息，
    并组织成 HoloOcean.make() 期望的格式。

    参数：
        cfg: dict
            包含以下键的全局配置：
              - simulation: 包括 agent_name, world, package_name, ticks_per_sec, frames_per_sec
              - agent: 包括 type, control_scheme, sensors, location, rotation
              - limits: 包括 env_min, env_max（仿真环境边界）
              - stage: 包括 name（场景名）

    返回值：
        dict：HoloOcean 场景配置，格式：
          {
              "name": "scenario_name",
              "world": "world_asset_path",
              "package_name": "holoocean_package",
              "main_agent": "agent_name",
              "ticks_per_sec": 100,
              "frames_per_sec": 60,
              "env_min": [x_min, y_min, z_min],
              "env_max": [x_max, y_max, z_max],
              "agents": [
                  {
                      "agent_name": "...",
                      "agent_type": "auv",
                      "control_scheme": "arcadestyle",
                      "sensors": [...],
                      "location": [...],
                      "rotation": [...]
                  }
              ]
          }
    """
    sim = cfg["simulation"]
    agent_cfg = cfg["agent"]
    limits = cfg["limits"]
    return {
        "name": cfg["stage"]["name"],
        "world": sim["world"],
        "package_name": sim["package_name"],
        "main_agent": sim["agent_name"],
        "ticks_per_sec": sim["ticks_per_sec"],
        "frames_per_sec": sim["frames_per_sec"],
        "env_min": limits["env_min"],
        "env_max": limits["env_max"],
        "agents": [
            {
                "agent_name": sim["agent_name"],
                "agent_type": agent_cfg["type"],
                "control_scheme": agent_cfg["control_scheme"],
                "sensors": agent_cfg["sensors"],
                "location": agent_cfg["location"],
                "rotation": agent_cfg["rotation"],
            }
        ],
    }


def get_agent_state(state, agent_name):
    """
    从仿真状态字典中提取特定代理的状态。

    HoloOcean 返回的状态可能有两种格式：
      1. 嵌套：state[agent_name] = {...sensory_data...}
      2. 平铺：state = {...sensory_data...}（单代理场景）

    此函数自动处理两种情况。

    参数：
        state: dict
            HoloOcean 返回的原始仿真状态
        agent_name: str
            要提取的代理名称

    返回值：
        dict：代理的状态（位姿、传感器数据等）
    """
    if agent_name in state and isinstance(state[agent_name], dict):
        return state[agent_name]
    return state


# ============================================================================
# 数据提取和处理函数
# ============================================================================

def rotation_matrix_to_euler(matrix):
    """
    将 3x3 旋转矩阵转换为欧拉角（滚转、俯仰、偏航）。

    参数：
        matrix: ndarray，形状 (3, 3)
            旋转矩阵

    返回值：
        ndarray，形状 (3,)：[roll, pitch, yaw] 欧拉角（弧度）
    """
    sy = np.sqrt(matrix[0, 0] ** 2 + matrix[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        roll = np.arctan2(matrix[2, 1], matrix[2, 2])
        pitch = np.arctan2(-matrix[2, 0], sy)
        yaw = np.arctan2(matrix[1, 0], matrix[0, 0])
    else:
        roll = np.arctan2(-matrix[1, 2], matrix[1, 1])
        pitch = np.arctan2(-matrix[2, 0], sy)
        yaw = 0.0
    return np.array([roll, pitch, yaw], dtype=float)


def extract_body_velocity(dvl_sensor):
    """
    从 DVL（多普勒速度测头）传感器读数中提取身体坐标系前向速度。

    DVL 传感器可能返回的格式有多种（1D、2D 数组或特殊结构），
    此函数统一处理所有情况，始终返回前 3 个分量（x, y, z 速度）。

    参数：
        dvl_sensor: array-like
            DVL 原始输出，可能是形状 (3,) 或 (1, 3) 或其他

    返回值：
        ndarray，形状 (3,)：[vx, vy, vz] 身体坐标系速度（m/s）
                          若数据缺失，返回 [0, 0, 0]
    """
    dvl = np.asarray(dvl_sensor)
    if dvl.ndim == 1 and dvl.size >= 3:
        return dvl[:3].astype(float)
    if dvl.ndim >= 2 and dvl.shape[-1] >= 3:
        return np.asarray(dvl[0]).reshape(-1)[:3].astype(float)
    return np.zeros(3, dtype=float)


def extract_gyro(imu_sensor):
    """
    从 IMU（惯性测量单元）传感器中提取角速度（陀螺仪）。

    IMU 通常返回 6 元向量 [ax, ay, az, gx, gy, gz]（加速度 + 角速度），
    或可能返回其他格式。本函数智能提取后 3 个分量（或其他位置）。

    参数：
        imu_sensor: array-like
            IMU 原始输出（可能是 6D、3D 或矩阵形式）

    返回值：
        ndarray，形状 (3,)：[gx, gy, gz] 角速度（rad/s）
                          若数据缺失，返回 [0, 0, 0]
    """
    imu = np.asarray(imu_sensor)
    if imu.ndim == 1:
        if imu.size >= 6:
            return imu[3:6].astype(float)
        if imu.size >= 3:
            return imu[:3].astype(float)
    if imu.ndim >= 2 and imu.shape[-1] >= 3:
        if imu.shape[0] >= 2:
            return np.asarray(imu[1]).reshape(-1)[:3].astype(float)
        return np.asarray(imu[0]).reshape(-1)[:3].astype(float)
    flat = imu.reshape(-1)
    if flat.size >= 3:
        return flat[-3:].astype(float)
    return np.zeros(3, dtype=float)


def extract_depth(depth_sensor, fallback_z):
    """
    从深度传感器或位置数据中提取深度值。

    如果深度传感器无效或缺失，使用 fallback_z（通常为位姿矩阵的 Z 坐标的反值）
    作为备选。

    参数：
        depth_sensor: array-like
            深度传感器读数（通常为 1D 数组的第一元素）
        fallback_z: float
            备选值，通常为 -pose[2, 3]（从位姿矩阵反推）

    返回值：
        float：深度（米）
    """
    depth = np.asarray(depth_sensor).reshape(-1)
    if depth.size >= 1:
        return float(depth[0])
    return float(-fallback_z)


# ============================================================================
# 工厂和后端选择
# ============================================================================

def _normalize_backend_name(backend_name):
    """
    规范化后端名称，映射多种别名到标准名称。

    参数：
        backend_name: str or None
            用户指定的后端名称（可能有多种拼写）

    返回值：
        str："holoocean"、"pvs" 或其他标准化后端名
    """
    backend = str(backend_name or "holoocean").strip().lower()
    if backend in {"ho", "holocean", "holoocean"}:
        return "holoocean"
    if backend in {"pvs", "pythonvehiclesimulator", "python_vehicle_simulator"}:
        return "pvs"
    return backend


def create_sim_wrapper(config, *, scenario_cfg, agent_name, show_viewport=False, verbose=False, window_res=None):
    """
    工厂函数：根据配置创建合适的仿真后端包装器。

    支持的后端：
      - holoocean（默认）：基于 UE4 的物理仿真器
      - pvs：PythonVehicleSimulator，轻量级直升机物理模拟

    参数：
        config: dict
            全局配置，包含 simulation.backend 字段
        scenario_cfg: dict
            仿真场景配置（由 build_scenario() 返回）
        agent_name: str
            要控制的代理名称
        show_viewport: bool
            是否显示 3D 渲染窗口
        verbose: bool
            是否启用详细日志
        window_res: tuple or None
            窗口分辨率

    返回值：
        HoloOceanSimWrapper 或 PVSSimWrapper：相应后端的包装器实例
    """
    backend_name = _normalize_backend_name((config or {}).get("simulation", {}).get("backend"))
    if backend_name == "pvs":
        from pvs_sim_wrapper import PVSSimWrapper

        return PVSSimWrapper(
            config=config,
            scenario_cfg=scenario_cfg,
            agent_name=agent_name,
            show_viewport=show_viewport,
            verbose=verbose,
        )

    return HoloOceanSimWrapper(
        scenario_cfg=scenario_cfg,
        agent_name=agent_name,
        show_viewport=show_viewport,
        verbose=verbose,
        window_res=window_res,
    )
