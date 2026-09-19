import pytest
from src.market_publication_references import collect_publication_references


def test_chunked_reference_inventory_preserves_scope_and_binding(monkeypatch):
    calls=[]
    def read(**kwargs):
        calls.append(kwargs)
        return dict(coverage=[dict(issue=i,status='PUBLISHED_DETAIL_VERIFIED') for i in kwargs['issues']],
                    rows=[dict(source_hashes={i:'hash','shared':'hash'}) for i in kwargs['issues']])
    monkeypatch.setattr('src.market_publication_references.read_n7_published_markets',read)
    issues=['001','002','003','004','005'];pub=dict(path='release.json',sha256='a'*64)
    assert collect_publication_references('root',publication=pub,issues=issues,chunk_size=2)==issues+['shared']
    assert [c['issues'] for c in calls]==[issues[:2],issues[2:4],issues[4:]]
    assert all(c['expected_sha256']==pub['sha256'] and c['merged_path']==pub['path'] for c in calls)


def test_missing_coverage_and_invalid_scope_fail(monkeypatch):
    monkeypatch.setattr('src.market_publication_references.read_n7_published_markets',
                        lambda **k:dict(coverage=[],rows=[]))
    with pytest.raises(ValueError,match='incomplete'):
        collect_publication_references('root',publication={'path':'p','sha256':'h'},issues=['1'])
    for issues,size in [([],10),(['1','1'],10),(['1'],0),(['1'],True)]:
        with pytest.raises(ValueError,match='unique issues'):
            collect_publication_references('root',publication={},issues=issues,chunk_size=size)
