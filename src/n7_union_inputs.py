"""Bind #439 prediction catalogs to rank provenance and shared code identity.

No fitting, chronology construction, label CSV reading, network, or writes.
"""
import gzip
import hashlib
import json
from pathlib import Path

from src.temporal_learning import implementation_closure, verify_implementation_closure


def bind_union_inputs(catalog_path, rank_dir, repository_root):
    """Return JSON binding exact catalog bytes, rank receipt and source cutoffs.

    All paths explicit. Mismatched/ambiguous source identities raise ValueError.
    Rank receipt metadata is read; actual ranks and payouts are not loaded.
    """
    catalog_raw=Path(catalog_path).read_bytes()
    catalog=json.loads(catalog_raw)
    rank_raw=(Path(rank_dir)/'receipt.json').read_bytes()
    rank=json.loads(rank_raw)
    sources=[]
    for item in rank['sources']:
        path=Path(item['study'])/'plans-frozen.json'
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if sha!=item['freeze_sha256'] or catalog['bindings'].get(str(path))!=sha:
            raise ValueError('rank/catalog source freeze mismatch')
        frozen=json.loads(raw)
        if frozen['seal']!=item['seal']:
            raise ValueError('rank source seal mismatch')
        sources.append(frozen['receipt'])
    clocks={}
    for item in catalog['issues']:
        issue=item['issue']
        owners=[s for s in sources if issue in s['issues']]
        if len(owners)!=1 or issue in clocks:
            raise ValueError('ambiguous issue source')
        owner=owners[0]
        if owner['source_hashes'].get(item['path'])!=item['sha256']:
            raise ValueError('rank/catalog probability bundle mismatch')
        raw=Path(item['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('catalog bundle bytes changed')
        bundle=json.loads(gzip.decompress(raw))
        if bundle['issue']!=issue or bundle['cutoffs']!=owner['cutoffs'][issue]:
            raise ValueError('source issue/cutoff mismatch')
        clocks[issue]=bundle['cutoffs']
    closure=implementation_closure(Path(repository_root),
        ['src.n7_union_inputs','src.fundamentals_n7_baseline','src.temporal_learning'],
        distributions=['numpy','pandas'])
    return json.dumps(dict(catalog_sha256=hashlib.sha256(catalog_raw).hexdigest(),
        rank_receipt_sha256=hashlib.sha256(rank_raw).hexdigest(),
        ranks_sha256=rank['outputs']['ranks.csv'],cutoffs=clocks,
        python_implementation=closure),sort_keys=True,separators=(',',':'))


def verify_union_binding(binding,catalog_path,rank_dir,repository_root):
    """Recheck an immutable binding; fail on source, cutoff or code mutation."""
    parsed=json.loads(binding)
    verify_implementation_closure(Path(repository_root),parsed['python_implementation'])
    if binding!=bind_union_inputs(catalog_path,rank_dir,repository_root):
        raise ValueError('union input binding changed')
    return True
