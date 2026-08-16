"""Issue #208: N-ticket construction, selection lanes, settlement and capital.

Generalizes #206's fixed-N7 generator to arbitrary N. Every ticket has exactly
N distinct matches; cross-ticket overlap is preserved and measured. Settlement
uses the frozen official SP labels; capital replay uses native ¥2 or the frozen
#207 EQUAL_1PCT active control on identical tickets.

REWORK v3 (PI payout-economics 2026-08-15): the pre-tax gross multiple of a
winning N-fold ticket includes the Beijing payout coefficient EXACTLY ONCE:

    pre_tax_gross_multiple = hit * PAYOUT_COEFFICIENT * prod(official_sp_i)

It is never divided out, never applied per leg, and never compounded as
0.65^N.  Expected ticket economics use the same boundary:
expected_pre_tax_net = PAYOUT_COEFFICIENT * prod(p*SP) - 1.  Raw unadjusted
products (official_sp_product, log_joint_probability, log_sp_product) are
retained ONLY as explicitly named diagnostics.

REWORK v2 (D2): SIMPLE_ACTIVE capital replicates #207's EQUAL_1PCT exactly:
  requested = pre * risk_fraction
  budget    = min(pre, requested)
  units     = floor(budget / TICKET_STAKE_YUAN)
  counts    = largest-remainder projection of uniform weights * units over the
              K selected tickets (identical to #207 _project_counts)
  funded    = counts.sum() * TICKET_STAKE_YUAN
  payout    = sum_i counts_i * TICKET_STAKE_YUAN * pre_tax_multiple_i
The old implementation truncated the budget to `len(settled)` ticket-count
units (funded ¥16 at K8 instead of ¥1,000) — that bug is removed.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from .contract import (
    ALL_SEEDS,
    K_GRID,
    N_GRID,
    NUISANCE_CANDIDATE_SEEDS,
    OUTCOMES,
    PAYOUT_COEFFICIENT,
    RANKER_FEATURES,
    SIMPLE_ACTIVE_RISK_FRACTION,
    STOCHASTIC_LANES,
    TICKET_STAKE_YUAN,
)
from .census import IssuePanel


class TicketBuildError(RuntimeError):
    """Raised when ticket construction or settlement fails closed."""


def _stable_seed(*parts: object) -> int:
    payload = "|".join(map(str, parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")


def _softmax(values: np.ndarray, temperature: float) -> np.ndarray:
    scaled = (np.asarray(values, dtype=float) - np.max(values)) / temperature
    weights = np.exp(np.clip(scaled, -40.0, 0.0))
    return weights / weights.sum()


def match_score(panel: IssuePanel) -> np.ndarray:
    """Pre-event match score used for candidate pool construction."""
    return (
        np.max(panel.control_probability * panel.predicted_sp, axis=1)
        * np.max(panel.control_probability, axis=1)
    )


def _canonical_ticket_arrays(
    panel: IssuePanel,
    selected: np.ndarray,
    outcomes: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return paired ticket legs ordered by immutable match identity.

    A parlay is an unordered set of ``(match, outcome)`` legs.  Sorting match
    rows and outcomes independently breaks those pairs and makes a mere leg
    permutation look like a distinct ticket.  Keep the arrays paired and use
    the immutable match id as the single canonical ordering key.
    """
    selected_array = np.asarray(selected, dtype=int)
    outcome_array = np.asarray(outcomes, dtype=int)
    if selected_array.ndim != 1 or outcome_array.ndim != 1:
        raise TicketBuildError("ticket legs must be one-dimensional")
    if len(selected_array) != len(outcome_array):
        raise TicketBuildError("ticket match/outcome lengths differ")
    order = np.argsort(panel.match_idx[selected_array], kind="stable")
    return selected_array[order], outcome_array[order]


