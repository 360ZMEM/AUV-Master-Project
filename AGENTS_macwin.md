# AGENTS_macwin.md — 毕设写作项目上下文索引（macOS/Windows 辅助侧职责）

> 本文件是 `AGENTS.md` 分流后的 **macwin 侧主索引**（`uname` 返回 Darwin / 命令不存在时读本文件）。
> **每次上下文清理/重置后，即使不是第一次进入，也必须完整读完本文件**，以在不重复探索的前提下恢复目标与约束。
> 维护约定：既要「概括」又要「行号对应」（`文件#Lxx-Lyy`），便于精准跳读；发现新关键位置随时补行号。高度专业化子内容分流到子文档并在此登记路径（**不得在仓库根目录新建散文件**）。
> 最后更新：2026-08-18（**事实源正式切换为 LaTeX**，见下方 §0.1；进入论文压缩阶段，计划见 [25_论文压缩计划.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/潜在待完成事项/25_论文压缩计划.md)）。

---

> ## 0.1 事实源（Source of Truth）— 已切换为 LaTeX（★铁律，2026-08-18 确认）
> **自迁移完成后，LaTeX 是论文唯一权威事实源，Markdown 降级为只读历史参照。**
> - **权威事实源**：`thuthesis/data/auv-chap01.tex … auv-chap06.tex` + `thuthesis/data/auv-appendix-a.tex` + `auv-abstract.tex`/`auv-denotation.tex`。所有正文/表格/公式/图注的修改**只改这些 `.tex`**（文件头已注明 *"Authoritative thesis source; edit this TeX file directly."*）。
> - **只读历史参照**：`docs/thesis/paper/*.md`（canonical Markdown）**不再回写、不再作为生成源**，仅供追溯早期措辞。**严禁**用 Markdown 覆盖或"重新生成"任何 `.tex`。
> - **不再运行 Markdown→LaTeX 生成器与新鲜度门禁**：`tools/sync_latex_references.py` 仅保留 references.bib 的字节一致副本同步功能，不再从 Markdown 生成正文。
> - **本条覆盖并取代**下文 §2 原则 9 与 §0「维护边界」中"Markdown 为内容事实源 / 由 canonical Markdown 确定性生成"的旧表述（保留原文仅为历史留痕，实际以本条为准）。
> - 图像资产仍以 `docs/thesis/figures/` 为唯一可提交源；被删/降级图的源路径写入各图组 `_SOURCE.md`/Artifact Manifest 以保可追溯。

