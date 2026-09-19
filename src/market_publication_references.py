"""Bounded-memory reference inventory for a frozen market publication."""
from src.n7_published_markets import read_n7_published_markets
from src.market_sqlite_retirement import market_reference_paths


def collect_publication_references(data_root, *, publication, issues, chunk_size=10):
    """Verify all requested issue views and return their protected raw paths.

    publication contains explicit path and sha256. Each chunk uses the same
    hash-bound published reader; missing coverage raises before any result is
    returned. Memory holds at most one chunk of detail rows plus path names.
    Caller owns cleaning locks, registry validation and evidence persistence.
    No network, writes, deletion or acceptance occurs here.
    """
    if (not isinstance(chunk_size,int) or isinstance(chunk_size,bool) or chunk_size<1
            or not issues or len(set(issues))!=len(issues)
            or any(not isinstance(i,str) or not i for i in issues)):
        raise ValueError('unique issues and positive chunk size required')
    protected=set()
    for offset in range(0,len(issues),chunk_size):
        selected=issues[offset:offset+chunk_size]
        result=read_n7_published_markets(data_root=data_root,merged_path=publication['path'],
            expected_sha256=publication['sha256'],issues=selected)
        coverage=result['coverage']
        if ([r['issue'] for r in coverage]!=selected or
                any(r['status']!='PUBLISHED_DETAIL_VERIFIED' for r in coverage)):
            raise ValueError('incomplete publication reference coverage')
        protected.update(market_reference_paths([],result['rows']))
        del result
    return sorted(protected)
