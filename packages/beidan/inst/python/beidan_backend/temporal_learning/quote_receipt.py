"""Validate serialized diagnostic quote-admission receipts at publication."""
import pandas as pd
from .core import Cutoff, TemporalContractError, utc


def validate_quote_admission_receipt(envelope: dict, cutoff: Cutoff,
                                     admitted_rows: int, implementation_hashes: dict) -> None:
    """Fail closed on missing/mismatched inner shared evidence context.

    Explicit cutoff is the original shared decision epoch; envelope is the R
    inspector's exported per-fixture admission receipt. Nonempty admitted quotes
    require complete inner shared metadata, matching cutoff/target issue,
    historical proxy availability, source/label maxima strictly before cutoff,
    equal implementation file maps and a bound cache/history identity. Zero
    admitted rows may carry an explicit NO_PRIOR_QUOTES/NO_SOURCE_QUOTES state;
    missing evidence is never allowed for a nonempty prior selection.
    No IO, fitting, selection, timestamp inference, or changed receipt on return.
    """
    if not isinstance(cutoff,Cutoff) or cutoff.kind!='DECISION_EPOCH' or type(admitted_rows) is not int or admitted_rows<0:
        raise TemporalContractError('Explicit quote cutoff/count required')
    if not isinstance(envelope,dict) or not isinstance(implementation_hashes,dict) or not implementation_hashes:
        raise TemporalContractError('Bound quote receipt and implementation required')
    outer=envelope.get('cutoff',{})
    stamp=pd.Timestamp(outer.get('cutoff_utc'))
    if stamp.tzinfo is None or utc(stamp)!=cutoff.cutoff_ts or outer.get('issue_id')!=cutoff.target_issue:
        raise TemporalContractError('Outer quote cutoff differs')
    shared=envelope.get('shared')
    if admitted_rows==0:
        if envelope.get('admission_state') not in {'NO_PRIOR_QUOTES','NO_SOURCE_QUOTES'}:
            raise TemporalContractError('Explicit empty admission state required')
        return
    required={'cutoff_identity','cutoff_kind','cutoff_ts','target_issue','implementation',
              'implementation_hashes','source_hashes','cache_key','admitted_history_sha256',
              'availability','maximum_source_time','maximum_training_label_timestamp'}
    if envelope.get('admission_state')!='PRIOR_PROXY_QUOTES' or not isinstance(shared,dict) or not required<=set(shared):
        raise TemporalContractError('Complete inner shared quote receipt required')
    inner=pd.Timestamp(shared['cutoff_ts'])
    if inner.tzinfo is None or utc(inner)!=cutoff.cutoff_ts or shared['cutoff_identity']!=cutoff.identity or shared['cutoff_kind']!=cutoff.kind or shared['target_issue']!=cutoff.target_issue:
        raise TemporalContractError('Inner shared cutoff/issue differs')
    availability=shared['availability'];policy=availability.get('policy',{})
    if availability.get('intended_use')!='HISTORICAL_DIAGNOSTIC' or policy.get('kind')!='HISTORICAL_PROXY' or policy.get('prospective_capable') is not False:
        raise TemporalContractError('Diagnostic quote availability required')
    for field in ['maximum_source_time','maximum_training_label_timestamp']:
        maximum=pd.Timestamp(shared[field])
        if maximum.tzinfo is None or not utc(maximum)<cutoff.cutoff_ts:
            raise TemporalContractError('Inner quote chronology exceeds cutoff')
    files=shared['implementation'].get('files')
    if not isinstance(files,dict) or not files or shared['implementation_hashes']!=files or any(implementation_hashes.get(path)!=sha for path,sha in files.items()):
        raise TemporalContractError('Inner shared implementation binding differs')
    hashes=[shared['cache_key'],shared['admitted_history_sha256'],*files.values()]
    if not isinstance(shared['source_hashes'],dict) or not shared['source_hashes']:
        raise TemporalContractError('Inner source binding required')
    hashes.extend(shared['source_hashes'].values())
    if not all(isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for v in hashes):
        raise TemporalContractError('Inner SHA256 identities required')
