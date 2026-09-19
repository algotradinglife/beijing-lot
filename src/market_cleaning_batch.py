"""Prepare market-only offline audit inputs; never read analysis completion flags."""
import json
import hashlib
from pathlib import Path
from src.temporal_learning.core import utc
from src.fundamentals_census import read_response
from src.fundamentals_market_history import verify_market_receipt, verify_selected_market_receipt
from src.nowscore_settlement import parse_page


def prepare_market_batch(root, plan_path, receipt_root, output):
    """Bind frozen reused scopes and receipts to an offline market audit.

    All paths are explicit, within repository_root. Original bytes are read only.
    Output must not exist. Missing or conflicting evidence raises ValueError.
    Returns the generated manifest; no fetching or analysis-page access occurs.
    """
    root = Path(root).resolve()
    plan_path, receipt_root, output = [root / p for p in (plan_path, receipt_root, output)]
    if output.exists():
        raise ValueError('Output already exists')
    plan = json.loads(plan_path.read_text())
    native = root / plan['inventory_path']
    if hashlib.sha256(native.read_bytes()).hexdigest() != plan['inventory_sha256']:
        raise ValueError('Inventory hash mismatch')
    issues = [e['issue'] for e in json.loads(native.read_text())['issues']]
    scopes = plan['reused_issues']
    if plan['batches'] or [s['issue'] for s in scopes] != issues or len(set(issues)) != len(issues):
        raise ValueError('Expected complete unique reused issue scope')
    hashes = {p.resolve().relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (plan_path, native)}
    fixtures, inventories, audit = [], [], []
    for scope in scopes:
        issue = scope['issue']
        roster = root / scope['roster_path']
        if hashlib.sha256(roster.read_bytes()).hexdigest() != scope['roster_sha256']:
            raise ValueError('Roster hash mismatch')
        meta, raw = read_response(roster)
        parsed = parse_page(raw, issue, 8)
        by_slot = {r['slot']: r for r in parsed}
        if len(by_slot) != len(parsed):
            raise ValueError('Duplicate roster slot')
        excluded = scope.get('quarantined_slots', [])
        declared = scope['fixtures']
        slots=[f['slot'] for f in declared+excluded]
        if len(slots)!=len(set(slots)):
            raise ValueError('Duplicate declared roster slot')
        if {r['slot'] for r in declared} & {r['slot'] for r in excluded} or {r['slot'] for r in declared + excluded} != set(by_slot):
            raise ValueError('Roster coverage mismatch')
        current = []
        for f in declared + excluded:
            if by_slot[f['slot']]['native_match_id'] != f['provider_id']:
                raise ValueError('Fixture identity mismatch')
        for f in declared:
            current.append(dict(f, decision_ts=utc(by_slot[f['slot']]['cutoff_text'].replace('截止时间：', '').replace('截止时间:', '').strip() + '+08:00').isoformat()))
        inventories.append(dict(issue=issue, roster_path=roster.resolve().relative_to(root).as_posix(),
            fixture_count=len(current), original_fixture_count=len(parsed),
            cutoffs={str(f['slot']):f['decision_ts'] for f in current}, identity_exclusions=excluded))
        fixtures.extend(current)
        rp = receipt_root / (issue + '-receipt.json')
        receipt = json.loads(rp.read_text())
        if receipt['issue'] != issue or receipt['state'] != 'CAPTURE_ATTEMPTED':
            raise ValueError('Invalid capture receipt')
        expected = {(f['slot'],m,f['provider_id']) for f in current for m in ('euro','total')}
        actual = [(r['slot'],r['market'],r['provider_id']) for r in receipt['rows']]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError('Market coverage mismatch')
        for r in receipt['rows']:
            p = root / r['path']
            if 'storage' in r:
                verify_selected_market_receipt(r,r['market']+':'+r['provider_id'])
            else:
                verify_market_receipt(p, r['market']+':'+r['provider_id'], r['sha256'])
            hashes[p.resolve().relative_to(root).as_posix()] = r['sha256']
            audit.append(dict(issue=issue,slot=r['slot'],market=r['market'],provider_id=r['provider_id'],
                path=p.resolve().relative_to(root).as_posix(),capture_sha256=r['sha256'],
                status='TRANSPORT_FAILURE' if r['state']=='TRANSPORT_FAILURE' else r['status'],
                **({'storage':r['storage']} if 'storage' in r else {})))
        hashes.update({p.resolve().relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (rp,roster)})
    payloads = dict(scope=dict(issues=issues,inventories=inventories,fixtures=fixtures,source_hashes=hashes),
        audit=audit,followup=dict(nowscore_comparison=[],retries=[]),recovery=[],decisions=[])
    output.mkdir(parents=True)
    outputs = {}
    for name,payload in payloads.items():
        p = output / (name+'.json')
        p.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False))
        outputs[name] = dict(path=p.resolve().relative_to(root).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    manifest = dict(issues=issues,source_inputs=outputs,outputs=outputs,historical_admission=False)
    (output/'input-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False))
    return manifest


def snapshot_market_anomalies(audit_path, output_path):
    """Write an explicitly partial anomaly ledger from completed per-issue files.

    Reads only numbered issue JSON files. Each row retains source evidence.
    Missing summary means running, never acceptance. Returns the ledger.
    """
    audit_path, output_path = Path(audit_path), Path(output_path)
    files = sorted(p for p in audit_path.glob('*.json') if p.stem.isdigit())
    rows, hashes = [], {}
    for path in files:
        payload = path.read_bytes()
        records = json.loads(payload)
        if any(r['issue'] != path.stem for r in records):
            raise ValueError('Audit issue identity mismatch')
        hashes[path.name] = hashlib.sha256(payload).hexdigest()
        rows.extend({k:v for k,v in r.items() if k not in ('rows','window')}
                    for r in records if r['status'] != 'QUOTES_PRIOR_DIAGNOSTIC')
    ledger = dict(state='PARTIAL_DIAGNOSTIC_SNAPSHOT', completed_issue_files=len(files),
                  input_hashes=hashes, rows=rows, historical_admission=False)
    output_path.write_text(json.dumps(ledger, ensure_ascii=False, allow_nan=False))
    return ledger


def replay_market_decisions(root, decisions_path, output_path):
    """Replay exact corrections from hash-bound raw evidence into a new file.

    Does not modify raw data or accept the batch. Requires all hashes to match;
    each returned market row retains its correction receipt and source hashes.
    """
    from src.fundamentals_scope_market import audit_fixture_market
    from src.fundamentals_census import decode_analysis_text
    from src.fundamentals_titan_euro import parse_titan_euro
    from src.fundamentals_titan_total import parse_titan_total_html
    from src.temporal_learning import Cutoff
    from src.temporal_learning.provenance import implementation_closure
    root = Path(root).resolve()
    output = root / output_path
    if output.exists():
        raise ValueError('Output already exists')
    decisions = json.loads((root / decisions_path).read_text())
    keys = [(d['issue'],d['slot'],d['market']) for d in decisions]
    if not decisions or len(keys) != len(set(keys)):
        raise ValueError('Invalid decision identities')
    closure = implementation_closure(root, ('src.market_cleaning_batch',))['files']
    rows = []
    for decision in decisions:
        if any(decision.get(k) not in decision['files'] for k in ('roster_path','capture_path')):
            raise ValueError('Consumed decision inputs must be hash-bound')
        for name, digest in decision['files'].items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
                raise ValueError('Decision evidence hash mismatch')
        _, raw = read_response(root/decision['roster_path'])
        fixtures = [f for f in parse_page(raw,decision['issue'],8) if f['slot']==decision['slot']]
        if len(fixtures)!=1:
            raise ValueError('Decision roster identity mismatch')
        meta, raw = read_response(root/decision['capture_path'])
        if meta['status'] != 200:
            raise ValueError('Decision capture unavailable')
        market = decision['market']
        parsed = parse_titan_euro(decode_analysis_text(raw)[0]) if market=='euro' else parse_titan_total_html(raw.decode('utf-8'))
        row = audit_fixture_market(fixtures[0],parsed,market=market,
            cutoff=Cutoff.decision_epoch(decision['issue'],decision['cutoff_utc']),
            source_hashes=decision['files'],implementation_hashes=closure,decision=decision)
        row.update(capture_path=decision['capture_path'],source_hashes=decision['files'])
        rows.append(row)
    output.write_text(json.dumps(rows,ensure_ascii=False,allow_nan=False))
    return rows


def merge_market_audits(root, summaries, output_path):
    """Merge disjoint, hash-verified diagnostic market batches into a manifest.

    summaries is a list of explicit path/sha256 dictionaries. Does not declare
    acceptance or upgrade historical availability. Per-issue payloads stay at
    their immutable source locations; the merged index binds their hashes.
    """
    root = Path(root).resolve()
    output = root / output_path
    if output.exists():
        raise ValueError('Output already exists')
    if not summaries:
        raise ValueError('No audit inputs')
    issues, rows, sources = [], [], []
    seen = set()
    for entry in summaries:
        path = root / entry['path']
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Summary hash mismatch')
        summary = json.loads(raw)
        if summary['historical_admission'] is not False:
            raise ValueError('Expected diagnostic audit')
        current = [i['issue'] for i in summary['issues']]
        if len(current) != len(set(current)) or seen.intersection(current):
            raise ValueError('Overlapping issue scope')
        if set(summary['output_hashes']) != {i+'.json' for i in current}:
            raise ValueError('Incomplete issue files')
        actual = []
        for issue in current:
            name = issue+'.json'
            source = path.parent/name
            payload = source.read_bytes()
            if hashlib.sha256(payload).hexdigest() != summary['output_hashes'][name]:
                raise ValueError('Issue output hash mismatch')
            records = json.loads(payload)
            if any(r['issue'] != issue for r in records):
                raise ValueError('Issue output identity mismatch')
            actual.extend({k:v for k,v in r.items() if k not in ('rows','window','source_hashes')} for r in records)
            sources.append(dict(issue=issue,path=source.relative_to(root).as_posix(),sha256=summary['output_hashes'][name]))
        if actual != summary['rows']:
            raise ValueError('Summary rows differ from issue files')
        scope_path=root/entry['scope_path']
        scope_key=scope_path.relative_to(root).as_posix()
        scope_raw=scope_path.read_bytes()
        if summary['source_hashes'].get(scope_key)!=hashlib.sha256(scope_raw).hexdigest():
            raise ValueError('Unbound frozen scope')
        scope=json.loads(scope_raw)
        expected={(f['issue'],f['slot'],f['provider_id'],m) for f in scope['fixtures'] for m in ('euro','total')}
        keys = [(r['issue'],r['slot'],r['provider_id'],r['market']) for r in actual]
        if set(keys)!=expected or len(scope['fixtures'])!=summary['fixture_count']:
            raise ValueError('Incomplete frozen fixture market coverage')
        if len(keys)!=len(set(keys)) or len(actual)!=summary['fixture_market_rows']:
            raise ValueError('Invalid market row coverage')
        seen.update(current)
        issues.extend(current)
        rows.extend(actual)
    result = dict(state='MERGED_DIAGNOSTIC_AUDITS_PENDING_ACCEPTANCE',issues=issues,
                  fixture_market_rows=len(rows),rows=rows,issue_sources=sources,
                  input_summaries=summaries,historical_admission=False)
    output.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return result


def apply_market_decisions(root, audit_path, decisions_path, output_path):
    """Create a complete corrected audit by replaying exact bound decisions.

    Verifies original per-issue hashes before applying replacements. Unaffected
    records are copied unchanged. Output must not exist; no raw writes occur.
    """
    from collections import Counter
    from tempfile import TemporaryDirectory
    root = Path(root).resolve()
    audit, out = root/audit_path, root/output_path
    if out.exists():
        raise ValueError('Output already exists')
    summary = json.loads((audit/'summary.json').read_text())
    original = {}
    for name,digest in summary['output_hashes'].items():
        raw = (audit/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Audit output hash mismatch')
        original[name]=json.loads(raw)
    with TemporaryDirectory(dir=root/'data/derived') as staging:
        replay_path = Path(staging)/'replay.json'
        corrected = replay_market_decisions(root, decisions_path, replay_path)
    patches={(r['issue'],r['slot'],r['market']):r for r in corrected}
    available={(r['issue'],r['slot'],r['market']) for rs in original.values() for r in rs}
    if not patches.keys()<=available:
        raise ValueError('Decision outside audit scope')
    decisions_by_key={(d['issue'],d['slot'],d['market']):d for d in json.loads((root/decisions_path).read_text())}
    originals={(r['issue'],r['slot'],r['market']):r for rs in original.values() for r in rs}
    for key, row in patches.items():
        before=originals[key]
        if any(row.get(k)!=before.get(k) for k in ('provider_id','cutoff_utc','original_status')):
            raise ValueError('Correction changes frozen fixture context')
        roster_path=decisions_by_key[key]['roster_path']
        roster_hashes={roster_path:before['source_hashes'][roster_path]} if roster_path in before['source_hashes'] else {}
        if not roster_hashes or any(row['source_hashes'].get(p)!=h for p,h in roster_hashes.items()):
            raise ValueError('Correction changes frozen roster evidence')
        expected_ids=before.get('roster_ids')
        if expected_ids is None:
            _,raw=read_response(root/roster_path)
            fixtures=[f for f in parse_page(raw,key[0],8) if f['slot']==key[1] and f['native_match_id']==before['provider_id']]
            if len(fixtures)!=1:
                raise ValueError('Replacement roster identity mismatch')
            expected_ids=[fixtures[0]['home_id'],fixtures[0]['away_id']]
        if row.get('roster_ids')!=expected_ids:
            raise ValueError('Correction changes frozen roster identity')
    out.mkdir()
    rows, issues, hashes = [], [], {}
    for info in summary['issues']:
        name=info['issue']+'.json'
        rs=[patches.get((r['issue'],r['slot'],r['market']),r) for r in original[name]]
        p=out/name
        p.write_text(json.dumps(rs,ensure_ascii=False,allow_nan=False))
        hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        rows.extend({k:v for k,v in r.items() if k not in ('rows','window','source_hashes')} for r in rs)
        issues.append(dict(info,counts=dict(Counter(r['status'] for r in rs))))
    summary.update(rows=rows,issues=issues,output_hashes=hashes,counts=dict(Counter(r['status'] for r in rows)))
    decision_file=root/decisions_path
    summary['source_hashes'][str(decision_file.relative_to(root))]=hashlib.sha256(decision_file.read_bytes()).hexdigest()
    summary['source_hashes'][str((audit/'summary.json').relative_to(root))]=hashlib.sha256((audit/'summary.json').read_bytes()).hexdigest()
    for r in corrected:
        summary['source_hashes'].update(r['source_hashes'])
    from src.temporal_learning.provenance import implementation_closure
    summary['implementation_hashes'].update(implementation_closure(root,('src.market_cleaning_batch',))['files'])
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,allow_nan=False))
    return summary
