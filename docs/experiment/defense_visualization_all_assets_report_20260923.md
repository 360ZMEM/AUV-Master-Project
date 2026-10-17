# AUV 海底电缆自主巡检答辩可视化附件总报告

> 2026-09-29 历史范围提示：本图录冻结 Sept23 附件，不含随后新增的当前磁巡检资产。主讲转到 [当前仓库与展示审阅](workspace_visualization_review_20260929.md)及 [PPT 当前入口](../../PPT制作/README.md)。下方毫米级埋深与解耦急停画面仅保留原配置含义，不代替当前图 71。

> 版本：2026-09-23  
> 范围：`docs/experiment/assets/` 中的全部图片、视频、数据报告、GUI 演进记录与 PC104 联调附件。  
> 数据属性：ROS2 数字孪生、实时话题采样或历史遥测回放，不等同于实海验收数据。

## 1. 报告结论

本附件集形成了四条可以独立核查的答辩证据链：

1. **自主巡检任务链**：搜索走廊、zig-zag 搜索、磁异常检测、CONFIRM 横扫、FWHM 反演、回线和沿线跟踪均有画面或机器报告支撑。
2. **FWHM 物理量链**：4331 个实时磁场—空间样本生成双侧半高交点和 13.8592 m 宽度，进而得到 1.0008 m 埋深；数字孪生真值为 1.0000 m。
3. **安全急停链**：真实 PySide6 ESTOP 按钮触发锁存命令，AUV 水平速度归零并从 11.61 m 上浮至 0.69 m；Foxglove 同步显示紧急上浮和安全到达状态。
4. **现场回放链**：30 秒和 100 秒版本均具备上位机、联合画面和独立战术视图，可在 Foxglove 登录、显卡或实时链路异常时直接播放。

正式答辩包 `defense_demo/` 共 **42 个**：22 张图片、6 个 H.264 视频、14 个 JSON/TSV/CSV/PDF 辅助文件。整个 `docs/experiment/assets/` 共 **75 个附件**：38 张图片、6 个视频和 31 个数据、配置或日志文件。下文逐项引用全部 38 张图片和全部 6 个视频，并索引其余机器可读附件。

## 2. 答辩优先使用清单

| 优先级 | 附件 | 用途 |
|---|---|---|
| A | [Foxglove 紧急上浮过程](assets/defense_demo/foxglove_emergency_surface_active.png) | 证明 ESTOP 后状态、深度曲线和三维上浮箭头同步变化 |
| A | [Foxglove 上浮完成](assets/defense_demo/foxglove_emergency_surface_complete.png) | 证明状态收束到 `SAFE · 已上浮` |
| A | [上位机 ESTOP 锁存](assets/defense_demo/console_estop_emergency_surface.png) | 证明急停来自真实上位机按钮且需要显式复位 |
| A | [FWHM 与真值对比](assets/defense_demo/fwhm_live/fwhm_live_truth_comparison.png) | 解释原始磁场剖面、半高交点、反演精度和质量门控 |
| A | [最终干净 Foxglove 布局](assets/defense_demo/foxglove_defense_assurance_final_clean.png) | 展示任务空间关系、FWHM 有效性和回线状态 |
| A | [30 秒联合视频](assets/defense_demo/auv_joint_demo_30s.mp4) | 中期汇报或答辩快速播放 |
| A | [100 秒联合视频](assets/defense_demo/auv_joint_demo_full_100s.mp4) | 完整任务叙事和故障回放兜底 |
| B | [100 秒独立战术视频](assets/defense_demo/mission_tactical_full_100s.mp4) | 无 Foxglove 时展示轨迹、横偏、置信度和 SNR |
| B | [急停机器验收报告](assets/defense_demo/emergency_surface_report.json) | 回答“是否真的上浮、速度是否归零” |
| B | [巡检机器验收报告](assets/defense_demo/defense_assurance_report.json) | 回答状态时序、FWHM 和埋深误差 |

答辩主线建议只使用 A 级附件。历史失败画面、登录页和旧彩条布局保留在本报告后部，供说明迭代过程或排查问题，不应混入主演示。

## 3. 核心任务与安全画面

### 3.1 Foxglove 紧急上浮过程

![Foxglove 紧急上浮过程：红色 ESTOP、EMERGENCY_SURFACE 标签、红色上浮箭头和下降中的深度曲线](assets/defense_demo/foxglove_emergency_surface_active.png)

该图是急停链路的主过程证据。画面中的深度已经由约 12 m 降至约 5.5 m，三维 AUV 上方显示红色上浮箭头，任务状态与三维标签均进入紧急上浮。此时机器报告记录的水平速度为 0.00 m/s。

