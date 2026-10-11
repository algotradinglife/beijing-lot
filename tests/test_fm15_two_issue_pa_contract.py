"""Offline orchestration contract checks; no provider calls or settlement files."""
import json
import subprocess
from pathlib import Path
import sys
import pytest
import ast
import hashlib


@pytest.mark.parametrize('mutation', ['valid','hash','decision','evidence','shift'])
def test_saved_pa_review_is_validated_without_network(tmp_path,mutation):
    root=tmp_path
    out=root/'results/fm15-two-issues-20261012'
    work=out/'review-work-01';call=out/'review-call-01'
    work.mkdir(parents=True);call.mkdir()
    packet=dict(fixture_id='26098:1',cutoff_utc='2026-09-24T05:00:00Z',base_hash='frozen-grid',home='H',away='A',competition='TEST',native_parameters={},native_rates=[{'role':'home'},{'role':'away'}],top_margins=[{'margin':0}],independent_market=[],asian_quotes=[],total_quotes=[],euro_quotes=[],article_facts=[],missing={'injuries':True})
    (out/'review-inputs.json').write_text(json.dumps({'fixtures':[packet]}))
    (work/'input.json').write_text(json.dumps({'fixtures':[packet]},ensure_ascii=False,indent=2))
    receipt=dict(exit_code=0,timed_out=False,model='opencode/deepseek-v4.1-flash')
    (call/'receipt.json').write_text(json.dumps(receipt))
    row={k:packet[k] for k in ('fixture_id','cutoff_utc','base_hash')}
    row.update(decision='apply',market_action='KEEP_NATIVE',reason='prior attack and defence',counterevidence='missing injuries',market_review='no new evidence',evidence_ids=['native_rates'])
    if mutation=='hash':row['base_hash']='changed'
    if mutation=='decision':row['decision']='invented'
    if mutation=='evidence':row['evidence_ids']=['unavailable:fact']
    if mutation=='shift':row['market_action']='UNIDENTIFIED_SHIFT'
    (work/'reviews.json').write_text(json.dumps([row]))
    script=Path(__file__).resolve().parents[1]/'scripts/fm15_two_issue_pa.py'
    result=subprocess.run([sys.executable,str(script),str(root),'0'],capture_output=True,text=True,timeout=10)
    assert (result.returncode==0)==(mutation=='valid')
    assert (out/'pa-selection-01.json').exists()==(mutation=='valid')


@pytest.mark.parametrize('bad_identity',[False,True])
def test_single_review_split_is_offline_and_preserves_all_receipts(tmp_path,bad_identity):
    out=tmp_path/'results/fm15-two-issues-20261012'
    (out/'review-call-01-summary').mkdir(parents=True)
    (out/'review-call-01-summary/stdout.txt').write_text('reached a model token limit')
    (out/'review-work-01').mkdir()
    script=Path(__file__).resolve().parents[1]/'scripts/fm15_review_first_batch.py'
    tree=ast.parse(script.read_text())
    prompt=next(n.args[0].value for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='write_text' and n.args and isinstance(n.args[0],ast.Constant) and str(n.args[0].value).startswith('FM-1.5.0单场'))
    sha=hashlib.sha256(prompt.encode()).hexdigest()
    packets=[]
    for i in range(1,7):
        p=dict(fixture_id=f'26098:{i}',cutoff_utc='2026-09-24T05:00:00Z',base_hash='grid',article_facts=[])
        packets.append(p)
        work=out/f'single-work-01-{i}';call=out/f'single-call-01-{i}'
        work.mkdir();call.mkdir()
        receipt=dict(exit_code=0,timed_out=False,prompt_sha256=sha)
        (call/'receipt.json').write_text(json.dumps(receipt))
        row={k:p[k] for k in ('fixture_id','cutoff_utc','base_hash')}
        row.update(decision='apply',market_action='KEEP_NATIVE',reason='rates',counterevidence='missing',market_review='no new evidence',evidence_ids=['native_rates'])
        if bad_identity and i==1:row['fixture_id']='future:1'
        (work/'review.json').write_text(json.dumps(row))
    (out/'review-inputs.json').write_text(json.dumps({'fixtures':packets}))
    result=subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True,text=True,timeout=10)
    assert (result.returncode==0)==(not bad_identity)
    if not bad_identity:
        selection=json.loads((out/'pa-selection-01.json').read_text())
        assert len(selection['call_paths'])==6
        assert len(json.loads((out/'review-work-01/reviews.json').read_text()))==6
        assert (out/'prompt-receipts'/f'{sha}.txt').read_text()==prompt
    else:
        assert not (out/'pa-selection-01.json').exists()


@pytest.mark.parametrize('mode',['reconstruct','missing','tampered_archive'])
def test_prompt_receipt_binding_uses_exact_bytes(tmp_path,mode):
    out=tmp_path/'results/fm15-two-issues-20261012'
    call=out/'review-call-01';call.mkdir(parents=True)
    original='FM-1.5.0 original frozen contract'
    sha=hashlib.sha256(original.encode()).hexdigest()
    (call/'receipt.json').write_text(json.dumps({'prompt_sha256':sha}))
    (out/'review-prompt-01.txt').write_text(original+'\n额外允许读summary.txt supplemental instructions')
    if mode=='missing':
        (call/'receipt.json').write_text(json.dumps({'prompt_sha256':'missing'}))
    if mode=='tampered_archive':
        archive=out/'prompt-receipts';archive.mkdir()
        (archive/(sha+'.txt')).write_text('changed prompt')
    script=Path(__file__).resolve().parents[1]/'scripts/fm15_bind_pa_prompts.py'
    result=subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True,text=True,timeout=10)
    assert (result.returncode==0)==(mode=='reconstruct')
    if mode=='reconstruct':
        assert (out/'prompt-receipts'/(sha+'.txt')).read_text()==original
        inventory=json.loads((out/'prompt-inventory.json').read_text())
        assert len(inventory)==1 and inventory[0]['sha256']==sha
