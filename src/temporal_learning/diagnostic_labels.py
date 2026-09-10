"""Explicit retrospective label clocks; never evidence of observed availability."""
import pandas as pd
from .core import Cutoff, TemporalContractError, utc


def diagnostic_label_clock(decision_time, *, cutoff, delay_hours):
    """Return a diagnostic decision-plus-delay clock strictly before cutoff.

    Delay is explicit, finite and positive. Missing/late clocks fail closed.
    No I/O, data admission, fitting, or claim of prospective availability.
    """
    if not isinstance(cutoff, Cutoff) or not isinstance(delay_hours, (int, float)) or not 0 < delay_hours < float('inf'):
        raise TemporalContractError('Explicit cutoff and positive label delay required')
    decision = utc(decision_time)
    label = decision + pd.Timedelta(hours=delay_hours)
    if pd.isna(label) or label >= cutoff.cutoff_ts:
        raise TemporalContractError('Diagnostic label clock must precede cutoff')
    return label.isoformat()
