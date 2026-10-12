from pathlib import Path
import pytest
from beidan_backend.fundamental_probability import (
    build_goal_baseline_context, export_goal_baseline_context,
)
from beidan_backend.temporal_learning import Cutoff, AvailabilityPolicy

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = dict(fixture_id='26103:79', issue_id='26103', home='Paju', away='Busan', handicap=0)


def test_shared_summary_adapter_replay_and_future_invariance():
    rows = [dict(team=t, venue=v, matches=n, goals_for=gf, goals_against=ga,
                 row_key=t, issue_code='HISTORY', issue_year=2026,
                 label_available_ts='2026-10-08T00:00:00Z',
                 data_available_ts='2026-10-08T00:00:00Z')
            for t,v,n,gf,ga in [('Paju','home',12,10,13),('Busan','away',13,20,21)]]
    cutoff = Cutoff.decision_epoch('26103','2026-10-09T14:42:26.035423Z')
    args = (FIXTURE,cutoff,{'raw':'abc'},AvailabilityPolicy.historical_proxy('DATED_SUMMARY_DIAGNOSTIC'),
            'HISTORICAL_DIAGNOSTIC',ROOT)
    c = build_goal_baseline_context(rows,*args)
    out = export_goal_baseline_context(c,FIXTURE,ROOT)
    assert len(out['summaries']) == 2
    assert out['summaries'][0]['team'] == 'Paju'
    assert out['cutoff_epoch'] == 1791556946.035423
    target = dict(rows[0],row_key='target',issue_code='26103',goals_for=999)
    future = dict(rows[0],row_key='future',data_available_ts='2026-10-10T00:00:00Z')
    changed = build_goal_baseline_context(rows+[target,future],*args)
    assert export_goal_baseline_context(changed,FIXTURE,ROOT)['summaries'] == out['summaries']
    assert changed.receipt.payload['target_rows_excluded'] == 1
    with pytest.raises(ValueError,match='binding'):
        export_goal_baseline_context(c,dict(FIXTURE,away='Other'),ROOT)
    with pytest.raises(Exception):
        export_goal_baseline_context({},FIXTURE,ROOT)
    with pytest.raises(ValueError,match='two unique'):
        build_goal_baseline_context(rows+[dict(rows[0],row_key='duplicate')],*args)
    for bad in [None,-1,1.5,True,2147483648]:
        with pytest.raises(ValueError,match='integer'):
            build_goal_baseline_context([dict(rows[0],goals_for=bad),rows[1]],*args)
    with pytest.raises(Exception,match='prospective'):
        build_goal_baseline_context(rows,FIXTURE,cutoff,{'raw':'abc'},
            AvailabilityPolicy.historical_proxy('DATED_SUMMARY_DIAGNOSTIC'),
            'PROSPECTIVE_DECISION',ROOT)
    with pytest.raises(ValueError,match='cutoff'):
        build_goal_baseline_context(rows,FIXTURE,None,{'raw':'abc'},args[3],args[4],ROOT)
    with pytest.raises(ValueError,match='policy'):
        build_goal_baseline_context(rows,FIXTURE,cutoff,{},args[3],args[4],ROOT)


def test_shared_adjustment_evidence_admission_and_prospective_fail_closed():
    from beidan_backend.fundamental_probability import (
        build_adjustment_evidence_context, export_adjustment_evidence_context,
    )
    rows = [dict(evidence_id=k,fixture_id=FIXTURE['fixture_id'],source_hash='hash-'+k,
                 row_key=k,issue_code='H',issue_year=2026,
                 label_available_ts='2026-10-08T00:00:00Z',
                 data_available_ts='2026-10-08T00:00:00Z') for k in ['e1','e2']]
    cutoff = Cutoff.decision_epoch('26103','2026-10-09T14:42:26.035423Z')
    args = (FIXTURE,cutoff,{'raw':'abc'},AvailabilityPolicy.historical_proxy('EVIDENCE_DIAGNOSTIC'),
            'HISTORICAL_DIAGNOSTIC',ROOT)
    c = build_adjustment_evidence_context(rows,*args)
    out = export_adjustment_evidence_context(c,FIXTURE,cutoff.cutoff_ts.timestamp(),args[4],ROOT)
    assert len(out['evidence']) == 2
    future = dict(rows[1],data_available_ts='2026-10-10T00:00:00Z')
    changed = build_adjustment_evidence_context([rows[0],future],*args)
    assert [r['evidence_id'] for r in export_adjustment_evidence_context(
        changed,FIXTURE,cutoff.cutoff_ts.timestamp(),args[4],ROOT)['evidence']] == ['e1']
    with pytest.raises(ValueError,match='availability'):
        export_adjustment_evidence_context(c,FIXTURE,cutoff.cutoff_ts.timestamp(),
                                          'PROSPECTIVE_DECISION',ROOT)
    with pytest.raises(ValueError,match='binding'):
        export_adjustment_evidence_context(c,FIXTURE,cutoff.cutoff_ts.timestamp()+1,args[4],ROOT)
    with pytest.raises(ValueError,match='Unique'):
        build_adjustment_evidence_context(rows+[dict(rows[0],row_key='other')],*args)
    observed = build_adjustment_evidence_context(rows,FIXTURE,cutoff,{'raw':'abc'},
        AvailabilityPolicy.observed('RECORDED_RELEASE'), 'HISTORICAL_DIAGNOSTIC',ROOT)
    assert len(export_adjustment_evidence_context(observed,FIXTURE,cutoff.cutoff_ts.timestamp(),
        'HISTORICAL_DIAGNOSTIC',ROOT)['evidence']) == 2
    prospective = build_adjustment_evidence_context(rows,FIXTURE,cutoff,{'raw':'abc'},
        AvailabilityPolicy.observed('RECORDED_RELEASE'),'PROSPECTIVE_DECISION',ROOT)
    exported = export_adjustment_evidence_context(prospective,FIXTURE,
        cutoff.cutoff_ts.timestamp(),'PROSPECTIVE_DECISION',ROOT)
    assert len(exported['evidence']) == 2
    assert exported['receipt']['partition_policy']['kind'] == 'OBSERVED_PRIOR_FIT'
    future_observed = build_adjustment_evidence_context([rows[0],future],FIXTURE,cutoff,
        {'raw':'changed'},AvailabilityPolicy.observed('RECORDED_RELEASE'),
        'PROSPECTIVE_DECISION',ROOT)
    assert len(export_adjustment_evidence_context(future_observed,FIXTURE,
        cutoff.cutoff_ts.timestamp(),'PROSPECTIVE_DECISION',ROOT)['evidence']) == 1
    with pytest.raises(ValueError,match='schema'):
        build_adjustment_evidence_context([dict(r,source_hash=None) for r in rows],*args)
