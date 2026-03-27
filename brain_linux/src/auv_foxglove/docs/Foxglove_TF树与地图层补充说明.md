# Foxglove TF 树与地图层补充说明

> 适用场景：AUV ROS2 模拟发布 + Foxglove 3D / Map 联动显示
>
> 目标：解释为什么要从独立 `Map` 面板切换到 3D 内置地图层，以及 TF 坐标系如何在 Foxglove 中形成可视化闭环。

---

## 1. 为什么要补这份说明

在调试过程中，曾出现如下现象：

- 独立 `Map` 面板导入后报 `Unknown panel type: Map`
- 3D 面板可以显示，但 GPS 与坐标系关系不够直观
- 用户希望同时看到：
  - 平滑连续的 AUV 运动
  - GPS 地图轨迹
  - TF 坐标树关系

因此，最终方案改为：

1. **数据发布器发布平滑运动状态**
2. **发布 `world -> auv/base_link` 动态 TF**
3. **发布 `auv/base_link -> auv/imu_link、auv/dvl_link、auv/depth_link` 静态 TF**
4. **Foxglove 3D 面板内使用 Map layer 展示地图，而不再使用独立 `Map` 面板**

这样既避免了 `Map` 面板类型兼容风险，又保留地图能力和 TF 可视化能力。

---

## 2. 当前推荐的 TF 结构

推荐 TF 树如下：

```text
world
└── auv/base_link
  ├── auv/imu_link
  ├── auv/dvl_link
  └── auv/depth_link
```

### 含义说明

- `world`：全局惯性坐标系，作为动态 TF 的根节点
- `auv/base_link`：AUV 本体基准坐标系
- `auv/imu_link`：IMU 传感器安装位姿
- `auv/dvl_link`：DVL 传感器安装位姿
- `auv/depth_link`：深度传感器安装位姿

### 这套结构的好处

- 3D 视图里可以直接看 AUV 在地图上的相对位姿
- 各传感器挂载位置清晰，便于后续扩展
- 对 Foxglove 的 3D 主题/地图层更友好

---

## 3. 一阶平滑积分模型的意义

以前的数据源偏“白噪声抖动”，主要问题是：

- 深度、速度、航向变化跳动太大
- GPS 和姿态缺乏连续性
- 3D 轨迹不自然

现在改为一阶平滑积分模型：

- 先生成缓慢变化的目标值
- 再通过惯性环节逐步逼近目标值
- 最后对位置进行积分更新

这样产生的效果：

- 轨迹连续
- 速度平滑
- 航向变化稳定
- 更接近真实 AUV 的运动状态

---

## 4. 为什么不用独立 Map 面板

独立 `Map` 面板曾出现兼容问题：

- 布局导入时被识别为 `Unknown panel type: Map`

在当前方案中，改用 **3D 面板内置地图层**：

- 不再单独创建 `Map` 面板
- 仍然显示地图底图
- 地图与 3D 物体、TF 树在同一个视图中联动

### 优点

- 少一个布局面板类型，兼容性更高
- 地图、轨迹、AUV 本体、TF 关系可以同时观察
- 用户不必在 Map 与 3D 两个面板之间切换

---

## 5. Foxglove 端显示结构建议

### 3D 面板

建议在 3D 面板中配置：

- `fixedFrame = world`
- `followTf = auv/base_link`
- `scene.transforms.visible = true`
- `layers.map = { type: satellite, enabled: true, opacity: 1 }`

### TF 参数化扩展

当前 TF 链路已经参数化，后续可以通过 launch 参数调整：

- `world_frame_id`：动态 TF 的根节点，默认 `world`
- `base_frame_id`：AUV 本体基准坐标系，默认 `auv/base_link`
- `imu_frame_id`、`dvl_frame_id`、`depth_frame_id`：现有静态传感器 frame
- `camera_frame_id`、`sonar_frame_id`：预留的未来扩展 frame，占位但默认不发布
- `*_frame_offset_xyz`：各 frame 的安装偏移，默认 `0.0,0.0,0.0`
- `publish_imu_tf`、`publish_dvl_tf`、`publish_depth_tf`：现有静态 frame 开关
- `publish_camera_tf`、`publish_sonar_tf`：未来扩展 frame 开关，默认关闭

这样做的好处是：

- 新增相机/声呐时，不需要改 TF 发布框架
- 只需要在 launch 层打开对应 frame 并填外参
- Foxglove 3D 的绑定关系和 ROS2 TF 树保持一致

### 图表与原始消息面板

建议保留：

- Plot：深度、温度、压力
- Raw Messages：IMU、状态、速度（必要时 GPS 也可保留原始消息用于调试）

---

## 6. 现在的生成器策略

当前生成器遵循以下原则：

1. 默认启用地图层，但不再创建独立 `Map` 面板
2. 3D 面板负责地图 + TF + AUV 位姿展示
3. 如果需要兼容更保守场景，可以使用 `--no-map` 关闭 3D 内置地图层

---

## 7. 调试顺序建议

### 7.1 先确认数据发布

```bash
ros2 topic list | grep '^/auv/'
ros2 topic echo /auv/depth --once
ros2 topic echo /tf --once
```

### 7.1.1 运行隔离说明

当前仿真侧会为每次启动自动生成独立的 HoloOcean UUID，用来隔离 POSIX semaphore，避免上一次异常退出留下的句柄影响下一次联调。

这意味着：

- 正常重启不需要手工清理 semaphore
- 旧的 HoloOcean 进程残留不会再和新进程抢同一组 sem
- 如果你要做多实例测试，可以继续通过不同启动进程隔离运行

### 7.2 再确认 Foxglove Bridge

```bash
ss -ltnp | grep ':8765'
```

### 7.3 再确认布局文件

- 导入 `output/auv_layout.generated.json`
- 不要导入 `.meta.json`

### 7.4 最后确认 3D 视图

- 能看到 `/auv/state/filtered`
- 能看到地图底图
- 能看到 `world -> auv/base_link` 的 TF 关系与随时间连续运动轨迹

### 7.5 调参时的建议顺序

1. 先确认 `world_frame_id` 和 `base_frame_id` 正确
2. 再确认 IMU/DVL/Depth 的静态 frame 是否按默认发布
3. 如果需要扩展相机或声呐，再启用 `publish_camera_tf` / `publish_sonar_tf`
4. 最后再调各 frame 的 `*_frame_offset_xyz`

---

## 8. 结论

如果再出现 `Unknown panel type: Map`，说明布局中仍然存在独立 Map 面板引用，或者导入的是旧布局文件。最佳处理方式不是继续绕 Map 面板，而是继续使用 **3D 内置地图层**，这也是当前推荐的最终方案。
