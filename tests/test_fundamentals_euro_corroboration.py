import base64
import hashlib
import json
from pathlib import Path

import pytest

from src.fundamentals_census import read_response, decode_analysis_text
from src.fundamentals_titan_euro import parse_titan_euro
from src.fundamentals_euro_corroboration import corroborated_euro


@pytest.mark.parametrize('price', ['1', '0.9', '0', '-1', 'NaN'])
def test_saved_source_low_price_rule(tmp_path, price):
    _, raw = read_response(Path('tests/fixtures/fundamentals_titan_euro/357841.json'))
    text = decode_analysis_text(raw)[0]
    import re
    import json5
    block = re.search(r'game\s*=\s*Array\((.*?)\)\s*;', text, re.S)
    records = json5.loads('[' + block[1] + ']')
    for i, record in enumerate(records):
        parts = record.split('|')
        if parts[23] == '0' and all(parts[10:13]):
            parts[10] = price
            records[i] = '|'.join(parts)
            break
    text = text[:block.start(1)] + ','.join(json.dumps(r) for r in records) + text[block.end(1):]
    raw = text.encode('utf-8')
    paths = []
    for host in ['1x2d.titan007.com', '1x2.nowscore.com']:
        url = f'https://{host}/357841.js'
        path = tmp_path / (host + '.json')
        path.write_text(json.dumps(dict(url=url, final_url=url, status=200,
            started_at_utc="2026-09-11T00:00:00Z", received_at_utc='2026-09-11T00:00:00Z', byte_count=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(), body_base64=base64.b64encode(raw).decode())))
        paths.append(path)
    with pytest.raises(ValueError):
        parse_titan_euro(text)
    if price in ['0', '-1', 'NaN']:
        with pytest.raises(ValueError):
            corroborated_euro(*paths)
        return
    before = [p.read_bytes() for p in paths]
    result = corroborated_euro(*paths)
    assert result == corroborated_euro(*paths)
    low = [q for q in result['parsed']['quotes'] if q.get('low_odds_multisource_accepted')]
    assert low and low[0]['odds_W'] == float(price)
    assert before == [p.read_bytes() for p in paths]
    with pytest.raises(ValueError):
        parse_titan_euro(text, corroborating_text=text + ' ')
    from src.fundamentals_euro_corroboration import replay_corroborated_euro
    roster = tmp_path / "roster.json"
    roster.write_text("{}")
    initial = tmp_path / "initial.json"
    fixture = dict(issue="100102", slot=1, native_match_id="357841",
        home_id="116", away_id="109", status="完场",
        cutoff_text="截止时间：2010-01-07 04:30", kickoff_time="05:00")
    initial.write_text(json.dumps([dict(category="INVALID_COMPANY_PRICE",
        provider_id="357841", path=str(paths[0]),
        capture_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
        rosters=[dict(path=str(roster), sha256=hashlib.sha256(roster.read_bytes()).hexdigest(), row=fixture)])]))
    comparison = tmp_path / "comparison.json"
    comparison.write_text(json.dumps(dict(nowscore_comparison=[dict(provider_id="357841", path=str(paths[1]))])))
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps(dict(fixtures=[dict(issue="100102", slot=1, decision_ts="2010-01-06T20:30:00Z")])))
    replay = replay_corroborated_euro(initial, comparison, scope, repository_root=Path.cwd())
    assert len(replay["fixtures"]) == 1 and replay["historical_admission"] is False
    assert replay["fixtures"][0]["low_companies"] == 1
    roster.write_text("changed")
    with pytest.raises(ValueError, match="roster changed"):
        replay_corroborated_euro(initial, comparison, scope, repository_root=Path.cwd())
    meta = json.loads(paths[1].read_text())
    meta['url'] = meta['final_url'] = 'https://1x2.nowscore.com/1.js'
    paths[1].write_text(json.dumps(meta))
    with pytest.raises(ValueError, match='identity'):
        corroborated_euro(*paths)
    meta['status'] = 404
    paths[1].write_text(json.dumps(meta))
    with pytest.raises(ValueError, match='Successful'):
        corroborated_euro(*paths)
