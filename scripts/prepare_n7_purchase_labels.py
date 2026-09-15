"""Prepare identity-bound outcomes only after both purchase grids pass replay.

CLI: project-python scripts/prepare_n7_purchase_labels.py CONFIG.json
Actual settlement SP remains the existing R/SQLite audit's responsibility.
"""
import csv
import hashlib
import json
from pathlib import Path
import sys

from src.temporal_learning import verify_implementation_closure
from src.strategy_diagnostic_inputs import read_verified_bundle_json
from src.fundamentals_census import read_response
from src.fundamentals_issue_pages import issue_analysis_pages
from src.fundamentals_home_away import roster_observed_results
from src.n7_purchase_labels import bind_purchase_roster_labels

cfg = json.loads(Path(sys.argv[1]).read_bytes())
root = Path(cfg['repository_root'])
sources = {}
parsed = {}
# Explicit hashes are required for every gate, catalog and old label input.
for name in ('main', 'structure', 'main_replay', 'structure_replay', 'gates', 'catalog', 'inputs'):
    binding = cfg[name]
    path = Path(binding['path'])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding['sha256']:
        raise ValueError('Gate input changed: ' + name)
    sources[str(path)] = binding['sha256']
    parsed[name] = json.loads(raw)
main, structure = parsed['main'], parsed['structure']
if main['scope'] != structure['scope'] or structure['parent_receipt_sha256'] != cfg['main']['sha256']:
    raise ValueError('Purchase grid parent or scope mismatch')
if main['scope'] != [x['issue'] for x in parsed['catalog']['issues']]:
    raise ValueError('Purchase grid/catalog scope mismatch')
if main['catalog_sha256'] != cfg['catalog']['sha256']:
    raise ValueError('Catalog differs from frozen purchase source')
for item in parsed['catalog']['issues']:
    if item['sha256'] != main['bindings'][item['issue']]['source_sha256']:
        raise ValueError('Bundle differs from frozen purchase source')
for name in ('main', 'structure'):
    receipt, proof = parsed[name], parsed[name + '_replay']
    if (receipt['status'] != 'FROZEN_NOT_SETTLED' or proof['status'] != 'PASS'
            or proof['receipt_sha256'] != cfg[name]['sha256']
            or proof['issues'] != len(receipt['scope'])
            or proof['allocations'] != len(receipt['scope']) * len(receipt['policies'])):
        raise ValueError('Incomplete independent allocation replay: ' + name)
    verify_implementation_closure(root, receipt['closure'])
    for relative, sha in receipt['code'].items():
        path = root / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('Purchase implementation changed: ' + relative)
        sources[str(path)] = sha
    for binding in receipt['bindings'].values():
        path = Path(cfg[name]['path']).parent / binding['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != binding['sha256']:
            raise ValueError('Frozen purchase file changed')
        sources[str(path)] = binding['sha256']
gate = parsed['gates']
if (gate['status'] != 'PASS' or gate['main_receipt_sha256'] != cfg['main']['sha256']
        or gate['structure_receipt_sha256'] != cfg['structure']['sha256']
        or gate['gates'] != len(structure['scope']) * len(structure['policies'])):
    raise ValueError('Incomplete independent group gate replay')
for item in parsed['catalog']['issues']:
    bundle = json.loads(read_verified_bundle_json(item['path'], item['sha256']))
    if bundle['issue'] != item['issue']:
        raise ValueError('Pre-label bundle issue mismatch')
# Only now may outcome bytes be opened.
old_path = Path(cfg['old_labels']['path'])
raw = old_path.read_bytes()
if hashlib.sha256(raw).hexdigest() != cfg['old_labels']['sha256']:
    raise ValueError('Original outcomes changed')
sources[str(old_path)] = cfg['old_labels']['sha256']
old = {}
for row in csv.DictReader(raw.decode().splitlines()):
    key = row['issue'], int(row['slot']), row['provider_id']
    if key in old:
        raise ValueError('Repeated original outcome identity')
    old[key] = row
labels, items = [], []
for item in parsed['catalog']['issues']:
    bundle = json.loads(read_verified_bundle_json(item['path'], item['sha256']))
    issue = item['issue']
    if bundle['issue'] != issue:
        raise ValueError('Bundle issue mismatch')
    sources[item['path']] = item['sha256']
    fixtures = bundle['expanded_pool']['fixtures']
    if issue in cfg['original_issues']:
        inventory, outcomes = [], []
        for fixture in fixtures:
            row = old[issue, fixture['slot'], str(fixture['provider_id'])]
            if float(row['handicap']) != fixture['handicap']:
                raise ValueError('Original handicap mismatch')
            inventory.append(dict(slot=fixture['slot'], provider_id=row['provider_id'], home=row['home'], away=row['away']))
            outcomes.append(dict(slot=fixture['slot'], actual_home=int(row['actual_home']), actual_away=int(row['actual_away']), result_state='完场'))
        cohort = 'ORIGINAL'
    else:
        path = Path(cfg['roster_directory']) / (issue + '.json')
        sha = parsed['inputs']['roster_bindings'][issue]['sha256']
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('Roster changed before parsing')
        meta, html = read_response(path)
        slots = [f['slot'] for f in fixtures]
        inventory = issue_analysis_pages(html, roster_url=meta['url'], issue=issue, slots=slots)
        outcomes = roster_observed_results(path, issue=issue, slots=slots)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('Roster changed during parsing')
        sources[str(path)] = sha
        cohort = 'ADDITIONAL'
    labels.extend(bind_purchase_roster_labels(issue, fixtures, inventory, outcomes, cohort))
    items.append({**item, 'cohort': cohort})
output = Path(cfg['output'])
output.mkdir(exist_ok=False)
(output / 'labels.json').write_text(json.dumps(labels, allow_nan=False))
(output / 'catalog.json').write_text(json.dumps({**parsed['catalog'], 'issues': items}, indent=2))
for name in ('scripts/prepare_n7_purchase_labels.py', 'src/n7_purchase_labels.py'):
    path = root / name
    sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
(output / 'receipt.json').write_text(json.dumps(dict(config=cfg, source_hashes=sources,
    files={name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ('labels.json', 'catalog.json')},
    historical_admission=False), indent=2))
print('Prepared post-freeze outcomes:', len(labels), 'fixtures across', len(items), 'issues')