### 3.2 Foxglove 安全到达

![Foxglove 上浮完成：顶部状态切换为 SAFE 已上浮，深度曲线收敛至约 0.69 m](assets/defense_demo/foxglove_emergency_surface_complete.png)

该图用于给急停流程收尾。顶部状态变为 `SAFE · 已上浮`，深度曲线到达 0.69 m 附近。正式验收条件为：观察到 ESTOP 和 SURFACED、最终深度不大于 0.8 m、上浮距离不小于 8 m、急停期间水平速度不大于 0.05 m/s。

### 3.3 上位机急停锁存

![PySide6 上位机 ESTOP 锁存界面：急停按钮失能、解除急停按钮生效、仲裁状态为 ESTOP LOCKED](assets/defense_demo/console_estop_emergency_surface.png)

该图证明急停通过真实 `MainWindow` 按钮事件触发。界面在锁存后禁止重复 ESTOP，启用显式复位，并显示“紧急上浮生效”。旧二进制协议仍发送 `TASK_CANCEL` 和零推进量；新增语义命令供 ROS2 安全仲裁与 Foxglove 同步。

## 4. FWHM 与算法证据

### 4.1 单次实时巡检 FWHM

![单次实时巡检 FWHM、几何真值、埋深误差、质量时序和质量分解](assets/defense_demo/fwhm_live/fwhm_live_truth_comparison.png)

该图应按左上、右上、左下、右下顺序讲解：

1. 实时磁场—空间样本形成连续剖面，左右绿色虚线为双侧半高交点；
2. FWHM 宽度为 13.8592 m，反演垂向距离 4.0008 m；
3. 扣除 3.0000 m 离底高度后，埋深估计为 1.0008 m，真值为 1.0000 m；
4. 有效性 0.9973、置信度 0.9917、覆盖率 1.0000、对称性 0.9867。

这里没有把置信度映射成 FWHM。FWHM 来自导航位置与磁场强度组成的空间剖面，置信度仅解释结果是否允许发布。

### 4.2 zig-zag 执行诊断

![zig-zag 请求轨迹、实测横偏、定波长成分以及航向限幅诊断](assets/defense_demo/zigzag_diagnosis.png)

该图属于算法诊断附件。旧路径中，瞬时航向限幅和最小转弯半径语义会削弱预期 zig-zag 分量；它解释了为什么后来采用显式搜索航点和独立 CONFIRM 横扫，而不是继续用一条视觉上夸张的正弦参考线。该图适合回答算法修复过程，不建议作为最终性能图。

## 5. Foxglove 布局演进图录

### 5.1 推荐最终画面

![答辩保障最终干净布局：TRACK、REJOIN、VALID 和物理量曲线](assets/defense_demo/foxglove_defense_assurance_final_clean.png)

这是常规巡检阶段最推荐的 Foxglove 静态图。三个顶部状态分别回答任务阶段、是否已回线和 FWHM 是否允许发布；主视图保留海床、电缆、AUV、路径和相对关系。

![答辩保障最终运行画面：埋深约 1 m、FWHM 宽度约 13.86 m](assets/defense_demo/foxglove_defense_assurance_final.png)

该图与上一张来自同类成功路径，但保留了悬浮数值框，适合核对具体数值，不适合直接作为论文插图。

![工程验收画面：TRACK 状态、埋深与 FWHM 质量指标](assets/defense_demo/foxglove_defense_assurance_engineering.png)

该图保留工程调试信息，用于核查状态和数值来源。其信息密度较高，展示优先级低于干净版。

### 5.2 感知布局迭代

![早期实时感知布局：WAITING 状态和空内容面板](assets/defense_demo/foxglove_defense_perception_1366_live.png)

该图记录布局接线初期状态，存在空面板和数据未到达问题，仅用于说明开发过程。

![第二版实时感知布局：CONFIRM 横扫，但仍保留无量纲彩条](assets/defense_demo/foxglove_defense_perception_1366_live_v2.png)

该图记录旧彩条方案。它直观说明为什么最终布局移除无刻度 Gauge，改用任务状态灯和带 m、nT、0–1 量纲的曲线。

### 5.3 Foxglove 登录阻塞历史

![Foxglove Desktop 初始欢迎页](assets/defense_demo/foxglove_desktop_initial.png)

![Foxglove 登录选择页](assets/defense_demo/foxglove_login_state.png)

这两张图仅记录曾经存在的人工登录阻塞。当前机器已建立本地布局并完成截图，答辩时不使用这两张图；它们用于解释为什么仓库同时保留无需在线登录的视频回放路径。

