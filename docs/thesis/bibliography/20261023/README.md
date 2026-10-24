# Bib—正文工程收口记录（2026-10-23）

本轮按仓库根目录的《Codex_auv_bib正文收口_20261023.md》完成共享 Bib 替换、必要正文同步与三份文档编译。文献身份及替代选择采用作者已完成人工核对的交付；未联网、未新增文献、未改写输入 Bib 元数据，也未重新开展文献检索或整篇论文 L3 逐句查证。

**更改文件与备份**

| 文件 | 本轮更改 |
|---|---|
| [共享 Bib](../../../../thuthesis/ref/auv-references.bib) | 用 [作者最终输入](../../../../auv-references-final-20261023.bib)完整覆盖，98 个唯一 citekey，字节一致。 |
| [第一章](../../../../thuthesis/data/auv-chap01.tex) | 同步两处核心段落，撤销相邻的错误标准归因；明确厂商案例和 DIVE-LD 项目报告的适用边界。 |
| [第二章](../../../../thuthesis/data/auv-chap02.tex) | 同步精度约束的标准来源与研究目标边界；仅修正需求表的来源文字，保留所有目标数值；区分 TMR8607 单轴手册参数与 TMR8637 三轴测试报告。 |
| [中期共享第一章](../../../../thuthesis/middle/chap01-background.tex) | 补齐 SBP 两篇来源与正式标准，将 0.2 m 明确为自主研究目标；main/school 同步生效。 |
| [文献入口](../README.md) | 更新为 98 条与本次收口记录，区分历史机器审计与作者确认的新库。 |

更改前的 Bib、三份 PDF、相关 TeX/编译记录已保存在 [before/](before/)，逐文件校验值见 [before_manifest.json](before_manifest.json)。本轮正文与 Bib 的独立差分见 [bib_body_changes.patch](bib_body_changes.patch)，它以本轮开始时的工作区为基准，没有混入原有未提交修改。

第 4、5 章在本轮期间有其他并行更新，本轮未编辑或回滚这两章；最终主论文已按更新后的正文重新编译。对 315 个模板、正文和图像文件进行前后哈希检查，除本轮四个内容文件与上述两章外，无其他既有文件变化；算法、实验数据、结果数值、图像、章节结构和引用样式均未由本轮修改。

**核心段落 A：磁探测指标与标准**

只列变更的指标归因句；前面的学术综述和后面的三芯海缆模型引用保留。

更改前：

```tex
本项目的 0.05 nT 灵敏度与 0.2 m 埋深误差指标则以《DL/T 1278---2025 海底电力电缆运行规程》\cite{dlt1278_2025}和《海底管道及海底电缆检测技术规范》\cite{tcsgpc_cable}为直接依据。
```

更改后：

```tex
在技术指标设置方面，本文参考《DL/T 1278---2025 海底电力电缆运行规程》所述运行维护要求，其适用范围为 10 kV 及以上交流海底电力电缆\cite{dlt1278_2025}，并结合《T/CIN 100---2026 海上风电场通航安全技术参数测量要求》中海缆探测设备与测量误差的规定\cite{tcin100_2026}。后者在附录 B.5 提出磁力仪灵敏度应优于 0.05 nT，第 7.2 条提出海缆埋深测量极限误差不超过 $\pm0.4~\mathrm{m}$。本文以 0.05 nT 作为磁测量灵敏度的设计参考，并将 0.2 m 设定为更严格的自主埋深估计研究目标，而非标准的规定限值或已通过实物验收的性能。
```

第二章相邻文字与表格也作同义修正，避免第一章收口后仍将 0.2 m 写成行业硬性限值。0.05 nT 是设计参考；T/CIN 100—2026 的埋深测量极限误差是 ±0.4 m；0.2 m 是更严格的自主研究目标，不表示整机实物验收已通过。DL/T 1278—2025 的引用限定于 10 kV 及以上交流海底电力电缆运维。

**核心段落 B：SBP 掩埋目标探测**

更改前：

```tex
侧扫声呐用于 AUV 海缆/管线自主跟踪已有系统性研究\cite{bagnitsky2011sidescan,feng2023automatic}，多平台声学建图也被用于海缆路由勘测\cite{jung2022multimodal}；针对掩埋目标，浅地层剖面仪凭借低频穿透在管线与海缆探测中发挥作用\cite{geomatching2022sbp,zheng2021zeroshot}，三维声学成像更被用于完全掩埋风电海缆的探测\cite{ha2022buried}。
```

更改后：

