# PC104 实物 fan-out 与仿真共存架构分析

日期：2026-07-11  
作者：清华 AUV 课题组  
状态：架构分析与实施建议，不代表已完成全部改造

## 一、本文目的

本文件用于沉淀 PC104 实物调试中引入的 UDP fan-out、Telnet 注入、PySide6 并发调试、ROS2 `protocol_udp` profile 与仿真链路之间的关系。

当前项目的一个关键事实是：仿真与实物共用同一套仓库、同一套 `common/` 数据契约、同一套 ROS2 bridge 代码。因此，实物调试基础设施必须明确边界，避免为了 PC104 现场便利而污染仿真默认链路。

核心问题包括：

- fan-out 是实物运行必需组件，还是调试便利组件？
- UDP fan-out 可用但 Zenoh side channel 暂不可用，意味着什么？
- fan-out 是否应该整合进启动脚本链路？
- 实物运行命令契约和仿真运行命令契约是否应该一致？
- sudo 权限在仿真、实物、工业部署中如何处理？
- 基于实物的改动是否需要通过仿真回归确认？

## 二、当前结论

fan-out 应该转正为 PC104 实物调试/并发运行基础设施，但不应成为仿真默认链路的一部分。

更准确地说：

- 仿真默认链路：不启用 fan-out。
- 实物单客户端链路：可以不用 fan-out，但需要处理 `21/udp` 低端口权限。
- 实物并发链路：推荐启用 fan-out。
- PySide6 + ROS2 同时接入 PC104：应启用 fan-out。
- 工业部署：fan-out 可以作为受控服务部署，但不建议依赖现场交互式 sudo。

## 三、fan-out 解决的真实问题

PC104 实物链路的关键约束是：

- PC104 使用 `192.168.0.101:21/udp`。
- 上位机网卡使用 `192.168.0.11`。
- 本机如果要接收 PC104 `$AUV` 上行，需要绑定 `192.168.0.11:21/udp`。
- `21/udp` 是 Linux 低端口，普通用户默认不能绑定。
- 同一个 UDP 本地端口不应由 ROS2 bridge 与 PySide6 同时直接抢占。

fan-out 的作用是把“谁占用真实 `21/udp`”收敛为一个唯一进程：

```text
PC104 192.168.0.101:21
        ^
        |
        v
fan-out 192.168.0.11:21
        |
        +--> ROS2    127.0.0.1:52365
        |
        +--> PySide6 127.0.0.1:52366

本地下行入口：
ROS2/PySide6 --> 127.0.0.1:52364 --> fan-out --> PC104
```

fan-out 当前具备三类功能：

1. 唯一绑定真实 `21/udp`。
2. 将 PC104 `$AUV` 上行复制到多个本地高端口消费者。
3. 对本地下行 `$CKTH` 做安全仲裁：
   - 识别来源是 ROS2、PySide6 还是未知端口。
   - 默认只放行零执行器包。
   - 阻断未知来源。
   - 阻断非零主推、侧推、舵角，除非显式开启高风险开关。

## 四、fan-out 和仿真的关系

仿真链路不需要 fan-out。

仿真默认数据流通常是：

```text
HoloOcean / PVS 仿真
    -> sim_holoocean bridge
    -> Zenoh JSON / ROS2 bridge
    -> ROS2 localization / controller / decision
```

仿真侧的特点：

- 不需要绑定真实 `192.168.0.11:21/udp`。
- 不需要接收 PC104 真实 `$AUV`。
- 不需要向 PC104 真实 `$CKTH` 下行。
- 不应要求 sudo。
- 不应因为实物 profile 引入 fan-out 依赖。

因此，fan-out 不应进入 `scripts/start_lin_sim.sh` 的默认路径。

如果未来需要“仿真模拟 PC104 UDP 协议”的特殊测试，可以另开 profile，例如：

```bash
scripts/start_lin_sim.sh both --backend protocol_udp --bridge-cfg config/bridge_params.protocol_udp.yaml
```

