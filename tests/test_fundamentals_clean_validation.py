import copy,gzip,hashlib,json
from pathlib import Path
import pytest
from src.fundamentals_clean_validation import read_clean_validation_release,clean_validation_forms,clean_validation_market,validation_predictor_clocks

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def sample():
 f=dict(issue='100101',slot=1,provider_id='999',home='H',away='A',competition='CUP',home_id='H',away_id='A')
 cuts={'1':'2010-01-01T12:00:00+00:00'}
 base=dict(f,kickoff_utc='2010-01-01T13:00:00Z',neutral_venue=None,identity_source='titan',competition_category='CUP')
 history=[dict(slot=1,history_id=str(i),event_date=f'2009-12-{i:02d}',home_id='H',away_id='A',home='H',away='A',home_goals=2,away_goals=1) for i in range(1,12)]
 payload=dict(fixtures=[f],clean=dict(cutoffs=cuts,integrated_fixtures=[base],source_fixtures=[dict(base,source='titan')],integrated_history=history,adjudications=[]))
 ep=dict(provider_id='999',home_team_id='H',away_team_id='A',kickoff_utc=base['kickoff_utc'],quotes=[dict(quote_id='1',company='C',quoted_at='2010-01-01T11:00:00Z',odds_W=2,odds_D=3,odds_L=4)])
 tp=dict(provider_id='999',home_team_id='H',away_team_id='A',kickoff_local='2010-01-01 21:00',changes=[dict(quote_id='0/C',company='C',quoted_local='1-1 19:00',phase='PREMATCH',line=2.5,over_hk=.9,under_hk=.9)])
 markets=[dict(market=k,provider_id='999',status='PARSED',path=k,capture_sha256=k,parsed=p) for k,p in [('euro',ep),('total',tp)]]
 return payload,markets,cuts


def test_clean_forms_reuse_and_future_invariance(sample):
 p,m,c=sample;h=[dict(slot=1,provider_id='999',home_handicap=-2)]
 kw=dict(cutoffs=c,window=10,minimum=10,source_hashes={'release':'abc'},repository_root=ROOT)
 x=clean_validation_forms(p,h,**kw)
 assert x['windows'][0]['status']=='OK_DIAGNOSTIC'
 assert x['context']['rows'][0]['home_venue_goals_for_pg']==2
 changed=copy.deepcopy(p);changed['clean']['integrated_history'].append(dict(p['clean']['integrated_history'][0],history_id='future',event_date='2010-01-02',home_goals=99))
 z=clean_validation_forms(changed,h,**kw)
 assert z['context']['rows']==x['context']['rows']
 assert z['windows'][0]['home_window']==x['windows'][0]['home_window']
 with pytest.raises(ValueError):clean_validation_forms(p,[],**kw)
 with pytest.raises(ValueError):clean_validation_forms(p,h,**dict(kw,cutoffs={}))
 empty=copy.deepcopy(p);empty['clean']['integrated_history']=[]
 assert clean_validation_forms(empty,h,**kw)['windows'][0]['status']=='INSUFFICIENT_HISTORY'


def test_clean_market_gates_and_clock(sample):
 p,m,c=sample;kw=dict(cutoffs=c,source_hashes={'release':'abc'},repository_root=ROOT)
 z=clean_validation_market(p,m,**kw)
 assert z['rows'][0]['status']=='READY' and z['rows'][0]['odds_W']==2
 forms=clean_validation_forms(p,[dict(slot=1,provider_id='999',home_handicap=-2)],window=10,minimum=10,**kw)
 clocks=validation_predictor_clocks(forms['context'],z,cutoffs=c)
 assert clocks[0]['predictor_clock_ts']=='2010-01-01T11:00:00+00:00'
 bad=copy.deepcopy(z);bad['receipts'][0]['provider_id']='wrong'
 with pytest.raises(ValueError):validation_predictor_clocks(forms['context'],bad,cutoffs=c)
 for market in ['euro','total']:
  bad=copy.deepcopy(m);next(r for r in bad if r['market']==market)['quote_identity_status']='QUARANTINED_WRONG_TEAM_ID'
  assert clean_validation_market(p,bad,**kw)['rows'][0]['status']=='QUARANTINED_IDENTITY'
 bad=copy.deepcopy(m);bad[1]['parsed']['changes'].append(dict(bad[1]['parsed']['changes'][0],quote_id='1/C',line=3))
 assert clean_validation_market(p,bad,**kw)['rows'][0]['status']=='QUOTE_CLOCK_CONFLICT'
 bad=copy.deepcopy(m);bad[0]['parsed']['quotes'][0]['quoted_at']=c['1']
 assert clean_validation_market(p,bad,**kw)['rows'][0]['status']=='NO_PRIOR_QUOTES'
 bad=copy.deepcopy(m);bad[1]['parsed']['home_team_id']='X'
 assert clean_validation_market(p,bad,**kw)['rows'][0]['status']=='TEAM_ID_MISMATCH'
 assert clean_validation_market(p,[],**kw)['rows'][0]['status']=='MARKET_UNAVAILABLE'
 with pytest.raises(ValueError):clean_validation_market(p,m+m,**kw)
 with pytest.raises(ValueError):clean_validation_market(p,m,**dict(kw,cutoffs={}))


def test_read_approved_release_hashes_and_scope(tmp_path,sample):
 p,m,c=sample;page=tmp_path/'100101.json';page.write_text(json.dumps(p));market=tmp_path/'market.json';market.write_text(json.dumps(m))
 files={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [page,market]}
 manifest=dict(analysis_paths=[str(page)],market_path=str(market),files=files,historical_admission=False,source_policy='TITAN_PRIMARY_NOWSCORE_CROSSCHECK_FILL')
 (tmp_path/'cleanup-manifest.json').write_text(json.dumps(manifest))
 x=read_clean_validation_release(tmp_path,cutoffs={'100101':c})
 assert len(x['payloads'])==1 and len(x['markets'])==2
 with pytest.raises(ValueError):read_clean_validation_release(tmp_path,cutoffs={})
 page.write_text('{}')
 with pytest.raises(ValueError,match='Changed release'):read_clean_validation_release(tmp_path,cutoffs={'100101':c})


def test_archived_clean_validation_fixture():
 saved=json.loads(gzip.decompress(Path('tests/fixtures/clean_validation_input.json.gz').read_bytes()))
 x=saved['input']
 assert x['forms']['context']['seal']==hashlib.sha256(x['forms']['context']['canonical_json'].encode()).hexdigest()
 assert saved['sha256']==hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
