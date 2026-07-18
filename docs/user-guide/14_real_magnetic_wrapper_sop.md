# 14. 真实磁传感器 Wrapper 使用 SOP

## 1. 适用场景

本页用于把 `FK2301 + 江苏多维 TMR8637` 接到 AUV 主仓，并按从浅到深的顺序验证：

1. 设备地址/标定是否解析正确
2. 不启 ROS 时 headless 能否运行
3. 只启 ROS magnetic wrapper 时是否能明确报错/恢复
4. 接入主栈后是否不影响其他模块

## 2. 默认文件

- 真实 wrapper 参数文件：
  - `brain_linux/config/magnetic_wrapper_fangkong.yaml`
- 默认九参数标定：
  - `hardware_wrappers/fangkong_adc/calibration_profiles/20260705T144937_magnetometer_9param.json`

## 3. 推荐顺序

### 3.1 只看配置，不连设备

```bash
python3 scripts/probe_fangkong_adc.py --print-config-only
python3 scripts/run_fangkong_adc_headless.py --dry-run
```

用途：

- 验证主仓 override 是否为 `192.168.0.12`
- 验证默认九参数路径可解析
- 验证 `fangkong_adc` API 可导入

### 3.2 只测 ADC 链路

```bash
python3 scripts/probe_fangkong_adc.py
```

未接 ADC 时，预期看到明确错误：

```text
[probe][ERROR] ADC 未就绪或链路错误: 连接失败: 192.168.0.12:1600: ...
```

如果 probe 曾经成功、随后突然超时，先确认没有残留 wrapper 进程：

```bash
ps -ef | grep magnetic_sensor_wrapper_node
pkill -f 'magnetic_sensor_wrapper_node --ros-args' || true
```

残留 wrapper 会同时占用 ADC TCP 连接，导致新进程在读寄存器时超时。

### 3.3 不启 ROS 的 headless 采集

```bash
python3 scripts/run_fangkong_adc_headless.py --duration 5
```

未接 ADC 时，预期报连接错误；接上后会打印最近一个校准后的三轴磁场值。

### 3.4 只起 ROS magnetic wrapper

```bash
bash scripts/run_real_magnetic_wrapper_smoke.sh
```

未接 ADC 时，预期：

- 节点能启动
- 日志持续打印连接失败
- 到超时后正常退出

### 3.5 接入整条主栈 smoke

```bash
bash scripts/run_stack_with_real_magnetic_wrapper.sh
```

未接 ADC 时，真实 wrapper 会持续报连接失败，但其余主栈应仍可起到 smoke 阶段。

## 4. 常改参数

优先改：

- `brain_linux/config/magnetic_wrapper_fangkong.yaml`

常见字段：

- `device_host`
- `device_port`
- `sample_rate_hz`
- `active_channels`
- `sensor_sensitivity_mv_per_ut`
- `calibration_profile_path`
- `axis_order`
- `axis_signs`
- `storage_enabled`

默认 `storage_enabled: false`，因此主仓 probe/headless/wrapper 调试不会在仓库根目录生成 `data/`。
只有需要 bench 录制原始波形或 lock-in 特征时，才临时打开它。

## 5. 容器网络与 socat 转发

FK2301 是 TCP server，wrapper/GUI/headless 是 TCP client。容器只要能主动访问
`192.168.0.12:1600`，就不需要 Docker publish `1600` 端口。

先在容器里测：

```bash
python3 - <<'PY'
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
s.connect(("192.168.0.12", 1600))
print("ok")
s.close()
PY
```

如果容器不通、但宿主机能直连 ADC，则在宿主机上开转发：

```bash
socat -d -d TCP-LISTEN:11600,bind=0.0.0.0,reuseaddr,fork TCP:192.168.0.12:1600
```

容器内通过 Docker 网关访问：

```bash
python3 scripts/probe_fangkong_adc.py --host 172.18.0.1 --port 11600
```

或临时把参数文件改成：

```yaml
device_host: 172.18.0.1
device_port: 11600
```

## 6. 注意事项

1. 不要依赖 GUI 里手工点“加载标定”才生效
2. 不要把 AUV 部署地址直接改进 submodule 默认配置里
3. 主仓真实 wrapper 和 mock magnetic wrapper 不要同时开
4. 未接 ADC 时，明确报错是正常现象，不应把节点直接写成崩溃退出
5. 若发现主仓根目录出现 `data/`，优先检查是否曾经以 `storage_enabled: true`
   或旧版本配置运行过 `fangkong_adc`
