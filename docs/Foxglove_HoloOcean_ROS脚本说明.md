# Foxglove / HoloOcean / ROS2 独立脚本说明

本文档说明当前仓库里用于 Foxglove、HoloOcean 和 ROS2 的独立脚本各自负责什么、如何调用、以及它们与主入口脚本的关系。

## 1. 设计原则

当前脚本设计遵循两个原则：

1. 主逻辑集中在已有入口脚本里，不重复实现。
2. 独立脚本只做“语义更清晰的包装”，方便日常使用和后续扩展。

因此，以下脚本都属于薄封装：

- `scripts/start_foxglove_layout.sh`
- `scripts/start_holoocean_sim.sh`
- `scripts/start_ros_brain.sh`
- `scripts/start_foxglove_holoocean_ros.sh`

## 2. 脚本职责

### 2.1 `scripts/start_foxglove_layout.sh`

作用：只生成 Foxglove 布局 JSON，不启动仿真、不启动 ROS2。

它的内部实际调用是：

- `scripts/build_foxglove_layout.sh`

适合场景：

- 你只改了布局配置，想快速重新生成 JSON
- 你想检查生成结果是否可导入 Foxglove Desktop
- 你想把 Foxglove 布局生成独立放进 CI 或手工检查流程

示例：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_foxglove_layout.sh --pretty
```

### 2.2 `scripts/start_holoocean_sim.sh`

作用：只启动 HoloOcean 仿真侧，内部转发到 `start_lin_sim.sh`。

默认模式：`both`

支持模式：

- `sim`
- `bridge`
- `both`

适合场景：

- 只看仿真本体行为
- 只看 Zenoh 桥接数据是否持续发布
- 需要在不启动 ROS2 的情况下做仿真侧排查

示例：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_holoocean_sim.sh both
```

### 2.3 `scripts/start_ros_brain.sh`

作用：只启动 ROS2 脑端，内部转发到 `start_lin_brain.sh`。

默认模式：`stack`

支持模式：

- `bootstrap`
- `decision`
- `example`
- `foxglove`
- `stack`

适合场景：

- 只改了控制、决策或可视化节点，想单独重启脑端
- 需要复现 ROS2 话题链路而不重启仿真
- 想单独验证 Foxglove 相关 ROS2 端依赖是否可用

示例：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_ros_brain.sh stack
```

### 2.4 `scripts/start_foxglove_holoocean_ros.sh`

作用：总控脚本，按顺序执行：

1. 生成 Foxglove layout JSON
2. 启动 HoloOcean / Zenoh
3. 启动 `foxglove_bridge`
4. 等待 10 秒
5. 启动 ROS2 brain

适合场景：

- 一键联调
- 整体回归
- 演示时需要一条命令起全链路

示例：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_foxglove_holoocean_ros.sh
```

## 3. 这些脚本之间的关系

推荐的使用层次是：

1. 日常改 Foxglove 布局时，用 `start_foxglove_layout.sh`
2. 单独排查仿真或桥接时，用 `start_holoocean_sim.sh`
3. 单独排查 ROS2 脑端时，用 `start_ros_brain.sh`
4. 需要端到端联调时，用 `start_foxglove_holoocean_ros.sh`

这套结构的好处是：

- 每个脚本职责单一
- 主入口逻辑不重复
- 后续新增 Zenoh 发布项时，不需要改一堆分散脚本

## 4. 参数说明

### `start_foxglove_layout.sh`

- `--topic-prefix /sim`：为布局里的 topic 加统一前缀
- `--with-map`：启用 3D 地图层
- `--pretty`：输出格式化 JSON
- 默认输出文件名会带上 Unix 时间戳，便于保留不同时刻的布局版本

### `start_holoocean_sim.sh`

- 第一个参数是模式，默认 `both`
- 后面的参数会原样传给 `start_lin_sim.sh`

### `start_ros_brain.sh`

- 第一个参数是模式，默认 `stack`
- 后面的参数会原样传给 `start_lin_brain.sh`

### `start_foxglove_holoocean_ros.sh`

- `--sim-mode`：传给 `start_lin_sim.sh`
- `--brain-mode`：传给 `start_lin_brain.sh`
- `--skip-layout`：跳过 Foxglove JSON 生成
- `--topic-prefix`：给布局统一加前缀
- `--with-map`：启用地图层
- `--layout-name`：布局 meta 名称
- `--layout-description`：布局 meta 描述
- `--layout-output`：布局输出路径
- `--layout-meta-output`：meta 输出路径
- `--layout-pretty`：格式化 JSON
- 若未显式指定 `--layout-output`，会自动生成带 Unix 时间戳的布局文件名

## 5. 推荐工作流

### 情况 A：只调 Foxglove 布局

```bash
cd scripts
bash start_foxglove_layout.sh --pretty
```

### 情况 B：只看仿真侧

```bash
cd scripts
bash start_holoocean_sim.sh bridge
```

### 情况 C：只看 ROS2 侧

```bash
cd scripts
bash start_ros_brain.sh stack
```

### 情况 D：完整联调

```bash
cd scripts
bash start_foxglove_holoocean_ros.sh
```

## 6. 注意事项

- 这些脚本都是薄包装，真正的业务逻辑仍然在 `start_lin_sim.sh`、`start_lin_brain.sh` 和 Foxglove 布局生成器里。
- `start_foxglove_holoocean_ros.sh` 现在会在 `brain_linux/install/setup.bash` 和 `foxglove-sdk/ros/install/local_setup.bash` 都存在时自动启动 `foxglove_bridge`。
- 如果以后 topic 名称或面板布局改了，优先改配置层和生成器，不要在每个脚本里重复改。
- 如果你要新增 Zenoh 发布项，先更新布局和字段真值表，再补脚本调用方式。
