#!/usr/bin/env python3
"""Build a self-contained Markdown result record from audited held-out runs."""
import argparse
import hashlib
import json
from pathlib import Path

from plot_v2_robustness_matrix import LABELS


POSITIVE = ['clean_wire', 'clean_dipole', 'steady_plus', 'steady_minus', 'periodic_current',
            'navigation_noise', 'weak_neighbor', 'combined_bounded', 'unknown_shape']


def read(path):
    return json.loads(path.read_text())


def interval(items, key):
    values = [r[key] for r in items if r.get(key) is not None]
    if not values:
        return '未发布／无完整结果'
    lo, hi = min(values), max(values)
    return f'{lo:.3f}' if abs(hi-lo)<.0005 else f'{lo:.3f}–{hi:.3f}'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    a=p.parse_args(); root=a.root
    main_dir=root/'05_held_out'; main=read(main_dir/'summary.json'); plan=read(main_dir/'plan.json')
    audits={name:read(root/(name+'.json')) for name in ['audit_held_out_05','audit_ablation_06','audit_ablation_07']}
    assert all(v['evidence_integrity_passed'] for v in audits.values())
    assert plan['split']=='held_out' and plan['seeds']==[501,502,503]
    reference_free=read(root/'06_reference_free_ablation/summary.json')
    direction_only=read(root/'07_direction_only_ablation/summary.json')
    for d in ['06_reference_free_ablation','07_direction_only_ablation']:
        q=read(root/d/'plan.json')
        assert q['sources']==plan['sources'] and q['supervisor_contract']==plan['supervisor_contract']
    runs=[s for s in main if s['method']=='supervised']
    positives=[s for s in runs if s['case'] in POSITIVE]
    negatives=[s for s in runs if s['case'] not in POSITIVE]
    positives_passed=all(s['true_quality_passed'] and s['core_coverage'] and not s['false_geometry_publication'] for s in positives)
    negatives_passed=all(not s['completed'] and s['zero_withdrawal_tail'] and s['upstream_recovery_requested'] for s in negatives)
    anonymous_passed=all(not s['completed'] and not s['named_target_completed'] for s in reference_free)
    directional_passed=all(s['true_quality_passed'] for s in direction_only)
    accepted=[s for s in runs if s['true_quality_passed']]
    legacy=[s for s in main if s['method']=='legacy']
    closure=dict(positive_runs=len(positives),positive_completed=sum(s['true_quality_passed'] for s in positives),
        negative_runs=len(negatives),negative_rejected=sum(s['zero_withdrawal_tail'] and not s['completed'] for s in negatives),
        named_false_geometry=sum(s['false_geometry_publication'] for s in runs),
        false_completion=sum(s['false_completion'] for s in runs),
        anonymous_runs=len(reference_free),anonymous_named_completions=sum(s['named_target_completed'] for s in reference_free),
        direction_only_runs=len(direction_only),direction_only_completed=sum(s['true_quality_passed'] for s in direction_only),
        finite_grid_expectations_passed=positives_passed and negatives_passed and anonymous_passed and directional_passed,
        scope='declared finite toy assumptions only; external anchor and navigation error bounds are required',
        plan_sha256=hashlib.sha256((main_dir/'plan.json').read_bytes()).hexdigest())
    (root/'finite_grid_completion.json').write_text(json.dumps(closure,indent=2)+'\n')
    text=f'''# AUV 主动磁巡检：扰流、导航与多源条件性稳健性实验

2026-09-29。本报告记录冻结参数后种子 501–503 的独立留出；原理、过程地图、诊断和逐例证据在同一目录。研究目标是完成可解释的硕士巡检系统及受控 toy 验证，工业海况或实艇部署另行验收。

## 结论与适用范围

在本次有限网格中，监督候选的 9 类声明正例完成 **{closure['positive_completed']}/{closure['positive_runs']}** 次，11 类拒绝对照撤权 **{closure['negative_rejected']}/{closure['negative_runs']}** 次；指定目标错误几何授权 **{closure['named_false_geometry']}/{len(runs)}**，错误任务完成 **{closure['false_completion']}/{len(runs)}**。完整任务的全核心真实横偏 MAE 为 **{interval(accepted,'core_true_mae_m')} m**，最大横偏范围 **{interval(accepted,'core_true_max_m')} m**。拒绝属于保护行为，不计作巡检成功。原始 [120 次同版对照摘要](05_held_out/summary.json) 与 [独立 CSV 审计](audit_held_out_05.json) 可复算。

旧链在本组完成 {sum(s['completed'] for s in legacy)}/{len(legacy)} 次，但其中存在 {sum(s['false_geometry_publication'] for s in legacy)} 次错误几何授权。更高的到端数不能单独证明任务更可靠：载体误差合格和指定目标中心发布正确是两个指标。

新增候选显式使用外部受控直线参考 `y=6±0.05 m`、导航硬误差假设 `0.10 m` 与磁中心预算 `0.10 m`。这些是额外条件；磁感知不自行证明目标身份或导航精度。未知埋深始终为空。本结果不证明任意多源识别、任意曲线海缆、三维铠装电磁场、完整 ROS 实时任务或真实停止距离。

## 方法与证据职责

仿真先验路线长 80 m，真实直线目标相对先验横偏 6 m，评价核心为 `[5,75] m`。浅角扫描从 `(-250,-15)` 至 `(-80,15) m`，航速 0.3 m/s；决策步长 0.25 s，原生动力学每步积分 5×0.05 s。磁包络峰值 20 nT、背景 1 nT、空间尺度 3 m，加标准差 0.03 nT 的独立高斯噪声。单源指数为直导线 0.5、偶极 1.0，未知对称包络为 0.7；邻源强度、间距和相位见冻结计划。本组位置误差界仅指水平 XY，固定垂向参考及标量包络不验证高度／姿态磁耦合。相干多源使用相量和再取模，不是完整三维电磁场。

`先验引导搜索 → 磁检测 → 主动横切 → 显式 FWHM／横向中心 → 有限跟踪` 仍是原来的磁算法。独立 opt-in 层只增加观测一致性、授权和简单接入修正，接口类型保持兼容，默认生产入口和旧数据不变。

| 增量 | 输入与动作 | 能说明什么 | 不能说明什么 |
| --- | --- | --- | --- |
| 条件式接入 | 测得偏移符号与世界地速减航向速度的代理；反向超过 0.02 m/s 选 5 m，其余 20 m | 改善声明方向的小流接入几何 | 代理含侧滑，不是直接流速测量；不是复杂最优规划 |
| 导航一致性 | 位移增量与独立世界系地速积分；20 s 有限窗 | 检查跳变和累积不一致 | 不消除固定共同偏差，不以协方差自证准确 |
| 指定目标授权 | 磁中心与独立外部区间一致性 | 拒绝不能关联到指定目标的几何 | 不从峰形识别相邻电缆数量或身份 |
| 扫描—跟踪一致性 | 冻结完整实测横切剖面，16 样本磁幅残差窗 | 识别观测变化并撤权 | 超出实测支撑区不外推；动态幅值变化可能要求重扫 |
| 有限质量预算 | 核心真实偏差条件上界与终点质量门 | 条件成立时约束发布与完成 | 不证明导航误差假设真实成立 |
| 撤权与恢复请求 | 锁存零目标速度／协议 RPM，30 s 请求上级恢复，记录 60 s | 观测软件保护与继续运动分开 | 未实现上级实际恢复，不保证悬停 |

条件上界为 `|真实载体−真实缆| ≤ |报告位置−参考中心| + 导航误差界 + 参考半宽`。只有导航和参考误差界实际成立时才有此保证；独立评价另外记录误差界实际是否成立。隐蔽偏差、跳变和漂移对照有意违约，不能以其声明协方差当成实测精度。

本组保留旧的 6 m 偏差先验，以观察搜索、横切及新增监督的行为。若高精度参考从一开始就可用于规划，理应进一步修正先验、缩短搜索；本文不声称比充分利用该参考的规划更高效。两方法对照含额外信息和条件式接入，不能作为等信息条件下的磁反演精度排名；无参考与只改接入消融专门区分这些贡献。

## 完整任务与故障过程

![图72：完整任务和局部撤权地图](figures/72_defense_robustness_process_maps.png)

图 72 从实际 CSV 展示搜索、横切、接入、核心跟踪与撤权后运动。融合邻源拒绝轨迹没有被画成零偏差完整任务。横纵轴比例不同。[矢量 PDF](figures/72_defense_robustness_process_maps.pdf)。

![图73：导航故障及零命令后运动](figures/73_defense_navigation_withdrawal_diagnostics.png)

图 73 把真实横偏、位置增量残差、编码主推和撤权后位移对应起来。导航跳变在注入同一仿真周期撤权，实际已在路段运行的车辆仍有惯性位移；不能说零命令等于艇停。[矢量 PDF](figures/73_defense_navigation_withdrawal_diagnostics.pdf)。

![图74：几何中心与载体误差的区别](figures/74_defense_geometry_vs_tracking_insight.png)

图 74 是答辩关键反例：一个可见融合峰可能给出偏移中心，而载体全核心 MAE 仍满足门限。监督组用独立参考拒绝关联，未发布中心以“未授权”表示，不能记作零误差。[矢量 PDF](figures/74_defense_geometry_vs_tracking_insight.pdf)。

![图75：有限留出网格](figures/75_defense_robustness_outcome_matrix.png)

图 75 每格是一条闭环，区分合格完成、撤权、错误几何授权、错误任务完成与超时。种子重复不是海况概率估计；参数网格也不是连续鲁棒性证明。[矢量 PDF](figures/75_defense_robustness_outcome_matrix.pdf)。

![图76：扰流过程、条件上界与撤权](figures/76_defense_current_process_and_limits.png)

图 76 展示反向小流的接入修正、周期流的真实横偏与条件上界，以及阶跃流响应和撤权后的持续位移。上界只画撤权前有合同支持的样本，撤权后继续记录真实运动。[矢量 PDF](figures/76_defense_current_process_and_limits.pdf)。

![图77：论文紧凑摘要](figures/77_defense_robustness_thesis_summary.png)

图 77 用两个紧凑面板供论文与主讲插图：反向小流按真实沿缆位置评价，旧链未覆盖区域明确标灰；融合邻源各误差按对应阈值归一化，说明路线指标通过时目标中心仍可能错误。[矢量 PDF](figures/77_defense_robustness_thesis_summary.pdf)。

## 逐条件结果（全部核心 Track，含回归）

完成数按目标任务统计；几何错误单列。误差范围仅列完整合格任务，拒绝样本的截短 MAE 保留在原始摘要，不用于与完整任务比较。

| 条件 | 旧链完成／3 | 旧链错误几何／3 | 监督完成／3 | 监督拒绝／3 | 监督完整任务 MAE / m | 监督完整任务最大横偏 / m |
| --- | ---: | ---: | ---: | ---: | --- | --- |
'''
    for case in [c['name'] for c in plan['cases']]:
        b=[s for s in legacy if s['case']==case]; q=[s for s in runs if s['case']==case]; ok=[s for s in q if s['true_quality_passed']]
        text+=f"| {LABELS[case]} | {sum(s['completed'] for s in b)} | {sum(s['false_geometry_publication'] for s in b)} | {sum(s['completed'] for s in q)} | {sum(s['withdrawal_time_s'] is not None for s in q)} | {interval(ok,'core_true_mae_m')} | {interval(ok,'core_true_max_m')} |\n"
    text+=f'''
## 消融与不利结果

关闭外部参考的 9 次消融：[原始摘要](06_reference_free_ablation/summary.json)、[独立审计](audit_ablation_06.json)。几何路线结束 {sum(s['geometric_route_completed'] for s in reference_free)}/9 次，指定目标完成 **{sum(s['named_target_completed'] for s in reference_free)}/9**。融合邻源仍可被沿异常跟随；降低身份声明是语义边界，不是磁观测已经解决多源歧义。

只改接入、不加监督的反向小流 3 次：[原始摘要](07_direction_only_ablation/summary.json)、[独立审计](audit_ablation_07.json)，完整合格任务 {sum(s['true_quality_passed'] for s in direction_only)}/3 次。这将运动几何收益与目标参考的拒绝收益分开，不能把全部改善归因于 FWHM 精度。

反向阶跃仍未完成；超界流、反相邻源与无源仍拒绝。未知对称包络的横向中心可支持本组有限任务，但不能授权埋深。单源幅值改变后撤权属于保守的观测更新要求，旧链继续完成并非在所有任务定义下都错误。

## 答辩风险与后续成本

| 边界 | 对答辩的影响 | 本轮处理 | 剩余工作及成本 |
| --- | --- | --- | --- |
| 独立参考额外提供信息 | 若省略会变成“磁算法自行识别错缆” | 主图／文案明示参考，附无参考消融 | toy 场地独立测量目标与导航误差；低至中 |
| 隐蔽共同偏差或相关故障 | 增量诊断可能一致却都错 | 条件上界只在实际误差界内使用 | 外部导航校核；本轮不承诺任意相关失效的识别 |
| 多源和场形不可辨识 | 峰形高置信不保证身份／埋深 | 拒绝目标关联与深度分别授权 | 已知几何受控横切标定；中；完整三维场高 |
| 反向阶跃／低速转向 | “抗流”容易被误讲成全向全时成功 | 同版失败、延迟与运动尾段展示 | 上级有限恢复、走廊与制动包络；中 |
| 曲率与远距离观测陈旧 | 固定一次横切不能无限跟踪 | 直线 80 m／70 m 核心条件 | 现有多横切作为历史扩展，曲线另验证；中 |
| ROS 实时链与实艇 | 离线加速闭环不能替代部署 | 混合 PID／编码／PVS 范围单列 | 目标平台验收，暂不计本轮完成；高 |

本轮创新表述宜聚焦“主动形成空间观测、显式质量与输出分离、可解释失效诊断、条件式接入”，不把简单监督规则包装成通用识别算法。主讲可用图 72 或 76；图 73／74／75 用于回答稳定性、错缆与适用范围问题。

## 后续受控 toy 试验的最小条件

先使用一根已知直线磁源与独立测量的轨迹、统一坐标和误差记录，再加入邻源、幅值变化及软件导航故障。外部参考与导航硬误差界须由独立测量支持，不能只复制本仿真的 0.05／0.10 m 数字；缩比后应重新做量纲一致的几何与幅值标定。完整双侧剖面、位置时间戳、磁采样、参考真值与拒绝原因一起保存。

导航增量诊断要求有独立地速来源，例如可核查的 DVL 或试验架速度测量。若地速只是同一位置差分，不能把两者一致当作独立导航正确性证据。只有 ArUco／手持剖面时可验证磁中心与拒绝，不应宣称水下完整导航或扰流通过。相位多源的实测场应按记录说明，不能将本组相量和模型直接当成真实三维场。

试验分别验收磁异常、指定目标横向几何、已标定深度与执行许可；无埋深标定仍保存空值。软件故障注入应注明“合成输入”，物理零推进与停止距离另测。这些是后续 toy 的可执行边界，不计为本轮已经完成的实物试验。

## 复现与版本

- 主对照：[执行前冻结计划](05_held_out/plan.json)、[完成后证据哈希](05_held_out/manifest.json)、[127 文件源码快照索引](05_held_out/source_snapshot_index.json)。
- [105 项 v2 测试日志](verification/v2_tests_105.log)与[验证记录](verification/tests.json)保留本版定向和整包检查。
- [结果完成前的评价规则](HELD_OUT_EVALUATION_RULES.md)、[有限网格完成检查](finite_grid_completion.json)。完成检查只覆盖本文声明的条件。
- 开发种子 401 与留出 501–503 分开；第一轮错误参考剖面的开发失败保留，第二／三／四轮不同版本不混算。本报告仅统计本次冻结留出。
- 本组导航位置噪声逐轴截断为 ±2σ；航向偏差同时进入导航与 PVS 局部回路。多源是相干标量包络相量和，含同相／反相／正交相位，不是完整三维铠装模型。
- 各方法共用初始化、随机流和触发规则；动作不同后的闭环观测自然不同。进程并行只缩短采样时间，运行墙钟不作为实时性指标。
- 字体复用 `tools/thesis_plot_style.py` 的 FandolSong／STIX；600 dpi PNG 与嵌入字体 PDF 成对，源码与图像哈希见各图 manifest。

从仓库根目录，使用新的输出目录执行：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /usr/bin/python3 tools/run_v2_defense_robustness.py \\
  --seeds 501 502 503 --split held_out --workers 3 --output-dir <新目录>
/usr/bin/python3 tools/audit_v2_defense_robustness.py --run-dir <新目录> --output <新审计.json>
/usr/bin/python3 tools/plot_v2_defense_robustness.py --run-dir <新目录> --seed 501 --output-dir <新图目录>
/usr/bin/python3 tools/plot_v2_robustness_matrix.py --run-dir <新目录> --seed 501 --output-dir <新图目录>
```

主要监督／接入参数、模型与输入扰动在运行前 `plan.json` 保存；底层 v2 构造配置、PID 和协议细节同时冻结源码及 `params.yaml`。重现应检查依赖版本与源码快照，不能仅依赖未提交工作树的 Git HEAD。源码快照用于审阅与恢复版本，实际运行仍需仓库布局和安装的数值／PVS 依赖。
'''
    (root/'README.md').write_text(text)
    print(json.dumps(closure))


if __name__=='__main__':
    main()
