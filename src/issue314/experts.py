"""Interpretable CORE/TAIL experts with explicit depth-1/2 support."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from issue209.dynamic_policy import _derived_seed

from .data import OUTCOMES

OUTCOME_INDEX = {outcome: index for index, outcome in enumerate(OUTCOMES)}
K_ANCHORS = (64, 192, 512, 1024, 2048)


@dataclass(frozen=True)
class ExpertSpec:
    name: str
    sleeve: str
    n: int
    selector: str
    outcome_direction: str
    generator: str
    pool_excess: int
    protection: str
    protected_leg_count: int

    def reset(self, factor: str) -> "ExpertSpec":
        values = {
            "n": {"n": 7},
            "generator": {"generator": "WOR"},
            "candidate_selector": {"selector": "GLOBAL", "pool_excess": 8},
            "outcome_direction": {"outcome_direction": "MARKET"},
            "coverage_protection": {
                "protection": "NONE",
                "protected_leg_count": 0,
            },
        }
        if factor not in values:
            raise ValueError(f"unknown reset factor: {factor}")
        return replace(self, **values[factor])


EXPERTS = (
    ExpertSpec(
        "CORE_N7_MARKET_WOR", "CORE", 7, "GLOBAL", "MARKET", "WOR", 8, "NONE", 0
    ),
    ExpertSpec("CORE_N7_VALUE_WOR", "CORE", 7, "VALUE", "VALUE", "WOR", 8, "NONE", 0),
    ExpertSpec("CORE_N7_VALUE_WR", "CORE", 7, "VALUE", "VALUE", "WR", 8, "NONE", 0),
    ExpertSpec(
        "CORE_N7_SELECTIVE", "CORE", 7, "HYBRID", "VALUE", "WOR", 8, "UNCERTAINTY", 1
    ),
    ExpertSpec("TAIL_N8_VALUE_WOR", "TAIL", 8, "VALUE", "VALUE", "WOR", 10, "NONE", 0),
    ExpertSpec(
        "TAIL_N9_DIVERGENCE",
        "TAIL",
        9,
        "DIVERGENCE",
        "DIVERGENCE",
        "WOR",
        10,
        "NONE",
        0,
    ),
    ExpertSpec("TAIL_N10_VALUE_WR", "TAIL", 10, "VALUE", "VALUE", "WR", 12, "NONE", 0),
    ExpertSpec(
        "TAIL_N7_DIVERGENCE_PROTECTED",
        "TAIL",
        7,
        "DIVERGENCE",
        "DIVERGENCE",
        "WOR",
        10,
        "DIVERGENCE",
        2,
    ),
)


def expert_registry() -> pd.DataFrame:
    return pd.DataFrame([asdict(spec) for spec in EXPERTS])


def generate_tickets(
    group: pd.DataFrame,
    spec: ExpertSpec,
    *,
    k: int,
    seed: int,
    unique_cap: int | None = None,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame, dict[str, object]]:
    """Generate one auditable prefix inside an explicit support map."""

    if spec.protected_leg_count < 0 or spec.protected_leg_count > spec.n:
        raise ValueError("invalid protected-leg count")
    market = group[[f"q_eu_bjline_{c}" for c in OUTCOMES]].to_numpy(float)
    line = group[[f"q_line_only_control_{c}" for c in OUTCOMES]].to_numpy(float)
    divergence = market - line
    value = market / np.clip(line, 1e-6, None)
    branch = _branch_weight(market, value, divergence, spec.outcome_direction)
    match_score = _match_score(market, value, divergence, spec.selector)
    pool_size = min(len(group), spec.n + spec.pool_excess)
    if pool_size < spec.n:
        return (
            np.empty((0, spec.n), int),
            np.empty((0, spec.n), int),
            pd.DataFrame(),
            {"natural_support": 0},
        )
    pool = np.argsort(-match_score, kind="stable")[:pool_size]
    support = _support_map(market, divergence, branch, pool, spec)
    natural = _natural_support(support, spec.n)
    target_unique = min(k if unique_cap is None else unique_cap, natural)
    rng = np.random.default_rng(
        _derived_seed(seed, str(group["issue"].iloc[0]), spec.name)
    )
    matches: list[np.ndarray] = []
    outcomes: list[np.ndarray] = []
    identities: set[tuple[tuple[int, int], ...]] = set()
    main = np.full(len(group), -1, dtype=int)
    alternative = np.full(len(group), -1, dtype=int)
    alternative_probability = np.zeros(len(group), dtype=float)
    for position, allowed in support.items():
        main[position] = int(allowed[0])
        if len(allowed) == 2:
            alternative[position] = int(allowed[1])
            probability = _support_probability(branch[position], allowed)
            alternative_probability[position] = float(probability[1])
    attempts = 0
    while len(matches) < k and attempts < 20:
        batch = max(128, 3 * (k - len(matches)))
        gumbel = np.log(np.clip(match_score[pool], 1e-12, None))[None, :] + rng.gumbel(
            size=(batch, len(pool))
        )
        local = np.argpartition(gumbel, -spec.n, axis=1)[:, -spec.n :]
        selected_batch = np.sort(pool[local], axis=1)
        chosen_batch = main[selected_batch].copy()
        random = rng.random(size=selected_batch.shape)
        use_alternative = (alternative[selected_batch] >= 0) & (
            random < alternative_probability[selected_batch]
        )
        chosen_batch[use_alternative] = alternative[selected_batch][use_alternative]
        for selected, chosen in zip(selected_batch, chosen_batch, strict=True):
            identity = tuple(
                sorted(zip(selected.tolist(), chosen.tolist(), strict=True))
            )
            if (
                spec.generator == "WOR"
                and identity in identities
                and len(identities) < target_unique
            ):
                continue
            if spec.generator == "WOR" and len(identities) >= target_unique:
                # Natural/explicit unique support is exhausted; funded copies are allowed.
                donor = len(matches) % max(1, len(identities))
                matches.append(matches[donor].copy())
                outcomes.append(outcomes[donor].copy())
            else:
                identities.add(identity)
                matches.append(selected)
                outcomes.append(chosen)
            if len(matches) == k:
                break
        attempts += 1
    if not matches:
        raise AssertionError(f"could not generate any ticket for {spec.name}")
    # Separate unique construction from capital exposure. If stochastic WOR search
    # does not enumerate the whole combinatorial support inside its bounded attempt
    # budget, additional funding is represented by explicit copies of generated
    # identities rather than silently changing the generator or reducing K.
    generated_unique = len(identities)
    donor = 0
    while len(matches) < k:
        matches.append(matches[donor % len(matches)].copy())
        outcomes.append(outcomes[donor % len(outcomes)].copy())
        donor += 1
    support_rows = []
    for pos in pool:
        allowed = support[int(pos)]
        support_rows.append(
            {
                "match_position": int(pos),
                "match_idx": int(group.iloc[int(pos)]["match_idx"]),
                "coverage_depth": int(len(allowed)),
                "main_outcome": OUTCOMES[int(allowed[0])],
                "protection_outcome": OUTCOMES[int(allowed[1])]
                if len(allowed) == 2
                else "",
                "protection_reason": spec.protection if len(allowed) == 2 else "NONE",
            }
        )
    receipt = {
        "natural_support": int(natural),
        "unique_identities": int(generated_unique),
        "unique_enumeration_status": (
            "TARGET_REACHED"
            if generated_unique >= target_unique
            else "BOUNDED_SEARCH_PLUS_COPIES"
        ),
        "funded_tickets": int(k),
        "pool_matches": int(len(pool)),
        "maximum_coverage_depth": int(max(len(v) for v in support.values())),
    }
    return (
        np.asarray(matches),
        np.asarray(outcomes),
        pd.DataFrame(support_rows),
        receipt,
    )


def settle_tickets(
    matches: np.ndarray,
    outcomes: np.ndarray,
    group: pd.DataFrame,
    settlement: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ticket gross, correct legs and miss distance; 0.65 is once/ticket."""

    joined = group[["match_idx"]].merge(
        settlement[
            ["match_idx", "result_code", "settlement_sp", "settlement_available"]
        ],
        on="match_idx",
        how="left",
        validate="one_to_one",
    )
    realized = joined["result_code"].map(OUTCOME_INDEX).fillna(-1).to_numpy(int)
    sp = pd.to_numeric(joined["settlement_sp"], errors="coerce").to_numpy(float)
    available = joined["settlement_available"].fillna(False).to_numpy(bool)
    selected_realized = realized[matches]
    valid = available[matches].all(axis=1)
    correct = (outcomes == selected_realized).sum(axis=1)
    wins = valid & (correct == matches.shape[1])
    gross = np.zeros(len(matches), dtype=float)
    if wins.any():
        gross[wins] = 2.0 * 0.65 * np.prod(sp[matches[wins]], axis=1)
    return gross, correct, matches.shape[1] - correct


