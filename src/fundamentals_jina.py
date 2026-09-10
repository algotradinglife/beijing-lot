"""Explicit parsing view for saved Jina HTML; original transport stays immutable."""
import hashlib
import re


def analysis_parsing_view(receipt, body):
    """Return metadata/body for parsing, with transport and transform provenance.

    Direct receipts pass through. Jina must be unredirected and wrap an exact
    supported analysis URL. Successful Jina HTML is strictly UTF-8; only stale
    GB2312/GBK meta declarations are changed in the in-memory parsing view.
    No fetch, disk writes, identity approval, or replacement decoding.
    """
    url = receipt['url']
    if not url.startswith('https://r.jina.ai/'):
        return receipt, body
    source_url = url[len('https://r.jina.ai/'):]
    if receipt['final_url'] != url or not re.fullmatch(
            r'https://(?:live\.nowscore\.com/analysis/\d+cn\.html|zq\.titan007\.com/analysis/\d+cn\.htm)', source_url):
        raise ValueError('Unsupported or redirected Jina analysis receipt')
    meta = dict(receipt, url=source_url, final_url=source_url, transport_url=url,
                transport_sha256=hashlib.sha256(body).hexdigest())
    parsed = body
    if receipt['status'] == 200:
        try:
            text = body.decode('utf-8-sig', errors='strict')
        except UnicodeDecodeError as error:
            meta['parser_error'] = str(error)
            meta['parser_body_sha256'] = meta['transport_sha256']
            meta['parser_transform'] = 'JINA_UTF8_DECODE_FAILURE'
            return meta, body
        parsed = re.sub(r'(?i)(<meta\b[^>]*\bcharset\s*=\s*["\x27]?\s*)(?:gb2312|gbk)\b',
                        r'\1utf-8', text).encode('utf-8')
    meta['parser_body_sha256'] = hashlib.sha256(parsed).hexdigest()
    meta['parser_transform'] = 'JINA_UTF8_HTML_META_NORMALIZATION'
    return meta, parsed
