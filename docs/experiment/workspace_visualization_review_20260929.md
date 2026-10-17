# 仓库差异、保留清单与当前答辩可视化

2026-09-29 核对；已执行 `git fetch origin main`。主仓 HEAD 与 origin/main 都是 `6e4632a296feef6c706588b06dc57bfe0899e967`，两个子模块也仍在基线 gitlink。系统新增能力主要位于未提交修改和未跟踪文件中，不能只审查已提交记录。

## 差异范围与阅读顺序

以下为包含本轮交付的最终工作区快照：

| 仓库 | 内容差异 | 零行差异 | 未跟踪文件 |
| --- | ---: | ---: | ---: |
| main | 154 | 1253 | 452 |
| AUV-Master-Mag | 14 | 202 | 420 |
| hardware_wrappers/fangkong_adc | 0 | 69 | 0 |

逐文件清单见 [TSV](assets/workspace_review_20260929/workspace_inventory.tsv) / [JSON](assets/workspace_review_20260929/workspace_inventory.json)。它们同时清点主仓和子模块，区分内容差异、零行差异与未跟踪文件；忽略行末空白，不修改文件。零行差异只说明没有文本增删，仍应在正式提交前核对权限或换行。文件计数以 JSON 为准，包含本轮新增资产；Git ignored 的 build、install、实验大包不属于待提交清单。

目前算法、原控制器、仲裁器、自治守卫和生产 VxWorks 文件未见实质文本增删。不能把共享目录的批量权限／换行变化说成控制系统重写。磁算法 v2 和专用 ROS 包则是整目录新增：提交主仓前须先提交磁子模块源码，再更新 gitlink，否则另一台机器无法复现。

当前事实按以下顺序阅读：

1. [限定条件仿真收口](../../AUV-Master-Mag/docs/v2/INSPECTION_SIMULATION_COMPLETION_20260928.md)：本阶段主结果。
2. [九趟原始包与图 71](../../AUV-Master-Mag/results/v2/inspection_simulation_closure_20260928/README.md)：当前源码、全核心航迹、反例。
3. [完整要求与版本审阅](../../AUV-Master-Mag/docs/v2/INSPECTION_V2_REQUIREMENTS_REVIEW_20260928.md)：历史测试与安装对应关系。
4. [分层任务输出](../../AUV-Master-Mag/docs/v2/INSPECTION_TASK_OUTCOME_OPERATOR_20260927.md)：到端、埋深、执行许可与失鲜。

## 哪些值得保留

| 改动族／关键路径 | 保留判断与原因 | 使用范围 |
| --- | --- | --- |
| `AUV-Master-Mag/src/auv_mag_tracking/v2/`、`tests/test_*v2*`、v2 配置和工具 | 保留。空间横切、背景修正、双侧半高交点、模型／标定检查、横向与深度独立许可、有限路线及 Hold 预算是当前方法主体 | 方法实验／受限仿真；未知模型和实物另验 |
| `brain_linux/src/auv_cable_tracking_v2/` | 保留专用算法节点、PID、执行桥、任务终态、独立目标身份、来源时效与预算监督；保留默认关闭的诊断候选并明确入口 | `stack-v2` 通用控制与独立 `inspection_nodes`/`flythrough_nodes` 不可互换 |
| 共享桥 `bridge_node.py`、本地化 `auv_localization_node.py`、launch 参数 | 保留 IMU 包时间门和导航 IMU 年龄门的 opt-in 行为；保留仿真时钟、任务/目标 ID、关闭合成图层和真值转发的入口 | 默认兼容旧链路，不能据此宣布部署时序通过 |
| `decoupled_cable_sim_node.py`、急停按钮与 relay、历史展示脚本 | 保留作展示回归和操作机制示例 | 解耦艇体／解析磁源不替代当前 PVS 巡检或生产固件急停 |
| `perception_quality_node.py` 正常退出修复 | 保留。当前日志证明影子节点能启动；不把 `tmp/perception_shutdown_smoke.log` 当任务完成证据 | 影子输出不驱动 BT/MPC |
| `csd_vx6.8_lastest/inspection_v2_candidate/`、IMV1 sidecar、ADC 子链证据 | 保留独立候选、主机测试和实测证据 | 未烧录候选不混称生产固件；ADC 子模块无实质内容差异 |
| 图 13、61、62、67–71、源码快照与原始日志 | 全部保留。正负证据共同解释能力与边界 | 图 71 为当前主结果；61/62 与实时性负图按原版本答问 |
| 论文 169 页当前版、236 页完整备份 | 保留。当前图 5.15 对应历史资产编号 71 | 不能继续在主讲使用旧论文页码／图号 |

## 哪些遗留应退出当前入口，哪些可以清理

| 项目 | 本轮处理／清理建议 | 原因 |
| --- | --- | --- |
| 旧 `defense-1080` / `defense-perception-1366` 的 ready、置信度和彩条 | 保留历史 profile，当前使用新 `inspection-v2`。旧 README 加迁移入口 | 避免把工业评分、磁剖面质量和执行许可合成一个“成功灯” |
| Sept23 单次约 1 mm 埋深图、旧视频 | 历史标签保留，不再作为当前巡检主结果 | 同源解析场的深度结果不能覆盖新模型失配和标定门 |
| 已撤回的 QoS／监测节流／多线程候选 | 不恢复产品开关；报告、快照和诊断脚本保留在答问链 | 严格时序门失败，不作为已完成性能修复 |
| 旧 V3/V4/V4.4 讲稿与累积 §1–58 建议 | 加版本提示，新增当前主讲入口与替换文案；不抹去历史文本 | 消除“尚不能完成巡检”与最新受限仿真完成之间的时间矛盾 |
| 1256 项首轮零行差异，子模块同类项 | 不纳入算法变更；提交审阅时用 `git -c core.filemode=false diff --ignore-space-at-eol` 查看正文 | 禁止整仓 chmod／换行重写淹没有意义补丁 |
| `AUV-Master-Mag/src/auv_mag_tracking.egg-info/`、缓存、临时 layout/meta | 可再生成的构建产物；从提交清单排除，必要时定点清理 | 不是方法源码；不删除当前运行依赖指向的文件 |
| `PPT制作/~$*.pptx` | 对应 PowerPoint 关闭后可删除锁文件 | 不删除仍打开文件的锁或正式 PPTX |
| `.auv_data_o1` 中运行日志、失败探针大包 | 若空间不足，先核对哈希与报告引用后归档，再清理可重复临时日志 | 不因为失败就删除实验反例或论文追溯资产 |

