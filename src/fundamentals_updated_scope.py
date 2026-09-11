"""Fixed-policy adapters for accepted whole-scope historical diagnostic batches."""
import copy
from pathlib import Path
from src.temporal_learning import Cutoff
from src.temporal_learning.core import utc, stable_json_hash
from src.fundamentals_clean_validation import clean_validation_forms, validation_predictor_clocks
from src.fundamentals_census import read_response
from src.fundamentals_issue_pages import issue_analysis_pages
from src.fundamentals_roster_handicap import roster_handicaps
from src.fundamentals_candidate_exclusion import exclude_zero_top2_disagreement
from src.fundamentals_consensus_portfolio import consensus_portfolios, independent_consensus_portfolio
from src.fundamentals_double_source import paired_double_source
from src.fundamentals_reuse_random import random_reuse_plan
from src.fundamentals_missed_portfolio import flatten_component_groups, fixed_n67_wallets


def audited_scope_market(fixtures, records, *, cutoffs, source_hashes):
    """Adapt already adjudicated Euro/OU company rows, never reparse raw pages.

    Exact fixture/market keys and native Cutoffs required. Invalid chronology,
    duplicates or inconsistent eligibility fail; unavailable markets remain
    explicit. Return existing projection input schema, with original receipts.
    Decimal Euro odds are averaged equally across selected companies. No I/O.
    """
    expected={(f['issue'],f['slot'],f['provider_id'],m) for f in fixtures for m in ('euro','total')}
    index={(r['issue'],r['slot'],r['provider_id'],r['market']):r for r in records}
    if len(index)!=len(records) or set(index)!=expected or not source_hashes:
        raise ValueError('Exact audited market identities and sources required')
    if set(cutoffs)!={str(f['slot']) for f in fixtures}:raise ValueError('Exact cutoffs required')
    rows=[];selected=[];receipts=[]
    for f in fixtures:
        issue,slot,pid=f['issue'],f['slot'],f['provider_id'];cut=cutoffs[str(slot)]
        if not isinstance(cut,Cutoff) or cut.target_issue!=issue:raise ValueError('Native cutoff identity mismatch')
        pair=[index[issue,slot,pid,m] for m in ('euro','total')]
        for r in pair:
            if utc(r['cutoff_utc'])!=cut.cutoff_ts or r['historical_admission'] is not False:
                raise ValueError('Audited market cutoff mismatch')
            ready=r['status']=='QUOTES_PRIOR_DIAGNOSTIC'
            if ready != bool(r['rows']) or r['prior_companies']!=len(r['rows']):
                raise ValueError('Audited company/status mismatch')
            if len({q['company'] for q in r['rows']})!=len(r['rows']):raise ValueError('Duplicate company')
            if any(utc(q['quoted_at'])>=cut.cutoff_ts for q in r['rows']):raise ValueError('Post-cutoff quote')
        row=dict(issue=issue,slot=slot,provider_id=pid,cutoff_utc=cut.cutoff_ts.isoformat(),
                 status='READY' if all(r['status']=='QUOTES_PRIOR_DIAGNOSTIC' for r in pair) else 'AUDITED_MARKET_UNAVAILABLE',
                 euro_status=pair[0]['status'],total_status=pair[1]['status'])
        if row['status']=='READY':
            for k in ('odds_W','odds_D','odds_L'):row[k]=sum(q[k] for q in pair[0]['rows'])/len(pair[0]['rows'])
            selected.extend(dict(q,issue=issue,slot=slot,provider_id=pid) for q in pair[1]['rows'])
            receipts.append(dict(issue=issue,slot=slot,provider_id=pid,euro=pair[0],total=pair[1],source_hashes=source_hashes))
        rows.append(row)
    return dict(rows=rows,selected=selected,receipts=receipts,
                cutoffs={s:c.cutoff_ts.isoformat() for s,c in cutoffs.items()},historical_admission=False)


