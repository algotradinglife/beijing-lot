"""Representative non-mapping client proving generic cutoff selection reuse."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .core import (
    Cutoff,
    PartitionPolicy,
    WeightingPolicy,
    prepare_learning_context,
    stable_json_hash,
)


@dataclass(frozen=True)
class ThresholdSelection:
    selection: float
    receipt: dict[str, Any]


def select_cutoff_threshold(
    history: pd.DataFrame,
    cutoff: Cutoff,
    *,
    score_column: str,
    binary_label_column: str,
    source_hashes: Mapping[str, str],
    implementation_hashes: Mapping[str, str],
    weighting_policy: WeightingPolicy = WeightingPolicy.expanding_equal(),
) -> ThresholdSelection:
    """Select one score threshold on tune, then verify direction on calibration."""

    context = prepare_learning_context(
        history,
        cutoff,
        source_hashes=source_hashes,
        implementation_hashes=implementation_hashes,
        partition_policy=PartitionPolicy(),
        weighting_policy=weighting_policy,
    )
    fit, tune, calibration = (
        context.partitions["fit"],
        context.partitions["tune"],
        context.partitions["calibration"],
    )
    if not {score_column, binary_label_column}.issubset(history):
        raise ValueError("threshold client lacks score or binary label")
    candidates = np.unique(fit[score_column].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy(float))
    if not len(candidates):
        raise ValueError("threshold client has no candidate")

    def accuracy(frame: pd.DataFrame, threshold: float) -> float:
        predicted = frame[score_column].ge(threshold).to_numpy(int)
        return float(np.mean(predicted == frame[binary_label_column].to_numpy(int)))

    tune_rows = [(float(value), accuracy(tune, float(value))) for value in candidates]
    selected, tune_accuracy = max(tune_rows, key=lambda item: (item[1], -item[0]))
    calibration_accuracy = accuracy(calibration, selected)
    receipt = dict(context.receipt.payload)
    receipt.update({
        "client": "REPRESENTATIVE_THRESHOLD_SELECTION",
        "selected_parameters": {"threshold": selected},
        "metrics": {
            "tune_accuracy": tune_accuracy,
            "calibration_accuracy": calibration_accuracy,
        },
        "gate_predicates": {"calibration_at_least_chance": calibration_accuracy >= 0.5},
        "selection_identity": stable_json_hash({
            "threshold": selected,
            "tune_accuracy": tune_accuracy,
            "calibration_accuracy": calibration_accuracy,
        }),
    })
    return ThresholdSelection(selected, receipt)
