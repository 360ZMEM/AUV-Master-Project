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

## 3. 本轮附加证据（未改 DVL 源码）

### DVL 字段注入对照

- 使用 Telnet 原始写地址分别对 `BD_*` 与 `WD_*` 进行注入。
- 结果：
  - `CASE_WD_ONLY`：`SYS=0x00000000`
  - `CASE_BD_ONLY`：`SYS=0x00001800`
- 结论：
  - `Seafloor_Grounding_Arbitration()` 当前运行时只认 `BD_Check/BD_Height`，不认 `WD_Check/WD_Depth`。
  - 因此 DVL 一侧本轮不需要修改源码，后续主要是 probe/注入方法统一到 `BD_*`。

## 4. 说明

- 本文档中的行号基于当前工作区修改后文件重新编号。
- 本轮尚未进行完整 VxWorks 构建/烧录验证；当前完成的是：
  1. DVL 字段级运行期证据补强；
  2. BUG-4 与 BUG-5/BUG-6 的最小侵入源码修复；
  3. 单独 diff 文档固化。
