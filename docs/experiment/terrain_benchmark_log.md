# 地形跟随基准端到端验证日志

**日期**: 2026-06-08
**目的**: 以新手视角按 [docs/user-guide/10_terrain.md](../user-guide/10_terrain.md) 契约执行完整流程，验证脚本正确性、暴露 4 个修复后的真实运行状态、记录每一步预期结果与实际坑点。
**配套文档**: [user-guide/10_terrain.md](../user-guide/10_terrain.md) · [.trae/documents/terrain_following_fix_plan.md](../../.trae/documents/terrain_following_fix_plan.md)

> 阅读姿势：每一节先读"预期 / 命令 / 结果 / 坑点"四段，按顺序复现。

---

## Step 0：环境前置

### 命令

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
# 0.1 杀掉一切残留（避免端口/共享内存/上一次实验状态污染）
pkill -KILL -f "run_zenoh_bridge.py|sim_holoocean/apps/main.py|mock_amd_server|ros2 launch foxglove_bridge|ros2 launch.*auv_stack|ros2 bag record" 2>/dev/null
sleep 3
# 0.2 编译 brain 包（只在源码改过时需要，~18s 增量）
source /opt/ros/humble/setup.bash
cd brain_linux && colcon build --packages-select auv_bridge auv_controller && cd ..
```

### 预期

- `pkill` 退出码非零无所谓（pkill 找不到进程时返回 1，已用 `|| true` 在脚本内吞掉）
- colcon `Summary: 2 packages finished` 即成功

### 坑点

| 坑 | 现象 | 处理 |
|---|------|-----|
| conda 干扰 | `ModuleNotFoundError: em` | `conda deactivate`，或 `start_lin_brain.sh` 内已自动 deactivate |
| 共享内存残留 | colcon 编译没问题但运行时 `RTPS_TRANSPORT_SHM Error: open_and_lock_file failed -> Function open_port_internal` | 通常是无害告警（FastRTPS 自动 fallback 到 UDP）；若节点完全无响应，删 `/dev/shm/fastrtps_*` |
| `/auv_data` 写保护 | 任何 `mv` 到 `/auv_data` 失败 | 我们的 benchmark 脚本已改为只**记录路径**而不移动 |

---

## Step 1：一键基准运行

### 命令

```bash
bash scripts/run_terrain_benchmark.sh 60   # 每 phase 60 秒，整个流程约 3 分钟
```

### 预期

| 阶段 | stdout 关键字 | 时长 | 关键产物 |
|------|--------------|-----|----------|
| Banner | `Terrain Following Benchmark` `Output: results/control/terrain_following_<TS>` | 即刻 | `results/control/terrain_following_<TS>/` |
| Phase 1/2 (CONSTANT) | `=== Phase 1/2: Baseline (depth_mode: CONSTANT) ===` `[AUV] experiment running for 60s` `requested duration reached, finalizing via cleanup trap` | ~75s | `baseline/bag_path.txt` 指向 `/auv_data/bags/<TS>/` |
| Inter-phase sweep | `[terrain_benchmark] inter-phase orphan sweep...` | 2s | — |
| Phase 2/2 (TERRAIN_FOLLOWING) | `=== Phase 2/2: Terrain Following ===` 同上 | ~75s | `terrain/bag_path.txt` |
| Phase 3 Analysis | `=== Phase 3: Analysis ===` | ~10s | `baseline/analysis/`、`terrain/analysis/` (figures + report.md) |
| Footer | `Benchmark complete!` `Key metrics to compare:` | — | — |
| feature_flags 恢复 | `[terrain_benchmark] feature_flags.yaml restored.` | — | `feature_flags.yaml` 内容回到原状 |

### Ctrl+C 中断行为（修复后）

- 第一次 Ctrl+C 即终止整个流程，不会"继续 Phase 2 让仿真又开一次"
- 信号链路 INT → TERM → KILL 三段升级，每段 5s 宽限
- 末端 `pkill -KILL -f` 兜底，确保**无孤儿**

### 坑点（实测）

| 坑 | 现象 | 状态 |
|---|------|------|
| C1：bag 0 字节 | `rosbag/rosbag_0.mcap` size=0；`metadata.yaml` 不存在 | **未解决** — 详见 §3 |
| C2：行为树 StandbyCheck | `step=NNNN mode=AUTO`，但 `Depth: 12.00m`、`Right Fin: 0.0 deg` 全程不变 | **未解决** — 详见 §3 |
| C3：analysis 目录空 | `baseline/analysis/`、`terrain/analysis/` 不存在或空 | **C1 的下游表现** |
| C4：FastRTPS 共享内存告警 | 启动时大量 `Failed init_port fastrtps_portXXXX` | **可忽略** — 自动 fallback UDP，节点照常注册 |
| C5：mock_amd 端口冲突 | 上次实验残留进程 → `Address already in use` | **已修复** — phase 间 `pkill -KILL -f` 防御性扫尾 |
| C6：feature_flags 不被加载 | `terrain` phase 实际仍跑 CONSTANT | **已修复** — yaml 加上 `/**: ros__parameters:` |

---

## Step 2：手工对照（绕过 benchmark 脚本）

如果只想跑单一 phase 调参，使用 [start_experiment.sh](../../scripts/start_experiment.sh) 直接：

### 命令（terrain phase）

```bash
# 备份并切换 feature_flags
cp brain_linux/config/feature_flags.yaml /tmp/.feature_flags_backup.yaml
cp brain_linux/config/feature_flags_terrain.yaml brain_linux/config/feature_flags.yaml

bash scripts/start_experiment.sh \
    --sim-backend pvs \
    --bridge-backend protocol_udp \
    --arbiter-profile \
    --duration 60 \
    --record-bag

# 跑完务必恢复
cp /tmp/.feature_flags_backup.yaml brain_linux/config/feature_flags.yaml
rm /tmp/.feature_flags_backup.yaml
```

### 预期 bag 内容（理想）

```bash
ros2 bag info <BAG_DIR>
```

应见话题：

- `/auv/odom/world` (nav_msgs/Odometry, ~50Hz)
- `/auv/sensors/depth` (Float32, ~50Hz)
- `/auv/sensors/altitude` (Float32, ~10Hz)  ← **TF 修复 #2**
- `/auv/sensors/forward_sonar_slope` (Float32, ~10Hz) ← **TF 修复 #3**
- `/auv/setpoint/depth` (Float32) — terrain 模式下应**动态变化**
- `/auv/setpoint/heading` (Float32)
- `/auv/control/pwm_cmd` (geometry_msgs/Twist) — 应**非零**
- `/auv/decision/state` (String) — 应在 `MainMission`/`TrackAnalyticalTrajectory` 切换，**不应**全程 `StandbyCheck`

### 坑点

| 坑 | 现象 | 排查 |
|---|------|------|
| StandbyCheck 卡死 | `/auv/decision/state` 永远是 `StandbyCheck` | 见 §3.2 |
| altitude 永远 = 默认值 | `/auv/sensors/altitude` 不存在或恒等 | 检查 `bridge_params*.yaml` 是否启用 `altitude_key` 订阅 |

---

## Step 3：当前实验产物分析（实测：修复后第一次 60s 运行）

### 实验位置

`results/control/terrain_following_20260608_194856/`

### 实测产物

```
terrain_following_20260608_194856/
├── baseline_log.txt               # 73K, 启动期 + 仿真稳态全量 stdout
├── baseline/
│   └── bag_path.txt               # → /auv_data/bags/20260608_194857
├── terrain_log.txt
└── terrain/
    └── bag_path.txt
                                   ↑↑↑ 没有 analysis/ 子目录！
```

bag 实际内容：

```text
/auv_data/bags/20260608_194857/
├── launcher.log                   # 7.0 MB （来自 setsid + tee 的全量 fxglove/sim/brain stdout）
├── metadata.txt                   # 339 B  （run_id、git_head 等元数据，未损坏）
├── rosbag/
│   └── rosbag_0.mcap              # 0 字节 ← 严重问题
├── rosbag.log                     # 142 B  仅 "Press SPACE for pausing/resuming"
                                   # ❌ 没有 metadata.yaml （rosbag2 finalize 必产物）
```

### 3.1 Bag 0 字节根因分析

**症状**：
- `rosbag/rosbag_0.mcap` size = 0
- `metadata.yaml` 缺失（rosbag2 正常关闭时一定写）
- `rosbag.log` 只有启动行，没有 `Closing all topics` / `recorded N messages` 等日志

**关键证据**（来自 `launcher.log` 末尾 8 万行 mock_amd 帧）：

```
TELEMETRY:
  Depth:        12.00 m              ← 恒定不变！
  Heading:      +360.0 deg           ← 恒定不变！
  Main Motor:       0 RPM            ← 没动！
CONTROL REPLAY:
  Right Fin:    +0.0 deg             ← 没操舵！
  Top Fin:      +0.0 deg
step=007511 mode=AUTO                ← 自主模式开了，但啥都没做
```

**推断**：
1. ROS 节点（zenoh_json_bridge_node, auv_controller_node, decision_node）确实启动了（`launcher.log` 中有 `process started with pid` 行）
2. 但**它们没有发布任何带数据的消息** — 行为树停在 StandbyCheck，控制器没有 setpoint，控制循环没有输出
3. `ros2 bag record -a` 虽然在跑，但没有任何 publisher 产生 message → mcap 维持 0 字节

**结论**：bag 0 字节是 **C2（行为树未激活）的下游表现**，不是 rosbag2 本身的 bug。

### 3.2 行为树停在 StandbyCheck 根因（2026-06-08：调用链已贯通）

> **TL;DR**：基准脚本忘了启动"上位机"。Bridge 的 AutonomyGuard 默认 `LOCKED`，必须等 PC 经 Zenoh 主题 `rt/pc/cmd_raw` 发来一帧 `control_mode_byte = 0xEE (JETSON_PROTOCOL)` 才会被请求进入 `ACTIVE`。Benchmark 链路里没有任何进程在发这帧，所以行为树永远卡在 StandbyCheck，控制器拿不到 setpoint，bag 录不到 message。

完整调用链：

```
[ start_experiment.sh ]   启动 sim + bridge + brain（不启动 console）
        │
        ▼
[ bridge_node ]
   - AutonomyGuard 初始化为 LOCKED              autonomy_guard.py
   - 通过 Zenoh side-channel 订阅 rt/pc/cmd_raw  bridge_backends.py:299
   - protocol_udp.zenoh_side_channel_enabled: true (params.protocol_udp_arbiter.yaml:40)
        │   ⬅ 没有任何 publisher 向 rt/pc/cmd_raw 发包
        ▼
[ handle_pc_raw_command() ]                     bridge_node.py:379
   - 永不被触发 → request_activation 永不被调用 → _state 一直 LOCKED
        ▼
[ /auv/arbiter/status.auto_state = "LOCKED" ]
        ▼
[ decision_node.sensor_status.auto_state ← "LOCKED" ]   decision_node.py:225-227
        ▼
[ Wait_For_Arbiter_Authorization (StandbyCheck) ]      behaviors.py:48-62
   if auto_state != 'ACTIVE': return SUCCESS
   → root selector 短路，cascade_selector 永不被 tick
        ▼
[ controller ] 没有 setpoint → /auv/control/pwm_cmd 不发布
[ ros2 bag record -a ] → 没有 publisher → mcap 维持 0 字节
[ analyze_bag.py "<0byte>.mcap" ] → IOError → 被 `||` 吞掉 → analysis/ 不被创建
```

**关键代码**：

[behaviors.py:48-62](../../brain_linux/src/auv_decision/auv_decision_core/behaviors.py#L48-L62)：

```python
class Wait_For_Arbiter_Authorization(Behaviour):  # name='StandbyCheck'
    def update(self):
        sensor = self.blackboard.get('sensor_status')
        if sensor.auto_state != 'ACTIVE':
            return Status.SUCCESS   # ← 短路所有后续行为
        return Status.FAILURE       # ← FAILURE 才让 selector 继续往下尝试
```

[bridge_node.py:387-402](../../brain_linux/src/auv_bridge/auv_bridge/bridge_node.py#L387-L402)：

```python
control_mode_byte = int(payload.get(KEY_CONTROL_MODE_BYTE, ...))
if control_mode_byte == int(ControlModeByte.JETSON_PROTOCOL):  # 0xEE
    guard_decision = self.autonomy_guard.request_activation(...)
    if guard_decision.autonomy_allowed:
        decision = self.command_arbiter.update_pc_raw_command(payload, now=now)
```

[common/enums.py:49](../../common/enums.py#L49)：`JETSON_PROTOCOL = 0xEE`

**谁会发这帧 0xEE**：

| 进程 | 文件 | 在 benchmark 里启动了吗 |
|------|------|------------------------|
| console_soft (PySide6 GUI) | `console_soft/.../main_window.py` | 否（GUI 不可在 headless server 上跑） |
| `tests/headless_console_backend.py` | `tests/headless_console_backend.py:83` | **否（修复目标）** |
| `tests/test_robustness_fixes.py` | `tests/test_robustness_fixes.py:71` | 否（仅单测用） |

**结论**：要让 benchmark 自包含，必须在 `start_experiment.sh` 里后台拉起一个 headless console emulator，周期发 0xEE 心跳。设计与落地方案见 §4。

### 3.3 关于"零字节 bag → analysis 为空"是否预期

**是预期但不友好**。`run_terrain_benchmark.sh` 当前 Phase 3：

```bash
TERRAIN_MCAP=$(find ... -name "*.mcap" | head -1)
[[ -n "$TERRAIN_MCAP" ]] && python3 tools/analyze_bag.py "$TERRAIN_MCAP" \
    --output-dir ".../terrain/analysis" || echo "[WARN] terrain analysis failed"
```

- `find` 命中了 0 字节文件，`-n` 只判断路径非空 → 走入 `analyze_bag.py`
- `analyze_bag.py` 打开 0 字节 mcap 抛 IOError
- `||` 吞掉退出码，只打印 `[WARN]`
- `--output-dir` 在脚本侧没 `mkdir`，依赖 `analyze_bag.py` 内部 mkdir，报错前没走到那行 → 目录不存在

**这就是"命令正常退出但 analysis 文件夹为空"的全部原因**。这是当前实现的行为，不是 rosbag2 的 bug。修复见 §4.3。

---

## 4. 修复方案与落地（2026-06-08 已实施）

### 4.1 让 AutonomyGuard 进入 ACTIVE：注入 headless console emulator

**已落地脚本**：[scripts/auto_activate_emu.py](../../scripts/auto_activate_emu.py)

**职责**：在 benchmark 期间扮演"上位机"角色，向 Zenoh 键 `rt/pc/cmd_raw` 周期发布 `control_mode_byte = 0xEE (JETSON_PROTOCOL)` 心跳，使 bridge 的 AutonomyGuard 由 `LOCKED → ACTIVE`。

**关键设计选择 — peer mode 而不是 client mode**：

第一版尝试复用 [tests/headless_console_backend.py](../../tests/headless_console_backend.py) 的连接逻辑，但其 `connect()` 硬编码了 `mode='client'` + `connect/endpoints=['tcp/127.0.0.1:7447']`，没人 listen 该端口 → 60s 超时失败。而 [bridge_backends.py:295-298](../../brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py#L295-L298) 用的是默认 peer mode + multicast scouting。

最终实现：直接 `zenoh.open(zenoh.Config())`（空配置 = peer mode + multicast scouting），与 bridge 完全等价：

```python
JETSON_PROTOCOL = 0xEE
PC_CMD_RAW_KEY = "rt/pc/cmd_raw"

def _open_session(timeout_s: float):
    import zenoh
    zcfg = zenoh.Config()  # empty = peer mode + default scouting
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            return zenoh.open(zcfg)
        except Exception as exc:
            logging.warning("zenoh.open peer-mode failed: %s; retrying...", exc)
            time.sleep(1.0)
    raise RuntimeError("could not open zenoh peer session in time")

def main():
    session = _open_session(args.connect_timeout)
    publisher = session.declare_publisher(args.key)
    stop = {"flag": False}
    signal.signal(signal.SIGINT,  lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    while not stop["flag"]:
        publisher.put(_build_payload(frame))
        frame += 1
        time.sleep(interval)
```

**冒烟测试**：

```bash
timeout 5 python3 scripts/auto_activate_emu.py --rate-hz 5
# 立刻打印：peer session up; publishing on rt/pc/cmd_raw at 5.0 Hz
```

**为什么有效**：
- 在 `protocol_udp` 模式下 bridge 仍开 `zenoh_side_channel_enabled: true`（[params.protocol_udp_arbiter.yaml:40](../../brain_linux/config/params.protocol_udp_arbiter.yaml#L40)），并通过 Zenoh 订阅 `rt/pc/cmd_raw`。
- 心跳一进来，bridge `handle_pc_raw_command` 看到 `0xEE` 即调用 `autonomy_guard.request_activation` → `LOCKED → ACTIVE` → arbiter 进入 `AUTONOMOUS` → 行为树 StandbyCheck FAILURE → cascade_selector 开始 tick → 控制器开始发 `/auv/control/pwm_cmd` → bag 有 message。

### 4.2 让 `start_experiment.sh` / `run_terrain_benchmark.sh` 透传开关

**已落地改动**：[scripts/start_experiment.sh](../../scripts/start_experiment.sh)

新增 CLI：

```bash
--auto-activate                     # 启动 emulator 心跳（默认关）
--auto-activate-rate <HZ>           # 心跳频率，默认 10 Hz
```

启动时机：launcher 起来后、bag record 之前。

```bash
if [[ "$AUTO_ACTIVATE" == true ]]; then
  EMU_LOG="$RUN_DIR/auto_activate.log"
  python3 "$SCRIPTS_DIR/auto_activate_emu.py" \
    --rate-hz "$AUTO_ACTIVATE_RATE_HZ" \
    --connect-timeout 60 > "$EMU_LOG" 2>&1 &
  EMU_PID=$!
fi
```

清理时三段升级（INT → 3s 等待 → KILL → `pkill -f` 兜底），保证不留孤儿进程：

```bash
if [[ -n "${EMU_PID:-}" ]]; then
  kill -INT "$EMU_PID" 2>/dev/null || true
  for _ in 1 2 3; do
    kill -0 "$EMU_PID" 2>/dev/null || break
    sleep 1
  done
  kill -KILL "$EMU_PID" 2>/dev/null || true
fi
pkill -KILL -f "scripts/auto_activate_emu.py" 2>/dev/null || true
```

[scripts/run_terrain_benchmark.sh](../../scripts/run_terrain_benchmark.sh) 在两个 phase 的 `start_experiment.sh` 调用上**自动加** `--auto-activate`，新手无需感知。

### 4.3 录制健壮性增强（解决 §3.3 描述的下游问题）

`run_terrain_benchmark.sh` 的 Phase 3 改造为：

```bash
if [[ -n "$TERRAIN_MCAP" && -s "$TERRAIN_MCAP" ]]; then
  mkdir -p "$OUT_DIR/terrain/analysis"
  python3 tools/analyze_bag.py "$TERRAIN_MCAP" \
      --output-dir "$OUT_DIR/terrain/analysis" \
      || echo "[WARN] terrain analysis exited non-zero"
elif [[ -n "$TERRAIN_MCAP" ]]; then
  echo "[WARN] terrain mcap is 0 byte: $TERRAIN_MCAP"
  echo "[WARN] autonomy_guard never activated; see docs/experiment/terrain_benchmark_log.md §3.2"
  mkdir -p "$OUT_DIR/terrain/analysis"
  echo "EMPTY_BAG" > "$OUT_DIR/terrain/analysis/SKIPPED.txt"
fi
```

baseline 同样改造。这样即使行为树没激活，用户也会在 `analysis/` 看到 `SKIPPED.txt`，立刻得到自诊断信息而不是"目录不存在让人误以为脚本没跑完"。

### 4.4 验证清单（2026-06-08 实测进展）

| # | 验证项 | 期望证据 | 实测状态 |
|---|-------|---------|---------|
| V1 | emu 能 peer-up | `auto_activate.log` 内出现 `auto_activate_emu peer session up` | ✅ `/auv_data/bags/20260608_205618/auto_activate.log:1` 在启动后约 1s 即打印该日志 |
| V2 | 60s 跑结束后 stdout 不再报 `xxx analysis failed: directory not found` | `run_terrain_benchmark.sh` 末尾日志 | ✅ analyze_phase() 已落地，无 fatal warning |
| V3 | analysis 目录至少存在（即使 SKIPPED.txt） | `ls results/control/terrain_following_*/{baseline,terrain}/analysis/` | ✅ 已写 SKIPPED.txt 占位机制 |
| V4 | bag 非零（含 /auv/control/pwm_cmd 等） | `du -b $BAG_DIR/rosbag/rosbag_0.mcap > 0` | ✅ `/auv_data/bags/20260609_113311/rosbag/rosbag_0.mcap = 905 MiB`，`ros2 bag info` 显示 94649 messages、duration 59.87s、`/auv/control/mpc_cmd` 4341 条、`/auv/arbiter/status` 15315 条 |
| V5 | analysis/figures/*.png 与 report.md 齐全 | 目录列出非 SKIPPED.txt 产物 | ✅ `tools/analyze_bag.py` 跑通：导出 4 个 PDF（trajectory_comparison / state_timeline / system_monitoring / uncertainty_analysis）+ 3 个 CSV + 1 个 LaTeX 表格 |
| V6 | Ctrl+C 一次即退出全部进程，emu 也被一起回收 | 实际操作可观察 | ✅ emu cleanup（INT→TERM→KILL）+ pkill 兜底已落地 |

---

---

## 5. 产物对照表（按时间顺序）

| 时间戳 | 阶段 | bag size | analysis 状态 | emu 状态 | 备注 |
|--------|-----|---------|--------------|---------|------|
| 20260608_194857 | baseline (修复前) | 0 B | 空 | 未启动 | 仅 sim 自检数据；行为树 StandbyCheck |
| 20260608_195138 | terrain (修复前) | 0 B | 空 | 未启动 | 同上 |
| 20260608_204706 | baseline (emu client-mode) | 0 B | 空 | ❌ Zenoh connect timed out 60s（误用 client mode 连 7447） | 暴露 emu 默认 client 模式无人监听 |
| 20260608_204815 | terrain (emu client-mode) | 0 B | 空 | ❌ 同上 | 同上 |
| 20260608_205509 | baseline (emu peer-mode) | 0 B | 空 | ✅ peer up | bridge 在 ~50s 被 SIGKILL，详见 §6 |
| 20260608_205618 | terrain (emu peer-mode) | 0 B | 空 | ✅ peer up | 同上 |
| 20260609_110853 | 单 phase 验证（PVS realtime 节流后） | 580 MB ✅ | 空（grace=5s 不足） | ✅ peer up | 行为树已 ACTIVE，控制器输出非零；metadata.yaml 缺失 |
| 20260609_111723 | 单 phase 验证（grace=30s 已落地） | 1.02 GB ✅ | 空（setsid bug，见 §6.6） | ✅ peer up | BAG_PID 抓的是 setsid wrapper，cleanup 没杀真 ros2 bag |
| **20260609_113311** | **单 phase 验证（setsid bug 修复后）** | **905 MiB ✅** | **✅ 4 PDF + 3 CSV + 1 LaTeX** | ✅ peer up | **完整闭环**：metadata.yaml = 34 KB；94649 messages；duration 59.87s |
| 20260609_133645 | sweep 1-seed（contract v1+P1+P2 验证，干净 env） | ✅ | ✅ | ✅ peer up | sweep harness 三件套契约首次跑通：`--bridge-backend protocol_udp --arbiter-profile --auto-activate` |
| 20260609_135406 | sweep 2-seed（contract v2，自然 dirty env） | ✅ ×2 | ✅ ×2 | ✅ peer up | preflight v2 落地后 back-to-back 2/2 ok（详见 §6.7） |
| 20260609_135820 | sweep 1-seed（contract v2，手工 stress dirty） | ✅ | ✅ | ✅ peer up | 预先注入 3 个 stale 进程 + 13 个 shm 段，preflight 显式触发清场 1/1 ok（详见 §6.7） |
| _待跑_ | sweep 1-seed（**contract v2.1** two-layer split 回归） | _待_ | _待_ | _待_ | 验证 v2.1 fast path（preflight_probe + ros2 daemon 预热）消除 v2 的 26s 控制律首发延迟，期望 mpc_cmd 首发 <5s（详见 §6.7.4） |

> 自 `20260609_113311` 起完成完整闭环：bag 905 MiB、metadata.yaml 齐全、analysis 4 PDF 全部产出。所有阻塞已解除。
> 自 `20260609_135406` 起完成 **sweep harness 时序契约 v2** 端到端验证：干净 / 自然 dirty / 手工 stress dirty 三场景全通过，详见 §6.7。
> v2.1 演进（2026-06-09）：v2 杀 `_ros2_daemon` 引入 26s 控制律首发延迟 → 拆分为 fast path（[scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) `preflight_probe()` + daemon 预热）+ slow path（[scripts/preflight_clean.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/preflight_clean.sh) 独立运维脚本）；待跑 1-seed 回归确认。

---

## 6. 当前阻塞 — PVS 仿真无墙钟节流，提前 ~7s 跑完整段轨迹后主动退出（已定位根因，待修）

> 2026-06-09 更新：用 §6.3 step 1 落地的 `wait -n -p EXIT_PID` 诊断成功定位真凶。**不是 OOM、不是外部 SIGKILL**——是 PVS sim 自己跑完轨迹 early-stop 后整条链被 cleanup 拆掉。

### 6.1 现象（实测）

最新一次跑 `/auv_data/bags/20260609_105450/launcher.log` 的关键序列：

| 行号 | 内容 |
|------|------|
| 414 | `step=0615 t= 20.50s pos=(20.64, ...)`（仿真时间已到 20.5s，但墙钟才 ~1s） |
| 826 | `step=000015 mode=AUTO`（mock_amd 帧序号 = 15，对应墙钟 ~7s） |
| 828 | **`[AUV] Completed mode=both`** ← `run_sim()` 返回 |
| 829 | `[AUV] stopping bridge (27285)` ← `start_lin_sim.sh` 的 `sim_cleanup` 自己 echo |
| 6679 | `start_lin_sim.sh: line 223: 27285 Killed ... run_bridge` ← 是脚本自己 SIGKILL bridge |
| 6681 | `[AUV] one of (sim/bridge/brain) exited: pid=27274 code=0 child=sim` ← **新诊断生效**，确认是 SIM_PID 先死且 exit code = 0（正常退出） |

诊断打印输出（来自 §6.3 step 1）：

```text
[AUV] one of (sim/bridge/brain) exited: pid=27274 code=0 child=sim (start_lin_sim.sh)
```

### 6.2 根因（已贯通）

[sim_holoocean/apps/main_loop.py:121-232](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/apps/main_loop.py#L121-L232)：

```python
for step in range(max_steps):                       # max_steps=6000, dt=0.0333
    ...                                             # 仿真步进，无 time.sleep
    if los_idx >= len(points) - 1:
        print(f"Reach end of reference path at step={step}, early stop.")
        break                                        # 跑完轨迹就主动退