本轮实际撤下的是当前展示和入口中的过时口径，没有批量删除历史实验、视频、海缆图层或用户文件。

## 实际可视化修改

- [新布局 JSON](../../foxglove_layout_project/output/inspection_v2_defense_20260929.json)：主 3D 与俯视保留海缆、搜索廊道、zig-zag、目标和航迹；默认不启用旧解耦艇体。状态文本明确“任务／桥许可／横向估计／埋深”，曲线展示实测／目标速度与 FWHM 测宽，不用置信度推算宽度。
- `zenoh_viz_bridge_node` 订阅 `/auv/cable/operational_status`；任务到端与暂停覆盖旧 TRACK 文本；1.5 s 失鲜转未知。即使场景／位姿停止到达，状态文本仍更新并清除旧估计。当前埋深未许可时只显示参考平面上的二维投影。
- 当前巡检的目标点／连线也只来自有效估计，失鲜删除；不再以仿真海缆最近点或 mock 置信度填成“检测结果”。黄色参考海缆和既有规划图层保留。
- 共享桥仅补展示数据：携带 v2 的 `lateral_valid`、`depth_valid`、FWHM 字段；未许可时清空展示埋深，不改执行控制。
- PySide6 的当前 v2 摘要改为“横向定位／埋深许可／FWHM”；状态失鲜清空旧测量值。旧版工业验收显示仍供原链路使用。

![当前 Qt：软件到端，埋深未许可](assets/workspace_review_20260929/console_route_complete.png)

![当前 Qt：暂停与上级处置请求](assets/workspace_review_20260929/console_suspended.png)

![当前 Qt：状态失鲜](assets/workspace_review_20260929/console_status_stale.png)

以上为真实 Qt 窗口的**合成状态显示检查**：通信与自动发送均未启用，不是当前完整巡检取证截图。Foxglove JSON 已生成并检查，没有以这些截图冒充 Foxglove 实际渲染。

## 验证与复现

定向 pytest **28 项通过**、两个 ROS 包构建成功、三份修改模块源码／安装文件哈希一致，七项实际 DDS 显示 smoke 均通过。[验证索引与哈希](assets/workspace_review_20260929/validation.json)、[测试日志](assets/workspace_review_20260929/inspection_visualization_review_tests.log)、[构建日志](assets/workspace_review_20260929/inspection_viz_build.log)和 [smoke JSON](assets/workspace_review_20260929/ros_display_smoke.json)已归档。合成 smoke 验证到端、撤权、未知埋深和断流清除，不代表真实任务或目标平台实时性。

仓库根目录执行：

```bash
python3 tools/audit_defense_workspace.py --output-dir /tmp/auv_workspace_audit
python3 -m foxglove_layout_project.generator.build_layout --profile inspection-v2 \
  --output foxglove_layout_project/output/inspection_v2_defense_20260929.json --pretty
source /opt/ros/humble/setup.bash
source brain_linux/install/setup.bash
ROS_DOMAIN_ID=179 ROS_LOCALHOST_ONLY=1 AUV_PROJECT_ROOT="$PWD" \
  /usr/bin/python3 tools/smoke_inspection_visualization.py --output /tmp/auv_viz_smoke.json
QT_QPA_PLATFORM=offscreen /usr/bin/python3 tools/capture_inspection_console.py \
  --output-dir /tmp/auv_console_display
```

需部署源码更新时，在 `brain_linux` 内执行 `PYTHONDONTWRITEBYTECODE=1 colcon build --packages-select auv_bridge auv_viz_bridge`，再 source 安装环境。Foxglove 导入新 JSON，连接既有 WebSocket；状态缺失时检查专用桥是否发布 `/auv/cable/operational_status`，不要用 mock 成功状态补齐。实际巡检展示使用 `viz_mock_mode:=false`、`viz_allow_synthetic_scene_fallback:=false`，实物／影子审阅还须关闭 `viz_publish_sim_ground_truth`；配置仍需按专用 launch 合同选择。主仓 CLI `--layout-profile inspection-v2` 只选择布局，不切换磁算法或赋予现场许可。

当前图 71 的原生 PVS 复跑按发布包 README；它不发布 ROS 话题。要录制当前真实联动界面，仍需专用 ROS 巡检入口和同次数据，或明确标为录制数据回放。历史 [30 秒视频](assets/defense_demo/auv_joint_demo_30s.mp4)、[100 秒视频](assets/defense_demo/auv_joint_demo_full_100s.mp4)可作界面机制备份，不能换标题当作当前图 71 的录屏。

答辩主讲、图片与逐页替换建议见 [PPT 当前同步报告](../../PPT制作/01new_系统变更与当前巡检答辩资产同步_20260929.md)。现场许可保持 `false`；实物标定与目标平台同次部署时序是后续任务。
