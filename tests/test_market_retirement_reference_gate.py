import hashlib

import pytest

from src.market_sqlite_retirement import verify_retirement_reference_exclusion


def test_candidate_must_belong_to_same_batch_and_exact_source(tmp_path):
    from src.market_sqlite_retirement import verify_retirement_capture_bindings
    capture = dict(kind='capture', batch_id='b', source_sha256='a' * 64,
                   data=dict(path='old.json', path_aliases=['old.json', 'markets/raw/a.json']))
    plan = dict(batch_id='b', candidates=[dict(path='markets/raw/a.json', sha256='a' * 64)])
    assert verify_retirement_capture_bindings(tmp_path, plan, [capture], batch_id='b')['candidates'] == 1
    with pytest.raises(ValueError, match='capture batch mismatch'):
        verify_retirement_capture_bindings(tmp_path, plan, [dict(capture, batch_id='other')], batch_id='b')
    with pytest.raises(ValueError, match='not bound'):
        verify_retirement_capture_bindings(tmp_path, plan, [], batch_id='b')
    with pytest.raises(ValueError, match='conflicting'):
        verify_retirement_capture_bindings(tmp_path, plan, [capture, dict(capture, source_sha256='b' * 64)], batch_id='b')
    plan['candidates'][0]['sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='not bound'):
        verify_retirement_capture_bindings(tmp_path, plan, [capture], batch_id='b')
    with pytest.raises(ValueError, match='retirement batch mismatch'):
        verify_retirement_capture_bindings(tmp_path, plan, [capture], batch_id='other')
    plan['candidates'][0]['sha256'] = None
    with pytest.raises(ValueError, match='not bound'):
        verify_retirement_capture_bindings(tmp_path, plan, [], batch_id='b')
    for digest in (None, '', 'not-a-sha256', 'A' * 64):
        plan['candidates'][0]['sha256'] = digest
        with pytest.raises(ValueError, match='invalid capture source hash'):
            verify_retirement_capture_bindings(tmp_path, plan, [dict(capture, source_sha256=digest)], batch_id='b')


def test_followup_hash_and_path_protect_all_relocated_aliases():
    from src.market_sqlite_retirement import market_followup_reference_paths
    capture = dict(kind='capture', source_sha256='a' * 64,
                   data=dict(path='old/a.json', path_aliases=['old/a.json', 'markets/raw/a.json']))
    documents = [{'requests': [{'files': {'old/other-name.json': 'a' * 64}}]}]
    expected = ['markets/raw/a.json', 'old/a.json']
    assert market_followup_reference_paths(documents, [capture]) == expected
    assert market_followup_reference_paths([{'source': 'old/a.json'}], [capture]) == expected
    assert market_followup_reference_paths([{'requests': []}], [capture]) == []
    assert market_followup_reference_paths([], []) == []
    with pytest.raises(ValueError, match='capture records'):
        market_followup_reference_paths([], [dict(capture, kind='quote')])
    with pytest.raises(ValueError, match='aliases'):
        market_followup_reference_paths([], [dict(capture, data={'path': 'a', 'path_aliases': ['b']})])
    for documents in ([{'source': 'markets/raw/a.json'}], [{'sha256': 'a' * 64}]):
        with pytest.raises(ValueError, match='aliases'):
            market_followup_reference_paths(documents, [dict(capture, data={
                'path': 'markets/raw/a.json', 'path_aliases': 'markets/raw/a.json'})])


def test_reference_gate_checks_actual_inputs_and_shared_paths(tmp_path):
    (tmp_path / 'markets/raw').mkdir(parents=True)
    snapshot = tmp_path / 'registry.json'
    snapshot.write_bytes(b'{}')
    snapshots = {'registry.json': hashlib.sha256(b'{}').hexdigest()}
    plan = {'candidates': [{'path': 'markets/raw/a.json'}]}
    result = verify_retirement_reference_exclusion(
        tmp_path, plan, snapshots=snapshots, protected_paths=['markets/raw/b.json'])
    assert result['candidates'] == 1
    assert result['raw_deletion_authorized'] is False
    with pytest.raises(ValueError, match='still referenced'):
        verify_retirement_reference_exclusion(
            tmp_path, plan, snapshots=snapshots,
            protected_paths=[str(tmp_path / 'markets/raw/a.json')])
    snapshot.write_bytes(b'changed')
    with pytest.raises(ValueError, match='snapshot changed'):
        verify_retirement_reference_exclusion(tmp_path, plan, snapshots=snapshots, protected_paths=[])
    snapshot.unlink()
    with pytest.raises(FileNotFoundError):
        verify_retirement_reference_exclusion(tmp_path, plan, snapshots=snapshots, protected_paths=[])


def test_reference_gate_rejects_unsafe_paths_and_empty_evidence(tmp_path):
    (tmp_path / 'markets/raw').mkdir(parents=True)
    source = tmp_path / 'snapshot.json'
    source.write_bytes(b'{}')
    snapshots = {'snapshot.json': hashlib.sha256(b'{}').hexdigest()}
    for name in ('../outside.json', str(tmp_path / 'markets/raw/a.json'), 'fundamentals/raw/a.json'):
        with pytest.raises(ValueError, match='unsafe retirement'):
            verify_retirement_reference_exclusion(tmp_path, {'candidates': [{'path': name}]},
                                                 snapshots=snapshots, protected_paths=[])
    plan = {'candidates': [{'path': 'markets/raw/a.json'}] * 2}
    with pytest.raises(ValueError, match='duplicate'):
        verify_retirement_reference_exclusion(tmp_path, plan, snapshots=snapshots, protected_paths=[])
    with pytest.raises(ValueError, match='snapshots required'):
        verify_retirement_reference_exclusion(tmp_path, {'candidates': []}, snapshots={}, protected_paths=[])
    link = tmp_path / 'link.json'
    link.symlink_to(source)
    with pytest.raises(ValueError, match='unsafe reference'):
        verify_retirement_reference_exclusion(tmp_path, {'candidates': []},
                                             snapshots={'link.json': snapshots['snapshot.json']}, protected_paths=[])