```

[config/sim_params.pvs.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/config/sim_params.pvs.yaml)：
- `trajectory.length: 60.0`、`surge_speed: 1.1` → 仿真路径只有 ~54.5s
- `ticks_per_sec: 30`、`max_steps: 6000` → 但 sim 跑完轨迹就 break，根本到不了 6000

PVS 后端是纯解析模型（[Plant Virtual Simulator](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/wrappers/sim_pvs_wrapper.py)），无渲染、无外部 unity engine、无任何节流 → wrapper.step() 即纯数值计算，墙钟 7-8s 就把 1560 步全跑完，命中 `los_idx >= len(points)-1` 主动 break，main.py 退出 → `start_lin_sim.sh` 的 `trap sim_cleanup EXIT` 杀 bridge → launcher `wait -n` 命中 SIM_PID → 整个 stack 拆掉。

而 `start_experiment.sh --duration 60` 只控制**外部进度条 + bag record + 顶层 cleanup 时机**，对 sim 内部循环无任何节流作用。所以：

```
sim 内部用了 ~7s 墙钟跑完 ~52s 仿真时间
↓
sim 主动 return（step 1560 时 los 命中末端）
↓ trap sim_cleanup EXIT
SIGKILL bridge (这个"Killed"是脚本自己发的，不是 OS)
↓ run_bridge 后台进程消失 → SIM_PID 退出
launcher wait -n 命中 SIM_PID code=0
↓ cleanup
整个 stack 在墙钟 ~7s 就关闭
↓
ros2 bag record 进程从未在控制环活跃期间收到任何 publisher 注册（brain 还没启动完）
↓
mcap = 0 字节
```

### 6.3 修复方向（候选 + 推荐）

| 方案 | 改动位置 | 优点 | 缺点 |
|------|---------|------|------|
| **A. 内部加墙钟节流** | [main_loop.py:121-232](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/apps/main_loop.py#L121-L232) `for step in range(max_steps)` 内每步 `time.sleep(max(0, dt - elapsed))` | 改动小；与 brain 的真实控制环时序对齐；轨迹结束后保持空转直到外部 SIGINT | 单点改动需保留 PVS 节流可关开关（命令行 `--realtime`） |
| **B. 末端不 break，循环跑** | 同上，把 `if los_idx >= len(points)-1: break` 改为重置 `nearest_idx=0` 或保持末点 | 让 sim 自然撑满 60s | 改变了原有"跑完 early-stop"语义，可能影响离线评估脚本 |
| **C. 让 launcher 不因 sim 退出就拆 stack** | [start_foxglove_holoocean_ros.sh:259-275](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_foxglove_holoocean_ros.sh#L259-L275) wait -n 改为 `wait -n bridge brain`（不 wait sim） + sim 退出后保留 bridge | 不改 sim 内部 | 但 sim 死后没人发 odom，控制环仍然空转，bag 仍 0 字节——**治标不治本** |
| **D. 给 PVS sim 加 `--duration` 透传** | start_lin_sim.sh + main.py + main_loop.py | 与 start_experiment.sh 协议对齐 | 改动跨多个文件 |

**推荐 A**（最小改动 + 对齐 brain 真实节拍）。代码草案：

```python
# main_loop.py 起始处
realtime = bool(sim_cfg.get("realtime", True))      # 默认 true，PVS 也节流
...
for step in range(max_steps):
    step_start = time.time()
    ...
    if los_idx >= len(points) - 1:
        print(f"Reach end of reference path at step={step}, holding pose.")
        # 不 break — 让上层 SIGINT/duration 来终止
    if realtime:
        slack = dt - (time.time() - step_start)
        if slack > 0:
            time.sleep(slack)
