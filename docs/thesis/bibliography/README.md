# 参考文献真实性审计

仓库发布历史审计摘要、差异表与索引；20261018/20261022 的完整 `evidence/` 网页响应和 `before/` 编译前快照属于本机缓存，已按工作区分流规则排除。离线重放命令需要这些本地缓存；新克隆应先重新采集到新日期目录，不能声称仅凭 Git 内的摘要完成同一原始响应重放。20261023 的最终工程验收及抽查截图随仓库发布。

主论文与两个中期报告共用唯一的研究文献源：[auv-references.bib](../../../thuthesis/ref/auv-references.bib)，现为 **98 条**。2026-10-23 按作者已完成人工核对的 [权威 Bib 输入](../../../auv-references-final-20261023.bib)原样覆盖；同步正式标准、SBP 论述及必要的手册/项目报告适用边界。更改前后正文、引用键检查与三份文档编译结果见 [Bib—正文工程收口记录](20261023/README.md)。

历史机器审计：[2026-10-22 续核记录](20261022/README.md)、[全量报告](20261022/audit_summary.md)、[验收记录](20261022/acceptance.json)、[必要字段复核](20261022/manual_review.md)、[次要字段/页码](20261022/secondary_review.md)。当时 99 条库的状态在 [JSON](20261022/audit_results.json) 和 [CSV](20261022/field_differences.csv) 中，必要字段通过 78/99，21 条待复核；这些数字不代表已经换入的 98 条库。原 [2026-10-18 完整交付](20261018/DELIVERY.md) 与原始证据保留。本次依作者确认与执行指令做本地工程收口，不联网、不重跑旧审计，也不将作者确认改写为旧工具的字段级 VERIFIED。

审计完成与文献真实性全部放行是两件事。`audit_acceptance_passed` 检查覆盖、证据完整性、编译和实际引用；`release_ready` 要求研究文献所有必要字段解决。后者为 false 时，终稿不得宣称参考文献全量核验通过。模板示例/上游测试数据单独列账，不要求作者修订上游示例来释放自己的论文。

## 安装与复跑

在仓库根目录执行：

本机仓库位于不支持 venv 所需软链接的 VirtualBox 共享文件系统，依赖环境放在用户目录的原生文件系统中；不会安装到 ROS 或系统 Python。

```bash
python3 -m venv "$HOME/.local/share/auv-bib-audit/venv"
"$HOME/.local/share/auv-bib-audit/venv/bin/pip" install -r tools/requirements-bib-audit.txt
make test-bib-audit
make bib-audit-offline
make bib-audit-acceptance
make bib-audit-check
```

最后一个命令是严格的终稿门禁；必要字段仍有例外时返回非零，这是预期拒止，不是工具故障。`bib-audit-offline` 仅重放现有证据，不联网；首次联网收集运行 `make bib-audit`。使用其他环境可传 `BIB_AUDIT_PYTHON=/path/to/python`。

重新采集最新网络状态时，使用新目录，保留旧证据：

```bash
"$HOME/.local/share/auv-bib-audit/venv/bin/python" tools/bib_audit.py --output docs/thesis/bibliography/YYYYMMDD
```

不在同一目录悄悄覆盖历史失败缓存；404/403/超时同样是需要保留的访问记录。此类结果只能表示本次访问失败，不能据此宣布文献不存在。`--workers` 默认 4，全局请求起点间隔至少 0.55 s，网络失败最多重试两次，尊重有上限的 Retry-After。IEEE API、OpenAlex 等需要权限时只记 ACCESS_BLOCKED，不借用没有权限的数据。

## 范围与证据

工具递归发现 `thuthesis/**/*.bib`，用 Pybtex 解析宏、嵌套大括号和作者，并保留原条目身份及文件哈希。2026-10-18 共发现 13 个库、333 条：研究库 99 条、工作模板与测试库 117 条、锁版本 vendor 副本 117 条。压缩归档不是活动输入，不打开或改写；`docs/.../before/` 中备份亦不进入 thuthesis 扫描。

静态扫描所有非归档 LaTeX 源码中的 cite/nocite、多引用命令、可选参数与 input/include 图，忽略注释和 verbatim/lstlisting/minted。它不执行任意 TeX 宏，故保留条件分支并集；动态键、无法解析的引用均显式列出。编译后 BCF 给出真实执行的引用，BBL 必须与之逐键一致。中期格式 smoke 分支多出的 `hewing2020learning` 属潜在引用，不能算正式报告正文漏引。