但这也不等同于真实 PC104 fan-out。fan-out 的核心价值来自真实低端口、真实板端和多客户端并发。

## 五、UDP fan-out 可用但 Zenoh 暂不可用的含义

当前已经验证：

- UDP fan-out 可用。
- PC104 `$AUV` 上行可经 fan-out 进入 ROS2。
- ROS2 non-passive 零执行器 `$CKTH` 可经 fan-out 下发 PC104。
- 普通用户 ROS CLI 可以读取 ROS2 bridge topic。
- fan-out 停止后 `21/52364/52365/52366 udp` 均可释放。

当前未闭合：

- sudo 全局 Python 仍不能 `import zenoh`。
- `eclipse-zenoh` 全局安装卡在 `Preparing metadata (pyproject.toml)`。
- PySide6 与 ROS2 的 Zenoh side channel 尚未实测闭合。

2026-07-11 更新：

- 普通用户 `/usr/bin/python3` 已可 import `zenoh`，来源为 `/home/gwxie/.local/lib/python3.10/site-packages`。
- sudo 默认 Python 仍不能 import `zenoh`。
- 通过显式环境变量可以让 sudo Python 复用用户侧 Zenoh：

```bash
sudo -n env \
  PYTHONPATH=/home/gwxie/.local/lib/python3.10/site-packages \
  /usr/bin/python3 -c "import zenoh; print(zenoh.__file__)"
```

- `PYTHONUSERBASE=/home/gwxie/.local` 也可用。
- `from zenoh import Config` 在 `PYTHONPATH` 注入场景下验证通过。
- 因此开发期不需要继续阻塞在全局 `pip install eclipse-zenoh`。

这意味着：

会影响：

- PySide6 通过 Zenoh 订阅 ROS2 内部状态。
- PySide6 与 ROS2 仲裁状态、任务状态的旁路交互。
- 更复杂的可视化、任务下发、状态同步。
- 未来多机分布式调试的统一消息总线。

不会影响：

- PC104 UDP 主链路。
- `$AUV` 上行。
- `$CKTH` 下行。
- ROS2 `protocol_udp` bridge。
- fan-out 上行复制。
- fan-out 零执行器安全下行。
- ROS2 non-passive 零执行器 soak。

工程判断：

Zenoh side channel 当前应定义为增强链路，不应作为 PC104 UDP 主链路的硬门禁。

补充判断：

- 开发期可以用 `sudo env PYTHONPATH=...` 作为临时旁路。
- 脚本中如果必须 sudo 启动 Python 且需要 Zenoh，应显式注入 `PYTHONPATH`，不要假设 sudo 会继承用户 site-packages。
- 工业部署不建议长期依赖 `/home/gwxie/.local` 这类用户目录；更稳妥方案是 systemd 环境配置、固定 venv、系统 wheel 或避免 sudo 启动需要 Zenoh 的进程。

## 六、实物运行命令契约

建议将实物运行契约分成三类，不与仿真默认命令混用。

### 1. 仿真默认契约

```bash
cd scripts
bash start_lin_sim.sh sim
bash start_lin_sim.sh both
```

特点：

- 不需要 sudo。
- 不启用 fan-out。
- 默认不接 PC104。
- 使用仿真配置与仿真 bridge 配置。

### 2. 实物 direct 契约

适用于只有 ROS2 bridge 一个客户端直接接 PC104 的场景。

```bash
cd scripts
bash start_lin_brain.sh stack \
  --backend protocol_udp \
  params_file:=/home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux/config/params.protocol_udp_pc104.yaml
```

特点：

- ROS2 bridge 直接绑定真实 `21/udp` 时需要权限处理。
- 不支持 PySide6 与 ROS2 可靠并发抢同一个真实端口。
- 适合最小链路或现场单客户端部署。

### 3. 实物 fan-out 并发契约

