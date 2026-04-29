# attacker_station 烟测与开关说明

本文档用于说明 `scripts/attacker_station.py` 的命令行参数、对应的特性开关、推荐烟测命令，以及当前仓库中仍未完成的项目和进度状态。

## 1. 目标

这个脚本的用途有两层：

1. 作为 Mock AMD 的第二路控制源，向同一 UDP 端点发送 `$CKTH` 控制帧。
2. 作为最小烟测工具，快速确认协议封包、响应回包、CSV 记录和实时摘要这几条链路是否正常。

## 2. 命令行参数与特性开关

下面按“参数 → 特性开关”的方式对应说明。默认状态表示脚本开箱即用；如果要关闭某项特性，可使用对应的 `--no-*` 形式。

| 命令行参数 | 特性开关 | 默认值 | 作用 | 适合的烟测场景 |
|---|---|---:|---|---|
| `--profile conflict` | 冲突流量档案 | `conflict` | 使用随机控制量制造竞争流量 | 验证协议帧和响应链路 |
| `--profile sweep` | 边界扫掠档案 | `conflict` | 在零值、正向、超限、反向等边界之间轮转 | 验证限幅、编码与边界值处理 |
| `--profile heartbeat` | 心跳档案 | `conflict` | 发送低噪声、零控制量的保活帧 | 做最小干扰 smoke test |
| `--csv` / `--no-csv` | CSV 轨迹记录 | `--csv` | 开关 CSV 输出；关闭后不落盘 | 只想看网络和控制链路时关闭 |
| `--live-report` / `--no-live-report` | 实时摘要输出 | `--live-report` | 开关运行中的 Sent/Received/Lost/RTT 摘要 | 做无噪声烟测时关闭 |
| `--rate-hz` | 发送频率 | 按 profile 默认值 | 指定发送频率 | 控制烟测节奏 |
| `--response-timeout-s` | 回包等待时长 | `1.0` | 单次发送后等待 `$AUV` 响应的超时 | 验证响应时延和丢包 |
| `--duration` | 运行时长 | `10.0` | `0` 表示一直运行，直到手动停止 | 短烟测或持续压测 |
| `--seed` | 随机种子 | `None` | 固定 `conflict` 档案的随机序列 | 回归复现 |
| `--csv-path` | CSV 输出路径 | 自动生成 | 指定 CSV 文件路径 | 保存一次烟测的轨迹 |
| `--mock-amd-host` / `--mock-amd-port` | 目标端点 | `127.0.0.1:52364` | 指向 Mock AMD UDP 服务 | 对接本地或远端服务 |
| `--listen-host` / `--listen-port` | 本地绑定端点 | `0.0.0.0:52367` | 绑定本地 UDP socket | 做多实例或指定出口时使用 |
| `--obj-address` | 协议对象地址 | `1` | 写入下行帧对象地址 | 对接多对象场景 |
| `--main-motor-rpm-scale` | 主推进缩放 | 协议默认值 | 控制推力到 RPM 的映射比例 | 校准推进响应 |
| `--side-motor-rpm` | 侧推固定值 | `0` | 写入下行帧侧推转速 | 侧推相关验证 |

### 2.1 已新增的开关

本次补齐了两个显式特性开关：

- `--no-csv`：关闭 CSV 落盘。
- `--no-live-report`：关闭周期性实时摘要输出。

这两个开关默认都是开启状态，保持原有行为不变；需要安静烟测或低干扰压测时再关闭。

## 3. 推荐烟测流程

### 3.1 只检查 CLI 和帮助文本

先确认脚本的参数解析与帮助信息没有问题：

```bash
/usr/bin/python3 scripts/attacker_station.py --help
```

### 3.2 最小烟测

如果本地已经有 Mock AMD 服务，可以用最小干扰配置先跑一轮：

```bash
/usr/bin/python3 scripts/attacker_station.py \
  --profile heartbeat \
  --duration 1 \
  --rate-hz 2 \
  --response-timeout-s 0.2 \
  --no-csv \
  --no-live-report
```

这条命令用于确认：

1. 参数可以正常解析。
2. `$CKTH` 请求能够发出。
3. 如果服务端有回包，脚本能正常接收并解析 `$AUV`。
4. 关闭 CSV 和实时摘要后，脚本仍然能稳定退出。

### 3.3 边界值回归烟测

如果要验证协议边界和控制量编码，使用扫掠档案：

```bash
/usr/bin/python3 scripts/attacker_station.py \
  --profile sweep \
  --duration 5 \
  --rate-hz 1 \
  --csv-path log/attacker_station_sweep.csv
```

这条命令会轮转零值、正向、超限和反向等典型边界，有助于发现限幅、符号和编码问题。

### 3.4 冲突流量复现

如果要复现随机竞争流量并固定结果，使用冲突档案并指定随机种子：

```bash
/usr/bin/python3 scripts/attacker_station.py \
  --profile conflict \
  --seed 42 \
  --duration 10 \
  --rate-hz 2
```

这条命令适合做回归复现，因为同样的种子会生成相同的随机序列。

## 4. 烟测关注点

建议按下面四个点判断烟测是否通过：

1. 请求帧能发出，并且目标地址正确。
2. 回包能收到，并能从 `$AUV` 中解析出关键字段。
3. `--no-csv` 生效后不生成 CSV 文件。
4. `--no-live-report` 生效后不会打印周期摘要，但脚本仍能正常结束。

## 5. 当前未完成项目确认

以下内容按仓库现有进度文档 [开发进度.md](../开发进度.md) 和当前代码状态仍属于未完全闭环项：

1. `auv_bridge` 的业务实现仍在推进中，Zenoh JSON 与 ROS2 DDS 的正式门控还未完全收敛。
2. 端到端自动化回归脚本还需要进一步标准化，尤其是稳定性和异常恢复场景。
3. 长时间运行下的时延分布、丢包恢复、不同工况切换的正式验收报告还不完整。
4. 仿真与实物协议的完整映射文档仍需继续补齐。

## 6. 当前进度确认

基于这次烟测和已有回归结果，可以确认以下事项：

1. `scripts/attacker_station.py` 已具备可用的 CLI、三种流量档案、CSV 记录和实时摘要能力。
2. 新增的 `--no-csv` 和 `--no-live-report` 开关已经补上，并有单元测试覆盖。
3. `tests/test_attacker_station.py` 已覆盖参数解析、协议封包、回包解析和关闭 CSV 的行为。
4. 现有回归仍保持通过，未引入明显回退。

## 7. 关联文件

- [攻击站脚本](../../scripts/attacker_station.py)
- [攻击站单元测试](../../tests/test_attacker_station.py)
- [开发进度](../开发进度.md)
- [文档索引](../INDEX.md)
