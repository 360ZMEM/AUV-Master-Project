# 2026-10-22 共享参考文献续核

主论文与两份中期报告继续使用同一个 [Bib 文件](../../../../thuthesis/ref/auv-references.bib)，99 条及全部 citekey 保持不变。当前必要字段通过 78/99，待复核 21 条，比 10 月 18 日减少 2 条。工具及编译验收通过，终稿真实性放行仍为 false。

本次在 10 月 18 日完整证据缓存上增加定向官方核验，并重算全部 333 条底账。继承证据保留原查询时间，并未声称所有站点在 10 月 22 日重新访问。旧报告、旧缓存和原 Bib 均保留；当前构建前的三份 PDF 另存于 [before](before/)。不改章节正文、算法、实验或专利材料。

## 新核验结果

| 条目 | 结果与边界 | 外部证据 |
|---|---|---|
| `purcell2000remus` | 出版年 2000 已核实，必要字段通过。WHOI 作者履历中的完整题录支持年份；履历与出版社的作者次序有差异，本轮不据履历覆盖作者顺序。 | [WHOI 作者履历](https://www.whoi.edu/cms/files/vitas/2006/4/currvit_9586.pdf) |
| `breivik2005guidance` | 出版年 2005 已核实，必要字段通过。依据论文首页会议出版信息；直接请求 TLS 失败保留，成功的浏览工具读取单独存档。 | [NTNU 保存的会议原稿](https://skoge.folk.ntnu.no/prost/proceedings/cdc-ecc05/pdffiles/papers/2657.pdf)、[读取快照](../web_snapshots/breivik2005guidance_20261022.json) |
| `scio2025energyachievement` | 在国家能源局找到同次国新办发布会完整实录，身份、在线资源类型及 2025 年已确认。原短题名与完整题名形成审阅差异；机构责任者仍未由署名唯一确认，未改 Bib。 | [官方实录](https://www.nea.gov.cn/20250826/81a62ca2aedb4f18ac107efd85c4b650/c.html) |
| `nowrdc2024diveld` | 官方页面结构化 `datePublished` 为 2023-04-04；2024 是页面另列的项目完成年份。年字段改列 MISMATCH，建议 2023；先确认引用的是项目网页还是最终报告，保持仅供审阅。责任者仍待核。 | [NOWRDC 项目页](https://nationaloffshorewind.org/projects/fully-autonomous-subsea-asset-inspection-by-a-shore-launched-auv/) |

所有机器采用的断言均重新经过原始响应片段检查。新增网页、PDF、访问失败和继承缓存可在 [证据索引](followup_evidence.json) 与 [evidence](evidence/) 按 URL、查询时间和 SHA-256 追溯。

## 进一步缩小人工选择范围

以下两项补探已有实质结果，仍涉及文献版本选择，不自动替换原记录。

- `orecatapult2025ras`：找到官方完整报告，扉页明确列作者 Paul Hatchett、Andrew Esson、Charlotte Holt，时间为 July 2025。原 Bib 是发布网页题名与机构责任者，报告本体题名还有单复数差异。若决定引用报告本体，可据 [官方 PDF 的第 2 个 PDF 页面](https://cms.ore.catapult.org.uk/wp-content/uploads/2025/07/Catapult-Foresighting-RAS-Report-Feb-25-v8-SPREADS.pdf) 整体重著录；不能只把赞助方当作报告作者。当前 author 的 UNVERIFIABLE 状态保留，并非该报告作者也无法找到。
- `gwec2025offshore`：原下载路由 [globaloffshorewindreport](https://www.gwec.net/reports/globaloffshorewindreport) 当前已指向 2026 版，不能用它证明 2025 版。原条目 URL 实为 2025 年发布新闻，仍需选择新闻或 2025 年报告本体；未用新版数据替代旧版。

优先打开 [21 条必要字段清单](manual_review.md) 和 [11 项字段建议](review_fields.diff)。页码、卷期等仍放在 [次要复核](secondary_review.md)，不要求逐条人工解决后才可继续写作。原 `barshalom2001estimation` 纸本／电子年冲突、团体标准征求意见稿身份和其他责任者／年份问题继续保留。

## 工具、构建与验收

本轮给证据断言增加 `review_only_fields`：有明确出版日期但存在所引资源或版本选择疑义时，字段可报告 MISMATCH 并附建议值，同时禁止进入安全修正候选。新增回归测试从外部片段加载、字段判定一直检查到补丁生成，确认疑义不会在后续自动应用中丢失。

| 验收项 | 当前结果 |
|---|---|
| 全部库覆盖 | 13 库、333 条，研究库 99 条 |
| 研究文献身份确认 | 95/99，原为 94/99 |
| 研究必要字段通过 | 78/99，原为 76/99 |
| VERIFIED 字段证据完整性 | 886/886；其中研究库 668 |
| 自动修正候选／仅供审阅候选 | 0／11；未应用任何 Bib 修改 |
| 自动测试 | 29/29 |
| 主论文构建 | 180 页；BCF 90 键 = BBL 90 条 |
| main 中期构建 | 36 页；BCF 12 键 = BBL 12 条 |
| school 中期构建 | 36 页；BCF 12 键 = BBL 12 条 |
| 引用、Biber 与证据完整性 | 通过，无未定义引用；三份实际 BCF 数据源一致 |
| GB/T 7714-2015 | 三份使用同一格式引擎并抽取实际文献表；必要元数据未全量放行 |
| 严格终稿门禁 | 预期拒止，必要字段仍有 21 条待复核 |

当前页数反映本轮构建时工作区已有正文；不是 10 月 18 日的 170／34 页历史快照，也不是本轮增加正文。实际 PDF 哈希和引用键见 [acceptance.json](acceptance.json)，构建前 PDF 与哈希在 [before](before/)。

日志：[审计](audit.log)、[测试](tests.log)、[三份构建](compile.log)、[机器验收](acceptance.log)、[严格门禁](release_check.log)。离线重复结果见 [replay_check.json](replay_check.json)。实际输出参考文献表保存在 [compiled](compiled/)。

## 重复执行

根目录默认审计与验收输出已转到本目录。重放该轮冻结断言：

```bash
"$HOME/.local/share/auv-bib-audit/venv/bin/python" tools/bib_audit.py \
  --offline --output docs/thesis/bibliography/20261022 \
  --supplement docs/thesis/bibliography/20261022/official_evidence.json
make test-bib-audit
make auv-thesis auv-middle-defense-main auv-middle-defense-school
make bib-audit-acceptance
make bib-audit-check
```

最后一个命令在当前状态必须返回非零。若要重新访问网络，请另建新日期输出目录，勿覆盖旧失败缓存。运行输入及工具哈希见 [inputs.sha256](inputs.sha256)；本轮固定断言为 [official_evidence.json](official_evidence.json)。文献正文是否支持论文论断（L3）未在本次验证范围内。
