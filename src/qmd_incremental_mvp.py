"""Synthetic squared-error diagnostic for the incremental QMD engineering MVP.

This module is deliberately tiny and dependency-free (Python standard library
only). It performs no historical learning, selection, prediction, or betting:
it only squares the gap between an observed 0/1 label and a predicted
probability. Importing it has no side effects (no scraping, no database access,
no file writes).

Row contract for the returned records:

* ``fixture_id`` -- nonempty string identifier, preserved verbatim (leading
  zeros are meaningful and never coerced to numbers).
* ``squared_error`` -- ``(predicted - observed) ** 2`` as a float, or ``None``
  when the label is missing (``observed is None``). A missing label is not zero
  and must not be reported as ``0.0``.
"""

from __future__ import annotations

from typing import Any, Sequence, TypedDict

__all__ = ["squared_errors", "SquaredError"]


class SquaredError(TypedDict):
    """Exact bridge record: a string identifier and a float or missing score."""

    fixture_id: str
    squared_error: float | None


def _require_finite_number(value: Any, index: int, field: str) -> float:
    """Return ``value`` as a float, rejecting bools, non-numbers, NaN and Inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field}[{index}] must be a number, got {type(value).__name__}")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field}[{index}] must be finite, got {value!r}")
    return number


def _require_probability(value: Any, index: int) -> float:
    """Return a finite probability in [0, 1] for ``predicted[index]``."""
    number = _require_finite_number(value, index, "predicted")
    if number < 0.0 or number > 1.0:
        raise ValueError(f"predicted[{index}] must be within [0, 1], got {value!r}")
    return number


def _require_label(value: Any, index: int) -> float | None:
    """Return a 0/1 label float, or None for a missing label."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"observed[{index}] must be 0, 1, or None, got {type(value).__name__}")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"observed[{index}] must be finite, got {value!r}")
    if number not in (0.0, 1.0):
        raise ValueError(f"observed[{index}] must be 0, 1, or None, got {value!r}")
    return number


def _require_identifier(value: Any, index: int) -> str:
    """Return a unique, nonempty string fixture identifier."""
    if not isinstance(value, str) or isinstance(value, bool):
        raise TypeError(f"ids[{index}] must be a string, got {type(value).__name__}")
    if value == "":
        raise ValueError(f"ids[{index}] must be nonempty")
    return value


def square_error(predicted: float, observed: float | None) -> float | None:
    """Squared error for one row; ``None`` when the label is missing.

    Inputs are validated by :func:`squared_errors`; this helper assumes an
    already-validated probability and a 0/1-or-None label.
    """
    if observed is None:
        return None
    return float((predicted - observed) ** 2)


def squared_errors(ids: Sequence[str], predicted: Sequence[float], observed: Sequence[float | None]) -> list[SquaredError]:
    """Pair each fixture with its squared error, preserving input order.

    Parameters
    ----------
    ids:
        Unique, nonempty string identifiers. Kept as strings so identifiers
        with leading zeros survive the boundary.
    predicted:
        Finite probabilities within ``[0, 1]``. Booleans are rejected.
    observed:
        Labels that are exactly ``0``, exactly ``1``, or ``None`` for a missing
        label. Booleans, NaN, Inf, and any other value are rejected.

    Returns
    -------
    list of dict
        One record per input row: ``{"fixture_id": str, "squared_error":
        float | None}``. An empty input yields ``[]``.

    Raises
    ------
    TypeError
        Wrong container/field types, or a boolean supplied as a number/label.
    ValueError
        Unequal lengths, empty/duplicate/non-string-invalid identifiers,
        out-of-range or non-finite numeric values, or a label that is not 0/1.
    """
    for name, values in (("ids", ids), ("predicted", predicted), ("observed", observed)):
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise TypeError(f"{name} must be a sequence of values, got {type(values).__name__}")

    if not (len(ids) == len(predicted) == len(observed)):
        raise ValueError(
            "ids, predicted, and observed must have equal lengths, got "
            f"{len(ids)}, {len(predicted)}, {len(observed)}"
        )

    checked_ids: list[str] = []
    seen_ids: set[str] = set()
    for index, raw_id in enumerate(ids):
        identifier = _require_identifier(raw_id, index)
        if identifier in seen_ids:
            raise ValueError(f"ids[{index}] is duplicated: {identifier!r}")
        seen_ids.add(identifier)
        checked_ids.append(identifier)

    records: list[SquaredError] = []
    for index in range(len(checked_ids)):
        probability = _require_probability(predicted[index], index)
        label = _require_label(observed[index], index)
        records.append(
            {
                "fixture_id": checked_ids[index],
                "squared_error": square_error(probability, label),
            }
        )
    return records