## 6. PySide6 上位机图录

### 6.1 正常任务与 DL/T 状态

![PySide6 上位机 DL/T 状态探针：任务阶段、航程、横偏、置信度与 SNR](assets/defense_demo/console_dlt_probe_20260919_111840.png)

该图体现从“实验工具”向“任务控制界面”的改造：任务阶段、巡检进度和海缆感知摘要集中在上方，任务参数与 ESTOP 位于底部稳定区域。

### 6.2 30 秒和 100 秒回放末帧

![30 秒上位机回放末帧](assets/defense_demo/auv_console_short_30s_20260919_162419_lastframe.png)

![100 秒上位机回放末帧](assets/defense_demo/auv_console_full_100s_20260919_162614_lastframe.png)

两张末帧用于快速检查视频是否完整生成。30 秒版本适合汇报插播，100 秒版本保留更完整的任务状态演进。

## 7. 视频总表与统一预览

所有正式视频均已用 `ffprobe` 验证为 H.264。Markdown 渲染器不一定内嵌播放，因此下表同时提供直接文件链接和静态封面。

| 视频 | 时长 | 分辨率 / 帧率 | 建议用途 |
|---|---:|---|---|
| [上位机短片](assets/defense_demo/auv_console_short_30s_20260919_162419.mp4) | 30 s | 1600×1000 / 6 fps | 快速说明状态回传和任务控制 |
| [上位机完整片](assets/defense_demo/auv_console_full_100s_20260919_162614.mp4) | 100 s | 1600×1000 / 4 fps | 完整上位机任务状态变化 |
| [联合短片](assets/defense_demo/auv_joint_demo_30s.mp4) | 30 s | 1920×1080 / 6 fps | **答辩首选短视频** |
| [联合完整片](assets/defense_demo/auv_joint_demo_full_100s.mp4) | 100 s | 1920×1080 / 4 fps | **答辩首选完整视频** |
| [战术视图短片](assets/defense_demo/mission_tactical_short_30s.mp4) | 30 s | 1152×1080 / 6 fps | Foxglove 不可用时的短回放 |
| [战术视图完整片](assets/defense_demo/mission_tactical_full_100s.mp4) | 100 s | 1152×1080 / 4 fps | Foxglove 不可用时的完整回放 |

### 7.1 上位机视频封面

![上位机 30 秒视频中段封面](assets/defense_demo/video_previews/auv_console_short_30s_20260919_162419_midframe.png)

![上位机 100 秒视频中段封面](assets/defense_demo/video_previews/auv_console_full_100s_20260919_162614_midframe.png)

### 7.2 联合视频封面

![联合 30 秒视频原有预览图](assets/defense_demo/auv_joint_demo_30s_preview.png)

![联合 30 秒视频统一中段封面](assets/defense_demo/video_previews/auv_joint_demo_30s_midframe.png)

![联合 100 秒视频统一中段封面](assets/defense_demo/video_previews/auv_joint_demo_full_100s_midframe.png)

联合视频左侧是数字孪生战术视图，右侧是真实 PySide6 界面，可同时说明自主任务运动和操作员状态回传。

### 7.3 独立战术视频封面

![独立战术 30 秒视频中段封面](assets/defense_demo/video_previews/mission_tactical_short_30s_midframe.png)

![独立战术 100 秒视频中段封面](assets/defense_demo/video_previews/mission_tactical_full_100s_midframe.png)

战术视图集中显示搜索廊道、规划 zig-zag、估计海缆、AUV 轨迹、横偏、置信度与磁 SNR，适合在实时 GUI 环境不稳定时使用。

## 8. 全部机器可读附件

### 8.1 验收与算法数据

| 附件 | 内容 |
|---|---|
| [defense_assurance_report.json](assets/defense_demo/defense_assurance_report.json) | SEARCH→CONFIRM→TRACK、FWHM、埋深和验收条件 |
| [defense_assurance_summary.tsv](assets/defense_demo/defense_assurance_summary.tsv) | 主巡检验收路径摘要 |
| [emergency_surface_report.json](assets/defense_demo/emergency_surface_report.json) | ESTOP、SURFACED、深度、上浮距离和水平速度 |
| [emergency_surface_summary.tsv](assets/defense_demo/emergency_surface_summary.tsv) | 急停演示路径与 PASS 摘要 |
| [fwhm_runtime_probe.json](assets/defense_demo/fwhm_runtime_probe.json) | PVS 联合运行中 FWHM 被拒绝的历史边界案例 |
| [zigzag_diagnosis.json](assets/defense_demo/zigzag_diagnosis.json) | zig-zag 拟合、运动学需求和限幅原因统计 |
| [FWHM 原始样本 CSV](assets/defense_demo/fwhm_live/fwhm_live_samples.csv) | 4331 个导航位置和磁场包络样本 |
| [FWHM 质量时序 CSV](assets/defense_demo/fwhm_live/fwhm_quality_timeline.csv) | 有效性、置信度和覆盖率时序 |
| [FWHM 汇总 JSON](assets/defense_demo/fwhm_live/fwhm_live_summary.json) | 真值、估计值、误差和附件索引 |
| [FWHM 矢量 PDF](assets/defense_demo/fwhm_live/fwhm_live_truth_comparison.pdf) | 适合论文、答辩 PDF 或高分辨率导出 |

