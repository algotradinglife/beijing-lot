"""Issue #209 action-conditioned dynamic ticket policy.

The independent experimental unit is a Beijing issue.  Nuisance ticket seeds
are aggregated inside each issue/action row and are never model features.  The
learner estimates the distribution of bankroll utility for a candidate action
from pre-event issue state plus explicit action parameters, then selects an
action before the issue result is observed.

This module deliberately keeps the first end-to-end action surface bounded.  It
is a learned mapping over N/K/generator choices, not a claim that the largest K
anchor is an operational stake cap or that the best historical grid cell is a
policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from .contract import INITIAL_BANKROLL, SEEDS, TAX_FACTOR, TICKET_STAKE

OUTCOMES = ("3", "1", "0")
OUTCOME_TO_INDEX = {value: index for index, value in enumerate(OUTCOMES)}
GENERATORS = ("TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR")
N_ANCHORS = (3, 5, 7, 8)
K_ANCHORS = (8, 32, 128, 512)
RISK_PENALTY = 0.35
POLICY_SEED = 209101


@dataclass(frozen=True)
class ActionSpec:
    """One explicit, auditable ticket action."""

    n: int
    k: int
    generator: str

    @property
    def key(self) -> str:
        if self.generator == "NO_BET":
            return "NO_BET"
        return f"N{self.n}_K{self.k}_{self.generator}"


def default_action_space() -> tuple[ActionSpec, ...]:
    active = tuple(
        ActionSpec(n=n, k=k, generator=generator)
        for n in N_ANCHORS
        for k in K_ANCHORS
        for generator in GENERATORS
    )
    return (ActionSpec(0, 0, "NO_BET"), *active)


def fixed_control_action() -> ActionSpec:
    """Matched fixed control inherited from the submitted N7/K8 dry-run."""

    return ActionSpec(7, 8, "TOP_VALUE")


def build_issue_states(
    units: pd.DataFrame,
    value: pd.DataFrame,
    probabilities: pd.DataFrame,
    *,
    horizon: str = "10h",
) -> pd.DataFrame:
    """Aggregate a variable-size M×3 pre-event surface to issue state.

    Outcome labels and settlement prices are intentionally not referenced.  The
    state describes candidate breadth, probability/value shape, divergence,
    uncertainty and market context available before settlement.
    """

    mask = units["snapshot_kind"].eq(horizon)
    frame = units.loc[mask].copy()
    aligned_value = value.reindex(frame.index)
    aligned_probability = probabilities.reindex(frame.index)
    rows: list[dict[str, object]] = []
    for issue, group in frame.groupby("issue", sort=True):
        index = group.index
        probs = aligned_probability.loc[index, list(OUTCOMES)].to_numpy(dtype=float)
        ev = aligned_value.loc[index, [f"ev_raw_{c}" for c in OUTCOMES]].to_numpy(
            dtype=float
        )
        q10_columns = [f"value_q10_{c}" for c in OUTCOMES]
        q90_columns = [f"value_q90_{c}" for c in OUTCOMES]
        if set(q10_columns).issubset(aligned_value.columns):
            q10 = aligned_value.loc[index, q10_columns].to_numpy(dtype=float)
            q90 = aligned_value.loc[index, q90_columns].to_numpy(dtype=float)
            interval = np.nanmax(q90 - q10, axis=1)
        else:
            interval = np.zeros(len(group), dtype=float)
        divergence = group[[f"eu_vs_line_divergence_{c}" for c in OUTCOMES]].to_numpy(
            dtype=float
        )
        best_ev = np.nanmax(ev, axis=1)
        sorted_ev = np.sort(np.nan_to_num(ev, nan=-np.inf), axis=1)
        margin = sorted_ev[:, -1] - sorted_ev[:, -2]
        entropy = -np.nansum(
            np.clip(probs, 1e-12, 1.0) * np.log(np.clip(probs, 1e-12, 1.0)), axis=1
        )
        accepted = group["mapping_accepted"].astype(bool).to_numpy()
        rows.append(
            {
                "issue": str(issue),
                "issue_year": int(group["issue_year"].iloc[0]),
                "temporal_role": str(group["temporal_role"].iloc[0]),
                "n_matches": int(group["match_idx"].nunique()),
                "n_accepted": int(accepted.sum()),
                "accepted_fraction": float(accepted.mean()),
                "books_mean": float(group["n_available_books"].mean()),
                "line_abs_mean": float(group["native_handicap_line"].abs().mean()),
                "line_std": float(group["native_handicap_line"].std(ddof=0)),
                "prob_entropy_mean": float(np.nanmean(entropy)),
                "prob_top_mean": float(np.nanmean(np.nanmax(probs, axis=1))),
                "prob_top_q90": _quantile(np.nanmax(probs, axis=1), 0.90),
                "value_best_mean": float(np.nanmean(best_ev)),
                "value_best_std": float(np.nanstd(best_ev)),
                "value_best_q50": _quantile(best_ev, 0.50),
                "value_best_q90": _quantile(best_ev, 0.90),
                "value_margin_mean": float(np.nanmean(margin)),
                "value_interval_mean": float(np.nanmean(interval)),
                "divergence_abs_mean": float(np.nanmean(np.abs(divergence))),
                "divergence_abs_q90": _quantile(np.abs(divergence).ravel(), 0.90),
                "divergence_signed_mean": float(np.nanmean(divergence)),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("no issue state is available for the requested horizon")
    return result.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def _quantile(values: np.ndarray, q: float) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.quantile(finite, q)) if len(finite) else 0.0


def evaluate_counterfactual_actions(
    units: pd.DataFrame,
    value: pd.DataFrame,
    probabilities: pd.DataFrame,
    tensor: pd.DataFrame,
    states: pd.DataFrame,
    *,
    actions: Iterable[ActionSpec] | None = None,
    horizon: str = "10h",
    seeds: tuple[int, ...] = SEEDS,
) -> pd.DataFrame:
    """Settle every development action, aggregating seeds within issue/action.

    These outcomes are training labels.  They are never passed to
    :func:`build_issue_states` or :func:`action_features`.
    """

    action_space = tuple(actions or default_action_space())
    unit_h = units[units["snapshot_kind"].eq(horizon)]
    winners = tensor[tensor["Y"].eq(1)].drop_duplicates(["issue", "match_idx"])
    winner_lookup = {
        str(issue): group.set_index("match_idx")[["realized_outcome", "SP_SETTLE"]]
        for issue, group in winners.groupby("issue")
    }
    state_meta = states.set_index("issue")[["issue_year", "temporal_role"]]
    rows: list[dict[str, object]] = []
    for issue, group in unit_h.groupby("issue", sort=True):
        issue_text = str(issue)
        index = group.index
        ev = value.reindex(index)[[f"ev_raw_{c}" for c in OUTCOMES]].to_numpy(dtype=float)
        probs = probabilities.reindex(index)[list(OUTCOMES)].to_numpy(dtype=float)
        match_ids = group["match_idx"].to_numpy(dtype=int)
        settlement = winner_lookup.get(issue_text)
        if settlement is None:
            continue
        realized = np.array(
            [OUTCOME_TO_INDEX.get(str(settlement["realized_outcome"].get(m)), -1) for m in match_ids],
            dtype=int,
        )
        winning_sp = np.array(
            [float(settlement["SP_SETTLE"].get(m, np.nan)) for m in match_ids], dtype=float
        )
        for action in action_space:
            if action.generator == "NO_BET":
                seed_pnl = np.zeros(len(seeds), dtype=float)
                seed_hits = np.zeros(len(seeds), dtype=float)
                effective_k = 0
            elif len(match_ids) < action.n:
                continue
            else:
                pnl_values = []
                hit_values = []
                effective_values = []
                for nuisance_seed in seeds:
                    ticket_matches, ticket_outcomes = generate_tickets(
                        ev,
                        probs,
                        action,
                        seed=_derived_seed(nuisance_seed, issue_text, action.key),
                    )
                    pnl, hit_rate = settle_ticket_arrays(
                        ticket_matches,
                        ticket_outcomes,
                        realized,
                        winning_sp,
                    )
                    pnl_values.append(pnl)
                    hit_values.append(hit_rate)
                    effective_values.append(len(ticket_matches))
                seed_pnl = np.asarray(pnl_values, dtype=float)
                seed_hits = np.asarray(hit_values, dtype=float)
                effective_k = int(min(effective_values))
            utility = 10_000.0 * np.log1p(seed_pnl / INITIAL_BANKROLL)
            rows.append(
                {
                    "issue": issue_text,
                    "issue_year": int(state_meta.loc[issue_text, "issue_year"]),
                    "temporal_role": str(state_meta.loc[issue_text, "temporal_role"]),
                    "action_key": action.key,
                    **asdict(action),
                    "effective_k": effective_k,
                    "stake_total": float(effective_k * TICKET_STAKE),
                    "seed_count": len(seeds),
                    "utility_bps": float(np.mean(utility)),
                    "utility_seed_q10_bps": float(np.quantile(utility, 0.10)),
                    "utility_seed_std_bps": float(np.std(utility, ddof=0)),
                    "mean_pnl": float(np.mean(seed_pnl)),
                    "pnl_seed_q10": float(np.quantile(seed_pnl, 0.10)),
                    "mean_hit_rate": float(np.mean(seed_hits)),
                }
            )
    return pd.DataFrame(rows).sort_values(["issue_year", "issue", "action_key"]).reset_index(
        drop=True
    )


def _derived_seed(seed: int, issue: str, action_key: str) -> int:
    # Stable FNV-1a-style mixer; the resulting seed is evidence metadata only.
    payload = f"{seed}:{issue}:{action_key}".encode("utf-8")
    value = 2166136261
    for byte in payload:
        value = (value ^ byte) * 16777619 & 0xFFFFFFFF
    return int(value)


def generate_tickets(
    ev: np.ndarray,
    probabilities: np.ndarray,
    action: ActionSpec,
    *,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate ticket arrays of match positions and outcome indices.

    Matches are always sampled without replacement *inside* a ticket. WR/WOR
    describes replacement of complete ticket identities across the K draws.
    """

    if action.generator not in GENERATORS:
        raise ValueError(f"unsupported generator: {action.generator}")
    if action.n <= 0 or action.k <= 0 or action.n > len(ev):
        raise ValueError("invalid active action dimensions")
    clean_ev = np.nan_to_num(ev, nan=0.0, posinf=0.0, neginf=0.0)
    clean_prob = np.nan_to_num(probabilities, nan=0.0, posinf=0.0, neginf=0.0)
    branch_weight = np.clip(clean_ev, 1e-12, None)
    match_weight = np.clip(branch_weight.max(axis=1), 1e-12, None)
    if action.generator == "TOP_VALUE":
        chosen = np.argsort(-match_weight, kind="stable")[: action.n]
        outcomes = np.argmax(branch_weight[chosen], axis=1)
        return (
            np.repeat(chosen[None, :], action.k, axis=0),
            np.repeat(outcomes[None, :], action.k, axis=0),
        )

    rng = np.random.default_rng(seed)
    wanted = action.k
    collected_matches: list[np.ndarray] = []
    collected_outcomes: list[np.ndarray] = []
    identities: set[tuple[tuple[int, int], ...]] = set()
    attempts = 0
    while len(collected_matches) < wanted and attempts < 20:
        batch = max(32, (wanted - len(collected_matches)) * 2)
        gumbel = rng.gumbel(size=(batch, len(match_weight)))
        score = np.log(match_weight)[None, :] + gumbel
        matches = np.argpartition(score, -action.n, axis=1)[:, -action.n :]
        for match_row in matches:
            # Stable order makes the identity and settlement deterministic.
            match_row = match_row[np.argsort(match_row)]
            outcome_rows = []
            for match_pos in match_row:
                weights = branch_weight[match_pos]
                if not np.isfinite(weights).all() or weights.sum() <= 0:
                    weights = np.clip(clean_prob[match_pos], 1e-12, None)
                outcome_rows.append(int(rng.choice(len(OUTCOMES), p=weights / weights.sum())))
            outcome_row = np.asarray(outcome_rows, dtype=int)
            identity = tuple(sorted(zip(match_row.tolist(), outcome_row.tolist())))
            if action.generator == "WEIGHTED_WOR" and identity in identities:
                continue
            identities.add(identity)
            collected_matches.append(match_row.copy())
            collected_outcomes.append(outcome_row)
            if len(collected_matches) >= wanted:
                break
        attempts += 1
    return np.asarray(collected_matches, dtype=int), np.asarray(collected_outcomes, dtype=int)


