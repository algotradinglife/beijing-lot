"""Read hash-bound published quote views for N7 research; no cleaning or writes."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from src.data_archive import read_archive_members


def read_n7_published_markets(*, data_root, merged_path, expected_sha256, issues):
    """Return every requested issue's published market rows and explicit gaps.

    Issues are unique ordered strings. The caller supplies the accepted release's
    merged path/hash; this reader verifies its bytes and each consumed detail,
    including archive hashes. It does not grant acceptance or prospective use.
    Missing issues remain NOT_PUBLISHED and are never replaced by later issues.
    Reads only derived quote views, not raw pages or settlement. Raises on unsafe
    paths, duplicate identities, corrupt hashes or summary/detail disagreement.
    Output contains issue_order, coverage, rows, source_hashes and false admission.
    """
    root = Path(data_root).resolve(strict=True)
    if not issues or any(not isinstance(i,str) or not i for i in issues) or len(set(issues))!=len(issues):
        raise ValueError('Unique ordered issue strings required')
    path = (root / merged_path).resolve(strict=True)
    path.relative_to(root)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError('Merged hash mismatch')
    merged = json.loads(raw)
    published = merged['issues']
    sources = {s['issue']:s for s in merged['issue_sources']}
    if (merged['historical_admission'] is not False or len(published)!=len(set(published))
            or len(sources)!=len(merged['issue_sources']) or set(sources)!=set(published)):
        raise ValueError('Published issue contract mismatch')
    hashes = {path.relative_to(root).as_posix():expected_sha256}
    archived = defaultdict(list)
    contents = {}
    for issue in issues:
        if issue not in sources:
            continue
        source = sources[issue]
        if 'archive' in source:
            ap = (root/source['archive']).resolve(strict=True)
            ap.relative_to(root)
            archived[(ap,source['archive_sha256'])].append(source)
        else:
            dp = (root/source['path']).resolve(strict=True)
            dp.relative_to(root)
            contents[issue] = dp.read_bytes()
            hashes[dp.relative_to(root).as_posix()] = source['sha256']
    for (ap,digest), entries in archived.items():
        result = read_archive_members(ap,[e['member'] for e in entries],expected_sha256=digest)
        hashes[ap.relative_to(root).as_posix()] = digest
        for entry in entries:
            contents[entry['issue']] = result[entry['member']]
    compact = defaultdict(list)
    for row in merged['rows']:
        compact[row['issue']].append(row)
    rows, coverage = [], []
    fields = ('issue','slot','provider_id','market','status','cutoff_utc','prior_companies')
    for issue in issues:
        if issue not in contents:
            coverage.append(dict(issue=issue,status='NOT_PUBLISHED',fixture_market_rows=0))
            continue
        if hashlib.sha256(contents[issue]).hexdigest()!=sources[issue]['sha256']:
            raise ValueError('Detail hash mismatch')
        detail = json.loads(contents[issue])
        keys = [(r['issue'],r['slot'],r['market']) for r in detail]
        if (not detail or len(keys)!=len(set(keys)) or any(r['issue']!=issue for r in detail)
                or any(r['market'] not in ('euro','total') for r in detail)
                or any(r['historical_admission'] is not False for r in detail)):
            raise ValueError('Detail row identity/admission mismatch')
        observed = sorted([tuple(r[k] for k in fields) for r in detail])
        expected = sorted([tuple(r[k] for k in fields) for r in compact[issue]])
        if observed!=expected:
            raise ValueError('Summary/detail mismatch')
        for row in detail:
            if row['status']=='QUOTES_PRIOR_DIAGNOSTIC' and (
                    not row['rows'] or len(row['rows'])!=row['prior_companies']):
                raise ValueError('Published quote count mismatch')
        rows.extend(detail)
        coverage.append(dict(issue=issue,status='PUBLISHED_DETAIL_VERIFIED',fixture_market_rows=len(detail)))
    return dict(issue_order=list(issues),coverage=coverage,rows=rows,source_hashes=hashes,
                detail_sources=[sources[i] for i in issues if i in sources],historical_admission=False)
