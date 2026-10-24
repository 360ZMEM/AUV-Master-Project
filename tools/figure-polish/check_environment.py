#!/usr/bin/env python3
"""Reject dependency drift before rendering, without installing or updating."""
import hashlib,json,os,platform,subprocess,sys
from importlib.metadata import version
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
lock=ROOT/'tools/figure-polish/requirements.lock'
requirements=dict(line.split('==',1) for line in lock.read_text().splitlines() if line and not line.startswith('#'))
actual={name:version(name) for name in requirements}
drift={name:{'expected':expected,'actual':actual[name]} for name,expected in requirements.items() if actual[name]!=expected}
if drift:raise SystemExit('Dependency drift: '+json.dumps(drift))
os.environ['FONTCONFIG_FILE']=str(ROOT/'config/diagram-governance/fonts.conf')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
fonts={}
for family in ['Songti SC','Noto Serif CJK SC']:
    resolved,path,index=subprocess.run(['fc-match','-f','%{family}|%{file}|%{index}',family],check=True,capture_output=True,text=True).stdout.split('|')
    assert resolved=='Noto Serif CJK SC',(family,resolved)
    fonts[family]={'family':resolved,'path':path,'index':index,'sha256':sha(path)}
fandol=Path('/usr/share/texlive/texmf-dist/fonts/opentype/public/fandol/FandolSong-Regular.otf')
fonts['FandolSong']={'path':str(fandol),'sha256':sha(fandol)}
drawio=subprocess.run(['dpkg-query','-W','-f','${Version}','draw.io'],capture_output=True,text=True,check=True).stdout
assert drawio=='24.7.17',drawio
record={'python':sys.version,'platform':platform.platform(),'resolved_packages':actual,'lock_sha256':sha(lock),
        'fonts':fonts,'drawio_package_version':drawio,'fontconfig_sha256':sha(os.environ['FONTCONFIG_FILE'])}
(ROOT/'docs/thesis/figure-polish/environment.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print('PASS: pinned dependencies, draw.io version and actual serif font files')