def _identity(panel: IssuePanel, selected: np.ndarray, outcomes: np.ndarray) -> str:
    selected, outcomes = _canonical_ticket_arrays(panel, selected, outcomes)
    payload = "|".join(
        f"{panel.issue}:{int(panel.match_idx[row])}:{OUTCOMES[int(outcomes[i])]}"
        for i, row in enumerate(selected)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_candidate_pool(
    panel: IssuePanel,
    n: int,
    *,
    draws_per_seed: int = 48,
) -> pd.DataFrame:
    """Generate a bounded candidate pool of exactly-N tickets.

    Mirrors #206: top-mass systematic candidates + weighted draws seeded by the
    frozen nuisance seeds. Candidate pool is shared across lanes/seeds; lane
    selection picks K from the pool. Vectorized construction.
    """
    if n not in N_GRID:
        raise TicketBuildError(f"n out of grid: {n}")
    m = len(panel.match_idx)
    if m < n:
        raise TicketBuildError(
            f"issue {panel.issue} has M={m}; N={n} infeasible"
        )
    scores = match_score(panel)
    ranked = np.argsort(-scores, kind="stable")
    top_width = min(len(ranked), 32)

    # Build the selected-match/outcome matrices (rows = candidate tickets).
    selected_rows: list[np.ndarray] = []
    outcome_rows: list[np.ndarray] = []
    source_rows: list[str] = []
    seen: set[str] = set()

    for offset in range(min(64, max(top_width, 1))):
        stride = 1 + (offset % 5)
        positions = (offset + stride * np.arange(n)) % top_width
        if len(np.unique(positions)) < n:
            positions = (offset + np.arange(n)) % top_width
        selected = ranked[positions]
        outcome_order = np.argsort(
            -panel.control_probability[selected], axis=1, kind="stable"
        )
        outcomes = outcome_order[np.arange(n), (offset // max(top_width, 1)) % 3]
        identity = _identity(panel, selected, outcomes)
        if identity not in seen:
            seen.add(identity)
            selected_rows.append(selected)
            outcome_rows.append(outcomes)
            source_rows.append("TOP_MASS_SYSTEMATIC")

    weights = np.clip(scores, 1e-15, None)
    weights = weights / weights.sum()
    for seed in NUISANCE_CANDIDATE_SEEDS:
        rng = np.random.default_rng(_stable_seed(seed, panel.split, panel.issue))
        for _ in range(draws_per_seed):
            selected = rng.choice(m, size=n, replace=False, p=weights)
            outcomes = np.asarray(
                [
                    rng.choice(3, p=panel.control_probability[row])
                    for row in selected
                ],
                dtype=int,
            )
            identity = _identity(panel, selected, outcomes)
            if identity not in seen:
                seen.add(identity)
                selected_rows.append(selected)
                outcome_rows.append(outcomes)
                source_rows.append("MARKET_WEIGHTED_WOR")

    if len(selected_rows) < max(K_GRID):
        raise TicketBuildError(
            f"issue {panel.issue} N={n} generated only {len(selected_rows)} candidates"
        )
    return _rows_to_frame(panel, selected_rows, outcome_rows, source_rows)


def _rows_to_frame(
    panel: IssuePanel,
    selected_rows: list[np.ndarray],
    outcome_rows: list[np.ndarray],
    source_rows: list[str],
) -> pd.DataFrame:
    """Vectorized ticket-feature computation from selected/outcome matrices."""
    count = len(selected_rows)
    if count == 0:
        return pd.DataFrame()
    canonical_rows = [
        _canonical_ticket_arrays(panel, selected, outcomes)
        for selected, outcomes in zip(selected_rows, outcome_rows, strict=True)
    ]
    selected_matrix = np.stack([row[0] for row in canonical_rows])  # T x n
    outcome_matrix = np.stack([row[1] for row in canonical_rows])  # T x n
    chosen_p = panel.control_probability[selected_matrix, outcome_matrix]
    chosen_sp = panel.predicted_sp[selected_matrix, outcome_matrix]
    chosen_official_sp = panel.official_sp[selected_matrix, outcome_matrix]
    chosen_realized = panel.realized[selected_matrix, outcome_matrix]
    exp_gross = np.prod(chosen_p * chosen_sp, axis=1)
    log_joint = np.sum(np.log(np.clip(chosen_p, 1e-15, 1.0)), axis=1)
    log_sp = np.sum(np.log(np.clip(chosen_sp, 1.0, None)), axis=1)
    outcome_hhi = np.sum(chosen_p**2, axis=1)
    match_rank = np.argsort(
        np.argsort(-np.max(panel.control_probability, axis=1))
    )
    rank_mean = match_rank[selected_matrix].mean(axis=1) / max(len(match_rank), 1)
    hit = np.all(chosen_realized, axis=1)
    # REWORK v3 (PI payout-economics): the pre-tax gross multiple includes the
    # Beijing payout coefficient EXACTLY ONCE per winning N-fold ticket.
    # Never divide it out, never apply per leg, never compound as 0.65^N.
    official_sp_product = np.prod(chosen_official_sp, axis=1)
    if panel.labels_available:
        pre_tax_multiple = np.where(
            hit, PAYOUT_COEFFICIENT * official_sp_product, 0.0
        )
    else:
        pre_tax_multiple = np.full(count, np.nan, dtype=float)
    identities = [
        _identity(panel, selected_matrix[i], outcome_matrix[i])
        for i in range(count)
    ]
    ticket_n = len(selected_matrix[0])
    return pd.DataFrame(
        {
            "issue": panel.issue,
            "split": panel.split,
            "year": panel.year,
            "n": ticket_n,
            "match_indices": [
                "|".join(str(int(x)) for x in panel.match_idx[row])
                for row in selected_matrix
            ],
            "outcomes": [
                "|".join(OUTCOMES[int(x)] for x in row) for row in outcome_matrix
            ],
            "ticket_identity": identities,
            "candidate_source": source_rows,
            "log_joint_probability": log_joint,
            "log_sp_product": log_sp,
            "official_sp_product": official_sp_product,
            # REWORK v3: expected executable ticket economics apply the
            # coefficient once: 0.65 * prod(p*SP) - 1.
            "expected_pre_tax_net": PAYOUT_COEFFICIENT * exp_gross - 1.0,
            "mean_selected_probability": np.mean(chosen_p, axis=1),
            "min_selected_probability": np.min(chosen_p, axis=1),
            "mean_selected_sp": np.mean(chosen_sp, axis=1),
            "outcome_hhi": outcome_hhi,
            "match_rank_mean": rank_mean,
            "realized_hit": hit,
            "pre_tax_gross_multiple": pre_tax_multiple,
        }
    )


def _ticket_row(
    panel: IssuePanel,
    selected: np.ndarray,
    outcomes: np.ndarray,
    source: str,
) -> dict[str, Any]:
    selected, outcomes = _canonical_ticket_arrays(panel, selected, outcomes)
    chosen_p = panel.control_probability[selected, outcomes]
    chosen_sp = panel.predicted_sp[selected, outcomes]
    chosen_official_sp = panel.official_sp[selected, outcomes]
    chosen_realized = panel.realized[selected, outcomes]
    exp_gross = float(np.prod(chosen_p * chosen_sp))
    # REWORK v3 (PI payout-economics): executable expected ticket economics
    # apply the Beijing payout coefficient exactly once: 0.65*prod(p*SP)-1.
    exp_pre_tax_net = PAYOUT_COEFFICIENT * exp_gross - 1.0
    log_joint = float(np.sum(np.log(np.clip(chosen_p, 1e-15, 1.0))))
    log_sp = float(np.sum(np.log(np.clip(chosen_sp, 1.0, None))))
    outcome_hhi = float(np.sum(chosen_p**2))
    match_rank = np.argsort(
        np.argsort(-np.max(panel.control_probability, axis=1))
    )
    rank_mean = float(match_rank[selected].mean() / max(len(match_rank), 1))
    hit = bool(np.all(chosen_realized))
    # Raw unadjusted diagnostic (explicitly named; not a payout multiple).
    official_sp_product = float(np.prod(chosen_official_sp))
    if panel.labels_available:
        pre_tax_multiple = (
            float(PAYOUT_COEFFICIENT * official_sp_product) if hit else 0.0
        )
    else:
        pre_tax_multiple = float("nan")
    return {
        "issue": panel.issue,
        "split": panel.split,
        "year": panel.year,
        "n": len(selected),
        "match_indices": "|".join(
            str(int(x)) for x in panel.match_idx[selected]
        ),
        "outcomes": "|".join(OUTCOMES[int(x)] for x in outcomes),
        "ticket_identity": _identity(panel, selected, outcomes),
        "candidate_source": source,
        "log_joint_probability": log_joint,
        "log_sp_product": log_sp,
        "official_sp_product": official_sp_product,
        "expected_pre_tax_net": exp_pre_tax_net,
        "mean_selected_probability": float(np.mean(chosen_p)),
        "min_selected_probability": float(np.min(chosen_p)),
        "mean_selected_sp": float(np.mean(chosen_sp)),
        "outcome_hhi": outcome_hhi,
        "match_rank_mean": rank_mean,
        "realized_hit": hit,
        "pre_tax_gross_multiple": pre_tax_multiple,
    }


def _lane_rng(lane: str, issue: str, k: int, seed: int) -> np.random.Generator:
    return np.random.default_rng(_stable_seed(lane, issue, k, seed))


def select_tickets(
    pool: pd.DataFrame,
    lane: str,
    k: int,
    *,
    seed: int,
    scores: np.ndarray | None = None,
) -> pd.DataFrame:
    """Select K tickets from the pool under the lane rule.

    MARKET_WR: softmax-weighted sample with replacement over joint prob.
    MARKET_WOR: softmax-weighted sample without replacement.
    VALUE_WOR: deterministic top-K by expected pre-tax net (simple residual).
    LEARNED_MLP: deterministic top-K by learned ranker score.

    REWORK v2 (D3/D4): for stochastic lanes the seed MUST be one of the 16
    preregistered hash seeds (ALL_SEEDS).  seed=0 is rejected — it was used by
    the old execution/controls and is not a registered seed.
    """
    if k <= 0 or pool.empty:
        raise TicketBuildError("invalid ticket-selection request")
    if lane in STOCHASTIC_LANES and seed not in ALL_SEEDS:
        raise TicketBuildError(
            f"stochastic lane {lane} requires a preregistered seed; got {seed}"
        )
    frame = pool.copy()
    if "ticket_identity" not in frame.columns:
        raise TicketBuildError("candidate pool lacks ticket_identity")
    if frame["ticket_identity"].duplicated().any():
        raise TicketBuildError("candidate pool contains semantic duplicate tickets")
    required_leg_columns = {"match_indices", "outcomes"}
    if not required_leg_columns.issubset(frame.columns):
        raise TicketBuildError("candidate pool lacks paired-leg columns")
    semantic_keys = frame.apply(
        lambda row: tuple(
            sorted(
                zip(
                    str(row["match_indices"]).split("|"),
                    str(row["outcomes"]).split("|"),
                    strict=True,
                )
            )
        ),
        axis=1,
    )
    if semantic_keys.duplicated().any():
        raise TicketBuildError("candidate pool contains semantic duplicate tickets")
    if lane != "MARKET_WR" and len(frame) < k:
        raise TicketBuildError(
            f"lane {lane} requested K={k} from only {len(frame)} unique tickets"
        )
    if lane == "MARKET_WR":
        rng = _lane_rng(lane, frame.issue.iloc[0], k, seed)
        probability = _softmax(frame.log_joint_probability.to_numpy(), 1.0)
        index = rng.choice(len(frame), size=k, replace=True, p=probability)
    elif lane == "MARKET_WOR":
        rng = _lane_rng(lane, frame.issue.iloc[0], k, seed)
        probability = _softmax(frame.log_joint_probability.to_numpy(), 1.0)
        index = rng.choice(len(frame), size=k, replace=False, p=probability)
    elif lane == "VALUE_WOR":
        index = np.argsort(
            -frame.expected_pre_tax_net.to_numpy(), kind="stable"
        )[:k]
    elif lane == "LEARNED_MLP":
        if scores is None or len(scores) != len(frame):
            raise TicketBuildError("learned ranker scores are missing")
        index = np.argsort(-np.asarray(scores), kind="stable")[:k]
    else:
        raise TicketBuildError(f"unknown lane {lane}")
    selected = frame.iloc[np.asarray(index, dtype=int)].copy()
    if lane != "MARKET_WR" and selected["ticket_identity"].duplicated().any():
        raise TicketBuildError(f"lane {lane} selected semantic duplicate tickets")
    selected["ticket_order"] = np.arange(1, len(selected) + 1)
    selected["lane"] = lane
    selected["k"] = k
    selected["seed"] = seed
    return selected


def settle_tickets(selected: pd.DataFrame) -> pd.DataFrame:
    """Pre-tax capital ledger rows for a selected K-ticket bundle (vectorized)."""
    multiples = selected["pre_tax_gross_multiple"].to_numpy(dtype=float)
    finite = np.isfinite(multiples)
    payouts = np.where(finite, multiples * TICKET_STAKE_YUAN, 0.0)
    return pd.DataFrame(
        {
            "issue": selected["issue"],
            "split": selected["split"],
            "year": selected["year"],
            "lane": selected["lane"],
            "k": selected["k"],
            "seed": selected["seed"],
            "ticket_order": selected["ticket_order"],
            "ticket_identity": selected["ticket_identity"],
            "match_indices": selected["match_indices"],
            "outcomes": selected["outcomes"],
            "n": selected["n"],
            "requested_stake_yuan": TICKET_STAKE_YUAN,
            "realized_hit": selected["realized_hit"],
            "pre_tax_gross_multiple": selected["pre_tax_gross_multiple"],
            "payout_yuan": payouts,
        }
    )


def bundle_capital(settled: pd.DataFrame, pre_issue_bankroll: float) -> dict[str, float]:
    """Issue-level capital ledger for a native-¥2 K-ticket bundle.

    post = pre - funded + payout, no top-up, integer ¥2 tickets.
    """
    funded = float(len(settled) * TICKET_STAKE_YUAN)
    payout = float(settled["payout_yuan"].sum())
    post = pre_issue_bankroll - funded + payout
    return {
        "pre_issue_bankroll_yuan": float(pre_issue_bankroll),
        "funded_stake_yuan": funded,
        "gross_payout_yuan": payout,
        "post_issue_bankroll_yuan": float(post),
        "net_pnl_yuan": float(post - pre_issue_bankroll),
        "turnover_yuan": funded,
        "funded_ticket_count": int(len(settled)),
    }


def _project_counts(weights: np.ndarray, budget_yuan: float) -> tuple[np.ndarray, float]:
    """Integer ¥2-unit projection with largest-remainder — #207 _project_counts.

    weights: simplex over the K selected tickets.  budget_yuan: total capital
    budget.  Returns (counts, residual) where counts are integer ¥2 units per
    ticket and residual = budget - counts.sum()*2 in [0, 2).
    """
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise TicketBuildError("invalid simplex weights")
    if not np.isclose(weights.sum(), 1.0):
        raise TicketBuildError("weights do not sum to 1")
    units = int(np.floor(budget_yuan / TICKET_STAKE_YUAN))
    raw = weights * units
    counts = np.floor(raw).astype(int)
    remainder = units - int(counts.sum())
    if remainder:
        order = np.argsort(-(raw - counts), kind="stable")
        counts[order[:remainder]] += 1
    residual = float(budget_yuan - counts.sum() * TICKET_STAKE_YUAN)
    if residual < -1e-9 or residual >= TICKET_STAKE_YUAN + 1e-9:
        raise TicketBuildError(
            f"integer projection residual outside [0,2): {residual}"
        )
    return counts, residual


def bundle_capital_equal1pct(
    settled: pd.DataFrame,
    pre_issue_bankroll: float,
    risk_fraction: float = SIMPLE_ACTIVE_RISK_FRACTION,
) -> dict[str, float]:
    """#207 EQUAL_1PCT active control: identical tickets, risk-fraction funding.

    requested = pre * fraction; budget = min(pre, requested); integer ¥2-unit
    projection over the K selected tickets (uniform weights, largest remainder).
    funded = units * 2 — matches #207 ledger (pre=100,000, K8 -> ¥1,000).
    """
    requested = pre_issue_bankroll * risk_fraction
    budget = min(pre_issue_bankroll, requested)
    k = len(settled)
    if k == 0:
        raise TicketBuildError("cannot fund an empty ticket bundle")
    weights = np.full(k, 1.0 / k, dtype=float)
    counts, residual = _project_counts(weights, budget)
    funded = float(counts.sum() * TICKET_STAKE_YUAN)
    multiples = settled["pre_tax_gross_multiple"].to_numpy(dtype=float)
    finite = np.isfinite(multiples)
    payout = float(
        np.sum(np.where(finite, counts * TICKET_STAKE_YUAN * multiples, 0.0))
    )
    post = pre_issue_bankroll - funded + payout
    return {
        "pre_issue_bankroll_yuan": float(pre_issue_bankroll),
        "funded_stake_yuan": funded,
        "gross_payout_yuan": payout,
        "post_issue_bankroll_yuan": float(post),
        "net_pnl_yuan": float(post - pre_issue_bankroll),
        "turnover_yuan": funded,
        "funded_ticket_count": int(counts.sum()),
        "projection_residual_yuan": residual,
        "requested_stake_yuan": float(requested),
    }


def mean_pairwise_overlap(selected: pd.DataFrame) -> float:
    """Mean pairwise Jaccard-like overlap over ticket match sets."""
    match_sets = [
        set(map(int, str(value).split("|")))
        for value in selected["match_indices"]
    ]
    if len(match_sets) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(match_sets)):
        for j in range(i + 1, len(match_sets)):
            inter = len(match_sets[i] & match_sets[j])
            union = len(match_sets[i] | match_sets[j])
            total += inter / union if union else 0.0
            count += 1
    return total / count if count else 0.0


def repeat_exposure(selected: pd.DataFrame) -> float:
    """Mean number of times a ticket identity repeats within the bundle."""
    counts = selected["ticket_identity"].value_counts()
    return float(counts.mean()) if len(counts) else 0.0


def ticket_hhi(selected: pd.DataFrame) -> float:
    counts = selected["ticket_identity"].value_counts(normalize=True)
    return float(np.sum(counts**2))


def fit_learned_ranker(
    train_tickets: pd.DataFrame,
    features: tuple[str, ...] = RANKER_FEATURES,
    *,
    seed: int = 208301,
) -> Any:
    """Fit the LEARNED_MLP lane ranker on labeled development tickets.

    REWORK v2 (D3): early_stopping is disabled (sklearn row-level validation
    could leak across tickets); the ranker is fit on chronological issue-block
    training tickets only, never on 2024/2025/2026.
    """
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    labeled = train_tickets.loc[
        train_tickets["realized_hit"].notna() & train_tickets["labels_available"]
    ].copy()
    if labeled.empty:
        raise TicketBuildError("no labeled development tickets for ranker fit")
    x = labeled.loc[:, list(features)].to_numpy(dtype=float)
    y = labeled["realized_hit"].astype(int).to_numpy()
    model = make_pipeline(
        StandardScaler(),
        MLPClassifier(
            hidden_layer_sizes=(12,),
            alpha=0.01,
            max_iter=120,
            random_state=seed,
            early_stopping=False,
        ),
    )
    model.fit(x, y)
    return model


def ranker_scores(model: Any, pool: pd.DataFrame, features: tuple[str, ...] = RANKER_FEATURES) -> np.ndarray:
    x = pool.loc[:, list(features)].to_numpy(dtype=float)
    return model.predict_proba(x)[:, 1]


__all__ = [
    "TicketBuildError", "bundle_capital", "bundle_capital_equal1pct",
    "fit_learned_ranker", "generate_candidate_pool", "match_score",
    "mean_pairwise_overlap", "ranker_scores", "repeat_exposure",
    "select_tickets", "settle_tickets", "ticket_hhi",
]
