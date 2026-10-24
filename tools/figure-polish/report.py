#!/usr/bin/env python3
"""Combine independent measurements and hash-bound visual attestations.

Does not grant PASS from export success, delete pending checks in the original
inspector, change policy, or infer that missing raw inputs were verified.
"""
import hashlib,json,re,shutil,subprocess,sys
from collections import Counter
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'.diagram-governance/runs/20261021_presentation_polish'
DOC=ROOT/'docs/thesis/figure-polish'
def read(p,default=None):return json.loads(p.read_text()) if p.exists() else default
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pixel(p):
    with Image.open(p) as im:
        im=im.convert('RGBA');return hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest()
def evidence(src,relative):
    target=DOC/'evidence'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    try:
        with Image.open(src) as im:
            im=im.convert('RGB');im.thumbnail((1500,1800));im.save(target)
    except OSError:
        return None
    return 'evidence/'+str(relative)

DEFERRED={
 'terrain_tz_tracking_pid_mpc':'用户暂缓；缺 results/control/terrain_following_20260823_215036/ 原始 bag/PVS trace；保留现有字体和产物',
 'terrain_3d_pid_terrain_trajectory':'用户暂缓；同一地形原始包缺失，旧图仍含非目标中文字体',
 'r13_v2_authority_modes_ua':'用户暂缓；缺 r13_v2_authority_policy_summary_by_scenario_mode.csv；旧图字体/图例仍待修复',
 'pc104_firmware_echo_timing':'用户暂缓四组 PC104；缺 pc104_udp_timing_echo_300s_20260822/udp_timing_samples.csv',
 'pc104_fault_timeline':'用户暂缓；缺 pc104_fault_injection_formal_v2_20260822/fault_timeline.csv；故障位和 watchdog 图例遮住曲线',
 'pc104_cross_layer_fault_timeline':'用户暂缓；缺 pc104_cross_layer_fault_sync_20260822_222112；现有图例/时间线仍需原输入复核',
 'pc104_cross_layer_soak_30min':'用户暂缓；缺 pc104_cross_layer_fault_sync_20260822_225436；柱图、RSS 图例和底部说明仍遮挡数据',
}
REPLAY={
 '03_complexity_comparison':'历史函数级复杂度输入包 results/decision/bt_vs_fsm/20260608_173806 未定位；静态成图已看，未以当前算法重算替代',
 '05_mpc_combined_summary':'历史 MPC 四时序绘图输入未定位；不能通过重跑仿真冒充旧试验的纯排版重绘',
 'ch4_enob_vs_osr':'缺 hardware_wrappers/fangkong_adc/raw_data/enob/20260809T161036/ch4_enob_results.json 与原绘图生成器',
 'ch4_noise_spectral_density':'缺同一 ADC 原始短接噪声序列/频谱缓存及原绘图生成器；不从图片猜造数值',
}

