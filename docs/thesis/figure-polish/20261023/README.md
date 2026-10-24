# 论文图像尺寸、分页与正文润色（2026-10-23）

**本轮调整完成；11 幅遗失输入的旧图按用户决定保留。** 不把旧图的已知遮挡、字体问题或未验证的重绘能力记为通过。前一轮严格/润色报告仍保留历史含义。

当前论文 **180 页**；48 图组、53 个资产、54 次插入、47 个含图物理页。34 页原生图 fresh 真实文字/形状检查无布局、映射或语义错误；17 项原生、10 项 Matplotlib 与 3 项实际 PDF 边界检查通过，33 文件再生成零变化。

## 尺寸与字窗的实际变化

第 1 章图片和图源维持；原生图保留全部文字、ID、连线及可编辑性。2.3/2.4 的纸面盒子和字号缩小约 20%，通过源线宽补偿或同倍率几何压缩保持纸面边框厚度；3.1 的纵向布局收紧 15%，字号保留。4.2 仅收紧下部任务泳道，上部菱形保留所需安全区，未强压至溢出。

| 图 | 宽 × 高：前 → 后（mm） | 最小标签基准：前 → 后（PDF pt） | 论文页对照 |
|---|---|---|---|
| 2.3（1） | 156.0 × 53.2 → 124.8 × 42.5 | 10.45 → 8.36 | [前](evidence/paper/2.3_0_before.png) / [后](evidence/paper/2.3_0_after.png) |
| 2.3（2） | 156.0 × 96.0 → 124.8 × 76.8 | 9.43 → 7.54 | [前](evidence/paper/2.3_1_before.png) / [后](evidence/paper/2.3_1_after.png) |
| 2.4 | 147.0 × 172.9 → 117.6 × 138.2 | 10.79 → 8.62 | [前](evidence/paper/2.4_0_before.png) / [后](evidence/paper/2.4_0_after.png) |
| 2.7 | 144.0 × 124.2 → 144.0 × 124.2 | 4.67 → 7.09 | [前](evidence/paper/2.7_0_before.png) / [后](evidence/paper/2.7_0_after.png) |
| 3.1 | 142.5 × 125.0 → 142.5 × 106.3 | 6.73 → 6.73 | [前](evidence/paper/3.1_0_before.png) / [后](evidence/paper/3.1_0_after.png) |
| 4.2 | 147.0 × 168.9 → 147.0 × 154.8 | 5.87 → 5.87 | [前](evidence/paper/4.2_0_before.png) / [后](evidence/paper/4.2_0_after.png) |
| 4.5 | 132.0 × 94.1 → 108.0 × 77.0 | 9.88 → 8.08 | [前](evidence/paper/4.5_0_before.png) / [后](evidence/paper/4.5_0_after.png) |
| 5.4 | 114.0 × 103.5 → 75.0 × 68.1 | 12.23 → 8.05 | [前](evidence/paper/5.4_0_before.png) / [后](evidence/paper/5.4_0_after.png) |
| 5.17 | 144.0 × 116.5 → 144.0 × 123.0 | 4.84 → 6.83 | [前](evidence/paper/5.17_0_before.png) / [后](evidence/paper/5.17_0_after.png) |

字号为真实 PDF 字形子集或 Agg 标签基准，经实际插入矩阵换算；公式下标和 Type3 中文抽字不完整，不能仅据此断言全部字形同字号。图 2.7(a) 的投影放大约 18%；图 5.17 的图例移出轨迹区并统一文字尺寸，两图所有绘制曲线数组与原输入哈希相同。

## 分页与文字

将应急、生命周期、行为树和参考生命周期图与相邻解释段落共同组织；保留必要的密集图尺寸。逐页筛查结果在 [acceptance.json](acceptance.json) 的 `float_sweep`，筛选依赖实际看图，不以导出成功代替复核。第 1 章技术路线图遵照用户要求维持。

正文将 46 处类名、消息路径、状态字段和工具名替换为功能或物理含义，另修正 21 处中文间空格；[逐项旧新映射](prose_edits.json) 保留复现标识。数学变量、协议帧和必要硬件字段保留；[可见实现标识检查](prose_audit.json) 无未解释项。同期第 1、2 章文献/标准修订另存外部差分，未回退，也不冒充本轮研究变更。

## 遗失输入图像：现状采样与保留

下列原 PDF/PNG 未侵入修改；样本从现有 PDF 实际渲染并逐一打开。旧字体、图例遮挡及原输入重绘不可验证的限制继续保留。

| 资产 | 现状预览 |
|---|---|
| `r13_v2_authority_modes_ua` | [原样采样](retained_samples/r13_v2_authority_modes_ua.png) |
| `05_mpc_combined_summary` | [原样采样](retained_samples/05_mpc_combined_summary.png) |
| `03_complexity_comparison` | [原样采样](retained_samples/03_complexity_comparison.png) |
| `ch4_enob_vs_osr` | [原样采样](retained_samples/ch4_enob_vs_osr.png) |
| `ch4_noise_spectral_density` | [原样采样](retained_samples/ch4_noise_spectral_density.png) |
| `pc104_cross_layer_fault_timeline` | [原样采样](retained_samples/pc104_cross_layer_fault_timeline.png) |
| `pc104_cross_layer_soak_30min` | [原样采样](retained_samples/pc104_cross_layer_soak_30min.png) |
| `pc104_fault_timeline` | [原样采样](retained_samples/pc104_fault_timeline.png) |
| `pc104_firmware_echo_timing` | [原样采样](retained_samples/pc104_firmware_echo_timing.png) |
| `terrain_3d_pid_terrain_trajectory` | [原样采样](retained_samples/terrain_3d_pid_terrain_trajectory.png) |
| `terrain_tz_tracking_pid_mpc` | [原样采样](retained_samples/terrain_tz_tracking_pid_mpc.png) |

完整路径、原图/预览 SHA-256 与已知限制见 [保留清单](retained_images.json)。

## 复现、证据与回滚

```sh
python3 tools/figure-polish/compact_20261023.py run
python3 tools/figure-polish/compact_20261023.py verify
python3 tools/figure-polish/compact_20261023.py prose_audit
```

`run` 仅由真实生成器重放排版/既有输入绘图，再编译论文；候选看图哈希不符或正式文件出现外部修改时拒绝覆盖。`verify` 只读检查图源、正式资产、输入与现有 PDF，重新渲染和测量；新图没有实际看图记录时不能通过最终报告。`prose_audit` 可在后续修订中重复运行，不自动删除变量或改写结论。

本轮 318 份工作树原件及其哈希在 `.diagram-governance/runs/20261023_compact_thesis/backup/` 与 `baseline_manifest.json`；只读复检保护 327 文件且零变化。前一轮备份完整保留。生成器、候选失败迭代、输入/曲线不变性、57 个 PDF 字体检查和命令日志也在该运行目录。

[逐页实际看图/同图继承记录](final_visual_review.json) · [候选看图](candidate_visual_review.json) · [逐项验收](acceptance.json)

本轮不运行新的巡检仿真或逆解，不更改算法、实验数值和现场许可；图像与写作润色完成度不等同于研究或实艇验收完成度。