`fwhm_runtime_probe.json` 是有价值的负结果：PVS 非标定场形虽产生宽度，但质量门控拒绝发布埋深。它支持“算法不会为视觉效果伪造结果”的工程论证。

### 8.2 视频元数据与生成旁证

| 附件 | 内容 |
|---|---|
| [30 秒上位机视频 JSON](assets/defense_demo/auv_console_short_30s_20260919_162419.json) | 输入、帧数和输出元数据 |
| [100 秒上位机视频 JSON](assets/defense_demo/auv_console_full_100s_20260919_162614.json) | 输入、帧数和输出元数据 |
| [上位机探针 JSON](assets/defense_demo/console_dlt_probe_20260919_111840.json) | 上位机截图数据来源和采样信息 |
| [视频统一清单 JSON](assets/defense_demo/video_inventory.json) | 六个视频的时长、分辨率、编码、帧率和预览路径 |

## 9. 推荐现场播放顺序

1. 用“最终干净 Foxglove 布局”说明系统有哪些空间实体和状态区。
2. 播放 30 秒联合视频，完成“任务下达—搜索—感知—跟踪—回传”的快速叙事。
3. 展示 FWHM 四联图，沿“原始测量—半高交点—垂向距离—埋深—质量门控”解释算法。
4. 点击上位机 ESTOP，切换到紧急上浮过程图，再以 SAFE 完成图收尾。
5. 若实时链路受阻，直接播放 100 秒联合视频；若上位机窗口受阻，播放独立战术视频。

## 10. 复现入口与资产边界

```bash
cd /home/zmem063/AUV-Master-Project
export AUV_DATA_ROOT="$PWD/.auv_data"

# 主巡检与实时 FWHM 证据
scripts/run_defense_assurance.sh --duration 260

# 真实上位机按钮触发的急停上浮
scripts/run_emergency_surface_demo.sh
```

相关配置与说明：

- [完整演示操作说明](defense_visualization_demo_README.md)
- [答辩保障策略](defense_assurance_strategy_20260919.md)
- [canonical Foxglove layout](../../foxglove_layout_project/output/auv_defense_perception_1366.json)
- [FWHM 实时采集工具](../../tools/capture_fwhm_live_evidence.py)

这些附件能够证明代码链、状态机、可视化和受控物理模型的一致性。埋深误差和 FWHM 指标属于确定性数字孪生结果；论文和答辩中应与实海试验、实物磁传感器标定及工程验收结论分开表述。

## 11. 上位机界面演进附件

本节图片用于回溯 PySide6 从原始实验界面到紧凑任务控制界面的演进。它们不是当前答辩主界面的替代品，但可以回答“界面如何迭代、不同分辨率是否测试、诊断页是否保留”等问题。

### 11.1 深色主题

![深色主题第一版改造效果](assets/gui_improvement/dark_after.png)

![深色主题紧凑版第二次迭代](assets/gui_improvement/dark_compact_v2.png)

![深色主题诊断页](assets/gui_improvement/dark_diagnostics.png)

深色主题与当前答辩视觉风格一致。紧凑版验证了主要状态、控制和任务参数在有限屏幕内的可读性，诊断页则保留传感器与通信排障入口。

### 11.2 浅色主题与间距迭代

![浅色主题第一版改造效果](assets/gui_improvement/light_after.png)

![浅色主题紧凑版](assets/gui_improvement/light_compact.png)

![浅色主题紧凑版第二次迭代](assets/gui_improvement/light_compact_v2.png)

![浅色主题诊断页](assets/gui_improvement/light_diagnostics.png)

![浅色主题最终微调](assets/gui_improvement/light_final_tweak.png)

![浅色主题面板间距调整](assets/gui_improvement/light_panel_spacing.png)

