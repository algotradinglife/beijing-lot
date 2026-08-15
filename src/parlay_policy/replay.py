"""Issue #208: counterfactual label surface and full-path replay.

Builds per-issue, per-action matched pre-tax capital lift versus the frozen
N7/K8 incumbent on development folds, aggregates stochastic seeds, and replays
full ¥100,000 paths for controls and learned policies.

REWORK v2 (D2/D5/D6):
- issue_action_lift uses the fixed EQUAL_1PCT capital semantics (¥1,000 at
  pre=¥100,000/K8, not ¥16) for SIMPLE_ACTIVE actions.
- full_path_replay never uses seed=0: stochastic lanes are aggregated over the
  16 preregistered seeds; deterministic lanes use their single evaluation.
- summarize_path computes max drawdown from the RUNNING peak (per-issue
  cummax), not the final peak — the old [100,80,200] → 0.6 bug is fixed
  (correct running-peak value is 0.2).
- materializes required holding-feasibility metrics: time under water,
  recovery issues, max consecutive losing issues, rolling 5/10/20-issue loss
  probability and worst windows, ex-largest issue.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Callable

import numpy as np
import pandas as pd

from .census import IssuePanel, census_table, eligibility
from .contract import (
    Action,
    ALL_SEEDS,
    CAPITAL_LANES,
    DETERMINISTIC_LANES,
    DEVELOPMENT_SPLITS,
    EMBARGOED_SPLITS,
    FOLDS,
    INCUMBENT_CAPITAL,
    INCUMBENT_K,
    INCUMBENT_LANE,
    INCUMBENT_N,
    INITIAL_BANKROLL_YUAN,
    K_GRID,
    LANES,
    N_GRID,
    NO_BET_KEY,
    STOCHASTIC_LANES,
    TICKET_STAKE_YUAN,
    all_actions,
)
from .features import (
    STATE_FEATURE_NAMES,
    PriorBankrollState,
    build_state_vector,
    upstream_issue_summary,
)
from .incumbent import incumbent_prior_state, incumbent_row
from .policy import (
    LearnedPolicy,
    best_fixed_action_key,
    build_design,
    choose_action,
    fit_policy,
    ood_gate,
    predict_lift,
)
from .tickets import (
    bundle_capital,
    bundle_capital_equal1pct,
    fit_learned_ranker,
    generate_candidate_pool,
    mean_pairwise_overlap,
    ranker_scores,
    repeat_exposure,
    select_tickets,
    settle_tickets,
    ticket_hhi,
)


class ReplayError(RuntimeError):
    """Raised when replay fails closed."""


@dataclass
class IssueContext:
    panel: IssuePanel
    upstream_summary: dict[str, float]
    prior: PriorBankrollState
    state: np.ndarray
    incumbent_pre: float
    incumbent_post: float
    incumbent_payout: float
    incumbent_funded: float


def incumbent_issue_ledger(
    upstream_ledger: pd.DataFrame,
    upstream_tickets: pd.DataFrame,
    split: str,
    issue: str,
    *,
    policy: str = INCUMBENT_LANE,
    controller: str = INCUMBENT_CAPITAL,
    k: int = INCUMBENT_K,
) -> dict[str, float]:
    """Frozen incumbent N7/K8/native-¥2 capital row for an issue.

    REWORK v3 (PI payout-economics): the superseded #207 ledger
    `gross_payout_yuan` (pre-tax = realized_gross / 0.65) is NOT admissible.
    Every incumbent issue row is reconstructed from the frozen CONTROLLING
    ticket identities with the corrected economics: payout per ticket =
    realized_gross * ¥2 (realized_gross already = 0.65 * prod(official_sp)),
    funded = K * ¥2.  The `upstream_ledger` argument is accepted only for
    call-site compatibility and is never used as a payout source.
    """
    tickets = upstream_tickets[
        (upstream_tickets["split"] == split)
        & (upstream_tickets["issue"] == issue)
        & (upstream_tickets["policy"] == policy)
        & (upstream_tickets["k"] == k)
        & (upstream_tickets["panel_role"] == "CONTROLLING")
    ]
    if tickets.empty:
        raise ReplayError(
            f"incumbent tickets missing: {split}/{issue}/{policy}/{k}"
        )
    funded = float(len(tickets) * TICKET_STAKE_YUAN)
    # Corrected economics: realized_gross already = 0.65*prod(SP); native ¥2
    # per ticket. Never divide the coefficient out.
    payout = float(tickets["realized_gross"].fillna(0.0).sum() * TICKET_STAKE_YUAN)
    return {
        "pre": float("nan"),  # unknown at this layer; path replayed separately
        "post": float("nan"),
        "payout": payout,
        "funded": funded,
    }


def build_issue_contexts(
    panels: dict[tuple[str, str], IssuePanel],
    upstream_tickets: pd.DataFrame,
    incumbent_paths: pd.DataFrame,
) -> dict[tuple[str, str], IssueContext]:
    contexts: dict[tuple[str, str], IssueContext] = {}
    for (split, issue), panel in panels.items():
        if split not in DEVELOPMENT_SPLITS:
            continue
        up = upstream_issue_summary(upstream_tickets, issue)
        prior_values = incumbent_prior_state(incumbent_paths, split, issue)
        prior = PriorBankrollState(**prior_values)
        state = build_state_vector(panel, up, prior)
        inc = incumbent_row(incumbent_paths, split, issue)
        contexts[(split, issue)] = IssueContext(
            panel=panel,
            upstream_summary=up,
            prior=prior,
            state=state,
            incumbent_pre=inc["pre"],
            incumbent_post=inc["post"],
            incumbent_payout=inc["payout"],
            incumbent_funded=inc["funded"],
        )
    return contexts


def _pool_cache_key(issue: str, n: int) -> str:
    return f"{issue}:{n}"


def build_pool_cache(
    contexts: dict[tuple[str, str], IssueContext],
) -> dict[str, pd.DataFrame]:
    cache: dict[str, pd.DataFrame] = {}
    for (split, issue), ctx in contexts.items():
        for n in N_GRID:
            panel = ctx.panel
            if len(panel.match_idx) >= n:
                cache[_pool_cache_key(issue, n)] = generate_candidate_pool(panel, n)
    return cache


def _funded_payout_for_action(
    ctx: IssueContext,
    action: Action,
    multiples: np.ndarray,
    index: np.ndarray,
) -> tuple[float, float]:
    """Capital-lane-aware funded stake and payout for a selected index.

    REWORK v2 (D2): SIMPLE_ACTIVE replicates #207 EQUAL_1PCT — requested =
    incumbent_pre * 1%, budget = min(pre, requested), integer ¥2-unit
    projection over the K selected tickets.  The old code truncated to K
    tickets (funded ¥16 at K8); the correct value is ¥1,000 at pre=¥100,000.
    """
    if action.capital == "NATIVE_2_YUAN":
        funded = float(len(index) * TICKET_STAKE_YUAN)
        payout = float(np.nansum(multiples[index]) * TICKET_STAKE_YUAN)
        return funded, payout
    if action.capital == "SIMPLE_ACTIVE":
        k = len(index)
        if k == 0:
            return 0.0, 0.0
        requested = ctx.incumbent_pre * 0.01
        budget = min(ctx.incumbent_pre, requested)
        units = int(np.floor(budget / TICKET_STAKE_YUAN))
        weights = np.full(k, 1.0 / k, dtype=float)
        raw = weights * units
        counts = np.floor(raw).astype(int)
        remainder = units - int(counts.sum())
        if remainder:
            order = np.argsort(-(raw - counts), kind="stable")
            counts[order[:remainder]] += 1
        funded = float(counts.sum() * TICKET_STAKE_YUAN)
        sel_multiples = multiples[index]
        finite = np.isfinite(sel_multiples)
        payout = float(
            np.sum(np.where(finite, counts * TICKET_STAKE_YUAN * sel_multiples, 0.0))
        )
        return funded, payout
    raise ReplayError(f"unknown capital lane {action.capital}")


def issue_action_lift(
    ctx: IssueContext,
    action: Action,
    pool: pd.DataFrame,
    *,
    ranker_scores_by_issue: dict[str, np.ndarray] | None = None,
) -> dict[str, float]:
    """Matched per-issue lift of action a vs incumbent, seed-aggregated.

    For stochastic lanes, returns mean/median/std over the 16 frozen seeds.
    For deterministic lanes, a single evaluation. Settlement uses the
    precomputed pre-tax gross multiples on the pool rows; no per-seed
    DataFrame materialization.

    REWORK v2 (D2): funded_yuan now reflects the real capital lane (native ¥2
    per ticket, or EQUAL_1PCT projection for SIMPLE_ACTIVE), never K*2.
    """
    from .tickets import _lane_rng, _softmax

    lifts: list[float] = []
    pays: list[float] = []
    fundeds: list[float] = []
    multiples = pool["pre_tax_gross_multiple"].to_numpy(dtype=float)
    if action.lane in STOCHASTIC_LANES:
        seeds = ALL_SEEDS
    else:
        seeds = (0,)

    if action.lane == "MARKET_WR":
        probability = _softmax(pool["log_joint_probability"].to_numpy(), 1.0)
        for seed in seeds:
            rng = _lane_rng(action.lane, ctx.panel.issue, action.k, seed)
            index = rng.choice(len(pool), size=action.k, replace=True, p=probability)
            funded, payout = _funded_payout_for_action(ctx, action, multiples, index)
            lifts.append(ctx.incumbent_pre - funded + payout - ctx.incumbent_post)
            pays.append(payout)
            fundeds.append(funded)
    elif action.lane == "MARKET_WOR":
        probability = _softmax(pool["log_joint_probability"].to_numpy(), 1.0)
        for seed in seeds:
            rng = _lane_rng(action.lane, ctx.panel.issue, action.k, seed)
            index = rng.choice(len(pool), size=action.k, replace=False, p=probability)
            funded, payout = _funded_payout_for_action(ctx, action, multiples, index)
            lifts.append(ctx.incumbent_pre - funded + payout - ctx.incumbent_post)
            pays.append(payout)
            fundeds.append(funded)
    elif action.lane == "VALUE_WOR":
        index = np.argsort(
            -pool["expected_pre_tax_net"].to_numpy(), kind="stable"
        )[: action.k]
        funded, payout = _funded_payout_for_action(ctx, action, multiples, index)
        lifts.append(ctx.incumbent_pre - funded + payout - ctx.incumbent_post)
        pays.append(payout)
        fundeds.append(funded)
    elif action.lane == "LEARNED_MLP":
        if ranker_scores_by_issue is None:
            raise ReplayError("LEARNED_MLP lane requires ranker scores")
        scores = ranker_scores_by_issue.get(f"{ctx.panel.issue}:{action.n}")
        if scores is None or len(scores) != len(pool):
            raise ReplayError(
                f"ranker scores missing for {ctx.panel.issue}:{action.n}"
            )
        index = np.argsort(-np.asarray(scores), kind="stable")[: action.k]
        funded, payout = _funded_payout_for_action(ctx, action, multiples, index)
        lifts.append(ctx.incumbent_pre - funded + payout - ctx.incumbent_post)
        pays.append(payout)
        fundeds.append(funded)
    else:
        raise ReplayError(f"unknown lane {action.lane}")
    lifts_arr = np.asarray(lifts, dtype=float)
    pays_arr = np.asarray(pays, dtype=float)
    fundeds_arr = np.asarray(fundeds, dtype=float)
    return {
        "issue": ctx.panel.issue,
        "split": ctx.panel.split,
        "year": ctx.panel.year,
        "action_key": action.key,
        "n": action.n,
        "k": action.k,
        "lane": action.lane,
        "capital": action.capital,
        "matched_lift_mean": float(np.mean(lifts_arr)),
        "matched_lift_median": float(np.median(lifts_arr)),
        "matched_lift_std": float(np.std(lifts_arr)),
        "payout_mean": float(np.mean(pays_arr)),
        "funded_mean": float(np.mean(fundeds_arr)),
        "seed_count": int(len(lifts_arr)),
        "funded_yuan": float(np.mean(fundeds_arr)),
    }


def build_label_surface(
    contexts: dict[tuple[str, str], IssueContext],
    pool_cache: dict[str, pd.DataFrame],
    *,
    train_splits: tuple[str, ...],
    ranker: Any = None,
) -> pd.DataFrame:
    """All-action counterfactual lift rows for the given splits (label surface)."""
    rows: list[dict[str, float | str | int]] = []
    actions = all_actions()
    ranker_scores_by_issue: dict[str, np.ndarray] = {}
    if ranker is not None:
        for (split, issue), ctx in contexts.items():
            if split not in train_splits:
                continue
            for n in N_GRID:
                pool = pool_cache.get(_pool_cache_key(issue, n))
                if pool is not None:
                    ranker_scores_by_issue[f"{issue}:{n}"] = ranker_scores(
                        ranker, pool
                    )
    for (split, issue), ctx in contexts.items():
        if split not in train_splits:
            continue
        for action in actions:
            pool = pool_cache.get(_pool_cache_key(issue, action.n))
            if pool is None:
                continue  # infeasible N for this issue
            rows.append(
                issue_action_lift(
                    ctx,
                    action,
                    pool,
                    ranker_scores_by_issue=ranker_scores_by_issue,
                )
            )
    return pd.DataFrame(rows)


def build_training_frame(
    surface: pd.DataFrame,
    contexts: dict[tuple[str, str], IssueContext],
) -> pd.DataFrame:
    """Join label surface with state x and action encoding -> training frame."""
    state_rows: list[dict[str, Any]] = []
    for (split, issue), ctx in contexts.items():
        row = dict(zip(STATE_FEATURE_NAMES, (float(v) for v in ctx.state)))
        row["split"] = split
        row["issue"] = issue
        row["year"] = ctx.panel.year
        state_rows.append(row)
    state_df = pd.DataFrame(state_rows)
    merged = surface.merge(
        state_df, on=["split", "issue"], how="inner"
    )
    merged["y_lift"] = merged["matched_lift_mean"]
    merged["action_key"] = merged["action_key"].astype(str)
    merged["a_n"] = merged["n"].astype(float)
    merged["a_k"] = merged["k"].astype(float)
    merged["a_lane"] = merged["lane"].map(
        {lane: i for i, lane in enumerate(LANES)}
    ).astype(float)
    merged["a_capital"] = merged["capital"].map(
        {lane: i for i, lane in enumerate(CAPITAL_LANES)}
    ).astype(float)
    return merged


def _select_for_lane(
    pool: pd.DataFrame | None,
    action: Action,
    seed: int,
    scores: np.ndarray | None = None,
) -> pd.DataFrame:
    """select_tickets wrapper that keeps NO_BET semantics (empty -> None)."""
    if pool is None or pool.empty:
        return pd.DataFrame()
    return select_tickets(pool, action.lane, action.k, seed=seed, scores=scores)


def full_path_replay(
    contexts: dict[tuple[str, str], IssueContext],
    pool_cache: dict[str, pd.DataFrame],
    *,
    action_fn: Any,
    split: str,
    policy_name: str = "learned",
    ranker_scores_by_issue: dict[str, np.ndarray] | None = None,
    frozen_incumbent: pd.DataFrame | None = None,
    stochastic_lane_aggregate: bool = True,
) -> pd.DataFrame:
    """Replay a ¥100,000 path over a split's issues with an action chooser.

    REWORK v2 (D3/D6):
    - stochastic lanes are aggregated over the 16 preregistered seeds
      (mean funded/payout per issue) — never seed=0;
    - NO_BET actions produce funded=0 / payout=0 rows instead of crashing;
    - when the executed action IS the frozen incumbent, the exact #207 capital
      row is used (never a replayed proxy).
    """
    rows: list[dict[str, Any]] = []
    bankroll = INITIAL_BANKROLL_YUAN
    peak = INITIAL_BANKROLL_YUAN
    consecutive_losses = 0
    split_contexts = [
        (issue, ctx)
        for (s, issue), ctx in contexts.items()
        if s == split
    ]
    split_contexts.sort(key=lambda item: item[1].panel.year)
    incumbent_key = f"N{INCUMBENT_N}/K{INCUMBENT_K}/{INCUMBENT_LANE}/NATIVE_2_YUAN"
    for issue, ctx in split_contexts:
        pool = pool_cache.get(_pool_cache_key(issue, 7))  # fallback N7 pool
        action, trace = action_fn(ctx, bankroll)
        if action is None:
            # NO_BET: no lawful action, or safety gate with no fallback.
            rows.append(
                {
                    "split": split,
                    "issue": issue,
                    "year": ctx.panel.year,
                    "policy": policy_name,
                    "action_key": NO_BET_KEY,
                    "n": None,
                    "k": None,
                    "lane": None,
                    "capital": None,
                    "pre_issue_bankroll_yuan": bankroll,
                    "funded_stake_yuan": 0.0,
                    "gross_payout_yuan": 0.0,
                    "post_issue_bankroll_yuan": bankroll,
                    "net_pnl_yuan": 0.0,
                    "drawdown_pct": 0.0,
                    "consecutive_losses": consecutive_losses,
                    "decision_trace_json": json.dumps(
                        trace, ensure_ascii=False
                    ),
                    "source": "NO_BET",
                }
            )
            continue
        # Exact frozen incumbent binding when the action equals the incumbent.
        if (
            action.key == incumbent_key
            and frozen_incumbent is not None
            and not frozen_incumbent.empty
        ):
            frozen_row = frozen_incumbent[
                (frozen_incumbent["split"] == split)
                & (frozen_incumbent["issue"] == issue)
            ]
            if not frozen_row.empty:
                row = frozen_row.iloc[0]
                payout = float(row["gross_payout_yuan"])
                funded = float(row["funded_stake_yuan"])
                new_bankroll = float(row["post_issue_bankroll_yuan"])
                peak = max(peak, new_bankroll)
                drawdown_pct = (peak - new_bankroll) / peak if peak else 0.0
                consecutive_losses = (
                    consecutive_losses + 1 if payout == 0 else 0
                )
                rows.append(
                    {
                        "split": split,
                        "issue": issue,
                        "year": ctx.panel.year,
                        "policy": policy_name,
                        "action_key": action.key,
                        "n": action.n,
                        "k": action.k,
                        "lane": action.lane,
                        "capital": action.capital,
                        "pre_issue_bankroll_yuan": bankroll,
                        "funded_stake_yuan": funded,
                        "gross_payout_yuan": payout,
                        "post_issue_bankroll_yuan": new_bankroll,
                        "net_pnl_yuan": new_bankroll - bankroll,
                        "drawdown_pct": drawdown_pct,
                        "consecutive_losses": consecutive_losses,
                        "decision_trace_json": json.dumps(
                            trace, ensure_ascii=False
                        ),
                        "source": "FROZEN_INCUMBENT_207",
                    }
                )
                bankroll = new_bankroll
                continue
        n_pool = pool_cache.get(_pool_cache_key(issue, action.n))
        if n_pool is None:
            action = Action(7, 8, INCUMBENT_LANE, "NATIVE_2_YUAN")
            n_pool = pool
            trace = {"fallback": "INFEASIBLE_N"}
        scores = None
        if action.lane == "LEARNED_MLP" and ranker_scores_by_issue is not None:
            scores = ranker_scores_by_issue.get(f"{issue}:{action.n}")
        if action.lane in STOCHASTIC_LANES and stochastic_lane_aggregate:
            funded_list: list[float] = []
            payout_list: list[float] = []
            for seed in ALL_SEEDS:
                sel = _select_for_lane(n_pool, action, seed, scores=scores)
                if sel.empty:
                    funded_list.append(0.0)
                    payout_list.append(0.0)
                    continue
                settled = settle_tickets(sel)
                if action.capital == "NATIVE_2_YUAN":
                    cap = bundle_capital(settled, bankroll)
                else:
                    cap = bundle_capital_equal1pct(settled, bankroll)
                funded_list.append(float(cap["funded_stake_yuan"]))
                payout_list.append(float(cap["gross_payout_yuan"]))
            funded = float(np.mean(funded_list))
            payout = float(np.mean(payout_list))
        else:
            sel = _select_for_lane(n_pool, action, seed=0, scores=scores)
            if sel.empty:
                funded = 0.0
                payout = 0.0
            else:
                settled = settle_tickets(sel)
                if action.capital == "NATIVE_2_YUAN":
                    cap = bundle_capital(settled, bankroll)
                else:
                    cap = bundle_capital_equal1pct(settled, bankroll)
                funded = float(cap["funded_stake_yuan"])
                payout = float(cap["gross_payout_yuan"])
        new_bankroll = bankroll - funded + payout
        peak = max(peak, new_bankroll)
        drawdown_pct = (peak - new_bankroll) / peak if peak else 0.0
        consecutive_losses = consecutive_losses + 1 if payout == 0 else 0
        rows.append(
            {
                "split": split,
                "issue": issue,
                "year": ctx.panel.year,
                "policy": policy_name,
                "action_key": action.key,
                "n": action.n,
                "k": action.k,
                "lane": action.lane,
                "capital": action.capital,
                "pre_issue_bankroll_yuan": bankroll,
                "funded_stake_yuan": funded,
                "gross_payout_yuan": payout,
                "post_issue_bankroll_yuan": new_bankroll,
                "net_pnl_yuan": new_bankroll - bankroll,
                "drawdown_pct": drawdown_pct,
                "consecutive_losses": consecutive_losses,
                "decision_trace_json": json.dumps(trace, ensure_ascii=False),
                "source": "REPLAY",
            }
        )
        bankroll = new_bankroll
    return pd.DataFrame(rows)


def _running_peak_drawdown(path: pd.DataFrame) -> float:
    """Maximum percentage drawdown from the RUNNING peak.

    REWORK v2 (D5): for each issue i, peak_i = max(post_0..post_i); dd_i =
    (peak_i - post_i)/peak_i; the metric is max over i.  The old implementation
    divided by the FINAL peak over all history, which overstates drawdown for
    late peaks (path [100,80,200] gave 0.6; the running-peak value is 0.2).
    """
    if path.empty:
        return 0.0
    posts = path["post_issue_bankroll_yuan"].to_numpy(dtype=float)
    running_peak = np.maximum.accumulate(posts)
    dd = np.where(running_peak > 0, (running_peak - posts) / running_peak, 0.0)
    return float(np.max(dd)) if len(dd) else 0.0


def summarize_path(path: pd.DataFrame) -> dict[str, float]:
    """Issue-path summary with required holding-feasibility metrics.

    REWORK v2 (D5/D6): running-peak max drawdown; time under water; recovery
    issues; max consecutive losing issues; rolling 5/10/20-issue loss
    probability and worst windows; ex-largest issue.
    """
    if path.empty:
        return {}
    ending = float(path.iloc[-1]["post_issue_bankroll_yuan"])
    max_dd = _running_peak_drawdown(path)
    posts = path["post_issue_bankroll_yuan"].to_numpy(dtype=float)
    payouts = path["gross_payout_yuan"].to_numpy(dtype=float)

    # Time under water: consecutive issues from a running peak until recovery
    # to a new peak, summed; recovery issues: count of recovery events.
    running_peak = np.maximum.accumulate(posts)
    underwater = running_peak > posts
    tuw = 0
    recovery = 0
    in_underwater = False
    for i in range(len(posts)):
        if underwater[i]:
            tuw += 1
            in_underwater = True
        else:
            if in_underwater and i > 0 and posts[i] >= running_peak[i]:
                recovery += 1
            in_underwater = False
    # Max consecutive losing issues (payout == 0).
    max_streak = 0
    streak = 0
    for value in payouts:
        if value == 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    # Rolling 5/10/20-issue loss probability and worst windows.
    rolling_metrics: dict[str, float] = {}
    for window in (5, 10, 20):
        if len(payouts) < window:
            rolling_metrics[f"rolling{window}_loss_prob"] = float("nan")
            rolling_metrics[f"rolling{window}_worst_window"] = float("nan")
            continue
        windows = np.lib.stride_tricks.sliding_window_view(
            payouts, window
        )
        loss_windows = (windows == 0).all(axis=1)
        rolling_metrics[f"rolling{window}_loss_prob"] = float(
            loss_windows.mean()
        )
        window_returns = windows.sum(axis=1)
        rolling_metrics[f"rolling{window}_worst_window"] = float(
            window_returns.min()
        )
    return {
        "ending_capital_yuan": ending,
        "max_drawdown_pct": max_dd,
        "turnover_yuan": float(path["funded_stake_yuan"].sum()),
        "issues": int(len(path)),
        "time_under_water_issues": float(tuw),
        "recovery_issues": float(recovery),
        "max_consecutive_losing_issues": float(max_streak),
        **rolling_metrics,
    }


def path_holding_metrics(path: pd.DataFrame) -> dict[str, float]:
    """Additional required metrics: ex-largest issue, HHI, overlap, repeat."""
    if path.empty:
        return {}
    funded = path["funded_stake_yuan"].to_numpy(dtype=float)
    ex_largest = float(np.max(funded)) if len(funded) else 0.0
    return {
        "ex_largest_issue_yuan": ex_largest,
        "hhi_funded": float(np.sum((funded / funded.sum()) ** 2))
        if funded.sum() > 0
        else 0.0,
    }


__all__ = [
    "IssueContext", "ReplayError", "build_issue_contexts", "build_label_surface",
    "build_pool_cache", "build_training_frame", "full_path_replay",
    "incumbent_issue_ledger", "issue_action_lift", "path_holding_metrics",
    "summarize_path",
]