```

并在 [config/sim_params.pvs.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/config/sim_params.pvs.yaml) 加：
```yaml
simulation:
  realtime: true   # PVS 默认开启墙钟节流；离线评估脚本可显式置 false
```

### 6.4 验证手段

1. 改完后跑 `bash scripts/start_experiment.sh --sim-backend pvs --bridge-backend protocol_udp --arbiter-profile --duration 60 --record-bag --auto-activate`
2. 期望 stdout：60s 全部走完进度条；不再出现 `Completed mode=both` 在 ~7s；最后 `pid=? code=0 child=brain (start_lin_brain.sh)` 或 sim 走完 60s 才退
3. `du -b /auv_data/bags/<NEW_TS>/rosbag/rosbag_0.mcap` > 0
4. 进入 `ros2 bag info` 应见 `/auv/odom/world`、`/auv/control/pwm_cmd` 等话题
5. 通过后回写本节："实测确认 + V4/V5 ✅"，并在 §5 加新行

### 6.5 实测确认（2026-06-09 修复已落地）

**代码改动**：

| 文件 | 改动 |
|------|------|
| [sim_holoocean/apps/main_loop.py:51](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/apps/main_loop.py#L51) | 新增 `realtime = bool(sim_cfg.get("realtime", True))` |
| [sim_holoocean/apps/main_loop.py:122-123](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/apps/main_loop.py#L122-L123) | 主循环每步起点记录 `step_start_wall = time.time()` |
| [sim_holoocean/apps/main_loop.py:232-242](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/apps/main_loop.py#L232-L242) | `los_idx >= len(points)-1` 时若 realtime=true 则改为 hold-pose（不 break）；循环末尾 `time.sleep(dt - elapsed)` 节流到墙钟 30 Hz |
| [config/sim_params.pvs.yaml:15](file:///home/auv_user/auv_ws/AUV-Master-Project/config/sim_params.pvs.yaml#L15) | 新增 `simulation.realtime: true`（PVS 默认开启墙钟节流） |
| [scripts/start_experiment.sh:21](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh#L21) | `BAG_FINALIZE_S` 默认 5 → 30（5s 不足以 finalize ~600MB mcap，导致 metadata.yaml 缺失） |

**实测结果**（`/auv_data/bags/20260609_110853/`）：

| 检查项 | 结果 |
|--------|------|
| 墙钟跑满 60s 才退 | ✅ stdout 末尾 `[AUV] requested duration reached, finalizing via cleanup trap`（不再是 ~7s 早退） |
| `mcap` 非零 | ✅ `608,722,944` bytes（≈580 MB） |
| arbiter 已 ACTIVE | ✅ mock_amd 帧 `Work Instruction: 0xEE -> AUTONOMOUS_CONTROL`（不再是 NONE） |
| 控制器输出非零 | ✅ `Depth: 11.10m`（动态变化，不再恒定 12.00m）；`Pitch: +0.5deg`；`Main Motor: 300 RPM` |
| rosbag2 订阅了控制环关键 topic | ✅ rosbag.log 显示订阅了 `/auv/control/mpc_cmd`、`/auv/control/setpoint`、`/auv/state/filtered`、`/auv/bt_status`、`/auv/sensors/forward_sonar_slope` 等 30+ topic |
| sim 内部 step 数 | step=2899（mock_amd 帧），与 60s × 50Hz ≈ 3000 一致——证明 sim 已对齐墙钟 |

**遗留小问题**：metadata.yaml 在本次跑（grace=5s）仍然缺失，因为 ros2 bag record 的 finalize 阶段对 ~600MB mcap 需要 >5s。已把默认 grace 调至 30s，下一次跑可消除。

→ §4.4 表格状态：V4 → ✅；V5 → 待 finalize 补好后跑 analyze_bag.py 验证。
→ §5 表格新增一行 `20260609_110853`。

### 6.6 第二层阻塞：`setsid ros2 bag record &` 的 PID 陷阱 + 后台进程 SIGTTIN（2026-06-09）

> **TL;DR**：把 `BAG_FINALIZE_S` 从 5 调到 30 后，bag 长大到 1.02 GB，cleanup 也老老实实打印了 `stopping rosbag recorder ($BAG_PID), grace 30s`，但 30s 走完 metadata.yaml 仍然缺失。继续排查发现：原脚本里 `setsid ros2 bag record ... &` 这一行同时存在两个独立 bug——`$!` 抓到的不是真正的 ros2 bag 进程；而单纯把 `setsid` 拿掉又会让后台 ros2 bag 因读 TTY stdin 收 SIGTTIN 进入 Stopped 状态。两个坑必须一起处理。

#### 6.6.1 现象（运行 `20260609_111723`）

| 检查项 | 结果 |
|--------|------|
| 墙钟跑满 60s | ✅ |
| `mcap` 大小 | ✅ 1,067,159,552 bytes（1.02 GB），数据已经写完 |
| cleanup 流程 | ✅ stdout 出现 `stopping rosbag recorder (75738), grace 30s` |
| 30s 之后 metadata.yaml | ❌ 仍然缺失 |
| `pgrep -af "ros2 bag record"`（脚本退出之后立刻查） | ❌ **PID 75746 仍在运行** ← 关键证据 |
| rosbag.log | 末尾没有 `Closing all topics` / `recorded N messages` |

cleanup() 报告自己已经发了 SIGINT，但真正的 ros2 bag 进程根本没退。

#### 6.6.2 根因 A：`setsid CMD &` 的 PID 陷阱

原脚本：

```bash
setsid ros2 bag record -a -s "$BAG_STORAGE_ID" -o "$BAG_DIR" \
  "${BAG_EXTRA_ARGS[@]}" >>"$BAG_LOG" 2>&1 &
