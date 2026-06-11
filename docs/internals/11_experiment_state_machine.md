# 实验编排状态机：start_experiment.sh

> 本文档面向维护者，描述 [scripts/start_experiment.sh](../../scripts/start_experiment.sh) 在一次完整 60s 仿真+录制实验中编排的所有进程及其状态机。
>
> 阅读前置：建议先看 [01_architecture.md](01_architecture.md) 与 [10_behavior_tree.md](10_behavior_tree.md) 了解 brain 决策栈，以及 [07_arbiter.md](07_arbiter.md) 了解 AutonomyGuard 状态机。

---

## 1. 进程拓扑（一次实验中存在的所有进程）

```
start_experiment.sh                  ← 顶层编排，本文档主体
 ├─ start_foxglove_holoocean_ros.sh  ← 集成 launcher（setsid 起新 session）
 │   ├─ run_foxglove_bridge          (ros2 launch foxglove_bridge)
 │   ├─ start_lin_sim.sh             ← sim wrapper
 │   │   ├─ python sim_holoocean/apps/main.py    ← PVS 解析模型仿真
 │   │   └─ python run_zenoh_bridge.py           ← Zenoh JSON 桥
 │   └─ start_lin_brain.sh           ← brain wrapper
 │       └─ ros2 launch auv_stack ... launch.py  ← bridge_node + decision_node + controller
 ├─ auto_activate_emu.py             ← 心跳模拟上位机（可选，默认关）
 ├─ ros2 bag record                  ← 全 topic 录制
 └─ progress_bar 子 shell            ← 进度条
```

`start_experiment.sh` 自身不发任何业务消息，只做四件事：

