"""Read-only verification of post-forecast validation dependency receipts."""
import hashlib
import json
from pathlib import Path
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_draw_versions import read_draw_version


def verify_clean_file_bindings(bindings, *, repository_root):
    """Verify path->SHA256 bindings, streaming large files; missing/mutated fail.

    Relative paths resolve against the explicit repository root. No writes.
    """
    for name, expected in bindings.items():
        path = Path(name)
        if not path.is_absolute():
            path = Path(repository_root) / path
        with path.open('rb') as handle:
            actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('Changed receipt dependency: ' + name)


def verify_clean_validation_receipts(study, *, repository_root):
    """Follow frozen prediction/catalog/import and settlement bindings read-only.

    This verifies an existing diagnostic artifact, never learns or selects.
    Requires its exact external catalogs, runtimes, sources and SQLite snapshot;
    archived report-only fixtures cannot pass full replay verification.
    """
    root = Path(repository_root).resolve()
    study = Path(study).resolve()
    signal = json.loads((study / 'signals/receipt.json').read_text())
    catalog = study / 'signals/catalog.json'
    verify_clean_file_bindings({**signal['files'], str(catalog): signal['catalog_sha256'],
        'config/expert_versions/draw.json': signal['original_catalog_sha256'],
        'scripts/predict_clean_validation.py': signal['implementation_sha256']}, repository_root=root)
    releases = {v: read_draw_version(catalog, v, repository_root=root) for v in ('0.1.0', '1.1.0')}
    for path in signal['files']:
        payload = json.loads((root / path).read_text())
        for attrs in payload['receipts'].values():
            receipt = attrs['prediction_receipt']
            if stable_json_hash(receipt) != attrs['prediction_seal']:
                raise ValueError('Changed prediction seal')
            if receipt['catalog_seal'] != releases[receipt['version']]['catalog_seal']:
                raise ValueError('Prediction catalog mismatch')
            verify_clean_file_bindings(receipt['imported_sources'], repository_root=root)
    factors = json.loads((study / 'factors.json').read_text())
    verify_clean_file_bindings(factors['implementation'], repository_root=root)
    verify_clean_file_bindings({str(study / name): factors['source_hashes'][key]
        for key, name in [('prepared', 'prepared.json'), ('projected', 'projected/receipt.json'),
                          ('signals', 'signals/receipt.json')]}, repository_root=root)
    result = json.loads((study / 'results.json').read_text())
    verify_clean_file_bindings({'scripts/settle_clean_validation.py': result['implementation_sha256'],
        str(study / 'settlement-audit.json'): result['audit_sha256']}, repository_root=root)
    audit = json.loads((study / 'settlement-audit.json').read_text())['receipt']
    verify_clean_file_bindings({**audit['implementation'], audit['db_path']: audit['db_sha256'],
        str(study / 'labels.json'): audit['labels_sha256'],
        str(study / 'plans-frozen.json'): audit['plans_sha256']}, repository_root=root)
    return True
