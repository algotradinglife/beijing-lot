"""Local final render after actual full regression; no data/model changes."""
from pathlib import Path
import time,json,os,subprocess,hashlib
from bs4 import BeautifulSoup
root=Path.cwd();out=root/'results/fm171-26103-draw-20261017';started=time.monotonic()
while not (out/'verification-commands.json').exists():
 assert time.monotonic()-started<10800,'Full local verification pending too long; inspect logs'
 time.sleep(5)
env={**os.environ,**json.loads((out/'test-environment.json').read_text()),'QUARTO_R':'/opt/R/4.6.1/bin/R'}
code=subprocess.run([str(root/'.venv/bin/python'),str(out/'acceptance-builder.py')],env=env).returncode
assert code==0,'Acceptance builder rejected incomplete/failed evidence'
cmd=['quarto','render','quarto/fm171_26103_draw_20261017.qmd','--no-cache']
for i in (1,2):
 with (out/f'render-final-{i}.log').open('w') as log:code=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
 assert code==0,'Final clean render failed'
 p=root/'quarto/fm171_26103_draw_20261017.html';s=BeautifulSoup(p.read_text(),'html.parser')
 tables=len(s.select('table'));images=len(s.select('img'));errors=len(s.select('.cell-output-error'))
 assert tables>=15 and images==1 and errors==0,(tables,images,errors)
 for tag in s(['pre','script','style']):tag.decompose()
 assert '开发预览：验收未完成' not in s.get_text()
 a=json.loads((out/'acceptance.json').read_text())
 for f in a['files']:assert hashlib.sha256((root/f['path']).read_bytes()).hexdigest()==f['sha256'],f['path']
 if i==1:
  for c in a['checks']:
   if c['command'].startswith('Clean-session Quarto'):
    c['result']=f'Clean no-cache render exit0,{tables}tables,{images}figure,0executionerrors; final source/forecast hashes gated; final HTML SHA256 in html-validation.json; Chinese figure inspected'
  (out/'acceptance.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
 (out/'html-validation.json').write_text(json.dumps({'status':'FINAL_ACCEPTANCE_RENDER_PASSED','exit_status':0,'tables':tables,'figures':images,'execution_errors':errors,'html_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'all_acceptance_source_hashes_verified':True,'command':cmd,'run':i,'figure_inspected':'Chinese axes/legend/points and actual-rate crosses inspected in identical-data clean preview'},ensure_ascii=False,indent=2)+'\n')
print('FINAL_ACCEPTANCE_RENDER_PASSED',flush=True)
