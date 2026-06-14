# T7 — Jetson 部署可行性（emulated）

> **对应论文章节**：§5.5 Sim-to-Real 与 Jetson 部署 / §5.1.2 算力开销
> **直接消费方**：论文 §5.5 emulated/real 双栏算力表（real 列待真机回填）；§5.6 limitations
> **生成时机**：Phase 4 — A 档（脚本就位 + 占位结构 + emulated 限定声明）；B 档（smoke 数据）因终端 stdout 隔离推迟到下次会话执行

本文档把"Jetson Orin 部署可行性"显式拆成 **emulated**（开发机 cpuset 模拟）与 **real**（真机回填）两层，确保论文 §5.5 即使在真机数据缺位时仍逻辑自洽，且不出现"在仿真主机上推断的延迟当成 Orin 真机延迟"的越界引用。

---

## 1. 文档定位与边界

| 项 | 值 |
| --- | --- |
| 测量对象 | brain_linux 节点链（auv_localization / auv_controller / 录制 bag） + 仿真后端 / Zenoh bridge 在同一主机的协同 CPU/MEM 占用与端到端话题延迟 |
| 测量手段 | `/proc/<pid>/stat` 5 Hz 采样（CPU%、VmSize、RSS）+ rosbag mcap 中 header.stamp ↔ recv 时间差 |
| 限定 | **emulated, not on-device**：开发机 x86_64，未启用 cpuset/cgroup 限频；不可外推为 Jetson Orin 真机延迟绝对值 |
| 真机部署计划 | 论文范围之外（D7.1 D4.2 已记入 [drift log](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)）；真机回填留接口表 |

> 论文写作约束（D4.2 的避雷映射）：所有引用本章数据的句子必须包含 *"emulated"* 前缀；不得宣称 Jetson Orin 端到端延迟绝对值。

---

## 2. emulated 方法学

### 2.1 原理

x86_64 主机以 5 Hz 频率采样目标进程 `/proc/<pid>/stat`，按 `(utime+stime)` 增量与采样间隔换算 CPU%。RSS 取 `stat[24] * page_size`，VmSize 取 `/proc/<pid>/status:VmSize`。脚本未对 CPU 频率/核数做强制约束，因此**只能以"软件栈是否可在算力受限场景下保持实时"作为相对结论**，不能给真机延迟绝对值。

### 2.2 进程白名单

