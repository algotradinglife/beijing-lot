"""Physical ticket construction for the Issue #312 action cube."""

from __future__ import annotations

import math

import numpy as np

from issue209.dynamic_policy import ActionSpec, OUTCOMES, generate_tickets

from .design import CubeAction, GENERATORS, MATCH_SELECTORS, OUTCOME_DIRECTIONS, PROTECTIONS


def generate_cube_tickets(
    ev: np.ndarray,
    probabilities: np.ndarray,
    divergence: np.ndarray,
    action: CubeAction,
    *,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Generate one K-ticket bundle and return realized protection count.

    The exact #306 anchor delegates to its accepted generator. Expanded actions
    first freeze a candidate match pool, then construct tickets, then spend a
    bounded portion of the same K-ticket budget on physical protection. No
    protection adds tickets or stake.
    """

    _validate_action(action, len(ev))
    if action.is_anchor:
        matches, outcomes = generate_tickets(
            ev,
            probabilities,
            ActionSpec(action.n, action.k, action.generator),
            seed=seed,
        )
        return matches, outcomes, 0

    clean_ev = _clean_positive(ev)
    clean_probability = _normalize_rows(_clean_positive(probabilities))
    clean_divergence = np.nan_to_num(divergence, nan=0.0, posinf=0.0, neginf=0.0)
    branch_weight = outcome_weights(
        clean_ev,
        clean_probability,
        clean_divergence,
        action.outcome_direction,
    )
    selector_weight = match_selector_weights(
        clean_ev,
        clean_probability,
        clean_divergence,
        branch_weight,
        action.match_selector,
    )
    pool_size = len(ev) if action.pool_excess < 0 else min(len(ev), action.n + action.pool_excess)
    candidate_positions = np.argsort(-selector_weight, kind="stable")[:pool_size]
    matches, outcomes = _generate_from_pool(
        branch_weight,
        clean_probability,
        candidate_positions,
        action,
        seed=seed,
    )
    protected_outcomes, protected = _apply_protection(
        matches,
        outcomes,
        branch_weight,
        clean_probability,
        clean_divergence,
        action,
        seed=seed + 17,
    )
    return matches, protected_outcomes, protected


def outcome_weights(
    ev: np.ndarray,
    probabilities: np.ndarray,
    divergence: np.ndarray,
    direction: str,
) -> np.ndarray:
    """Map one M×3 pre-event tensor to positive outcome sampling weights."""

    if direction not in OUTCOME_DIRECTIONS:
        raise ValueError(f"unsupported outcome direction: {direction}")
    if direction == "MARKET_P":
        weights = probabilities
    elif direction == "RAW_VALUE":
        weights = ev
    else:
        centered = divergence - divergence.mean(axis=1, keepdims=True)
        scale = divergence.std(axis=1, keepdims=True)
        z = centered / np.where(scale > 1e-9, scale, 1.0)
        divergence_weight = probabilities * np.exp(np.clip(z, -2.0, 2.0))
        if direction == "DIVERGENCE":
            weights = divergence_weight
        else:
            weights = np.sqrt(_normalize_rows(ev) * _normalize_rows(divergence_weight))
    return _normalize_rows(np.clip(weights, 1e-12, None))


def match_selector_weights(
    ev: np.ndarray,
    probabilities: np.ndarray,
    divergence: np.ndarray,
    branch_weight: np.ndarray,
    selector: str,
) -> np.ndarray:
    """Return a pre-event score for admitting matches to the ticket pool."""

    if selector not in MATCH_SELECTORS:
        raise ValueError(f"unsupported match selector: {selector}")
    best_value = ev.max(axis=1)
    entropy = -np.sum(probabilities * np.log(np.clip(probabilities, 1e-12, 1.0)), axis=1)
    cold = 1.0 - probabilities.min(axis=1)
    divergence_abs = np.abs(divergence).max(axis=1)
    if selector == "GLOBAL_VALUE":
        return branch_weight.max(axis=1)
    if selector == "BEST_VALUE":
        return best_value
    if selector == "LOW_ENTROPY":
        return 1.0 / np.clip(entropy, 1e-6, None)
    if selector == "COLD_EXCLUDABLE":
        return cold
    if selector == "DIVERGENCE":
        return divergence_abs
    return (
        _rank01(best_value) + _rank01(cold) + _rank01(divergence_abs)
    ) / 3.0


def _generate_from_pool(
    branch_weight: np.ndarray,
    probabilities: np.ndarray,
    candidate_positions: np.ndarray,
    action: CubeAction,
    *,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    if action.generator not in GENERATORS:
        raise ValueError(f"unsupported generator: {action.generator}")
    local_weight = branch_weight[candidate_positions]
    match_weight = np.clip(local_weight.max(axis=1), 1e-12, None)
    if action.generator == "TOP_VALUE":
        local = np.argsort(-match_weight, kind="stable")[: action.n]
        chosen = candidate_positions[local]
        outcomes = np.argmax(branch_weight[chosen], axis=1)
        return (
            np.repeat(chosen[None, :], action.k, axis=0),
            np.repeat(outcomes[None, :], action.k, axis=0),
        )

    rng = np.random.default_rng(seed)
    collected_matches: list[np.ndarray] = []
    collected_outcomes: list[np.ndarray] = []
    identities: set[tuple[tuple[int, int], ...]] = set()
    attempts = 0
    while len(collected_matches) < action.k and attempts < 40:
        batch = max(64, (action.k - len(collected_matches)) * 3)
        score = np.log(match_weight)[None, :] + rng.gumbel(
            size=(batch, len(candidate_positions))
        )
        local_rows = np.argpartition(score, -action.n, axis=1)[:, -action.n :]
        for local_row in local_rows:
            match_row = np.sort(candidate_positions[local_row])
            outcome_row = np.asarray(
                [
                    int(
                        rng.choice(
                            len(OUTCOMES),
                            p=branch_weight[position] / branch_weight[position].sum(),
                        )
                    )
                    for position in match_row
                ],
                dtype=int,
            )
            identity = _identity(match_row, outcome_row)
            if action.generator == "WEIGHTED_WOR" and identity in identities:
                continue
            identities.add(identity)
            collected_matches.append(match_row)
            collected_outcomes.append(outcome_row)
            if len(collected_matches) == action.k:
                break
        attempts += 1
    return np.asarray(collected_matches, dtype=int), np.asarray(collected_outcomes, dtype=int)


def _apply_protection(
    matches: np.ndarray,
    outcomes: np.ndarray,
    branch_weight: np.ndarray,
    probabilities: np.ndarray,
    divergence: np.ndarray,
    action: CubeAction,
    *,
    seed: int,
) -> tuple[np.ndarray, int]:
    if action.protection not in PROTECTIONS:
        raise ValueError(f"unsupported protection: {action.protection}")
    if action.protection == "NONE" or len(matches) == 0:
        return outcomes, 0
    fraction = {
        "ALT_UNCERTAINTY": 0.125,
        "ALT_DIVERGENCE": 0.125,
        "SOFT_REENTRY_05": 0.05,
        "SOFT_REENTRY_15": 0.15,
    }[action.protection]
    wanted = min(len(matches), max(1, math.ceil(fraction * len(matches))))
    result = outcomes.copy()
    rng = np.random.default_rng(seed)
    protected_indices = rng.permutation(len(matches))[:wanted]
    used = (
        {_identity(match_row, outcome_row) for match_row, outcome_row in zip(matches, result, strict=True)}
        if action.generator == "WEIGHTED_WOR"
        else set()
    )
    applied = 0
    for index in protected_indices:
        match_row = matches[index]
        outcome_row = result[index].copy()
        old_identity = _identity(match_row, outcome_row)
        if action.protection == "ALT_UNCERTAINTY":
            entropy = -np.sum(
                probabilities[match_row]
                * np.log(np.clip(probabilities[match_row], 1e-12, 1.0)),
                axis=1,
            )
            leg = int(np.argmax(entropy))
            candidates = np.argsort(-branch_weight[match_row[leg]], kind="stable")
        elif action.protection == "ALT_DIVERGENCE":
            leg = int(np.argmax(np.abs(divergence[match_row]).max(axis=1)))
            candidates = np.argsort(-divergence[match_row[leg]], kind="stable")
        else:
            cold_probability = probabilities[match_row].min(axis=1)
            leg = int(np.argmin(cold_probability))
            candidates = np.argsort(probabilities[match_row[leg]], kind="stable")
        replacement = next(
            (int(candidate) for candidate in candidates if candidate != outcome_row[leg]),
            None,
        )
        if replacement is None:
            continue
        outcome_row[leg] = replacement
        new_identity = _identity(match_row, outcome_row)
        if action.generator == "WEIGHTED_WOR":
            used.discard(old_identity)
            if new_identity in used:
                used.add(old_identity)
                continue
            used.add(new_identity)
        result[index] = outcome_row
        applied += 1
    return result, applied


def _validate_action(action: CubeAction, n_matches: int) -> None:
    if action.n not in range(3, 11) or action.k not in (8, 32, 128, 512):
        raise ValueError("invalid N/K")
    if n_matches < action.n:
        raise ValueError("issue has fewer matches than N")
    if action.pool_excess >= 0 and action.n + action.pool_excess < action.n:
        raise ValueError("candidate pool is smaller than N")


def _clean_positive(values: np.ndarray) -> np.ndarray:
    return np.clip(
        np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0), 1e-12, None
    )


def _normalize_rows(values: np.ndarray) -> np.ndarray:
    total = values.sum(axis=1, keepdims=True)
    return values / np.where(total > 0, total, 1.0)


def _rank01(values: np.ndarray) -> np.ndarray:
    order = np.argsort(np.argsort(values, kind="stable"), kind="stable")
    return order.astype(float) / max(1, len(values) - 1)


def _identity(
    match_row: np.ndarray, outcome_row: np.ndarray
) -> tuple[tuple[int, int], ...]:
    return tuple(sorted(zip(match_row.tolist(), outcome_row.tolist(), strict=True)))
