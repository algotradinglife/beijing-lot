"""Domain source-identity checks for paired residual-cash research."""
import hashlib
import json
from pathlib import Path


def verify_refill_sources(directory, expected_receipt_sha):
    """Verify #447 receipt and every bound member before reading candidate data.

    Returns the verified receipt. Paths and expected SHA256 are explicit.
    Missing/replaced members raise; reads bytes only, no writes or learning.
    """
    root=Path(directory);raw=(root/'prediction-freeze.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_receipt_sha:
        raise ValueError('Refill receipt identity mismatch')
    receipt=json.loads(raw)
    for name,sha in receipt['files'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:
            raise ValueError('Refill member identity mismatch: '+name)
    return receipt


def verify_paired_audit(directory, reference_receipt):
    """Require the exact audit bytes consumed by #447 control settlement.

    Only call after decision freeze: audit snapshot contains outcomes/SP.
    A relocated identical snapshot is allowed; revised internally valid audits
    fail. Returns verified supplied-path hashes; no writes or label selection.
    """
    root=Path(directory);reference=Path(reference_receipt['audit_study']);verified={}
    for name in ['plans-frozen.json','audit-snapshot.json','evaluation-receipt.json']:
        path=root/name;sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if sha!=reference_receipt['settlement_inputs'][str(reference/name)]:
            raise ValueError('Paired audit identity mismatch: '+name)
        verified[str(path)]=sha
    return verified
