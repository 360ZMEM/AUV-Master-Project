"""Zenoh 仿真桥接层。

负责把仿真侧状态发布到 Zenoh 主题，并接收下行控制命令，作为仿真和
决策之间的轻量中间件适配器。
"""

import json
import threading
import time


class ZenohBridge:
    """Zenoh 发布/订阅桥接器。"""

    def __init__(self, config):
        """使用桥接配置初始化会话、发布器和控制命令缓存。"""
        self.config = config
        self._session = None
        self._publishers = {}
        self._cmd_lock = threading.Lock()
        self._latest_cmd = None
        self._latest_cmd_ts = 0.0
        self._subscriber = None
        self._open_zenoh = None

    def open(self):
        """打开 Zenoh 会话并注册发布器与控制命令订阅。"""
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

        uplink = self.config["uplink_keys"]
        for name, keyexpr in uplink.items():
            self._publishers[name] = self._session.declare_publisher(keyexpr)

        cmd_key = self.config["downlink_cmd_key"]

        def on_cmd(sample):
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
        """关闭所有 Zenoh 句柄并释放会话资源。"""
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
        """向指定通道发布 JSON 负载。"""
        if channel_name not in self._publishers:
            return
        payload = json.dumps(payload_dict, ensure_ascii=False)
        self._publishers[channel_name].put(payload)

    def get_uplink_topic(self, channel_name):
        """查询指定通道对应的 Zenoh 主题名。"""
        return self.config["uplink_keys"].get(channel_name, "")

    def get_latest_cmd(self):
        """返回最近一次收到的下行命令及其时间戳。"""
        with self._cmd_lock:
            return self._latest_cmd, self._latest_cmd_ts
