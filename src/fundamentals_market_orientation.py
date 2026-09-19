"""Exact, evidence-bound market orientation corrections; no global team aliases."""
from copy import deepcopy
from pathlib import PurePosixPath
import re

from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


def orient_market_view(fixture, parsed, decision, *, market, cutoff, source_hashes):
    """Return a corrected parsed copy and exact field-change receipt; no I/O.

    Only an approved full reversal of this issue/slot/provider/market is allowed.
    REVERSE_AND_HISTORICAL_ID additionally requires explicit canonical source-side
    IDs equal to the reversed roster, retaining an intermediate identity receipt.
    Three distinct roster, market and independent evidence paths must be bound
    to the supplied verified hashes. European decimal W/L prices swap; draw
    prices and timestamps do not. OU lines (goals) and HK over/under prices
    remain unchanged. Optional home_team_name/away_team_name must occur together.
    Missing context, incomplete schemas, changed evidence and repeat application
    raise ValueError. The original parsed object is never mutated.
    """
    if not isinstance(cutoff, Cutoff) or cutoff.kind != 'DECISION_EPOCH':
        raise ValueError('Explicit decision cutoff required')
    if market not in ('euro', 'total'):
        raise ValueError('Unsupported market')
    if (not isinstance(fixture,dict) or not {'issue','slot','native_match_id','home_id','away_id'}<=fixture.keys()
            or not isinstance(parsed,dict) or not {'provider_id','home_team_id','away_team_id'}<=parsed.keys()
            or not isinstance(decision,dict) or not isinstance(source_hashes,dict)):
        raise ValueError('Complete orientation context required')
    roster_ids=[str(fixture['home_id']),str(fixture['away_id'])]
    source_ids=[parsed['home_team_id'],parsed['away_team_id']]
    action=decision.get('action')
    canonical_ids=decision.get('canonical_source_ids') if action=='REVERSE_AND_HISTORICAL_ID' else source_ids
    if (any(not isinstance(x,str) or not x.isdigit() or int(x)<=0 for x in roster_ids+source_ids)
            or len(set(roster_ids))!=2 or len(set(source_ids))!=2 or canonical_ids!=roster_ids[::-1]):
        raise ValueError('Only an exact two-team reversal is allowed')
    if action=='REVERSE_AND_HISTORICAL_ID':
        if source_ids==canonical_ids or any(raw in roster_ids and raw!=canonical for raw,canonical in zip(source_ids,canonical_ids)):
            raise ValueError('Compound source-side identity contradicts known teams')
    context=dict(issue=fixture['issue'],slot=fixture['slot'],provider_id=fixture['native_match_id'],
        market=market,roster_ids=roster_ids,source_ids=source_ids,cutoff_utc=cutoff.cutoff_ts.isoformat())
    if action=='REVERSE_AND_HISTORICAL_ID':
        context['canonical_source_ids']=canonical_ids
    if (decision.get('approved') is not True or action not in ('REVERSE_MARKET_ORIENTATION','REVERSE_AND_HISTORICAL_ID')
            or not decision.get('adjudication_id') or cutoff.target_issue!=fixture['issue']
            or parsed['provider_id']!=fixture['native_match_id']
            or any(decision.get(k)!=v for k,v in context.items())):
        raise ValueError('Unauthorized exact orientation context')
    required=[decision.get(k) for k in ('roster_path','capture_path','independent_evidence_path')]
    files=decision.get('files',{})
    if (not isinstance(files,dict) or any(not isinstance(p,str) or not p for p in required)
            or len(set(required))!=3 or any(p not in files for p in required)):
        raise ValueError('Three distinct bound evidence paths required')
    for path,digest in files.items():
        if not isinstance(path,str) or not path:
            raise ValueError('Orientation evidence hash/path mismatch')
        p=PurePosixPath(path)
        if (p.is_absolute() or '..' in p.parts or not re.fullmatch('[0-9a-f]{64}',str(digest))
                or source_hashes.get(path)!=digest):
            raise ValueError('Orientation evidence hash/path mismatch')
    if ('home_team_name' in parsed)!=('away_team_name' in parsed):
        raise ValueError('Both optional team names required')
    if market=='euro' and (not isinstance(parsed.get('quotes'),list)
            or any(not isinstance(q,dict) or not {'quote_id','odds_W','odds_D','odds_L','quoted_at'}<=q.keys() for q in parsed['quotes'])):
        raise ValueError('Complete European quote schema required')
    if market=='total' and any(not isinstance(parsed.get(k),list) for k in ('overview','changes')):
        raise ValueError('Complete total-goal schema required')
    intermediate=deepcopy(parsed)
    identity_changes=[]
    for field,value in zip(('home_team_id','away_team_id'),canonical_ids):
        if intermediate[field]!=value:
            identity_changes.append(dict(path='/'+field,before=intermediate[field],after=value))
            intermediate[field]=value
    adjusted=deepcopy(intermediate)
    orientation_changes=[]
    for home,away in [('home_team_id','away_team_id')]+(
            [('home_team_name','away_team_name')] if 'home_team_name' in parsed else []):
        adjusted[home],adjusted[away]=intermediate[away],intermediate[home]
        orientation_changes.extend([dict(path='/'+home,before=intermediate[home],after=adjusted[home]),
                        dict(path='/'+away,before=intermediate[away],after=adjusted[away])])
    if market=='euro':
        for i,q in enumerate(parsed['quotes']):
            adjusted['quotes'][i]['odds_W']=q['odds_L']
            adjusted['quotes'][i]['odds_L']=q['odds_W']
            orientation_changes.extend([dict(path=f'/quotes/{i}/odds_W',quote_id=q['quote_id'],before=q['odds_W'],after=q['odds_L']),
                            dict(path=f'/quotes/{i}/odds_L',quote_id=q['quote_id'],before=q['odds_L'],after=q['odds_W'])])
    receipt=dict(**context,adjudication_id=decision['adjudication_id'],
        action=action,decision_sha256=stable_json_hash(decision),
        original_parsed_sha256=stable_json_hash(parsed),intermediate_parsed_sha256=stable_json_hash(intermediate),
        adjusted_parsed_sha256=stable_json_hash(adjusted),
        identity_changes=identity_changes,orientation_changes=orientation_changes,
        changes=identity_changes+orientation_changes,source_hashes=dict(files),original_preserved=True,historical_admission=False)
    return dict(parsed=adjusted,receipt=receipt)