适用于 ROS2 与 PySide6 同时接入 PC104。

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
scripts/start_pc104_fanout_concurrent.sh --passive
scripts/start_pc104_fanout_concurrent.sh --non-passive --command-hz 2.0
scripts/status_pc104_fanout_concurrent.sh
scripts/stop_pc104_fanout_concurrent.sh
```

长时间零执行器 soak：

```bash
scripts/run_pc104_fanout_zero_soak.sh --duration 600 --command-hz 2.0
```

PySide6 手动启动：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/console_soft/auv_console_pyside6
/usr/bin/python3 main.py --config console_config.pc104_fanout.yaml
```

特点：

- fan-out 是唯一绑定真实 `21/udp` 的进程。
- ROS2 使用 `127.0.0.1:52365 -> 127.0.0.1:52364`。
- PySide6 使用 `127.0.0.1:52366 -> 127.0.0.1:52364`。
- 默认阻断非零执行器下行。
- 支持并发观察、并发调试和安全下行仲裁。

## 七、sudo 与工业部署替代方案

仿真链路不需要 sudo。

fan-out 当前需要 sudo，是因为它要绑定 Linux 低端口 `21/udp`。这是操作系统权限要求，不是 fan-out 业务逻辑要求。

可选替代方案如下。

### 方案 A：PC104 改用高端口

如果板端协议允许，将 PC104 通信端口从 `21/udp` 改为高端口，例如 `52364/udp`。

优点：

- 最干净。
- 不需要 sudo。
- 不需要特殊 Linux capability。

缺点：

- 需要修改板端或部署配置。
- 可能影响已有实物协议约定。

### 方案 B：systemd 托管 fan-out

由系统管理员预先配置 fan-out service。

现场用户只执行：

```bash
systemctl start pc104-fanout
systemctl status pc104-fanout
systemctl stop pc104-fanout
```

优点：

- 工业环境更可控。
- 权限边界清晰。
- 日志可以进 journald。

缺点：

- 需要部署 service 文件。
- 需要定义配置路径、日志策略和重启策略。

### 方案 C：独立 fan-out 二进制加 capability

将 fan-out 打包成独立可执行文件，只给该二进制绑定低端口权限：

```bash
sudo setcap 'cap_net_bind_service=+ep' /path/to/pc104_udp_fanout
```

优点：

- 不需要给整个 Python 解释器授权。
- 比直接 sudo Python 更适合转正。

缺点：

- 需要打包与发布流程。
- 需要确认 capability 在目标系统上的可维护性。

### 方案 D：降低系统低端口阈值

```bash
sudo sysctl net.ipv4.ip_unprivileged_port_start=0
```

优点：

- 简单直接。

缺点：

- 影响全系统安全边界。
- 不建议作为工业默认方案。

推荐排序：

1. 如果能改板端端口，优先高端口。
2. 如果必须使用 `21/udp`，工业部署优先 systemd 托管。
3. 如果需要独立可执行部署，可考虑二进制 `setcap`。
4. 不建议全局降低低端口阈值。

## 八、仿真共存回归要求

由于实物和仿真共用代码，实物改动必须通过仿真回归确认。

当前已经确认的是实物 fan-out 路径，不等于已经确认仿真全链路不受影响。

建议最小回归矩阵：

| 编号 | 场景 | 命令 | 期望 |
|------|------|------|------|
| A | 仿真单独启动 | `scripts/start_lin_sim.sh sim` | 仿真进程能启动，无 fan-out/sudo 依赖 |
| B | 仿真 bridge | `scripts/start_lin_sim.sh bridge` | bridge 能按默认 config 启动 |
| C | 仿真完整链路 | `scripts/start_lin_sim.sh both` + `scripts/start_lin_brain.sh stack` | ROS topic、控制输出正常 |
| D | ROS2 默认 stack | `scripts/start_lin_brain.sh stack` | 默认不误用 PC104 fan-out profile |
| E | ROS2 protocol_udp 仿真 profile | `scripts/start_lin_brain.sh stack --backend protocol_udp ...` | 不误连 PC104 实物端口 |
| F | PC104 fan-out profile | `scripts/start_pc104_fanout_concurrent.sh --passive` | 实物路径独立工作 |