def _branch_weight(
    market: np.ndarray, value: np.ndarray, divergence: np.ndarray, direction: str
) -> np.ndarray:
    if direction == "MARKET":
        raw = market
    elif direction == "VALUE":
        raw = market * np.clip(value, 1e-6, None)
    elif direction == "DIVERGENCE":
        z = divergence / np.clip(divergence.std(axis=1, keepdims=True), 1e-6, None)
        raw = market * np.exp(np.clip(z, -2.0, 2.0))
    else:
        raise ValueError(direction)
    return raw / raw.sum(axis=1, keepdims=True)


def _match_score(
    market: np.ndarray, value: np.ndarray, divergence: np.ndarray, selector: str
) -> np.ndarray:
    if selector == "GLOBAL":
        return market.max(axis=1)
    if selector == "VALUE":
        return value.max(axis=1)
    if selector == "DIVERGENCE":
        return np.abs(divergence).max(axis=1)
    if selector == "HYBRID":
        return (
            _rank(value.max(axis=1))
            + _rank(market.max(axis=1))
            + _rank(np.abs(divergence).max(axis=1))
        ) / 3
    raise ValueError(selector)


def _support_map(
    market: np.ndarray,
    divergence: np.ndarray,
    branch: np.ndarray,
    pool: np.ndarray,
    spec: ExpertSpec,
) -> dict[int, np.ndarray]:
    support = {int(pos): np.argsort(-branch[pos], kind="stable")[:1] for pos in pool}
    if spec.protected_leg_count == 0:
        return support
    if spec.protection == "UNCERTAINTY":
        certainty = (
            np.sort(market[pool], axis=1)[:, -1] - np.sort(market[pool], axis=1)[:, -2]
        )
        protected = pool[
            np.argsort(certainty, kind="stable")[: spec.protected_leg_count]
        ]
    elif spec.protection == "DIVERGENCE":
        protected = pool[
            np.argsort(-np.abs(divergence[pool]).max(axis=1), kind="stable")[
                : spec.protected_leg_count
            ]
        ]
    elif spec.protection == "RANDOM":
        # Stable negative-control placement; never informed by the realized outcome.
        protected = pool[: spec.protected_leg_count]
    else:
        raise ValueError("protection count requires an explicit protection rule")
    for pos in protected:
        support[int(pos)] = np.argsort(-branch[pos], kind="stable")[:2]
    return support


def _natural_support(support: dict[int, np.ndarray], n: int) -> int:
    # Coefficient of x^n in product(1 + depth_j*x).
    coefficient = [1] + [0] * n
    for outcomes in support.values():
        depth = len(outcomes)
        for degree in range(n, 0, -1):
            coefficient[degree] += coefficient[degree - 1] * depth
    return int(coefficient[n])


def _support_probability(branch: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    weights = branch[allowed]
    return weights / weights.sum()


def _rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(np.argsort(values, kind="stable"), kind="stable")
    return order.astype(float) / max(1, len(values) - 1)