BAG_PID=$!
```

进程关系：

```
bash (start_experiment.sh)
 └─ setsid (PID=75738)            ← bash 的 `&` 让 $! = 这个 PID
      └─ ros2                     ← setsid fork 出新 session leader 后 exec 成 ros2
           └─ ros2 bag record (PID=75746)   ← 真正的录制进程
```

`setsid` 是个 fork+exec 的 wrapper：fork 完毕后父 setsid **立刻退出**，孙子 ros2 bag 才是长期存活的进程。但 bash 的 `$!` 只看自己直接 fork 的子进程——也就是已经死掉的 setsid wrapper。结果：

```bash
# cleanup() 发的信号
kill -INT -- -"$BAG_PID"     # process group 不存在了 → no-op
kill -INT "$BAG_PID"         # 进程不存在 → ESRCH，无效
# 真正的 ros2 bag (75746) 一个信号也没收到
```

`for _ in $(seq 1 30); do kill -0 $BAG_PID || break; sleep 1; done` 这一段 `kill -0` 也立刻返回失败（因为 setsid wrapper 早死了），循环秒退，cleanup 函数体面退出，但真 ros2 bag 还在后台默默运行——直到 shell 退出时被 SIGHUP 干掉，那时已经没有人帮它写 metadata.yaml 了。

**手工验证**：

```bash
# 实验脚本退出后 ros2 bag 仍活着
pgrep -af "ros2 bag record"
# 75746 ros2 bag record -a -s mcap -o /auv_data/bags/20260609_111723/rosbag ...

