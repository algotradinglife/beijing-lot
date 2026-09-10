"""Reusable data preparation for the versioned historical expert refresh.

No scraping or implicit fitting. Chronology is delegated to temporal_learning;
all period membership is explicitly nominated by the research contract.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash, utc
from src.temporal_learning.diagnostic_labels import diagnostic_label_clock
from src.temporal_learning.predictor_clock import require_prior_predictor_clock


def read_refresh_features(prior, experiment, clean_study, *, train_count, test_count, initial_issues):
    """Read nominated frozen feature snapshots and return label-free train/test tables.

    prior is the old 32+16 study; experiment supplies its verified predictor
    clocks; clean_study is the completed new-period projection. Counts specify
    a fixed chronological research contract, not a learned partition choice.
    Raises on source drift, incomplete projections, identities or bad counts.
    Preserves per-fixture decision times; returns source hashes and full cutoffs.
    """
    prior=Path(prior);experiment=Path(experiment);clean=Path(clean_study)
    old_training=json.loads((prior/'training.json').read_text())
    old=json.loads((prior/'predictions.json').read_text())
    old_clocks=json.loads((experiment/'predictions.json').read_text())
    if stable_json_hash(old_clocks['receipt'])!=old_clocks['seal']:
        raise ValueError('Old clock receipt changed')
    if stable_json_hash(old_clocks['predictions'])!=old_clocks['receipt']['predictions_sha256']:
        raise ValueError('Old forecast snapshot changed')
    prepared=json.loads((clean/'prepared.json').read_text())
    projection=json.loads((clean/'projected/receipt.json').read_text())
    if stable_json_hash(prepared['receipt'])!=prepared['seal']:
        raise ValueError('Prepared receipt changed')
    if hashlib.sha256((clean/'prepared.json').read_bytes()).hexdigest()!=projection['prepared_sha256']:
        raise ValueError('Prepared projection binding changed')
    sources={**prepared['receipt']['source_hashes'],**prepared['receipt']['files'],
             **projection['files'],**projection['implementation']}
    # Validate the immutable old feature/clock bindings before using their rows.
    sources.update({str(prior/'training.json'):old_clocks['receipt']['source_hashes'][str(prior/'training.json')],
                    str(prior/'predictions.json'):old_clocks['receipt']['source_hashes'][str(prior/'predictions.json')]})
    for name,expected in sources.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Refresh source changed: '+name)
    issues=old_training['training_issues']+list(old['selected']['cutoffs'])+prepared['receipt']['contract']['issues']
    if len(issues)!=train_count+test_count or len(set(issues))!=len(issues) or not 1<=initial_issues<train_count:
        raise ValueError('Explicit train/CV/test issue counts do not match source scope')
    features=old_training['features'];columns=list(dict.fromkeys(['issue_code','slot','provider_id','handicap',
        'baseline_draw','baseline_cover','data_available_ts','predictor_clock_ts']+sum(features.values(),[])))
    rows=[{k:r.get(k) for k in columns} for r in old_training['data']]
    clock={(r['issue'],r['slot'],r['provider_id']):r['predictor_clock_ts'] for r in old_clocks['receipt']['clocks']}
    cuts={}
    for r in rows: cuts.setdefault(r['issue_code'],{})[str(r['slot'])]=r['data_available_ts']
    # The original full-roster CV decision epochs are retained separately below.
    cuts.update(old['selected']['cutoffs'])
    for r in old['features']:
        key=(r['issue'],r['slot'],r['provider_id'])
        item={k:r.get(k) for k in columns};item.update(issue_code=r['issue'],
            data_available_ts=cuts[r['issue']][str(r['slot'])],predictor_clock_ts=clock[key]);rows.append(item)
    for issue in prepared['receipt']['contract']['issues']:
        path=clean/'projected'/f'{issue}.json'
        if str(path) not in projection['files']:
            raise ValueError('Projection issue not bound')
        payload=json.loads(path.read_text());cuts[issue]=prepared['receipt']['cutoffs'][issue]
        if payload['cutoffs']!={issue:cuts[issue]}:
            raise ValueError('Projected fixture cutoff differs')
        for r in payload['features']:
            item={k:r.get(k) for k in columns};item.update(issue_code=issue,
                data_available_ts=cuts[issue][str(r['slot'])]);rows.append(item)
    frame=pd.DataFrame(rows)
    keys=['issue_code','slot','provider_id']
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError('Unique complete feature identities required')
    frame['issue_year']=[utc(t).year for t in frame.data_available_ts]
    train_issues=issues[:train_count];test_issues=issues[train_count:]
    decision=min(cuts[test_issues[0]].values(),key=utc)
    validation_cutoffs={i:old_training['validation_cutoffs'].get(i,min(cuts[i].values(),key=utc))
                        for i in train_issues[initial_issues:]}
    contract=dict(train_issues=train_issues,test_issues=test_issues,initial_issues=initial_issues,
        features=features,validation_cutoffs=validation_cutoffs,cutoffs=cuts,
        cutoff_issue=test_issues[0],cutoff_ts=decision,availability='HISTORICAL_PROXY_DIAGNOSTIC_ONLY',
        evaluation='RETROSPECTIVE_FIXED_HOLDOUT_ALREADY_OBSERVED_HISTORY',
        source_policy='TITAN_PRIMARY_NOWSCORE_CHECK_FILL',label_delay_hours=6,
        model_version='2.0.0',api_version='1.1.0',draw_weight_policy='CV_DEFAULT_OR_CALLER_OVERRIDE',
        high_weight=.5)
    files=[prior/'training.json',prior/'predictions.json',experiment/'predictions.json',
           clean/'prepared.json',clean/'projected/receipt.json']
    sources.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    return dict(contract=contract,train=frame.loc[frame.issue_code.isin(train_issues)].copy(),
        test=frame.loc[frame.issue_code.isin(test_issues)].copy(),source_hashes=sources,
        readiness=prepared['readiness'])


def attach_refresh_labels(features, labels, *, cutoff, label_delay_hours):
    """Join completed identity-matched labels and create shared diagnostic clocks.

    Returns admitted-ready rows and an explicit exclusion ledger. label_status
    must be COMPLETED; inconsistent IDs are excluded, duplicate issue/slots or
    feature keys fail. No imputing scores, fitting, or changing fixture cutoffs.
    Shared availability checks in fitting remain authoritative.
    """
    if not isinstance(cutoff,Cutoff):raise ValueError('Explicit fit cutoff required')
    keys=['issue_code','slot','provider_id']
    if (features[keys].isna().any().any() or labels[['issue_code','slot']].isna().any().any() or
        features.duplicated(keys).any() or labels.duplicated(['issue_code','slot']).any()):
        raise ValueError('Duplicate refresh label/feature identity')
    matched=features.merge(labels,on=keys,how='left',validate='one_to_one',indicator=True)
    admitted=[];excluded=[]
    for row in matched.to_dict('records'):
        reason=None
        if row['_merge']!='both':reason='NO_MATCHING_LABEL_IDENTITY'
        elif row['label_status']!='COMPLETED':reason=str(row['label_status'])
        elif any(pd.isna(row[k]) or not np.isfinite(row[k]) or row[k]<0 or row[k]%1 for k in ['actual_home','actual_away']):
            raise ValueError('Invalid completed score')
        elif utc(row['data_available_ts'])+pd.Timedelta(hours=label_delay_hours)>=cutoff.cutoff_ts:
            reason='LABEL_NOT_AVAILABLE_BEFORE_FIT_CUTOFF'
        if reason:
            excluded.append(dict(**{k:row[k] for k in keys},reason=reason));continue
        row['label_available_ts']=diagnostic_label_clock(row['data_available_ts'],cutoff=cutoff,delay_hours=label_delay_hours)
        net=row['actual_home']-row['actual_away']+row['handicap']
        row['draw_target']=net==0
        row['cover_target']=net*(1 if row['handicap']<0 else -1)>0
        row.pop('_merge');admitted.append(row)
    columns=list(dict.fromkeys([c for c in matched.columns if c!='_merge']+
        ['label_available_ts','draw_target','cover_target']))
    return pd.DataFrame(admitted,columns=columns),pd.DataFrame(excluded,columns=keys+['reason'])


def calibration_rows(cv, training, *, cutoff):
    """Build rate-calibration history from a single preselected policy's OOF rows.

    Rejects a multi-candidate result: tree tuning must finish before these OOF
    issues begin. Preserves actual predictor/label clocks and records missing
    expert predictions as explicit exclusions. No fitting or writes.
    """
    receipt=cv['receipt']
    if (not isinstance(cutoff,Cutoff) or receipt['cutoff_identity']!=cutoff.identity or
        receipt['cutoff_ts']!=cutoff.cutoff_ts.isoformat() or
        stable_json_hash(receipt)!=cv['seal'] or
        stable_json_hash(cv['oof'])!=receipt['oof_sha256'] or len(receipt['candidates'])!=1):
        raise ValueError('One preselected cutoff-bound OOF policy required')
    keys=['issue_code','slot','provider_id'];oof=pd.DataFrame(cv['oof'])
    fields=keys+['issue_year','data_available_ts','label_available_ts','baseline_draw','handicap']
    joined=oof.merge(training[fields],on=keys,how='left',validate='one_to_one',indicator=True)
    if not joined['_merge'].eq('both').all():
        raise ValueError('OOF training identities do not match')
    joined=joined.drop(columns='_merge')
    ready=joined.draw_signal.isin(['POSITIVE','NEGATIVE','ABSTAIN']) & joined.draw_probability.notna()
    exclusions=joined.loc[~ready,keys].assign(reason='MISSING_EXPERT_PREDICTOR')
    return joined.loc[ready].copy(),exclusions
