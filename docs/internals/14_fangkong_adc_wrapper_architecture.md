# 14. FK2301 / TMR8637 Real Magnetic Wrapper 架构约定

## 1. 本次固化结论

本仓库对 `hardware_wrappers/fangkong_adc` 的接入采取以下固定分层：

1. `fangkong_adc` submodule 继续负责：
   - FK2301 TCP 连接
   - 24 bit ADC 读流
   - 电压解码
   - `mV/uT -> uT` 换算
   - 九参数标定加载与应用
2. 主仓 `auv_decision_ros` wrapper 只负责：
   - 注入本仓库层 override
   - 启停 headless 采集
   - 坐标轴重排/符号修正
   - 发布 ROS `sensor_msgs/MagneticField`
   - 掉线告警与重试

这意味着后续如果更换 ADC/传感器，优先改 submodule API；如果只是改 AUV 接线、IP、坐标系、ROS topic，则只改主仓 wrapper 和配置。

## 2. IP 约定

- `fangkong_adc` 单独运行时，默认设备地址仍保持 `192.168.1.198:1600`
- 主仓真实 wrapper 默认 override 到 `192.168.0.12:1600`

这样可以同时满足：

- submodule 自己作为独立上位机仓库时不破坏原有联调习惯
- AUV 主仓部署到 Jetson 时，不再依赖 submodule 内部写死 IP

## 3. 默认九参数标定

当前固定默认 profile：

```text
hardware_wrappers/fangkong_adc/calibration_profiles/20260705T144937_magnetometer_9param.json
```

要求：

- 该文件必须被版本控制
- `fangkong_adc` 默认配置加载它
- 主仓真实 wrapper 默认也加载它
- 不再要求 GUI 手工点击“加载标定”才能生效

## 4. 路径解析规则

为避免以下常见问题：

- 从 submodule 根目录运行可用，但从主仓运行失效
- GUI 下可用，ROS console script 下失效
- `user_config.yaml` 写入到错误工作目录

当前统一规则是：

- `fangkong_adc` 内相对路径一律按 submodule 根目录解析
- 主仓 wrapper 内相对路径一律按主仓根目录解析
- 需要落盘的 `user_config.yaml` 也必须写回 submodule 的 `config/user_config.yaml`

## 5. 主仓默认配置入口

真实 magnetic wrapper 默认参数文件：

```text
brain_linux/config/magnetic_wrapper_fangkong.yaml
```

该文件是 Jetson/AUV 主仓层的配置真源，负责：

- ADC 地址 override
- 默认标定文件路径
- 采样率/通道/灵敏度
- 轴顺序与符号

## 6. 脚本分层

从浅到深的联调入口固定为：

1. `scripts/probe_fangkong_adc.py`
2. `scripts/run_fangkong_adc_headless.py`
3. `scripts/run_real_magnetic_wrapper_smoke.sh`
4. `scripts/run_stack_with_real_magnetic_wrapper.sh`

原则：

- 每一层都要在“未接 ADC”时给出明确错误
- 不允许只有 GUI 能看懂、脚本看不懂的失败路径
