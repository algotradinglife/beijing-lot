"""Fixed retrospective windows. Never an admission path for historical decisions."""
from dataclasses import asdict
from datetime import datetime
import copy
import json
from zoneinfo import ZoneInfo

from .core import Cutoff, TemporalContractError, stable_json_hash, utc


def diagnostic_quote_window(rows, *, cutoff, source_hashes, implementation_hashes):
    """Filter timestamped target-market quotes, NOT outcomes or learning rows.

    Unique quote_id and timezone-aware quoted_at are mandatory. Source clocks
    are historical proxies, never proof of availability. Keep strictly prior
    quotes; no replacement by untimed opening prices. Pure, receipt-bound.
    """
    if not isinstance(cutoff, Cutoff) or cutoff.kind != 'DECISION_EPOCH':
        raise TemporalContractError('Explicit decision cutoff required')
    if not source_hashes or not implementation_hashes:
        raise TemporalContractError('Source and implementation hashes required')
    ids = [r['quote_id'] for r in rows]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise TemporalContractError('Unique quote IDs required')
    for row in rows:
        if datetime.fromisoformat(row['quoted_at'].replace('Z', '+00:00')).tzinfo is None:
            raise TemporalContractError('Timezone-aware quote timestamp required')
    selected = [r for r in rows if utc(r['quoted_at']) < cutoff.cutoff_ts]
    receipt = dict(cutoff_identity=cutoff.identity, cutoff_ts=cutoff.cutoff_ts.isoformat(),
        target_issue=cutoff.target_issue, historical_admission=False,
        evidence_class='HISTORICAL_PROXY', intended_use='RETROSPECTIVE_DESCRIPTION_ONLY',
        maximum_source_availability=None, maximum_label_availability=None,
        maximum_quote_time=max((utc(r['quoted_at']).isoformat() for r in selected), default=None),
        excluded_same_or_later=len(rows)-len(selected), selected_ids=[r['quote_id'] for r in selected],
        source_hashes=source_hashes, implementation_hashes=implementation_hashes,
        input_sha256=stable_json_hash(rows), selected_sha256=stable_json_hash(selected))
    receipt_json = json.dumps(receipt,sort_keys=True,separators=(',',':'))
    receipt['identity'] = stable_json_hash(receipt)
    return dict(rows=copy.deepcopy(selected), receipt=receipt,receipt_json=receipt_json)


def diagnostic_date_window(rows, *, cutoff, window, minimum, timezone, excluded_ids,
                           source_hashes, implementation_hashes):
    """Select last N dated observations for descriptive replay only.

    Rows require unique string history_id and ISO event_date. Dates have no
    availability evidence: exclude the entire cutoff local day and every known
    target-issue match ID. No inference of source/label availability, fitting,
    tuning, cache reuse, persistence or prospective admission. Sparse windows
    return no selected rows and an explicit insufficient status. Receipt binds
    inputs, fixed parameters and selected IDs; weights are equal descriptive
    weights, not tuned recency. Actual capture times belong to source receipts.
    """
    if not isinstance(cutoff, Cutoff) or cutoff.kind != 'DECISION_EPOCH':
        raise TemporalContractError('Explicit decision cutoff required')
    if type(window) is not int or type(minimum) is not int or not 1 <= minimum <= window:
        raise TemporalContractError('Invalid fixed window/minimum')
    if not source_hashes or not implementation_hashes or not excluded_ids:
        raise TemporalContractError('Source, implementation and target identities required')
    day = cutoff.cutoff_ts.tz_convert(ZoneInfo(timezone)).date()
    ids = [r['history_id'] for r in rows]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise TemporalContractError('Unique history IDs required')
    prior = []
    reasons = {'TARGET_ISSUE_ID': 0, 'SAME_DAY_OR_FUTURE': 0, 'OUTSIDE_WINDOW': 0}
    for row in rows:
        event = datetime.strptime(row['event_date'], '%Y-%m-%d').date()
        if row['history_id'] in excluded_ids:
            reasons['TARGET_ISSUE_ID'] += 1
        elif event >= day:
            reasons['SAME_DAY_OR_FUTURE'] += 1
        else:
            prior.append(row)
    prior.sort(key=lambda r: (r['event_date'], r['history_id']), reverse=True)
    selected = prior[:window]
    reasons['OUTSIDE_WINDOW'] = max(0, len(prior) - window)
    status = 'OK_DIAGNOSTIC' if len(selected) >= minimum else 'INSUFFICIENT_HISTORY'
    if status != 'OK_DIAGNOSTIC':
        selected = []
    receipt = dict(cutoff_identity=cutoff.identity, cutoff_ts=cutoff.cutoff_ts.isoformat(),
        target_issue=cutoff.target_issue, evidence_class='HISTORICAL_PROXY',
        historical_admission=False, source_availability='UNPROVEN', label_availability='UNPROVEN',
        maximum_source_availability=None, maximum_label_availability=None,
        intended_use='RETROSPECTIVE_DESCRIPTION_ONLY', partition='NO_FIT_TUNE_CALIBRATION',
        fixed_window=window, minimum=minimum, timezone=timezone, status=status,
        available_prior_rows=len(prior), excluded_counts=reasons,
        selected_ids=[r['history_id'] for r in selected],
        maximum_event_date=max((r['event_date'] for r in selected), default=None),
        equal_weight=1 / len(selected) if selected else None, ess=len(selected),
        source_hashes=source_hashes, implementation_hashes=implementation_hashes,
        excluded_ids=sorted(excluded_ids), input_sha256=stable_json_hash(rows),
        selected_sha256=stable_json_hash(selected))
    receipt['identity'] = stable_json_hash(receipt)
    return dict(rows=copy.deepcopy(selected), receipt=receipt)
