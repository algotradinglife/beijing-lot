"""Resume only complete byte-bound allocations; never overwrite partial work."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

import pytest


@pytest.mark.parametrize('mutation',['none','funded','source','partial'])
def test_expanded_dispatch_resume(tmp_path,monkeypatch,mutation):
    inputs=tmp_path/'inputs';inputs.mkdir();(inputs/'input-receipt.json').write_text('{"batches":[{}]}')
    batch=tmp_path/'batch-000';batch.mkdir();(batch/'batch-receipt.json').write_text('{}')
    cat=batch/'catalog.json';cat.write_text('{}')
    output=batch/'allocations';output.mkdir()
    source=tmp_path/'source';source.write_text('original')
    funded=output/'funded.csv';funded.write_text('original')
    config=dict(study=str(tmp_path),repository_root=str(Path.cwd()),python=sys.executable,rscript='unused')
    cp=tmp_path/'config.json';cp.write_text(json.dumps(config));tp=tmp_path/'template.json';tp.write_text('{}')
    (batch/'allocation-config.json').write_text(json.dumps(dict(catalog=str(cat),catalog_sha256=hashlib.sha256(cat.read_bytes()).hexdigest(),output_dir=str(output))))
    freeze=dict(files={'funded.csv':hashlib.sha256(funded.read_bytes()).hexdigest()},
                source_hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()},implementation={})
    fp=output/'plans-frozen.json';fp.write_text(json.dumps(freeze))
    (output/'prediction-replay.json').write_text(json.dumps(dict(status='PASS',freeze_sha256=hashlib.sha256(fp.read_bytes()).hexdigest(),implementation={})))
    if mutation=='funded':funded.write_text('changed')
    if mutation=='source':source.write_text('changed')
    if mutation=='partial':fp.unlink()
    monkeypatch.setattr(sys,'argv',['dispatch',str(cp),str(tp),'0'])
    if mutation=='none':runpy.run_path('scripts/run_n7_expanded_allocation_batches.py',run_name='__main__')
    else:
        with pytest.raises(ValueError):runpy.run_path('scripts/run_n7_expanded_allocation_batches.py',run_name='__main__')
    assert funded.read_text()==('changed' if mutation=='funded' else 'original')
