import copy

import pytest

from src.market_retirement_relocations import bind_relocated_capture_aliases
from src.market_retirement_relocations import protect_relocated_paths


def test_explicit_relocation_adds_alias_without_mutating_capture():
    record = dict(kind='capture', source_sha256='a' * 64,
                  data={'path': 'data/raw/page.json'})
    original = copy.deepcopy(record)
    target = '/volume/markets/raw/verified-responses/' + 'a' * 64 + '.json'
    result = bind_relocated_capture_aliases(
        [record], {'/project/data/raw/page.json': target},
        original_root='/project', data_root='/volume')
    assert record == original
    assert result[0]['data']['path_aliases'] == [record['data']['path'], target[len('/volume/'):]]
    assert bind_relocated_capture_aliases(
        result, {'/project/data/raw/page.json': target},
        original_root='/project', data_root='/volume') == result


def test_missing_mapping_retains_original_and_bad_identity_fails():
    record = dict(kind='capture', source_sha256='a' * 64,
                  data={'path': '/project/page.json'})
    args = dict(original_root='/project', data_root='/volume')
    assert bind_relocated_capture_aliases([record], {}, **args)[0]['data']['path_aliases'] == ['/project/page.json']
    for target in ['/other/a.json', '/volume/markets/raw/verified-responses/' + 'b' * 64 + '.json', None]:
        with pytest.raises(ValueError, match='identity mismatch'):
            bind_relocated_capture_aliases([record], {'/project/page.json': target}, **args)
    with pytest.raises(ValueError, match='absolute relocation roots'):
        bind_relocated_capture_aliases([], {}, original_root='relative', data_root='/volume')
    with pytest.raises(ValueError, match='capture records'):
        bind_relocated_capture_aliases([dict(record, kind='quote')], {}, **args)
    with pytest.raises(ValueError, match='source digest'):
        bind_relocated_capture_aliases([dict(record, source_sha256='bad')], {}, **args)
    with pytest.raises(ValueError, match='unsafe original'):
        bind_relocated_capture_aliases([dict(record, data={'path': '../page.json'})], {}, **args)
    with pytest.raises(ValueError, match='invalid capture aliases'):
        bind_relocated_capture_aliases([dict(record, data={'path': 'page', 'path_aliases': []})], {}, **args)


def test_old_shared_reference_protects_relocated_copy():
    target = '/volume/markets/raw/verified-responses/a.json'
    mapping = {'/project/data/raw/a.json': target}
    args = dict(original_root='/project', data_root='/volume')
    refs = ['data/raw/a.json', '/unmapped/file']
    assert protect_relocated_paths(refs, mapping, **args) == {*refs, target}
    assert protect_relocated_paths(['/project/data/raw/a.json'], mapping, **args) == {
        '/project/data/raw/a.json', target}
    for bad in ['../x', '', None]:
        with pytest.raises(ValueError, match='unsafe protected'):
            protect_relocated_paths([bad], mapping, **args)
    for bad in ['/elsewhere/file', '/volume/../elsewhere/file', None]:
        with pytest.raises(ValueError, match='unsafe relocation'):
            protect_relocated_paths(refs, {'/project/data/raw/a.json': bad}, **args)
    with pytest.raises(ValueError, match='absolute relocation roots'):
        protect_relocated_paths([], {}, original_root='relative', data_root='/volume')


def test_unmapped_historical_alias_protects_mapped_copy():
    digest = 'a' * 64
    target = '/volume/markets/raw/verified-responses/' + digest + '.json'
    capture = dict(kind='capture', source_sha256=digest,
                   data=dict(path='old/a.json', path_aliases=['old/a.json', 'other/b.json']))
    for protected in ['other/b.json', '/project/other/b.json']:
        result = protect_relocated_paths(
            [protected], {'/project/old/a.json': target}, original_root='/project',
            data_root='/volume', captures=[capture])
        assert target in result
        assert 'old/a.json' in result
