# 可视化反馈闭环迁移记录 2026-07-05

## 1. 目标

本轮将磁探测工业化分支的工作重心迁移到可视化闭环，先验证两个入口：

- PySide6 上位机：确认能启动并生成截图。
- Foxglove 公网页面：确认浏览器工具可调用、可截图，并能推进到用户人工登录点。

## 2. PySide6 上位机截图

入口脚本：

```bash
python3 tools/gui_console_loop.py \
  --launch \
  --screenshot-only \
  --wait-seconds 1 \
  --output-dir results/visual_feedback/gui_pyside6_injection
```

本轮环境状态：

- `DISPLAY`: 未设置
- `WAYLAND_DISPLAY`: 未设置
- `pyautogui`: 已安装，但无 `DISPLAY` 时导入失败，表现为 `KeyError: 'DISPLAY'`
- fallback: `qt_offscreen`

已补齐上位机运行依赖：

- `pyserial==3.5`
- `configobj==5.0.9`
- `scapy==2.7.0`
- `pyautogui==0.9.54`

有效截图：

- `results/visual_feedback/gui_pyside6_injection/console_20260705_220037.png`
- `results/visual_feedback/gui_pyside6_injection/console_20260705_220237.png`

截图尺寸均为 `1400x900 RGB`。已确认截图内容为 PySide6 上位机主界面，包含实时监测区、控制面板、任务区、ESTOP、手动遥控、任务类型等区域。

安全边界：

- 未点击 ESTOP。
- 未点击自主授权。
- 未点击 mission/任务下发。
- 仅启动、渲染和截图。

## 3. Foxglove 浏览器流程

使用 MCP integrated_browser 工具完成：

1. `browser_tabs` 列出当前 tab，初始为空。
2. `browser_navigate` 打开 `https://app.foxglove.dev/`。
3. 页面自动跳转到 `https://app.foxglove.dev/signin?returnTo=%2Fdashboard`。
4. `browser_snapshot` 读取到登录页交互元素。
5. `browser_take_screenshot` 截取登录入口页面。

浏览器 View ID：

`bc29b8f9-e616-475e-8e84-dc0b5fcdf13f`

页面状态：

- URL: `https://app.foxglove.dev/signin?returnTo=%2Fdashboard`
- Title: `登录 | Foxglove`
- 可见登录方式：
  - Sign in with Microsoft
  - Sign in with SSO
  - 使用邮箱登录
  - 注册入口

安全边界：

- 未尝试绕过登录。
- 未输入账号或密码。
- 未修改云端 layout。
- 当前已停在需要用户人工登录的位置。

## 4. 当前结论

- PySide6 上位机截图闭环可用；当前无桌面会话时使用 Qt offscreen 渲染。
- `pyautogui` 已安装，但在没有 `DISPLAY/WAYLAND_DISPLAY` 的环境中不能用于真实桌面截图。
- Foxglove 浏览器工具链可用；已能打开公网 Foxglove 并截图登录页。
- 下一步需要用户在 browser view 中完成 Foxglove 登录，然后继续验证：
  - 是否能打开 dashboard/studio。
  - 是否能连接本机 Foxglove bridge。
  - 是否能导入或查看 `foxglove_layout_project/output/auv_layout.generated.json`。
  - 是否能看到 `/auv/sensors/magnetic`、`/auv/cable/tracking`、`/auv/cable/diagnostics`、`/auv/control/setpoint`。

## 5. 下一步命令

PySide6 重跑截图：

```bash
python3 tools/gui_console_loop.py \
  --launch \
  --screenshot-only \
  --wait-seconds 2 \
  --output-dir results/visual_feedback/gui_pyside6_injection
```

Foxglove 登录后继续检查时，优先用浏览器 MCP：

```text
browser_snapshot -> browser_take_screenshot
```

若进入桌面环境并存在 `DISPLAY`，再使用：

```bash
python3 tools/foxglove_public_loop.py \
  --url https://app.foxglove.dev/ \
  --wait-seconds 5 \
  --output-dir results/visual_feedback/foxglove
```

## 6. Foxglove Layout 导入与 Rosbag 回放验证

导入文件：

```text
foxglove_layout_project/output/auv_layout.generated.1781879459.json
```

人工导入后，Foxglove layout 已生效：

- Layout 名称显示为 `auv_ layout.generated`
- 页面中可见 `/auv/cable/tracking`
- 页面中可见 `/auv/cable/diagnostics`
- 可见 3D、Markdown、Plot、Raw/Message 类面板

连接结论：

- 错误路径：通过 dashboard 快捷入口进入时，URL 曾使用 `ds=rosbridge-websocket`。
- 该路径会显示 `连接失败`，因为本项目启动的是 ROS2 `foxglove_bridge`，不是 rosbridge server。
- 正确路径：使用 `Foxglove WebSocket` 数据源，URL 为 `ws://localhost:8765`。
- 正确 URL 参数形态：

```text
ds=foxglove-websocket&ds.url=ws%3A%2F%2Flocalhost%3A8765
```

