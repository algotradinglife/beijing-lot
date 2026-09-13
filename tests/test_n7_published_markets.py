import hashlib
import io
import json
import tarfile
import pytest

from src.n7_published_markets import read_n7_published_markets


@pytest.mark.parametrize('archived',[False,True])
def test_published_reader_keeps_missing_issues_and_checks_bytes(tmp_path,archived):
    rows=[dict(issue='001',slot=1,provider_id='002',market=m,status='QUOTES_PRIOR_DIAGNOSTIC',
               cutoff_utc='2010-01-01T00:00:00Z',prior_companies=1,rows=[{'company':'A'}],
               historical_admission=False) for m in ('euro','total')]
    raw=json.dumps(rows).encode();digest=hashlib.sha256(raw).hexdigest()
    if archived:
        with tarfile.open(tmp_path/'archive.tar','w') as archive:
            item=tarfile.TarInfo('audit/001.json');item.size=len(raw)
            archive.addfile(item,io.BytesIO(raw))
        source=dict(issue='001',archive='archive.tar',member='audit/001.json',sha256=digest,
                    archive_sha256=hashlib.sha256((tmp_path/'archive.tar').read_bytes()).hexdigest())
    else:
        (tmp_path/'detail.json').write_bytes(raw)
        source=dict(issue='001',path='detail.json',sha256=digest)
    merged=dict(issues=['001'],issue_sources=[source],rows=rows,historical_admission=False)
    p=tmp_path/'merged.json';p.write_text(json.dumps(merged));md=hashlib.sha256(p.read_bytes()).hexdigest()
    args=dict(data_root=tmp_path,merged_path='merged.json',expected_sha256=md,issues=['000','001','003'])
    result=read_n7_published_markets(**args)
    assert result['issue_order']==args['issues']
    assert [r['status'] for r in result['coverage']]==['NOT_PUBLISHED','PUBLISHED_DETAIL_VERIFIED','NOT_PUBLISHED']
    assert result['rows']==rows and not result['historical_admission']
    with pytest.raises(ValueError,match='Unique'):
        read_n7_published_markets(**{**args,'issues':['001','001']})
    with pytest.raises(ValueError,match='Merged hash'):
        read_n7_published_markets(**{**args,'expected_sha256':'0'*64})
    merged['rows'][0]['prior_companies']=2;p.write_text(json.dumps(merged))
    with pytest.raises(ValueError,match='Summary/detail'):
        read_n7_published_markets(**{**args,'expected_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    merged['rows'][0]['prior_companies']=1;p.write_text(json.dumps(merged))
    changed=tmp_path/('archive.tar' if archived else 'detail.json');changed.write_bytes(changed.read_bytes()+b' ')
    with pytest.raises(ValueError,match='hash mismatch'):
        read_n7_published_markets(**args)
