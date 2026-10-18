"""Acceptance-only rendered-artifact regression; no model or selection code."""
from pathlib import Path
import base64,datetime,hashlib,json,sys
from bs4 import BeautifulSoup
assert len(sys.argv)==2
root=Path(sys.argv[1]).resolve(strict=True)
out=root/'results/margin-combination-study-20261018-v2'
html=root/'quarto/margin_combination_study_20261018.html'
a=json.loads((out/'acceptance.json').read_text());assert a['status']=='ACCEPTED'
soup=BeautifulSoup(html.read_text(),'html.parser')
tables=len(soup.select('table'));images=soup.select('img');assert tables>=16 and len(images)==3
suite_tables=[]
for t in soup.select('table'):
 headers=[h.get_text(strip=True) for h in t.select('thead th')]
 if all(x in headers for x in ['suite','tests','passed','failed','errors','warnings','skipped']):suite_tables.append((t,headers))
assert len(suite_tables)==1,'Full-suite evidence table must be visibly rendered'
table,headers=suite_tables[0];expected={r['suite']:r for r in a['tests']};seen=set()
for row in table.select('tbody tr'):
 values=[x.get_text(strip=True) for x in row.select('td')];record=dict(zip(headers,values));suite=record['suite'];seen.add(suite)
 for key in ['tests','passed','failed','errors','warnings','skipped']:
  assert float(record[key].replace(',',''))==expected[suite][key],(suite,key)
assert seen==set(expected)
for node in soup.select('pre,code'):node.decompose()
text=soup.get_text(' ',strip=True)
assert '阶段报告：完整验收尚未完成' not in text
assert 'No blocking findings' in text
for phrase in ['Error in','Execution halted']:assert phrase not in text
for p,h in a['source_hashes'].items():assert hashlib.sha256((root/p).read_bytes()).hexdigest()==h,p
for p,h in a['output_hashes'].items():assert hashlib.sha256((out/p).read_bytes()).hexdigest()==h,p
for i,img in enumerate(images,1):
 Path(f'/tmp/margin-study-final-figure-{i}.png').write_bytes(base64.b64decode(img['src'].split(',',1)[1]))
receipt={'status':'FINAL_ACCEPTANCE_RENDER_VERIFIED','generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tables':tables,'figures':len(images),'full_suite_evidence_table_verified':True,'review_verdict_visible':True,'no_execution_error_text':True,'preliminary_notice_absent':True,'source_and_output_hashes_verified':True,'html_sha256':hashlib.sha256(html.read_bytes()).hexdigest(),'acceptance_sha256':hashlib.sha256((out/'acceptance.json').read_bytes()).hexdigest(),'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'render_log_sha256':hashlib.sha256((out/'render-final.log').read_bytes()).hexdigest()}
(out/'html-validation.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