只有 A-C 至少通过后，才能说“实物基础设施没有破坏仿真默认链路”。

2026-07-11 当前回归进展：

- A 类仿真单独启动 smoke 已通过：
  - `timeout --foreground 30s bash scripts/start_lin_sim.sh sim`
  - 仿真解析 `config/sim_params.yaml` 与 `config/bridge_params.yaml`。
  - HoloOcean 主循环正常输出 LOS + cascaded PID 步进日志。
  - 未要求 fan-out，未占用 PC104 `21/udp`。
- B 类仿真 bridge smoke 已通过：
  - `timeout --foreground 30s bash scripts/start_lin_sim.sh bridge`
  - bridge 持续输出 `depth≈12m` 与磁场 `|B|≈1.6e-07T` 样本。
- ROS2 默认 launch 参数已检查：
  - `ros2 launch brain_linux/launch/auv_stack.launch.py --show-args`
  - 默认 `params_file` 为 `brain_linux/config/params.yaml`。
  - 默认 `bridge_backend` 为 `zenoh_json`。
  - 默认未指向 PC104 direct 或 fan-out profile。
- 清理状态：
  - 仿真/bridge 停止后未发现残留仿真进程。
  - `21/udp`、`52364/udp`、`52365/udp`、`52366/udp` 均为空闲。

保留项：

- `scripts/start_lin_brain.sh stack` 完整长窗口回归尚未闭合；当前终端环境下输出异常简短，需要单独用更干净终端或日志落盘方式复测。
- `scripts/start_lin_sim.sh both` 同时启动 sim + bridge 的组合回归尚未闭合。

## 九、实物调试基础设施转正建议

建议将当前实物调试成果整理为正式基础设施，而不是散落的临时脚本。

### 1. Telnet 注入基础设施

用途：

- 读取 VxWorks 符号。
- 注入 DVL/IMU/深度等伪传感器值。
- 观察状态机变量。
- 验证 BUG-4/5/6。

关键原则：

- `lkup` 要精确匹配符号，避免误命中 `Current_State_printf` 这类相似符号。
- VxWorks shell 对 float 支持有限，复杂场景应使用 raw IEEE754 整数写入。
- 自动化 execute 脚本必须保留手动 Telnet 读回作为权威证据。

相关文件：

- `scripts/vxworks_bug4_runtime_probe.py`
- `scripts/vxworks_dvl_runtime_probe.py`
- `debug-pc104-telnet-udp.md`
- `.trae/documents/深度安全_空板HIL验证SOP.md`
- `.trae/documents/深度安全BUG实物HIL状态机验证记录.md`

### 2. UDP fan-out 基础设施

用途：

- 让 ROS2 与 PySide6 同时接入 PC104。
- 避免多个进程抢占 `21/udp`。
- 对下行 `$CKTH` 做安全仲裁。
- 保留实物调试日志和端口释放检查。

相关文件：

- `scripts/pc104_udp_fanout.py`
- `scripts/start_pc104_fanout_concurrent.sh`
- `scripts/stop_pc104_fanout_concurrent.sh`
- `scripts/status_pc104_fanout_concurrent.sh`
- `scripts/run_pc104_fanout_zero_soak.sh`
- `brain_linux/config/params.protocol_udp_pc104_fanout.yaml`
- `console_soft/auv_console_pyside6/console_config.pc104_fanout.yaml`

### 3. PySide6 实物 profile

用途：

- 避免 legacy `port_set.txt` 干扰。
- 通过 YAML 显式指定 PC104 或 fan-out 端点。
- 固化 `obj_address=1` 与安全保护参数。

相关文件：

