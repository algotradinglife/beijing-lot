"""Package already checked frozen new48 results and published prior evidence."""
import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.fundamentals_expanded_comparison import read_verified_report_archive, merge_variant_reports
from src.fundamentals_clean_receipts import verify_clean_file_bindings, verify_clean_validation_receipts
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure, verify_implementation_closure

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source', 'conflict', 'before-original', 'before-conflict', 'output', 'fixture'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    root = Path.cwd()
    out = Path(args.output)
    if out.exists() or Path(args.fixture).exists():
        raise FileExistsError('Immutable new output and fixture required')
    source, conflict = Path(args.source), Path(args.conflict)
    verify_clean_validation_receipts(source, repository_root=root)
    bindings = {}
    for directory in (source, conflict):
        frozen = json.loads((directory / 'plans-frozen.json').read_text())
        receipt = frozen['receipt']
        if stable_json_hash(receipt) != frozen['seal']:
            raise ValueError('Invalid current freeze seal')
        verify_implementation_closure(root, receipt['implementation'])
        verify_clean_file_bindings({**receipt['source_hashes'], **receipt['plan_hashes']}, repository_root=root)
        for name in ('results.json', 'plans-frozen.json'):
            path = directory / name
            bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        result = json.loads((directory / 'results.json').read_text())
        if result['freeze_seal'] != frozen['seal']:
            raise ValueError('Current result/freeze mismatch')
    old, old_seal = read_verified_report_archive(args.before_original)
    old_conflict, _ = read_verified_report_archive(args.before_conflict)
    prior_factor_paths = [p for p in old_seal['receipt']['source_hashes'] if p.endswith('/factors.json')]
    if len(prior_factor_paths) != 1:
        raise ValueError('One prior factors receipt required')
    prior_factor_path = prior_factor_paths[0]
    verify_clean_file_bindings({prior_factor_path: old_seal['receipt']['source_hashes'][prior_factor_path]}, repository_root=root)
    prior_factors = json.loads(Path(prior_factor_path).read_text())['rows']
    new_factors = json.loads((source / 'factors.json').read_text())['rows']
    prior_index = {(r['issue'], r['slot'], r['provider_id']): r for r in prior_factors}
    new_index = {(r['issue'], r['slot'], r['provider_id']): r for r in new_factors}
    if len(prior_index) != len(prior_factors) or len(new_index) != len(new_factors) or not prior_index.keys() <= new_index.keys():
        raise ValueError('Invalid factor expansion scope')
    columns = ['p_W', 'p_D', 'p_L', 'q_W', 'q_D', 'q_L']
    maximum_change = max(abs(row[c] - new_index[key][c]) for key, row in prior_index.items() for c in columns)
    bindings[prior_factor_path] = hashlib.sha256(Path(prior_factor_path).read_bytes()).hexdigest()
    current = json.loads((source / 'results.json').read_text())
    current_conflict = json.loads((conflict / 'results.json').read_text())
    before = merge_variant_reports(old['rows'], old_conflict['rows'])
    after = merge_variant_reports(current['rows'], current_conflict['rows'])
    if {(r['issue'], r['policy']) for r in before} != {(r['issue'], r['policy']) for r in after}:
        raise ValueError('Before/after scope mismatch')
    if len(after) != 48 * 72:
        raise ValueError('Expected 48 issues by 72 variants')
    for path in (args.before_original, args.before_conflict, str(source / 'prepared.json')):
        bindings[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    receipt = dict(scope='UPDATED_INPUTS_POST_EXPOSURE_RETROSPECTIVE', source_hashes=bindings,
                   generated_at=datetime.now(timezone.utc).isoformat(), budget_cny=1024,
                   unit_cny=2, payout_factor=.65, initial_capital_cny=100000,
                   expert_versions={'draw': '1.1.0', 'high_margin': '0.1.0'},
                   expert_weights={'draw': .5, 'high_margin': .5}, no_retraining=True,
                   input_comparison=dict(before=len(prior_index), after=len(new_index),
                                         common=len(prior_index), maximum_probability_change=maximum_change),
                   implementation=implementation_closure(root, ['scripts.package_expanded_comparison']))
    receipt['report_files'] = {
        p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
        ['r/fundamentals_expanded_comparison.R', 'r/fundamentals_repeated_double.R',
         'r/fundamentals_compression_bridge.R', 'r/fundamentals_integration_weight.R',
         'quarto/75_expanded_new48_variants.qmd']}
    seal = stable_json_hash(receipt)
    prepared = json.loads((source / 'prepared.json').read_text())
    payload = dict(rows=after, before=before, readiness_before=old['readiness'],
                   readiness_after=prepared['readiness'], freeze_seal=seal)
    out.mkdir(parents=True)
    files = {'results.json': json.dumps(payload, indent=2),
             'plans-frozen.json': json.dumps(dict(receipt=receipt, seal=seal), indent=2)}
    for name, body in files.items():
        (out / name).write_text(body)
    archive = dict(files=files, hashes={n: hashlib.sha256(b.encode()).hexdigest() for n, b in files.items()})
    Path(args.fixture).write_bytes(gzip.compress(json.dumps(archive).encode(), mtime=0))
    print('PACKAGED', len(before), len(after), 'paired rows', flush=True)