---
> 当前 LaTeX 状态（2026-08-13）：附录 A 已完成学术化重组，连续结果图已完成紧凑排版，第 4--6 章公式符号已完成学术化；第 1、2、3、5、6 章 canonical 已完成 TMR8637、SK2301、“新息”及关键概念顺序规范化；第 5.1 节已从证据边界概述重写为仿真实施架构、单次闭环生命周期、多场景跑批组织与评价口径；UA-MPC、ES-EKF、DLIA、LOS、组合导航结构和声磁接力的引用归属已按“本文方法—理论基础/启发”分离，LaTeX 正文中的插入式双破折号已清零；TMR8637 随附资料已完成原图归档、参数拆表和曲线裁剪，编号 6# 模组报告核验为 200 pT/√Hz @ 1 Hz、约 20--30 pT/√Hz @ 50 Hz，完整测量链仍待实测；论文联合构建为 179 页 A4。
> 维护边界〔**2026-08-18 更新，以 §0.1 为准**〕：~~第 1–6 章继续由 canonical Markdown 确定性生成~~ → **现全书第 1–6 章及附录 A 均改为直接手改 `.tex`，不再由 Markdown 生成、不再跑新鲜度门禁**（详见 §0.1）。`docs/thesis/paper/*.md` 仅作只读历史参照。
> 验收记录：[附录A_LaTeX学术化重组验收_20260808.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/附录A_LaTeX学术化重组验收_20260808.md)。
> 图页验收：[连续结果图与正文共存排版验收_20260808.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/连续结果图与正文共存排版验收_20260808.md)。
> 符号验收：[第三章后LaTeX公式符号学术化验收_20260808.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/第三章后LaTeX公式符号学术化验收_20260808.md)。
> 传感器与概念验收：[TMR8637规范化与概念顺序审计验收_20260808.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/TMR8637规范化与概念顺序审计验收_20260808.md)；随附资料及 50 Hz 噪声谱已核验，2026-08-11 以平整扫描件替换旧翻拍原图并舍弃接线端子图；2026-08-13 将三轴性能参数独立排为表 2.10，出版图只保留电压-磁场传输曲线和两幅噪声特性曲线。当前权威 PDF 因前置新增主动横切图，TMR 曲线顺延为图 2.6/2.7；裁剪参数、原图、出版图与哈希见 [tmr8637_test_report/_SOURCE.md](file:///Users/bytedance/coding/AUV-Master-Project/docs/thesis/figures/hardware/tmr8637_test_report/_SOURCE.md)。
> 第 5.1 节验收：[第五章5.1仿真实施架构重写验收_20260808.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/第五章5.1仿真实施架构重写验收_20260808.md)。

## 0. 一句话目标（Prime Directive）

本仓库在 **两个平台并行运行**、职责截然不同（见 [AGENTS.md](file:///Users/bytedance/coding/AUV-Master-Project/AGENTS.md)）：
- **Linux 侧**（有 ROS2 环境）＝ 论文主体写作 + 实验佐证，索引见 [AGENTS_linux.md](file:///Users/bytedance/coding/AUV-Master-Project/AGENTS_linux.md)。
- **macwin 侧（本对话）** ＝ 完成 **Linux 侧做不了的、依赖 GUI/电脑操纵/浏览器/联网** 的辅助任务，与 Linux 侧 **并行（concurrent）** 推进同一篇论文。

**本对话（macwin 侧）核心职责 = 六类辅助任务**（[毕业写作无ROS辅助完善计划.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/毕业写作无ROS辅助完善计划.md#L3)）：
1. **文献 grounding 与引用信息维护**（bibtex ↔ GB/T 7714-2015）。
2. **互联网检索文献 / fetch PDF**（必要时浏览器注入 cookies 走院校认证下载）。
3. **架构图更新与维护**（drawio 直接绘制——容器内做不了，最终产物落在本侧）。
4. **操纵实际电脑 / 浏览器**，完成 docker 容器内无法完成之事。
5. 潜在杂项与背景唠嗑。
6. **LaTeX 出版装配与答辩 Beamer**：把审核通过的 Markdown、引用库和图片资产装配到 `thuthesis/` 与 `thubeamer-1.2/`，维护跨平台编译和资产同步。

与 Linux 侧的 **明确 boundary（交接面）**（[计划#L16](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/毕业写作无ROS辅助完善计划.md#L16)）：
- **架构图交接**：Linux 侧写「严格自包含的图描述文本」→ 本侧用 drawio 直接绘制/编辑/导出。
- **文献检索交接**：Linux 侧标注需要的引用点/占位符 → 本侧检索、下载、生成 bibtex 与 GB/T 7714 文本回填。

写作 baseline（与 Linux 侧一致）：**实验结果服务于写作，不让指标凌驾逻辑**；创新点表述克制而不回避；面向清华教授要拿高分。

---

## 1. 指令 Prompt 与作者背景

### 1.1 Prompt 位置
- **本侧计划书（macwin）**：[毕业写作无ROS辅助完善计划.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/毕业写作无ROS辅助完善计划.md)
  - 辅助任务定位 / 与容器职责差异：`#L1-L3`
  - macwin 侧核心文档说明（即本文件）：`#L5`
  - SOP 记录与分流要求：`#L7`
  - **预备任务清单（本阶段任务源）**：`#L11-L14`（电脑操纵 / 联网检索 / bibtex→GB/T / 通用阅读+drawio）
  - 与主 Prompt 一致执行 + 明确 boundary（架构图 / 文献交接）：`#L16`
  - 注意事项（缺依赖可要求安装 / 分门别类 / 初次接手时 Linux 侧文件可能未生成）：`#L18-L22`
- **主计划书（Linux 侧，任务总源）**：[毕业写作完善计划.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/毕业写作完善计划.md)
  - 项目定位与分工：`#L1`；老架构代码位置：`#L3`；Jetson 主线 + protocol_udp/zenoh + pvs/holoocean：`#L13`
  - 附件目录清单：`#L33-L36`；预备操作清单：`#L40-L56`；协作/写作操作清单：`#L58-L67`
  - 落盘规范（`01new_` 前缀、未完成/核心中间进度同步分流、图片相对路径）：`#L71-L85`；起点建议（第五章）：`#L87`
- **顶层分流**：[AGENTS.md](file:///Users/bytedance/coding/AUV-Master-Project/AGENTS.md) → `uname`：Linux 读 `AGENTS_linux.md`；Darwin/无命令读本文件。

### 1.2 作者背景
- 作者：谢冠文 <xgw24@mails.tsinghua.edu.cn>，清华专硕，2026 年 8 月。
- 分工：本人负责 **控制、软件基础、电路、传感器选型、电磁屏蔽**；声呐及其加工由丁同学负责；大项目是中航天佑张师兄（工程博士）课题。
- 详细心路历程与 Q&A 背景：[AI对话记录——了解背景信息.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/AI对话记录——了解背景信息.md)（~773KB，11792 行；**禁止全量 Read/grep，会卡死**；用 `Q&A` 序号定界，主题图谱见 [AGENTS_linux.md](file:///Users/bytedance/coding/AUV-Master-Project/AGENTS_linux.md) §6.4）。

---

## 2. 已形成的原则（Principles）

1. **⚠️ 命令必须带超时 + 防硬卡死（本侧头号铁律）**：本机（Darwin）长命令（网络、CLI 冷启动、大 PDF、递归 `find`/`ls -R`、含中文/复杂正则的 `grep`）极易卡死。
   - **关键教训（2026-08-06 实测）**：`gtimeout`/`with_timeout.sh` **只能杀子进程，挡不住「工具/harness 层」的硬卡死**——前台 Shell 调用一旦卡死无法中断，事后也无法切后台。故超时包装器**不是**可靠护栏。
   - **可靠规避（按优先级）**：
     1. **搜索/遍历一律不用 Shell**：用 **Explore 子代理**（独立上下文，卡死只影响子代理）或直接 **Read** 已知文件。
     2. **凡必须跑的 Shell，一开始就设 `run_in_background: true`**（切勿指望事后切后台）＋ Read 日志；后台命令即使硬卡死也不阻塞前台。
     3. 网络类仍用自带开关：`curl --max-time N` / `wget --timeout=N`。
     4. 万不得已在前台 grep：加 `LC_ALL=C` + 固定串 `-F`，避开中文多字节正则触发的卡死。
   - **已知会卡死的操作**：`ls -R`、深层 `find /`、无 `--max-time` 的 `curl`、含中文的 `grep -rnE`、全量读 773KB AI 对话。
2. **目标导向 + 上下文回归**：每次上下文重置后必读本文件；不做无意义重复扫描。
3. **写作优先于指标 / 创新点克制不回避 / 改动走奥卡姆剃刀且正交**（与 Linux 侧一致，红线见 [rating.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/rating.md)）。
4. **本侧只做辅助、不碰实验代码逻辑**：本侧不运行仿真、不改 ROS/控制代码；只做检索、绘图、文件读写、引用维护。涉及实验的改动交 Linux 侧。
5. **架构图 → drawio 直接产出**：本侧具备 drawio 桌面 CLI（见 §3.5），可直接绘制/导出 PNG/SVG/PDF。接收 Linux 侧「自包含图描述文本」后落地为 `.drawio` + 导出图；产物统一放 `docs/thesis/figures/architecture/`（[project_memory](context://memory/projects/-Users-bytedance-coding-AUV-Master-Project/project_memory.md) 约定）或 `毕业设计写作文档/相关插图（架构图）/`。
6. **图片一律 markdown 相对路径引用**；占位符对 Ctrl/Cmd+F 友好（唯一、可检索）。
7. **落盘前缀 / 分流规范**：旧 AI 初稿 `01_`…；新写作 `01new_`…；专业化内容分流子目录并在此登记；**不在根目录建散文件**。
8. **文献落盘**：PDF → `毕业设计写作文档/参考文献/文献PDF/`；bibtex / GB/T 文本 → `毕业设计写作文档/参考文献/文献引用信息/`。引用信息目录已有总索引、分主题记录和 canonical `references.bib`；PDF 目录当前为空。
9. **⚠️〔已被 §0.1 取代〕一份事实、两种出版视图**：~~章节迁移验收前，`docs/thesis/paper/*.md` 是内容事实源~~。**现行以 §0.1 为准：LaTeX 是唯一事实源，Markdown 只读历史参照。** 图片仍只以 `docs/thesis/figures/` 为可提交资产源。

---

## 3. 能力契约与 SOP（macwin 侧，均已实测）

> 环境：macOS 26.4.1（Darwin arm64）。Homebrew 在 `/opt/homebrew`；另有 `/usr/local`（TeXLive 2026、pandoc、gs）。系统 python3 = 3.9.6（`/usr/bin/python3`，**几乎无第三方库**，pip 21.2.4 可联网）。**Node/npm 缺失**。

### 3.0 超时兜底契约（贯穿所有命令）
> ⚠️ **超时包装器只杀子进程，挡不住 harness 层硬卡死**（见 §2.1）。真正可靠的护栏是 **① 搜索用 Explore 子代理/Read；② Shell 一开始就 `run_in_background:true`**。下表为「命令内部」的时长约束，非硬卡死护栏。

| 场景 | 推荐做法 | 备注 |
|---|---|---|
| **搜索/遍历（首选）** | **Explore 子代理** 或 **Read** | 不进前台 Shell，杜绝硬卡死 |
| **必须跑的 Shell** | 一开始就 `run_in_background:true` → Read 日志 | 后台命令硬卡死也不阻塞前台 |
| 网络（curl/wget） | `curl --max-time 15 -s ...` / `wget --timeout=15` | 网络类优先自带开关 |
| 命令内部时限 | `gtimeout <秒> <cmd>` 或 `with_timeout.sh` | 仅约束子进程，非硬卡死护栏 |
| 前台 grep（万不得已） | 加 `LC_ALL=C` + `-F` 固定串 | 避开中文多字节正则卡死 |

### 3.1 电脑操纵（Computer Use MCP）
- **权限现状**：`accessibility: granted` + `screenRecording: granted`（**均已授权，可点击/输入/读 UI + 截图看屏**，2026-08-06 用户授权后复测通过）。
- **可用工具**：`mcp_Computer_Use_*`（click / type_text / press_key / scroll / drag / list_apps / get_app_state / perform_action / set_value 等；schema 需先经 ToolSearch 载入）。
- **SOP**：可用 accessibility 树（`get_app_state`/`list_apps`）+ 点击/输入 + 截图完成桌面自动化与视觉校验。drawio 视觉自检可用截图或 Read 导出 PNG 两种方式。

### 3.2 互联网检索与抓取
- **WebSearch / WebFetch**（deferred，用 ToolSearch `select:WebSearch,WebFetch` 载入）：已实测 WebSearch 可返回学术结果（OUP/Wiley/MDPI/IEEE 等，含 DOI）。WebFetch 对 **认证/私有页返回空**，不能替代院校下载。
- **命令行**：`curl`、`wget`、`jq` 齐备。**Crossref REST 已实测可用**（见 §3.3）。
- **院校认证下载 SOP（待实操验证）**：公开 PDF 直接 `curl --max-time N -L -o`；付费墙走浏览器工具登录注入 cookies，或用户手动下载后放入 `参考文献/文献PDF/`。

### 3.3 文献检索 → BibTeX → GB/T 7714-2015（★核心，已端到端实测通过）
**工具链已确认**：TeXLive 2026（`xelatex`/`latexmk`/`biber`/`bibtex`）、`biblatex-gb7714-2015` 与 `gbt7714` 宏包均在（`kpsewhich gbt7714.sty` 命中）；pandoc 3.10（含 `+lua`，无独立 pandoc-citeproc）；**无 CSL 版 7714** → 走 biblatex/bst 路线。`bibtexparser` 等 py 库缺失但 pip 可装。

**SOP（已跑通，产物正确）：**
1. **检索**（Crossref）：
   `curl --max-time 15 -s "https://api.crossref.org/works?query.bibliographic=<关键词>&rows=3&select=DOI,title,author,container-title,published" | jq '.message.items[] | {DOI,title:.title[0]}'`
2. **DOI → BibTeX**（两条路径都实测可用）：
   - `curl --max-time 15 -sL -H "Accept: application/x-bibtex" "https://api.crossref.org/works/<DOI>/transform/application/x-bibtex"`
   - 备用：`curl --max-time 15 -sL -H "Accept: application/x-bibtex" "https://doi.org/<DOI>"`
3. **BibTeX → GB/T 7714-2015 渲染文本**：最小 `.tex`（`\usepackage[backend=biber,style=gb7714-2015]{biblatex}`）→ `latexmk -xelatex` → `pdftotext -layout` 抽参考文献段。
   - **实测输出**（作为字段完整性判据的样例）：
     `[1] JACOBI M, KARIMANZIRA D. Underwater pipeline and cable inspection using autonomous underwater vehicles[C/OL]//2013 MTS/IEEE OCEANS - Bergen. IEEE, 2013: 1-6. DOI: 10.1109/oceans-bergen.2013.66 08089.`
   - **字段完整性准则**：若渲染缺作者/年份/来源/页码 → bibtex 字段不全，需回 Crossref/出版社补 `author/year/booktitle|journal/pages/volume/number`。
- 落盘：bibtex 与 GB/T 文本 → [参考文献/文献引用信息/](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/参考文献/文献引用信息)。

### 3.4 多格式文件阅读（macOS 侧比 Linux 侧更全）
| 格式 | 方法 | 备注 |
|---|---|---|
| `.pdf`（文本层） | `with_timeout.sh 15 pdftotext -layout <pdf> -`（poppler 已装）；元信息 `pdfinfo` | **必须带超时**；比 Linux 侧的 gs 方案更准，中文 OK |
| `.pdf`（扫描/图纸） | 无 OCR（`tesseract` 未装）；选读或截图/交人工 | 图纸类 txtwrite 仅出图框文字 |
| `.docx` | `pandoc -t plain <file>.docx` | 已在 Linux 侧验证；本侧 pandoc 3.10 同理 |
| `.md`/`.txt`/代码 | Read 工具；结构用 `grep -nE "^#{1,3} "` | 首选 |
| `.png/.svg/.jpg` | Read 工具（多模态直接看图） | 架构图/结果图 |
| **大文件（>~80KB / >600 行）** | **Read 分块**（`offset`+`limit`，每次 300–400 行，按行锚点定位）或 **Explore 子代理**（只读摘录） | ⚠️ **整读会触发「系统未知错误」**（如 `05new_experiments_and_discussion.md` 约 93KB）；禁止一次性整读 |
| `.drawio` | 视为 XML Read；或看同名 `.png/.svg` | |
- 未装：`mutool`/`qpdf`/`tesseract`/`tree`/`node`。需要时 `brew install`。

### 3.5 drawio-skill（架构图直接产出，★本侧独有优势）
- **技能存在**：`/Users/bytedance/.trae-cn/skills/drawio-skill`（Skill 调用名 `drawio-skill`）。
- **CLI 已装且可运行**：`drawio`（Homebrew，`/opt/homebrew/bin/drawio`，实测 `--version`=30.3.14）；App 在 `/Applications/draw.io.app`。
- **基本流程**（详见技能文档）：① 查依赖 → ② 规划 shapes/布局 → ③ 写 `.drawio` XML → ④ **预览导出（不加 `-e`）** `drawio -x -f png -s 2 -o d.png in.drawio` → ⑤ 视觉自检（本侧 accessibility OK 但截图受限，可直接 Read 导出的 PNG 做多模态自检）→ ⑥ 评审改 → ⑦ **最终导出加 `-e`** 并对 PNG 跑 `scripts/repair_png.py`（修 IEND 截断）。
- **导出命令务必配超时**：`with_timeout.sh 60 drawio -x -f png ...`（Electron 冷启动可能慢）。
- **风格约定**（见 [project_memory](context://memory/projects/-Users-bytedance-coding-AUV-Master-Project/project_memory.md)）：IEEE 风格、Noto Serif/Times New Roman、主干线宽 3/次要 2、反馈虚线 DASH、画布 1440×940、严禁重叠、学术抽象块（非代码文件名）。
- 现有 13 张系统图（`.drawio/.png/.svg/.drawio.png` 四件套）在 [docs/thesis/figures/architecture/](file:///Users/bytedance/coding/AUV-Master-Project/docs/thesis/figures/architecture)；入选 LaTeX/Beamer 的图按 §3.6 契约额外生成 PDF/slide 变种。

### 3.6 LaTeX 与 Beamer 编译契约（2026-08-07 实测）
- 详细事实锚点：[首轮格式化与同步契约：环境与模板状态](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/首轮格式化与同步契约_20260807.md#L48-L128)。
- **ThuThesis**：仓库内 7.6.0；项目入口 `auv-thesis.tex` 固定 XeLaTeX + BibLaTeX/Biber + `gb7714-2015` + Fandol。`cd thuthesis && gtimeout 300 make auv-thesis` 会先检查第 1–6 章及附录 A 的 Markdown→LaTeX 同步状态和文献暂存，再构建 170 页 A4 F3 文档；当前无未解析引用、缺字或 Overfull。
- **ThuBeamer 1.2**：官方 `make beamer` 的 PdfLaTeX 路径不可作为 macOS 入口；项目入口 `auv-defense.tex` 固定 XeLaTeX + Fandol + 16:9。`cd thubeamer-1.2 && gtimeout 240 make defense` 已从干净构建状态生成 14 页骨架，BibTeX 引用已解析，日志无溢出。
- **仓库门禁**：`thuthesis` 已建立 `latex-migration-f1` 分支和 `.gitattributes`，261 个 CRLF 伪改动已归一化；原有 `data/chap01.tex` 与版本管理说明的真实修改保持未暂存。`thubeamer-1.2` 仍不是独立仓库。
- **迁移边界**：不覆盖两个模板的示例入口；新增 `auv-thesis.tex` / `auv-defense.tex`。正文、文献和图像的映射、Beamer 叙事、PDF/slide 图变种及 Linux→macOS 交接规则均以详细契约为准。

---

## 4. 目录地图与关键交付物（macwin 侧视角）

### 4.1 本侧维护的产出与工作目录 `毕业设计写作文档/`
- [毕业写作无ROS辅助完善计划.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/毕业写作无ROS辅助完善计划.md)（本侧计划书）
- [LaTeX迁移与答辩/首轮格式化与同步契约_20260807.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/首轮格式化与同步契约_20260807.md)（论文/答辩迁移、编译、图表变种与跨平台同步事实锚点）
- [LaTeX迁移与答辩/F2_第1至3章逐章迁移验收_20260807.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/F2_第1至3章逐章迁移验收_20260807.md)（F2 源/目标哈希、结构清单、编译与视觉验收）
- [LaTeX迁移与答辩/F3_第4至6章及附录迁移验收_20260807.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/F3_第4至6章及附录迁移验收_20260807.md)（F3 去重、状态边界、源/目标哈希、170 页编译与视觉验收）
- [LaTeX迁移与答辩/TMR8637规范化与概念顺序审计验收_20260808.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/TMR8637规范化与概念顺序审计验收_20260808.md)（TMR8637/TMR8607 参数边界、SK2301 采集链、ADC 量化、新息/NIS、ES-EKF/FWHM 叙述顺序及图片 TODO）
- [LaTeX迁移与答辩/第五章5.1仿真实施架构重写验收_20260808.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/LaTeX迁移与答辩/第五章5.1仿真实施架构重写验收_20260808.md)（仿真运行编排、在线闭环、证据生成、单次生命周期与多场景跑批组织）
- [参考文献/文献PDF/](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/参考文献/文献PDF) 当前为空；[参考文献/文献引用信息/](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/参考文献/文献引用信息) 已有 8 个索引/主题/BibTeX 文件，本侧持续维护。
- [相关插图（架构图）/](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/相关插图（架构图）)（**当前空**，drawio 产物可落此或 figures/architecture）
- [工具/](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/工具)：`split_ai_conv.py`（AI 对话切分，Linux 侧建）、`with_timeout.sh`（本侧建，超时包装器）
- 未完成/核心中间进度同步/潜在待完成事项（落盘规范目录）

### 4.2 Linux 侧已建交付物（**本侧只读参考，勿覆盖**）
- [AGENTS_linux.md](file:///Users/bytedance/coding/AUV-Master-Project/AGENTS_linux.md)（22KB，主索引，含全量行号锚点、AI 对话主题图谱、roadmap）
- [dashboard.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/dashboard.md)（进度看板，三级标题×pass；本侧据此认领「图片(1)/参考文献(5)」类缺口）
- [plan.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/plan.md)、[rating.md](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/rating.md)

### 4.3 论文正文实体（写作主战场，Linux 侧主导）
- [docs/thesis/paper/](file:///Users/bytedance/coding/AUV-Master-Project/docs/thesis/paper)：canonical 迁移入口为 `01_background_and_significance.md`、`02_system_design.md`、`03_state_estimation.md`、`04new_decision_and_control.md`、`05new_experiments_and_discussion.md`、`06_conclusion_and_outlook.md` 与附录 A；`INDEX.md` 已同步，旧 04/05 只保留作历史对照。
- 图目录 [docs/thesis/figures/](file:///Users/bytedance/coding/AUV-Master-Project/docs/thesis/figures)（architecture / experiments / terrain_following / cable_acceptance / console_operator_video）
- 审核报告（`毕业设计写作文档/审核报告_*.md`）：第三/四/五章 + 学术风格

### 4.4 附件与参照 `相关附件和参照/`（spec 源，本侧检索/读取用）
- `原始AUV类核心文档/`、`原始AUV部分潜在技术细节/`（BMS/罗盘/电机等高度专业化，选读）
- `本人新增传感器类/`（TMR8637 磁传感器 spec、FK2301 ADC）、`相关国家标准和行业论文/`（DL/T 1278—2025、T/CSGPC、GB/T 17502 等）、`考核和阶段性同步文件/`（采购清单 docx）

---

## 5. 当前情况（预备操作阶段快照，2026-08-07）

### 5.1 预备任务 DoD 核对（本侧计划书 `#L11-L14`）
| 预备任务 | 状态 | 结论 |
|---|---|---|
| 确认电脑操纵能力（computer use） | ✅ | accessibility=granted；screenRecording=**denied**（截图受限，见 §3.1） |
| 确认联网检索/下载 | ✅ | WebSearch 可用；Crossref 可用；院校认证下载 SOP 待实操 |
| 确认 bibtex + GB/T 7714-2015 | ✅ | **端到端实测通过**（§3.3），产出格式正确 |
| 确认多格式阅读（PDF/docx/代码/drawio） | ✅ | pdftotext/pandoc/Read 齐备（§3.4） |
| 确认 drawio-skill 存在与流程 | ✅ | 技能 + CLI(v30.3.14) + App 均在（§3.5） |
| 建立 `AGENTS_macwin.md` | ✅ | 本文件 |
| 超时兜底原则 + 包装器 | ✅ | §2.1 / §3.0 / `工具/with_timeout.sh` |

### 5.2 与 Linux 侧的并行态势
- Linux 侧已完成 P0 预备并进入 **P1 第五章审核**；已产出 dashboard/plan/rating/审核报告。
- 本侧已完成引用信息库和正文引用点的首轮收口；文献 PDF 仍待用户经院校认证下载。最终架构图统一在 `docs/thesis/figures/architecture/`，过渡目录 `相关插图（架构图）/` 保持为空。

### 5.3 已知约束/风险
- Computer Use 的 accessibility 与 screenRecording 均已授权；drawio 可通过桌面截图或读取导出 PNG 两种方式视觉自检。
- 付费文献墙 → 需浏览器 cookies 或用户手动下载，尚未实操验证。
- 系统 python3 第三方库匮乏 → 优先命令行工具链（curl/jq/pdftotext/latexmk），必要时 `pip install`/`brew install`。

### 5.4 LaTeX 首轮格式化快照（F0）
- 6 章 canonical 正文约 62 个图片引用，路径全部存在，但当前全部引用 PNG；入选论文的架构/曲线图需补同源 PDF，入选答辩的高密度图按需补 `_slide_169` 变种。
- 6 章真实引用键均可在 83 条 canonical `references.bib` 中命中；`tools/sync_latex_references.py` 为论文生成字节一致副本，为 Beamer 生成去注释且将 `@online` 映射为 `@misc` 的 BibTeX 兼容副本。
- **F1 已完成**：04/05 canonical 决策、`thuthesis` 分支/行尾基线、两个项目专用入口、6 章/附录骨架、14 页答辩叙事骨架及独立 Makefile target 均已落盘并从干净状态编译通过。
- **F2 已完成**：第 1–3 章共迁移 8 张图、12 张表、35 组展示公式；逐章合计 35 个引用键次，跨章去重后为 32 个唯一键。逐章引用集合一致，联合干净构建为 69 页 A4，验收细节见 F2 子文档。
- **F3 已完成**：第 4–6 章与附录共迁移 50 张非重复图、41 张表、10 组公式和 2 段 Bash 清单；去重后证据状态与结果边界一致。全书 255 个标签唯一，联合干净构建为 170 页 A4，验收细节见 F3 子文档。
- **F4 已完成**：中英文摘要、63 项符号与缩略语、17 页主答辩与 3 页备份已完成；附录 A、连续结果图排版和公式符号随后完成专项收口。当前进入 F5 发布审计。

---

## 6. 下一步（roadmap 摘要）

总路径：**承接 Linux 侧 boundary，产出文献与架构图两类交付物**。
- **A. 文献 grounding（对齐 dashboard 标「参考文献(5)」的节点）**：从第一章综述 + 第五章讨论所需引用切入 → Crossref 检索 → 落 bibtex + GB/T 文本到 `参考文献/文献引用信息/`，PDF 到 `参考文献/文献PDF/` → 回填正文占位符。优先补：海上风电/海缆故障率权威数据（1.1）、AUV 磁探测与埋深反演（1.2/2.3/3.3）、行为树与 MPC 综述（1.3/4.x）。
- **B. 架构图统一/补绘**：清点 dashboard 标「图片(1)」节点（2.2 双脑架构、3.1.2 组合导航框架、4.x 行为树/BT 等）；接收 Linux 侧图描述文本 → drawio 落地 → 导出四件套 → 相对路径回填。
- **C. 图风格统一**：按 §3.5 风格约定核对现有 13 张架构图 + 第四/五章 matplotlib 图的风格一致性（与 Linux 侧 P3 协同）。
- **D. LaTeX F1--F4（已完成）**：仓库基线、canonical 决策、第 1--6 章与附录迁移、摘要、符号表及 20 页答辩均已完成；当前推进 F5 发布审计与证据补齐。
- **E. 图表同步**：Linux 侧实验图更新必须同交 `_SOURCE.md`/manifest/生成命令/样本量；macOS 侧维护 draw.io 与出版变种。并行交接以 Git 提交为单位，不对两个活跃工作树执行裸 `rsync --delete`。
- **F. TMR8637 随附测试报告核验（已完成）**：三张资料分别确认为端子定义、编号 6# 模组三轴测试汇总和三轴本底噪声谱；50 Hz 处按纸质曲线读取约 20--30 pT/\(\sqrt{\mathrm{Hz}}\)，中心量级约 20 pT/\(\sqrt{\mathrm{Hz}}\)。四阶 Butterworth 低通在 0.5 Hz 截止频率下的模组本体 RMS 噪声估计为 0.014--0.022 nT；该结论只证明模组本体裕度，完整 TMR8637--SK2301--DLIA 链路仍待实测。

> **已定决策（2026-08-06 用户确认）**：
> 1. **文献下载分工**：本侧只负责**检索出摘要 + 链接并记录**（落 `参考文献/文献引用信息/`）；**由用户人工登录**（院校认证），再按用户指引下载 PDF → 放 `参考文献/文献PDF/`。本侧不自动注入 cookies 抓付费墙。
> 2. **架构图落盘**：**最终图统一落 [docs/thesis/figures/architecture/](file:///Users/bytedance/coding/AUV-Master-Project/docs/thesis/figures/architecture)**；[毕业设计写作文档/相关插图（架构图）/](file:///Users/bytedance/coding/AUV-Master-Project/毕业设计写作文档/相关插图（架构图）) 仅存放 **ROS 支线中间过渡 / 未完成** 的图。
> 3. **gtimeout 已安装**（§3.0，超时首选写法）。
> 4. **Computer Use 已全权限**（§3.1，含截图）。