```tex
侧扫声呐用于 AUV 海缆/管线自主跟踪已有系统性研究\cite{bagnitsky2011sidescan,feng2023automatic}，多平台声学建图也被用于海缆路由勘测\cite{jung2022multimodal}。针对掩埋目标，浅地层剖面仪（Sub-Bottom Profiler，SBP）利用声波对海底沉积层的穿透能力，已被用于海底电缆埋深调查与掩埋管线目标检测\cite{wunderlich2016burial,zheng2021zeroshot}。三维声学成像更被用于完全掩埋风电海缆的探测\cite{ha2022buried}。
```

侧扫声呐、多平台建图、三维成像的其他引用不变。中期报告同步引用 `wunderlich2016burial` 与 `zheng2021zeroshot`，分别表达海缆埋深调查与掩埋管线检测，没有将管线结果写成真实高压海缆的精度验收。

**引用键与输入一致性**

- 输入及目标 Bib 的 SHA-256 均为 `a73e01e01bb1839b949e0534405a46b9de5cb77a3497ac6b834c13b5f0a1b9b4`；98 条、98 个唯一键，未格式化重写。
- 删除 `tcsgpc_cable`、`geomatching2022sbp`，新增 `tcin100_2026`；无其他 citekey 重命名。
- 全仓非归档 TeX 搜索未发现两个旧键的引用。历史审计、备份和 Bib 头部说明保留旧键仅用于追溯，不是生效引用。
- 三份实际 BCF 均仅加载 `ref/auv-references.bib`；BCF 与 BBL 的条目集合逐键一致，没有重复 BBL 条目、未定义键或缺失条目。
- 中期报告正式正文从 12 条增加到 16 条实际引用；静态包含图另有 1 条格式 smoke 分支引用，不计入正式报告。主论文实际引用 89 条；库内其余 9 条仍可供后续使用，不为凑满条目而新增无关引用。
- 已核对最终 BBL：正式标准按 S 类型、Project 129 与 2017 厂商案例按 R 类型输出；TMR 手册为 2024 / Version 1.0；两条没有确证出版年的 Teledyne 资料未重新生成 year 字段。继续使用原有 `gb7714-2015` 样式，编号由 Biber/LaTeX 自动生成。

静态检查见 [static_checks.json](static_checks.json)，最终编译/BCF/BBL/PDF 检查见 [acceptance.json](acceptance.json)。

**三份文档编译与排版验收**

实际执行：

```bash
make auv-thesis auv-middle-defense-main auv-middle-defense-school
```

| 文档 | 结果 | PDF 页数 | BCF 键数 / BBL 条目 | 产物 |
|---|---|---:|---:|---|
| 主论文 | PASS | 180 | 89 / 89 | [PDF](../../../../thuthesis/build/auv-thesis/auv-thesis.pdf) |
| 中期报告 main | PASS | 38 | 16 / 16 | [PDF](../../../../thuthesis/build/middle-main/auv-middle-defense-main.pdf) |
| 中期报告 school | PASS | 38 | 16 / 16 | [PDF](../../../../thuthesis/build/middle-school/auv-middle-defense-school.pdf) |

最终上述三目标整体命令返回 0，日志见 [build-delivery.log](build-delivery.log)。XeLaTeX 最终日志无未定义引用、未定义交叉引用、缺字、重复定义或 Overfull 警告；Biber 最终日志无 WARN/ERROR，两版中期报告各自的既有格式门禁均 PASS，模板仍为 v7.7.1。主论文保持 180 页；两版中期报告由 36 页变为 38 页，正文及书目按原模板自然分页，未更改结构或格式参数。

首次增量构建曾读取旧 BCF，出现旧键的过渡警告；重新生成 BCF 后最终日志已清除。首次三目标连续构建在学院版开始时以 143 终止；学院版单独重跑和随后完整三目标重跑均返回 0，不存在待解决的构建阻塞。

已抽查主论文 SBP 段落、正式标准段落、第二章指标来源表，以及书目中正式标准、SBP 两篇、TMR 手册和项目报告；中期报告抽查指标段落及参考文献页。目标段落无重复引用、乱码、错位、意外空白或显著溢出。PDF 全文抽取中的代码控制字符会产生额外换页符，物理页码以 `pdftotext -bbox` 的 page 元素和逐页提取复核，不使用全文 `\f` 数量推定。

PDF 抽查截图及其对应文档哈希见 [visual_checks.json](visual_checks.json) 与 [rendered/](rendered/)。主论文抽查实页 26、27、37、163–165；中期报告抽查 main 实页 6 与 school 实页 35–36。

**未解决的纯工程问题**

既有 `gb7714-2015` 对 TMR 手册的版本信息重复显示为两次 `Version 1.0`，在更改前 PDF 中同样存在。它不是新 Bib 的重复条目或未定义引用；本轮按“不改交付 Bib 元数据、引用风格”的约束保留，并在 [acceptance.json](acceptance.json) 中登记。除此之外，本次 Bib—正文工程收口无待解决问题；本轮完成不代表整个学位论文 L3 逐句审查完成。
