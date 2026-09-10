"""Classify frozen-model replay without admitting data or changing fit cutoffs."""
import warnings
from . import Cutoff


class HistoricalReplayWarning(UserWarning):
    """A frozen model is being evaluated inside/before its training boundary."""


def prediction_scope(cutoff, training_issues, model_cutoff):
    """Return scope and warn for retrospective use; never fit or alter cutoffs.

    Both cutoffs must be explicit shared Cutoff objects. Training membership
    takes precedence over time. Earlier nonmembers are retrospective holdouts,
    not prospective out-of-sample predictions. No I/O or target labels used.
    """
    if not isinstance(cutoff, Cutoff) or not isinstance(model_cutoff, Cutoff):
        raise ValueError('Explicit prediction and model cutoffs required')
    if cutoff.target_issue in training_issues:
        scope = 'IN_SAMPLE_REPLAY'
        message = '训练内回放：此期属于模型训练期，结果可能偏乐观，不代表样本外预测能力。'
    elif cutoff.cutoff_ts < model_cutoff.cutoff_ts:
        scope = 'RETROSPECTIVE_REPLAY'
        message = '回顾诊断：模型冻结时间晚于本场决策时间，不代表当时可获得的预测。'
    else:
        return 'OUT_OF_SAMPLE'
    warnings.warn(message, HistoricalReplayWarning, stacklevel=2)
    return scope