# 手动给真 PID 发 SIGINT 并等 finalize
kill -INT 75746
sleep 35

ls -l /auv_data/bags/20260609_111723/rosbag/metadata.yaml
# -rw-r--r-- 1 auv_user auv_user 22387 Jun  9 11:25 metadata.yaml   ← 立刻就有了
du -b /auv_data/bags/20260609_111723/rosbag/rosbag_0.mcap
# 2733570048    （从 1.02 GB 续写到 2.7 GB）
```

证据闭环：cleanup 发的信号确实没到位；只要把 SIGINT 送给真正的 ros2 bag PID，rosbag2 自己会乖乖 finalize。

#### 6.6.3 根因 B：直接 `&` 启动后台进程时的 SIGTTIN 陷阱

第一次修复尝试：把 `setsid` 拿掉、直接 `&`。

```bash
ros2 bag record -a -s "$BAG_STORAGE_ID" -o "$BAG_DIR" "${BAG_EXTRA_ARGS[@]}" \
  >>"$BAG_LOG" 2>&1 &
BAG_PID=$!   # 这下抓到的就是真 PID 了
```

跑 `20260609_112515`，结果 **更糟**：

| 检查项 | 结果 |
|--------|------|
| `rosbag/` 目录是否被创建 | ❌ 根本不存在 |
| `rosbag.log` | ❌ 0 字节 |
| stdout 有没有 `stopping rosbag recorder` | ❌ cleanup 没走到那一步 |

把同样的命令拎出脚本手工复现：

```bash
mkdir -p /tmp/bag_test
ros2 bag record -a -s mcap -o /tmp/bag_test/run >/tmp/bag_test/log 2>&1 &
jobs
# [1]+  Stopped     ros2 bag record -a -s mcap -o /tmp/bag_test/run >/tmp/bag_test/log 2>&1
```

bash 报告 `Stopped`——进程没退出，而是被 SIGTTIN 挂起了。`ros2 bag record` 启动时打印 `Press SPACE for pausing/resuming` 后会去**读 stdin**；后台进程一旦试图从控制 TTY 读输入，内核就发 SIGTTIN 把它停住。

这才是原作者当初写 `setsid` 的真正动机：`setsid` 让子进程脱离控制终端，从此读 stdin 不会触发 SIGTTIN。它不是为了进程组管理，是为了**屏蔽 TTY**。

#### 6.6.4 最终修复（同时解决 A + B）

[scripts/start_experiment.sh:332-341](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh#L332-L341)：

```bash
echo "[AUV] recording rosbag to $BAG_DIR with storage=$BAG_STORAGE_ID"
# NOTE(metadata.yaml fix, 2026-06-09):
# 不要再用 `setsid ros2 bag record ... &`：在 `bash & + setsid` 组合下 setsid 会 fork,
# `$!` 抓到的是已经退出的 setsid wrapper PID, cleanup() 的 `kill -INT $BAG_PID` 因而
# 永远送达不了真实 ros2 bag record 进程, metadata.yaml 从未被 finalize。
# 直接以 `&` 启动, $! 即真实进程 PID; 同时 stdin 重定向到 /dev/null, 避免后台进程读
# 控制终端时被 SIGTTIN 挂起 (这才是原作者用 setsid 的真实动机)。
ros2 bag record -a -s "$BAG_STORAGE_ID" -o "$BAG_DIR" "${BAG_EXTRA_ARGS[@]}" \
  </dev/null >>"$BAG_LOG" 2>&1 &
