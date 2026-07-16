# VxWorks 源码最小侵入修复 Diff 说明（2026-07-15）

## 1. 本次修改文件

1. `csd_vx6.8_lastest/DataProcess.c`
2. `csd_vx6.8_lastest/SecurityEmergencyManage.c`

## 2. 修改补丁位置与行号

### 2.1 `csd_vx6.8_lastest/DataProcess.c`

#### 补丁 A：BUG-4 深度保护位回灌到状态快照

- 基本位置：`Current_state(_Current_State *temp)` 内
- 当前行号：`593-610`
- 关键行：
  - `596`：`temp->Current_Sys_Abnorm_Inf= Sys_Abnorm_Inf_Judgement;`
  - `604-610`：按 `Depth_Exceed_FromUI12_Depth_Para1/2` 计数补入 `0x00000200/0x00000400`
- 修改目的：
  - 修复 BUG-4 中“执行链已闭合，但导出状态快照看不到 Bit9/Bit10”的问题。
  - 让 `$AUV`/UI 读取的 `Current_Sys_Abnorm_Inf` 与软件深度保护计数保持一致。

#### 补丁 B：`Remote_Assignment` 一次性 emergency override

- 基本位置：`Remote_Assignment(_To_MCUFD *temp)` 前后
- 当前行号：`2657-2712`
- 关键行：
  - `2657-2661`：新增 `g_remote_assignment_output_override` 与 `Remote_Assignment_Set_Output_Override(u8 enable)`
  - `2698-2708`：新增一次性 override 消费逻辑
  - `2711` 起：仅在 `preserve_existing_output == 0` 时才用 UI/LORA shadow 重建执行器字段
- 修改目的：
  - 修复 BUG-5/BUG-6 中 `Remote_Assignment()` 用 UI shadow 覆盖应急/自救主推与舵面的行为。
  - 保留常规 remote 打包语义，只对单次应急发送生效。

#### 补丁 B-2：DVL 保护位不再被 MCU 回报码 `else` 清掉

- 基本位置：`Unpack_Data_From_FMCU(u8 *temp_buf)` 内 `McuFD_Sys_Abnorm_Inf` 映射段
- 当前行号：`1148-1167`
- 关键行：
  - `1148-1153`：新增 Doxygen 注释，明确 Bit11/12/13 为软件仲裁主导
  - `1154-1167`：保留 Bit11/12/13 的 MCU 置位镜像，去掉 `else` 清位分支
- 修改目的：
  - 修复 live 链路中 `Seafloor_Grounding_Arbitration()` 已置位 Bit11/12/13，但在 `$AUV` 导出前又被 `Data_From_FMCU.McuFD_Sys_Abnorm_Inf` 的 `else` 分支清掉的问题。
  - 让 DVL soft/hard/lost 三类软件保护位能稳定进入 `Current_State.Current_Sys_Abnorm_Inf` 并导出到 `$AUV`/UI。

### 2.2 `csd_vx6.8_lastest/SecurityEmergencyManage.c`

#### 补丁 C：应急发送包装函数

- 基本位置：文件头部函数声明区
- 当前行号：`23-33`
- 关键行：
  - `23`：`extern void Remote_Assignment_Set_Output_Override(u8 enable);`
  - `25-33`：新增 `Emergency_Remote_Assignment(_To_MCUFD *temp)`
- 修改目的：
  - 给安全/应急路径提供统一出口。
  - 在进入 `Remote_Assignment()` 前先打开一次性 override，避免应急输出被 UI shadow 覆盖。

#### 补丁 D：BUG-4 深度超限路径改用应急发送

- 基本位置：`EmergencyTask()` 深度超限两段分支
- 当前行号：
  - 第一段：`141`
  - 第二段：`172`
- 修改目的：
  - 保证 BUG-4 的自救主推/舵面按 `Instruction_To_FMCU` 当前值下发。

#### 补丁 E：Pool safety 路径改用应急发送

- 基本位置：`Pool_Safety_Check(void)` 内
- 当前行号：
  - `1459`
  - `1469`
  - `1479`
- 修改目的：
  - 保证池测安全路径下的停推/打舵输出不被 UI shadow 覆盖。

#### 补丁 F：DVL 丢底 / 硬阈值拉起路径改用应急发送

- 基本位置：`Seafloor_Grounding_Arbitration(void)` 内
- 当前行号：
  - `1558`：DVL lost lock 自救
  - `1643`：硬阈值拉起
- 修改目的：
  - 保证 DVL 自救输出的 `motor1` 与舵面按仲裁结果进入最终 `$MCUFD`。

#### 补丁 G：`EmergencyTask` 不再用 MCU `else` 清掉 DVL 软件保护位

- 基本位置：`EmergencyTask()` 内 `Data_From_FMCU.McuFD_Sys_Abnorm_Inf` 映射段
- 当前行号：`320-340`
- 关键行：
  - `322-327`：新增 Doxygen 注释，说明 Bit11/12/13 为软件仲裁位优先
  - `320-340`：保留 Bit11/12/13 的 MCU 置位镜像，去掉三段 `else` 清位