由 [run_jetson_emulated_bench.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh#L88) 的 `pgrep -f` 模式定义，包含：

| 模式 | 对应组件 | 论文 §5.1 模块名 |
| --- | --- | --- |
| `sim_holoocean/apps/main\.py` | 仿真后端入口（PVS / HoloOcean） | 仿真主体 |
| `run_zenoh_bridge\.py` | DDS↔Zenoh 桥 | 通信层 |
| `mock_amd_server` | 母船端 mock | 主控仿真 |
| `brain_linux/.*ros2` | brain_linux 下所有 ROS2 节点 | 算法/控制层 |
| `ros2 bag record` | mcap 录制 | 数据采集 |

> brain_linux/ROS2 子进程的 CPU% 之和近似论文 §5.5 算力主体。

### 2.3 输出产物

```
log/jetson_emulated/<TS>_<scenario>/
├── cpu_mem.csv            # ts_iso, pid, cmd, cpu_pct, mem_kb, rss_kb
├── sampler.log            # 采样器侧记录
├── experiment.log         # start_experiment.sh 主线日志
└── cpu_mem_boxplot.png    # per-process CPU% 与 RSS MB 箱型图（matplotlib 缺失则缺）
```

---

## 3. 复现命令（论文级）

### 3.1 默认 5 min baseline 场景

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
bash scripts/run_jetson_emulated_bench.sh \
  --duration 300 \
  --scenario baseline \
  --sample-hz 5
```

输出：`log/jetson_emulated/<TS>_baseline/`。论文表 5-X *emulated* 列直接来自该 csv 聚合。

### 3.2 高扰动场景对照（combined_stress）

```bash
bash scripts/run_jetson_emulated_bench.sh \
  --duration 300 \
  --scenario combined_stress
```

> 用于回答："NIS+自适应R+UA-MPC 在最坏工况下 CPU 是否仍 < 100%（单核当量）"。

### 3.3 smoke 档（CI / 烟雾测试用，60 s）

```bash
bash scripts/run_jetson_emulated_bench.sh --duration 60 --scenario baseline
```

---

## 4. 期望指标矩阵（emulated 列）

| 指标 | 来源字段 | 期望（基于 Phase 1 Apple M1 + PVS 经验） | 论文阈值 |
| --- | --- | --- | --- |
| 仿真+ROS2 总 CPU%（5 Hz 中位数） | `cpu_mem.csv` 同 ts 求和 | < 600%（约 6 核当量；Orin 8 核 → < 75% 余量） | "可移植 Orin"判据 |
| brain_linux 节点 CPU% 中位数 | filter cmd LIKE `%brain_linux%` | < 200%（2 核当量） | EKF+MPC 实时 |
| RSS 峰值（brain_linux 全节点） | `rss_kb` max sum | < 1024 MB | Orin 8 GB 充裕 |
| mpc_period_ms p95 | `/auv/control/setpoint` 间隔 | < 200 ms（5 Hz 控制） | 论文 §4.5.1 控制频率 |
| ekf_period_ms p95 | `/auv/state/filtered` 间隔 | < 50 ms（20 Hz 状态） | 论文 §3.4 |
| imu→setpoint 端到端延迟 p95 | mcap 后处理 | < 250 ms | 论文 §5.5 实时性 |

> p95 延迟来自 mcap 后处理，**不**由 cpu_mem.csv 直接给出；需要补充小工具或在 [tools/run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) 上扩展。**当前为占位**。

---

## 5. 论文 §5.5 双栏表占位

| 模块 | emulated CPU% 中位 | emulated RSS MB | emulated p95 周期 ms | real (Orin) | 备注 |
| --- | --- | --- | --- | --- | --- |
| auv_localization (ES-EKF) | ⏳ B3 | ⏳ B3 | ⏳ B3 | 待真机回填 | 20 Hz 状态发布 |
| auv_controller (UA-MPC) | ⏳ B3 | ⏳ B3 | ⏳ B3 | 待真机回填 | CasADi+IPOPT 5 Hz |
| sim/bridge | ⏳ B3 | ⏳ B3 | — | n/a | 仅 emulated；Orin 不跑仿真 |
| **brain 子图合计** | ⏳ B3 | ⏳ B3 | — | 待真机回填 | 论文真机判据行 |

> "real" 列在论文成文前若仍无真机数据，按 D4.2 处理：列标 *"待真机回填"*，并在 §5.6 limitations 显式声明。

---

## 6. emulated → real 真机迁移接口

为论文未来工作章节预留：

| 接口项 | emulated 现状 | real 需要做的最小改动 |
| --- | --- | --- |
| 进程白名单 | x86 主机 cmd 模式（[run_jetson_emulated_bench.sh#L88](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh#L88)） | Orin 上仅保留 brain_linux/.*ros2 + ros2 bag record；仿真/bridge 无 |
| 采样源 | `/proc/<pid>/stat` | 同；可附加 `tegrastats` 解析（GPU/EMC 频率） |
| 实验主线 | start_experiment.sh + sim 后端 | 改为 Orin 上以已录 bag 回放（rosbag2 play）+ brain_linux 节点链；不依赖仿真 |
| 时间基准 | 主机系统时钟 | Orin 系统时钟 + chrony 同步；header.stamp 需对齐 |
| 输出位置 | `log/jetson_emulated/` | `log/jetson_real/`（建议）；保持同列 schema |

> 该接口稳定后，论文 §5.5 真机列可一次性回填；脚本无需大改。

---

## 7. 与 Phase 4 计划的对应

| 计划行 | 内容 | 当前状态 |
| --- | --- | --- |
| §3.2 T7 | `06_jetson_deploy_emulated.md` §5.5 | ✅ A 档（本文档） |
| §3.4 G | run_jetson_emulated_bench.sh → CPU/MEM/IPOPT 时延 → §5.5 | ⏳ B3 数据回填（D7.2 终端隔离暂缓） |
| §8 #11/12/13 (B1-B3) | smoke 档 jetson_bench | ⏳ deferred |

引用计划 §3.2 T7 行原话：

> ``docs/thesis/06_jetson_deploy_emulated.md`` | §5.5 | Jetson 仿真侧 CPU/MEM/IPOPT 时延 + 部署可行性结论 | A：方法学；B：跑 jetson_bench；C：画饱和曲线

本文档完成 A 档（方法学 + 占位 + 限定声明 + 接口表），B/C 档（数据 + 图）由后续会话补。

---

## 8. 验收清单

- [x] 文档明示 *"emulated, not on-device"* 限定（§1）
- [x] 复现命令可单条复制粘贴（§3）
- [x] 期望指标表给出 §5.5 阈值锚点（§4）
- [x] §5.5 双栏表头与列定义就绪（§5）
- [x] real 真机迁移接口列出（§6）
- [ ] B3：执行 §3.1 命令并把数据回填 §4 §5（D7.2 解锁后）
- [ ] mcap 后处理脚本：补 `mpc_period_ms` / `ekf_period_ms` / `imu→setpoint` p95 三项（§4 标注的占位）
- [ ] 真机 Orin 列回填（论文范围外，未来工作）

---

## 9. 已知限制

| 限制 | 来源 | 论文写作避雷 |
| --- | --- | --- |
| x86 主机 != Orin 算力 | 本质 | 全文加 *"emulated"*；real 列空 |
| `/proc` CPU% 估算粗糙（一次 sleep） | [run_jetson_emulated_bench.sh#L99-L107](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh#L99-L107) | 论文给中位数 + 箱型图，不报单点峰值 |
| matplotlib 缺失则跳过出图 | [run_jetson_emulated_bench.sh#L138-L182](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh#L138-L182) | C 档画图前先 `pip install matplotlib` |
| 时间基准为主机系统时钟 | 默认 | 不同主机/Orin 间不可直接对比延迟绝对值 |
| 端到端 p95 不在 csv 中 | 未实现 | §4 中三行延迟 p95 须 mcap 后处理（C 档新增小工具） |

---

## 10. 与同族 thesis 文档的链接

- [00_overview.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/00_overview.md) — 总览中的算力分支
- [05_scenario_recipes.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/05_scenario_recipes.md) — `--scenario` 取值来源
- [04_mpc_robustness_ablation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md) — IPOPT 时延数据来源（与本表 §4 中 mpc_period_ms 共享）
- [07_drift_log_and_known_issues.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md) — D4.2 D7.1 D7.2

---