def settle_ticket_arrays(
    ticket_matches: np.ndarray,
    ticket_outcomes: np.ndarray,
    realized_outcomes: np.ndarray,
    winning_sp: np.ndarray,
) -> tuple[float, float]:
    """Settle a ticket panel against one shared issue outcome state."""

    if len(ticket_matches) == 0:
        return 0.0, 0.0
    realized = realized_outcomes[ticket_matches]
    valid_sp = winning_sp[ticket_matches]
    hit = np.all(ticket_outcomes == realized, axis=1) & np.all(
        np.isfinite(valid_sp) & (valid_sp > 0), axis=1
    )
    gross = np.zeros(len(ticket_matches), dtype=float)
    if hit.any():
        gross[hit] = TICKET_STAKE * TAX_FACTOR * np.prod(valid_sp[hit], axis=1)
    stake = len(ticket_matches) * TICKET_STAKE
    return float(gross.sum() - stake), float(hit.mean())


STATE_FEATURES = (
    "n_matches",
    "n_accepted",
    "accepted_fraction",
    "books_mean",
    "line_abs_mean",
    "line_std",
    "prob_entropy_mean",
    "prob_top_mean",
    "prob_top_q90",
    "value_best_mean",
    "value_best_std",
    "value_best_q50",
    "value_best_q90",
    "value_margin_mean",
    "value_interval_mean",
    "divergence_abs_mean",
    "divergence_abs_q90",
    "divergence_signed_mean",
)


