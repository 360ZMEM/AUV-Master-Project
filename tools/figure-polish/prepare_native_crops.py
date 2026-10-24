#!/usr/bin/env python3
"""Create high-risk source/page crops, without marking them viewed."""
from pathlib import Path
import hashlib,json
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];RUN=ROOT/'.diagram-governance/runs/20261021_presentation_polish'
records=json.loads((RUN/'checks_all.json').read_text());out=[]
selection={'auv_v2_dual_brain_async_hardware':'bus','auv_code_layer_architecture':'g3','auv_ros2_node_topology':'bus','auv_runtime_dataflow':'b5','auv_safety_arbiter_deployment':'j3','auv_system_subsystem_organization':'o_safe','auv_system_capability_map':'deploy','auv_system_autonomy_functional_loop':'state','auv_v2_uncertainty_highway':'e','auv_v2_behavior_tree_illustration':'route','auv_v2_emergency_transition':'g3','auv_v2_mission_lifecycle_flow':'br2','fig_perception_pipeline':'fit','fig_zigzag_probe':'t_est','fig_arch_onion':'p3'}
for r in records:
    if r['file'].startswith('AUV-Master-Mag/thesis/'):continue
    path=Path(r['file']);page=r['page_index'];cells=r['measured']['cells'];target=selection.get(path.stem)
    if target not in cells:
        candidates=[(k,v) for k,v in cells.items() if v['fragments'] and k not in ('0','1') and v['shape']['w']<800]
        target=max(candidates,key=lambda kv:len(kv[1]['rendered']))[0]
    rect=cells[target]['shape'];png=ROOT/r['png'];im=Image.open(png);viewport=r['measured']['svg'];sx,sy=im.width/viewport['w'],im.height/viewport['h'];pad=45
    box=(max(0,(rect['x']-pad)*sx),max(0,(rect['y']-pad)*sy),min(im.width,(rect['right']+pad)*sx),min(im.height,(rect['bottom']+pad)*sy))
    crop=RUN/'native-crops'/f'{path.stem}_p{page}_{target}.png';crop.parent.mkdir(parents=True,exist_ok=True);im.crop(tuple(map(round,box))).save(crop)
    out.append({'file':r['file'],'page':page,'cell_id':target,'source_sha256':r['source_sha256'],'crop':crop.relative_to(ROOT).as_posix(),'crop_sha256':hashlib.sha256(crop.read_bytes()).hexdigest(),'visual_review':'PENDING'})
(RUN/'native_crop_inventory.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
# A contact sheet keeps each crop at natural size up to 650 px wide. These
# sheets are only review aids; the original crop and source hash remain above.
for batch in range(0,len(out),4):
    ims=[]
    for item in out[batch:batch+4]:
        pic=Image.open(ROOT/item['crop']).convert('RGB');pic.thumbnail((700,600));ims.append((item,pic))
    w=1440;h=sum(max(im.height for _,im in ims[i:i+2])+45 for i in range(0,len(ims),2))
    sheet=Image.new('RGB',(w,h),'white');draw=ImageDraw.Draw(sheet);y=0
    for row in range(0,len(ims),2):
        for col,(item,pic) in enumerate(ims[row:row+2]):
            x=col*720;draw.text((x+5,y+5),Path(item['file']).stem+' p'+str(item['page']),fill='black');sheet.paste(pic,(x+5,y+35))
        y+=max(im.height for _,im in ims[row:row+2])+45
    sheet.save(RUN/'native-crops'/f'sheet_{batch//4+1}.png')
print('prepared',len(out),'high-risk crops')
