# 真机迁移SOP

从仿真迁移到真实AUV硬件的完整操作规程。

> **本文档是 6 步速记表，便于现场对照执行**。
> 如需完整的多 Level 实施路径（S1 链路审计 → S2 静态执行器 → S3 影子导航 → S4 单点闭环 → S5 全自主，每阶段独立 shell 入口、独立通过判据、独立失败回退），请前往 [`docs/real_deployment/INDEX.md`](../real_deployment/INDEX.md)。
> 急停 SOP 与"双保险"分工见 [`06_kill_switch.md`](../real_deployment/06_kill_switch.md)。仿真↔真机参数差异速查见 [`07_param_diff_sim_vs_real.md`](../real_deployment/07_param_diff_sim_vs_real.md)。

---

## 真机系统架构

```
上位机(PC) ←UDP→ Jetson(ROS2决策栈) ←UDP→ AMD PC104(执行层/VxWorks)
```

---

## 迁移检查清单

### Step 1: 通信链路配置

- 修改 `brain_linux/config/params.protocol_udp_arbiter.yaml`：
  - `protocol_udp.remote_host`: 127.0.0.1 → AMD实际IP
  - `protocol_udp.remote_port`: 确认AMD监听端口
  - `protocol_udp.bind_port`: Jetson监听端口（默认52364）
- 修改上位机 `console_config.yaml`：
  - `udp.target_host`: Jetson/AMD实际IP
  - `zenoh.router`: Jetson的Zenoh Router地址

### Step 2: 控制器参数切换

- 真机PID已在 `params.protocol_udp_arbiter.yaml` 中独立调优
- 关键差异：

| 参数 | 仿真 | 真机 |
|------|------|------|
| 深度Kp | 1.0 | 0.30 |
| 航向Kp | 40.0 | 9.0 |
| 速度Kp | 5.0 | 28.0 |
| 速度前馈 | 0/0/0 | 2.497/27.730/0.547 |
| 舵角限幅 | ±15° | ±30° |

### Step 3: 启动方式

```bash
# 使用仲裁器Launch（真机标配）
cd scripts
bash start_lin_brain.sh stack --arbiter-profile
```

等价于：

```bash
ros2 launch brain_linux auv_arbiter_stack.launch.py
```

### Step 4: 安全验证流程（上电前必做）

1. `minimal:=true` 模式：验证通信链路，不发送控制命令
2. `passive_mode:=true`：接收遥测，shadow观察，不发送
3. 手动遥控测试：上位机MANUAL模式，验证舵角/推力响应
4. 自主模式测试：上位机发送0xEE模式字节，验证仲裁器切换
5. ESTOP测试：紧急切断，验证推力归零

### Step 5: 传感器标定

- TF偏移：launch参数 `*_frame_offset_xyz` 填入真实安装位置
- EKF噪声：确认 `imu_acc_is_linear` 与真实IMU行为一致
- 海底深度：`seabed_depth_m` 根据作业水域设置
- 电压阈值：`guard_min_total_voltage_v` 匹配电池组

### Step 6: 关键配置文件地图

| 文件 | 角色 | 真机必须关注 |
|------|------|-------------|
| brain_linux/config/params.protocol_udp_arbiter.yaml | ROS2节点参数(真机) | 是 |
| config/real_params.yaml | 仿真侧覆盖(预留) | 否(Jetson不跑仿真) |
| console_soft/.../console_config.yaml | 上位机配置 | 是 |
| brain_linux/config/feature_flags.yaml | 功能开关 | 是 |
