from copy import deepcopy
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_market_orientation import orient_market_view


@pytest.mark.parametrize('market',['euro','total'])
def test_exact_orientation_evidence_and_prices(market):
    f=dict(issue='100609',slot=2,native_match_id='355292',home_id='649',away_id='803')
    p=dict(provider_id='355292',home_team_id='803',away_team_id='649',
        home_team_name='South Africa',away_team_name='France',
        quotes=[dict(quote_id='1',odds_W=4.5,odds_D=3.5,odds_L=1.8,quoted_at='2010-06-22T13:00:00Z')],
        overview=[dict(line=2.5,over_hk=.9,under_hk=.95)],
        changes=[dict(quote_id='1/A',phase='PREMATCH',line=2.5,over_hk=.8,under_hk=1.0)])
    cutoff=Cutoff.decision_epoch('100609','2010-06-22T13:45:00Z')
    hashes={'roster.json':'a'*64,'market.json':'b'*64,'independent.json':'c'*64}
    d=dict(approved=True,action='REVERSE_MARKET_ORIENTATION',adjudication_id='EXACT-TEST',
        issue=f['issue'],slot=f['slot'],provider_id=f['native_match_id'],market=market,
        roster_ids=['649','803'],source_ids=['803','649'],cutoff_utc=cutoff.cutoff_ts.isoformat(),
        roster_path='roster.json',capture_path='market.json',independent_evidence_path='independent.json',
        files=hashes)
    args=dict(market=market,cutoff=cutoff,source_hashes=hashes)
    before=deepcopy(p)
    result=orient_market_view(f,p,d,**args)
    assert p==before and result==orient_market_view(f,p,d,**args)
    q=result['parsed']
    assert (q['home_team_id'],q['away_team_id'])==('649','803')
    assert (q['home_team_name'],q['away_team_name'])==('France','South Africa')
    assert q['overview']==p['overview'] and q['changes']==p['changes']
    assert q['quotes'][0]['odds_D']==3.5 and q['quotes'][0]['quoted_at']==p['quotes'][0]['quoted_at']
    assert q['quotes'][0]['odds_W']==(1.8 if market=='euro' else 4.5)
    assert result['receipt']['original_parsed_sha256']==stable_json_hash(p)
    assert result['receipt']['historical_admission'] is False
    with pytest.raises(ValueError,match='reversal'):
        orient_market_view(f,q,d,**args)
    for key,value in [('approved',False),('slot',3),('provider_id','other'),('market','other'),
                      ('cutoff_utc','2010-06-22T12:45:00+00:00'),('source_ids',['1','2'])]:
        with pytest.raises(ValueError,match='Unauthorized'):
            orient_market_view(f,p,dict(d,**{key:value}),**args)
    with pytest.raises(ValueError,match='hash/path'):
        orient_market_view(f,p,d,**dict(args,source_hashes=dict(hashes,**{'independent.json':'d'*64})))
    with pytest.raises(ValueError,match='distinct'):
        orient_market_view(f,p,dict(d,independent_evidence_path='market.json'),**args)
    bad=deepcopy(p);del bad['away_team_name']
    with pytest.raises(ValueError,match='names'):
        orient_market_view(f,bad,d,**args)
    bad=deepcopy(p)
    if market=='euro':del bad['quotes'][0]['odds_L']
    else:del bad['overview']
    with pytest.raises(ValueError,match='schema'):
        orient_market_view(f,bad,d,**args)
    bad=dict(p,home_team_id='999')
    with pytest.raises(ValueError,match='reversal'):
        orient_market_view(f,bad,d,**args)
    with pytest.raises(ValueError,match='context'):
        orient_market_view({},p,d,**args)
    with pytest.raises(ValueError,match='context'):
        orient_market_view(f,p,d,**dict(args,source_hashes=None))
    with pytest.raises(ValueError,match='cutoff'):
        orient_market_view(f,p,d,**dict(args,cutoff=None))
    no_names={k:v for k,v in p.items() if not k.endswith('_team_name')}
    assert orient_market_view(f,no_names,d,**args)['parsed']['home_team_id']=='649'
