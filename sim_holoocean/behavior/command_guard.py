"""
控制命令护栏 - 下行命令的边界保护和超时处理。

该模块实现仿真侧的安全护栏，在执行每一条下行控制命令之前进行：
  1. 解析验证：从 Zenoh JSON 中提取并归一化控制向量
  2. 超时检查：如果命令超龄（>timeout_s），使用上一条有效命令
  3. 限幅保护：将舵角和推力限制在允许范围内
  4. 首条命令检查：（可选）启动阶段等待首条可信命令

本护栏保证仿真永远不会接收到畸形、超龄或违反物理约束的命令。

关键概念：
  - 命令超时：如果 now - cmd_ts > timeout_s，视为舍弃
  - 护栏保持性：若输入无效，始终返回有效的前一命令（不是零向量）
  - 限幅策略：舵角和推力分别限幅，避免执行器过度激励
"""

import time
import numpy as np
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder in [PROJECT_ROOT, PROJECT_ROOT / "common"]:
    folder = str(folder)
    if folder not in sys.path:
        sys.path.insert(0, folder)

from common.protocol import KEY_BOTTOM, KEY_LEFT, KEY_RIGHT, KEY_THRUST, KEY_TOP, normalize_control_command


class CommandGuard:
    """────────────────────────────────────────────────────────────────
    下行控制命令的安全护栏
    ────────────────────────────────────────────────────────────────

    职责：
      1. 从上游 Zenoh 接收的原始命令消息进行解析和格式验证
      2. 检查命令的时间新鲜度（是否超时）
      3. 对舵角和推力执行硬限幅
      4. 在命令无效时退回到上一条有效命令（冗余安全）

    保证性质：
      - 始终返回长度为 5 的命令向量
      - 舵角 [0:4] 被限制在 [-fin_abs_max, fin_abs_max]
      - 推力 [4] 被限制在 [thrust_min, thrust_max]
      - 超时命令被视为无效，使用上一条有效命令

    流程（每个时间步）：
      1. sanitize(cmd_msg, previous_cmd, cmd_ts) 入口
      2. _extract_command() 解析和归一化 JSON
      3. 检查时间戳新鲜度
      4. 限幅处理
      5. 返回安全的 5 元向量
    """

    def __init__(self, cfg):
        """
        初始化护栏。

        参数：
            cfg (dict)：来自全局配置的 'bridge' 组。包含：
              - cmd_timeout_s (float)：命令超时阈值（秒），默认 0.5s
              - require_first_cmd (bool)：是否要求启动时收到首条命令，默认 False
              - fin_abs_max (float)：舵角限幅（度），默认 30°（HoloOcean 兼容）
              - thrust_min, thrust_max (float)：推力限幅范围，默认 [-100, 100]

        配置示例：
            cfg = {
                'cmd_timeout_s': 0.5,
                'require_first_cmd': True,
                'fin_abs_max': 30.0,
                'thrust_min': -100.0,
                'thrust_max': 100.0,
            }
        """
        self.cfg = cfg
        self.timeout_s = float(cfg.get("cmd_timeout_s", 0.5))
        self.require_first_cmd = bool(cfg.get("require_first_cmd", False))
        self.start_time = time.time()

        # ────────────────────────────────────────
        # 执行器限幅
        # ────────────────────────────────────────
        self.fin_abs_max = float(cfg.get("fin_abs_max", 30.0))
        self.thrust_min = float(cfg.get("thrust_min", -100.0))
        self.thrust_max = float(cfg.get("thrust_max", 100.0))

    def _extract_command(self, cmd_msg):
        """
        从原始命令消息中提取和归一化控制向量。

        解析流程：
          1. 验证 cmd_msg 是否为 None（无命令）
          2. 调用 normalize_control_command() 将计数单位转为标准单位
          3. 按照标准顺序提取舵角和推力：[right, top, left, bottom, thrust]
          4. 返回为 numpy 数组（便于后续限幅）

        参数：
            cmd_msg (dict or None)：Zenoh 接收的原始命令字典

        返回值：
            ndarray (5,) 或 None：
              - 成功：[right_deg, top_deg, left_deg, bottom_deg, thrust_pct]
              - 失败或无命令：None

        容错策略：
            解析失败时（包括格式错误、缺失字段）静默返回 None，
            不抛出异常，由调用层处理。
        """
        if cmd_msg is None:
            return None
        try:
            norm = normalize_control_command(cmd_msg)
        except Exception:
            return None
        return np.asarray(
            [
                norm[KEY_RIGHT],
                norm[KEY_TOP],
                norm[KEY_LEFT],
                norm[KEY_BOTTOM],
                norm[KEY_THRUST],
            ],
            dtype=float,
        )

    def sanitize(self, cmd_msg, previous_cmd, cmd_ts):
        """
        执行完整的命令护栏流程。

        流程：
          1️⃣ 解析命令：_extract_command() 从 JSON 提取
          2️⃣ 有效性检查：若无命令，返回前一命令或零向量（取决于 require_first_cmd）
          3️⃣ 超时检验：if (now - cmd_ts) > timeout_s，丢弃，使用前一命令
          4️⃣ 限幅保护：舵角限制在 [-fin_abs_max, +fin_abs_max]，推力限制在 [thrust_min, thrust_max]
          5️⃣ 返回：always 返回有效的 5 元向量

        冗余设计：
          - 若上游命令断开，始终返回前一命令（不急停）
          - 允许配置 require_first_cmd 来强制等待首个命令
          - 超时后自动降级到上一命令（故障恢复）

        参数：
            cmd_msg (dict or None)：当前接收的命令消息
            previous_cmd (array-like)：上一个有效的命令向量
            cmd_ts (float)：命令的时间戳（上游发送时刻）

        返回值：
            ndarray (5,)：经过护栏处理后的安全命令向量

        示例：
            >>> guard = CommandGuard(cfg)
            >>> # 无命令到达时，返回上一条
            >>> cmd = guard.sanitize(None, [0, 0, 0, 0, 50], time.time())
            >>> # 命令超时时，自动使用上一条
            >>> stale_cmd = {'thrust': 50}  # 时间戳太旧
            >>> cmd = guard.sanitize(stale_cmd, [0, 0, 0, 0, 50], old_time)
        """
        now = time.time()
        cmd = self._extract_command(cmd_msg)

        # ────────────────────────────────────────
        # 步骤 1️⃣：检查命令有效性
        # ────────────────────────────────────────
        if cmd is None or cmd.size != 5:
            # 若启动阶段尚未收到有效命令，返回零向量
            if self.require_first_cmd and (now - self.start_time) < self.timeout_s:
                return np.zeros(5, dtype=float)
            # 否则使用上一条命令（冗余安全）
            return np.asarray(previous_cmd, dtype=float).reshape(5)

        # ────────────────────────────────────────
        # 步骤 2️⃣：检查时间新鲜度
        # ────────────────────────────────────────
        if now - float(cmd_ts) > self.timeout_s:
            # 命令老化，丢弃，使用上一条
            return np.asarray(previous_cmd, dtype=float).reshape(5)

        # ────────────────────────────────────────
        # 步骤 3️⃣：限幅处理
        # ────────────────────────────────────────
        cmd = cmd.copy()
        # 舵角限幅（4 个通道）
        cmd[:4] = np.clip(cmd[:4], -self.fin_abs_max, self.fin_abs_max)
        # 推力限幅（1 个通道）
        cmd[4] = np.clip(cmd[4], self.thrust_min, self.thrust_max)
        return cmd
