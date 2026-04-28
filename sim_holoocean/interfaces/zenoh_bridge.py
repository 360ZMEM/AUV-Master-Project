"""Zenoh 仿真桥接层 - 实时发布订阅中间件。

该模块实现了 HoloOcean 仿真侧与 ROS2 决策侧之间的轻量级消息桥接：

架构设计：
  上行（仿真→决策）：
    - 仿真在每个时间步计算传感器数据
    - 打包为 JSON，通过 ZenohBridge.publish() 发送到多个 Zenoh topic
    - 决策侧通过 ROS2 订阅这些 Zenoh topic（via auv_bridge）

  下行（决策→仿真）：
    - 决策侧发布控制命令到 Zenoh downlink_cmd_key
    - ZenohBridge 异步接收和缓存最新命令
    - 仿真侧通过 get_latest_cmd() 轮询获取命令

关键职责：
  1. 会话管理：打开/关闭 Zenoh 会话，连接配置生效
  2. 发布器创建：为每个 topic 分配发布器实例（高性能缓存）
  3. 订阅器创建：单一控制命令通道，使用回调缓存最新值
  4. 线程安全：使用互斥锁保护命令缓存的并发访问
  5. 容错处理：序列化/反序列化异常时忽略（丢弃该消息）

使用流程：
  >>> from common.protocol import ZENOH_TOPIC_GROUND_TRUTH
  >>> bridge = ZenohBridge(config)
  >>> bridge.open()
  >>> # 发布传感器数据
  >>> bridge.publish("ground_truth", {"position_ned": [0, 0, -10]})
  >>> # 接收控制命令
  >>> cmd, ts = bridge.get_latest_cmd()
  >>> bridge.close()
"""

import json
import threading
import time


