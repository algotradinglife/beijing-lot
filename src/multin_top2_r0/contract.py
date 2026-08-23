"""Frozen contract for BJ-UNIFIED-MULTIN-R0-001/v1."""

from __future__ import annotations

CONTRACT_ID = "BJ-UNIFIED-MULTIN-R0-001/v1"
ISSUE_NUMBER = 348
N_VALUES = tuple(range(3, 11))
OUTCOMES = ("3", "1", "0")
YEARS = (2023, 2024)
HORIZON = "10h"
FUNDED_UNITS = 512
STAKE_PER_UNIT_CNY = 2.0
ISSUE_STAKE_CNY = FUNDED_UNITS * STAKE_PER_UNIT_CNY
PAYOUT_FACTOR = 0.65
STARTING_CAPITAL_CNY = 100_000.0
BOOTSTRAP_DRAWS = 2_000
BOOTSTRAP_SEED = 348_001

# First seven masks are independent binary columns; later columns are fixed
# Walsh/XOR interactions.  Thus every N>=7 design contains 128 unique rows,
# every leg is 64/64 balanced, and every pair is orthogonal.
DESIGN_MASKS = (1, 2, 4, 8, 16, 32, 64, 3, 5, 9)


def tickets_for_n(n: int) -> int:
    if n not in N_VALUES:
        raise ValueError(f"N outside contract: {n}")
    return min(128, 2**n)


def units_per_ticket(n: int) -> int:
    tickets = tickets_for_n(n)
    if FUNDED_UNITS % tickets:
        raise AssertionError("ticket count does not divide funded units")
    return FUNDED_UNITS // tickets
