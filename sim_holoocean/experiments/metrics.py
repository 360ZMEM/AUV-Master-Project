"""
仿真性能指标计算 - 轨迹跟踪误差评估。

该模块从仿真历史记录中计算关键性能指标（KPI），用于控制器性能评估。

计算的指标：
  - rms（均方根误差）：位置跟踪的整体误差
  - mean_error（平均误差）：位置误差的平均值
  - trajectory_length（轨迹长度）：参考轨迹的总长度
  - axis_ratio（轴向比）：平均误差相对于轨迹长度的比例
  - sat_ratio（饱和率）：控制命令达到饱和限制的时间步比例
  - safety_event_count（安全事件计数）：触发的安全事件总数
  - pass_rms（RMS 阈值通过）：是否满足 RMS 误差要求
  - pass_axis_ratio（轴向比通过）：是否满足轴向比要求

使用方式：
  >>> from metrics import compute_metrics
  >>> history = {
  ...     "pos": [[0, 0, 0], [1, 0.5, -0.5]],
  ...     "ref": [[0, 0, 0], [1, 0.5, -0.5]],
  ...     "saturated_any": [False, True],
  ...     "safety_event_count": 0,
  ... }
  >>> eval_cfg = {"rms_threshold_m": 0.5, "axis_ratio_threshold": 0.1}
  >>> metrics = compute_metrics(history, eval_cfg)
"""

import numpy as np


def compute_metrics(history, eval_cfg):
    """
    从仿真历史计算性能指标。

    逻辑：
      1. 提取位置和参考轨迹
      2. 计算逐点误差的欧几里得范数
      3. 计算 RMS、平均误差、轴向比
      4. 统计控制饱和率和安全事件
      5. 与阈值比较得出 pass/fail 结论

    参数：
        history (dict)：仿真运行历史，包含：
          - pos (array-like)：AUV 实际轨迹 [N, 3]
          - ref (array-like)：参考轨迹 [N, 3]
          - saturated_any (list[bool])：每步控制是否饱和
          - safety_event_count (int)：安全事件总数
        eval_cfg (dict)：评估配置，包含：
          - rms_threshold_m (float)：RMS 误差阈值（米）
          - axis_ratio_threshold (float)：轴向比阈值

    返回值：
        dict：包含所有计算指标
          - rms (float)：均方根误差（米）
          - mean_error (float)：平均误差（米）
          - trajectory_length (float)：轨迹长度（米）
          - axis_ratio (float)：轴向比（无量纲）
          - sat_ratio (float)：饱和率 [0, 1]
          - safety_event_count (int)：安全事件计数
          - pass_rms (bool)：是否通过 RMS 阈值检查
          - pass_axis_ratio (bool)：是否通过轴向比检查

    边界情况：
      - 空 history：返回 NaN 值和 False 通过标志
      - 长度不匹配：截断至较短长度
    """
    pos = np.asarray(history["pos"], dtype=float)
    ref = np.asarray(history["ref"], dtype=float)

    if pos.size == 0 or ref.size == 0:
        # ────────────────────────────────────────────────
        # 空 history：返回默认值
        # ────────────────────────────────────────────────
        sat_count = int(np.sum(history.get("saturated_any", [])))
        sat_total = len(history.get("saturated_any", []))
        sat_ratio = sat_count / max(sat_total, 1)
        return {
            "rms": float("nan"),
            "mean_error": float("nan"),
            "trajectory_length": 0.0,
            "axis_ratio": float("inf"),
            "sat_ratio": sat_ratio,
            "safety_event_count": int(history.get("safety_event_count", 0)),
            "pass_rms": False,
            "pass_axis_ratio": False,
        }

    # ────────────────────────────────────────────────
    # 标准化形状：处理 1D 输入
    # ────────────────────────────────────────────────
    if pos.ndim == 1:
        pos = pos.reshape(1, -1)
    if ref.ndim == 1:
        ref = ref.reshape(1, -1)

    # ────────────────────────────────────────────────
    # 对齐长度：取较短序列
    # ────────────────────────────────────────────────
    n = min(len(pos), len(ref))
    pos = pos[:n]
    ref = ref[:n]

    # ────────────────────────────────────────────────
    # 计算误差指标
    # ────────────────────────────────────────────────
    err = np.linalg.norm(ref - pos, axis=1)
    rms = float(np.sqrt(np.mean(err * err)))

    trajectory_length = float(np.sum(np.linalg.norm(np.diff(ref, axis=0), axis=1)))
    mean_error = float(np.mean(err))
    axis_ratio = mean_error / max(trajectory_length, 1e-9)

    sat_count = int(np.sum(history["saturated_any"]))
    sat_ratio = sat_count / max(len(history["saturated_any"]), 1)

    return {
        "rms": rms,
        "mean_error": mean_error,
        "trajectory_length": trajectory_length,
        "axis_ratio": axis_ratio,
        "sat_ratio": sat_ratio,
        "safety_event_count": int(history["safety_event_count"]),
        "pass_rms": rms <= float(eval_cfg["rms_threshold_m"]),
        "pass_axis_ratio": axis_ratio <= float(eval_cfg["axis_ratio_threshold"]),
    }
