#!/usr/bin/env python3
"""Replace one historical figure with audited compact robustness evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from write_v2_robustness_report import interval

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True)
    a=p.parse_args(); closure=json.loads((a.results/'finite_grid_completion.json').read_text())
    assert closure['finite_grid_expectations_passed'], 'do not integrate an unverified positive conclusion'
    runs=json.loads((a.results/'05_held_out/summary.json').read_text())
    q=[s for s in runs if s['method']=='supervised']; ok=[s for s in q if s['true_quality_passed']]
    legacy=[s for s in runs if s['method']=='legacy']
    mae=interval(ok,'core_true_mae_m'); mx=interval(ok,'core_true_max_m')
    p5=ROOT/'thuthesis/data/auv-chap05.tex'; p6=ROOT/'thuthesis/data/auv-chap06.tex'
    text=p5.read_text(); old6=p6.read_text()
    backup=ROOT/'thuthesis/backups/20260929_before_robustness_169p'
    for path in [p5,p6]:
        assert path.read_bytes()==(backup/'data'/path.name).read_bytes(), 'thesis changed after backup: review before integrating'
    start=text.index('\\subsection{ROS 链路、横流边界与多横切扩展}')
    stop=text.index('较宽先验采用连续余弦浅角多横切',start)
    new=rf'''\subsection{{扰流、导航与多源的条件性监督}}\label{{sec:ch05-inspection-ros-boundary}}\label{{sec:ch05-inspection-robustness}}

在上述限定条件基线上，增加独立观测监督与条件式接入，保持磁反演和控制接口不变。世界系地速与报告位移的增量／有限窗一致性用于诊断跳变和漂移；接受的完整横切剖面冻结为磁幅参考，观测变化则撤权。接入仅在测得反向横向扰动代理超过 0.02 m/s 时由 20 m 缩短为 5 m，其余保留原配方；该代理包含侧滑，不能视为直接流速测量。目标授权另用受控外部区间 $y=6\pm0.05$ m，假设导航硬误差不超过 0.10 m，并对全核心横偏应用三角不等式上界。外部参考是额外信息，不能当作磁算法独立识别目标或实测导航精度的证据；无参考时只记录磁异常路线，通用目标完成标志保持假。

冻结参数后，20 条件、三个留出种子与两方法形成 120 次原生 PVS 对照。监督候选在孤立源、正反 0.03 m/s 稳态流、$\pm0.02$ m/s 周期流、小导航扰动、弱邻源、组合扰动和未知对称包络的横向任务中完成 {closure['positive_completed']}/{closure['positive_runs']} 次；全核心真实横偏 MAE 为 {mae.replace('–','--')} m、最大横偏为 {mx.replace('–','--')} m。其余 {closure['negative_rejected']}/{closure['negative_runs']} 次撤权，错误几何授权与错误任务完成均为 {closure['named_false_geometry']}/60 和 {closure['false_completion']}/60。旧链有 {sum(s['false_geometry_publication'] for s in legacy)}/60 次错误几何授权，尽管融合邻源的载体误差仍可通过路线门（图~\ref{{fig:ch05-inspection-robustness-summary}}）。拒绝不算任务成功，截短误差不与完整任务排名；三种子有限网格不等于海况成功概率。未知对称场形的横向通过亦不授权埋深。

\begin{{figure}}[htbp]
\centering
\includegraphics[width=0.96\linewidth,height=0.38\textheight,keepaspectratio,alt={{独立留出反向小流在条件式五米接入下完成真实核心段，旧二十米接入未覆盖；融合邻源的车辆误差通过相应门限但中心错误，额外参考监督拒绝目标授权}}]{{experiments/fwhm_v2/77_defense_robustness_thesis_summary.pdf}}
\caption{{条件式接入与指定目标几何授权的独立留出反例。左图全部核心 Track 样本含回归，灰区为旧链未覆盖段；右图误差按不同职责的阈值归一化。监督候选另有外部参考；接入收益由仅改几何的三次消融验证。}}\label{{fig:ch05-inspection-robustness-summary}}
\end{{figure}}

关闭外部参考的九次消融均未授权指定目标完成，其中融合邻源仍可被沿磁异常跟随；只改接入的反向小流三次均合格完成，分开了运动几何与外部参考的贡献。位置跳变同一仿真周期撤权，慢漂移以有限窗诊断；反向阶跃和超界流仍可能拒绝。监督撤权后 60 s 命令持续为零，30 s 请求上级恢复，但车辆仍滑行或漂移；该请求不等于已完成上级恢复。导航误差界和参考实际成立时才有条件性保证，相关共同偏差、曲线电缆和完整三维多源场仍不在本组范围。

\paragraph{{历史 ROS 与多横切证据}}
历史同版 ROS--PID--守卫--本地 UDP--原生 PVS 的八条有限航迹为七条到端、一条反向阶跃暂停；暂停后 241/241 周期零命令，60 s 仍移动 5.683 m。稳态最大横偏 0.742--1.234 m 相对估计线，不能替代本次相对真缆的误差；历史软件链与新增独立回路不拼为一次实时或实艇验收。

'''
    p5.write_text(text[:start]+new+text[stop:])
    modified=p5.read_text().replace('历史 ROS 横流与多横切结果见第~\\ref{sec:ch05-inspection-ros-boundary}节',
        '扰流／输入失配监督与历史 ROS 多横切边界见第~\\ref{sec:ch05-inspection-ros-boundary}节')
    p5.write_text(modified)
    old_para=next(line for line in old6.splitlines() if line.startswith('当前磁巡检源码在孤立直线磁源'))
    replacement=rf'磁巡检的原生 PVS 限定基线在两场形各三种子覆盖 70 m 核心，无源三次拒绝。新增冻结留出在 20 条件下形成 120 次两方法对照：独立监督的有限正例 {closure["positive_completed"]}/{closure["positive_runs"]} 完成，其余 {closure["negative_rejected"]}/{closure["negative_runs"]} 撤权，错误几何授权与错误任务完成均为零；全核心真实横偏 MAE {mae.replace("–","--")} m、最大 {mx.replace("–","--")} m。这些结果依赖外部受控目标参考、导航误差界与直线短段条件，无参考不授权指定目标。仅改接入的消融分离了运动几何收益，撤权零命令仍不等于艇停；历史 ROS 链与本次独立回路不拼为实时整任务验收。'
    p6.write_text(old6.replace(old_para,replacement))
    figure=a.results/'figures/77_defense_robustness_thesis_summary.pdf'
    target=ROOT/'docs/thesis/figures/experiments/fwhm_v2'/figure.name
    assert not target.exists(), 'do not replace an existing published figure'
    shutil.copyfile(figure,target)
    result=dict(changes={str(p.relative_to(ROOT)):dict(before_sha256=hashlib.sha256((backup/'data'/p.name).read_bytes()).hexdigest(),after_sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [p5,p6]},
        added_figure=str(target.relative_to(ROOT)),figure_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        replaced_historical_figure='61_finite_track_current_envelope_and_clock.pdf remains preserved in assets and 169/236-page backups',
        current_pdf_before_backup=str(backup.relative_to(ROOT)))
    (a.results/'thesis_source_sync.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
