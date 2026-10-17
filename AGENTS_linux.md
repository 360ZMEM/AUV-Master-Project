# AGENTS_linux.md — 毕设写作项目上下文索引（Linux/主体职责）

> **中期报告与模板治理（2026-10-13）**：[验收与命令](docs/middle-defense/ACCEPTANCE.md#产物与构建契约)、[实际大纲/原稿映射](docs/middle-defense/OUTLINE.md#实际采用大纲与原文映射)、[上下文](docs/middle-defense/CONTEXT.md)。根与thuthesis目录均有 `make auv-middle-defense`、`-main`、`-school`；完整上游v7.7.1锁版本vendor与本地报告/学院适配分离。论文正文、书目及旧图不改，原170页基线已备份并回归；报告截止日2026-10-13由用户确认。整艇M2.5与任务级实物仍未完成，不因报告编译通过而升级研究状态。后续接手先读这三份文档及根《中期报告codex指引.md》。

> **扰流／导航／多源答辩补强完成（2026-09-29）**：[独立报告与六对宋体图](AUV-Master-Mag/results/v2/defense_robustness_20260929/README.md)、[PPT完整记录](PPT制作/03new_扰流导航多源稳健性与答辩资产同步_20260929.md)、[逐项收口](毕业设计写作文档/核心中间进度同步/01new_扰流导航多源条件性稳健性收口_20260929.md)。120次留出＋12消融同127项源码，105/105测试；正例27/27完成、拒绝33/33，候选错误目标几何与错误完成均0/60。toy外部参考与实际水平导航误差界是额外条件，埋深为空，撤权后仍运动。论文170页，169／236版冻结；新图77为5.16／PDF139，旧图71保留。两份PPT记录和外部讲稿已同步，默认ROS工厂、现场许可及原PPTX不因本轮放行。

> **2026-09-29 仓库与展示续审**：[相对 origin/main 的逐文件清单、保留／清理与当前可视化](docs/experiment/workspace_visualization_review_20260929.md)及 [PPT 当前入口](PPT制作/README.md)。HEAD 与远端同哈希但新增 v2 主体多为未跟踪文件；新增 `inspection-v2` 布局和桥终态／失鲜文本，Qt 去旧工业 ready 混淆。图 71 仍是原生 PVS 主证据，合成 DDS／Qt 检查不冒充完整任务。


> **答辩资产差分总账（2026-09-29）**：[169／236 页与全部素材](PPT制作/02new_论文169与236页差分_答辩资产总账_20260929.md)合并两份 PPT/FWHM 记录的最新口径，登记 22 幅保留图旧新号／页、45 幅移出图预览、63 对发布图与 2 张 UI 截图、原记录资产、12 张 PDF 页对照与三份 TeX 双向 patch；隔离还原验证通过。169 页论文与完整备份、实验图及原 PPTX 不变；仿真完成／埋深空值／历史 ROS／现场时序边界分开。

> **论文精简（2026-09-28）**：[删减记录](docs/thesis/THESIS_CONDENSATION_20260928.md)将 PDF 从 236 页收束至 169 页；第 5 章 67 图→22 图，保留 FWHM 稳定性、场形拒绝、图 71 当前巡检与必要 ROS/多横切边界。只改第 5/6 章及附录 A，前四章、字体/模板/参考文献与实验原始资产不变。[236 页完整备份](thuthesis/backups/20260928_full_236p/README.md)含原版 PDF、450 文件完整源码图像包及校验；当前磁巡检图现为图 5.15。编译/引用/Overfull 检查与关键页面抽查通过；历史实验论文哈希仍对应原版备份。

> **仿真目标完成（2026-09-28，用户调整范围）**：[仿真收口](AUV-Master-Mag/docs/v2/INSPECTION_SIMULATION_COMPLETION_20260928.md)及[独立发布报告/图像/原始包](AUV-Master-Mag/results/v2/inspection_simulation_closure_20260928/README.md)固定当前磁算法的 20 m F 接入配方：单直导线/偶极各 3/3 完成并覆盖 70 m 核心段，无源 3/3 拒绝；全核心真实横偏 MAE 0.771–0.774 m、最大 1.321 m，埋深为空。阶段筛样遗漏回归的初稿已作废，原始开发包保留，三项审阅回归通过。图 71 宋体 PNG/PDF、论文第 5/6 章、发布入口和 PPT §58 已同步。按新标准完成仿真及答辩阶段，真实输入/部署时序转后续，现场许可 false；下方原始实物范围的“未完成/阻塞”条目保留历史含义。

> **原始目标完成度与版本收口（2026-09-28）**：[完整要求审阅](AUV-Master-Mag/docs/v2/INSPECTION_V2_REQUIREMENTS_REVIEW_20260928.md)固定当前磁算法 88/88、ROS 标准整包 101/101 通过，选定运行/保留备份模块 62/62 源码安装一致；[源码与日志归档](AUV-Master-Mag/results/v2/inspection_candidate_review_20260928/review.json)记录旧候选 6 文件演进及有限范围 origin/main 内容差异。现有控制器/仲裁/生产 VxWorks 无内容改动，共享桥 IMU 包时间门默认关闭；独立候选另列。旧全路线不冒充当前整任务。目标 Jetson 入口与同次实物输入—执行—运动包仍缺，完整目标未达成，现场许可 false。

> **声呐输入域与记录介质续审（2026-09-28）**：[独立输入修复报告](AUV-Master-Mag/docs/v2/INSPECTION_SONAR_QUALITY_DOMAIN_20260928.md)复现并拒绝 `p_track>1` / `age_s<0` 的身份误授权，保留未知埋深 NaN；安装版定向/DDS 7 项通过。首次构建遇 vboxsf 生成缓存 Text file busy，清理该缓存并禁字节码重建成功。[原生 ext4 记录短试](AUV-Master-Mag/results/v2/inspection_native_log_replay_20260928/README.md)磁测接收最大空档仍 0.915 s、Setpoint 3/39 正向，未到 Confirm/Track；不作介质收益或完整任务通过声明，许可 false。TCP 21/23 可连接但服务标识读取超时，未确认 PC104 身份；目标 Jetson 入口待提供。

> **巡检结论统一（2026-09-28）**：[冻结矩阵](AUV-Master-Mag/docs/v2/INSPECTION_V2_FREEZE_AND_FIELD_GATE_20260927.md)已同步图 61 的七趟到端/一趟撤权与图 67–70 时序负证据，分开论文方法/受限软件候选、目标平台完整任务时序及物理现场版。论文第 5/6 章、发布 README、运行契约和 PPT 建议 §57 同口径；历史测试计数不冒充当前版本。现场许可保持 `false`。

> **去在线 PVS 的动态航迹重放（2026-09-28）**：[图 70、独立联表与原始包](AUV-Master-Mag/docs/v2/INSPECTION_DYNAMIC_REPLAY_TIMING_LIMIT_20260928.md)把图 61 历史位姿前 12 s 以 10 Hz 开环重放，磁测/声呐重新合成；声呐每周期或名义 5 Hz 的两趟短试磁测独立接收最大空档 1.167/0.820 s，最终 Setpoint 正向 0/46、1/34，均未到 Confirm/Track。后一趟发布阶段墙钟/线程 CPU 最长 0.731/0.253 s。两趟不作降频因果比较；无在线 PVS 后仍未通过本机连续性门。开环无运动反馈/桥/PC104，现场许可 `false`。

> **分进程实时 PVS 双端预算剖析（2026-09-28）**：[图 69 与同次原始回调/供数耗时](AUV-Master-Mag/docs/v2/INSPECTION_PROCESS_PVS_LIVENESS_20260928.md)显示另一次 10 Hz 名义短试供数器工作最长 1.045 s，59 个相邻磁测发布间隔中 8 个超过 0.25 s，其中 6 个前一周期工作亦超 0.25 s；算法活跃回调最长 0.558 s、完整状态发布最长 0.302 s。状态发布启用 cProfile，不能用本机最坏值外推 Jetson；既有监测分频反事实也未通过严格门。图仅答问备份，不改产品或现场许可。

> **分进程实时 PVS 活性短试（2026-09-28）**：[图 68、独立联表审计与原始包](AUV-Master-Mag/docs/v2/INSPECTION_PROCESS_PVS_LIVENESS_20260928.md)使用已安装算法、PID、墙钟 PVS 供数和独立 DDS 记录器四进程。4 Hz/10 Hz 短试磁测接收最大空档 1.280/1.334 s，PVS 本地协议正向仅 6/40、1/80 周期，均未到 Confirm/Track；供数最长空档亦超过 1 s。首次开发样本作废，最终包装器固定运行前后 8 输入哈希。分进程仍未证明连续巡检，不可把降频当修复；目标平台完整任务、桥/PC104 和实艇仍缺，现场许可 `false`。

> **加速飞越同次接收诊断（2026-09-28）**：[图 67、独立联表审计与六趟短试](AUV-Master-Mag/docs/v2/INSPECTION_FLYTHROUGH_SAME_SESSION_RECEIPT_LIMIT_20260928.md)将仿真来源戳映射到夹具发布时间，并与另进程 DDS Setpoint/PID 接收对齐。两趟四周期短试最终 Setpoint 最大空档 1.803/1.656 s；一趟首周期 PID 已被独立进程收到，同进程观察端却晚约 1.048 s，桥因失鲜零主推。PVS 五步积分最多约 0.099 s；多线程夹具反事实仍失败并撤回，不启观测器亦有 1.478 s 周期长尾。图 61 完整合成航迹不能替代目标平台时序验收，现场许可 `false`。

> **有限任务推进／撤权独立审计（2026-09-28）**：[原始轨迹重算报告与审计 JSON](AUV-Master-Mag/docs/v2/INSPECTION_TASK_LIVENESS_AUDIT_20260928.md)将图 61 的 8 条同版合成全链分开判定：7 条软件有限路线到端，反向阶跃 1 条未到端但 Hold 后 241 周期三层零命令且请求恢复；PVS 仍漂移 5.683 m。审计器支持有预算可恢复 Hold 的任务判据，3 项定向测试通过。该结果没有独立 DDS 来源时序或物理 PC104/实艇证据，不是海况成功率，现场许可 `false`。

> **同次 ROS 接收来源时效诊断（2026-09-28）**：[独立负结果、分层宋体图及 33 文件哈希](AUV-Master-Mag/docs/v2/INSPECTION_SAME_SESSION_ROS_RECEIPT_DIAG_20260928.md)把固定供数、监督门周期、独立 DDS Setpoint/PID 同次采集。三趟 0.2 m/s 合成短探针健康供数最大缺口 0.263/0.291/0.395 s，正向最终 Setpoint 23/35、13/34、29/34，接收时来源年龄超 1.3 s 分别 4、2、4 条，严格总门均失败；第三趟守卫窗 22/23 零 Setpoint，独立接收端与夹具观察端显示晚到正向。PID 来源门开启组记录 9 次来源失鲜零推力，但仿真 `/clock` 与墙钟不同步且无跨层因果 ID，不能声称逐条拦截。图只用于机制解释，现场许可 `false`。

> **巡检 ROS 独立接收端采证（2026-09-28）**：[记录器、现场用法与 DDS 合成烟测](AUV-Master-Mag/docs/v2/INSPECTION_ROS_RECEIPT_RECORDER_20260928.md)补齐 schema 2 的 `ros_setpoint.csv` / `pid.csv` 实际接收表，保留每条来源戳、本机墙钟—单调钟换算、导航／磁测及 SHA-256。最终隔离烟测两组各 12/12 条 Setpoint/PID；有效历元组故意注入 1.038 s 旧正向消息并如实记录，零时戳组不可审阅。采集完成不等于时序通过；跨设备对时、完整任务、桥/PC104 与真实目标仍缺，现场许可 `false`。

> **完整监测归零上界诊断（2026-09-28）**：[独立负结果报告](AUV-Master-Mag/docs/v2/INSPECTION_ZERO_MONITOR_UPPER_BOUND_20260928.md)在隔离进程中省去 57/57 与 59/59 次完整 tracking/派生监测，仍每周期发布 Hold 预算状态；固定 CPU 那趟健康供数最大缺口 0.206 s 达门，却仅 35/39 正 Setpoint、最大空档 0.616 s，故障守卫 15/15 Setpoint 与 13/13 PID 零。该反事实本身没有上位机状态，不是可部署修改；不据此推进产品异步监测重构。目标平台同次输入—决策—输出剖析和完整任务仍未完成，现场许可 `false`。

> **巡检 PID 接收来源时效修复（2026-09-28）**：[独立报告和 DDS 原始摘要](AUV-Master-Mag/docs/v2/INSPECTION_PID_RECEIVED_SOURCE_GATE_20260928.md)在巡检专用 PID 增加默认关闭的正向 Setpoint header 来源年龄门，并接入候选 launch。隔离墙钟 DDS 同一控制器先以来源年龄 1.030 s 的旧正向消息输出零推、再以 0.030 s 新消息输出 13.53% 推力；源码/安装版同 SHA，定向 17/17、包目录直接 pytest 98/98。`colcon test` 初始因过旧的安装版 `auv_common` 缺少 IMV1 在收集阶段失败；重建 `auv_common` 后标准整包测试 98 项、0 错误/失败/跳过。此项未接算法、桥、PC104 或完整任务，现场许可仍 `false`。

> **低速／来源接收时效负结果（2026-09-28）**：[独立报告与宋体时序图](AUV-Master-Mag/docs/v2/INSPECTION_LOW_SPEED_CLOCK_ENVELOPE_20260928.md)记录 0.2 m/s、1.3 s 候选门四条独立短诊断均未过严格总门；唯一健康供数达标的仿真墙钟夹具为 24/42 正 Setpoint、最大空档 0.325 s，故障保护窗 16/16 Setpoint 与 9/9 PID 零。独立 DDS 观察端的 63 条正向消息中 9 条到达时来源年龄超过 1.3 s，最高 1.757 s。非仿真运行合成标定被既有身份门正确拒绝。[现场同次时序包](AUV-Master-Mag/docs/v2/INSPECTION_SAME_SESSION_TIMING_ENVELOPE_20260928.md)现升 schema 2，增加正向最终 Setpoint 的接收端来源年龄检查，构造单测 6 项通过。产品算法和默认 launch 未采用低速候选；无完整任务、桥、PC104 或实艇同次证据，现场许可 `false`。

> **目标平台同次时序验收入口（2026-09-28）**：[现场时序包合同、空白清单与审计脚本](AUV-Master-Mag/docs/v2/INSPECTION_SAME_SESSION_TIMING_ENVELOPE_20260928.md)补上健康段输入来源年龄/监督周期/ROS-PID-UDP-PC104 输出最大空档和故障后持续零命令的可执行检查。构造正例及旧来源戳、漏速、板端不一致/篡改负例通过工具单测；诊断包装器在无输入 ROS 节点记录 259 周期。现场清单仍空，`field_release_authorized=false`；同次真实目标、完整任务、物理板端和运动包仍未验收。

> **监测发布分层反事实（2026-09-28）**：[逐消息时序图与独立报告](AUV-Master-Mag/docs/v2/INSPECTION_MONITOR_PARTITION_LIMIT_20260928.md)确认长回调中完整状态发布可占 274/343 ms；隔离诊断进程让 63 次正常轨迹状态入口中 50 次跳过完整监测，同时每次保留 Hold 预算状态。唯一健康供数通过门的运行（46 次、最大间隔 0.184 s）最终 Setpoint 仍仅 27/40 正向、最大空档 0.318 s，严格门失败；前三次供数失约，不作分频收益比较。正式节点和 launch 未采用该诊断分频，现场许可 `false`。

> **节拍／最新值队列反事实（2026-09-28）**：[独立报告、图与原始哈希](AUV-Master-Mag/docs/v2/INSPECTION_CADENCE_QOS_ENVELOPE_20260928.md)新增 0.2/0.4 s 决策与监督门最新值输入五趟独立短探针，四趟供数最大间隔小于 0.25 s，但五趟最终 Setpoint 都含零速、严格总门均失败；最佳正向 34/40、最大输出空档 0.415 s。原健康窗从首次任务发布起算，包含建链时间；回顾性去除首 1 s 后五趟仍非全正向。试验性监督门最新输入 QoS 开关已撤回，源码快照保留，安装版与源码回到前版同哈希。目标平台同次时间轴和完整任务仍需验收，现场许可 `false`。

> **可恢复输入与来源授权候选（2026-09-28）**：[独立报告、原始事件和图](AUV-Master-Mag/docs/v2/INSPECTION_RECOVERABLE_SOURCE_AUTHORITY_20260928.md)将算法决策起点的输入快照、短暂导航缺口的有预算 Hold、导航／磁测原始时间戳检查及独立最终 Setpoint 门组合为默认关闭的候选。旧门在延迟旧导航到达时曾有一条故障守卫窗正向漏放；增加来源戳后两趟分别 23/23、16/16 Setpoint 零输出。最终无追踪运行在故障守卫窗 Setpoint 15/15、PID 6/6 零，恢复 28/34 正向；但健康供数最大空档 0.349 s、最终输出最大空档 0.512 s，严格连续性门失败。结果目录 14 趟全为 `passed=false`、105 文件哈希已登记，ROS 包 93/93；无桥/PVS/UDP/PC104/实艇同次验证。现场许可 `false`，不能声称 10 Hz 持续巡检。

> **双进程 Setpoint 来源门候选（2026-09-28）**：[独立负结果报告](AUV-Master-Mag/docs/v2/INSPECTION_TWO_RATE_SETPOINT_GATE_20260928.md)新增默认关闭的算法候选→独立输出门→既有 Setpoint 接口，限制候选 0.35 s、传感器 0.5 s、预算 1.5 s，保留原始候选 header stamp。门槛单测及 ROS 包 87/87 通过；最终严格单独 ROS smoke 的失鲜/预算稳定段零输出，但健康 3 s 仅 20 条正输出、最大空档 0.472 s，未过最少 24 条／最大 0.3 s 门。三进程协方差检查版健康段仅 6/36 正向，最大空档 0.806 s；先前 13/26 及首正向前锁存负例同样保留。旧 launch 与历史结果未改。不能据此宣称 10 Hz 巡检、PVS/PC104 或实艇停车通过，现场许可 false。

> **CPU 包络续证（2026-09-27）**：[线程 CPU/墙钟诊断图与独立报告](AUV-Master-Mag/docs/v2/INSPECTION_TELEMETRY_CPU_ENVELOPE_20260927.md)显示回调长尾主要实际占用 CPU。试验性 0.5 s 完整监控节流在前三次短探针中仍未过严格健康门；其中 29/32 正 Setpoint 的八核对照还连带降频了 Hold 预算，不能视作安全改善。将预算恢复逐周期后，输入缺口最大 0.233 s 的八核对照仅 2/32 正 Setpoint、最大空档 1.143 s。该未通过的产品开关已撤回，只保留诊断脚本、图和原始数据；现场许可不变。

> **巡检桥 Setpoint 来源时效候选（2026-09-27）**：[独立报告与图](AUV-Master-Mag/docs/v2/INSPECTION_BRIDGE_SETPOINT_PROVENANCE_20260927.md)记录安装版专用桥新增 0.5 s 上游决策新鲜度门。本地 UDP 回环中，新鲜 Setpoint/PID 给 25% 主推，Setpoint 失鲜或 Hold 而 PID 仍新鲜为零，命令保活也为零；包级 84/84。安装版 5 s ROS/PID/桥/PVS 短试因 DDS 投递超时没有完整结果，源码节点的另一短试又因导航失鲜保守撤权；均不能当连续运行通过或 PC104/实艇停车证据。路径 1→3 的磁场形/埋深许可与此执行门独立，现场许可 false。

> **独立 ROS 进程连续性负证据（2026-09-27）**：[墙钟短探针、回调时序图与逐消息原始记录](AUV-Master-Mag/results/v2/inspection_process_wallclock_20260927/README.md)。安装版算法与 PID 分进程、静止合成输入 10 Hz、健康 5 s／失鲜 3 s／恢复 4 s；初版验收过松的 `true` 已明确作废。5 s 传感器预热＋CPU 3–5 亲和性复跑中，夹具供数最大缺口 0.366 s、Setpoint 1.120 s；一次 0.790 s 决策使导航年龄从 0.323 增至 1.114 s，触发失鲜锁存。[逐事件审计](AUV-Master-Mag/results/v2/inspection_process_wallclock_20260927/observable_command_tail_audit.json)显示最后正向 Setpoint 至首条零 Setpoint 1.013 s，至夹具收到首条零 PID 1.188 s，中间三条正 PID（两条在零 Setpoint 接收后；不能据此断言控制器收到零指令后仍计算正推力）。将 PID 时效参数独立改为 0.5 s、长状态发布降为 1/5、双线程诊断反事实均未构成产品修复。较早空闲复跑故障守卫窗 18/18 Setpoint 与 13/13 PID 零输出。无 PVS/UDP/PC104/实艇，不能作为连续运行合格或现场许可。路径 1→3 中间场形埋深拒绝定向回归 1/1 通过，历史 5600 次结果未改。

> 本文件是 `AGENTS.md` 分流后的 Linux 侧主索引。**每次上下文清理/重置后，即使不是第一次进入，也必须完整读完本文件**，以在不重复探索的前提下恢复目标与约束。
> 维护约定：本文件既要「概括」又要「行号对应」（`文件#Lxx-Lyy`），以便精准跳读；发现新关键位置随时补行号。目标体量 ~50KB，高度专业化的子内容分流到子文档并在此登记路径。
> 最后更新：2026-09-29（条件性稳健性与170页论文／PPT资产完成；真实部署另验）

> **运行资源条件续证**：[短探针诊断与图](AUV-Master-Mag/results/v2/inspection_wait_bound_20260927/README.md)把一次高负载拒止定位为进入决策前导航年龄约 0.10 s、决策后 1.10 s，越过候选 0.5 s 门；其后 13/13 周期本地 UDP 主推为零。另一次同配方短运行没有复现，函数级剖析平均约 73 ms/决策。两次都只覆盖搜索开头，不是完成样本或目标 Jetson 时序验收；产品门限保持不变，图 63 冻结结果未改。

> **突变流提前撤权候选**：[图 63 与独立报告](AUV-Master-Mag/docs/v2/INSPECTION_TRACK_TRANSIENT_WITHDRAWAL_20260927.md)把 4 s 横向扰动代理变化门设为 opt-in；安装 ROS/PID/守卫/UDP/PVS 同版三条完整合成任务中，稳态反向流和正向阶跃完成 80 m，反向阶跃于 848.5 s 撤权，比旧门早 35 s。撤权后 241/241 周期三层零命令仍于 897.25 s 物理越出合成 ±2 m 巡检带。追加稳态正向流高负载尝试因导航墙钟失鲜被保守拒绝；ROS 包首次 80/83；仅修正合成测试时序后独立 domain 复跑 83/83，产品导航失鲜撤权未改变。候选门限回顾性选择，物理导航、流速、处置与 PC104 证据未完成，现场许可 false。

> **任务终态输出续证**：[图 62 与独立报告](AUV-Master-Mag/docs/v2/INSPECTION_TASK_OUTCOME_OPERATOR_20260927.md)把有限路线到端、深度许可和桥执行许可分层显示；同版安装 ROS/PID/守卫/UDP/PVS 两条合成任务分别得到正常 SOFTWARE_ROUTE_COMPLETE 与反向流 SUSPENDED，故障 241/241 周期三层零命令，埋深均空。桥与上位机各 1.5 s 失鲜转未知，不沿用旧完成标签。正常到端末样本 PVS 仍约 0.304 m/s，任务到端不等于艇停。ROS 包 83 项、上位机状态视图 5 项通过，图 62 已入发布页、论文/PPT；现场物理验收仍缺，许可 false。

> **显式流速预算与飞越 Hold 时基续证**：[图 61 与独立报告](AUV-Master-Mag/docs/v2/INSPECTION_ROUTE_FINITE_CURRENT_CLOCK_20260927.md)在独立合成配置中声明 0.05 m/s 流速上界、30 s Hold 和 19.6 m 所需净距；同版安装 ROS/PID/守卫/UDP/PVS 的稳态正反流各 3 个磁噪声种子均完成 80 m，突加反向同幅流却在 883.5 s 因 2.009 m 路线横偏撤权，913.5 s 按仿真时钟请求上级处置，60 s 零推力仍漂移 5.683 m。ROS 包 80 项通过。图 60 默认配置无 Hold 流速预算，与图 61 不可混同；磁种子不代表海况概率，物理流速、PC104、实艇滑行和上级动作仍缺，现场许可 false。

> **共同错线目标关联补项**：[图 56 的邻源敏感性](AUV-Master-Mag/docs/v2/INSPECTION_MAGNETIC_ISOLATION_LIMIT_20260927.md)说明单峰/高置信度不等于目标身份；[图 57 的独立局部目标锚点](AUV-Master-Mag/docs/v2/INSPECTION_RUNTIME_TARGET_ASSOCIATION_ANCHOR_20260927.md)在安装版 ROS/PID/守卫/UDP/原生 PVS 同次三组对照中，把偏移地图下声磁共同锁错的误完成改为 Confirm 拒绝，真实单源保持 80 m 完成。非仿真运行时声呐新增任务/目标绑定的物理锚点清单启动门，物理来源仍须人工/现场验收；现场许可 `false`。逐例原始哈希见 `data/57_runtime_target_anchor_joint_wrong.json`。

> **近邻可分辨性续证**：[图 58 的目标专属走廊](AUV-Master-Mag/docs/v2/INSPECTION_TARGET_EXCLUSIVE_CORRIDOR_20260927.md)揭示锚点相交仍可能放行 $6.6\pm0.5$ m 近邻；新 opt-in Confirm 要求声呐整条 2σ 区间落入独立调查证明无邻线的走廊。三条合成磁算法扫描及另三条同版安装 ROS/PID/守卫/UDP/原生 PVS 对照，均显示旧门误放近邻、新门拒邻线并许可真目标；该阶段非仿真锚点清单为 schema 2，旧 schema 1 拒绝。图 57 是旧门全链历史快照，图 58 解释几何，当前版全链原始哈希见 `58_target_exclusive_corridor_ros_pvs_audit.json`；物理调查缺失，现场许可仍 `false`。

> **Track 身份连续性续证**：[图 59 与独立报告](AUV-Master-Mag/docs/v2/INSPECTION_TRACK_IDENTITY_ROUTE_CORRIDOR_20260927.md)发现仅 Confirm 有走廊仍可在 Track 中接收近邻改指并继续给目标速度 338 周期／84.5 s；当前 opt-in Track 每次有效声呐更新核对全程专属走廊，安装 ROS/PID/守卫/UDP/PVS 同版负例首周期撤权、后60 s 241/241 周期三层零命令，正常目标仍完成80 m。上界缩到6.50 m 则真目标于623.5 s误拒。非仿真锚点清单现为 schema 3，专属调查必须覆盖 Confirm 与完整路线；图 58/schema 2 为前一阶段快照，图59原始哈希在 `59_track_identity_route_corridor.json`。物理调查及停车包缺失，现场许可 `false`。

> **有限 Track 路线偏差续证**：[图 60 与独立报告](AUV-Master-Mag/docs/v2/INSPECTION_ROUTE_ONLINE_DEVIATION_20260927.md)把既有最大横偏阈值由终点裁决前移到巡检首次越界：同版安装 ROS/PID/守卫/UDP/原生 PVS 单种子零流及追加0.04 m/s 横流均完成80 m；追加0.40 m/s 强横流时，850 s 横偏2.020 m首周期撤权，后60 s 241/241周期三层零命令仍漂移23.531 m、907.5 s越出合成边界。该组三例默认 YAML 未配置 Hold 海流预算，`RECOVERY_REQUIRED` 原因是 `hold_budget_unconfigured`，不能借用另一候选0.05 m/s界。横偏是相对冻结估计线而非真实缆距，现场执行包和流速上界未验收，许可 `false`。三例原始哈希见 `60_route_deviation_withdrawal_and_drift.json`。

> **最新磁巡检候选索引**：[`INSPECTION_SHALLOW_SURVEY_ROS_PVS_CHAIN_20260927.md`](AUV-Master-Mag/docs/v2/INSPECTION_SHALLOW_SURVEY_ROS_PVS_CHAIN_20260927.md)（图 51：新 opt-in `shallow_survey` 经 ROS/PID，正向与故障例还经守卫/UDP，完成三／四横切、接入和有限 Track；逐例数据与源码哈希见报告）。先前图 47/48 的[扫描与预算](AUV-Master-Mag/docs/v2/INSPECTION_SHALLOW_ZIGZAG_PVS_ENVELOPE_20260927.md)、图 49 的[出口奇偶性](AUV-Master-Mag/docs/v2/INSPECTION_SHALLOW_ZIGZAG_EXIT_PARITY_20260927.md)、图 50 的[隔离 PVS 接入](AUV-Master-Mag/docs/v2/INSPECTION_SHALLOW_ZIGZAG_PVS_REJOIN_TRACK_20260927.md)保留为阶段证据。新链的目标声呐区间与横流仍由真值夹具生成，未接物理 PC104；非仿真启动拒绝，现场许可仍为 `false`。论文第 5 章已引用图 47–52；进度细节见 `毕业设计写作文档/dashboard.md` 顶部。

> **最新收口与连续性索引**：[已知目标首验／宽先验研究的剖面决策](AUV-Master-Mag/docs/v2/INSPECTION_V2_FIELD_FIRST_PROFILE_20260927.md)、[图 52 的 Hold 双时基与 300 s 持续零输出](AUV-Master-Mag/docs/v2/INSPECTION_SHALLOW_SURVEY_HOLD_CLOCK_20260927.md)。旧图 51 与三种子为时基修正前源码快照，原始结果不覆盖；当前源码在加速仿真 30.0 s 请求上级处置，修正后正向正常任务 CSV 与图 51 正例完全一致。图 52 已入 thuthesis／PPT 建议；ROS 包 66 项测试通过。**请求恢复不等于上级动作或实艇停住**，现场许可仍为 `false`。

> **横流输入偏差续证**：[图 53 与独立报告](AUV-Master-Mag/docs/v2/INSPECTION_SHALLOW_SURVEY_CURRENT_BIAS_20260927.md)在同版合成 ROS/PID/协议/PVS 中固定真横流 $0.040$ m/s，只改变决策消息；低报 $0.005$ m/s 完成 Track，低报 $0.020$ m/s 在接入长度耗尽后 Hold、61/61 周期零命令、PVS 仍滑行约 2.82 m。严重偏差超出自报 2σ，入口门不能自己识别；图 53 已入论文和 PPT 备份，S 剖面仍只作仿真研究，现场许可 `false`。

> **静态目标清单续审**：[任务配置绑定报告](AUV-Master-Mag/docs/v2/STATIC_TARGET_PRIOR_MISSION_ENVELOPE_20260927.md)将无运行时声呐的非仿真 F 剖面清单升级为 schema v2，固定整份加载的 `cable_tracking` 配置（排除清单自引用）。改边界、飞越终点或控制速度会拒绝启动；任务消息改／省略目标深度或速度会拒绝接令；旧 v1 清单也拒绝。安装文件与源码一致，ROS 包 66 项测试通过；论文/PPT 已同步。物理地图真伪与实艇验收仍缺，现场许可 `false`。

> **静态清单 ROS 接线**：[墙钟 DDS 独立探针](AUV-Master-Mag/docs/v2/INSPECTION_STATIC_PRIOR_ROS_DDS_20260927.md)由安装空间加载 v2 节点，合成 schema v2 清单下经 DDS 拒绝错速任务、接受匹配任务；改搜索边界后的第二次启动失败。原始输入与源码哈希在报告中，`use_sim_time=false`；没有导航、控制器或 PC104，不是实际航行。论文/PPT 已同步，现场许可仍 `false`。

> **地图偏移与正向恢复**：[图 54 静态窄地图偏移反例](AUV-Master-Mag/docs/v2/INSPECTION_STATIC_HINT_BIAS_20260927.md)显示 1.1 m 偏移使单源拒绝、融合邻源准入；[图 55 运行时声呐主导授权](AUV-Master-Mag/docs/v2/INSPECTION_SONAR_MAP_BIAS_RECOVERY_20260927.md)在同一合成偏移下完成正确单源 80 m Track、拒绝邻源，并在线索失鲜后 61/61 周期零命令。新开关默认关闭，目标声呐线与概率均为夹具；现场仍须真实目标关联与物理标定。独立磁包已提供 `setup.py` 并在本机系统 Python editable 安装，`brain_linux/README.md` 记录无临时 `PYTHONPATH` 导入 smoke。图 55 已入论文/PPT；现场许可 `false`。

---

## 0. 一句话目标（Prime Directive）

把一台四年前「上位机纯遥控」的老 AUV，升级为满足 **海上风电海底电缆自主巡检** 的战略平台，并据此完成一篇**高度工程化但具备扎实创新点**的清华专硕毕业论文。**本对话（Linux 侧）的核心职责 = 完成论文主体写作与实验佐证**，把毕设推进到 pass 2（见 §5 进度语义）。

关键判据（写作 baseline）：**实验结果服务于写作，不能让指标凌驾于逻辑之上**。既不滥用「首创/第一次」，也不回避真正的创新点。面向清华教授要能拿高分。

---

## 1. 指令 Prompt 与作者背景

### 1.1 主 Prompt 位置
- **主计划书**：[毕业写作完善计划.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/毕业写作完善计划.md)
  - 项目定位与分工：`#L1`
  - 老架构代码位置（C# 上位机 / VxWorks）：`#L3`
  - Jetson 主线 + protocol_udp/zenoh + pvs/holoocean 说明：`#L13`
  - 更新版 VxWorks（`csd_vx6.8_lastest`，新增安全机制/可被 Jetson 控制/水池分级部署）：`#L14`
  - 两个 submodule（电缆声磁跟踪算法库 + 硬件 wrapper）说明：`#L15`
  - `docs/thesis/paper` 素材现状与已知问题（只报指标/堆补丁/风格不统一）：`#L17-L29`
  - 附件目录清单：`#L33-L36`
  - **预备操作清单（本阶段任务源）**：`#L40-L56`
  - **协作/写作操作清单**：`#L58-L67`
  - 落盘规范（`01new_` 前缀、未完成/核心中间进度同步分流、图片相对路径）：`#L71-L85`
  - 建议起点：从第五章 + 上下文全面审核与衔接开始：`#L87`
- **无 ROS 辅助侧计划**：[毕业写作无ROS辅助完善计划.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/毕业写作无ROS辅助完善计划.md)（macwin 侧职责：检索/文献/浏览器/电脑操纵）
- **顶层分流**：[AGENTS.md](file:///home/auv_user/auv_ws/AUV-Master-Project/AGENTS.md) → `uname` 返回 Linux 读本文件；Darwin 读 `AGENTS_macwin.md`。

### 1.2 作者背景
- 作者：谢冠文 <xgw24@mails.tsinghua.edu.cn>，清华专硕，2026 年 8 月。
- 分工：本人负责 **控制、软件基础、电路、传感器选型、电磁屏蔽**；**声呐及声呐相关加工由丁同学负责**；整个大项目是中航天佑张师兄（工程博士）的课题，本毕设是其中「控制/软件/感知」这条主线。
- 详细心路历程与 Q&A 背景：[AI对话记录——了解背景信息.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/AI对话记录——了解背景信息.md)（~773KB，可用 `Q&A` 序号精准定界；线级索引见 §6.4）。

---

## 2. 已形成的原则（Principles）

1. **目标导向 + 上下文回归**：每次上下文重置后必读本文件与 `dashboard.md`；不做无意义的重复扫描。
2. **写作优先于指标**：结果服务论文逻辑；补实验是为了佐证/填逻辑断点，不是堆数字。
3. **创新点表述克制而不回避**：少用「首创」，但清晰立住真正创新（降维反演、UA-MPC、双脑异构、磁卫生布局等）。
4. **改动的奥卡姆剃刀 + 正交性**：欢迎创新性更改，但**严禁未经授权、会使已有实验失效的更改**；改动须最小、与既有实验正交（详见 [rating.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/rating.md)）。
5. **写作 / 实验严格隔离**（用对话分支）：
   - 新增实验且**未获批准** → 落盘 [毕业设计写作文档/未完成内容/](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/未完成内容)（或落到代码仓库 `results/` 后软链接至此）。
   - 实验**符合预期、无 WIP** → 落盘 [毕业设计写作文档/核心中间进度同步/](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/核心中间进度同步)。
   - 写作支线读取「特定 scope」实验结果前，先反馈：结果是什么、达成什么目的。
6. **图片一律用 markdown 相对路径引用**；占位符必须对 Ctrl/Cmd+F 友好（唯一、可检索）。
7. **架构图 → drawio（宿主机执行）**：容器内不生成 drawio，改为写「严格自包含的图描述文本」（元素/相对位置/上下文/约束具象化）+ markdown 明确占位符，转交宿主机或另一 AI 复现。
8. **落盘前缀规范**：旧 AI 初稿用 `01_`、`02_`…；新写作用 `01new_`、`02new_`… 前缀，纳入更高 level 推演 + 实物 spec + 「做了什么/为什么/仿真&实物结合」。
9. **不在根目录新建散文件**；专业化内容分流到子目录并在本文件登记路径。
10. **环境噪声**：Shell 命令常伴随 `crashpad/prctl` WARNING，属无害噪声，可忽略/过滤（`| grep -v prctl | grep -v crashpad`）。

---

## 3. 文件阅读方法与契约（多格式）

已确认的稳定读取方式（**本容器内无 pdftotext/poppler/pymupdf/pdfplumber/pypdf/python-docx**；已安装：pandoc、ghostscript、pandas、matplotlib、PIL）：

| 格式 | 方法 | 备注 |
|------|------|------|
| `.md` / `.txt` / 代码 | Read 工具；结构用 `grep -nE "^#{1,3} "` | 首选 |
| `.pdf`（文本层） | `timeout 60 gs -sDEVICE=txtwrite -dFirstPage=A -dLastPage=B -o /tmp/x.txt "<pdf>"` 再 Read `/tmp/x.txt` | **必须加 `timeout` 且限页**，大 PDF 全量会卡住；中文可正常抽取（已验证 DL/T1278、TMR8637 spec） |
| `.pdf`（扫描/图纸） | 无 OCR；按计划 §L85「CAD/PCB 等专有格式选读」处理，必要时截图/交宿主机 | 图纸类多为矢量，txtwrite 可能仅出图框文字 |
| `.docx` | `pandoc -t plain "<file>.docx"` | 已验证（采购清单读取正常） |
| `.png/.svg/.jpg` | Read 工具（多模态直接看图） | 架构图/结果图 |
| `.drawio` | 视为 XML 文本 Read；或看同名 `.png/.svg` | |
| CAD (`.dwg` 等)/PCB/`.docx` 图纸 | 选读，优先看 `图纸PDF版` 里的 PDF | |

> `tools/convert_to_pdf.py`（计划 `#L21` 提及、须在 `docs/` 下运行）**当前路径下未找到该脚本**（`tools/` 下现存的是 `plot_*.py`、`dlt1278_cable_report.py` 等出图/报告脚本）。→ 记入待澄清项（见 §7）。

---

## 4. 目录地图与关键文件（含行号锚点）

### 4.1 论文写作根目录 `毕业设计写作文档/`
- [研究生毕业设计初稿.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/研究生毕业设计初稿.md)（2284 行，含大量 AI 口水话；结构见 §6.1）
- [AI对话记录——了解背景信息.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/AI对话记录——了解背景信息.md)（背景 Q&A，§6.4）
- 子目录（预备阶段**均为空**，待按 §2.5 规范填充）：
  - `未完成内容/`、`核心中间进度同步/`、`潜在待完成事项/`、`相关插图（架构图）/`、`参考文献/{文献PDF,文献引用信息}/`

### 4.2 论文素材 `docs/thesis/`（旧 AI 初稿 + 图）
- 过程日志 `00_overview.md` … `16_cable_dlt1278_scoring_and_operator_products.md` + `INDEX.md`
- **正文章节 `docs/thesis/paper/`**（写作主战场）：
  - [01_background_and_significance.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/01_background_and_significance.md)
  - [02_system_design.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/02_system_design.md)
  - [03_state_estimation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/03_state_estimation.md)
  - [04new_decision_and_control.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/04new_decision_and_control.md)（canonical；旧 04 仅作历史对照）
  - [05new_experiments_and_discussion.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/05new_experiments_and_discussion.md)（canonical；约 93KB；结构见 §6.2）
  - [06_conclusion_and_outlook.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/06_conclusion_and_outlook.md)
  - [A_appendix_implementation_and_data_index.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/A_appendix_implementation_and_data_index.md)
  - 附属：`INDEX.md`、`e2e_distorted_prior_next_plan.md`、`experiment_gap_and_next_plan.md`、`pvs_extreme_cable_scenarios.md`
- 图目录 `docs/thesis/figures/`：`architecture/`（drawio+png+svg 多份系统图）、`cable_acceptance/`、`console_operator_video/`、`experiments/`、`terrain_following/`
- 其他 docs 入口：[docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md)、[docs/JETSON_DEPLOYMENT_CONTEXT.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/JETSON_DEPLOYMENT_CONTEXT.md)、`docs/prompt.md`、`docs/real_deployment/`、`docs/user-guide/`、`docs/internals/`

### 4.3 附件与参照 `相关附件和参照/`
- `原始AUV类核心文档/`：VxWorks最新协议.md、软件通信协议.md、程序实现.md、设计方案2021.5.28.md、湖上试验大纲.md、`MCU 程序（STM32）/`、`图纸等更细节硬件spec/图纸PDF版/{第一..四册}`
- `原始AUV部分潜在技术细节/`：VxWorks最新协议.pdf、`csd_vx6.8_lastest/`、BMS电池监控、主推电机、北斗gps资料、SMCL舵机、3DM-GX3-25(电子罗盘)协议 pdf、能源变换/MCU 模块等（**高度专业化，选读**）
- `本人新增传感器类/`：**TMR8637技术规格.pdf**（磁传感器，实测 TMR8607 芯片系）、`ADC以太网转换器FK2301/`
- `相关国家标准和行业论文/`：**DL/T 1278—2025 海底电力电缆运行规程.pdf**、T/CSGPC、GB/T 17502-2009、海缆探测技术选型、国际巡检规范、《海底电缆巡检运维管理规范》、`重要国家标准/`
- `考核和阶段性同步文件/`：采购清单 docx（第一批 9562.3 元 / 第二批 5368 元）

### 4.4 代码大本营（软件基地，仅供写作抽象，勿改坏）
- Jetson 主线：`brain_linux/`、`algorithm/`、`common/`、`config/`、`scenarios/`、`scripts/`、`sim_holoocean/`、`tests/`、`tools/`
- 仿真结果 `results/`（写作数据源，规模见 §6.3）
- 老架构：`console_soft/csharp`（C# 上位机）、`csd_vx6.8_lastest_bak`（旧 VxWorks）、`csd_vx6.8_lastest`（新 VxWorks，安全机制/分级部署）
- Submodules（`.gitmodules`）：
  - `AUV-Master-Mag` → 电缆声磁跟踪算法库（github 360ZMEM/AUV-Master-Mag）
  - `hardware_wrappers/fangkong_adc` → FK2301 ADC + 江苏多维 TMR8637 wrapper（github 360ZMEM/fangkong_adc）

### 4.5 本索引维护的产出文件（预备操作交付物）
- 本文件 `AGENTS_linux.md`
- [dashboard.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/dashboard.md)（进度看板，§5）— 待建
- [plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/plan.md)（实物部署功能缺口）— 待建
- [rating.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/rating.md)（负结果/风险/第一性更改登记）— 待建

---

## 5. dashboard.md 进度语义（速查）

以 **三级标题（无三级则退化到二级标题）** 为行目标，列：`章节 | pass | 缺失项 | 依赖前序任务 | 备注`。
- **pass 1** — 实验/写作信息仍需显著完善。
- **pass 2** — 大体完善，仅需润色/口径/参考文献。**← 本对话主目标止于 pass 2。**
- **pass 3** — 主体完成，主查前后一致性。
- 缺失项分类：1 图片 / 2 文字 / 3 实验 / 4 其他信息 / 5 参考文献。

---

## 6. 结构索引（行号锚点）

### 6.1 研究生毕业设计初稿.md（2284 行）
- 目录（暂定）`#L5`；参考文献 `#L239`；References `#L342`
- 第一章 绪论与文献综述 `#L109`（1.1 背景 `#L111` / 1.2 探测现状 `#L149` / 1.3 控制决策现状 `#L181` / 1.4 创新点 `#L203` / 1.5 组织 `#L215`）
- 夹杂大量 Q&A 段（Q109/A111 …）与「第二导师」写作点评，属背景对话残留
- 第二章 系统架构与多源感知建模（多份重复标题）`#L764 / #L1086 / #L1341 / #L1588`；全景回顾 `#L1734`
  - 2.1 需求/标准对齐 `#L766`；2.2 双脑硬件架构 `#L1088`；2.3 海缆磁场建模与降维反演 `#L1343`（核心解套 2.3.4 `#L1394`）；2.4 载荷标定/杆臂 `#L1590`；2.5 小结 `#L1661`
- 第三章 声磁协同融合状态估计 `#L1808`（3.1 引言 `#L1810`）
- **注意**：初稿中「第四章/第五章」目前多以「〔示例〕〔待回填〕」提纲形式出现（`#L227` 四章、`#L229` 五章），正文实体主要在 `docs/thesis/paper/04、05`。

### 6.2 docs/thesis/paper/05new_experiments_and_discussion.md（canonical，约 93KB）
- 5.1 平台与指标 `#L3`（5.1.1 虚实架构 `#L5` / 5.1.2 指标定义 `#L18`）
- 5.2 数字孪生场景 `#L26`（复杂海缆场景 `#L28` / 综合压力 `#L46` / 噪声注入 `#L50`）
- 5.3 硬件集成与标定 `#L54`（链路压力 `#L58` / 磁杆臂标定 `#L62` / 故障自救 `#L85`）
- 5.4 近底巡检与反演精度 `#L89`（大电流台 `#L93` / 实测磁场反演 `#L97`）
- 5.5 结果讨论与仿真到实物边界 `#L99`：已完成总表 `#L103` / Terrain 主结果 `#L130` / PID 地形消融 `#L170` / MPC 极端路径 `#L186` / ES-EKF 鲁棒性 `#L221` / UA-MPC 定位消融 `#L253` / 控制指标 `#L270` / UA-MPC 归因 `#L293` / 迁移性 `#L299` / DL/T 1278 验收 `#L307` / 端到端证据分层 `#L397`
- 5.6 缺失实验与讨论 `#L494`
- 5.7 极端场景 `#L506`（S-curve `#L510` / Hairpin `#L521` / Slope `#L532` / Buried Gap `#L543` / Cross Current `#L554` / Combined `#L565` / 代理环境 smoke `#L579`）
- 5.8 本章小结 `#L613`

### 6.3 results/（写作数据源，文件数）
`cable_ops_report/`(531) `control/`(526) `control_aggregates/`(342) `uncertainty_aggregates/`(99) `visual_feedback/`(55) `localization/`(35) `thesis_sweep_aggregates/`(27) `es_ekf_extrinsics/`(29) `mag_extrinsics/`(16) `tuning/`(14) `decision/`(7) `cable_tracking/`(1) `archive/`(155)

### 6.4 AI对话记录——了解背景信息.md（11792 行；Q1–Q129 / A1–A131）
> 文件过大，**禁止全量 Read/grep（会卡死）**。已用切分脚本 [split_ai_conv.py](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/工具/split_ai_conv.py) 按 Q/A 标记切成 17 个 ~45KB 块（输出到 `/tmp/ai_conv_chunks/`，含 `_INDEX_markers.txt` 全量行号索引 + `_MANIFEST.txt`）。需精读时按下表行号只读目标区间，或 `python3 毕业设计写作文档/工具/split_ai_conv.py` 重新生成分块。
> 定位法：所有 Q/A 都是 `## Qn` / `## Am`（注意 Q 与 A 编号有 +2 错位，如 Q129↔A131）。

Q/A 行号锚点（部分）：Q1`#L3` Q10`#L908` Q20`#L1829` Q30`#L2826` Q40`#L4019` Q50`#L4983` Q60`#L5720` Q70`#L6840` Q80`#L7589` Q90`#L8483` Q100`#L9331` Q110`#L10278` Q120`#L11047` Q129`#L11707`。

**主题图谱（写作最相关，按主题给行锚）：**
- **分工边界**（张师兄工程博士出资/陈老师总师人设/丁同学声呐）：A1 `#L20-L90`、A40 `#L4082`、A51 `#L5244`。
- **三层架构（上位机/Jetson/AMD）为何优于两层**：A4 `#L369-L397`、A73(双脑异步) `#L7157`、创新点一 `#L10193`。
- **三相电缆螺旋绞合磁场为何可测 + 声磁接力**：A14 `#L1251-L1298`、A124(1.87nT 含金量/三级演进) `#L11186-L11251`、A127(砂石掩埋不影响磁导率/埋深反演) `#L11427-L11468`。
- **磁标定（硬/软铁、椭球拟合、非正交性、杆臂）**：A66 `#L6588`、A93(杆臂改正 SOP) `#L8651-L8705`、A102(非正交) `#L9416`、A103(硬软铁椭球拟合) `#L9515-L9565`。
- **缩比模型合理性 / 坡莫合金·钢丝铠装屏蔽 / 剥洋葱实验**：A117(4mm vs 10cm 极限缩比恶劣工况) `#L10654`、A118(SWA 钢丝铠装采购) `#L10730`、A126(海缆解剖规程) `#L11349-L11389`。
- **宿舍/低成本磁实验台（双通道声卡生偶极子/三相、10A 电流台）**：A65(几何布局+真值标定) `#L6496`、A115(避开 50Hz) `#L10487`、A121/A122/A123(声卡三相) `#L10966 / #L11057 / #L11113`、A52(电缆选型 3 芯) `#L5325`。
- **Jetson 双脑（NVPModel 25W/散热/JTOP、UDP 桥接、接口）**：A28 `#L2637-L2721`、A27(AMD↔Jetson 连接) `#L2523-L2615`、A34(UDP 收发代码) `#L3236`、A105(六层软件全景) `#L9701-L9747`。
- **行为树 + 之字形搜索 + 不确定性触发**：A62(行为树草案/T-CSGPC 3.4 之字形) `#L6211-L6254`、A96(决策vs控制边界/模式切换门槛) `#L8938-L8975`。
- **安全自救（漏水/失联心跳/低电/失控 + VxWorks 兜底）**：A64 `#L6391-L6456`。
- **行业标准解构（DL/T1278、T/CSGPC、GB/T 17502/12327、IEEE 1120）**：A55 `#L5596`、A56(磁力仪硬指标/埋深精度) `#L5668-L5699`、A57(作业规程/评价) `#L5732-L5782`、A58(GB 国标) `#L5805`。
- **磁探测选型/隔离电源/ADC（Fluxgate、HSF-500、±15V 隔离、ADS1256、ENOB）**：A59 `#L5879`、A82(0.05nT 噪声矛盾) `#L7810`、A83(隔离电源三级) `#L7891-L7933`、A84(BOM) `#L7962`、A104(ENOB/空间走样/铠装涡流相移) `#L9596-L9668`。
- **论文骨架与写作方法论（6 章黄金结构 / 创新点包装 / 防流水账铁律）**：A90(6 章结构) `#L8431-L8472`、A91–A100(逐章目录+检索词) `#L8497 起`、A110(创新点三条+架构图工具链) `#L10124-L10205`、A128(四大升维突破口:主动感知/物理信息融合/模态拒止容错/Sim-to-Real 随机映射) `#L11503-L11533`、A131(2.2 节写作骨架+翻译矩阵) `#L11723-L11786`。

**durable 约束/第一性决策（写作/实验红线，与 rating.md 呼应）：**
- 三大边界（初稿 `研究生毕业设计初稿.md` `#L461/#L478/#L503`，源于此对话）：①声呐"拿来主义"剥离给丁同学；②软件安家于 Jetson+Mock AMD；③三相电缆+磁屏蔽"偷天换日"（核心突破）。
- 严禁"跨层污染"三层洋葱架构：A61 `#L6059-L6096`。
- 创新点须克制表述、指标合规优先于"能测到"：A73 `#L7147-L7157`、A106(平台化思维 vs 产品) `#L9792`。

---

## 7. 已完成 / 待改进实验 与 待澄清项

### 7.1 已有实验（来自 05 章）
Terrain Following（PID/MPC 地形跟随）、ES-EKF 多场景多种子鲁棒性、UA-MPC 定位/控制消融、DL/T1278 数字孪生验收、端到端 distorted-prior 边界、PVS 六自由度闭环恢复、磁杆臂/安装角标定、双脑链路实时性压测、故障注入自救。

### 7.2 计划书点名的薄弱点（→ 写作重点）
- 只报指标、缺原理与因果诊断；堆补丁导致前后矛盾/信息冗余；图风格不统一（第四、五章 matplotlib 图需全面审核 + 风格统一 + 关键消融补充，覆盖潜在未覆盖点/负结果/逻辑断点）。计划 `#L60-L67`。

### 7.3 待澄清项（TODO_CLARIFY，Ctrl+F 友好）
1. `tools/convert_to_pdf.py` 计划提及但当前仓库未见 → 是否已移动/重命名？（现用 gs+timeout 方案替代，见 §3）
2. HoloOcean 后端「不完全可用」，当前以 PVS 为准（计划 `#L13`）；写作中涉及 HoloOcean 的实验需标注可复现边界。
3. 初稿第四/五章为提纲，实体在 `docs/thesis/paper/04、05` → `01new_`…`05new_` 迁移策略需在 roadmap 落定。

---

## 8. 下一步（roadmap 摘要）

详见 `plan.md` / `rating.md` / `dashboard.md`。总路径：**从第五章 + 上下文的全面审核与衔接切入** → 建 dashboard 全量行级进度 → 逐章 `0Xnew_` 重写（High-level 推演 + 实物 spec + 仿真/实物结合）→ 图统一 + 关键消融补充 → 架构图文本化交宿主机。

### 8.1 完整 Roadmap（分阶段）
- **P0 预备（已完成）**：文件/目录存在性核对；PDF/docx 阅读契约（§3）；`AGENTS_linux.md` / `dashboard.md` / `plan.md` / `rating.md` 建立；AI 背景对话行级索引（§6.4）。
- **P1 第五章审核与衔接（当前起点，计划书 `#L87`）**：
  1. 精读 canonical `05new_experiments_and_discussion.md`，逐 5.x 小节比对 `dashboard.md` pass 值与缺失项，落实到行。
  2. 梳理「指标→原理→因果」链，识别逻辑断点/前后矛盾/信息冗余（计划书 `#L26-L27`）。
  3. 清点第 4/5 章所有 matplotlib 图 → 建立「图清单 + 风格差异表」（尺寸/字号/配色/坐标），为统一做准备。
  4. 把 §5.6 缺口 + §7 责任边界回填进 `rating.md` A/B 表（已初步完成，精读后补细）。
- **P2 逐章 `0Xnew_` 重写**：01→05 顺序，每章融入 High-level 推演 + 实物 spec（附件 §4.3）+「做了什么/为什么/仿真&实物结合」；创新点表述走 §2.3 baseline。
- **P3 图统一 + 关键消融补充**：matplotlib 风格契约落地；补 dashboard 标 pass1 且缺「实验(3)」的行（新增实验走写作/实验隔离，落 `未完成内容/`→批准后 `核心中间进度同步/`）。
- **P4 架构图文本化**：按 §2.7 写自包含图描述 + Ctrl+F 友好占位符，交宿主机 drawio。
- **P5 参考文献 + 一致性（pass3 收尾，超出本对话主目标）**。

### 8.2 立即下一步（本对话续作建议）
正文读取与后续迁移统一从 `docs/thesis/paper/04new_decision_and_control.md`、`05new_experiments_and_discussion.md` 开始；无 `new` 后缀的 04/05 只用于历史差异追溯，不再作为事实源。

### 8.3 预备操作交付物核对（P0 DoD）
| 交付物 | 计划书条目 | 状态 |
|---|---|---|
| 文件夹/文件存在性确认 | `#L42` | ✅ |
| 多格式阅读契约 | `#L43` | ✅（§3；`convert_to_pdf.py` 缺失已记 §7.3） |
| `AGENTS_linux.md`（行号对应，~50KB） | `#L44-L47` | ✅ |
| `dashboard.md`（三级标题行/pass/缺失/依赖/备注） | `#L49-L54` | ✅ |
| `plan.md`（部署功能缺口） | `#L55` | ✅ |
| `rating.md`（负结果/第一性更改） | `#L56` | ✅ |
| 计划与 roadmap | `#L87` | ✅（本节 §8.1） |
