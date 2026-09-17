import hashlib
import json
import pytest
from src import n7_extension_labels as m


def test_freeze_before_outcomes_and_hash_failure(tmp_path, monkeypatch):
    roster=tmp_path/'roster';roster.write_text('raw');sha=hashlib.sha256(b'raw').hexdigest()
    p=tmp_path/'plan';plan=dict(status='FROZEN_REPLAYED',historical_admission=False,
      plans={k:[] for k in ['BASE','ORIGINAL','PROB','EV','PROB_CAP','EV_CAP']},
      issue='001',cutoff={'target_issue':'001'},roster_sha256=sha,
      fixtures=[dict(issue='001',slot=1,provider_id='42',handicap=-1)])
    p.write_text(json.dumps(plan));h=hashlib.sha256(p.read_bytes()).hexdigest()
    monkeypatch.setattr(m,'read_response',lambda p:({'url':'https://example.test'},''))
    monkeypatch.setattr(m,'issue_analysis_pages',lambda *a,**k:[dict(slot=1,provider_id='42',home='a',away='b')])
    monkeypatch.setattr(m,'roster_observed_results',lambda *a,**k:[dict(slot=1,actual_home=2,actual_away=0,result_state='完场')])
    assert json.loads(m.read_extension_labels(p,h,roster,sha))[0]['actual_home']==2
    with pytest.raises(ValueError,match='hash mismatch'):m.read_extension_labels(p,'bad',roster,sha)
    plan['plans'].pop('BASE');p.write_text(json.dumps(plan))
    with pytest.raises(ValueError,match='Incomplete'):m.read_extension_labels(p,hashlib.sha256(p.read_bytes()).hexdigest(),roster,sha)
