#!/usr/bin/env python3
"""Outcome-unexposed deterministic ticket allocators frozen for #145.

The public entry point is :func:`allocate`.  Inputs are a non-negative weight
vector indexed by the canonical base-3 ticket ordinal; outputs are integer
multiplicities for that same ordinal order.  No score, result, SP, settlement,
or payout field is accepted by this module.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Sequence


ENGINE_VERSION = "bj145-allocation-engine-v2"
FULL_TICKETS = 3 ** 7
UNIT_STAKE_YUAN = 2
CODES = ("3", "1", "0")
MECHANISMS = (
    "WR_DUPLICATE_STAKE",
    "WOR_DISTINCT",
    "RESIDUAL_SYSTEMATIC",
    "CAPPED_REPEAT",
    "DETERMINISTIC_TOP_MASS",
    "FULL_ENUMERATED",
)


def _validate_weights(weights: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in weights)
    if not values:
        raise ValueError("weight vector must not be empty")
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("weights must be finite and non-negative")
    if sum(values) <= 0:
        raise ValueError("weight vector must have positive total weight")
    return values


def _validate_m(m: int, k: int, cap: int | None = None) -> int:
    if isinstance(m, bool) or m < 0:
        raise ValueError("M must be a non-negative integer")
    capacity = k * cap if cap is not None else k
    if m > capacity:
        raise ValueError("M exceeds the frozen ticket-space capacity")
    return int(m)


def stable_uniform(*parts: object) -> float:
    """Exact #137 stable_uniform: first 64 SHA-256 bits plus 0.5."""
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def _inverse_cdf(weights: tuple[float, ...], unit: float) -> int:
    # #137 compares the raw stable_uniform directly to cumulative rounded
    # probability masses; do not rescale by the floating-point total.
    target = unit
    cumulative = 0.0
    for ordinal, weight in enumerate(weights):
        cumulative += weight
        if target <= cumulative or ordinal == len(weights) - 1:
            return ordinal
    raise AssertionError("inverse CDF did not select an ordinal")


def _wr(weights: tuple[float, ...], m: int, seed: str, identity_signature: str) -> tuple[int, ...]:
    counts = [0] * len(weights)
    for draw_index in range(m):
        unit = stable_uniform("bj137", "WR", seed, identity_signature, draw_index)
        counts[_inverse_cdf(weights, unit)] += 1
    return tuple(counts)


def _wor(weights: tuple[float, ...], m: int, seed: str, identity_signature: str) -> tuple[int, ...]:
    keys = []
    for ordinal, weight in enumerate(weights):
        if weight <= 0:
            key = math.inf
        else:
            unit = max(stable_uniform("bj137", "WOR", seed, identity_signature, ordinal), 1e-18)
            key = -math.log(unit) / weight
        keys.append((key, ordinal))
    selected = sorted(keys)[:m]
    counts = [0] * len(weights)
    for _, ordinal in selected:
        counts[ordinal] = 1
    return tuple(counts)


def _hamilton(weights: tuple[float, ...], m: int) -> tuple[int, ...]:
    total = sum(weights)
    quotas = [m * weight / total for weight in weights]
    counts = [math.floor(quota) for quota in quotas]
    remainder = m - sum(counts)
    order = sorted(range(len(weights)), key=lambda ordinal: (-(quotas[ordinal] - counts[ordinal]), ordinal))
    for ordinal in order[:remainder]:
        counts[ordinal] += 1
    return tuple(counts)


def _capped_hamilton(weights: tuple[float, ...], m: int, cap: int) -> tuple[int, ...]:
    """Iterated capped-Hamilton allocation with deterministic ordinal ties."""
    if cap < 1:
        raise ValueError("cap must be positive")
    counts = [0] * len(weights)
    remaining = m
    while remaining:
        active = [ordinal for ordinal, count in enumerate(counts) if count < cap]
        if not active:
            raise ValueError("cap capacity exhausted")
        active_weight = sum(weights[ordinal] for ordinal in active)
        if active_weight <= 0:
            active_weight = float(len(active))
            effective = {ordinal: 1.0 for ordinal in active}
        else:
            effective = {ordinal: weights[ordinal] for ordinal in active}
        quotas = {ordinal: remaining * effective[ordinal] / active_weight for ordinal in active}
        additions = {ordinal: min(math.floor(quotas[ordinal]), cap - counts[ordinal]) for ordinal in active}
        added = sum(additions.values())
        if added:
            for ordinal, amount in additions.items():
                counts[ordinal] += amount
            remaining -= added
            continue
        ordinal = min(
            active,
            key=lambda candidate: (-(quotas[candidate] - math.floor(quotas[candidate])), candidate),
        )
        counts[ordinal] += 1
        remaining -= 1
    return tuple(counts)


def allocate(
    mechanism: str,
    weights: Sequence[float],
    m: int,
    *,
    seed: str = "NA",
    identity_signature: str = "",
    cap: int | None = None,
) -> tuple[int, ...]:
    """Return deterministic ticket multiplicities for one frozen allocation cell."""
    values = _validate_weights(weights)
    if mechanism not in MECHANISMS:
        raise ValueError(f"unknown mechanism: {mechanism}")
    if mechanism == "CAPPED_REPEAT":
        if cap is None:
            raise ValueError("CAPPED_REPEAT requires cap")
        m = _validate_m(m, len(values), cap)
    else:
        m = _validate_m(m, len(values))
    if mechanism == "WR_DUPLICATE_STAKE":
        return _wr(values, m, str(seed), identity_signature)
    if mechanism == "WOR_DISTINCT":
        return _wor(values, m, str(seed), identity_signature)
    if mechanism == "RESIDUAL_SYSTEMATIC":
        return _hamilton(values, m)
    if mechanism == "CAPPED_REPEAT":
        return _capped_hamilton(values, m, int(cap))
    if mechanism == "DETERMINISTIC_TOP_MASS":
        counts = [0] * len(values)
        for ordinal in sorted(range(len(values)), key=lambda candidate: (-values[candidate], candidate))[:m]:
            counts[ordinal] = 1
        return tuple(counts)
    if m != len(values):
        raise ValueError("FULL_ENUMERATED requires M equal to ticket-space size")
    return tuple(1 for _ in values)


def counts_fingerprint(counts: Sequence[int]) -> dict[str, int | str]:
    values = tuple(int(value) for value in counts)
    if any(value < 0 for value in values):
        raise ValueError("counts must be non-negative")
    digest = hashlib.sha256(json.dumps(values, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "counts_sha256": digest,
        "draw_count": sum(values),
        "unique_count": sum(value > 0 for value in values),
        "duplicate_count": sum(max(value - 1, 0) for value in values),
        "max_multiplicity": max(values, default=0),
    }


def golden_weights(ticket_space_k: int = FULL_TICKETS) -> tuple[float, ...]:
    """Stable positive synthetic vector used only for executable golden vectors."""
    if ticket_space_k < 1:
        raise ValueError("ticket space must be positive")
    raw = tuple(float(((ordinal * 37 + 11) % 1009) + 1) for ordinal in range(ticket_space_k))
    total = sum(raw)
    return tuple(value / total for value in raw)


def ticket_code(ordinal: int, legs: int = 7) -> str:
    if ordinal < 0 or ordinal >= 3 ** legs:
        raise ValueError("ticket ordinal out of range")
    digits = ["0"] * legs
    value = ordinal
    for index in range(legs - 1, -1, -1):
        digits[index] = CODES[value % 3]
        value //= 3
    return "".join(digits)