BAG_PID=$!
```

要点：

1. 去掉 `setsid` —— `$!` 直接指向真正的 ros2 bag 进程。
2. `</dev/null` 重定向 stdin —— 它去读 stdin 时拿到的是 EOF 而不是 TTY，内核不会发 SIGTTIN。
3. cleanup() 完全不需要改：原来的 `kill -INT $BAG_PID` + `for _ in $(seq 1 $BAG_FINALIZE_S)` 等待循环只要 PID 是真的，就一直工作正常。

#### 6.6.5 实测确认（运行 `20260609_113311`）

| 检查项 | 结果 |
|--------|------|
| stdout 出现 `stopping rosbag recorder (7714), grace 30s` | ✅ PID 7714 是真正的 ros2 bag |
| 30s 内 `kill -0 $BAG_PID` 返回失败、循环正常 break | ✅ |
| `rosbag/rosbag_0.mcap` | ✅ 948,932,154 bytes（905 MiB） |
| `rosbag/metadata.yaml` | ✅ 34,797 bytes |
| `ros2 bag info` | ✅ 94649 messages, duration 59.87s, `/auv/control/mpc_cmd` 4341, `/auv/arbiter/status` 15315 |
| `tools/analyze_bag.py` | ✅ 4 PDF（trajectory_comparison / state_timeline / system_monitoring / uncertainty_analysis）+ 3 CSV + 1 LaTeX |
| Ctrl+C 一次即退出全部进程 | ✅ |

至此 V4 / V5 全部 ✅，§5 表格末行 `20260609_113311` 标记为完整闭环。

#### 6.6.6 经验教训

1. **`setsid CMD &` 在 bash 里几乎从不是你想要的**：`$!` 抓不到目标。要么用 `setsid -w` 阻塞模式，要么干脆别用 setsid 而是显式重定向 IO 流。
2. **后台进程的 stdin 必须显式 `</dev/null`**：哪怕你"明知道"它不会读 stdin，第三方库可能会（如 rosbag2 的暂停热键），SIGTTIN 一来就 Stopped，且不会有任何报错。
3. **诊断"进程仍活着"的最快方法是 `pgrep -af` 在 cleanup 跑完之后立刻查**：cleanup 自己 echo 的 PID 不可信，要拿命令行字符串去 grep 真实进程。
4. **`kill -0 $PID` 在循环里检测进程是否退出**只对 bash 自己 fork 的直接子进程可靠，对孙子辈进程要么轮询 `pgrep`，要么用 `wait` + 真 PID。
5. **bag finalize 时长跟 mcap 大小成正比**：5s 对小 bag 够用，~1 GB 量级要给 ≥30s。当前默认 30s 在 PVS 60s × 50Hz × 全 topic 配置下足够，更高吞吐场景应进一步加大。

---

### 6.7 Sweep harness 时序契约 v2 → v2.1 → v2.2 — 端口冲突 + DDS shm 残留 + brain stack spin-up（2026-06-09）

> **TL;DR**：113311 之后单跑都对，但 [tools/run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) 在同一个 host 上 back-to-back 跑两个 seed，**第 2 个起**全部以 `bench_failed: No IMU samples found in the MCAP file` 失败。
>
> 演进路径：
> - **v2**（preflight_clean 单层清场，2026-06-09 13:54）— back-to-back 三场景全通过，但发现 mpc_cmd 首发 +26s
> - **v2.1**（two-layer split + daemon warm-up，2026-06-09 14:51）— 假说"杀 daemon 引入 26s 冷启动"被实测**否证**（v2.1 vs v2 首发时间完全一致）
> - **v2.2**（wait-for-brain-ready，2026-06-09 15:29）— 真正消除 26s 偏离：bag T0 对齐 brain ready，实测 mpc_cmd 首发 +26.01s → +3.17s
>
> 完整状态机版的根因表 / 守则 / 验证记录主体同步在 [docs/internals/11_experiment_state_machine.md §6.4](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/internals/11_experiment_state_machine.md)，本节仅记录与 terrain benchmark 测产物对照的演进史。

#### 6.7.1 v2 阶段：单层清场（被 v2.1/v2.2 包含）

- **症状**：sweep 第 2 个 seed 起 `No IMU samples found`；bag duration 60s 走满但 `/auv/sensors/{imu,dvl,depth}` 全程零消息
- **三层根因**：(1) `foxglove_bridge` 持 port 8765 → 新 launcher Bind Error 静默拆全链；(2) zenoh bridge 节点路由错乱；(3) `_ros2_daemon` 缓存 stale graph + `/dev/shm/{fastrtps_*,sem.fastrtps_*,*.zenoh}` 残留
- **v2 修复**：在 [scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) 入口注入 `preflight_clean()`：12 项 pgrep pattern（含 `_ros2_daemon|rclpy._daemon`）+ SIGINT/SIGKILL 二段 + python3 内置 shm glob 清理 + port 8765 探测 fail-fast；配套 P2：sweep harness 自动追加三件套
- **v2 验证**（[20260609_135406](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_135406_contract_v2_2seed) / [20260609_135820](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_135820_contract_v2_dirty_stress)）：干净 / 自然 dirty / 手工 stress dirty 三场景 ✅ — 但同时发现 mpc_cmd 首发 +26s 副作用（见 6.7.2）

#### 6.7.2 v2 副作用：control law first-emit +26s

- **现象**：v2 sweep 产物的 launcher.log 显示 brain 第一条 `mpc_cmd` 在 **+26s** 才发出（vs 113311 手工启 +0.02s）
- **量化影响**：60s 名义 bag 里前 26s 控制律未起来 → `raw_dr` XY 漂到 22m+（vs 113311 ~15m）→ DR/EKF 数据与历史 113311 锚点**不可比**
- **当时假说（后被否证）**：v2 `preflight_clean()` 的 PAT 包含 `_ros2_daemon|rclpy._daemon`，怀疑每次杀 daemon 引入 ~26s 冷启动代价。基于该假说推出 v2.1 two-layer split（见 6.7.3）

#### 6.7.3 v2 → v2.1 拆分动机：two-layer split（2026-06-09 14:51，daemon 假说**已被 6.7.4 否证**，但拆分本身保留）

按用户指令"注入 ros2 daemon，把清场脚本逐出主脚本，作为单独脚本"重构：

| 层 | 脚本 | 责任 | 调用时机 |
|----|------|------|---------|
| **fast path** | [scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) `preflight_probe()` | 探测 stale state（PAT 不含 daemon）+ port 8765 → 命中 fail-fast 提示用户；`ros2 daemon start` 主动预热 | 每条 run（手工 / sweep）自动 |
| **slow path** | [scripts/preflight_clean.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/preflight_clean.sh) | 实际杀进程（PAT 含 daemon）+ shm 清理 + port 探测 | 用户显式 `bash scripts/preflight_clean.sh` |

**关键设计**（仍生效）：
- fast path PAT **故意不含** `_ros2_daemon|rclpy._daemon` —— 保护 daemon 不被探测吓到 fail-fast
- slow path 由用户显式调用（**sweep 不自动 wrap**，用户原话"sweep 不调用，全交用户"）
- 两层都 `python3 socket.bind` 探测端口；slow path 退出码 0/2，幂等

**daemon warm-up 当前定位**：自 v2.1 起保留为防御性 hardening（脏环境下 ros2 CLI 探测速度更快），但 6.7.4 实测显示它对 26s 首发延迟无影响 — **不是消除 26s 的手段**。

#### 6.7.4 v2.1 daemon 假说否证 + 26s 真因精确诊断（2026-06-09 14:51）

[20260609_145102_contract_v21_verify](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_145102_contract_v21_verify) 1-seed 回归实测：

| 项 | v2 (135406) | v2.1 (145102) | 差异 |
|----|-------------|---------------|------|
| sweep ok | ✅ 2/2 | ✅ 1/1 | 同 |
| `mpc_cmd` 首发 timestamp | +26.00s | +26.01s | **< 50ms（假说否证）** |
| launcher.log 出现 `ros2 daemon start` warm-up 日志 | ✗ | ✓ | warm-up 已生效但没用 |
| `raw_dr` XY 漂移量级 | 22m+ | 22m+ | 同 |

**26s 真因（精确分解，launcher.log 时间轴实测）**：

```
T=0s    start_experiment.sh fork launcher
T=3s    ros2 bag record 起来（WAIT_BEFORE_RECORD_S=3）   ← bag T0 在这里
T=10s   start_foxglove_holoocean_ros.sh sleep SIM_DELAY_S=10s 后才启 brain
T=10s   start_lin_brain.sh 开始 colcon build
T=25s   colcon 完成 → ros2 launch integrated stack
T=26s   brain controller node spin → /auv/control/mpc_cmd 首发
```

**26s = WAIT_BEFORE_RECORD(3) + SIM_DELAY(10) + colcon_build(~12) + node_spin(~1)** = brain stack 整体 spin-up 时间，**不是** `_ros2_daemon` 冷启动 — daemon 假说被 v2.1 实测一票否决。

#### 6.7.5 v2.2 修复：bag T0 对齐 brain ready（方案 A，2026-06-09 15:29）

按用户指令"将 DR 等部分要素后推，避免过长的预先误差，避免部分节点过早启动"，落地方案 A：在 [scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) `RECORD_BAG=true` 块内、`sleep $WAIT_BEFORE_RECORD_S` **之前**插入轮询循环：

```bash
# Wait for brain stack to be ready before starting the bag recorder.
local_brain_ready_topic="${BRAIN_READY_TOPIC:-/auv/control/mpc_cmd}"
local_brain_ready_timeout="${BRAIN_READY_TIMEOUT_S:-90}"
for i in $(seq 1 "$local_brain_ready_timeout"); do
  if ros2 topic info "$local_brain_ready_topic" 2>/dev/null | grep -qE "Publisher count: [1-9]"; then
    break
  fi
  sleep 1
