# references.bib 使用说明

> 本目录 `references.bib` 是第 1–4 章参考文献的**统一 BibTeX 库**，供论文正文 `\cite{}` 直接引用。
> 检索/摘要/链接明细仍以各主题 Markdown（`10_bg_offshore.md` / `20_detection.md` / `30_estimation.md` / `40_control.md`）与 `00_引用点总索引.md` 为准；`.bib` 只承载可编译的题录。

## 1. 工具链（GB/T 7714-2015）
- 引擎：`xelatex` + `biblatex`（backend=biber）+ `biblatex-gb7714-2015`。
- 导言区示例：
  ```latex
  \usepackage[backend=biber, style=gb7714-2015]{biblatex}
  \addbibresource{references.bib}
  ```
- 文末：`\printbibliography`。编译顺序：`xelatex → biber → xelatex → xelatex`。
- **务必以 UTF-8 打开/保存**；中文条目已加 `langid={chinese}`，gb7714 会自动切换中英文著录格式（如"等" vs "et al."）。

## 2. 分区与状态
> **库总量：83 条**（A 70 ｜ B 6 ｜ C 7）。其中中文条目（`langid={chinese}`）共 7 条（B 区 3、C 区 4）。此表与 `.bib` 文件头部的分区统计（约第 13 行）一致。
> **A 区含"展望/未来趋势"子区（F1–F8，共 8 条）**，专供第 6 章"结论与展望"引用；DOI 均可经 Crossref 解析，题录取自官方 content negotiation 接口。

| 区 | 含义 | 条数 | 类型分布 | 可否直接用 |
|---|---|---|---|---|
| **A** | Crossref/DataCite 内容协商**已验证**题录（DOI 可自动解析） | 70 | book 4 / article 47 / inproceedings 16 / online 3 | ✅ 可直接引用 |
| **B** | 题录经**期刊官网/会议原文核实**，但 DOI 属 **CSTR/期刊自有体系，Crossref 不可解析**（中文期刊/新刊/会议） | 6 | article 5 / inproceedings 1 | ✅ 可引用；DOI 需用 CSTR/万方或原刊链接核销，勿指望 Crossref |
| **C** | 政策/行业报告/标准/网页，**无 DOI**（`@online`, [EB/OL]/[R]/[S]） | 7 | online 7 | ⚠ 核对正式文件名/发布号/访问日期 |

> **A/B 边界的准确含义**：A 区与 B 区题录**均已核实、均可放心 `\cite`**；唯一区别是 **DOI 能否经 `api.crossref.org` 内容协商解析**。B 区 6 条中——中文刊 `10.11993/*`（水下无人系统学报：`sun2026magnetic`、`zhang2023sinsdvl`）、`10.16516/*`（南方能源建设：`cen2017submarine`）前缀注册于 **CSTR/万方**；`10.23380/*`（InUS Transactions 新刊：`zhang2025submarine`）、`10.23784/*`（Hydrographische Nachrichten：`wunderlich2016burial`）尚未进 Crossref；`hatlo2015accurate`（Jicable'15 会议原文）无 DOI。这些条目在原刊官网/会议论文集可正常核验，只是不在 Crossref 索引里。

## 3. 引用键约定
`作者姓 + 年份 + 主题词`（全小写），如 `mayne2000constrained`、`sola2017quaternion`、`sun2026magnetic`。
每条上方注释给出 `[索引号] 引用点 章节 + 来源核验状态`，与 `00_引用点总索引.md` 的 C*/D*/E*/G* 编号一一对应。