证据优先级为正式出版社/发布机构的指定记录、出版社提交的 Crossref/DataCite 元数据、其他索引。标题近似搜索只产生候选；真实 DOI 不能单独证明其绑定题录正确。同题预印本与正式会议稿通过 DOI/版本锚定分开，绝不自动换文献。作者核对保持顺序和完整性，兼容缩写及明确的字符转写，不用相似度分数直接放行。

`official_evidence.json` 记录需要专属读取的官方页面、原始证据片段及有限裁决理由。所有断言须从缓存外部响应中重新找出；片段不存在或字段值不受片段支持，就不能 VERIFIED。部分站点直接 HTTP 被阻断、浏览工具可访问时，将工具原始返回及时间保存在 `web_snapshots/`，再由工具导入，保留直接访问失败与替代证据两条记录。网页 footer 年份、URL 中年份、项目完成日期，不自动当成出版年。人工裁决过的片段配置仍需要审阅，不等于 API 自动发现，也不构成第二个独立数据源。

Crossref 与 OpenAlex 的相同记录不作为独立投票；来源族、原始值和 URL 均保留。出版社可明确裁决其正式题录与索引简称，但纸本/电子版年份冲突不能靠多数投票消除。

## 字段、修正与 GB/T 7714-2015

每条文献检查类型、DOI、题名、作者、年、刊物/会议/书名、出版社、卷、期、页码、文章编号。字段状态严格区分 VERIFIED、MISMATCH、UNVERIFIABLE、ACCESS_BLOCKED、SOURCE_CONFLICT、NOT_APPLICABLE。VERIFIED 必须附证据 ID、URL、查询时间、原始响应 SHA-256、来源族与外部字段值。缺失的可选出版社不强制添加；不适用/省略的字段明确说明原因。

必要字段为身份、类型、题名、责任者及适用出版年；论文/会议要求刊物，专著要求出版社。无标注日期的 online/manual 且原库未声称年份时，不因缺年份强制人工审核；已声称年份但无法核实的条目仍需审查。页码、卷期、文章编号和 DOI 异常集中在次要清单，不能把仅页码问题升级为必要人工审核。

页码仅接受正式出版页码或登记的明确页码区间；绝不用 PDF 页数推算。Crossref 仅给单个数字 `page` 时，其语义先记 UNVERIFIABLE。只有明确 `article-number` / 论文编号才能移入 `eid`；没有语义证据的数字页码按作者授权省略，原值和响应保留。Early Access 无正式页码就不补。

只读审计默认生成 `safe_corrections.patch`、`safe_changes.json`、`review_changes.json`、`review_fields.diff`，不写原库。`review_fields.diff` 是逐字段审阅视图，不是可直接套用的 BibTeX 补丁。安全修正可在审阅候选后通过 `--apply-safe` 应用，修改前保留完整原文件；争议修改不应用。唯一身份且官方完整字段一致的 DOI 拼写错误、明确的正式标准类型、已核实定位符可安全修正；版本替换、作者/题名争议保留。官方断言可用 `review_only_fields` 指定有资源或版本疑义的字段；即使发现明确外部值，也只生成审阅差异，不进入安全修正。

项目内部检索、技术解释和“待核对”说明原来写在 `note` 中，会被打印到参考文献表；安全修正将其移为 `audit-note` 源码注释，保留原文但不作为出版字段输出。中文/外文 citekey 保持不变。

主论文和两份报告已经加载 `biblatex` 的 `style=gb7714-2015`。实际核对 BCF/BBL、Biber 警告、PDF 文献页及类型标识；标准电子载体的 `[S/OL]` 是标准允许的标识。格式引擎通过不代表资料齐全：团体标准征求意见稿、疑似误署责任者、无法证实的出版年份仍需按异常清单处理。本轮不自动把征求意见稿说成已发布标准，也不猜造标准号、出版地或发布日期。

修正后重新执行：

```bash
make auv-thesis auv-middle-defense-main auv-middle-defense-school
make bib-audit-offline
make bib-audit-acceptance
```

当前 Bib—正文同步和 PDF 检查见 [2026-10-23 工程收口](20261023/README.md)；历史机器审计见 [2026-10-22 续核记录](20261022/README.md)，首次安全修改见 [2026-10-18 交付记录](20261018/DELIVERY.md)。历史审计处理 L1 文献身份、L2 书目字段；本次工程收口不代表整个学位论文的 L3 逐句文献真实性审查已经完成。需要重新审计时应显式指定新的输出目录，保留上述历史证据。
