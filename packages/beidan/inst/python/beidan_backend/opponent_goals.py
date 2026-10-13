"""Domain preparation for opponent-normalized Poisson attack/defence research.

Every admission, partition, recent mass, ESS and implementation receipt comes
from shared temporal_learning. R owns the statistical fit through glmnet.
"""
from pathlib import Path
from dataclasses import asdict
import hashlib
import pandas as pd
from .temporal_learning import (Cutoff, AvailabilityFilter, AvailabilityPolicy,
    PartitionPolicy, WeightingPolicy, prepare_learning_context)
from .temporal_learning.context_replay import verify_learning_context
from .temporal_learning.core import stable_json_hash


def prepare_opponent_goals(rows, fixture, excluded_native_ids, cutoff,
                           source_hashes, repository_root, policy):
    """Return prior goal observations, per-team venue weights and full receipts.

    rows: unique row_key per source fixture/scope/match, date-only factual scores,
    competition_id and boolean neutral_reported. excluded_native_ids is the
    full target/future roster, including deliberately bad early dates. Original
    date+1 UTC availability is diagnostic only. Duplicate prior match copies
    must agree on every fitting fact; contradictions fail closed. Rows with no
    competition metadata must be explicitly removed by the caller and counted.
    policy: recent_n, alpha, minimum_recent_matches, minimum_recent_ess;
    sparse team/venue groups use the shared expanding-equal long prior.
    Return contexts alongside their receipts, making independent verification
    possible before R fits. No fitting, file writes or market inputs.
    """
    if (not isinstance(cutoff,Cutoff) or cutoff.kind!='DECISION_EPOCH'
            or fixture.get('issue_id')!=cutoff.target_issue
            or not excluded_native_ids or fixture.get('provider_id') not in excluded_native_ids
            or len(excluded_native_ids)!=len(set(excluded_native_ids)) or not source_hashes):
        raise ValueError('Explicit bound cutoff and complete target/future roster required')
    if (set(policy)!={'recent_n','alpha','minimum_recent_matches','minimum_recent_ess'}
            or type(policy['recent_n']) is not int or policy['recent_n']<1
            or type(policy['minimum_recent_matches']) is not int
            or policy['minimum_recent_matches']<policy['recent_n']
            or not 0<policy['alpha']<1 or policy['minimum_recent_ess']<=0):
        raise ValueError('Explicit valid opponent recent policy required')
    frame=pd.DataFrame(rows)
    facts=['match_id','event_date','home_id','away_id','home_score','away_score',
           'score_scope','competition_id','neutral_reported']
    if frame.empty or not set(facts+['row_key'])<=set(frame) or frame.row_key.duplicated().any():
        raise ValueError('Nonempty unique factual rows required')
    dates=pd.to_datetime(frame.event_date,format='%Y-%m-%d',utc=True,errors='raise')
    frame['label_available_ts']=dates+pd.Timedelta(days=1)
    frame['data_available_ts']=frame.label_available_ts
    frame['event_order_ts']=dates
    frame['issue_year']=dates.dt.year
    frame['issue_code']=frame.match_id.map(lambda m:cutoff.target_issue if m in excluded_native_ids else 'MATCH:'+m)
    root=Path(repository_root)
    bindings={**source_hashes,'input_rows':stable_json_hash(rows),'fixture':stable_json_hash(fixture),
              'excluded_roster':stable_json_hash(sorted(excluded_native_ids)),
              'policy':stable_json_hash(policy),
              'R_fit':hashlib.sha256((root/'packages/beidan/R/opponent_goals.R').read_bytes()).hexdigest()}
    availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy(
        'DATE_PLUS_ONE_UTC_OPPONENT_NETWORK_DIAGNOSTIC'),data_available_column='data_available_ts')
    admission=prepare_learning_context(frame,cutoff,source_hashes=bindings,repository_root=root,
        implementation_modules=('beidan_backend.opponent_goals',),
        implementation_distributions=('pandas','numpy'),availability=availability,
        intended_use='HISTORICAL_DIAGNOSTIC',partition_policy=PartitionPolicy('FIXED_PRIOR_FIT',0,0,1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=1))
    verify_learning_context(admission,repository_root=root)
    prior=admission.partitions['fit']
    if prior[facts].isna().any().any():raise ValueError('Prior fitting facts cannot be missing')
    for col in ['match_id','home_id','away_id','competition_id','score_scope']:
        if not prior[col].map(lambda x:isinstance(x,str) and bool(x)).all():
            raise ValueError('Nonempty character factual identities required')
    for col in ['home_score','away_score']:
        if not prior[col].map(lambda x:not isinstance(x,bool) and isinstance(x,(int,float))
                              and float(x).is_integer() and 0<=x<=2147483647).all():
            raise ValueError('Nonnegative integer scores required')
    if not prior.neutral_reported.map(lambda x:type(x)is bool).all():
        raise ValueError('Boolean neutral source marker required')
    if prior.home_id.eq(prior.away_id).any():raise ValueError('Distinct oriented team identities required')
    if (prior.groupby('match_id')[facts].nunique(dropna=False)>1).any().any():
        raise ValueError('Conflicting prior match copies require adjudication')
    if not isinstance(fixture.get('competition_id'),str) or not fixture['competition_id']:
        raise ValueError('Explicit target competition identity required')
    prior=prior[prior.competition_id.eq(fixture['competition_id'])]
    if prior.empty:raise ValueError('No prior target-competition network')
    unique=prior.sort_values(['match_id','row_key'],kind='stable').drop_duplicates('match_id').reset_index(drop=True)
    # One scoring observation per team per match. Venue grouping is native input.
    observations=[]
    for side,own,opponent,goals,against in [('home','home_id','away_id','home_score','away_score'),
                                           ('away','away_id','home_id','away_score','home_score')]:
        f=unique.copy();f['team_id']=f[own];f['opponent_id']=f[opponent]
        f['goals']=f[goals];f['against']=f[against]
        f['venue']=f.neutral_reported.map(lambda n:'neutral' if n else side)
        f['home_indicator']=f.neutral_reported.map(lambda n:.5 if n else float(side=='home'))
        f['row_key']=f.match_id+':'+side
        observations.append(f)
    goals=pd.concat(observations,ignore_index=True).sort_values(['team_id','venue','event_order_ts','match_id'],kind='stable')
    contexts=[];weighted=[];support=[]
    for (team,venue),group in goals.groupby(['team_id','venue'],sort=True):
        recent=len(group)>=policy['minimum_recent_matches']
        wp=(WeightingPolicy.recent_state_blend(policy['recent_n'],policy['alpha'],
               minimum_ess=policy['minimum_recent_ess'],recent_order_column='event_order_ts')
            if recent else WeightingPolicy.expanding_equal(minimum_ess=1))
        ctx=prepare_learning_context(group,cutoff,source_hashes={**bindings,
            'admission':stable_json_hash(admission.receipt.payload),'group':stable_json_hash([team,venue])},
            repository_root=root,implementation_modules=('beidan_backend.opponent_goals',),
            implementation_distributions=('pandas','numpy'),availability=availability,
            intended_use='HISTORICAL_DIAGNOSTIC',partition_policy=PartitionPolicy('FIXED_PRIOR_FIT',0,0,1),
            weighting_policy=wp)
        verify_learning_context(ctx,repository_root=root)
        fit=ctx.partitions['fit'].copy();ledger=ctx.weight_ledger
        fit['weight']=ledger.weight.to_numpy()
        fit['long_mass']=ledger.long_mass.to_numpy();fit['recent_mass']=ledger.recent_mass.to_numpy()
        weighted.append(fit)
        contexts.append(ctx)
        support.append(dict(team_id=team,venue=venue,matches=len(fit),recent_active=recent,
            ess=ctx.receipt.payload['weight_receipt']['effective_sample_size']))
    combined=pd.concat(weighted,ignore_index=True)
    ledgers=[dict(team_id=ctx.partitions['fit'].team_id.iloc[0],
        venue=ctx.partitions['fit'].venue.iloc[0],
        ledger=ctx.weight_ledger.assign(row_key=ctx.partitions['fit'].row_key.to_numpy())
          .to_json(orient='records',date_format='iso',double_precision=15)) for ctx in contexts]
    return dict(observations=combined[['row_key','match_id','event_date','team_id','opponent_id',
        'goals','against','competition_id','venue','home_indicator','weight','long_mass','recent_mass']].to_dict('records'),
        support=support,admission=admission,contexts=contexts,receipts=[c.receipt.payload for c in contexts],ledgers=ledgers,
        admitted_matches=len(unique),admitted_rows=len(prior),duplicates_removed=len(prior)-len(unique),
        policy=policy,cutoff=cutoff.cutoff_ts.isoformat())


