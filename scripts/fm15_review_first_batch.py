"""Split a verified token-limited six-fixture task into bounded single reviews."""
from pathlib import Path
import json,subprocess,sys,hashlib
root=Path(sys.argv[1]).resolve();out=root/'results/fm15-two-issues-20261012'
failed=out/'review-call-01-summary'
assert 'reached a model token limit' in (failed/'stdout.txt').read_text()
packets=json.loads((out/'review-inputs.json').read_text())['fixtures'][:6]
caller=Path('/home/drwho1985/.codex/skills/pa-analysis/scripts/call_pa.py')
rows=[];calls=[];local_reviews=[]
for i,p in enumerate(packets,1):
 local_path=out/f'local-review-26098-{i}.json'
 if local_path.exists():
  local_receipt=out/f'local-review-26098-{i}-receipt.json'
  lr=json.loads(local_receipt.read_text());row=json.loads(local_path.read_text())
  assert lr['reviewer']=='ROOT_CODEX' and hashlib.sha256(local_path.read_bytes()).hexdigest()==lr['review_sha256']
  assert hashlib.sha256((out/'review-inputs.json').read_bytes()).hexdigest()==lr['input_sha256']
  assert all(row[k]==p[k]==lr[k] for k in ('fixture_id','cutoff_utc','base_hash'))
  assert row['decision']=='retain' and row['market_action']=='UNIDENTIFIED_SHIFT'
  rows.append(row);local_reviews.append(str(local_receipt.relative_to(root)))
  print('Accepted disclosed local review',p['fixture_id'],flush=True)
  continue
 work=out/f'single-work-01-{i}';work.mkdir(exist_ok=True)
 (work/'input.json').write_text(json.dumps(p,ensure_ascii=False))
 prompt=out/f'single-prompt-01-{i}.txt'
 prompt.write_text('''FM-1.5.0单场历史诊断盲审。只读input.json，只写review.json。禁其他路径、联网、安装、目标赛果和北单。一次Python读取并只打印名称、lambda、native_rates、top_margins、independent_market、asian_quotes、total_quotes和article_facts，不打印哈希。原生lambda已混合近期0.5，不重复加成；市场仅复核，不自动替换lambda。基于攻击、防守、赛事类别、独立事实审核中心。没有额外可量化信息就KEEP_NATIVE；明确独立事实支持移位但幅度未知就UNIDENTIFIED_SHIFT且retain；其他apply，尾部统一中心等距最多2档、任侧>=10%纳入整对、外围0.3，不能强行下注排序。
输出单个JSON对象，字段fixture_id/cutoff_utc/base_hash原样从input复制，decision=apply或retain，market_action=KEEP_NATIVE或UNIDENTIFIED_SHIFT，reason最多30中文字（具体数据），counterevidence最多20字，market_review最多40字（接受/拒绝哪些信息），evidence_ids选择1-4个根字段名：native_rates,top_margins,independent_market,asian_quotes,total_quotes,euro_quotes,missing，或文章evidence_id。直接短句判定，一次Python写文件，不探索环境或重复读取打印，最后仅报文件名。''')
 call=out/f'single-call-01-{i}'
 if not (call/'receipt.json').exists():
  assert not call.exists()
  result=subprocess.run([sys.executable,str(caller),'--prompt-file',str(prompt),'--cwd',str(work),'--output-dir',str(call),'--timeout','300','--model','opencode/deepseek-v4.1-flash'],capture_output=True,text=True)
  (out/f'single-driver-01-{i}.log').write_text(result.stdout+result.stderr)
 r=json.loads((call/'receipt.json').read_text())
 if r['exit_code']!=0:
  diagnostic=(call/'stdout.txt').read_text()+(call/'stderr.txt').read_text()
  assert any(x in diagnostic for x in ('ECONNRESET','unknown certificate verification error')),f'Single {i}: nontransient failure'
  retry=out/f'single-call-01-{i}-network-retry'
  if not (retry/'receipt.json').exists():
   assert not retry.exists() and not (work/'review.json').exists()
   result=subprocess.run([sys.executable,str(caller),'--prompt-file',str(prompt),'--cwd',str(work),'--output-dir',str(retry),'--timeout','300','--model','opencode/deepseek-v4.1-flash'],capture_output=True,text=True)
   (out/f'single-network-driver-01-{i}.log').write_text(result.stdout+result.stderr)
  call=retry;r=json.loads((call/'receipt.json').read_text())
 assert r['exit_code']==0 and not r['timed_out'] and (work/'review.json').exists(),f'Single {i}: stop and inspect'
 row=json.loads((work/'review.json').read_text())
 assert all(row[k]==p[k] for k in ('fixture_id','cutoff_utc','base_hash'))
 assert row['decision'] in ('apply','retain') and row['market_action'] in ('KEEP_NATIVE','UNIDENTIFIED_SHIFT')
 assert row['market_action']!='UNIDENTIFIED_SHIFT' or row['decision']=='retain'
 allowed={'native_rates','top_margins','independent_market','asian_quotes','total_quotes','euro_quotes','missing'}|{a['evidence_id'] for a in p['article_facts']}
 assert 1<=len(row['evidence_ids'])<=4 and set(row['evidence_ids'])<=allowed
 archive=out/'prompt-receipts';archive.mkdir(exist_ok=True)
 assert hashlib.sha256(prompt.read_bytes()).hexdigest()==r['prompt_sha256']
 (archive/(r['prompt_sha256']+'.txt')).write_bytes(prompt.read_bytes())
 rows.append(row);calls.append(str(call.relative_to(root)))
 print('Accepted single',p['fixture_id'],flush=True)
rp=out/'review-work-01/reviews.json';assert not rp.exists()
rp.write_text(json.dumps(rows,ensure_ascii=False,indent=2))
(out/'pa-selection-01.json').write_text(json.dumps({'batch':1,'call_path':calls[0],'call_paths':calls,'local_review_receipts':local_reviews,'review_path':str(rp.relative_to(root))},indent=2)+'\n')