def prepare_updated_issue(report, records, inventory, *, cutoffs, source_hashes, repository_root, window, minimum):
    """Read the bound roster; reuse authoritative history windows and clocks.

    Inputs are verified analysis/market snapshots and scope inventory. Returns
    existing R projection schema. Preserve all declared slots and exclusion
    reasons; ineligible analysis never supplies model histories. No writes,
    scraping, settlement extraction, tuning or expert inference.
    """
    issue=inventory['issue'];clean=copy.deepcopy(report['clean'])
    stamps={s:c.cutoff_ts.isoformat() for s,c in cutoffs.items()}
    if report['issue']!=issue or clean['cutoffs']!=stamps or inventory['cutoffs']!=stamps:
        raise ValueError('Analysis scope cutoff mismatch')
    meta,raw=read_response(Path(inventory['roster_path']))
    slots=list(map(int,stamps))
    fixtures=issue_analysis_pages(raw,roster_url=meta['url'],issue=issue,slots=slots)
    bases={f['slot']:f for f in clean['integrated_fixtures']}
    if len(bases)!=len(fixtures) or set(bases)!=set(slots):raise ValueError('Analysis fixture coverage')
    eligible=set()
    for f in fixtures:
        b=bases[f['slot']]
        if (b['issue'],b['provider_id'])!=(issue,f['provider_id']):raise ValueError('Analysis identity mismatch')
        if b['integration_eligible'] and b['original_roster_status']!='完场':raise ValueError('Invalid completed eligibility')
        if b['integration_eligible']:eligible.add(f['slot'])
    clean['integrated_history']=[h for h in clean['integrated_history'] if h['slot'] in eligible]
    h=roster_handicaps(inventory['roster_path'],issue=issue,slots=slots)
    forms=clean_validation_forms(dict(clean=clean,fixtures=fixtures),h,cutoffs=stamps,window=window,minimum=minimum,
                                 source_hashes=source_hashes,repository_root=repository_root)
    for w in forms['windows']:
        if w['slot'] not in eligible:w['status']='ANALYSIS_EXCLUDED:'+bases[w['slot']]['exclusion_reason']
    market=audited_scope_market(fixtures,records,cutoffs=cutoffs,source_hashes=source_hashes)
    clocks=validation_predictor_clocks(forms['context'],market,cutoffs=stamps)
    return dict(issue=issue,cutoffs=stamps,handicaps=h,forms=forms,market=market,clocks=clocks,roster_path=inventory['roster_path'])


def updated_strategy_plans(frame, *, cutoffs, seeds, budget_cny, unit_cny, payout_factor):
    """Reuse frozen N5/N6/N7 policies and equal-wallet mix on a new issue.

    Native cutoffs, integer CNY1024/2, one .65 factor and explicit unique seeds
    are required. Single swaps affect repeated positions only; doubles unchanged.
    Returns 4 deterministic plus 4*len(seeds) sealed plans and exclusion ledger.
    No labels, fitting or I/O. Empty post-filter pools fail through the existing
    exclusion contract; insufficient role pools produce cash-only plans.
    """
    if (budget_cny,unit_cny,payout_factor)!=(1024,2,.65) or not seeds or len(set(seeds))!=len(seeds) or any(type(s) is not int for s in seeds):
        raise ValueError('Explicit constants and seeds required')
    current,excluded=exclude_zero_top2_disagreement(frame,cutoffs=cutoffs)
    cuts={str(s):cutoffs[str(s)] for s in current.slot}
    constants=dict(budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor)
    plans={}
    for n in (5,6):
        b=independent_consensus_portfolio(current,cutoffs=cuts,group_size=n,minimum_anchor_market=.5,
            max_uses=budget_cny//(unit_cny*2**(n-2)),max_pair_overlap=n-1,seed=0,conversion_budget_fraction=0,**constants)
        b.pop('seal');b['double_source']='BASELINE';b['seal']=stable_json_hash(b);plans[f'N{n}_NO_SWAP']=b
    u3=consensus_portfolios(current,cutoffs=cuts,minimum_anchor_market=.5,skeleton_max_uses=3,
        skeleton_pair_overlap=5,seed=41902,**constants)['plans']['PRIMARY_FILL']
    u6=independent_consensus_portfolio(current,cutoffs=cuts,minimum_anchor_market=.5,max_uses=6,
        max_pair_overlap=5,seed=41902,conversion_budget_fraction=0,group_size=7,**constants)
    for u,b in ((3,u3),(6,u6)):plans[f'U{u}_BASELINE']=paired_double_source(b,cutoffs=cuts,double_source='BASELINE',**constants)
    flat7=flatten_component_groups(plans['U3_BASELINE'],cutoffs=cuts,n=7,**constants)
    for seed in seeds:
        for n,rate,prefix in ((5,.1,'N5_S'),(5,.25,'N5_SWAP_S'),(6,.1,'N6_S')):
            plans[f'{prefix}{seed:03}']=random_reuse_plan(plans[f'N{n}_NO_SWAP'],cutoffs=cuts,seed=seed,
                single_probability=rate,double_probability=0,group_size=n,**constants)
        flat5=flatten_component_groups(plans[f'N5_S{seed:03}'],cutoffs=cuts,n=5,**constants)
        plans[f'MIX_S{seed:03}']=fixed_n67_wallets(dict(N5=flat5,U3=flat7),cutoffs=cuts,wallets=dict(N5=512,U3=512),**constants)
    return dict(plans=plans,exclusions=excluded)