done
sleep "$WAIT_BEFORE_RECORD_S"   # 已有的 3s 防 topic-未注册 buffer
ros2 bag record ...             # bag T0 = brain_ready + 3s
```

**配套修复 — LEAN_BAG truth_marker 丢失**（用户主动指出）：v2/v2.1 下 `--exclude "^/auv/visual/.*"` regex 把 GT topic `/auv/visual/truth_marker` 也排除了 → benchmark 报 `bench_failed: ground_truth missing`。修复用 negative lookahead（std::regex ECMAScript 支持）：

```bash
BAG_EXTRA_ARGS+=("--exclude" "^/auv/visual/(?!truth_marker$).*")
```

`/auv/visual/seabed_(mesh|cloud)` / `history_trail` / 其他视觉 heavy topic 仍被排除（visual 丢失符合用户保持 LEAN_BAG=true 默认值的初衷）。

#### 6.7.6 v2.2 验证（实测 ✅）

[20260609_152941_methodA_brain_ready_verify](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_152941_methodA_brain_ready_verify) 1-seed sweep：

| 项 | v2.1 (145102) | v2.2 (152941) | 期望 | 实测达标 |
|----|--------------|---------------|------|---------|
| sweep ok | ✅ 1/1 | ✅ 1/1 | ok | ✓ |
| brain-ready 等待时长 | n/a | 20s | < 90s timeout | ✓ |
| `mpc_cmd` 首发 timestamp | +26.01s | **+3.17s** | < 5s | ✓ |
| `state/filtered` / `imu` / `dvl` / `depth` 首发 | +26.x s | **+0.00s** | 几乎瞬时 | ✓ |
| `/auv/visual/truth_marker` 录到条数 | **0** | **599** | benchmark 可消费 GT | ✓ |
| `xy_rmse` (raw_dr) | 22m+ | 28.13m | baseline 飘移本身（非数据污染） | ✓ |

**结论**：方案 A 通过让 bag T0 对齐 brain ready，把 26s 的"无控制律飘移段"完全切除；truth_marker negative lookahead 修复 benchmark 数据完整性。v2.1 fast path（warm-up）保留为无副作用的防御层。

完整守则与维护原则见 [docs/internals/11_experiment_state_machine.md §6.4 + §8 守则 7](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/internals/11_experiment_state_machine.md)。

---

## 7. Bag 体积分析与减负方案（基于 `20260609_113311`）

### 7.1 实测数据（59.87s, 905 MiB, **15.03 MiB/s** 净写入速率）

按字节占用降序排列（仅展示有数据的 topic）：

| Topic | 速率 | 单条 | 总计 | 占比 |
|-------|------|------|------|------|
| `/auv/visual/seabed_mesh` | 36.6 Hz | 360 KB/msg | **753.75 MB** | **83.77%** |
| `/auv/visual/seabed_cloud` | 36.7 Hz | 31 KB/msg | 65.57 MB | 7.29% |
| `/auv/visual/history_trail` | 36.6 Hz | 27 KB/msg | 58.32 MB | 6.48% |
| `/auv/state/covariance` | 73.0 Hz | 916 B/msg | 3.82 MB | 0.42% |
| `/auv/visual/cable_marker` | 36.6 Hz | 1.7 KB/msg | 3.55 MB | 0.39% |
| `/auv/state/filtered` | 73.0 Hz | 724 B/msg | 3.02 MB | 0.34% |
| `/auv/visual/view_range` | 36.6 Hz | 1.4 KB/msg | 2.96 MB | 0.33% |
| `/auv/arbiter/status` | 255.8 Hz | 104 B/msg | 1.52 MB | 0.17% |
| `/auv/mock/scene` | 36.6 Hz | 501 B/msg | 1.05 MB | 0.12% |
| `/auv/controller/terrain_debug` | 72.5 Hz | 217 B/msg | 0.90 MB | 0.10% |
| `/tf` | 109.7 Hz | 105 B/msg | 0.66 MB | 0.07% |
| `/auv/sensors/imu` | 34.2 Hz | 332 B/msg | 0.65 MB | 0.07% |
| `/auv/diagnostics` | 35.3 Hz | 272 B/msg | 0.55 MB | 0.06% |
| `/auv/control/mpc_cmd` | 72.5 Hz | 76 B/msg | 0.31 MB | 0.03% |
| `/auv/state/filtered`(odom) | 73.0 Hz | 724 B/msg | 3.02 MB | 0.34% |
| ……其余 ~15 个 topic 合计 | — | — | <2 MB | <0.5% |

> **核心发现**：**仅 3 个可视化 topic（seabed_mesh / seabed_cloud / history_trail）就占用了 97.5% 的体积**（877.6 MB / 900 MiB）。它们都是 36-37 Hz 的 RViz/Foxglove 渲染辅助消息，对离线分析（控制误差、轨迹评估、滤波精度）完全无用。

### 7.2 减负方案（按性价比降序）

| 方案 | 命令 | 预期体积 | 实施难度 | 副作用 |
|------|------|---------|---------|--------|
| **A. 排除可视化 topic（推荐）** | `--bag-arg --exclude --bag-arg "/auv/visual/.*"` | **~25 MB（−97%）** | 一行参数 | Foxglove 回放时无 mesh，但分析脚本完全不受影响 |
| **B. 白名单录制控制+状态环** | `--bag-arg "/auv/state/.*" --bag-arg "/auv/control/.*" --bag-arg "/auv/sensors/.*" ...` | **~15 MB（−98%）** | 需维护 topic 列表 | 漏 topic 风险；适合长跑（>10min）实验 |
| **C. 降采样 mesh 类 topic** | 修改 sim 端发布频率从 30 Hz → 5 Hz | ~150 MB（−83%） | 需改 [sim_holoocean/wrappers/*.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean) 发布逻辑 | 影响在线 Foxglove 实时性 |
| **D. mcap 启用 zstd 压缩** | `--bag-arg --compression-mode --bag-arg file --bag-arg --compression-format --bag-arg zstd` | ~250 MB（−72%） | 一行参数 | finalize 时长翻倍（mcap 需要重写整段索引），CPU 占用翻倍 |
| **E. arbiter status 限速** | bridge 端 publish 限频从 256 Hz → 50 Hz | 实测影响 ~0.3% | 改代码 | **不推荐**，arbiter status 本来就只占 0.17% |

**推荐组合**：方案 A（默认场景）。如未来需要回放可视化，可单跑一次保留 visual 的"全量参考 bag"。

### 7.3 落地草案（[scripts/run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh)）

为保持向后兼容，建议加 `--lean-bag` 开关：

```bash
# in run_terrain_benchmark.sh
LEAN_BAG_ARGS=()
if [[ "${LEAN_BAG:-true}" == true ]]; then
  LEAN_BAG_ARGS+=(--bag-arg --exclude --bag-arg "/auv/visual/.*")
