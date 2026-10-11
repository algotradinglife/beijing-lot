"""Recover receipt-exact prompt bytes; hashes, never guesses, authorize recovery."""
from pathlib import Path
import hashlib,json,sys
out=Path(sys.argv[1]).resolve()/'results/fm15-two-issues-20261012'
texts=[p.read_text() for p in out.glob('*prompt-*.txt')]
texts += [s.split('\n额外允许读summary.txt')[0] for s in texts if s.startswith('FM-1.5.0')]
for s in list(texts):
 for marker in ('\n前轮达到输出token上限','\n严格步骤：'):
  if marker in s:
   prefix,suffix=s.split(marker,1)
   texts.append(prefix.split('\n额外允许读summary.txt')[0]+marker+suffix)
archive=out/'prompt-receipts';archive.mkdir(exist_ok=True)
lookup={hashlib.sha256(t.encode()).hexdigest():t for t in texts}
inventory=[]
receipts=list(out.glob('review-call-*/receipt.json'))+list(out.glob('single-call-*/receipt.json'))+list(out.glob('text-call-*/receipt.json'))
assert receipts
for p in receipts:
 r=json.loads(p.read_text());sha=r['prompt_sha256'];target=archive/(sha+'.txt')
 if target.exists():
  assert hashlib.sha256(target.read_bytes()).hexdigest()==sha
 else:
  assert sha in lookup,f'Missing receipt-exact prompt: {p}'
  target.write_text(lookup[sha])
 inventory.append({'receipt_path':str(p.relative_to(out)),'prompt_path':str(target.relative_to(out)),'sha256':sha})
(out/'prompt-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
print('Bound',len(inventory),'PA receipts to exact prompt bytes.')
