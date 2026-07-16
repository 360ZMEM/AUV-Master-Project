# 数据来源

- 源 run: `results/decision/bt_vs_fsm/20260608_173806`
- 同步时间: 2026-06-20 15:04:15
- 来源根: `/auv_data`（不随仓库同步，仅本地存在）

## 论文压缩降级记录（2026-08-18，批次 C 图去重）

- `06_hysteresis_debounce_chattering.png`（原 `fig:ch04-bt-fsm-chattering`）：**从正文降级归档，图片文件保留在本组不删**。理由：该图呈现的“单阈值 149.09 次 → 迟滞去抖 2.23 次、降幅约 98.5%”已在 §4.2 正文以数值完整给出，图与正文数值重复。正文仅保留复杂度对比（`03_complexity_comparison.png`）与扩展开销（`04_expansion_cost.png`）两图，反应时延/生存率/去抖降幅的等价性以数值表述。
- 同批：ch04 应急仲裁图 `fig:ch04-emergency-arbitration`（原引用 `architecture/auv_v2_emergency_transition.pdf`）与 ch02 `fig:ch02-emergency-arbitration` 为同一图同一 alt，ch04 处删除重复插图、改交叉引用第 2 章图，图片资产仍由 ch02 引用，未删。
