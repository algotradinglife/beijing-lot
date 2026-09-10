"""Compact R-facing context without discarding the original audit artifact."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from src.fundamentals_bulk_capture import atomic_json


def project_feature_context(source_path, output_path):
    """Verify a sealed full context and persist a small feature-facing view.

    Preserve every feature row, selected history identity/date/score, cutoff,
    source hash and code hash. This view is only for expert_feature_table.
    Repeated per-window receipts remain in the immutable original, bound by
    its file hash; they are not copied into R's feature computation. No network
    or learning. Existing unequal outputs, corrupt seals and in-place writes
    fail. Returns the output path; writes only the declared derived file.
    """
    source = Path(source_path); output = Path(output_path)
    if source.resolve() == output.resolve():
        raise ValueError('Preserve the original context')
    raw = source.read_bytes(); full = json.loads(raw)
    canonical = json.loads(full['canonical_json'])
    if hashlib.sha256(full['canonical_json'].encode()).hexdigest() != full['seal'] or any(full[k] != v for k,v in canonical.items()):
        raise ValueError('Original context seal or content changed')
    projected = {k:v for k,v in canonical.items() if k != 'receipts'}
    history_fields = ('history_id','event_date','home_id','away_id','home_goals','away_goals','raw_sha256','source')
    projected['receipts'] = [dict(issue=r['issue'],slot=r['slot'],provider_id=r['provider_id'],
        views={name: {'rows':[{k:row[k] for k in history_fields if k in row} for row in view['rows']]}
               for name,view in r['views'].items()}) for r in canonical['receipts']]
    projected['input_file_hashes'] = dict(projected['input_file_hashes'])
    projected['input_file_hashes'][str(source.resolve())] = hashlib.sha256(raw).hexdigest()
    projected['implementation_hashes'] = dict(projected['implementation_hashes'])
    projected['implementation_hashes']['src/context_projection.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    projected['projection'] = 'FEATURE_ROWS_UNCHANGED_FULL_WINDOW_RECEIPTS_IN_BOUND_ORIGINAL'
    encoded = json.dumps(projected,ensure_ascii=False,separators=(',',':'))
    result = dict(projected,canonical_json=encoded,seal=hashlib.sha256(encoded.encode()).hexdigest())
    if output.exists():
        if json.loads(output.read_text()) != result:
            raise ValueError('Frozen projected context changed')
    else:
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.context-projection-',dir=output.parent) as directory:
            staged = Path(directory)/'context.json'
            atomic_json(staged,result)
            os.replace(staged,output)
    return str(output)
