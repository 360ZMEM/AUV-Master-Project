# 中期报告派生验收

事实截止日：2026-10-13。用户已确认现论文题目与“硕士学位论文中期报告”身份。本记录区分文档派生、研究验证和正式提交。

**文档派生已完成，交付可审阅的中期报告候选版。** 两版均34页（前置4、正文29、参考文献1、附录0），共享六章正文，含9图、5表、12条文献。A1–F4共30项文稿验收通过；学院中期专用栏目适用性待补资料，Microsoft Word原生渲染未执行，正式提交仍由本人及导师确认。研究完成状态见下文，不因文稿验收通过而提升。

## 产物与构建契约

在仓库根目录或 `thuthesis/` 执行：

```bash
make auv-middle-defense          # 默认学院适配口径
make auv-middle-defense-main     # 锁定上游口径
make auv-middle-defense-school   # 显式学院适配口径
make auv-thesis                  # 原170页学位论文主线
make verify-thuthesis            # 离线核验完整vendor与运行文件
```

| 产物 | 位置 | 语义 |
|---|---|---|
| 共用报告源 | [auv-middle-defense.tex](../../thuthesis/auv-middle-defense.tex)、[middle](../../thuthesis/middle/) | 六章、概述、设置只有一套 |
| 默认学院版 | [school PDF](../../thuthesis/build/middle-school/auv-middle-defense-school.pdf) | Word资料有限差分 |
| 上游版 | [main PDF](../../thuthesis/build/middle-main/auv-middle-defense-main.pdf) | 不加载学院差分；保留真实中期报告身份 |
| 原主论文 | [auv-thesis.pdf](../../thuthesis/build/auv-thesis/auv-thesis.pdf) | 研究正文未改写；2026-10-17 起编译输出位于独立 build 目录 |
| 实际大纲/映射 | [OUTLINE](OUTLINE.md) | 候选到最终结构、图表取舍和页码 |
| 证据索引 | [evidence.tsv](evidence.tsv) | 原始/汇总来源级别、条件、统计口径、哈希及核对方法 |

主论文与中期报告的 `.aux`/`.bbl`/PDF 隔离。中期构建自动执行 `tools/check_middle_build.py`，遇缺字、缺引用、待重跑Biber、重复标签、越界盒或错误模板来源时返回失败；不屏蔽告警。发行源码锁见 [upstream-lock.json](../../thuthesis/upstream-lock.json)。

2026-10-17 的主论文输出目录迁移见 [迁移记录](../thesis/AUV_THESIS_BUILD_RELOCATION_20261017.md)。下文 2026-10-13 的日志、PDF 哈希与完整性审计均为当日冻结验收记录；其对应的旧 PDF 和最终日志现保存在 [迁移前备份](../../thuthesis/backups/20261017_before_build_relocation/manifest.json)，不把新路径的重编译哈希回填到历史清单。

## 模板与学院格式差分