已确认 8765 端口后端为：

```text
/opt/ros/humble/lib/foxglove_bridge/foxglove_bridge
```

回放命令：

```bash
source /opt/ros/humble/setup.bash
timeout 25s ros2 bag play \
  /auv_data/bags/20260705_213816/rosbag \
  --start-offset 65 \
  --rate 1.0
```

回放数据源：

```text
/auv_data/bags/20260705_213816/rosbag/rosbag_0.mcap
```

该 bag 包含：

- `/auv/sensors/magnetic`
- `/auv/cable/tracking`
- `/auv/cable/diagnostics`
- `/auv/control/setpoint`
- `/auv/state/filtered`
- `/auv/visual/cable_marker`
- `/auv/visual/seabed_mesh`

直接 ROS 订阅验证：

```text
count=1
{"time_s": 1783258797.2788277, "estimated_cable_xy_m": [...], "cross_track_m": 6.727489511987574, ...}
```

Foxglove 画面验证：

- 左侧问题面板显示 `没有发现问题`
- 3D 面板显示海底 mesh 与线状 marker
- 右侧 plot/raw/message 面板在接收回放数据
- 页面顶部显示 `ws://localhost:8765`

注意事项：

- `ros2 topic list` 和 `ros2 topic echo` 在本环境中仍可能触发 ROS daemon 的 `xmlrpc.client.Fault: rclpy.ok()` 问题。
- 对回放链路取证时，优先使用直接 `rclpy` 订阅脚本或 Foxglove 截图，不依赖 ROS2 CLI daemon。

## 7. Layout 生成脚本调整

`foxglove_layout_project/generator/build_layout.py` 已调整为默认双输出：

1. 历史归档输出，位于原 output 目录，使用 UNIX 时间戳区分，不覆盖：

```text
foxglove_layout_project/output/auv_layout.generated.<unix_timestamp>.json
```

2. 临时导入输出，位于仓库根目录 `tmp/foxglove_layout/`，可覆盖：

```text
tmp/foxglove_layout/auv_layout.generated.json
```

验证命令：

```bash
python3 -m foxglove_layout_project.generator.build_layout --pretty
```

本轮验证生成：

