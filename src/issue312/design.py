"""Frozen space-filling action design for Issue #312."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd
from scipy.stats import qmc

N_VALUES = tuple(range(3, 11))
K_VALUES = (8, 32, 128, 512)
MATCH_SELECTORS = (
    "GLOBAL_VALUE",
    "BEST_VALUE",
    "LOW_ENTROPY",
    "COLD_EXCLUDABLE",
    "DIVERGENCE",
    "HYBRID",
)
POOL_EXCESS = (0, 2, 4, -1)  # -1 means every eligible match.
OUTCOME_DIRECTIONS = ("MARKET_P", "RAW_VALUE", "DIVERGENCE", "HYBRID")
GENERATORS = ("TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR")
PROTECTIONS = (
    "NONE",
    "ALT_UNCERTAINTY",
    "ALT_DIVERGENCE",
    "SOFT_REENTRY_05",
    "SOFT_REENTRY_15",
)
DESIGN_SEED = 312001
SCREENING_ACTIONS = 192


@dataclass(frozen=True)
class CubeAction:
    """One physically executable joint ticket-construction action."""

    n: int
    k: int
    match_selector: str
    pool_excess: int
    outcome_direction: str
    generator: str
    protection: str

    @property
    def key(self) -> str:
        pool = "ALL" if self.pool_excess < 0 else f"P{self.pool_excess}"
        return (
            f"N{self.n}_K{self.k}_S{self.match_selector}_"
            f"{pool}_O{self.outcome_direction}_G{self.generator}_R{self.protection}"
        )

    @property
    def is_anchor(self) -> bool:
        return (
            self.match_selector == "GLOBAL_VALUE"
            and self.pool_excess == -1
            and self.outcome_direction == "RAW_VALUE"
            and self.protection == "NONE"
        )


def anchor_actions() -> tuple[CubeAction, ...]:
    """Exact N/K/generator semantics inherited from Issue #306."""

    return tuple(
        CubeAction(n, k, "GLOBAL_VALUE", -1, "RAW_VALUE", generator, "NONE")
        for n in N_VALUES
        for k in K_VALUES
        for generator in GENERATORS
    )


def build_action_registry(
    *, size: int = SCREENING_ACTIONS, seed: int = DESIGN_SEED
) -> pd.DataFrame:
    """Return anchors plus a seeded discrete Latin-hypercube screen."""

    anchors = list(anchor_actions())
    if size < len(anchors):
        raise ValueError("screening design cannot omit exact #306 anchors")
    factor_levels = (
        N_VALUES,
        K_VALUES,
        MATCH_SELECTORS,
        POOL_EXCESS,
        OUTCOME_DIRECTIONS,
        GENERATORS,
        PROTECTIONS,
    )
    sampler = qmc.LatinHypercube(d=len(factor_levels), seed=seed)
    points = sampler.random(n=max(4096, 16 * size))
    extras: list[CubeAction] = []
    seen = {action.key for action in anchors}
    for point in points:
        levels = [
            values[min(int(value * len(values)), len(values) - 1)]
            for value, values in zip(point, factor_levels, strict=True)
        ]
        action = CubeAction(*levels)
        if action.key in seen:
            continue
        seen.add(action.key)
        extras.append(action)
        if len(anchors) + len(extras) >= size:
            break
    if len(anchors) + len(extras) != size:
        raise RuntimeError("space-filling design did not produce enough unique actions")
    rows = []
    for order, action in enumerate([*anchors, *extras]):
        rows.append(
            {
                "design_order": order,
                "action_key": action.key,
                **asdict(action),
                "is_anchor": action.is_anchor,
                "design_seed": seed,
            }
        )
    result = pd.DataFrame(rows)
    if result["action_key"].duplicated().any():
        raise AssertionError("action registry is not unique")
    return result


def registry_diagnostics(registry: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Publish marginal balance and observed pairwise level coverage."""

    factors = [
        "n",
        "k",
        "match_selector",
        "pool_excess",
        "outcome_direction",
        "generator",
        "protection",
    ]
    marginal_rows = []
    for factor in factors:
        counts = registry[factor].value_counts(dropna=False)
        for level, count in counts.items():
            marginal_rows.append(
                {
                    "factor": factor,
                    "level": str(level),
                    "count": int(count),
                    "fraction": float(count / len(registry)),
                }
            )
    pair_rows = []
    for left_index, left in enumerate(factors):
        for right in factors[left_index + 1 :]:
            observed = registry[[left, right]].drop_duplicates().shape[0]
            possible = registry[left].nunique() * registry[right].nunique()
            pair_rows.append(
                {
                    "left_factor": left,
                    "right_factor": right,
                    "observed_level_pairs": int(observed),
                    "possible_level_pairs": int(possible),
                    "coverage_fraction": float(observed / possible),
                }
            )
    return pd.DataFrame(marginal_rows), pd.DataFrame(pair_rows)


def actions_from_registry(registry: pd.DataFrame) -> tuple[CubeAction, ...]:
    """Rehydrate a committed registry without redefining action semantics."""

    columns = [
        "n",
        "k",
        "match_selector",
        "pool_excess",
        "outcome_direction",
        "generator",
        "protection",
    ]
    return tuple(CubeAction(**row) for row in registry[columns].to_dict("records"))
