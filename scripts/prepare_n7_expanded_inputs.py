"""Thin offline release adapter; source parsing/archive contracts stay shared.

CLI: project-python scripts/prepare_n7_expanded_inputs.py CONFIG.json
CONFIG declares root, release/hash, old result/hash, archived scope descriptors,
published scope paths/hashes and archive registry paths/hashes. Output must be
new. Copies only hash-verified roster receipts; no scraping or settlement reads.
"""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys

import pandas as pd
from src.data_archive import read_archive_members
from src.fundamentals_roster_handicap import roster_handicaps
from src.n7_published_markets import read_n7_published_markets
from src.n7_research_scope import exclude_n7_research_fixtures

cfg = json.loads(Path(sys.argv[1]).read_text())
root = Path(cfg['data_root']);out = Path(cfg['output'])
if out.exists():
    raise ValueError('Output already exists')
for name, identity in cfg['source_hashes'].items():
    if hashlib.sha256(Path(name).read_bytes()).hexdigest() != identity:
        raise ValueError('Declared input changed: ' + name)
release = json.loads((root / cfg['release']).read_text())
old = set(pd.read_csv(cfg['old_results'], dtype={'issue': str}).issue)
issues = sorted(set(release['issues']) - old)
if len(issues) != cfg['new_issue_count']:
    raise ValueError('New scope changed')
scopes = []
for item in cfg['scopes']:
    if 'archive' in item:
        content = read_archive_members(root/item['archive'],[item['member']],expected_sha256=item['sha256'])[item['member']]
    else:
        content = (root/item['path']).read_bytes()
        if hashlib.sha256(content).hexdigest()!=item['sha256']:
            raise ValueError('Scope changed')
    scopes.append(json.loads(content))
entries = []
for path in cfg['archive_registries']:
    entries.extend(json.loads(Path(path).read_text())['entries'])
requests = defaultdict(dict);direct = {}; expected = {}; roster_bindings = {}
for scope in scopes:
    for row in scope['inventories']:
        issue = row['issue']
        if issue not in issues:
            continue
        logical = row['roster_path'];identity = scope['source_hashes'][logical]
        if issue in expected:
            if expected[issue] != identity:
                raise ValueError('Conflicting roster evidence')
            continue
        expected[issue]=identity
        if logical.startswith('data/'):
            matches=[
                e for e in entries if '/data/' in e['source'] and
                (logical == 'data/'+e['source'].split('/data/',1)[1] or logical.startswith('data/'+e['source'].split('/data/',1)[1]+'/'))]
            if len(matches)!=1:
                raise ValueError('Ambiguous or absent migrated roster: '+logical)
            e=matches[0];prefix='data/'+e['source'].split('/data/',1)[1]
            member=Path(e['source']).name+logical[len(prefix):]
            requests[(e['archive'],e['archive_sha256'])][issue]=member
            roster_bindings[issue]=dict(archive=e['archive'],archive_sha256=e['archive_sha256'],member=member,sha256=identity)
        else:
            path=(root/logical).resolve();path.relative_to(root.resolve())
            direct[issue]=path.read_bytes()
            roster_bindings[issue]=dict(path=logical,sha256=identity)
if set(expected)!=set(issues):
    raise ValueError('Missing roster scopes: '+str(set(issues)-set(expected)))
for (archive,identity), batch in requests.items():
    payloads=read_archive_members(root/archive,list(batch.values()),expected_sha256=identity)
    direct.update({i:payloads[m] for i,m in batch.items()})
for issue,raw in direct.items():
    if hashlib.sha256(raw).hexdigest()!=expected[issue]:
        raise ValueError('Roster byte mismatch: '+issue)
scope_rows, exclusion_ledger = exclude_n7_research_fixtures(
    release['rows'], cfg.get('excluded_fixtures', []), expected)
out.mkdir(parents=True);(out/'rosters').mkdir()
handicaps=[];roster_hashes={}
for issue in issues:
    path=out/'rosters'/f'{issue}.json';path.write_bytes(direct[issue]);roster_hashes[str(path)]=expected[issue]
    slots=sorted({r['slot'] for r in scope_rows if r['issue']==issue})
    if not slots:
        continue
    for row in roster_handicaps(path,issue=issue,slots=slots):
        handicaps.append(dict(issue=issue,**row))
del direct
batch_receipts=[];source_hashes={}
for start in range(0,len(issues),25):
    batch_issues=issues[start:start+25]
    market=read_n7_published_markets(data_root=root,merged_path=cfg['release'],
        expected_sha256=cfg['release_sha256'],issues=batch_issues)
    market['rows'], market['scope_exclusions'] = exclude_n7_research_fixtures(
        market['rows'], [e for e in cfg.get('excluded_fixtures', []) if e['issue'] in batch_issues], expected)
    batch_dir=out/f'batch-{start//25:03d}';batch_dir.mkdir()
    market_path=batch_dir/'published-markets.json.gz'
    market_path.write_bytes(gzip.compress(json.dumps(market,ensure_ascii=False,allow_nan=False).encode(),mtime=0))
    market_hash=hashlib.sha256(market_path.read_bytes()).hexdigest()
    (batch_dir/'handicaps.json').write_text(json.dumps(dict(rows=[h for h in handicaps if h['issue'] in batch_issues],
        roster_hashes=roster_hashes,market_snapshot_sha256=market_hash,historical_admission=False),allow_nan=False))
    source_hashes.update(market['source_hashes']);del market
    batch_receipts.append(dict(path=str(batch_dir),issues=batch_issues,market_sha256=market_hash,
        handicap_sha256=hashlib.sha256((batch_dir/'handicaps.json').read_bytes()).hexdigest()))
    print('Prepared quote batch',start//25,len(batch_issues),flush=True)
(out/'scope.json').write_text(json.dumps(dict(issues=issues,old_issues=sorted(old),all_issues=sorted(old|set(issues)),exclusions=exclusion_ledger)))
(out/'input-receipt.json').write_text(json.dumps(dict(config=cfg,config_sha256=hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(),
    source_hashes=source_hashes,roster_bindings=roster_bindings,issues=len(issues),batches=batch_receipts,
    outputs={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['scope.json']},
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope_implementation_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/'src/n7_research_scope.py').read_bytes()).hexdigest(),
    historical_admission=False),indent=2))
print('Prepared',len(issues),'issues and',len(handicaps),'roster handicap rows',flush=True)