0. **Pre-flight 探测 + brain-ready 等待**（contract v2.2 / 2026-06-09）：
   (a) 入口轻量探测：端口 8765 + stale brain/zenoh 进程命中即 fail-fast 提示用户运行 `bash scripts/preflight_clean.sh`（防御性 hardening，详见 [§6.4](#64-sweep-harness-pre-flight--brain-ready-等待已修contract-v22--2026-06-09)）；
   (b) bag record 启动前轮询 `/auv/control/mpc_cmd` publisher 出现（timeout 90s），让 bag T0 对齐 brain ready，避免前 ~25s 录到 brain spin-up 期的飘移数据（详见 [§6.4.2](#642-bag-t0-对齐-brain-ready方案-a-2026-06-09)）。重的清场动作已外提到独立脚本 [scripts/preflight_clean.sh](../../scripts/preflight_clean.sh)，由用户显式调用。
1. 创建 `RUN_DIR=$LOG_ROOT/<TS>/`，写 `metadata.txt`
2. 后台拉起 launcher、emu、ros2 bag record 三组子进程
3. 通过 `--duration` 控制实验时长，到点触发 cleanup
4. 通过 `trap cleanup EXIT INT TERM` 保证无论怎么退都能 finalize bag + 杀干净所有子孙

实验里真正驱动业务的状态机不在 shell 脚本里，而在 brain 的 AutonomyGuard 与行为树（见 [07_arbiter.md](07_arbiter.md)、[10_behavior_tree.md](10_behavior_tree.md)）。本文档关注的是 **shell 编排层** 的隐式状态机——它**不是**一个显式的 `STATE=...` 变量，而是由"哪些 PID 还活着"集体决定。

---

## 2. 进程状态变量

[start_experiment.sh](../../scripts/start_experiment.sh) 里所有可能存在的全局 PID 句柄：

| 变量 | 启动位置 | 持有者 | 终止条件 |
|------|---------|--------|---------|
| `LAUNCH_PID` | [L310](../../scripts/start_experiment.sh#L310) | `setsid bash start_foxglove_holoocean_ros.sh` | cleanup 中 SIGINT → SIGTERM(group) → SIGKILL(group) 三段升级 |
| `EMU_PID` | [L321](../../scripts/start_experiment.sh#L321) | `python3 auto_activate_emu.py`（仅 `--auto-activate` 时存在） | cleanup 中 SIGINT → 3s 等待 → SIGKILL |
| `THROTTLE_PID` | [L373](../../scripts/start_experiment.sh#L373) | `python3 visual_throttle.py`（仅 `--lean-bag-visual` 时存在） | cleanup 中 SIGINT → 3s 等待 → SIGKILL；位置在 BAG 之后 LAUNCH 之前 |
| `BAG_PID` | [L341](../../scripts/start_experiment.sh#L341) | `ros2 bag record` 直接 `&`（**无 setsid**） | cleanup 中 SIGINT → 轮询 BAG_FINALIZE_S 秒 → 必要时 SIGTERM |
| `PROGRESS_PID` | [L348](../../scripts/start_experiment.sh#L348) | `run_progress_bar` 子 shell | duration 到点 SIGTERM；cleanup 中冗余 kill |

每个 PID 句柄等价于一个布尔状态位：**存活 / 已退**。整体实验的"shell 状态"是这四（五）位的联合：

| Phase | LAUNCH | EMU | THROTTLE | BAG | PROGRESS | 含义 |
|-------|--------|-----|----------|-----|----------|------|
| **INIT** | ✗ | ✗ | ✗ | ✗ | ✗ | 解析 CLI、注入 lean-bag exclude、确认存储后端、写 metadata.txt |
| **LAUNCHED** | ✓ | ? | ? | ✗ | ✗ | launcher 起来，throttle/emu 视开关而定，尚未 sleep WAIT_BEFORE_RECORD_S |
| **RECORDING** | ✓ | ? | ? | ✓ | ✗ | bag 已开录，等待 duration 或 Ctrl+C |
| **TIMING** | ✓ | ? | ? | ✓ | ✓ | duration 模式下进度条转动 |
| **DRAINING** | ✓→? | ✓→? | ✓→? | ✓→? | ✓→✗ | cleanup 进行中，三段升级杀子进程、等 bag finalize |
| **DONE** | ✗ | ✗ | ✗ | ✗ | ✗ | 脚本退出，metadata.yaml 已写 |

> EMU / THROTTLE 列加 "?" 是因为它们依赖 `--auto-activate` / `--lean-bag-visual` 开关，并非每次实验都启动。

---

## 3. 时序图（duration 模式，正常路径）

下面是 `bash scripts/start_experiment.sh --duration 60 --auto-activate --record-bag` 的关键时间轴（实测 `20260609_113311`）：

```
t=0.0s   ┌─[INIT]
         │  parse args, source ROS env, mkdir RUN_DIR, write metadata.txt
         │  trap cleanup EXIT INT TERM
         └─►
t=0.3s   ┌─[LAUNCHED]                      
         │  setsid bash start_foxglove_holoocean_ros.sh ... > tee LAUNCH_LOG &
         │  LAUNCH_PID=$!  (实测：PID 7280 左右)
         │  ↓ launcher 内部依次起：
         │    foxglove_bridge → start_lin_sim.sh → start_lin_brain.sh
         │    （此过程 ~3-5s，brain 中 ros2 launch 注册各节点最慢）
         │
         │  if AUTO_ACTIVATE:
         │    python3 auto_activate_emu.py --rate-hz 10 --connect-timeout 60 &
         │    EMU_PID=$!
         │    emu 内部 zenoh.open(peer mode) 持续重试直到 bridge 的 zenoh 起来
         │
t=3.3s   │  sleep WAIT_BEFORE_RECORD_S=3   ← 经验值，等 ROS topic 注册稳定
         │
t=3.3s   ┌─[RECORDING]
         │  ros2 bag record -a -s mcap </dev/null >>BAG_LOG &
         │  BAG_PID=$!  (实测：PID 7714)
         │  ↓ rosbag2 自我注册 ~30+ topic 订阅
         │
t=3.5s   │  emu 第一帧 0xEE 发出 → bridge handle_pc_raw_command → 
         │    AutonomyGuard LOCKED → ACTIVE → arbiter AUTONOMOUS_CONTROL →
         │    行为树 cascade_selector tick → controller 开始发 mpc_cmd
         │
t=3.5s   ┌─[TIMING]
         │  run_progress_bar 60 &
         │  PROGRESS_PID=$!
         │  sleep 60   ← 主线程在这里阻塞
         │
t=63.5s  │  duration 到点
         │  kill PROGRESS_PID; wait PROGRESS_PID
         │  echo "requested duration reached, finalizing via cleanup trap"
         │  exit 0   ← 触发 trap EXIT
         │
t=63.5s  ┌─[DRAINING]
         │  cleanup() 开始执行：
         │  
         │  (1) PROGRESS：已死，noop
         │  
         │  (2) BAG：
         │      kill -INT -- -BAG_PID  (process group, fail) ||
         │      kill -INT BAG_PID      (PID, success — BAG_PID 是真进程)
         │      for i in 1..30: kill -0 BAG_PID || break; sleep 1
         │      ↓ 实测约 3-5s 内退出（rosbag2 写 metadata.yaml 后正常退）
         │  
         │  (3) LAUNCHER：
         │      kill -INT -- -LAUNCH_PID  (process group, success — setsid 让它是 leader)
         │      for i in 1..30: kill -0 LAUNCH_PID || break; sleep 1
         │      ↓ launcher 内部 wait -n 触发它自己的 cleanup → 杀 sim/bridge/brain
         │      若 30s 后仍存活 → SIGTERM(group) → 2s → SIGKILL(group)
         │  
         │  (4) ORPHAN SWEEP：
         │      pkill -KILL -f "run_zenoh_bridge.py|sim_holoocean/apps/main.py|mock_amd_server"
         │  
         │  (5) EMU：
         │      kill -INT EMU_PID; 3s 轮询；必要时 SIGKILL
         │      pkill -KILL -f "scripts/auto_activate_emu.py"
         │
t=68.0s  └─[DONE]  脚本退出码 0，metadata.yaml 已 finalize
```

实测 cleanup 总耗时 **约 3-5s**（绝大部分是等 bag finalize），launcher 那一段几乎在第一秒内就因 SIGINT 退完。

---

## 4. trap-based 状态转移（含异常路径）

`trap cleanup EXIT INT TERM` 是这套编排的核心安全网。三种触发路径：

```
┌─────────────────────────────────────────────────────────────┐
│ 触发源                          │ 路径                       │
├─────────────────────────────────────────────────────────────┤
│ A. duration 到点 → exit 0       │ EXIT trap → cleanup()      │
│ B. 用户 Ctrl+C                  │ INT trap → cleanup()       │
│                                 │   (cleanup 完成后 shell    │
│                                 │    继续因 INT 死亡 → 再触  │
│                                 │    EXIT trap，cleanup 是   │
│                                 │    幂等的所以无害)         │
│ C. 顶层进程被 SIGTERM           │ TERM trap → cleanup()      │
│ D. wait $LAUNCH_PID 自然返回    │ wait 退出 → 脚本顺序往下   │
│    (无 --duration 模式)         │   → 脚本结束 → EXIT trap   │
│ E. set -e 触发 (任何 cmd 失败)  │ shell 异常退出 → EXIT trap │
└─────────────────────────────────────────────────────────────┘
```

cleanup 函数是**幂等**的——所有 `kill` 命令都用 `|| true` 兜底，所有 PID 检查都用 `[[ -n "${VAR:-}" ]]` 防御。这意味着：

- 多次触发（如 duration → EXIT，期间用户又按 Ctrl+C → INT）不会出错
- 部分子进程已经先一步死掉（如 bridge 自己崩了），cleanup 仍然能正常往下走
- BAG_PID/LAUNCH_PID 在变量赋值前被中断（极早期 INT），`${BAG_PID:-}` 为空字串，相应分支跳过

---

## 5. 子进程的状态机：与 shell 编排层的耦合关系

shell 层编排"何时拉起 / 何时拆除"，子进程内部各自有更细粒度的状态机。本节列出耦合点。

### 5.1 launcher → sim/bridge/brain（[start_foxglove_holoocean_ros.sh](../../scripts/start_foxglove_holoocean_ros.sh)）

launcher 内部用 `wait -n -p EXIT_PID` 守护三个子进程；任意一个先死它就走 `sim_cleanup`。重要状态转移：

- `start_lin_sim.sh` 内有 `trap sim_cleanup EXIT`，因此 sim 死时会自杀 bridge 进程（见 [§6.2](../experiment/terrain_benchmark_log.md#62-根因已贯通) 中 PVS 早退引发的链式拆除）
- 现版本通过 `simulation.realtime: true` + hold-pose 让 PVS 不会早退
- start_experiment.sh 杀 LAUNCH_PID 时用的是 `kill -INT -- -$PID`，依赖 `setsid` 保证 LAUNCH_PID 是新 session leader、整组都收得到 INT

### 5.2 auto_activate_emu → AutonomyGuard

emu 是 shell 层和 brain 层之间的"激活信号源"。状态耦合：

```
emu                              bridge.AutonomyGuard
─────                            ────────────────────
启动 (peer mode)                  LOCKED (默认)
zenoh peer up                       │
  │                                 │
  │ 第一帧 0xEE                     │
  └───────────────────────────────► │
                                  ARMED
                                    │ 第二帧 0xEE
                                    └───► ACTIVE
                                            │
                                            ▼
                                  arbiter AUTONOMOUS_CONTROL
                                            │
                                            ▼
                                  decision_node tick → controller 输出
                                            │
                                            ▼
                                  ros2 bag record 收到 mpc_cmd 流
```

shell 层 cleanup 杀 EMU_PID 后，bridge 在数秒内会因为收不到心跳超时而回退到 LOCKED，但此时 ros2 bag 已经在 finalize 阶段，下游不再产生新消息。

### 5.3 BAG 与 LAUNCH 之间的关闭顺序

cleanup 中 **先杀 bag，后杀 launcher** 是关键设计。如果反序：

```
WRONG: 先杀 launcher → controller 立刻死 → mpc_cmd 流断 → 
       bag 仍在录但只录到一堆"末尾消息缺失"的不完整序列
       且 launcher 死会带着 zenoh 一起死，bag 的 ROS 节点订阅也跟着乱
```

正确顺序：bag 先收 SIGINT → 它把当前缓冲 flush 成 metadata.yaml → 退出 → 再杀 launcher 让 sim/bridge/brain 整组 INT。这样 bag 的内容是一个完整闭区间。

---

## 6. 历史踩坑与状态机修正记录

> 详见 [terrain_benchmark_log.md §6.6](../experiment/terrain_benchmark_log.md)

### 6.1 `setsid CMD &` 的 PID 陷阱（已修）

旧版本 `setsid ros2 bag record ... &` 让 `$!=setsid wrapper PID`，wrapper 立刻退、孙子 ros2 bag 还活着。cleanup 杀的 PID 早死了，真 ros2 bag 没收到 SIGINT，metadata.yaml 永远不写。

修复：直接 `&` 启动 + `</dev/null` 屏蔽 TTY 避免 SIGTTIN。这样 `BAG_PID` 即真进程，cleanup 状态机正常工作。

### 6.2 BAG_FINALIZE_S 默认值 5 → 30（已修）

PVS 60s × 50Hz × 30+ topic 的 bag 大小 ~900 MiB；rosbag2 写 metadata.yaml 需要遍历整个 mcap 索引，5s 不足。改为 30s 后 cleanup 等待循环正常完成。

### 6.3 PVS 仿真无墙钟节流导致 LAUNCH 早退（已修）

旧版本 PVS sim 7s 跑完轨迹 → break → launcher wait -n 命中 → cleanup 整组拆除 → 那时 brain 还没起完，bag 录不到任何 publisher。修复在 `main_loop.py` 加 realtime 节流 + hold-pose（[terrain_benchmark_log.md §6.5](../experiment/terrain_benchmark_log.md#65-实测确认2026-06-09-修复已落地)）。

### 6.4 Sweep harness 孤儿进程 + DDS shm 残留（已修，contract v2.1 / 2026-06-09）

**症状**：`tools/run_thesis_sweep.py` back-to-back 多 seed 运行时，**第 2 个及之后**的 run 会以 `bench_failed: No IMU samples found in the MCAP file` 失败；同一脚本单跑（干净环境）则成功。113311 走通 = 当时手工杀干净；115829-121806 六次 sweep 都失败 = 当时环境脏。

**根因（三层）**：

| 层 | 残留物 | 为什么破坏下一 run |
|----|--------|--------------------|
| 进程 | `foxglove_bridge` 占 `port 8765` | 新 launcher 内的 foxglove_bridge `Bind Error` → launcher 的 `wait -n` 命中即拆全链 → brain colcon build 阶段被 SIGTERM → `/auv/sensors/{imu,dvl,depth}` 永不发布 |
| 进程 | `zenoh_viz_bridge_node` / `zenoh_json_bridge_node` 持续 zenoh peer | 新 bridge 上线后出现重复 publisher，topic 路由错乱 |
| 进程 | `_ros2_daemon`（rclpy._daemon）缓存上 run 的 node graph | 新 `ros2 bag record -a` 拿到 stale graph，进程起来但 `rosbag/` 目录从不创建 |
| 共享内存 | `/dev/shm/fastrtps_*` + `/dev/shm/sem.fastrtps_*` | 阻塞 FastRTPS discovery，新节点注册超时 |
| 共享内存 | `/dev/shm/*.zenoh` | 阻塞 zenoh 启动 |

**修复（v2.1，two-layer split）**：

v2 曾把全部清场内联进 `start_experiment.sh` 的 `preflight_clean()`。该函数同时杀掉 `_ros2_daemon`，导致每条新 run 付 ~26s daemon 冷启动代价（详见 [terrain_benchmark_log.md §6.7.6](../experiment/terrain_benchmark_log.md#676-v2--v21-拆分动机26s-冷启动副作用--运维动作显式化-2026-06-09)）。v2.1 把契约一分为二：

| 层 | 实现 | 触发时机 | 行为 |
|----|------|---------|------|
| **fast path** | [start_experiment.sh `preflight_probe()`](../../scripts/start_experiment.sh) trap 之前执行 | 每次主脚本启动 | 1) 探测 stale brain/zenoh 进程 + port 8765 → 命中即 fail-fast 提示运行 preflight_clean.sh；2) `ros2 daemon start` 预热（消除 26s 冷启动）；不杀任何进程，不动 shm |
| **slow path** | [scripts/preflight_clean.sh](../../scripts/preflight_clean.sh) 独立运维脚本 | 用户在 fail-fast 后手动调用 | 1) `pgrep -af` 命中 12 项进程模式（含 `_ros2_daemon` + 两种 `zenoh_*_bridge_node`）；2) SIGINT → 2s → SIGKILL → 1s；3) `python3` 删 `/dev/shm/{fastrtps_*, sem.fastrtps_*, *.zenoh}`；4) port 8765 探测最多 10×1s；仍占用 → `exit 2` |

**关键设计**：
- **fast path 在 trap 之前**：preflight 自身失败不应触发当前 run 的 cleanup
- **fast path 不杀进程**：保护 `_ros2_daemon` 不被无谓重启 → 控制律首发延迟从 +26s 降到 <5s
- **slow path 由用户显式调用**：清场是运维动作，不是脚本自动行为；契约对调用方透明
- **idempotent**：干净 host 上 fast path = port probe + daemon warm-up（已在跑则 no-op）；slow path = pgrep 无匹配、glob 无文件 → 0 副作用
- **不依赖 `ss/lsof/netstat`**：两层都用 `python3 socket` 探测端口（python3 是 hard dependency）
- **覆盖所有调用方**：sweep / 手工 / terrain_benchmark 都共享这两层

**P2（配套）**：[run_thesis_sweep.py `run_one()`](../../tools/run_thesis_sweep.py) 默认追加 `--bridge-backend protocol_udp --arbiter-profile --auto-activate` 三件套（用户未显式 `--start-arg` 时），消除调用方记忆负担。**Sweep 不会自动调用 preflight_clean.sh**：若 sweep 第 2 个 run 起就遇到 fail-fast，需要用户停下来手动跑 `bash scripts/preflight_clean.sh` 再续。

**验证记录（[terrain_benchmark_log.md §5](../experiment/terrain_benchmark_log.md#5-产物对照表) 同步）**：

| 场景 | 契约版本 | 验证目录 | 结果 |
|------|----------|---------|------|
| 干净 env baseline 1-seed | v2 | `log/thesis_sweep/20260609_133645_contract_p1p2_verify` | ✅ 1/1 ok（控制律 +0s） |
| 自然 dirty env 2-seed | v2 | `log/thesis_sweep/20260609_135406_contract_v2_2seed` | ✅ 2/2 ok 但控制律 +26s 冷启动副作用浮现 |
| 手工 stress dirty (3 stale + 13 shm) | v2 | `log/thesis_sweep/20260609_135820_contract_v2_dirty_stress` | ✅ 1/1 ok |
| v2.1 干净 env 1-seed 回归 | v2.1 | （待跑） | 预期：控制律首发 <5s |

---

## 7. 兼容性：状态机变量与 CLI 的对照

| CLI flag | 影响的 PID 槽 | 默认 | 说明 |
|----------|--------------|------|------|
| `--no-record-bag` | 跳过 BAG_PID | false（即默认录） | RECORDING phase 直接跳过 |
| `--duration N` | 启用 PROGRESS_PID | "" | 进入 TIMING phase；不给则 wait LAUNCH_PID |
| `--auto-activate` | 启用 EMU_PID | false | benchmark 必须开，否则 AutonomyGuard 永远 LOCKED |
| `--auto-activate-rate HZ` | 影响 EMU 行为 | 10 | bridge guard timeout = 1s，5+ Hz 即可 |
| `--bag-finalize SECONDS` | 影响 DRAINING 等待时长 | 30 | <10s 对 ~1 GB bag 不够 |
| `--wait-before-record SECONDS` | LAUNCHED → RECORDING 间延迟 | 3 | 过短可能 ros2 bag 启动时 topic 还没注册 |
| `--scenario / --seed / --mpc-mode` | export env，不创建新 PID | - | 通过环境变量传入 sim/brain 子进程 |

---

## 8. 参考实现要点（实现者守则）

1. **trap 必须覆盖 EXIT/INT/TERM 三个信号**，缺一会留孤儿。
2. **后台启动的进程必须显式 `</dev/null`**，否则后台 read TTY 会触发 SIGTTIN 进入 Stopped 状态（不是 exit）。
3. **`$!` 只对直接 fork 的子进程可信**。`setsid CMD &` 中的 `$!` 是 setsid wrapper，wrapper 立刻死，孙子才是目标——避免使用此组合。
4. **按"业务依赖反向顺序"清理**：bag → launcher → orphan sweep → emu。bag 必须最先收 SIGINT 才能 finalize。
5. **cleanup 必须幂等**——每个 kill 加 `|| true`，每个变量加 `${VAR:-}` 防御。
6. **三段信号升级（INT → TERM → KILL）只对 LAUNCH 生效**，因为 launcher 内部还要级联清理孙辈。BAG/EMU 不需要 KILL，它们都是 well-behaved 进程。
7. **Pre-flight 必须分两层（contract v2.1）**：fast path 在 trap 之前轻量探测（端口 8765 + stale brain/zenoh 进程），命中即 `exit 2` 提示用户运行 `bash scripts/preflight_clean.sh`；fast path 自身**不杀进程、不动 shm**，但负责 `ros2 daemon start` 预热（消除 26s 冷启动）。slow path（独立运维脚本 [scripts/preflight_clean.sh](../../scripts/preflight_clean.sh)）才是真正杀进程 + shm 清理 + port probe；用户显式调用，幂等。两层都用 `python3 socket.bind` 探测端口（不依赖 `ss/lsof/netstat`）。详见 [§6.4](#64-sweep-harness-孤儿进程--dds-shm-残留已修contract-v21--2026-06-09)。
