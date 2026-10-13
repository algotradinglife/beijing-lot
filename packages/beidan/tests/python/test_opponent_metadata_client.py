"""Offline entry-point integration: exact hashes, no cache mutation, replay."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from test_unified_sources import saved_pair

ROOT=Path(__file__).resolve().parents[4]


def test_offline_metadata_entrypoint_is_idempotent_and_records_missing_clock(tmp_path):
    pages,_,identity=saved_pair()
    hot=tmp_path/'hot';(hot/'source-extraction').mkdir(parents=True)
    db=hot/'source-extraction/raw.sqlite'
    provenance=[]
    with sqlite3.connect(db) as con:
        con.execute('create table captures(source text,url text,observed_at text,sha256 text,body blob)')
        for url,p in pages.items():
            source='titan' if 'titan' in url else 'nowscore'
            sha=hashlib.sha256(p['body']).hexdigest()
            con.execute('insert into captures values(?,?,?,?,?)',(source,url,p['observed_at'],sha,p['body']))
            provenance.append(dict(fixture_id='20064:293',source=source,url=url,sha256=sha,observed_at=p['observed_at']))
    fixtures=[dict(fixture_id='20064:293',**identity),dict(fixture_id='20064:294',**{**identity,'kickoff_utc':None})]
    missing=[{**p,'fixture_id':'20064:294'} for p in provenance]
    inp=tmp_path/'input.json';inp.write_text(json.dumps(dict(fixtures=fixtures,provenance=provenance+missing)))
    env={**os.environ,'BEIDAN_HOT_ROOT':str(hot),'PYTHONPATH':str(ROOT/'packages/beidan/inst/python')}
    command=[sys.executable,str(ROOT/'scripts/replay_fm17_opponent_metadata.py'),'--input',str(inp),'--output',str(tmp_path/'out')]
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    subprocess.run(command,cwd=ROOT,env=env,check=True,capture_output=True)
    result=json.loads((tmp_path/'out/metadata.json').read_bytes())
    assert len(result['parsed'])==2
    assert sum(r['state']=='MISSING_FROZEN_CLOCK' for r in result['ledger'])==2
    assert result['network_attempts']==0
    assert result['input_sha256']==hashlib.sha256(inp.read_bytes()).hexdigest()
    first=(tmp_path/'out/metadata.json').read_bytes()
    subprocess.run(command,cwd=ROOT,env=env,check=True,capture_output=True)
    assert first==(tmp_path/'out/metadata.json').read_bytes()
    assert before==hashlib.sha256(db.read_bytes()).hexdigest()
    bad=subprocess.run(command+['--fixture','unknown'],cwd=ROOT,env=env,capture_output=True)
    assert bad.returncode!=0 and b'Unknown requested fixture' in bad.stderr