- 修改目的：
  - 修复 live 链路中 `EmergencyTask()` 周期性运行时，会把 `Seafloor_Grounding_Arbitration()` 刚置上的 Bit11/12/13 再次清掉的问题。
  - 让 DVL soft/hard/lost 三类软件保护位在主循环 + `NetSendTask` 的真实发送路径中稳定进入 `$AUV.sys`。

## 3. 本轮附加证据（未改 DVL 源码）

### DVL 字段注入对照

- 使用 Telnet 原始写地址分别对 `BD_*` 与 `WD_*` 进行注入。
- 结果：
  - `CASE_WD_ONLY`：`SYS=0x00000000`
  - `CASE_BD_ONLY`：`SYS=0x00001800`
- 结论：
  - `Seafloor_Grounding_Arbitration()` 当前运行时只认 `BD_Check/BD_Height`，不认 `WD_Check/WD_Depth`。
  - 因此 DVL 一侧本轮不需要修改源码，后续主要是 probe/注入方法统一到 `BD_*`。

### DVL live `$AUV` 可见性专项 probe

- 运行时观测到：
  - 注入 DVL soft 条件后，`Sys_Abnorm_Inf_Judgement` 可短暂变为 `0x00000800`
  - 但 `Current_State.Current_Sys_Abnorm_Inf` 与 `$AUV.sys` 仍保持 `0`
- 结合源码审计确认：
  - `DataProcess.c:1148-1172` 会按 `Data_From_FMCU.McuFD_Sys_Abnorm_Inf` 周期性维护 Bit11/12/13
  - 当 MCU 回报码尚未携带这些软件保护位时，旧逻辑中的 `else` 会把软件仲裁刚置上的位再次清掉
- 结论：
  - 这不是 probe 假象，而是 live 导出链路上的真实清位路径
  - 因此新增补丁 B-2 作为最小侵入修复

### DVL live `$AUV` 发送路径追加证据

- 运行时观测到：
  - `Current_State.Current_Sys_Abnorm_Inf = 0x00000800`
  - `To_UI12_Buf[126:129] = 00 00 08 00`
  - 但 live 抓到的 `$AUV.sys` 仍为 `0`
- 进一步验证：
  - 暂停 `EmergencyTask` 后，再做同样的 DVL soft 注入，live `$AUV.sys` 稳定变为 `0x00000800`
- 结论：
  - `DataProcess.c` 之外，`SecurityEmergencyManage.c` 中 `EmergencyTask()` 的旧 `else` 清位逻辑也是 live 发送链路的实际清位点
  - 因此新增补丁 G 作为最小侵入修复

### 补丁 G 烧录后追加复验证据

- 本轮重新烧录后，使用：
  - `sudo -n /usr/bin/python3 scripts/vxworks_dvl_runtime_probe.py --host 192.168.0.101 --execute --case all --capture-uplink`
- 直接结果：
  - `AFTER SOFT`：`Sys_Abnorm=0x00000800`，但脚本最终采到的 `$AUV.sys=0x00000000`
  - `AFTER HARD`：`Sys_Abnorm=0x00001800`，但脚本最终采到的 `$AUV.sys=0x00000000`
  - `AFTER LOST`：`Sys_Abnorm=0x00002000`，但脚本最终采到的 `$AUV.sys=0x00000000`
- 进一步追加时间序列 probe 后确认：
  - live `$AUV.sys` 并非始终为 `0`
  - 在 DVL soft 注入后，连续抓包能看到 `0x00000800 -> 0x00000000` 的短暂过渡
  - 同期内存观测为：
    - `Sys_Abnorm_Inf_Judgement` 初始为 `0x00000800`
    - 约 `0.2s ~ 0.3s` 后再次掉回 `0x00000000`
    - `DVL_Prase_Data.BD_Check = 0x40000000 (2.0f)`、`BD_Height = 0x40200000 (2.5f)` 全程保持不变
- 隔离实验结论：
  - 仅挂起 `NetRecvTask` / `UnpackNetDataTask`，该清位现象仍存在，说明并非下行网络包持续覆盖导致
  - 挂起 `EmergencyTask` 后，`Sys_Abnorm_Inf_Judgement` 可稳定保持 `0x00000800`，且 `UI_WIFI_Instruction.FromUI12_Ctrl_Mode` 不再从 `0xEE` 翻为 `0x01`
- 当前收口：
  - 最新板端行为已经证明：清位源仍位于 `EmergencyTask` 实际运行路径
  - 但该行为与当前工作区中补丁 G 落盘后的 `SecurityEmergencyManage.c` 源码表现不一致
  - 因此现阶段更准确的判断是：
    1. 要么板端镜像未实际带上补丁 G；
    2. 要么 `EmergencyTask` 运行路径中仍存在尚未覆盖到的等价清位逻辑
  - 在进入下一轮源码修改前，建议优先把“当前烧录镜像是否真实包含补丁 G”作为第一确认项，避免再次盲改、盲烧。

## 4. 说明

- 本文档中的行号基于当前工作区修改后文件重新编号。
- 当前已完成至少一轮包含补丁集的烧录与 live 复验。
- 截至本文档最新状态：
  1. BUG-4、BUG-5/BUG-6 已具备较强的实机闭合证据；
  2. DVL live `$AUV` 导出链已确认仍有未闭合点，且根因继续收缩到 `EmergencyTask` 实际运行路径；
  3. 单独 diff 文档与追加 probe 证据已经同步固化。
