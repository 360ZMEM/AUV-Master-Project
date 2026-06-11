# 00 — 原则页：上电之前必读

把 Jetson 接入真实 AUV 之前，把这页读完。它解释了为什么有 5 个阶段、为什么默认 mock、为什么有急停、为什么不动主线代码。

---

## 一、 三大战术指导原则（Why we shadow / unit-test / black-box）

### 1.1 影子测试 Shadowing
在剥夺 AMD 控制权之前，先让 Jetson 作为"观察员"运行——对比"我的指令"与"人类的指令"。
- 实现：S3 阶段 `passive_mode:=true`，bridge 节点照常发布 `/auv/bridge/shadow_cmd`，但**不**真发 UDP 下行。
- 工具：[tools/shadow_diff_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/shadow_diff_recorder.py)。
- 通过判据：航向 RMSE < 10°，深度 RMSE < 0.5 m。

### 1.2 协议单元化
不要相信任何大端序转换。先写一个独立的 ping-pong。
- S1 阶段直接征用 [scripts/vxworks_safety_hil.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/vxworks_safety_hil.py) `--mode auto-udp`。
- 单元自检：S0 已用 `python3 -c "build_downlink_packet(...) → 72B → parse_downlink_packet(...)"` 做 roundtrip。

### 1.3 数据黑匣子化
实测第一天最重要的不是控制算法，是 `ros2 bag record -a`。没有数据，实机问题永远"难以理解"。
- S5 全程录 bag。`mock` 路径直接复用 [scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh)。
- 离线分析：[docs/user-guide/04_rosbag_analysis.md](../user-guide/04_rosbag_analysis.md)。

---

## 二、 三大架构智慧（How the codebase enforces safety）

### 2.1 Hardware Interface 隔离层
算法不直接调 UDP。`Generic_AUV_Interface` 有两个落地：
- `Mock_AMD_Interface` — sim_holoocean + protocol_udp 后端（仿真用）
- `PC104_UDP_Interface` — 真机下行 21 端口（实机用）

切换环境只改一行 yaml：[brain_linux/config/params.protocol_udp_arbiter.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.protocol_udp_arbiter.yaml) 的 `protocol_udp.remote_host`。

### 2.2 Kill-Switch（急停）
[scripts/real_deployment/kill_switch.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/kill_switch.sh) 周期发 `Work_Cmd=0x02 + Motor_Speed=0 + ctrl_mode=0x01` 的 ESTOP 帧 @ 20 Hz。
- 它**独立于 ROS2/Zenoh**，只依赖 `common.protocol`。
- VxWorks 失联安全机制是冗余保险——Jetson 进程死循环 → AMD 1s 内自发停机。
- 详见 [06_kill_switch.md](06_kill_switch.md)。

### 2.3 Sequence Number 对齐
PC104 没有 `ros2 bag`。`$AUV` 上行帧自带帧序号。
- 诊断方法：发现序号从 100 跳到 105 → WiFi 或 AMD 内部丢包。
- 工具：[tools/actuator_polarity_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/actuator_polarity_recorder.py) 写 CSV 后 grep 序号差。

---

## 三、 本会话固化的三条铁律

| # | 铁律 | 落地形式 |
|---|------|---------|
| 1 | **完全向后兼容** | 不改 launch / yaml / start_*.sh / .py 主线源码；新增 shell 与工具与现有正交 |
| 2 | **静态验证优先** | 每个 stage shell 都有 `--dry-run`；S0 是离线 colcon build + pytest + 协议自检 |
| 3 | **mock AMD 默认** | `--target` 默认 `mock`；`real` 强制需要 `--i-have-physical-auv` |

---

## 四、 标准文档对位

| 标准 | 实物部署引用点 |
|------|---------------|
| [自主式水下航行器设计方案 2021.5.28](../../标准文档/自主式水下航行器设计方案2021.5.28.md) | S2 极性方向（左舵/右舵安装方位）、S5 巡检剖面 |
| [软件通信协议](../../标准文档/软件通信协议.md) | S1 字节序/scale；`$CKTH` 72B / `$AUV` 145B 帧布局 |
| [VxWorks 最新协议](../../标准文档/VxWorks最新协议.md) | S1 双向握手；`Current_Cmd_State` 反馈位 |
| DLT+1278—2025 海底电力电缆运行规程 PDF（`标准文档/`） | S5 寻迹任务工程合规 |

---

## 五、 失败时的求救锚点

- 不知道哪个 stage 出错 → 看 `log/real_deployment/<RUN_ID>/report.md`
- 想立刻停 → `bash scripts/real_deployment/kill_switch.sh --target $TARGET`（或 Ctrl+C 触发 trap）
- 不确定参数 → [07_param_diff_sim_vs_real.md](07_param_diff_sim_vs_real.md)
- 启动后 8 秒以内进程崩 → 检查 `log/real_deployment/<RUN_ID>/stack.log` 与 `mock_amd.stderr`