class ZenohBridge:
    """────────────────────────────────────────────────────────────────
    Zenoh 发布/订阅桥接器（主类）
    ────────────────────────────────────────────────────────────────

    职责：
      - 管理 Zenoh 会话的生命周期
      - 为上行 topic 创建发布器
      - 为下行 topic 创建订阅器，缓存最新命令
      - 确保发布和接收的线程安全

    属性：
      config (dict)：桥接配置，包含：
        - 'session'：Zenoh 会话配置字典
        - 'uplink_keys'：{名称 → Zenoh keyexpr} 的 dict（发布通道）
        - 'downlink_cmd_key'：控制命令订阅的 keyexpr（接收通道）
      _session：Zenoh session 对象（打开后）
      _publishers (dict)：{名称 → Zenoh Publisher} 映射
      _cmd_lock (threading.Lock)：保护 _latest_cmd 的互斥锁
      _latest_cmd (dict|None)：最新接收的控制命令 JSON
      _latest_cmd_ts (float)：命令接收时的 Unix 时间戳
    """

    def __init__(self, config):
        """初始化桥接器（不打开会话）。

        参数：
            config (dict)：从 config/bridge_params.yaml 加载的配置

        异常：
            无（推迟到 open()）
        """
        self.config = config
        self._session = None
        self._publishers = {}
        self._cmd_lock = threading.Lock()
        self._latest_cmd = None
        self._latest_cmd_ts = 0.0
        self._subscriber = None
        self._open_zenoh = None

    def open(self):
        """打开 Zenoh 会话并注册所有发布器与订阅器。

        流程：
          1. 导入 zenoh 模块（延迟导入）
          2. 从 config['session'] 构建 Zenoh Config 对象
          3. 打开 Zenoh 会话
          4. 为 config['uplink_keys'] 中的每个通道创建 Publisher
          5. 为 config['downlink_cmd_key'] 创建 Subscriber（异步回调）

        返回值：
            self（支持链式调用）

        异常：
            ImportError：未找到 zenoh 包

        示例：
            >>> bridge = ZenohBridge(cfg)
            >>> bridge.open()  # 会话已就绪
            >>> bridge.publish("imu", {...})
        """
        try:
            import zenoh
        except Exception as exc:
            raise ImportError(
                "zenoh python package not found. Add it to requirements and install first."
            ) from exc

        self._open_zenoh = zenoh
        session_cfg = self.config.get("session", {})
        zcfg = zenoh.Config()
        for key, value in session_cfg.items():
            zcfg.insert_json5(str(key), json.dumps(value))

        self._session = zenoh.open(zcfg)

        # 注册所有上行发布器
        uplink = self.config["uplink_keys"]
        for name, keyexpr in uplink.items():
            self._publishers[name] = self._session.declare_publisher(keyexpr)

        # 注册下行控制命令订阅器
        cmd_key = self.config["downlink_cmd_key"]

        def on_cmd(sample):
            """────────────────────────────────────────────────────────────
            Zenoh 订阅回调：解析并缓存最新控制命令

            流程：
              1. 提取 Zenoh sample 的 payload（字节序列）
              2. 尝试解析为 UTF-8 JSON 字符串
              3. 将 JSON dict 存入 _latest_cmd，更新时间戳
              4. 如果解析失败，静默丢弃（避免阻塞回调）

            参数：
                sample (zenoh.Sample)：Zenoh 发布的消息
            ────────────────────────────────────────────────────────────
            """
            payload = sample.payload.to_bytes() if hasattr(sample.payload, "to_bytes") else bytes(sample.payload)
            try:
                data = json.loads(payload.decode("utf-8"))
            except Exception:
                return
            with self._cmd_lock:
                self._latest_cmd = data
                self._latest_cmd_ts = time.time()

        self._subscriber = self._session.declare_subscriber(cmd_key, on_cmd)
        return self

    def close(self):
        """关闭所有 Zenoh 句柄并释放会话资源。

        流程（顺序重要）：
          1. 撤销订阅器声明，释放回调线程
          2. 撤销所有发布器声明
          3. 关闭会话，释放网络资源

        容错：
            所有 undeclare/close 调用都用 try-except 包裹，
            防止部分失败导致其他资源泄露。

        返回值：
            无
        """
        if self._subscriber is not None:
            try:
                self._subscriber.undeclare()
            except Exception:
                pass
            self._subscriber = None

        for pub in self._publishers.values():
            try:
                pub.undeclare()
            except Exception:
                pass
        self._publishers = {}

        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def publish(self, channel_name, payload_dict):
        """向指定通道发布 JSON 负载。

        参数：
            channel_name (str)：通道名称（必须在 config['uplink_keys'] 中）
            payload_dict (dict)：任意嵌套的 Python 字典

        行为：
            - 若 channel_name 不存在，静默返回（无异常）
            - 使用 json.dumps(ensure_ascii=False) 保留中文字符
            - 通过发布器的 put() 方法发送（异步）

        示例：
            >>> bridge.publish("imu", {
            ...     "accel_ned": [0.1, 0.05, 9.81],
            ...     "gyro_ned": [0.001, 0.002, 0.003],
            ... })
        """
        if channel_name not in self._publishers:
            return
        payload = json.dumps(payload_dict, ensure_ascii=False)
        self._publishers[channel_name].put(payload)

    def get_uplink_topic(self, channel_name):
        """查询指定通道对应的完整 Zenoh 主题表达式。

        参数：
            channel_name (str)：通道名称

        返回值：
            str：Zenoh keyexpr，如 'rt/auv/sensors/imu'；
                 不存在时返回空字符串

        用途：
            调试和文档生成时确认实际使用的 Zenoh 路径
        """
        return self.config["uplink_keys"].get(channel_name, "")

    def get_latest_cmd(self):
        """返回最近一次收到的下行命令及其时间戳。

        返回值：
            tuple (cmd, ts)：
              - cmd (dict|None)：最新的控制命令 JSON；
                                未收到任何命令时为 None
              - ts (float)：命令接收时的 Unix 时间戳；
                           无命令时为 0.0

        线程安全：
            使用 _cmd_lock 确保读取一致性

        示例：
            >>> cmd, ts = bridge.get_latest_cmd()
            >>> if cmd is not None:
            ...     throttle = cmd.get("throttle", 0)
            ...     rudder = cmd.get("rudder", 0)
        """
        with self._cmd_lock:
            return self._latest_cmd, self._latest_cmd_ts