完整上游采用 [ThuThesis v7.7.1](https://github.com/tuna/thuthesis/releases/tag/v7.7.1)，提交 `8b4d9443f39275d0492236ae4bfcd4532b799972`。完整267个受控源文件及许可、2个生成文件保存在 `thuthesis/vendor/v7.7.1/`，17个模板运行文件激活到实际编译目录。上游样例/文档/测试的最新版可在vendor查看；没有覆盖课题正文和原有示例目录。正常编译不追踪开发分支、不自动联网。

指定 Word 目录中56个有效文件均完成抽取，73个源文件（含附属文件）哈希保护；12个适用页面实际查看。[详细核对](word-audit/findings.md)同时检查实际段落、OOXML样式/节属性与渲染，不将未使用样式当要求。

| 要求 | 来源位置 | 上游行为 | 本地处理 | 核对结果 |
|---|---|---|---|---|
| 报告身份与字段 | 用户确认；旧开题PDF第1页核验学号等 | proposal封面标“选题报告” | 两版共同patch仅改为“中期报告”；日期2026-10-13 | 真实封面已检查；不是学院差分 |
| A4与3cm页边距 | `09正文 第3章` sectPr | A4/3cm | 保持 | XML数值一致 |
| 正文宋体12pt、20pt基线、两字缩进 | `09`实际P0003/P0004 | 12/20bp、两字缩进 | 保持；本机正文Fandol宋体、数学XITS | 尺寸一致；不冒称Windows字形逐像素一致 |
| 章标题黑体16pt，段前24/后18pt | `09`P0001/Heading1 | 16bp、27/27bp | 仅school改24/18bp | `middle/school-format.tex` |
| 节14、小节13pt及前后间距 | `09`Heading2、P0012/Heading3 | 14/13bp、24/6及12/6bp | 保持；冲突的全文样例14pt不优先于专用正文例 | 来源范围明确 |
| 页眉、页码、目录 | `09`与`06目录` | 页眉细线；前置罗马、正文阿拉伯；自动目录 | 保持；最终页面另查 | Word距纸边与TeX参数不机械等同 |
| 表/图题11pt、参考文献10.5/16pt | `17表格`、`18图`、`10-1参考文献` | 对应字号及相对位置一致 | 保持，自动编号/书目 | 不照搬LO转换中的重叠和断表 |
| 终稿表单 | 委员、授权、声明、成果、最终决议示例 | 可按文类加入 | 中期不加入 | N/A：不是本报告栏目 |

学院资料未找到中期专用表单/硬性页数；当前六章和约30页正文来自写作指引的编辑目标。LibreOffice 对旧DOC的网格/字体转换存在已记录差异，Microsoft Word 原生渲染为 NOT_RUN。适配表示与已给资料的明确数值对齐，不能代替学院对专用栏目或正式提交的确认。

## 命令、构建与回归记录

环境见 [environment.json](environment.json)：XeTeX/TeX Live 2022 Debian、latexmk4.76、Biber2.17、Poppler22.02、LibreOffice7.3、Python3.10。没有重装/升级用户的TeX Live。

- 升级前：原 `make auv-thesis` 及 `LATEXMK='latexmk -g'` 强制重编译通过，日志在 [baseline](baseline/)。原模板/论文504文件快照保存在 `thuthesis-before.tar.gz`，169/236页历史备份未动。
- G2代表页：两版 smoke 包含封面、标题、表、图、公式和引用，实际编译后查看封面；日志为 `baseline/smoke-main.log`、`baseline/smoke-school.log`。
- 升级后原稿首次遇旧Biber缓存残留，表现为无具体缺失项却反复请求Biber。隔离复现后仅把可再生缓存移到 `baseline/cache-before-reset/`，重新构建成功；没有改书目、正文或过滤错误。诊断见 [biblatex-stale-rerun.json](diagnostics/biblatex-stale-rerun.json)。
- 原论文正文/图/书目保护、8页模板排版变化与实际页面检查见 [thesis-regression.json](thesis-regression.json)。旧/新均170页；授权说明措辞按上游改变；参考文献152–158页重排，条目内容一致；其他162页提取文本一致。
- `tools/manage_thuthesis.py` 的完整vendor核验、激活、回退及编辑保护在隔离副本完成15项通过，实际受管文件哈希未变；见 [update-tool-check.json](update-tool-check.json)。没有为测试在真实工作区来回切换版本。

最终记录为 [final-builds.json](final-builds.json)，2026-10-13 13:46–13:47（本地时间）。两版在最后一处正文修改后实际重新编译；显式school别名随后复用同一PDF并再次执行检查。主论文此前已在新模板下完成重编译与受影响页面回归，最后一次make是无源变化的增量检查。没有用旧PDF冒充新报告。

| 实际命令 | 退出码 | 日志 | 产物 |
|---|---:|---|---|
| `make auv-middle-defense` | 0 | [school日志](final-build-school.log) | school，34页 |
| `make auv-middle-defense-main` | 0 | [main日志](final-build-main.log) | main，34页 |
| `make auv-middle-defense-school` | 0 | [别名日志](final-build-school-alias.log) | 同一school，34页 |
| `make auv-thesis` | 0 | [论文日志](final-build-thesis.log) | 原论文，170页 |
| `make verify-thuthesis` | 0 | [模板日志](final-build-template.log) | 267源文件、2生成文件与17激活文件核验 |

最终PDF SHA-256：

```text
main   5f1b951e1a54d26cdaaf93f7f5939a7b347dc16dc5f01fb215053969ac4b68d9
school bfbae2d0d4ee73c14e68c590096a11326121bc27a988b90f62e196e49e9e29cc
thesis c622cee72099184f7f60bee99b2d512a25f1b25876bc9e44ce3924416e143977
```

最终 [完整性审计](delivery-integrity.json)核对112条证据来源、51项绘图来源/旧图/生成器/输出、14份原研究源及48项旧图。504项初始文件中489项不变，15项为7个模板内容更新、Makefile和7个可再生论文产物；无意外变化或缺失。两版recorder实际读取同一本地class和共享章节，只有school加载学院差分；去除分页信息后的全文相同。

视觉证据为 [school逐页记录](visual-school.json)、[main逐页记录](visual-main.json)，分别绑定最终PDF和34张130dpi页面图；共68页均实际查看。两版各40项目录与41条书签均与页面匹配。[最终字号审计](figure-size-check.json)的`post_fix`检查18处图像：磁图最低9.0002pt，系统适配图9.5002pt，ADC图11.3227pt，TikZ图10.5pt。早期失败记录保留为历史，不用于最终通过判断。

告警分类：两版最终日志各4条`Underfull hbox`均在表2.1第一列的中文换行，PDF第9页已查看，无裁切、遮挡或越界，保留；无`Overfull`、缺字、未定义引用或待重跑书目。原论文14条既有Underfull（升级前15条）已在回归中检查。Poppler渲染每版出现7条字体类型/嵌入声明提示，命令返回0且所有页面无可见乱码；提示未屏蔽。PDF第17页章尾完整边界段留白较多，仍在页数预算内，不删必要实验边界来填满版面。未执行Microsoft Word原生逐像素对照，不将LibreOffice字体替换当作Word原样。

## 发现及处理

1. 初版存在三处章末2–3行孤页：压缩第1/2章重复收尾、第5章M2.5重复定义；未压字号、版心或负间距。
2. 八幅复用图中七幅缩放后存在约5–8pt关键小字：中期报告单独适配，原图、原绘图脚本和实验数据保留。磁图及系统图来源/导出记录分别为 `middle-magnetic-figures.json`、`middle-systems-figures.json`；首次字号审计保留在 `figure-size-check.json`。
3. 内容核对补清二维线偶极和三维点偶极区别；受控基线背景来自生成器；两组滤波矩阵输入不同；控制差分含混合编码尺度；历史背景raw缺失只按汇总引用；时序反例补精确来源。修订不改变旧论文结论/旧结果。
4. 严格区分条件性横向巡检、深度空值、外部参考、导航误差界和真实部署。控制负收益、场形误拒、阶跃撤权后漂移及PC104旧恢复序列失败均保留。
5. 最后一次全页检查发现main章5末尾仅一行独占一页，删除重复过渡句后main由35页收束至34页；school仍34页。两版重新构建、重新渲染并再次逐页检查通过。没有改变研究结论。

## A1–F4逐项验收

下表PASS仅指本次文稿任务对应检查满足；历史研究负结果、缺失原始包和正式学院审核另列，不混为研究通过率。证据路径均相对本目录，PDF页码为物理页。

| ID | 状态 | 检查方法/实际命令 | 证据路径或页码 | 发现与处理 | 剩余动作 |
|---|---|---|---|---|---|
| A1 | PASS | 初始git状态/差分、tar和SHA清单；最终逐文件比较 | `baseline/`、`delivery-integrity.json` | 504项基线、用户既有修改保留，无重置 | 无 |
| A2 | PASS | 14研究源+48旧图SHA；170页文本与受影响页比较 | `thesis-regression.json`、`delivery-integrity.json` | 正文/书目/旧图不变；上游授权文字与参考文献重排已列出 | 无 |
| A3 | PASS | `make verify-thuthesis`；检查最终recorder/class SHA | `upstream-lock.json`位于thuthesis；两版`.check.json` | 完整v7.7.1与本地适配分离，实际加载本地类文件 | 后续换版本重新核验 |
| A4 | PASS | 56份Word抽取/样式比对；12页实际查看 | `word-audit/findings.md`及其清单 | 已辨别终稿样例范围；school仅章标题24/18bp差分 | 专用中期表单另列H1，不冒称已获学院认可 |
| A5 | PASS | wrapper/recorder比对；隔离15项激活/回退检查 | `delivery-integrity.json`、`update-tool-check.json` | 默认school，共用全文；输出/缓存隔离；只回退受管模板 | 无 |
| B1 | PASS | 用户确认、真实setup及旧开题资料对照；看最终封面 | `CONTEXT.md`、两版PDF1–2 | 题目/中期身份/截止日2026-10-13与姓名学号正确，无示例人物 | 正式提交审核 |
| B2 | PASS | 阅读全部六章及概述，检查源与PDF | `OUTLINE.md`、两版PDF2、5–33 | 背景、方法、结果、问题、计划均成文，无空章/占位句 | 无 |
| B3 | PASS | 核读汇总、可用CSV轻量复算、112来源SHA | `evidence.tsv`、两绘图manifest、`delivery-integrity.json` | 分母/单位/MAE-RMSE/独立运行与重叠窗口分开；缺raw只按汇总级引用 | 原包可选补档，不补造复算 |
| B4 | PASS | 逐节检查贡献归属、时态和验证层级 | PDF5、7、18、26–33；`review-content.json` | 原艇/复用理论、作者改造、已验证子链和计划分开 | 无 |
| B5 | PASS | 核对局部条件、反例、集中讨论 | PDF12–17、19–21、25–30 | 失配2.753m、误拒、控制负收益、撤权仍漂移、旧恢复失败保留 | 研究缺口按W1–W5推进 |
| B6 | PASS | 图文/符号/版本/引用逐项核读与导出核验 | `review-content.json`、`evidence.tsv`、`delivery-integrity.json` | 明确二维线偶极、z/h/d、统一导航系与不同输入矩阵；12引文有效 | 无 |
| C1 | PASS | 将第5章缺口逐项映射第6章工作包 | PDF29–33；`OUTLINE.md` | 目标—证据—缺口—下一验证连续 | 无 |
| C2 | PASS | 检查W1–W5每行前置/窗口/验收/受阻处理 | PDF32表6.1 | 使用前置满足后相对周数，不承诺未知日期 | 实施时由现场条件更新 |
| C3 | PASS | 核对M2.5定义及完成状态 | PDF28、30–32；`PLAN-M25`证据 | 基础平台恢复/受控水中运行尚未完成，不等同海缆任务 | 待同次实物证据 |
| C4 | PASS | 对照原目标及本次指引；检查计划准入 | 第5.3/6.1–6.4节 | 改实施顺序，保留必要反馈/水密/退出，不降学位要求或新增远期支线 | 无 |
| D1 | PASS | `pdfinfo`、目录和实际全页核对 | `figure-size-check.json.post_fix`、`OUTLINE.md` | 两版4+29+1+0=34，满足编辑预算 | 无 |
| D2 | PASS | 逐章文件/目录/书签/最终页码对照 | `OUTLINE.md`、`figure-size-check.json.post_fix` | 实际六章与二级目录、原稿映射、最终页码已回填 | 无 |
| D3 | PASS | 全文顺读及章尾分页检查 | `review-content.json`、两版视觉记录 | 压缩重复收尾和同质结果，无附录回填；不删必要条件 | 无 |
| D4 | PASS | 从概述/目录定位成果、证据与下一步，再顺读方法结果 | PDF2–4、10–28、31–33 | 表1指向第3/4章结果与第5/6章缺口计划；正文不依赖聊天或视频 | 此项为阅读自审，非真人计时试验 |
| D5 | PASS | 全文体例与词句审查 | 六章正文、`review-content.json` | 按问题/方法/证据叙述；代码路径留在维护资料，非流水账 | 无 |
| E1 | PASS | 实际执行五个make入口 | `final-builds.json`、五份最终日志 | 均exit0；两报告在最后源变更后重编译；主论文已新模板回归 | 无 |
| E2 | PASS | 自动日志检查及人工告警分类 | 两版`.check.json`、最终`.log`、本记录告警段 | 无错误/缺图/缺字/未定义引用/重复标签/Overfull；4条Underfull已看 | 无 |
| E3 | PASS | `pdftoppm -r 130 -png`后实际`view_image`每页 | `visual-school.json`、`visual-main.json` | 最终34+34页已全部查看，无已知遮挡/乱码/越界 | 无 |
| E4 | PASS | 图表六标准核读、实际嵌入字号计算、逐页查看 | `figure-size-check.json.post_fix`；PDF7、13–16、22、24–25、27、32 | 数据可回查/目的明确/最终可读/风格一致/表达准确/源可维护；18放置≥9pt，长表公式完整 | 无 |
| E5 | PASS | 看封面目录页脚；40目录项与41书签逐项检查 | PDF1–4、34；字号审计的目录/书签记录 | 正确中期身份、罗马/阿拉伯页码，无终稿声明/假签名 | 专用表单适用性见H1 |
| E6 | PASS | 主论文重编译+受影响页检查；新增图脚本实际运行 | `thesis-regression.json`、`plot-magnetic.log`、两绘图manifest | 原170页研究内容保真；7适配图独立保存，保留原图 | 无 |
| F1 | PASS | 检查源/PDF/维护文档/命令实际存在并可读 | 本记录产物表、`delivery-check.json` | 双PDF、六章源、大纲映射、30项验收齐备 | 无 |
| F2 | PASS | 文档状态与研究层级逐项分列 | 本记录“两条完成度”及第4.5/5/6章 | 文档完成；M2.5/任务级实物未完成未验证；资料阻塞另列 | 按缺口补证，不升级已有状态 |
| F3 | PASS | 已确认信息复用，剩余事项集中且给最小变更位置 | 本记录H1/H2与人工事项表 | 不要求重查已验图文；仅专用通知/正式审核留人工 | 本人/导师处理正式要求 |
| F4 | PASS | 同步/回退隔离验证；共用源/实际绘图入口核对 | `update-tool-check.json`、下方命令与`CONTEXT.md` | 显式锁版本更新；一套正文、两格式，无自动覆写课题数据 | 以后按实际新版本回归 |

图表六标准的具体依据：量化图使用冻结数据或保留原矢量曲线；图2.1清楚标示“接口示意”；各图有正文用途和条件图注；配色沿用论文宋体/STIX风格，线型辅助区分；坐标单位、对数轴、异比例地图和归一化阈值均标明；脚本、来源SHA及PDF/PNG齐备。原PC104 raw缺失时只组合旧PDF矢量内容，没有数字化截图生成新数据。

## 两条完成度与未完成事项

文档派生：模板更新、给定学院材料核对、六章正文、图表、构建、双版全页视觉检查、原主线回归均完成。30项文稿验收为PASS；没有已知未修复的构建或严重排版缺陷。当前可作为本人/导师审阅候选稿，**不将学院专用栏目尚待确认或正式审核表述为已通过**。

研究层面：

| 层级 | 截止日状态 | 证据与下一步 |
|---|---|---|
| 方法与受控仿真 | 已完成所述条件下验证 | 第3章FWHM/场形拒绝/有限巡检，第4章估计控制对照；不外推为海况概率 |
| 实物子链 | 已有测量、计算和真实通信证据 | 第4章TMR/ADC/复I/Q、Jetson、PC104；历史背景与PC104部分raw不在当前检出，按汇总级引用 |
| M2.5基础平台与水中受控运行 | 未完成、未验证 | 第4.5/5.3/6.1；需能源、反馈、执行、固定水密与同次受控运动/退出包 |
| 真实磁标定、目标关联和完整任务时序 | 待完成 | W3/W4；需要可溯源几何与真实输入、导航误差依据和同次链路 |
| 任务级实物海缆巡检 | 未完成、未验证 | 依赖W1–W4、人员设备和场地，不由文档或子链通过推定 |

本次文稿任务不操作现场，所以现场资源不足仅限制研究计划推进，不自动成为编译/写作阻塞。对缺失raw不制造补算结果；可补原包后提高证据等级。

尚未完成/未验证事项单列如下，不因资料缺失而停止已授权写作，也不将它们算作文稿通过的研究结果：

| 编号 | 状态 | 原因及影响 | 是否影响当前候选稿 | 下一动作 |
|---|---|---|---|---|
| H1 中期专用通知/必填栏目适用性 | BLOCKED | 给定目录只有终稿Word示例，未发现独立中期要求，不能证明没有其他通知 | 不妨碍按现有材料审阅；正式提交前须确认，若新增硬性栏目则先补齐 | 本人提供/确认适用通知；仅改封面、前置或栏目映射 |
| H2 Microsoft Word原生渲染对照 | NOT_RUN | 当前使用LibreOffice转换、XML核对及PDF视觉；Windows字体/行网格非逐像素等同 | 不阻止当前LaTeX候选；不声称Word原样一致 | 如学院要求原生Word比对，再用其环境核验 |
| H3 历史PC104及背景原始包完整复算 | BLOCKED | 部分原CSV/两份背景NPZ不在当前检出；已按详细汇总或原矢量图引用 | 不妨碍限定层级主张；不能提升为本机raw复算通过 | 找回原包并核SHA后可补复算 |
| H4 M2.5及完整海缆实物任务 | NOT_RUN | 当前尚缺同次整艇反馈、执行、运动及退出证据 | 不自动阻止中期材料；报告明确未完成 | 按W1–W5及现场条件推进 |
| H5 正式提交审核 | NOT_RUN | 本轮交付为候选，未提交学院、未代签或发送 | 正式送交之前需要本人/导师审核 | 审核研究范围、材料要求和署名 |

人工只需处理：

| 问题/原因 | 已查来源 | 默认建议 | 确认后最小修改范围 |
|---|---|---|---|
| 是否另有中期专用通知/必填栏目；目录内无法推知未提供要求 | 56份有效Word、旧开题PDF、根写作指引；已集中询问一次 | 先审阅当前六章稿，正式提交前核对本届通知 | `middle/setup.tex`、共享前置页或`OUTLINE.md`局部映射 |
| 正式提交及本人/导师认可，工具不能代为决定 | 已完成事实/图文/排版验收，题目类型截止日用户已确认 | 以默认school PDF作为审阅入口 | 仅修改审核意见涉及位置；不复制两套正文 |

没有要求用户替本轮逐页排版检查。题目、类型、截止日不再重复提问；历史缺失raw按证据边界处理，现阶段无需为完成文稿强行补实验。

## 图像再次导出与环境

普通LaTeX编译直接使用已交付PDF图，不要求安装Python绘图依赖。本次独立绘图环境为 `/home/zmem063/.local/share/auv-middle/venv`，Python3.10、numpy1.24.4、matplotlib3.5.1、PyMuPDF1.28.2；只新增PyMuPDF到隔离环境，没有安装/升级TeX Live。版本表见 [requirements-middle-figures.txt](../../tools/requirements-middle-figures.txt)。在当前机器可复用已实际运行的命令：

```bash
/home/zmem063/.local/share/auv-middle/venv/bin/python tools/plot_middle_magnetic.py
/home/zmem063/.local/share/auv-middle/venv/bin/python tools/plot_middle_systems.py
make auv-middle-defense-main
make auv-middle-defense-school
/home/zmem063/.local/share/auv-middle/venv/bin/python tools/plot_middle_systems.py --audit-final
```

在另一台Linux机器新建绘图环境可采用下列迁移示例（本次实际环境建立细节见`environment.json`；正常make无需执行）：

```bash
python3 -m venv /本机可写路径/auv-middle-venv
/本机可写路径/auv-middle-venv/bin/python -m pip install -r tools/requirements-middle-figures.txt
```

还需可用的Poppler和论文现有Fandol字体。共享目录`vboxsf`可能不支持venv链接，因此本次环境放在本机原生文件系统。全局`pip check`中的既有HoloOcean/posix-ipc依赖问题未处理，本次绘图导入与导出均已通过，未把无关环境问题伪报为修复。每次重绘或修改正文后重新编译、检查受影响图页；如作为新的最终稿交付，再绑定新的PDF哈希和全页视觉记录。

## 以后同步、回退和更新证据

正常重编译使用上面的make入口。模板不在普通编译时自动更新。以后从官方发布页选定明确版本后，在仓库根目录执行（把 `vX.Y.Z` 替换为真实标签）：

```bash
python3 tools/manage_thuthesis.py fetch --tag vX.Y.Z
python3 tools/manage_thuthesis.py activate --tag vX.Y.Z
make verify-thuthesis
make auv-middle-defense-main
make auv-middle-defense-school
make auv-thesis
```

`fetch`保存整个官方标签树及源哈希，再由其ins生成类文件；不会隐式激活。`activate`先检查当前运行模板是否有本地改动，备份再只更换受管运行文件并写锁。已有同名vendor拒绝覆盖；发现本地模板改动拒绝自动切换，需要先将有意适配移到本地设置再协调。

切换后若需回退，使用该次打印的路径：

```bash
python3 tools/manage_thuthesis.py rollback --snapshot thuthesis/backups/template-switch/本次快照目录
```

回退仅恢复模板文件及其旧锁，遇切换后再次修改会拒绝覆盖。本次7.6.0→7.7.1的实际快照为 `thuthesis/backups/template-switch/20261013T131439138343`；回到该初始未锁定状态后可编译原论文，但中期make会要求先激活受管理的版本。后续受管理版本间回退会恢复旧锁。**不会回退正文、原始数据、原图或其他用户改动。**

未来版本需重新检查共享报告身份patch与school标题接口、实际加载路径、引用日志及受影响页面，不能因激活成功就宣称所有排版通过。新增实物证据按 [CONTEXT](CONTEXT.md) 最后一节的单套正文入口更新并登记 `evidence.tsv`，再编译/渲染受影响页面。
