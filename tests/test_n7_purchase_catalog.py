import copy
import pytest
from src.n7_purchase_catalog import merge_purchase_catalogs


def test_merge_preserves_explicit_scope_missing_reasons_and_input():
    row = {'issue': '001', 'path': '/frozen/a.gz', 'sha256': 'a' * 64}
    catalogs = [{'issues': [row, {**row, 'issue': '009'}]},
                {'issues': [], 'unavailable': {'002': 'NO_MARKETS'}}]
    original = copy.deepcopy(catalogs)
    result = merge_purchase_catalogs(catalogs, [['001'], ['002']], ['001', '002'])
    assert result['issues'] == [row]
    assert result['unavailable_issues'] == [{'issue': '002', 'status': 'NOT_EVALUABLE', 'reason': 'NO_MARKETS'}]
    assert catalogs == original
    assert result['historical_admission'] is False


@pytest.mark.parametrize('change', ['duplicate_scope', 'missing_issue', 'bad_hash', 'duplicate_row', 'overlap_missing'])
def test_merge_rejects_ambiguous_or_incomplete_catalogs(change):
    row = {'issue': '001', 'path': '/frozen/a.gz', 'sha256': 'a' * 64}
    catalogs, scopes, requested = [{'issues': [row]}], [['001']], ['001']
    if change == 'duplicate_scope':
        catalogs *= 2
        scopes *= 2
    elif change == 'missing_issue':
        requested.append('002')
    elif change == 'bad_hash':
        row['sha256'] = None
    elif change == 'duplicate_row':
        catalogs[0]['issues'].append(dict(row))
    else:
        catalogs[0]['unavailable'] = {'001': 'CONFLICT'}
    with pytest.raises(ValueError):
        merge_purchase_catalogs(catalogs, scopes, requested)
