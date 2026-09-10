import gzip
import json
import hashlib
import shutil
from pathlib import Path
import pytest
from src.fundamentals_score_diagnostic import prepare_score_diagnostic


def test_saved_second_issue_reuses_windows_and_rejects_proxy_learning(tmp_path,monkeypatch):
    fixture=Path('tests/fixtures/fundamentals_multi_issue')
    for p in fixture.glob('*.json.gz'):
        (tmp_path/p.name.removesuffix('.gz')).write_bytes(gzip.decompress(p.read_bytes()))
    kwargs=dict(issue='100102',cutoffs=json.loads((fixture/'100102-cutoffs.json').read_text()),
        expected_fixture_count=43,window=10,minimum=10,repository_root=str(Path.cwd()),cache_dir=None)
    monkeypatch.setattr('src.fundamentals_home_away.roster_observed_results',lambda *a,**k:pytest.fail('labels opened during preparation'))
    paths=[str(tmp_path/f'100102-001-{s}.json') for s in ('titan','nowscore')]
    out=prepare_score_diagnostic(str(tmp_path/'100102-roster.json'),paths,**kwargs)
    assert len(out['windows'])==len(out['handicaps'])==len(out['gates'])==43
    assert all(g['status']=='UNAVAILABLE_FOR_FITTING' and 'cannot authorize' in g['reason'] for g in out['gates'])
    assert out['source_policy']=='TITAN_PRIMARY_NOWSCORE_FILL_CROSSCHECK_NONVETO'
    assert 'page_fields' not in out and 'results' not in out
    assert any(w['status']=='OK_DIAGNOSTIC' for w in out['windows'])
    assert all(not w['home_receipt']['historical_admission'] for w in out['windows'])
    helper = 'src/fundamentals_roster_handicap.py'
    assert out['implementation_hashes'][helper] == hashlib.sha256(Path(helper).read_bytes()).hexdigest()
    copied = tmp_path/'repository'
    shutil.copytree('src', copied/'src', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree('r', copied/'r')
    with (copied/helper).open('a') as handle:
        handle.write('\n# provenance regression mutation\n')
    changed = prepare_score_diagnostic(str(tmp_path/'100102-roster.json'), [],
        **{**kwargs, 'repository_root':str(copied)})
    assert changed['implementation_hashes'][helper] != out['implementation_hashes'][helper]
    empty=prepare_score_diagnostic(str(tmp_path/'100102-roster.json'),[],**kwargs)
    assert len(empty['windows'])==43 and all(w['status']=='IDENTITY_UNAVAILABLE' for w in empty['windows'])
    with pytest.raises(ValueError):prepare_score_diagnostic(str(tmp_path/'100102-roster.json'),paths,**{**kwargs,'cutoffs':{}})
