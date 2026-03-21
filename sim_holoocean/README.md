# sim_holoocean

HoloOcean 仿真与桥接模块，只保留仿真相关逻辑。

## 子目录
- apps: 入口脚本（主仿真、Zenoh 桥接）
- interfaces: HoloOcean API、坐标转换、感知模型、Zenoh 通信
- behavior: 仿真侧安全与命令防护
- experiments: 评估与调参脚本

## 分层约束
- 本层不包含 ROS2 决策逻辑。
- 通信边界使用 common 协议常量与校验函数。