## 4. 已修正 / 需注意
- **REMUS（C6, `purcell2000remus`）**：DOI 由错误的 `…881247`（实为 Stojanovic 声通信文）**修正为 `10.1109/OCEANS.2000.881250`**，已据 OCEANS 2000 参考文献列表核对。
- **Cui 2018（D5, `cui2018magnetometer`）**：Crossref 全称含 pedestrian/foot-mounted 应用域，页码 **166–174**（非索引原记 1017–1024）。
- **Yordanova 2020（`yordanova2020coverage`）**：Crossref 页码 **4774–4780**（非 4781）。
- **Piché（`piche2016online`）**：Crossref online-first 2015，正式卷期年 2016。
- **Wunderlich（`wunderlich2016burial`）**：据 dhyg.de 原文 + HYDRO 2016 PPT 修正——作者 **Jan Arvid Ingulfsen / Sabine Müller**（原录入 Arild / Sebastian 有误）；页码 **HN 105: 50–54**（原记 6–11 系 HYDRO 2016 会议稿页码，非期刊版）。
- **Zhang 2025（`zhang2025submarine`）**：作者名补全为 **Zhang, Qiang**（原缩写 Qi）。
- **Sun 2026（`sun2026magnetic`）/ Zhang 2023（`zhang2023sinsdvl`）**：据水下无人系统学报官网**补全全部作者**（8 位 / 5 位），已去除 `and others`。
- **Chen 2023（`chen2023kalman`）**：DataCite 已解析（DOI `10.48550/arXiv.2306.07225`），5 位作者全，**已从 B 区移入 A 区**。
- **Mesbah 2016（`mesbah2016stochastic`）**：题名/作者经 IEEE Xplore + eScholarship 双源核实。
- 页码统一用 `--`（en-dash）；mojibake（`â€"`/`Ã¤` 等）已清洗为 UTF-8 正确字符。
- **新增第 6 章展望子区（A 区 F1–F8，8 条）**：`tobin2017domain`（域随机化 Sim-to-Real，IROS 2017 奠基）、`yan2026digitaltwin`（数字孪生驱动 AUV 集群，*Communications Engineering* 2026）、`hewing2020learning`（学习型 MPC 综述，*Annu. Rev.* 2020）、`zarrouki2024stochastic`（带不确定性传播时域的随机 NMPC，ACC 2024，呼应 UA-MPC）、`bodenmann2024realtime`（实时海缆检测，IEEE/OES AUV 2024）、`yan2023formation`（多 AUV 编队控制综述，*Intelligence & Robotics* 2023）、`li2025cooplocalization`（最大熵鲁棒多 AUV 协同定位，*IEEE T-ASE* 2025）、`curtin2018resident`（驻留式 AUV 与水下对接，AUV 2018）。题录均取自 Crossref content negotiation 官方接口，DOI 可解析。

## 5. 待办（不影响主体编译）
- **A6/A7/A10 三个零散点已入库**：A6 教材出处 `griffiths2017electrodynamics`（Biot-Savart 三芯正演物理基础，A 区）；A7 铠装涡流屏蔽 `hatlo2015accurate`（Jicable'15 三芯海缆损耗解析公式，B 区，无 DOI）；A10 50 Hz 陷波 `song2020dlia`（数字锁相放大器抗工频干扰，A 区）。
- **B 区 6 条已全部核实完毕**（`zhang2025submarine` / `wunderlich2016burial` / `cen2017submarine` / `sun2026magnetic` / `zhang2023sinsdvl` / `hatlo2015accurate`）：题录已定，仅 DOI 不在 Crossref 索引（属 CSTR/自有体系或无 DOI），下载 PDF 时用 CSTR/万方、原刊或会议论文集链接。
- **C 区 7 条 `@online` 待用户核对正式出版信息**：
  - `dlt1278_2025`（[37]/A5 DL/T 1278—2025）：待核对正式发布日期与出版社（拟中国电力出版社），及 0.05 nT/0.2 m 指标出处页码；
  - `tcsgpc_cable`（[38]）：待补完整标准号 `T/CSGPC ×××—××××` 与发布年；
  - `dnv2024cablefailure`（[39]）：待核对发布日期；
  - `nea2026shenlan` / `nea2025shenlan` / `scio2026offshore` / `geomatching2022sbp`：核对正式文件名与访问日期。
- Su 2025（`su2025precise`）Crossref 页码为 1–4，疑为摘要页，正式页码待核对。

## 6. 复核用命令（可选，均为公开接口，无需登录）
任一 DOI 重新拉取 BibTeX：
```
https://api.crossref.org/works/{DOI}/transform/application/x-bibtex   # 期刊/会议/图书
https://api.datacite.org/application/x-bibtex/{DOI}                    # arXiv 等 DataCite
```
