import hashlib
import pytest
from src.fundamentals_jina import analysis_parsing_view
from src.fundamentals_census import decode_analysis_text


def test_proxy_view_preserves_original_and_binds_transform():
    url='https://r.jina.ai/https://zq.titan007.com/analysis/123cn.htm'
    receipt=dict(url=url,final_url=url,status=200)
    body='<meta charset="gb2312"><title>长春亚泰</title>'.encode()
    meta,parsed=analysis_parsing_view(receipt,body)
    assert decode_analysis_text(parsed)[0].endswith('长春亚泰</title>')
    assert meta['transport_url']==receipt['url']==url
    assert b'gb2312' in body
    assert meta['transport_sha256']==hashlib.sha256(body).hexdigest()
    assert meta['parser_body_sha256']==hashlib.sha256(parsed).hexdigest()
    with pytest.raises(ValueError):
        analysis_parsing_view(dict(receipt,final_url='https://example.com'),body)
    with pytest.raises(ValueError):
        analysis_parsing_view(dict(receipt,url='https://r.jina.ai/https://evil.test'),body)
    failed, raw = analysis_parsing_view(receipt,b'\xff')
    assert failed['parser_error'] and raw == b'\xff'


def test_direct_and_failed_receipts_keep_bytes():
    r=dict(url='https://live.nowscore.com/analysis/123cn.html',final_url='x',status=200)
    assert analysis_parsing_view(r,b'\xff')==(r,b'\xff')
    url='https://r.jina.ai/https://live.nowscore.com/analysis/123cn.html'
    _,body=analysis_parsing_view(dict(url=url,final_url=url,status=422),b'\xff')
    assert body==b'\xff'
