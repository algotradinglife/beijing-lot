"""Bounded first-cycle complete-action catalog for Issue #282."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

N_VALUES = tuple(range(3, 9))
K_ANCHORS = (8, 32, 128, 512)
GENERATORS = ("TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR")
SELECTORS = ("ALL", "TOP_HALF_VALUE")
OUTCOME_WEIGHT_MODES = ("CELL_VALUE", "MARKET_PROBABILITY")


@dataclass(frozen=True)
class PrototypeAction:
    """One auditable S/O/N/G/K action with equal initial ticket stakes."""

    selector: str
    outcome_weight_mode: str
    n: int
    generator: str
    k: int

    def __post_init__(self) -> None:
        if self.selector not in SELECTORS:
            raise ValueError(f"unsupported selector: {self.selector}")
        if self.outcome_weight_mode not in OUTCOME_WEIGHT_MODES:
            raise ValueError(
                f"unsupported outcome weighting: {self.outcome_weight_mode}"
            )
        if self.n not in N_VALUES:
            raise ValueError(f"unsupported N: {self.n}")
        if self.generator not in GENERATORS:
            raise ValueError(f"unsupported generator: {self.generator}")
        if self.k <= 0:
            raise ValueError("K must be positive")

    @property
    def key(self) -> str:
        selector = "ALL" if self.selector == "ALL" else "TOP50"
        outcome = "VALUE" if self.outcome_weight_mode == "CELL_VALUE" else "MARKET"
        return f"S{selector}_O{outcome}_N{self.n}_{self.generator}_K{self.k}"


def prototype_action_space() -> tuple[PrototypeAction, ...]:
    """Return the preregistered bounded action surface in deterministic order."""

    return tuple(
        PrototypeAction(selector, outcome, n, generator, k)
        for selector, outcome, n, generator, k in product(
            SELECTORS,
            OUTCOME_WEIGHT_MODES,
            N_VALUES,
            GENERATORS,
            K_ANCHORS,
        )
    )
