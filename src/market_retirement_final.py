"""Compose final review, content, consumer and reference retirement gates."""
import hashlib
import json
from pathlib import Path

from src.market_retirement_gate import verify_retirement_content
from src.market_retirement_consumers import verify_retirement_collector
from src.market_retirement_membership import verify_reference_membership
from src.market_retirement_relocations import protect_relocated_paths
from src.market_sqlite_batch import verified_market_json
from src.market_sqlite_query import query_market_records
from src.market_sqlite_retirement import verify_retirement_reference_exclusion
from src.temporal_learning.provenance import implementation_closure


def verify_final_retirement(data_root, project_root, plan, *, bundle, review):
    """Verify a reviewed frozen evidence bundle under caller-owned writer locks.

    Final Codex review must bind this whole bundle, current transitive code and
    exact plan. Reference inventory coverage is part of that final review; scoped
    component reviews are rejected. No writes/deletion occur here. The command
    must also hold cleaning and worker locks throughout execution and bind its
    own implementation in review.command_hashes.
    """
    root = Path(data_root).resolve(strict=True)
    project = Path(project_root).resolve(strict=True)
    encoded = json.dumps(bundle, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if (review.get('state') != 'FINAL_RETIREMENT_REVIEW_PASSED' or review.get('findings') != [] or
            review.get('bundle_sha256') != hashlib.sha256(encoded).hexdigest()):
        raise ValueError('final retirement review required')
    code = implementation_closure(project, ('scripts.retire_market_sqlite_batch',))['files']
    for name in list(code):
        for parent in Path(name).parents:
            initializer = project / parent / '__init__.py'
            if parent != Path('.') and initializer.is_file():
                code[str(initializer.relative_to(project))] = hashlib.sha256(initializer.read_bytes()).hexdigest()
    if review.get('implementation_hashes') != code:
        raise ValueError('retirement implementation changed')
    required = {'plan', 'acceptance', 'deployment', 'index', 'references', 'snapshots', 'program_manifest_sha256', 'reference_membership', 'effective_configuration'}
    if set(bundle) != required or not bundle['references'] or not bundle['snapshots']:
        raise ValueError('complete retirement bundle required')
    documents = {}
    for role in ('plan', 'acceptance', 'deployment', 'index'):
        ref = bundle[role]
        path = (root / ref['path']).resolve(strict=True)
        path.relative_to(root)
        documents[role] = verified_market_json(path, ref['sha256'])
    if documents['plan'] != plan or plan.get('batch_id') != documents['acceptance'].get('batch_id'):
        raise ValueError('reviewed retirement plan mismatch')
    verify_reference_membership(root, bundle['reference_membership'])
    protected = set()
    snapshots = dict(bundle['snapshots'])
    for ref in bundle['references']:
        path = (root / ref['path']).resolve(strict=True)
        path.relative_to(root)
        proof = verified_market_json(path, ref['sha256'])
        protected.update(proof['protected_paths'])
        snapshots[str(path.relative_to(root))] = ref['sha256']
    if 'relocation' in plan:
        ref = plan['relocation']
        path = (root / ref['path']).resolve(strict=True)
        path.relative_to(root)
        mappings = verified_market_json(path, ref['sha256'])
        snapshots[str(path.relative_to(root))] = ref['sha256']
        accepted = documents['acceptance']
        captures = []
        for issue in accepted['issues']:
            captures.extend(query_market_records(accepted['database'], issue=issue, kind='capture'))
        protected = protect_relocated_paths(
            protected, mappings, original_root=ref['original_root'], data_root=root,
            captures=captures)
    for path in ('registry/markets-current.json', documents['index']['index_path']):
        relative = str((root / path).resolve(strict=True).relative_to(root))
        if relative not in snapshots:
            raise ValueError('active consumer snapshot missing')
    references = verify_retirement_reference_exclusion(root, plan, snapshots=snapshots, protected_paths=protected)
    consumers = verify_retirement_collector(root, deployment=documents['deployment'],
        index_evidence=documents['index'], program_manifest_sha256=bundle['program_manifest_sha256'],
        effective_configuration=bundle['effective_configuration'])
    content = verify_retirement_content(root, plan, acceptance_reference=bundle['acceptance'])
    return dict(state='FINAL_RETIREMENT_GATES_PASSED', batch_id=plan['batch_id'],
                content=content, consumers=consumers, references=references)
