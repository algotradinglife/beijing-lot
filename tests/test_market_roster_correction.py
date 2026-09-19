import hashlib

import pytest

from src.market_roster_correction import correct_roster_names


def test_exact_empty_name_correction_is_replayable_and_preserves_other_rows():
    raw = b'<select id="dropIssueNum"><option selected value="20094"></option></select><tr id="row_506" matchid="506"><a id="HomeTeam_1898621" onmouseover="/temp/1898621_21040.htm"></a><td>0-0</td></tr><tr id="row_507" matchid="507"><td>unchanged</td></tr>'
    body = b'independently checked evidence'
    digest = hashlib.sha256(body).hexdigest()
    change = dict(slot=506, provider_id='1898621', role='home', team_id='21040', name='Kolos', evidence_sha256=[digest])
    kwargs = dict(issue='20094', corrections=[change], evidence={digest: body})
    result, receipt = correct_roster_names(raw, **kwargs)
    assert correct_roster_names(raw, **kwargs) == (result, receipt)
    assert b'>Kolos</a><td>0-0</td>' in result
    assert b'<tr id="row_507" matchid="507"><td>unchanged</td></tr>' in result
    assert b'Kolos' not in raw
    assert receipt['source_sha256'] == hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match='empty name'):
        correct_roster_names(result, **kwargs)
    for field, value in [('team_id', '999'), ('provider_id', '999'), ('slot', 999), ('evidence_sha256', []), ('name', '')]:
        with pytest.raises(ValueError):
            correct_roster_names(raw, **dict(kwargs, corrections=[dict(change, **{field: value})]))
    with pytest.raises(ValueError, match='issue'):
        correct_roster_names(raw, **dict(kwargs, issue='20093'))
    with pytest.raises(ValueError, match='hash'):
        correct_roster_names(raw, **dict(kwargs, evidence={digest: b'changed'}))
    with pytest.raises(ValueError, match='duplicate'):
        correct_roster_names(raw, **dict(kwargs, corrections=[change, change]))
