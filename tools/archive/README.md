# tools/archive/ — 已归档脚本

本目录收录**已废弃或被取代的一次性调试/验证脚本**。它们在开发过程中曾用于定位某个具体 bug 或验证某次修复，但目前：

- **零活跃引用**：不被任何 shell 脚本（`scripts/**`）或活跃论文文档（`docs/**`）以 `tools/<name>.py` 路径调用；
- **已被更成熟的入口脚本取代**，或其诊断对象（bug）已修复、结论已并入论文正文。

归档采用 `git mv` 以保留文件历史。归档前均已 `grep` 全仓确认无引用（仅脚本自身 `--help`/用法字符串自引用）。

> 需要复现历史诊断时可直接运行本目录脚本，但注意其中的硬路径/实验编号多为当时一次性数据集，未必仍存在。日常维护与新实验请使用 [../README.md](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/README.md) 索引中的现役脚本。

---

## 归档清单

| 脚本 | 原用途 | 归档原因 |
|---|---|---|
| [analyze_mcap_v2.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/analyze_mcap_v2.py) | AUV mcap 实验数据分析 V2（手写 ROS2 CDR 反序列化） | 被 [analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py) / [analyze_mcap_experiments.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_mcap_experiments.py) 取代（迭代版本，非最终链路） |
| [analyze_mcap_v3.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/analyze_mcap_v3.py) | AUV mcap 实验数据分析 V3（改用 `ros2 bag` API） | 同上，V3 亦为过渡迭代版本，已被现役 bag 分析工具取代 |
| [analyze_turning.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/analyze_turning.py) | 从 MCAP 读 IMU 角速度、识别剧烈转向时间段 | 被 [analyze_turning_convergence.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_turning_convergence.py) 取代（后者直接给 ES-EKF vs StdEKF 转向段收敛对比） |
| [pid_ros2_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/pid_ros2_test.py) | ROS2 PID 控制器离线测试（PVS 动力学验证 params.yaml，三场景） | 被 [pid_tuner_pvs.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_tuner_pvs.py)（PID 调优最终版）与 [mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py) 取代 |
| [analyze_ekf_drift.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/analyze_ekf_drift.py) | 一次性深度分析"实验#4 (20260503_151522) 的 EKF 方向不一致异常" | 一次性调试脚本；对象 bug 已定位修复，绑定的单次实验数据集不再维护 |
| [debug_dvl_velocity.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/debug_dvl_velocity.py) | 一次性诊断 PVS 后端 DVL 速度定义与坐标系（nu[0:3] body/world、Rzyx 校验） | 一次性调试脚本；DVL 坐标系问题已修复 |
| [verify_dvl_fix.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/verify_dvl_fix.py) | 一次性验证 DVL 坐标系修复效果（方向一致性 + 积分轨迹对比） | 一次性验证脚本；与 debug_dvl_velocity.py 配套，修复已确认 |
| [verify_init_pos_alignment.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/verify_init_pos_alignment.py) | 一次性验证初始位置对齐（跑两次 enhanced_benchmark_analysis 比 RMSE） | 一次性验证脚本；对齐逻辑已确认并固化进现役基准工具 |
| [diagnose_coordinate_mismatch.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/diagnose_coordinate_mismatch.py) | 一次性诊断坐标系不匹配（真值/EKF/DVL 积分轨迹范围异常，RMSE 470+ m） | 一次性调试脚本；坐标系不匹配已定位修复 |