def main():
    inventory=read(DOC/'inventory.json',[])
    checks=read(RUN/'checks_all.json',[])
    manual=read(DOC/'native_visual_review.json',[])
    reviews={(x['file'],x['page']):x for x in manual}
    snapshot_reviews={(x['file'],x['page']):x for x in read(DOC/'snapshot_visual_review.json',[])}
    crops=read(RUN/'native_crop_inventory.json',[])
    exports=read(RUN/'exports.json',{})
    paper=read(RUN/'paper_audit.json',{})
    paper_reviews={x['physical_page']:x for x in read(DOC/'paper_visual_review.json',[])}
    placements=paper.get('placements',[])
    preview_pages={x['physical_page']:x for x in paper.get('page_previews',[])}
    actual_pdf=ROOT/'thuthesis/build/auv-thesis/auv-thesis.pdf'
    current_paper=paper.get('pdf_sha256')==sha(actual_pdf)
    pdf_audits={x['path']:x for x in read(RUN/'pdf_audit.json',[])}
    tests=read(RUN/'selftest/result.json',{})
    mpl_tests=(RUN/'inspector-tests.log').read_text() if (RUN/'inspector-tests.log').exists() else ''
    tests_ok=tests.get('status')=='PASS' and '10 passed' in mpl_tests
    idem=read(RUN/'source_idempotence.json',{})
    idem_ok=idem.get('pass') and all((ROOT/p).is_file() and sha(ROOT/p)==v for p,v in idem.get('after',{}).items())
    readonly=read(RUN/'readonly_integrity.json',{})
    baselines=read(RUN/'baseline_manifest.json',[])
    backup_ok=all((RUN/'backup'/x['path']).is_file() and sha(RUN/'backup'/x['path'])==x['sha256'] for x in baselines)
    native=[]
    for r in checks:
        path=ROOT/r['file'];pi=r.get('page_index');issues=[]
        if not path.is_file() or r.get('source_sha256')!=sha(path):issues.append('SOURCE_CHANGED_AFTER_FRESH')
        issues += [x.get('code','INSPECTION_ERROR') for x in r.get('errors',[])]
        cov=r.get('coverage',{})
        if len(set(cov.values()))!=1 or not cov.get('expected_labels'):issues.append('INCOMPLETE_LABEL_MEASUREMENT')
        review=reviews.get((r['file'],pi));inherited=None
        if r['file'].startswith('AUV-Master-Mag/thesis/'):
            candidates=[x for x in checks if not x['file'].startswith('AUV-Master-Mag/thesis/') and Path(x['file']).name==path.name and x.get('page_index')==pi]
            if len(candidates)==1:
                canonical=candidates[0];review=reviews.get((canonical['file'],pi))
                if sha(ROOT/canonical['file'])==sha(path) and pixel(ROOT/canonical['png'])==pixel(ROOT/r['png']):inherited=canonical['file']
                else:issues.append('SNAPSHOT_NOT_SOURCE_AND_PIXEL_IDENTICAL')
            else:issues.append('SNAPSHOT_CANONICAL_UNRESOLVED')
            direct=snapshot_reviews.get((r['file'],pi))
            if not direct or direct.get('status')!='VIEWED' or direct['source_sha256']!=r.get('source_sha256') or direct['full_png_sha256']!=sha(ROOT/r['png']) or direct['crop_sha256']!=sha(ROOT/direct['crop']):
                issues.append('SNAPSHOT_DIRECT_VIEW_PENDING')
        if not review:issues.append('NO_ACTUAL_VISUAL_REVIEW')
        elif review['source_sha256']!=r.get('source_sha256') or (
                sha(ROOT/(review['full_png'] if inherited else r['png']))!=review['full_png_sha256']
                and pixel(ROOT/r['png'])!=review.get('full_pixel_sha256')):
            issues.append('VISUAL_REVIEW_HASH_STALE')
        if review and (not (ROOT/review['high_risk_crop']).exists() or sha(ROOT/review['high_risk_crop'])!=review['crop_sha256']):issues.append('CROP_REVIEW_STALE')
        formal=exports.get(r['file']);formal_ok=False
        if inherited:formal=exports.get(inherited)
        if formal:
            formal_ok=formal.get('source_sha256')==r.get('source_sha256') and all((ROOT/o['path']).is_file() and sha(ROOT/o['path'])==o['sha256'] for o in formal.get('outputs',[]))
        elif path.stem=='auv_v2_five_layer_functional_architecture':
            canonical=ROOT/'docs/thesis/figures/architecture'/path.name
            # The approved two-page source and its formal two-page PDF are
            # checked through actual paper placements, not a single-page exporter.
            ps=[x for x in placements if Path(x['asset']).stem==path.stem]
            formal_ok=sha(path)==sha(canonical) and len(ps)==2 and all(x['source_sha256']==sha(ROOT/x['asset']) for x in ps)
        if not formal_ok:issues.append('FORMAL_EXPORT_PROVENANCE_STALE')
        export_source=inherited or r['file']
        formal_pdf=str(Path(export_source).with_suffix('.pdf'))
        fa=pdf_audits.get(formal_pdf)
        if not fa or fa['sha256']!=sha(ROOT/formal_pdf):issues.append('FORMAL_PDF_FONT_AUDIT_PENDING')
        elif fa['unexpected_sans_cjk'] or fa['embedding_warning']:issues.append('FORMAL_PDF_FONT_ERROR')
        if not tests_ok:issues.append('INSPECTOR_TESTS_NOT_PASSED')
        if not idem_ok:issues.append('SOURCE_IDEMPOTENCE_NOT_CURRENT')
        ps=[x for x in placements if Path(x['asset']).stem==path.stem and x.get('source_page',1)==pi+1]
        for p in ps:
            v=paper_reviews.get(p['physical_page']);preview=preview_pages[p['physical_page']]
            if not current_paper or not v or v['sha256']!=preview['sha256']:issues.append('PAPER_PAGE_REVIEW_PENDING')
        after=evidence(ROOT/r['png'],Path('native')/(path.stem+f'_p{pi}_after.png')) if r.get('png') else None
        crop_link=evidence(ROOT/review['high_risk_crop'],Path('native')/(path.stem+f'_p{pi}_crop.png')) if review else None
        before=RUN/'backup'/path.with_suffix('.png').relative_to(ROOT)
        before_link=evidence(before,Path('native')/(path.stem+'_before.png')) if before.exists() else None
        before_provenance='Working-tree publication backup'
        if not before_link and inherited:
            own_baseline=RUN/'backup'/r['file'];canonical_baseline=RUN/'backup'/inherited
            if sha(own_baseline)==sha(canonical_baseline):
                canonical_png=canonical_baseline.with_suffix('.png')
                if canonical_png.exists():before_link=evidence(canonical_png,Path('native')/(path.stem+'_before.png'))
                before_provenance='Baseline native source byte-identical to canonical; canonical working-tree publication backup shown'
        if not before_link:
            fallback=next((x for x in read(RUN/'baseline_rerender.json',[]) if Path(x['native_source']).name==path.name),None)
            if fallback:
                before_link=evidence(ROOT/fallback['preview'],Path('native')/(path.stem+'_before.png'))
                before_provenance=fallback['provenance']
        native.append({'file':r['file'],'page':pi,'source_sha256':r.get('source_sha256'),'coverage':cov,
            'status':'PASS_POLISH' if not issues else 'NEEDS_REVIEW','issues':sorted(set(issues)),
            'snapshot_inherited_from':inherited,'before':before_link,'before_provenance':before_provenance,'after':after,'crop':crop_link,
            'paper_placements':ps,'H10':'9pt advisory; actual placement recorded' if ps else 'N/A: not directly inserted in auv-thesis'})
    assets=[]
    for asset in sorted({a for g in inventory for a in g['assets']}):
        path=ROOT/asset;stem=path.stem;issues=[]
        ps=[p for p in placements if p['asset']==asset]
        for p in ps:
            v=paper_reviews.get(p['physical_page']);preview=preview_pages.get(p['physical_page'],{})
            if not current_paper or p['source_sha256']!=sha(path) or not v or v['sha256']!=preview.get('sha256'):issues.append('PAPER_PAGE_REVIEW_PENDING')
        audit=pdf_audits.get(asset)
        if audit:
            if audit['sha256']!=sha(path):issues.append('PDF_AUDIT_STALE')
            if audit['unexpected_sans_cjk']:issues.append('UNEXPECTED_SANS_CJK')
            if audit['embedding_warning']:issues.append('PDF_FONT_EMBEDDING_WARNING')
        raw_native=path.with_suffix('.drawio')
        renderer=RUN/'mpl'/(stem+'.json')
        renderer_status='N/A: photo / original scan / screenshot'
        if raw_native.exists():
            nr=[x for x in native if x['file']==raw_native.relative_to(ROOT).as_posix()]
            if not nr or any(x['status']!='PASS_POLISH' for x in nr):issues.append('NATIVE_PAGE_GATE_PENDING')
            renderer_status='Native Chromium shape-aware measurement'
        elif renderer.exists():
            ar=read(renderer);renderer_status=f"Agg: {ar['label_count']} labels measured"
            if any(ar[x] for x in ['collisions','clipped_text','missing_cjk_glyphs']):issues.append('MPL_GEOMETRY_ERROR')
        elif path.suffix=='.pdf':renderer_status='Static PDF + actual full-image/page review; raw replay unavailable'
        status='PASS_POLISH'
        reason=''
        if stem in DEFERRED:status='USER_DEFERRED_INPUTS';reason=DEFERRED[stem]
        elif stem in REPLAY:status='USER_DEFERRED_INPUTS';reason='用户确认这些输入稍后从旧电脑迁移；'+REPLAY[stem]
        elif issues:status='NEEDS_REVIEW'
        before=RUN/'backup'/path.relative_to(ROOT)
        before_png=before.with_suffix('.png') if path.suffix=='.pdf' else before
        after_png=path.with_suffix('.png') if path.suffix=='.pdf' else path
        before_link=evidence(before_png,Path('paper-assets')/(stem+'_before.png')) if before_png.exists() else None
        after_link=evidence(after_png,Path('paper-assets')/(stem+'_after.png')) if after_png.exists() else None
        assets.append({'asset':asset,'sha256':sha(path),'status':status,'reason':reason,'issues':sorted(set(issues)),
                       'renderer':renderer_status,'before':before_link,'after':after_link,'placements':ps})
    by_asset={x['asset']:x for x in assets};groups=[]
    for group in inventory:
        states={by_asset[p]['status'] for p in group['assets']}
        status='PASS_POLISH' if states=={'PASS_POLISH'} else 'USER_DEFERRED_INPUTS' if states=={'USER_DEFERRED_INPUTS'} else 'PARTIAL_USER_DEFERRED' if 'USER_DEFERRED_INPUTS' in states else 'NEEDS_REVIEW'
        groups.append({**group,'status':status})
    pending=[x for x in assets if x['status']!='PASS_POLISH']
    passed=not pending and all(x['status']=='PASS_POLISH' for x in native) and readonly.get('pass') and backup_ok
    generators=[p for p in [ROOT/x['path'] for x in baselines] if p.suffix=='.py' and p.is_file()]
    acceptance={'status':'PASS' if passed else 'NEEDS_REVIEW','scope':'32 native sources/34 pages; 48 actual thesis figure groups/54 placements',
        'backup_files':len(baselines),'backup_integrity':backup_ok,'native_selftest':tests.get('status'),
        'mpl_10_tests':bool('10 passed' in mpl_tests),'idempotence':bool(idem_ok),'readonly_integrity':readonly.get('pass'),
        'paper_pages':paper.get('pages'),'paper_sha256':paper.get('pdf_sha256'),'paper_is_current':current_paper,
        'native_counts':dict(Counter(x['status'] for x in native)),'asset_counts':dict(Counter(x['status'] for x in assets)),
        'group_counts':dict(Counter(x['status'] for x in groups)),
        'cached_inputs':read(RUN/'cached_detail_runs.json',{}),
        'generators':{str(p.relative_to(ROOT)):sha(p) for p in generators},
        'semantic_edits':{'path':'docs/thesis/figure-polish/presentation_edits.json','sha256':sha(DOC/'presentation_edits.json')},
        'visual_review_manifests':{name:sha(DOC/name) for name in ['native_visual_review.json','snapshot_visual_review.json','paper_visual_review.json']},
        'environment_lock':{'path':'tools/figure-polish/requirements.lock','sha256':sha(ROOT/'tools/figure-polish/requirements.lock'),
                            'fontconfig_sha256':sha(ROOT/'config/diagram-governance/fonts.conf'),
                            'browser_staging':read(RUN/'browser_staging.json',{})},
        'native':native,'assets':assets,'figure_groups':groups,'remaining':pending}
    (RUN/'acceptance.json').write_text(json.dumps(acceptance,ensure_ascii=False,indent=2)+'\n')
    (DOC/'acceptance.json').write_text(json.dumps(acceptance,ensure_ascii=False,indent=2)+'\n')
    lines=['# 全仓图像展示性治理记录','',f"当前状态 **{acceptance['status']}**。本轮修改图源/生成器/正式图像，保留研究数据、数值和结论；用户暂缓项及无法重绘项未提升为通过。",'',
        f"- 范围：32 个当前原生源 / 34 页；48 个论文图组 / 54 次实际插入。冻结历史 21 份保留。",f"- 原生页状态：`{acceptance['native_counts']}`；论文资产：`{acceptance['asset_counts']}`。",f"- 论文：{paper.get('pages')} 页；48 个含图物理页逐张打开。最终页面哈希须与 [看图记录](paper_visual_review.json) 相符。",f"- 追加式备份 {len(baselines)} 文件，校验 `{backup_ok}`；两份嵌套扩展开销旧副本采用用户认可的旧主图恢复基线，并未声称取得原嵌套副本。",'',
        '## 重跑与只读验收','', '```sh','python3 tools/figure-polish/workflow.py run','python3 tools/figure-polish/workflow.py verify','```','',
        '第一条只重放已有缓存绘图，含备份、自测、生成器、原生导出、候选图像哈希门、论文构建和 fresh 验收；不运行仿真/逆解。第二条不改图源、正式产物、研究输入或论文 PDF，仅生成复检证据并验证前后哈希。退出码 2 表示尚有待复核/用户暂缓项，不能解释为全量通过。', '',
        '## 本轮口径和工具','',
        '- [POLICY.md](POLICY.md)：用户允许最小字号妥协，9 pt 作为建议；仍禁止遮字、溢出、改数值和宽泛豁免。原严格规范未修改。`PASS_POLISH` 专指本轮口径，不代表原严格 9 pt 门槛通过；原 inspector 的待验字段未被删除。',
        '- [环境与字体实测](environment.json)、[11项暂缓决定](deferral_decisions.json)另列；`inventory.json` 是初始范围清单，最终状态以本页和 `acceptance.json` 为准。',
        '- [主图源22页看图记录](native_visual_review.json)、[同步副本12页独立看图记录](snapshot_visual_review.json)分别绑定全图与高风险局部哈希；副本另核对源文件及像素一致性。',
        '- 原生固定层序/网格布局，draw.io Desktop 24.7.17，Playwright 1.63 / Chromium 153；本轮不需要 ELK。共享目录子进程执行失败通过同哈希本机浏览器缓存修复。',
        '- Matplotlib 3.10.7：真实 Agg 文字测量、形状/连线/图例检查；3D 遮挡和集合图元仍要求实际看图。draw.io 字体为 Noto Serif CJK SC；新绘 Matplotlib 为 FandolSong，旧的真实宋体不会谎称已换为同一字库。',
        '- [FONT_EMBEDDING.md](FONT_EMBEDDING.md)：Fandol CFF 以 Type3 矢量轮廓嵌入，解决跨阅读器错误；中文 PDF 全文检索能力存在限制，原生 Python 与标签测量记录保留。',
        f"- 实测：原生缺陷/合法/变异 17 项 `{tests.get('status')}`；Matplotlib 10 项测试 `{acceptance['mpl_10_tests']}`；源再生成幂等 `{bool(idem_ok)}`；只读保护 `{readonly.get('pass')}`。",'',
        '## 当前剩余问题','']
    for x in pending:lines.append(f"- `{x['status']}` — `{x['asset']}`：{x['reason'] or ', '.join(x['issues'])}。")
    lines += ['', '## 逐原生文件、逐页证据','', '| 图源 / 页 | 标签测量 | 状态 | 证据 | 问题 |','|---|---:|---|---|---|']
    for x in native:
        cov=x['coverage'];links=' / '.join(f'[{label}]({x[k]})' for k,label in [('before','前'),('after','后'),('crop','局部')] if x[k])
        lines.append(f"| `{x['file']}` / {x['page']} | {cov.get('measured_labels')}/{cov.get('expected_labels')} | {x['status']} | {links} | {', '.join(x['issues']) or ('已独立看图；同源/同像素复核：'+x['snapshot_inherited_from'] if x['snapshot_inherited_from'] else '无未解决原生布局缺陷')} |")
    lines += ['', '## 逐论文图组','', '| 图号 | 状态 | 实际物理页 | 产物与前后证据 |','|---|---|---|---|']
    for group in groups:
        items=[by_asset[p] for p in dict.fromkeys(group['assets'])];pages=sorted({p['physical_page'] for x in items for p in x['placements']});links=[]
        for x in items:
            links.append('`'+Path(x['asset']).stem+'` '+ ' / '.join(f'[{label}]({x[k]})' for k,label in [('before','前'),('after','后')] if x[k]))
        lines.append(f"| {group['number']} | {group['status']} | {', '.join(map(str,pages))} | {'<br>'.join(links)} |")
    lines += ['', '## 尺寸、回滚及可追溯性','',
        '实际插入使用 XeTeX 的 FmN/ImN 序列、源 PDF 页尺寸和实际变换矩阵核对，未猜测印刷页偏移；[acceptance.json](acceptance.json) 含逐次毫米尺寸、提取字形子集最小字号及 Agg 标签基准字号。Type3 中文与公式下标不能仅靠 PDF 抽字判定完整字高。',
        '前图优先来自本轮开始前的工作树导出备份；fig_perception_pipeline 与 fig_zigzag_probe 的基线 PNG 为 LFS 指针，故从已备份原生源在锁定字体环境重渲染，明确不冒充缺失的历史位图。快照无独立旧导出时保留原生备份并核对当前源/像素身份。完整 2× 图、SHA-256、命令和原始备份在 `.diagram-governance/runs/20261021_presentation_polish/`。',
        '保护已有脏工作树，未执行 reset/checkout/提交/推送。两份嵌套副本恢复基线的用户决定详见运行目录 `backup_gaps.json`；不隐藏原始逐字节备份缺口。',
        '研究工作完成度及现场许可不因本轮图像治理升级。完整原生图可编辑；历史仿真、真实 PC104、离线分析和真实部署边界继续区分。','']
    (DOC/'README.md').write_text('\n'.join(lines))
    print(json.dumps({k:acceptance[k] for k in ['status','native_counts','asset_counts','group_counts','backup_integrity','idempotence','readonly_integrity']},ensure_ascii=False))
    return 0 if passed else 2
if __name__=='__main__':sys.exit(main())