def action_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the explicit pre-outcome state/action feature matrix."""

    result = frame.loc[:, list(STATE_FEATURES)].astype(float).copy()
    result["action_n"] = frame["n"].astype(float)
    result["action_log2_k"] = np.log2(frame["k"].astype(float).clip(lower=1.0))
    result["action_stake_fraction"] = frame["stake_total"].astype(float) / INITIAL_BANKROLL
    result["n_x_entropy"] = result["action_n"] * result["prob_entropy_mean"]
    result["n_x_value"] = result["action_n"] * result["value_best_mean"]
    result["n_x_divergence"] = result["action_n"] * result["divergence_abs_mean"]
    result["k_x_breadth"] = result["action_log2_k"] / result["n_matches"].clip(lower=1.0)
    result["k_x_uncertainty"] = result["action_log2_k"] * result["value_interval_mean"]
    for generator in ("NO_BET", *GENERATORS):
        indicator = frame["generator"].eq(generator).astype(float)
        result[f"generator_{generator}"] = indicator
        result[f"generator_{generator}_x_divergence"] = (
            indicator * result["divergence_abs_mean"]
        )
    if any(
        forbidden in result.columns
        for forbidden in ("seed", "Y", "SP_SETTLE", "realized_outcome", "mean_pnl")
    ):
        raise AssertionError("outcome or seed leaked into action features")
    return result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def join_states_and_actions(states: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    joined = outcomes.merge(
        states.drop(columns=["issue_year", "temporal_role"]), on="issue", how="left", validate="many_to_one"
    )
    if joined[list(STATE_FEATURES)].isna().all(axis=None):
        raise ValueError("issue states did not join action outcomes")
    return joined


def fit_action_models(
    training: pd.DataFrame,
    *,
    families: tuple[str, ...] = ("LOGISTIC_TWO_PART", "MLP_TWO_PART"),
    seed: int = POLICY_SEED,
) -> dict[str, object]:
    """Fit bounded maintained-library mean and downside action models."""

    x = action_features(training)
    target = training["utility_bps"].to_numpy(dtype=float)
    pnl = training["mean_pnl"].to_numpy(dtype=float)
    positive = (pnl > 0.0).astype(int)
    counts = training.groupby("issue")["action_key"].transform("count").to_numpy(dtype=float)
    weights = 1.0 / np.clip(counts, 1.0, None)
    x_scaler = StandardScaler().fit(x)
    xs = x_scaler.transform(x)
    y_clip = float(max(50.0, np.quantile(np.abs(target), 0.995)))
    y = np.clip(target, -y_clip, y_clip)
    bundles: dict[str, object] = {
        "feature_columns": list(x.columns),
        "x_scaler": x_scaler,
        "target_clip_bps": y_clip,
    }
    if "LOGISTIC_TWO_PART" in families:
        classifier = LogisticRegression(C=0.2, max_iter=2000, solver="lbfgs")
        classifier.fit(xs, positive, sample_weight=weights)
        bundles["LOGISTIC_TWO_PART"] = classifier
    if "MLP_TWO_PART" in families:
        mlp = MLPClassifier(
            hidden_layer_sizes=(64, 32),
            activation="relu",
            solver="adam",
            alpha=0.01,
            batch_size=256,
            learning_rate_init=5e-4,
            max_iter=300,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
            random_state=seed,
        )
        mlp.fit(xs, positive, sample_weight=weights)
        bundles["MLP_TWO_PART"] = mlp
    positive_mask = positive == 1
    nonpositive_mask = ~positive_mask
    if positive_mask.sum() < 100 or nonpositive_mask.sum() < 100:
        raise ValueError("two-part action model lacks positive or non-positive support")
    positive_payoff = HistGradientBoostingRegressor(
        loss="squared_error",
        max_iter=160,
        learning_rate=0.06,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=2.0,
        random_state=seed,
    )
    positive_payoff.fit(
        x.loc[positive_mask], np.log1p(pnl[positive_mask]), sample_weight=weights[positive_mask]
    )
    stake = training["stake_total"].to_numpy(dtype=float)
    loss_fraction = np.clip(-pnl / np.clip(stake, TICKET_STAKE, None), 0.0, 1.0)
    nonpositive_loss = HistGradientBoostingRegressor(
        loss="squared_error",
        max_iter=160,
        learning_rate=0.06,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=2.0,
        random_state=seed,
    )
    nonpositive_loss.fit(
        x.loc[nonpositive_mask],
        loss_fraction[nonpositive_mask],
        sample_weight=weights[nonpositive_mask],
    )
    bundles["POSITIVE_PAYOFF"] = positive_payoff
    bundles["NONPOSITIVE_LOSS_FRACTION"] = nonpositive_loss
    downside = HistGradientBoostingRegressor(
        loss="quantile",
        quantile=0.10,
        max_iter=180,
        learning_rate=0.06,
        max_leaf_nodes=15,
        min_samples_leaf=40,
        l2_regularization=2.0,
        random_state=seed,
    )
    downside.fit(x, y, sample_weight=weights)
    bundles["DOWNSIDE_Q10"] = downside
    return bundles


def predict_action_models(bundle: dict[str, object], frame: pd.DataFrame, family: str) -> pd.DataFrame:
    x = action_features(frame)
    expected_columns = list(bundle["feature_columns"])
    if list(x.columns) != expected_columns:
        raise ValueError("dynamic action feature schema drift")
    xs = bundle["x_scaler"].transform(x)
    positive_probability = bundle[family].predict_proba(xs)[:, 1]
    positive_pnl = np.expm1(bundle["POSITIVE_PAYOFF"].predict(x))
    loss_fraction = np.clip(bundle["NONPOSITIVE_LOSS_FRACTION"].predict(x), 0.0, 1.0)
    negative_pnl = -frame["stake_total"].to_numpy(dtype=float) * loss_fraction
    expected_pnl = positive_probability * positive_pnl + (1.0 - positive_probability) * negative_pnl
    mean = 10_000.0 * np.log1p(expected_pnl / INITIAL_BANKROLL)
    q10 = bundle["DOWNSIDE_Q10"].predict(x)
    result = frame[["issue", "issue_year", "temporal_role", "action_key", "n", "k", "generator"]].copy()
    result["predicted_mean_utility_bps"] = mean
    result["predicted_positive_probability"] = positive_probability
    result["predicted_positive_pnl"] = positive_pnl
    result["predicted_nonpositive_pnl"] = negative_pnl
    result["predicted_q10_utility_bps"] = q10
    result["predicted_risk_score"] = mean + RISK_PENALTY * np.minimum(q10, 0.0)
    cash = result["generator"].eq("NO_BET")
    result.loc[
        cash,
        ["predicted_mean_utility_bps", "predicted_q10_utility_bps", "predicted_risk_score"],
    ] = 0.0
    return result


def select_policy_actions(
    predictions: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    allow_no_bet: bool = True,
) -> pd.DataFrame:
    """Choose one pre-outcome action per issue from predictions only."""

    eligible = predictions if allow_no_bet else predictions[predictions["generator"].ne("NO_BET")]
    selected = (
        eligible.sort_values(
            ["issue", "predicted_risk_score", "action_key"],
            ascending=[True, False, True],
            kind="stable",
        )
        .groupby("issue", as_index=False)
        .first()
    )
    # Actual outcomes are joined only after the selection identity is frozen.
    actual_columns = [
        "issue",
        "action_key",
        "utility_bps",
        "mean_pnl",
        "stake_total",
        "mean_hit_rate",
    ]
    return selected.merge(actual[actual_columns], on=["issue", "action_key"], how="left", validate="one_to_one")


def family_selection_receipt(
    bundles: dict[str, object],
    tune: pd.DataFrame,
    *,
    families: tuple[str, ...] = ("LOGISTIC_TWO_PART", "MLP_TWO_PART"),
) -> tuple[str, dict[str, dict[str, float]], pd.DataFrame]:
    """Select a model family on 2022 issue-level policy utility only."""

    metrics: dict[str, dict[str, float]] = {}
    prediction_frames = []
    for family in families:
        predictions = predict_action_models(bundles, tune, family)
        predictions["model_family"] = family
        # Model-family selection evaluates genuine active parameter choice.  The
        # separate capital-safe arm may choose NO_BET after the family is frozen.
        selected = select_policy_actions(predictions, tune, allow_no_bet=False)
        metrics[family] = {
            "issues": float(selected["issue"].nunique()),
            "mean_selected_utility_bps": float(selected["utility_bps"].mean()),
            "total_selected_pnl": float(selected["mean_pnl"].sum()),
            "active_fraction": float(selected["generator"].ne("NO_BET").mean()),
        }
        prediction_frames.append(predictions)
    family = max(
        families,
        key=lambda name: (metrics[name]["mean_selected_utility_bps"], -families.index(name)),
    )
    return family, metrics, pd.concat(prediction_frames, ignore_index=True)


def fixed_control_results(counterfactuals: pd.DataFrame) -> pd.DataFrame:
    key = fixed_control_action().key
    return counterfactuals[counterfactuals["action_key"].eq(key)].copy()


def oracle_diagnostic(counterfactuals: pd.DataFrame) -> pd.DataFrame:
    """Outcome-aware ceiling for regret diagnosis only; never a policy input."""

    return (
        counterfactuals.sort_values(
            ["issue", "utility_bps", "action_key"], ascending=[True, False, True], kind="stable"
        )
        .groupby("issue", as_index=False)
        .first()[["issue", "action_key", "utility_bps", "mean_pnl"]]
        .rename(columns={
            "action_key": "oracle_action_key",
            "utility_bps": "oracle_utility_bps",
            "mean_pnl": "oracle_mean_pnl",
        })
    )