![浅色主题面板间距第二次调整](assets/gui_improvement/light_panel_spacing_v2.png)

浅色主题主要用于检查颜色依赖、字体对比度和间距，不作为当前答辩默认主题。最终采用深色主题，是因为它与 Foxglove 和视频战术视图之间的视觉跳变更小。

## 12. Xvfb 与 PC104 联调截图

### 12.1 无真实设备的 GUI 启动检查

![Xvfb 虚拟显示下的上位机初始窗口](assets/gui_debug/xvfb_dummy_console_initial.png)

![Xvfb 1920×1080 上位机完整画面](assets/gui_debug/xvfb_dummy_console_1920x1080.png)

这两张图证明上位机可以在虚拟显示环境完成启动和截图，适合 CI、服务器和无物理显示器场景。

### 12.2 PC104 分阶段联调

![PC104 只读观察阶段上位机](assets/gui_debug/xvfb_pc104_readonly_console.png)

![PC104 第二阶段观察模式](assets/gui_debug/xvfb_pc104_stage2_observe_console.png)

![PC104 第三阶段零量前向模式](assets/gui_debug/xvfb_pc104_stage3_zero_forward_console.png)

![PC104 第四阶段 Zenoh 联调界面](assets/gui_debug/xvfb_pc104_stage4_zenoh_console.png)

这组截图记录了从只读、观察、零量前向到 Zenoh 接入的分级联调策略。它们用于证明真实控制链路采用渐进放权，没有在初次连接时直接发送有动力指令。

## 13. GUI 配置、窗口清单与 PC104 日志索引

### 13.1 GUI 辅助文件

| 附件 | 内容 |
|---|---|
| [Zenoh Xvfb 联调配置](assets/gui_debug/xvfb_pc104_stage4_zenoh_config.yaml) | PC104 第四阶段 GUI/Zenoh 参数 |
| [深色第一版窗口清单](assets/gui_improvement/dark_after_windows.txt) | 截图时可见窗口记录 |
| [深色紧凑版窗口清单](assets/gui_improvement/dark_compact_v2_windows.txt) | 深色紧凑版可见窗口记录 |
| [浅色第一版窗口清单](assets/gui_improvement/light_after_windows.txt) | 浅色第一版可见窗口记录 |
| [浅色紧凑版窗口清单](assets/gui_improvement/light_compact_windows.txt) | 浅色紧凑版可见窗口记录 |
| [浅色紧凑版 v2 窗口清单](assets/gui_improvement/light_compact_v2_windows.txt) | 浅色第二版可见窗口记录 |

### 13.2 PC104 按钮字段检查

| 附件 | 内容 |
|---|---|
| [按钮字段检查配置](assets/pc104_button_field_check/console_pc104_button_check.yaml) | 安全字段验证时的上位机配置 |
| [fanout 按钮字段检查日志](assets/pc104_button_field_check/fanout_button_field_check.log) | 下行字段解析记录 |
| [GUI ESTOP 日志](assets/pc104_button_field_check/gui_estop.log) | ESTOP 操作侧日志 |
| [GUI 主推开启日志](assets/pc104_button_field_check/gui_main_thruster_on.log) | 主推按钮操作侧日志 |
| [ESTOP 后 telnet 记录](assets/pc104_button_field_check/telnet_after_estop.log) | PC104 接收 ESTOP 后的状态 |
| [主推开启后 telnet 记录](assets/pc104_button_field_check/telnet_after_main_thruster_on.log) | PC104 接收主推字段后的状态 |

### 13.3 无传感器联调边界

| 附件 | 内容 |
|---|---|
| [4/5 自动 UDP 预期失败](assets/pc104_sensorless_limit/auto_udp_4of5_bit14_expected_fail.log) | 缺传感器条件下 bit14 门控的预期失败 |
| [零量真实 PC104 fanout](assets/pc104_sensorless_limit/fanout_zero_real_pc104.log) | 零量前向主日志 |
| [零量控制器日志](assets/pc104_sensorless_limit/fanout_zero_real_pc104_controller.log) | 零量前向控制器侧日志 |
| [bug4 基线记录](assets/pc104_sensorless_limit/telnet_bug4_baseline_after_zero_fanout.log) | 零量 fanout 后的 PC104 基线 |
| [DVL dry-run 基线](assets/pc104_sensorless_limit/telnet_dvl_baseline_dryrun.log) | 无 DVL 实物条件下的边界记录 |

这些日志属于实物接口证据，不应与数字孪生 FWHM 精度混为一谈。它们支持的是安全字段、分级放权和无传感器条件下的已知边界。
