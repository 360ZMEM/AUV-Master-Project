# 11. Sensor Wrapper IP 与网段协调

## 1. 目标

当多个 Jetson 侧真实传感器都改为“独立 wrapper + capability gate”组织后，IP 规划不能继续散落在各个子仓或 GUI 默认值里。本页给出统一约定。

## 2. 基本原则

1. **设备厂商仓库的默认 IP 只服务于单仓联调**
   - 例如 `fangkong_adc` 默认保留 `192.168.1.198`
2. **AUV 主仓部署时，一律由主仓 override**
   - 例如真实 magnetic wrapper 默认改成 `192.168.0.12`
3. **ROS wrapper 不直接信任 GUI 保存的地址**
   - GUI 仅是一个调试入口，不是 AUV 主仓部署真源
4. **每个传感器一个配置源**
   - 不把多个传感器的 IP 混在同一个随机脚本里

## 3. 当前约定

### 3.1 磁传感器 / FK2301

- submodule standalone 默认：
  - `192.168.1.198:1600`
- 主仓真实 wrapper 默认：
  - `192.168.0.12:1600`
- 主仓参数文件：
  - `brain_linux/config/magnetic_wrapper_fangkong.yaml`

### 3.2 前视声呐

当前仍在 wrapper skeleton 阶段，后续接真机时建议采用同样规则：

- 厂商 SDK/驱动仓库保留原始联调地址
- 主仓建立独立 `brain_linux/config/<sonar_wrapper>.yaml`
- launch 只读取主仓配置

## 4. 推荐地址分配方式

建议 Jetson 端给“独立以太网传感器”按功能固定地址段，而不是谁先接上谁占：

```text
192.168.0.10x  导航/惯导相关
192.168.0.12   FK2301 / TMR8637 磁采集
192.168.0.13x  声呐/测距类
192.168.0.20x  工程调试与临时设备
```

这样做的好处：

- 文档、脚本、交换机配置更容易对齐
- 一眼能看出设备用途
- 更容易做故障替换和备件接入

## 5. 配置层次

对真实设备，建议固定三层：

1. **submodule 默认配置**
   - 保证原仓库单独运行不坏
2. **主仓 wrapper 参数文件**
   - 作为 AUV 部署真源
3. **launch/脚本临时 override**
   - 只用于临时实验，不做长期真源

不要把长期地址只写在：

- GUI “保存配置”
- shell 历史命令
- 某个临时 notebook

## 6. 故障定位顺序

如果真实传感器起不来，优先按以下顺序排查：

1. 主仓参数文件中的 `device_host/device_port` 是否正确
2. 传感器电口是否在 Jetson 所在网段
3. 是否被旧 GUI/旧调试脚本占用
4. 能否用最浅层 `probe` 脚本直接连通
5. 再看 ROS wrapper 和 supervisor

不要一上来就直接怀疑行为树或 controller。