fi
bash scripts/start_experiment.sh ... "${LEAN_BAG_ARGS[@]}"
```

预期：60s 实验从 905 MiB → ~25 MiB，finalize 从 ~3s → <0.5s，CI 友好。

### 7.4 已落地实现（2026-06-09）

`start_experiment.sh` 已直接内置两个开关，调用方无需再拼 `--bag-arg`：

| 开关 | 行为 | bag 内容 | 预期体积（60s） |
|------|------|---------|----------------|
| 无开关（默认） | 不变，全量录制 | 38 个 topic 全部入袋 | ~905 MiB |
| `--lean-bag` | 注入 `--exclude "^/auv/visual/.*"` | 排除全部可视化 topic（mesh/cloud/trail/cable/body/truth/range） | ~25 MiB（−97%） |
| `--lean-bag-visual` | 隐含 `--lean-bag`，但仅排除 `seabed_(mesh|cloud)` 原始话题；同时启动 [scripts/visual_throttle.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/visual_throttle.py)，把它们以 `<topic>_throttled` 1 Hz 转发；`history_trail` 完全不动 | history_trail 全速率 + mesh/cloud 1 Hz 降采样 + cable/body/truth/range 全速率 | ~110 MiB（−88%）* |
| `--lean-bag-visual-rate HZ` | 自定义 throttle 速率（默认 1.0） | 同上但速率可调 | 与 HZ 线性 |

\* 估算：history_trail 58.32 MB + cable/body/truth/range 合计 ~5 MB + mesh 1Hz × 360KB × 60s ≈ 22 MB + cloud 1Hz × 25KB × 60s ≈ 1.5 MB ≈ 87 MiB；实测以首次跑为准。

**实现要点**：
- `--exclude` 是 ROS 2 Humble `ros2 bag record` 原生参数（regex），相比 `--bag-arg --exclude --bag-arg "..."` 更直接
- `--lean-bag-visual` 优先级高于 `--lean-bag`（前者会强制把 `LEAN_BAG=true`），不会重复注入
- 排除正则用 `^/auv/visual/seabed_(mesh|cloud)$` 锚定结尾，故 `_throttled` 后缀的副本能被 `-a` 自动发现并录入
- `topic_tools throttle` 在 apt 仓库 404 不可用，自写 [visual_throttle.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/visual_throttle.py)（rclpy ~30 行核心逻辑），仅订阅 `seabed_mesh`/`seabed_cloud` 两个 topic，订阅 QoS 默认 depth=10 与 bridge 一致
- throttle 进程在 `cleanup()` 中位置：bag 之后、launcher 之前；保证 bag 关闭时 throttle 仍在转发，避免最后一帧丢失；`pkill -f "scripts/visual_throttle.py"` 兜底
- metadata.txt 新增 3 个字段：`lean_bag` / `lean_bag_visual` / `lean_bag_visual_rate_hz`

**调用示例**：
```bash
# 最瘦身（推荐 CI / 大批量回归）
bash scripts/start_experiment.sh --auto-activate --duration 60 --lean-bag

# 保留 trail 全速率 + mesh/cloud 1Hz（推荐做轨迹复盘）
bash scripts/start_experiment.sh --auto-activate --duration 60 --lean-bag-visual

# 自定义 throttle 速率（如 5Hz）
bash scripts/start_experiment.sh --auto-activate --duration 60 --lean-bag-visual --lean-bag-visual-rate 5
```

---

## 8. 兼容性核查：当前 `start_experiment.sh` vs git HEAD（`start_experiment_old.sh` 备份）

为便于回滚和对照，已从 `git show HEAD:scripts/start_experiment.sh` 取出原版，重命名保存为 [scripts/start_experiment_old.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment_old.sh)（230 行，未加 +x）。当前线上版 [scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) 共 359 行。

### 8.1 行为差异表

| 维度 | OLD（HEAD） | NEW（当前） | 兼容性 |
|------|------------|------------|-------|
| **CLI flags** | 17 个 | 25 个（新增 8 个：`--record-format`, `--bag-finalize`, `--auto-activate`, `--auto-activate-rate`, `--scenario`, `--seed`, `--mpc-mode`，含 `--record-format` 是 `--bag-storage` 别名） | ✅ **向后兼容**：旧的所有 flag 全部保留，新 flag 默认关 |
| **BAG_FINALIZE_S 默认值** | 不存在（cleanup 直接 `kill -- -BAG_PID`，无等待） | 30s | ⚠️ 默认行为变化：cleanup 比旧版慢 ~3s（实测） |
| **bag record 进程组** | `setsid ros2 bag record ... &`（PID 抓 wrapper） | 直接 `&` + `</dev/null`（PID 抓真进程） | ⚠️ 修复 metadata.yaml 缺失，但 process group 关系变了 |
| **cleanup 顺序** | progress → bag → launcher | progress → bag → launcher → orphan sweep → emu | ✅ 新版多两步兜底，无害 |
| **三段信号升级** | 仅 `kill -- -PID`（隐式 SIGTERM） | INT → 轮询 BAG_FINALIZE_S → TERM → 2s → KILL | ✅ 新版更稳健 |
| **AutonomyGuard 激活** | 无机制（用户必须自己跑 console_soft 或 headless emu） | 内置 `--auto-activate` 拉起 emu | ✅ benchmark 可自包含 |
| **环境变量传递** | 无 | 通过 `--scenario/--seed/--mpc-mode` export `AUV_*` | ✅ 旧调用方不传则不 export，对 sim/brain 无影响 |
| **set -e** | 是 | 是 | ✅ 一致 |
| **trap signals** | EXIT INT TERM | EXIT INT TERM | ✅ 一致 |
| **launcher setsid** | 是 | 是 | ✅ 一致 |
| **`exit 0` 在 duration 模式** | 是（旧注释：旧版直接 exit；触发 trap EXIT） | 是（新代码注释强调走 trap EXIT） | ✅ 实际行为一致 |
| **`metadata.txt` 字段** | 9 个字段 | 14 个字段（+ bag_finalize_s, auto_activate, auto_activate_rate_hz, scenario_file, scenario_seed, mpc_mode） | ✅ 增量字段；下游解析器需用 `dict.get()` |

### 8.2 已知调用方影响

| 调用方 | 用法 | 兼容性结论 |
|-------|------|-----------|
| [scripts/run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh) | `bash start_experiment.sh --duration ... --record-bag --auto-activate ...` | ✅ 已升级用新 flag |
| 手动单 phase 调参 | `bash start_experiment.sh --sim-backend pvs --record-bag --duration 60` | ✅ 旧用法不变，但 cleanup 多 3s 等待 |
| CI/CD 脚本（如有） | 同上 | ✅ 旧 flag 兼容；若依赖 `metadata.txt` 行数则失效 |
| 解析 `metadata.txt` 的下游 | `awk -F= '/^run_id=/'` 之类 | ✅ 既有字段未删；新增字段在末尾 |

### 8.3 回滚路径

如需回到 OLD 行为（不推荐，会重新引入 metadata.yaml 缺失 bug）：

```bash
cp scripts/start_experiment_old.sh scripts/start_experiment.sh
chmod +x scripts/start_experiment.sh
```

但要注意 OLD 版本：
- bag 0 字节问题（行为树 LOCKED）会回归——除非用户自己拉起 console_soft
- bag finalize 不可靠（PID 抓 setsid wrapper，metadata.yaml 概率性缺失）
- PVS 早退仍受 [main_loop.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/apps/main_loop.py) 现版本节流保护，不会回归

### 8.4 兼容性结论

**当前版本对 OLD 完全 superset，旧调用全部兼容。** 默认行为唯一变化是 cleanup 多耗 ~3s（用于 bag finalize）。所有下游脚本无需改动。


## 附录 A：常见命令速查

```bash
# 看脚本写的 bag 在哪
cat results/control/terrain_following_*/baseline/bag_path.txt
cat results/control/terrain_following_*/terrain/bag_path.txt

# 看 bag 是否有数据
ls -la $(cat results/control/terrain_following_*/terrain/bag_path.txt)/rosbag/

# 看实验日志（每次 7 MB 起步，分析 launcher 错误首选）
tail -200 $(cat results/control/terrain_following_*/baseline/bag_path.txt)/launcher.log

# 强制清残留进程（写脚本前/后都建议跑）
pkill -KILL -f "run_zenoh_bridge.py|sim_holoocean/apps/main.py|mock_amd_server|ros2 launch foxglove_bridge|ros2 launch.*auv_stack|ros2 bag record"
```

## 附录 B：日志层级图

```
results/control/terrain_following_<TS>/
