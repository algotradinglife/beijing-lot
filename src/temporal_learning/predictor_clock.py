"""Diagnostic target predictor clocks, distinct from observed availability."""
import pandas as pd
from .core import Cutoff, TemporalContractError, utc, stable_json_hash


def diagnostic_predictor_clock(event_dates, quote_times, *, cutoff, timezone, source_hashes):
    """Bound dated history by the end of its local day and timed quotes exactly.

    Inputs are the rows actually used by a cutoff-bound feature snapshot.
    Dates/quotes remain historical proxies, never availability evidence.
    Return a sealed clock ledger; missing clocks or same/later clocks fail.
    No I/O, fitting or timestamp inference for untimed current-page content.
    """
    if not isinstance(cutoff, Cutoff) or not source_hashes or not event_dates:
        raise TemporalContractError('Cutoff, history clocks and source hashes required')
    history = [(pd.Timestamp(d).tz_localize(timezone) + pd.Timedelta(days=1)).tz_convert('UTC') for d in event_dates]
    quotes = [utc(t) for t in quote_times]
    if any(pd.isna(t) for t in history + quotes):
        raise TemporalContractError('Missing predictor clock')
    maximum = max(history + quotes)
    if maximum >= cutoff.cutoff_ts:
        raise TemporalContractError('Predictor clock is not strictly prior to its fixture cutoff')
    receipt = dict(cutoff_ts=cutoff.cutoff_ts.isoformat(), target_issue=cutoff.target_issue,
        event_dates=sorted(event_dates), quote_times=sorted(quote_times),
        maximum_predictor_clock=maximum.isoformat(), source_hashes=source_hashes,
        evidence_class='HISTORICAL_PROXY_NOT_OBSERVED_AVAILABILITY', historical_admission=False)
    return dict(receipt=receipt, seal=stable_json_hash(receipt))


def require_prior_predictor_clock(clock, cutoff):
    """Fail closed on absent or same/later diagnostic predictor clocks; no I/O."""
    parsed = utc(clock)
    if not isinstance(cutoff, Cutoff) or pd.isna(parsed) or parsed >= cutoff.cutoff_ts:
        raise TemporalContractError('Predictor clock must precede prediction cutoff')
