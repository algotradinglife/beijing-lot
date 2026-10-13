#!/usr/bin/env python3
"""Bounded company-3 corroboration of genuinely absent prior Asian/OU histories."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import time
from beidan_backend.catalog.paths import location
from beidan_backend.transport import fetch_issue_page,FetchError
from beidan_backend.market_capture.history import over_under_history_url,parse_asian_handicap_history_json,parse_over_under_history_json
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--queue',required=True);p.add_argument('--output',required=True)
a=p.parse_args();from pathlib import Path
queue=Path(a.queue);output=Path(a.output);raw=location('hot:fm17-market-recapture/20261013-company3-probe',require_exists=False);raw.mkdir(parents=True,exist_ok=True)
records=[];last=None
for f in json.loads(queue.read_bytes()):
 kickoff=datetime.fromisoformat(f['kickoff_at']);ct=datetime.fromisoformat(f['cutoff_utc'])
 url=over_under_history_url(f['provider_id_nowscore'],3,kickoff)
 if f['market']=='asian':url=url.replace('oddskind=1','oddskind=0')
 key=f['fixture_id'].replace(':','_')+'-'+f['market'];target=raw/(key+'.json')
 if target.exists():
  r=json.loads(target.read_bytes());assert r['url']==url and r['cutoff_utc']==f['cutoff_utc']
  if r.get('sha256'):assert hashlib.sha256(Path(r['raw_path']).read_bytes()).hexdigest()==r['sha256']
  records.append(r);continue
 if last is not None:time.sleep(max(0,1-(time.monotonic()-last)))
 last=time.monotonic();r=dict(fixture_id=f['fixture_id'],market=f['market'],company_id='3',url=url,cutoff_utc=f['cutoff_utc'],queue_sha256=hashlib.sha256(queue.read_bytes()).hexdigest(),state='REQUEST_FAILURE',quotes=[])
 try:
  x=fetch_issue_page(url,timeout=15,retries=1,backoff_sec=1);body=x.body
  path=raw/(key+'.raw');assert not path.exists();path.write_bytes(body)
  assert path.read_bytes()==body
  r.update(raw_path=str(path),sha256=hashlib.sha256(body).hexdigest(),observed_at=x.observed_at)
  try:
   parse=parse_asian_handicap_history_json if f['market']=='asian' else parse_over_under_history_json
   rows,counters=parse(body,kickoff_hkt=kickoff)
   r.update(state='PARSED',counters=counters)
   for row in rows:
    if not row.complete:continue
    values=(dict(handicap=row.line_value,home_decimal=1+row.odds['home'],away_decimal=1+row.odds['away']) if f['market']=='asian' else dict(line=row.line_value,over_decimal=1+row.odds['over'],under_decimal=1+row.odds['under']))
    r['quotes'].append(dict(fixture_id=f['fixture_id'],company_id='3',quote_at=row.snapshot_ts_hkt,source_url=url,raw_row_sha256=row.raw_row_sha256,**values))
  except ValueError as e:r.update(state='EMPTY_HISTORY' if str(e)=='Titan O/U history is empty' else 'PARSER_FAILURE',error=str(e))
 except FetchError as e:r.update(error=str(e),observed_at=datetime.now(timezone.utc).isoformat())
 # No cutoff selection here: shared admission in R decides temporal eligibility.
 target.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');records.append(r)
 print(key,r['state'],len(r['quotes']),flush=True)
output.write_text(json.dumps(dict(client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),queue_sha256=hashlib.sha256(queue.read_bytes()).hexdigest(),records=records),ensure_ascii=False,indent=2)+'\n')