- `console_soft/auv_console_pyside6/main.py`
- `console_soft/auv_console_pyside6/src/ui/main_window.py`
- `console_soft/auv_console_pyside6/console_config.pc104.yaml`
- `console_soft/auv_console_pyside6/console_config.pc104_fanout.yaml`
- `.trae/documents/PySide6上位机_PC104并发调试计划与SOP_20260711.md`

### 4. ROS2 PC104 profile

用途：

- 将 ROS2 `protocol_udp` 实物参数从仿真配置中剥离。
- 固化 PC104 `obj_address=1`。
- 固化安全默认 remote payload，避免 idle 状态下清零板端影子保护参数。

相关文件：

- `brain_linux/config/params.protocol_udp_pc104.yaml`
- `brain_linux/config/params.protocol_udp_pc104_fanout.yaml`
- `brain_linux/src/auv_bridge/auv_bridge/arbiter.py`
- `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`
- `brain_linux/src/auv_bridge/test/test_arbiter.py`

## 十、需要拍板的事项

### 拍板点 1：fan-out 是否转正

建议：

- 转正为 PC104 实物并发 profile。
- 不进入仿真默认链路。
- 不作为所有实物 direct 场景的强制依赖。

### 拍板点 2：实物默认运行方式

可选：

- direct ROS2：链路短，但 PySide6 并发困难。
- fan-out：链路多一层，但并发、安全仲裁、日志更强。

建议：

- 调试和联调默认 fan-out。
- 单客户端部署可保留 direct。

### 拍板点 3：工业权限策略

可选：

- 现场 sudo。
- systemd service。
- 独立二进制 `setcap`。
- 改板端高端口。

建议：

- 开发期允许 sudo。
- 工业部署优先 systemd 或高端口。

### 拍板点 4：Zenoh side channel 优先级

建议：

- 不阻塞 UDP 主链路。
- 作为增强链路单独排期。
- 在需要 GUI 订阅 ROS2 内部状态或任务旁路控制前闭合。

### 拍板点 5：仿真回归门禁

建议：

- fan-out/PC104 profile 继续推进前，应跑一次仿真默认链路回归。
- 回归通过后，再考虑把实物基础设施写入更正式的 `docs/` 文档。

### 拍板点 6：非零执行器短测门禁

建议：

- 非零 `/cmd_vel` 或 MPC 输出短测必须单独确认机械、电源、急停和现场安全。
- fan-out 默认仍应阻断非零执行器，只有短测命令显式打开。

## 十一、推荐实施路径

建议分三步推进。

第一步：文档转正。

- 保留本文作为架构分析。
- 将关键命令和 SOP 摘入 `.trae/documents/PySide6上位机_PC104并发调试计划与SOP_20260711.md`。
- 后续可整理为 `docs/PC104实物调试基础设施.md`。

第二步：仿真回归。

- 跑 `scripts/start_lin_sim.sh sim`。
- 跑 `scripts/start_lin_sim.sh bridge`。
- 跑 ROS2 默认 `stack`。
- 确认默认仿真链路不要求 fan-out、不要求 sudo、不误用 PC104 profile。

第三步：实物基础设施产品化。

- 明确 `direct` 与 `fan-out` 两套 profile。
- 增加 systemd 或独立二进制部署方案。
- 增加日志轮转和健康检查。
- 将 non-passive soak 扩展到 10-30 分钟。
- 在用户明确安全许可后做非零 `/cmd_vel` 受控短测。

## 十二、当前建议结论

建议采用以下原则：

1. fan-out 转正，但定位为 PC104 实物并发基础设施。
2. 仿真默认链路不启用 fan-out。
3. Zenoh side channel 暂不作为 UDP 主链路门禁。
4. 实物调试命令契约与仿真命令契约显式分离。
5. sudo 只作为开发期方案；工业部署应转为 systemd、高端口或独立二进制 capability。
6. 所有实物 profile 修改必须通过仿真默认链路回归。
7. 非零执行器测试必须单独拍板，不能被普通启动脚本隐式触发。
