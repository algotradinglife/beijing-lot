"""Offline PA orchestration contracts: no provider requests or target outcomes."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/fm15_26102_pa.py'

@pytest.fixture
def setup_run(tmp_path):
    out=tmp_path/'results/fm15-26102-20261012';out.mkdir(parents=True)
    packets=[dict(fixture_id=f'26102:{i}',base_hash=f'{i:064x}',cutoff_utc='2026-10-01T00:00:00Z',home='H',away='A',competition='SYNTHETIC_ONLY',native_parameters=[],native_rates=[],top_margins=[],independent_market=None,total_constraint=None,asian_quotes=[],total_quotes=[],missing={'lineups':'missing'}) for i in range(1,87)]
    (out/'review-inputs.json').write_text(json.dumps({'fixtures':packets}))
    caller=tmp_path/'fake_caller.py'
    caller.write_text('''import sys,json,hashlib,argparse
from pathlib import Path
p=argparse.ArgumentParser()
for k in ('prompt-file','cwd','output-dir','timeout','model'):p.add_argument('--'+k,required=True)
a=p.parse_args();work=Path(a.cwd);out=Path(a.output_dir);out.mkdir();mode=(work.parents[2]/'mode.txt').read_text()
r={'exit_code':1 if mode=='provider_failure' else 0,'timed_out':False,'model':a.model,'cwd':str(work),'prompt_sha256':hashlib.sha256(Path(a.prompt_file).read_bytes()).hexdigest()}
if mode=='wrong_model':r['model']='UNAUTHORIZED_PROVIDER'
if mode=='wrong_cwd':r['cwd']=str(work.parent)
if mode=='bad_prompt_hash':r['prompt_sha256']='bad'
(out/'receipt.json').write_text(json.dumps(r));(out/'stdout.txt').write_text('synthetic');(out/'stderr.txt').write_text('synthetic')
rows=[]
for x in json.loads((work/'input.json').read_text()):
 y={k:x[k] for k in ('fixture_id','cutoff_utc','base_hash')};y.update(decision='apply',market_action='KEEP_NATIVE',reason='Synthetic',counterevidence='Synthetic',market_review='Synthetic',evidence_ids=['native_rates'])
 if mode=='bad_base':y['base_hash']='bad'
 if mode=='bad_decision':y['decision']='unsupported'
 if mode=='bad_shift':y['market_action']='UNIDENTIFIED_SHIFT'
 if mode=='bad_evidence':y['evidence_ids']=['target_score']
 rows.append(y)
if mode!='missing_output':(work/'reviews.json').write_text(json.dumps(rows))
''')
    return tmp_path,out,caller

def test_worker_reuse_is_offline_and_selections_bind_inputs(setup_run):
    root,out,caller=setup_run;(root/'mode.txt').write_text('normal')
    cmd=[sys.executable,str(SCRIPT),str(root),'0',str(caller)]
    first=subprocess.run(cmd,capture_output=True,text=True);assert first.returncode==0,first.stderr
    selections=list(out.glob('pa-selection-*.json'));assert len(selections)==15
    before={p.name:p.read_bytes() for p in selections}
    (root/'mode.txt').write_text('provider_failure')
    second=subprocess.run(cmd,capture_output=True,text=True);assert second.returncode==0,second.stderr
    assert before=={p.name:p.read_bytes() for p in selections}
    assert len(list(out.glob('pa-call-*')))==15
    assert all(json.loads(p.read_text())['input_sha256'] for p in selections)

@pytest.mark.parametrize('mode',['provider_failure','wrong_model','wrong_cwd','bad_prompt_hash','bad_base','bad_decision','bad_shift','bad_evidence','missing_output'])
def test_invalid_receipts_or_review_bindings_fail_closed(setup_run,mode):
    root,out,caller=setup_run;(root/'mode.txt').write_text(mode)
    run=subprocess.run([sys.executable,str(SCRIPT),str(root),'0',str(caller)],capture_output=True,text=True)
    assert run.returncode!=0
    assert not list(out.glob('pa-selection-*.json'))
    assert len(list(out.glob('pa-call-*')))==1
    assert (out/'pa-call-01/receipt.json').is_file()

def test_explicit_remaining_batch_range_preserves_earlier_attempts(setup_run):
    root,out,caller=setup_run;(root/'mode.txt').write_text('normal')
    run=subprocess.run([sys.executable,str(SCRIPT),str(root),'1',str(caller),'11'],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    selected=sorted(int(p.stem.rsplit('-',1)[1]) for p in out.glob('pa-selection-*.json'))
    assert selected==list(range(11,44,3))
    assert not (out/'pa-work-02').exists()

@pytest.mark.parametrize('minimum',['0','44'])
def test_invalid_remaining_range_fails_before_call(setup_run,minimum):
    root,out,caller=setup_run;(root/'mode.txt').write_text('normal')
    run=subprocess.run([sys.executable,str(SCRIPT),str(root),'1',str(caller),minimum],capture_output=True,text=True)
    assert run.returncode!=0
    assert not list(out.glob('pa-call-*'))
