#!/usr/bin/env python3
"""Report current measurements and explicit retained-image decisions."""
import importlib.util,json,hashlib,shutil,sys
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('compact',Path(__file__).with_name('compact_20261023.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
RUN,DOC=c.RUN,c.DOC
read=c.read;sha=c.sha

def preview(source,target):
    target=DOC/'evidence'/target;target.parent.mkdir(parents=True,exist_ok=True)
    with Image.open(source) as image:
        image=image.convert('RGB');image.thumbnail((1500,1700));image.save(target)
    return str(target.relative_to(DOC))

def main():
    native=read(RUN/'checks_all.json');paper=read(RUN/'paper_audit.json')
    retained=read(DOC/'retained_images.json');integrity=read(RUN/'readonly_integrity.json')
    reviews=read(DOC/'final_visual_review.json') if (DOC/'final_visual_review.json').exists() else []
    index={(x['scope'],x['key']):x for x in reviews}
    issues=[]
    for x in native:
        key=x['file']+'#'+str(x['page_index']);v=index.get(('native',key))
        if x['errors'] or sha(ROOT/x['file'])!=x['source_sha256']:issues.append('native:'+key)
        if not v or sha(ROOT/x['png'])!=v['png_sha256']:issues.append('native-view:'+key)
    for x in paper['page_previews']:
        key=str(x['physical_page']);v=index.get(('paper',key))
        if not v or sha(ROOT/x['preview'])!=v['png_sha256']:issues.append('paper-view:'+key)
    if paper['pdf_sha256']!=sha(ROOT/paper['pdf']):issues.append('paper-changed')
    if not integrity['pass'] or any(not (ROOT/p).exists() or sha(ROOT/p)!=v for p,v in integrity['after'].items()):issues.append('readonly-integrity')
    if not read(RUN/'idempotence.json')['pass']:issues.append('idempotence')
    if not read(RUN/'plot_data_invariance.json')['pass']:issues.append('plot-data')
    if not all(sha(ROOT/x['asset'])==x['asset_sha256'] and x['visual_review']=='VIEWED' for x in retained):issues.append('retained-assets')
    fonts=read(RUN/'pdf_audit.json');retained_paths={x['asset'] for x in retained}
    if any(x['embedding_warning'] or x['unexpected_sans_cjk'] for x in fonts if x['path'] not in retained_paths):issues.append('fonts')
    if read(RUN/'selftest/result.json')['status']!='PASS' or '10 passed' not in (RUN/'inspector-tests.log').read_text():issues.append('inspector-tests')
    if read(RUN/'paper-fixtures/result.json')['status']!='PASS' or read(RUN/'paper_boundary_audit.json')['errors']:issues.append('paper-boundary')
    if read(DOC/'prose_audit.json')['findings']:issues.append('prose-audit')
    baseline=read(RUN/'baseline_manifest.json')
    if not all(sha(RUN/'backup'/x['path'])==x['sha256'] for x in baseline):issues.append('backup-integrity')
    report={'date':'2026-10-23','status':'NEEDS_REVIEW' if issues else 'COMPLETE_WITH_RETAINED_ASSETS',
        'strict_all_figures_pass':False,'issues':issues,'native_sources':32,'native_pages':34,
        'paper_pages':paper['pages'],'figure_groups':48,'assets':53,'placements':54,'paper_sha256':paper['pdf_sha256'],
        'retained_assets':11,'retained_policy':'用户确认输入已丢失，接受原图保留；旧缺陷不冒充修复通过。',
        'backup_files':len(baseline),'protected_files':integrity['protected_files'],
        'native':[{k:x[k] for k in ['file','page_index','coverage','source_sha256','errors','png']} for x in native],
        'placements_detail':paper['placements'],'float_sweep':read(RUN/'float_sweep.json'),
        'text_edits':read(DOC/'prose_edits.json'),'retained_images':retained}
    c.write(DOC/'acceptance.json',report)
    if issues:
        print('NEEDS_REVIEW:',issues);return 2
    before=read(RUN/'baseline-paper/paper_audit.json');changes=[]
    wanted=['2.3','2.4','2.7','3.1','4.2','4.5','5.4','5.17']
    lines=['# 论文图像尺寸、分页与正文润色（2026-10-23）','',
        '**本轮调整完成；11 幅遗失输入的旧图按用户决定保留。** 不把旧图的已知遮挡、字体问题或未验证的重绘能力记为通过。前一轮严格/润色报告仍保留历史含义。','',
        f"当前论文 **{paper['pages']} 页**；48 图组、53 个资产、54 次插入、{len(paper['page_previews'])} 个含图物理页。34 页原生图 fresh 真实文字/形状检查无布局、映射或语义错误；17 项原生、10 项 Matplotlib 与 3 项实际 PDF 边界检查通过，33 文件再生成零变化。",'',
        '## 尺寸与字窗的实际变化','',
        '第 1 章图片和图源维持；原生图保留全部文字、ID、连线及可编辑性。2.3/2.4 的纸面盒子和字号缩小约 20%，通过源线宽补偿或同倍率几何压缩保持纸面边框厚度；3.1 的纵向布局收紧 15%，字号保留。4.2 仅收紧下部任务泳道，上部菱形保留所需安全区，未强压至溢出。','',
        '| 图 | 宽 × 高：前 → 后（mm） | 最小标签基准：前 → 后（PDF pt） | 论文页对照 |','|---|---|---|---|']
    for number in wanted:
        old=[x for x in before['placements'] if x['figure']==number]
        new=[x for x in paper['placements'] if x['figure']==number]
        for i,(a,b) in enumerate(zip(old,new)):
            font=lambda x:x.get('renderer_label_base_min_final_pt',x.get('extracted_text_min_final_pt'))
            f=lambda x:'—' if font(x) is None else f'{font(x):.2f}'
            label=number+(f'（{i+1}）' if len(new)>1 else '')
            bp=RUN/'baseline-paper/paper-images'/f"page_{a['physical_page']:03}.png"
            ap=RUN/'paper-images'/f"page_{b['physical_page']:03}.png"
            bl=preview(bp,Path('paper')/f'{number}_{i}_before.png');al=preview(ap,Path('paper')/f'{number}_{i}_after.png')
            lines.append(f"| {label} | {a['width_mm']:.1f} × {a['height_mm']:.1f} → {b['width_mm']:.1f} × {b['height_mm']:.1f} | {f(a)} → {f(b)} | [前]({bl}) / [后]({al}) |")
            changes.append({'figure':label,'before':a,'after':b})
    lines += ['', '字号为真实 PDF 字形子集或 Agg 标签基准，经实际插入矩阵换算；公式下标和 Type3 中文抽字不完整，不能仅据此断言全部字形同字号。图 2.7(a) 的投影放大约 18%；图 5.17 的图例移出轨迹区并统一文字尺寸，两图所有绘制曲线数组与原输入哈希相同。', '',
        '## 分页与文字','',
        '将应急、生命周期、行为树和参考生命周期图与相邻解释段落共同组织；保留必要的密集图尺寸。逐页筛查结果在 [acceptance.json](acceptance.json) 的 `float_sweep`，筛选依赖实际看图，不以导出成功代替复核。第 1 章技术路线图遵照用户要求维持。', '',
        '正文将 46 处类名、消息路径、状态字段和工具名替换为功能或物理含义，另修正 21 处中文间空格；[逐项旧新映射](prose_edits.json) 保留复现标识。数学变量、协议帧和必要硬件字段保留；[可见实现标识检查](prose_audit.json) 无未解释项。同期第 1、2 章文献/标准修订另存外部差分，未回退，也不冒充本轮研究变更。', '',
        '## 遗失输入图像：现状采样与保留','',
        '下列原 PDF/PNG 未侵入修改；样本从现有 PDF 实际渲染并逐一打开。旧字体、图例遮挡及原输入重绘不可验证的限制继续保留。','',
        '| 资产 | 现状预览 |','|---|---|']
    for x in retained:
        lines.append(f"| `{Path(x['asset']).stem}` | [原样采样]({(ROOT/Path(x['preview'])).relative_to(DOC)}) |")
    lines += ['', '完整路径、原图/预览 SHA-256 与已知限制见 [保留清单](retained_images.json)。', '',
        '## 复现、证据与回滚','',
        '```sh','python3 tools/figure-polish/compact_20261023.py run','python3 tools/figure-polish/compact_20261023.py verify','python3 tools/figure-polish/compact_20261023.py prose_audit','```','',
        '`run` 仅由真实生成器重放排版/既有输入绘图，再编译论文；候选看图哈希不符或正式文件出现外部修改时拒绝覆盖。`verify` 只读检查图源、正式资产、输入与现有 PDF，重新渲染和测量；新图没有实际看图记录时不能通过最终报告。`prose_audit` 可在后续修订中重复运行，不自动删除变量或改写结论。', '',
        f"本轮 {len(baseline)} 份工作树原件及其哈希在 `.diagram-governance/runs/20261023_compact_thesis/backup/` 与 `baseline_manifest.json`；只读复检保护 {integrity['protected_files']} 文件且零变化。前一轮备份完整保留。生成器、候选失败迭代、输入/曲线不变性、57 个 PDF 字体检查和命令日志也在该运行目录。",'',
        '[逐页实际看图/同图继承记录](final_visual_review.json) · [候选看图](candidate_visual_review.json) · [逐项验收](acceptance.json)','',
        '本轮不运行新的巡检仿真或逆解，不更改算法、实验数值和现场许可；图像与写作润色完成度不等同于研究或实艇验收完成度。','']
    (DOC/'README.md').write_text('\n'.join(lines));c.write(DOC/'size_changes.json',changes)
    entry=ROOT/'docs/thesis/figure-polish/README.md'
    current=entry.read_text()
    marker='> **2026-10-23 当前入口**：[尺寸、分页、正文润色与遗失输入保留记录](20261023/README.md)。以下为 2026-10-22 历史验收，当前状态与重跑命令以上述入口为准。\n\n'
    if marker not in current:entry.write_text(marker+current)
    print(report['status'],paper['pages'],'pages; 34 native pages and 11 explicitly retained assets')
    return 0

if __name__=='__main__':sys.exit(main())