def verify_opponent_preparation(prepared, fixture, cutoff, repository_root):
    """Independently bind exported domain observations to verified shared fits.

    Verifies all contexts with shared replay and reconciles the R boundary rows,
    venue support and full ledger exports. Mutated observations, wrong fixture,
    cutoff, receipts or R implementation fail. No fitting or side effects.
    """
    root=Path(repository_root)
    admission=verify_learning_context(prepared['admission'],repository_root=root)
    expected=admission.receipt.payload['source_hashes']
    if (not isinstance(cutoff,Cutoff) or admission.cutoff!=cutoff
            or prepared['cutoff']!=cutoff.cutoff_ts.isoformat()
            or expected.get('fixture')!=stable_json_hash(fixture)
            or expected.get('policy')!=stable_json_hash(prepared['policy'])
            or expected.get('R_fit')!=hashlib.sha256((root/'packages/beidan/R/opponent_goals.R').read_bytes()).hexdigest()):
        raise ValueError('Prepared fixture/cutoff/policy/implementation differs')
    rows=[];support=[];receipts=[];ledgers=[]
    for context in prepared['contexts']:
        verify_learning_context(context,repository_root=root)
        if context.cutoff!=cutoff or context.receipt.payload['source_hashes'].get('admission')!=stable_json_hash(admission.receipt.payload):
            raise ValueError('Group cutoff/admission differs')
        fit=context.partitions['fit'].copy();ledger=context.weight_ledger
        team=fit.team_id.iloc[0];venue=fit.venue.iloc[0]
        policy=prepared['policy']
        expected_weighting=(WeightingPolicy.recent_state_blend(policy['recent_n'],policy['alpha'],
            minimum_ess=policy['minimum_recent_ess'],recent_order_column='event_order_ts')
            if len(fit)>=policy['minimum_recent_matches'] else WeightingPolicy.expanding_equal(minimum_ess=1))
        if (context.receipt.payload['weight_receipt']['policy']!=asdict(expected_weighting)
                or context.receipt.payload['source_hashes'].get('group')!=stable_json_hash([team,venue])
                or context.receipt.payload['source_hashes'].get('fixture')!=expected['fixture']
                or not fit.team_id.eq(team).all() or not fit.venue.eq(venue).all()):
            raise ValueError('Group weighting policy or identity differs')
        fit['weight']=ledger.weight.to_numpy()
        fit['long_mass']=ledger.long_mass.to_numpy();fit['recent_mass']=ledger.recent_mass.to_numpy()
        rows.extend(fit[['row_key','match_id','event_date','team_id','opponent_id',
            'goals','against','competition_id','venue','home_indicator','weight','long_mass','recent_mass']].to_dict('records'))
        support.append(dict(team_id=team,venue=venue,matches=len(fit),
            recent_active=context.receipt.payload['weight_receipt']['policy']['kind']=='RECENT_STATE_BLEND',
            ess=context.receipt.payload['weight_receipt']['effective_sample_size']))
        receipts.append(context.receipt.payload)
        ledgers.append(dict(team_id=team,venue=venue,ledger=ledger.assign(row_key=fit.row_key.to_numpy()).to_json(orient='records',date_format='iso',double_precision=15)))
    if any(prepared[k]!=v for k,v in [('observations',rows),('support',support),('receipts',receipts),('ledgers',ledgers)]):
        raise ValueError('Exported opponent preparation differs from shared contexts')
    # An independently valid context must still describe the admitted football
    # facts, not fabricated rows with an unchanged source-binding string.
    prior=admission.partitions['fit']
    unique=prior[prior.competition_id.eq(fixture['competition_id'])].sort_values(
        ['match_id','row_key'],kind='stable').drop_duplicates('match_id')
    lookup=unique.set_index('match_id')
    factual_keys=[]
    for row in rows:
        side=row['row_key'].rsplit(':',1)[-1]
        if side not in ('home','away') or row['match_id'] not in lookup.index:
            raise ValueError('Group rows differ from admitted source facts')
        fact=lookup.loc[row['match_id']]
        opponent='away' if side=='home' else 'home'
        values=dict(match_id=str(fact.name),event_date=fact.event_date,team_id=fact[side+'_id'],
            opponent_id=fact[opponent+'_id'],goals=fact[side+'_score'],against=fact[opponent+'_score'],
            competition_id=fact.competition_id,venue='neutral' if fact.neutral_reported else side,
            home_indicator=.5 if fact.neutral_reported else float(side=='home'))
        if any(row[k]!=v for k,v in values.items()):
            raise ValueError('Group rows differ from admitted source facts')
        factual_keys.append(row['row_key'])
    expected_keys={m+':'+side for m in unique.match_id for side in ('home','away')}
    if len(factual_keys)!=len(expected_keys) or set(factual_keys)!=expected_keys:
        raise ValueError('Incomplete or duplicate admitted scoring groups')
    return prepared