```text

## 10. 3f 回放可视化修复与 2D 俯视图补充（2026-07-09）

针对 `docs/thesis/paper/05_experiments_and_discussion.md` 中 3f 正结果对应的 fresh run：

```text
/auv_data/bags/20260709_134856/rosbag
```

本轮补充了一个 replay sidecar：

```bash
source /opt/ros/humble/setup.bash
source brain_linux/install/local_setup.bash
python3 tools/replay_visual_overlay_bridge.py
```

用途：

- 为只含 `/auv/state/filtered` 的 3f bag 恢复 `/auv/visual/*` 视觉话题；
- 在 replay 过程中把 `dlt1278_summary` 中沿用旧口径的“总分”文案重写为“扣分合计”；
- 补发：
  - `/auv/visual/auv_body`
  - `/auv/visual/history_trail`
  - `/auv/visual/cable_marker`
  - `/auv/visual/view_range`
  - `/auv/visual/seabed_mesh`
  - `/auv/visual/scale_bar`

Foxglove 1366 layout 当前结论：

- `acceptance-1366` 已恢复稳定俯视显示：
  - 电缆先验线
  - AUV 本体箭头
  - 历史轨迹
  - 视距圈
  - 地形背景
  - `10 m` 比例尺
- `topview` 采用 `perspective=false`，用于低视差验收态观察。
- `pilot-1366` 与 `acceptance-1366` 现共享同一套 3D topic 契约与地形/比例尺能力。

典型截图：

- `results/visual_feedback/3f_visual_audit_20260709/foxglove/acceptance_1366_terrain_scale.png`

新增离线 2D 俯视图脚本：

```bash
python3 tools/plot_replay_top_view.py \
  --bag /auv_data/bags/20260709_134856/rosbag \
  --tracking-config results/cable_ops_report/replay_e2e/_configs/heavy.yaml \
  --output results/visual_feedback/3f_visual_audit_20260709/foxglove/replay_top_view.png \
  --title '3f Cable Replay Top View'
```

2D 俯视图产物：

- `results/visual_feedback/3f_visual_audit_20260709/foxglove/replay_top_view.png`
- `results/visual_feedback/3f_visual_audit_20260709/foxglove/replay_top_view.json`

图中包含：

- cable prior
- AUV trajectory
- start / latest
- heading arrow
- `10 m` scale bar

说明：

- 当前 3D 中的海底层为 replay 验证所用的轻量 proxy mesh，用于恢复空间语义与展示完整度；
- 它不是原始高保真 seabed point cloud 的等价替代，但足以支撑本轮 3f 可视化审计与答辩展示预演。
foxglove_layout_project/output/auv_layout.generated.1783260962.json
tmp/foxglove_layout/auv_layout.generated.json
```

## 8. PySide6 点击注入验证

验证方式：

- 使用 `QT_QPA_PLATFORM=offscreen`
- 使用 PySide6 自带 `QtTest.QTest.mouseClick`
- 目标窗口为实际 `src.ui.main_window.MainWindow`
- 未点击 ESTOP、任务下发、自主授权、初始化、通信连接等高风险按钮

安全点击目标：

1. 点击 `QTabWidget` 的 `任务配置` tab。
2. 返回 `航点规划` tab。
3. 点击 `开始选点` 按钮。

验证结果：

```text
initial_tab_index= 0
initial_tab_text= 航点规划
after_tab_click_index= 1
after_tab_click_text= 任务配置
before_button_selecting_waypoint= False
after_button_selecting_waypoint= True
after_button_enabled= False True
status_message= 地图选点模式已开启 - 请在地图上点击添加航点
```

截图产物：

```text
results/visual_feedback/gui_pyside6_click_probe/click_probe_1783261553.png
```

结论：

- PySide6 上位机可以在无桌面会话的 offscreen 环境中接收模拟点击。
- tab 切换和按钮槽函数均能被 Qt 事件系统触发。
- 当前验证覆盖的是 Qt 级别点击，不依赖 `pyautogui`。
- 后续若需要真实桌面级点击、窗口拖拽或跨应用操作，仍需要 `DISPLAY/WAYLAND_DISPLAY`。

## 9. Foxglove Layout 免文件选择验证

问题背景：

- Foxglove Web 的 layout 导入会触发系统级文件选择窗口。
- 浏览器工具无法直接操作系统级文件选择窗口。
- 当前 Docker 仓库路径 `/home/auv_user/auv_ws/AUV-Master-Project` 在宿主机映射为：

```text
/Users/bytedance/coding/AUV-Master-Project
```

### 9.1 Base64 URL 参数验证

对 layout JSON 做了紧凑化与 base64url 编码：

```text
raw_bytes=8781
compact_bytes=5358
base64url_chars=7144
urlencoded_json_chars=8516
```

测试过以下 URL 参数名：

```text
layout=<base64url>
layoutData=<base64url>
layoutJson=<base64url>
```

为了判断参数是否真正生效，构造了一个明显不同的 probe layout：

```text
# AUV URL Layout Probe
If this panel is visible, URL layout injection worked.
```

实际结果：

- Foxglove 页面没有显示 probe layout。
- 页面仍显示已保存的 `auv_ layout.generated`。
- URL 被 Foxglove 自动补上 `layoutId=lay_0eTMD35mSIuRpPoy`。
- 结论：当前 Foxglove Web 不接受这些 base64 layout JSON 查询参数。

该结果与 Foxglove shareable links 文档一致：Web 深链公开支持的是保存后的 `layoutId`，而不是任意导出的 layout JSON。

### 9.2 可用绕过方案

当前可用方案是：

1. 首次导入 layout JSON，仍需人工选择文件。
2. 导入成功后复用 Foxglove 分配的 `layoutId`。
3. 后续直接打开带 `layoutId` 和数据源参数的深链，不再触发文件选择。

当前已验证可用的深链：

```text
https://app.foxglove.dev/guanwen/p/prj_0eTMB6alu9ojy3u3/view?layoutId=lay_0eTMD35mSIuRpPoy&ds=foxglove-websocket&ds.url=ws%3A%2F%2Flocalhost%3A8765
```

首次导入时宿主机文件路径：

```text
/Users/bytedance/coding/AUV-Master-Project/tmp/foxglove_layout/auv_layout.generated.json
```

### 9.3 辅助脚本

新增脚本：

```text
tools/foxglove_layout_deeplink.py
```

用途：

- 生成推荐的 `layoutId` 深链。
- 输出宿主机侧的 layout JSON 路径。
- 可选输出 base64 实验 URL，但该路径当前已验证不被 Foxglove Web 接受。

命令：

```bash
python3 tools/foxglove_layout_deeplink.py
```

输出文件：

```text
tmp/foxglove_layout/open_auv_layout.url
```

可选诊断：

```bash
python3 tools/foxglove_layout_deeplink.py --print-base64-experiment
```

## 10. Foxglove 自动导入 Layout 两种方案验证

### 10.1 方案一：Playwright file chooser

验证结论：

- 当前 Foxglove 页面在 layout 菜单打开前后都没有常驻 `input[type=file]`。
- 菜单中存在 `从文件导入……`。
- 这说明不能用普通 DOM selector 直接找隐藏 input。
- 正确路线是 Playwright 的 `expect_file_chooser()`，点击 `从文件导入……` 后由 Playwright 拦截 file chooser，再用 `set_files()` 注入 JSON。

当前容器状态：

```text
playwright Python package: installed
chromium browser: downloaded
Playwright browser launch: ok
installed deps: libnspr4, libnss3, libasound2
```

最小浏览器验证：

```text
title=ok
file_inputs=1
screenshot=results/visual_feedback/foxglove/playwright_minimal.png
```

本地 file chooser probe：

```text
direct=auv_layout.generated.json 12412
chooser_log=dynamic:auv_layout.generated.json:12412
screenshot=results/visual_feedback/foxglove/playwright_filechooser_probe.png
```

新增导入脚本 probe：

```text
script=tools/foxglove_playwright_import_layout.py
input=tmp/foxglove_layout/auv_layout.generated.json
result=ok
screenshot=results/visual_feedback/foxglove/playwright_import_script_probe.png
```

已新增脚本：

```text
tools/foxglove_playwright_import_layout.py
```

默认导入最新可覆盖 layout：

```text
tmp/foxglove_layout/auv_layout.generated.json
```

首次使用命令：

```bash
python3 tools/foxglove_playwright_import_layout.py --pause-for-login
```

后续复用同一个 Playwright profile：

```bash
python3 tools/foxglove_playwright_import_layout.py
```

该脚本会：

1. 打开 Foxglove deep link。
2. 点击 layout 菜单。
3. 点击 `从文件导入……`。
4. 使用 Playwright `expect_file_chooser().set_files(...)` 注入 layout JSON。
5. 截图到 `results/visual_feedback/foxglove/playwright_import_layout.png`。

如果在宿主机运行，layout 文件对应路径为：

```text
/Users/bytedance/coding/AUV-Master-Project/tmp/foxglove_layout/auv_layout.generated.json
```

### 10.2 方案二：IndexedDB 注入

只读探测结果：

```text
IndexedDB databases:
- foxglove-extensions-local
- foxglove-extensions-org-om_0eTMB6abmAEa7CFH
- foxglove-layouts
- foxglove-recents
```

Foxglove layout 存储结构：

```text
DB: foxglove-layouts
Store: layouts
keyPath: ["namespace", "layout.id"]
namespace: remote-om_0eTMB6abmAEa7CFH
current layoutId: lay_0eTMD35mSIuRpPoy
layout data path:
- layout.baseline.data
- layout.working.data
```

当前已保存 layout：

```text
name: auv_layout.generated
configById count: 14
contains /auv/cable/tracking: true
```

最新 tmp layout：

```text
path: tmp/foxglove_layout/auv_layout.generated.json
configById count: 15
contains /auv/cable/tracking: true
contains /auv/cable/diagnostics: true
```

本地 IndexedDB probe：

```text
dryRun=true
before.found=true
before.keyPath=["namespace", "layout.id"]
before.existingName=probe-before
before.existingConfigCount=0

dryRun=false
after.found=true
after.name=auv_layout.generated
after.configCount=15
```

截图：

```text
results/visual_feedback/foxglove/indexeddb_inject_script_probe.png
```

已新增实验脚本：

```text
tools/foxglove_indexeddb_inject_layout.py
```

只读检查：

```bash
python3 tools/foxglove_indexeddb_inject_layout.py --dry-run --pause-for-login
```

实际注入：

```bash
python3 tools/foxglove_indexeddb_inject_layout.py
```

该脚本会把 layout JSON 写入：

```text
foxglove-layouts.layouts
key: [remote-om_0eTMB6abmAEa7CFH, lay_0eTMD35mSIuRpPoy]
layout.baseline.data
layout.working.data
```

风险边界：

- 这是 Foxglove Web 的内部实现细节，不属于公开稳定 API。
- 高频迭代时它最省事，但 Foxglove 版本升级可能改变 DB/store/keyPath。
- 推荐流程仍是：
  1. 首次或结构大变时用 Playwright file chooser 导入。
  2. 日常打开用 `layoutId` deep link。
  3. 高频内部调试才用 IndexedDB 注入。

### 10.3 删除线上 layout 后的重新验证边界

用户已在 Foxglove Web 端删除此前人工导入的 layout。随后通过 IDE 浏览器检查真实页面：

```text
current page title: 查看 | Foxglove
current layout button: 默认
current URL layoutId: lay_0eTMBzNviTJMDBqK
previous generated layout: not active
```

结论：

- 前面的真实网页检查只能证明 IDE 浏览器中曾经加载过 `auv_layout.generated`。
- 删除线上 layout 后，不能再把该状态视为可复用证据。
- 本地 Playwright 机制验证仍然有效：
  - Chromium 可启动。
  - `expect_file_chooser().set_files(...)` 可绕过 OS 文件选择器。
  - 同形 IndexedDB 注入脚本可写入 layout 结构。
- 真正缺口是 Playwright 受控浏览器的登录态。IDE 浏览器登录态和 Playwright profile 不是同一个浏览器状态。

已更新脚本，支持通过 Playwright storage state JSON 注入登录态：

```text
tools/foxglove_playwright_import_layout.py --storage-state <auth.json>
tools/foxglove_indexeddb_inject_layout.py --storage-state <auth.json>
```

推荐重新验证命令：

```bash
python3 tools/foxglove_playwright_import_layout.py \
  --storage-state tmp/foxglove_auth/auth.json \
  --timeout-ms 60000
```

如果只读确认 IndexedDB 存储结构：

```bash
python3 tools/foxglove_indexeddb_inject_layout.py \
  --storage-state tmp/foxglove_auth/auth.json \
  --dry-run \
  --timeout-ms 60000
```

说明：

- `--storage-state` 适合从已登录浏览器导出的 `auth.json` 做一次性端到端导入验证。
- 长期高频调试仍建议用 `--pause-for-login` 在 Playwright 持久 profile 中登录一次，后续复用 `tmp/foxglove_playwright_profile`。

### 10.4 auth.json 后的真实页面注入结果

用户在仓库根目录提供：

```text
auth.json
```

检查结果：

```text
keys=["cookies", "origins"]
cookies=8
origin=https://app.foxglove.dev
```

脚本更新：

```text
tools/foxglove_playwright_import_layout.py
- 支持 --storage-state auth.json
- 支持当前 layout 按钮为 默认 / Default 时打开 layout 菜单
- 不再把 networkidle 作为 Foxglove 页面硬性就绪条件

tools/foxglove_indexeddb_inject_layout.py
- 支持 --storage-state auth.json
- 不再把 networkidle 作为 Foxglove 页面硬性就绪条件
```

Playwright 受控浏览器已具备 `auth.json` 注入能力，但本轮容器到 Foxglove 公网页面的网络/渲染不稳定，因此只作为备用路线保留。

本轮推荐并已验证成功的方法是：在已登录的 IDE 浏览器中直接注入 Foxglove IndexedDB。

1. 使用已登录的 IDE 浏览器 Foxglove 页。
2. 在容器中临时启动带 CORS 的 layout 文件服务：

```text
http://127.0.0.1:8899/tmp/foxglove_layout/auv_layout.generated.json
```

3. 从 IDE 浏览器页面执行 `fetch(...)` 读取最新 layout JSON。
4. 写入当前页面同 origin 的 IndexedDB：

```text
DB: foxglove-layouts
Store: layouts
keyPath: ["namespace", "layout.id"]
namespace: remote-om_0eTMB6abmAEa7CFH
layoutId: lay_0eTMBzNviTJMDBqK
layout.baseline.data: tmp/foxglove_layout/auv_layout.generated.json
layout.working.data: tmp/foxglove_layout/auv_layout.generated.json
```

写入前：

```text
existingName=默认
existingConfigCount=3
```

写入后：

```text
name=auv_layout.generated
configCount=15
containsTracking=true
containsDiagnostics=true
```

刷新后真实 Foxglove 页面验证：

```text
layout button: auv_layout.generated
topic panel: /auv/cable/tracking
topic panel: /auv/cable/diagnostics
page title: 查看 | Foxglove
```

结论：

- 用户删除线上 layout 后，已通过 IDE 浏览器 + IndexedDB 直接注入方式恢复最新 `auv_layout.generated`。
- 这不是 Foxglove 官方导入 API，但已经完成真实登录页面中的 layout 恢复与可视化闭环验证。
- 后续如果容器到 Foxglove 的 TLS 连接恢复，可继续用 `auth.json` 跑 Playwright file chooser 路线验证“正式导入”。

### 10.5 1366x1024 layout 拆分与压缩

问题：

- 原 `mentor-demo` layout 在 1366x1024 下把 15 个 panel 放进单页。
- 右侧只有约 32% 宽度，却堆叠状态、plot、RawMessages、DL/T 汇总和小 3D。
- 主 3D 占 68%，导致右侧 panel 过窄，出现文字和图例重叠。

调整策略：

- 不继续在单页塞满所有信息。
- 拆分为两套 1366 profile：
  - `pilot-1366`：驾驶/调试主屏，优先看主 3D、模式、置信度、电源、核心电缆曲线、误差和速度闭环。
  - `acceptance-1366`：验收/报告证据屏，优先看俯视 3D、电缆核心量、声磁质量、RawMessages 和 DL/T 汇总。
- 默认临时 layout 改为 `pilot-1366`，保证后续自动注入默认打开更清爽的驾驶态。

生成结果：

```text
tmp/foxglove_layout/auv_layout.generated.json        panels=8  rootSplit=52  profile=pilot-1366
tmp/foxglove_layout/auv_layout.pilot_1366.json       panels=8  rootSplit=52
tmp/foxglove_layout/auv_layout.acceptance_1366.json  panels=7  rootSplit=42
```

归档输出：

```text
foxglove_layout_project/output/auv_layout.generated.1783266217.json  # pilot-1366 初版
foxglove_layout_project/output/auv_layout.generated.1783266223.json  # acceptance-1366
foxglove_layout_project/output/auv_layout.generated.1783266342.json  # pilot-1366 v2
foxglove_layout_project/output/auv_layout.generated.1783266440.json  # 默认 pilot-1366
```

浏览器注入验证：

```text
before: name=auv_layout.generated, configCount=15
after:  name=auv_layout.pilot_1366, configCount=8, rootSplit=52
```

截图：

```text
foxglove_pilot_1366_layout.png
foxglove_pilot_1366_layout_v2.png
```

视觉结论：

- `pilot-1366` 已在真实 Foxglove 页面加载，顶部 layout 按钮显示 `auv_layout.pilot_1366`。
- 主 3D 从 68% 收到 52%，右侧可用宽度提高。
- 删除驾驶态中的大字 `Indicator!leak` 后，右上状态区域不再出现明显大字重叠。
- 右侧 panel 数量下降，交互元素从约 95 降到约 59。
- 验收相关 RawMessages 和 DL/T 汇总不再挤在驾驶主屏，改由 `acceptance-1366` 承担。

### 10.6 带仿真数据的 layout 二次收敛

本轮启动 PVS + `protocol_udp` + cable tracking 链路，并用真实 Foxglove WebSocket 页面观察布局：

```text
Foxglove URL: ...&ds=foxglove-websocket&ds.url=ws://localhost:8765
pilot layout: auv_layout.pilot_1366
simulation: scripts/start_experiment.sh --sim-backend pvs --bridge-backend protocol_udp --duration 120 ...
```

运行证据：

```text
/auv/cable/tracking sample:
industrial_ready=true
acceptance_flags=[]
burial_status=ready
confidence≈0.956
burial_sigma_m≈0.137
route_progress_m≈56.7
```

观察结论：

- `pilot-1366` 在带数据状态下能接入 `ws://localhost:8765`，3D、状态、速度闭环和诊断曲线均有实时数据。
- `/auv/cable/tracking` 当前是 `std_msgs/String` 内嵌 JSON。Foxglove Plot 对 `String.data` 中的 JSON 字段路径不稳定，容易出现 warning。因此不把电缆 JSON 数值曲线放在驾驶主屏。
- `industrial_ready`、`acceptance_flags`、`burial_status` 这类强结构化文本更适合由上位机解析成状态卡；Foxglove 只保留小 RawMessages 用于调试抽查。
- DL/T 1278 长文本报告也不适合继续塞进 Foxglove，应迁到上位机或文档/报告查看器。

最终本轮 layout 调整：

```text
pilot-1366:
- 左侧 68%：速度闭环 + 跟踪误差，上下排列。
- 右侧 32%：小 3D、模式/置信度/电源、/auv/cable/tracking RawMessages。
- 删除驾驶主屏中的 Plot!cable_tracking，避免 String JSON 字段绘图 warning。

acceptance-1366:
- 左侧 72%：电缆质量/证据趋势 + tracking/diagnostics RawMessages + bt_status。
- 右侧 28%：俯视 3D。
- 删除 Markdown!dlt1278_summary，长报告迁出 Foxglove。
```

生成产物：

```text
tmp/foxglove_layout/auv_layout.generated.json        # 默认 pilot-1366
tmp/foxglove_layout/auv_layout.pilot_1366.json
tmp/foxglove_layout/auv_layout.acceptance_1366.json
foxglove_layout_project/output/auv_layout.generated.1783307746.1.json
```

截图：

```text
foxglove_pilot_1366_live_before_next_adjust.png
foxglove_pilot_1366_live_compact3d.png
foxglove_pilot_1366_live_compact3d_v3.png
```

10.7 已实施：

- 增加轻量 ROS2 标量/状态 topic，把 `industrial_ready`、`acceptance_flags`、`route_progress_m` 等字段从 JSON 字符串拆成 Foxglove 可直接 Plot/Indicator 的字段。
- 上位机新增“电缆巡检 ready/pass”监控卡片，承接实时验收结论；DL/T 长报告入口仍建议后续放到上位机报告页。

### 10.7 电缆 tracking JSON 的字段拆分与双端监控

问题：

- `/auv/cable/tracking` 是 `std_msgs/String`，单条 JSON 约 2400 字符。
- Foxglove Plot 不能稳定直接绘制 `String.data` 内部 JSON 字段，旧 layout 中的 `/auv/cable/tracking.cross_track_m` 等路径会出现 warning。
- 这些字段本身很重要，不能只放 RawMessages。

样本捕捉：

```text
sample=tmp/foxglove_layout/cable_tracking_sample.json
sample_chars=2424
top_fields=21
diagnostics_fields=36
```

本轮选取 10 个高价值监控字段：

```text
industrial_ready
acceptance_flags
mode
cross_track_m
route_progress_m
burial_depth_m
burial_sigma_m
confidence
magnetic_snr_db
magnetic_confidence
```

样本值：

```text
industrial_ready=False
acceptance_flags=['route_offset_over_limit', 'burial_uncertainty_missing']
mode=quality_limited
cross_track_m=357.6114558371803
route_progress_m=100.99019513592785
burial_depth_m=1.5
burial_sigma_m=None
confidence=0.6500000000000001
magnetic_snr_db=73.1339540802201
magnetic_confidence=0.6500000000000001
```

新增 Foxglove 友好派生 topic：

```text
/auv/cable/industrial_ready       std_msgs/Bool
/auv/cable/mode                   std_msgs/String
/auv/cable/acceptance_flags       std_msgs/String
/auv/cable/status_text            std_msgs/String
/auv/cable/cross_track_m          std_msgs/Float32
/auv/cable/route_progress_m       std_msgs/Float32
/auv/cable/burial_depth_m         std_msgs/Float32
/auv/cable/burial_sigma_m         std_msgs/Float32
/auv/cable/confidence             std_msgs/Float32
/auv/cable/magnetic_snr_db        std_msgs/Float32
/auv/cable/magnetic_confidence    std_msgs/Float32
```

验证：

```text
ros2 topic list | rg /auv/cable
# 已出现全部派生 topic

ros2 topic echo /auv/cable/status_text --once
data: 'READY | mode=track | flags=none
  cross=0.00 m | progress=13.8 m
  burial=-5.92 m | sigma=0.001 m
  conf=1.000 | snr=109.2 dB | mag_conf=...'
```

Foxglove layout 调整：

- `pilot-1366` 删除错误的 `Plot!cable_tracking`，新增 `Indicator!cable_ready`、`Markdown!cable_status`、`Markdown!cable_flags`、`Gauge!cable_confidence`。
- `pilot-1366` 曲线区高度从主区域降低到约 38%，只保留速度闭环和跟踪误差。
- `acceptance-1366` 的电缆曲线改为消费 `/auv/cable/*` typed topic，不再引用 `/auv/cable/tracking.<field>`。
- `acceptance-1366` 曲线行约占证据区 31%，其余空间给 ready/status/flags 与 RawMessages。

上位机调整：

- `bridge_node` 订阅 `/auv/cable/tracking`，提取上述 10 个字段，放入 `rt/auv/telemetry` 的 `cable_monitor` 摘要。
- PySide6 上位机底栏新增“电缆巡检监控”卡片，显示：
  - 结论：READY / NOT READY
  - 模式：`mode`
  - 偏移/埋深/进度
  - 置信度/SNR/磁置信度
  - 验收标志

上位机 offscreen 验证：

```text
结论: READY | track
偏移/埋深/进度: 0.02 m / -5.92 m / 13.8 m
置信度/SNR: 1.000 / 109.2 dB / mag 1.000
验收标志: none
```

### 10.8 DL/T 1278 风格评分、产物和可视化合龙

本轮把 DL/T 1278 风格实时状态接入运行时、Foxglove 和上位机。

定位：

- 离线最终评分仍由 `tools/dlt1278_cable_report.py` 负责，产出 `inspection_summary.json`、`dlt1278_report.md`、CSV 和图像产物。
- 运行时新增“DL/T 1278 风格实时摘要”，用于值守人员在实验过程中判断当前 evidence 是否可用、扣分项是什么、最终应查看哪些产物。

新增运行时 topic：

```text
/auv/cable/dlt1278_summary              std_msgs/String
/auv/cable/dlt1278_state                std_msgs/String
/auv/cable/dlt1278_total_score          std_msgs/Float32
/auv/cable/industrial_acceptance_pass   std_msgs/Bool
```

`/auv/cable/tracking` JSON 中新增：

```text
industrial_acceptance_pass
dlt1278.state
dlt1278.total_score
dlt1278.worst_single_score
dlt1278.score_items
dlt1278.industrial_conclusion_readiness
dlt1278.output_products
```

实时评分口径与离线报告当前已实现项保持一致：

- `海缆位移`：II 类，8 分。
- `海缆埋深不足`：III 类，16 分。
- `埋深估计精度未达 0.15m`：II 类，8 分。

Foxglove layout 更新：

```text
tmp/foxglove_layout/auv_layout.generated.json        # 默认 pilot-1366
tmp/foxglove_layout/auv_layout.pilot_1366.json
tmp/foxglove_layout/auv_layout.acceptance_1366.json
```

`pilot-1366` 新增：

- `Indicator!cable_pass`：工业验收 PASS/FAIL。
- `Indicator!dlt1278_state`：正常/注意/异常/严重状态。
- `Gauge!dlt1278_score`：旧版 DL/T 风格总分表述，当前已弃用并转为“扣分合计”语义。
- `Markdown!dlt1278_summary`：扣分项、ready/pass 和产物链摘要。

`acceptance-1366` 新增同一组 DL/T 状态看板，并继续保留趋势曲线和 RawMessages 证据区。

上位机更新：

- `bridge_node` 将 `dlt1278` 摘要并入 Zenoh `rt/auv/telemetry` 的 `cable_monitor`。
- PySide6 底部“电缆巡检监控”卡片新增：
  - `READY/PASS` 或 `NOT READY/FAIL`
  - DL/T 状态/扣分合计
  - 实时扣分项
  - 产物链摘要

验证：

```bash
python3 -m py_compile \
  brain_linux/src/auv_control/auv_decision_ros/cable_tracking_node.py \
  brain_linux/src/auv_bridge/auv_bridge/bridge_node.py \
  console_soft/auv_console_pyside6/src/ui/main_window.py \
  foxglove_layout_project/config/topics.py \
  foxglove_layout_project/generator/layout_builder.py

cd brain_linux
source /opt/ros/humble/setup.bash
colcon build --packages-select auv_decision_ros auv_bridge --symlink-install
```

构建结果：

```text
Summary: 2 packages finished
```

注意：

- 当前已经运行中的 ROS 节点不会自动加载新 Python 代码。
- 要看到 `/auv/cable/dlt1278_summary` 等新增 topic，需要重启 cable tracking/bridge 相关进程，或重新运行 `scripts/start_experiment.sh`。

### 10.9 Foxglove 中 AUV 反复跳动/抽搐问题

用户在 Foxglove 观察到 AUV 反复跳动。已确认问题存在。

本轮实测关键现象：

```text
/auv/state/filtered 与 /auv/visual/auv_body 的末端坐标差约 1329 m。
```

根因：

- 旧 Foxglove 3D 面板同时默认显示：
  - `/auv/state/filtered`
  - `/auv/visual/auv_body`
  - `/auv/visual/truth_marker`
- 这些来源不是同一个可视化坐标源，且更新频率/原点可能不同。
- 在 3D 面板中叠加显示时，会表现为 AUV 在多个位置之间跳动。

修复：

- 3D 默认只显示 `/auv/visual/auv_body` 作为 AUV 主体。
- `/auv/state/filtered` 和 `/auv/visual/truth_marker` 在 3D 中默认隐藏，保留为手动 debug 图层。

生成后核验：

```text
tmp/foxglove_layout/auv_layout.generated.json
/auv/state/filtered visible=False
/auv/visual/auv_body visible=True
/auv/visual/truth_marker visible=False

tmp/foxglove_layout/auv_layout.acceptance_1366.json
/auv/visual/auv_body visible=True
/auv/visual/truth_marker visible=False
```

已对当前已登录 Foxglove 页面执行 IndexedDB 注入：

```text
layoutId: lay_0eTMBzNviTJMDBqK
before.configCount=8
before.stateVisible=true
before.truthVisible=true

after.configCount=16
after.hasDltSummary=true
after.hasCablePass=true
after.stateVisible=false
after.truthVisible=false
```

刷新后页面确认：

- layout 按钮仍显示 `auv_layout.pilot_1366`。
- 新面板已经加载，包含 `/auv/cable/dlt1278_summary` 等 DL/T 状态面板。
- 3D 面板只保留单一 AUV body，消除了多位姿源叠加导致的跳动。

### 10.10 PySide6 上位机 DL/T 卡片 offscreen 点按与截图验证

目标：

- 验证 PySide6 上位机新增的“电缆巡检监控”卡片可以显示 DL/T 1278 风格状态、扣分合计、扣分项和产物链。
- 验证无桌面会话下仍可通过 Qt offscreen 渲染截图。
- 验证安全模拟点按链路仍可用，且不触碰 ESTOP、自主授权、任务下发、通信连接等高风险按钮。

新增验证脚本：

```text
tools/gui_console_dlt_probe.py
```

运行命令：

```bash
QT_QPA_PLATFORM=offscreen python3 tools/gui_console_dlt_probe.py --wait-seconds 0.5
```

脚本执行内容：

1. 启动真实 `src.ui.main_window.MainWindow`。
2. 注入一条代表最新 ready/pass 实验成果的 `cable_monitor` 样本：
   - `industrial_ready=true`
   - `industrial_acceptance_pass=true`
   - `dlt1278_state=注意状态`
   - `dlt1278_total_score=24`
   - 扣分项为 `海缆埋深不足(16分)` 和 `埋深估计精度未达 0.15m(8分)`
3. 执行安全点击：
   - 切换到 `任务配置` tab。
   - 返回 `航点规划` tab。
   - 点击 `开始选点`。
4. 保存截图和 JSON 记录。

本轮输出：

```text
results/visual_feedback/gui_pyside6_dlt_probe/console_dlt_probe_20260706_123847.png
results/visual_feedback/gui_pyside6_dlt_probe/console_dlt_probe_20260706_123847.json
```

验证结果：

```text
dangerous_actions_executed=false
clicked_controls=["tab:任务配置", "tab:航点规划", "button:开始选点"]
after_button_selecting_waypoint=true
after_button_start_enabled=false
after_button_end_enabled=true
status_message=地图选点模式已开启 - 请在地图上点击添加航点
```

新增卡片显示：

```text
结论: READY/PASS | track
偏移/埋深/进度: 0.42 m / 1.42 m / 58.7 m
置信度/SNR: 0.956 / 87.3 dB / mag 0.931
DL/T状态/扣分合计: 注意状态 / 24
扣分项: 海缆埋深不足(16分)；埋深估计精度未达 0.15m(8分)
验收标志: none
产物链: tracking.jsonl, inspection_summary.json, dlt1278_report.md, operator_view/*.png
```

未点击的危险控件：

```text
紧急切断 ESTOP
解除急停
请求自主
手动接管
下发任务
连接 Zenoh
任务开启
任务取消
```

结论：

- PySide6 上位机新增 DL/T 1278 风格监控内容显示正常。
- Qt offscreen 截图链路可用。
- QtTest 模拟点按链路可用。
- 本轮验证没有触发任何高风险控制动作。
