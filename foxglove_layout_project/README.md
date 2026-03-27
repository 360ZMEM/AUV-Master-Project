# AUV Foxglove 布局生成项目

本目录提供一个与 Console 上位机软件中的 Foxglove 方案同风格的参数化布局生成器，目标是让 `AUV_Master_Project` 也能采用单一 topic 真值源、稳定的 layout JSON、以及后续可扩展的 Foxglove 工作流。

## 结构

- `config/`：Foxglove topic 与字段路径配置
- `generator/`：布局生成器
- `output/`：生成出的 layout JSON 和 meta 文件
- `examples/`：联调或快速验证脚本

## 当前默认布局

默认布局围绕当前 ROS2 联调链路组织：

- 3D 面板：`3D!auv3d`
- 3D 图层：AUV 实时姿态、truth pose、海底点云、电缆线、历史轨迹、视域范围
- 深度跟踪：`Plot!depth`
- 速度跟踪：`Plot!speed`
- 执行器输出：`Plot!control`
- Raw Messages：`RawMessages!imu`、`RawMessages!dvl`、`RawMessages!state`、`RawMessages!setpoint`、`RawMessages!cmdvel`、`RawMessages!status`

## 生成方式

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --pretty
```

如果要给 topic 加统一前缀，例如模拟环境：

```bash
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --topic-prefix /sim --pretty
```

如果后续要启用 3D 地图层：

```bash
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --with-map --pretty
```

如果要连同“虚假数据”快照一起生成：

```bash
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --with-mock-topics --pretty
```

## 导入 Foxglove

生成结果默认写入：

- `foxglove_layout_project/output/auv_layout.generated.<unix>.json`
- `foxglove_layout_project/output/auv_layout.generated.<unix>.meta.json`

其中 `*.json` 文件可导入 Foxglove Desktop，`*.meta.json` 仅用于追踪生成来源。

当启用 `--with-mock-topics` 时，还会额外生成：

- `foxglove_layout_project/output/auv_layout.generated.<unix>.mock_topics.json`
- `foxglove_layout_project/output/auv_layout.generated.<unix>.mock_topics.meta.json`

这两个文件用于检查 mock scene 的可见层和示例 payload，不是 Foxglove Desktop 的布局文件。

## 关键约束

1. 布局树叶子必须使用 `PanelType!slug`
2. 不要把 `Speed`、`Depth` 这类裸名字直接写进 `layout`
3. 新增面板前先补 `configById`，再补 `layout`
4. `3D`、`Plot`、`RawMessages` 是当前可用的基础面板类型

## 设计原则

1. topic 名称只在 `config/topics.py` 里维护
2. builder 只负责组装布局，不负责猜测 topic
3. 生成的 JSON 要能重复运行并保持稳定
4. 后续若新增 Zenoh 发布项，必须先补 topic 配置，再补布局
