#!/usr/bin/env python3
"""Materialize the bounded #285 protection confirmation panel."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue282.labels import divergence_value_surface  # noqa: E402
from issue284.labels import build_subset_ticket_stream, derived_subset_seed  # noqa: E402
from issue285.protection import (  # noqa: E402
    chosen_protected_legs,
    derived_ticket_seed,
    protect_ticket_portfolio,
    ranked_alternative_outcomes,
    settle_unique_ticket_portfolio,
    ticket_miss_distance,
)

OUTCOMES = ("3", "1", "0")
OUTCOME_TO_POSITION = {outcome: position for position, outcome in enumerate(OUTCOMES)}
RULES = ("ADVERSE_SIGNED_DIVERGENCE", "RANDOM_BUDGET_CONTROL")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", ROOT)),
    )
    parser.add_argument(
        "--issue209-results", type=Path, default=ROOT / "results/issue-209"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-285")
    parser.add_argument("--n-values", type=int, nargs="+", default=[7, 8, 9, 10])
    parser.add_argument("--k-values", type=int, nargs="+", default=[16, 64, 128])
    parser.add_argument(
        "--proposal-families",
        nargs="+",
        default=["DIVERGENCE_WEIGHTED", "UNIFORM"],
    )
    parser.add_argument("--subsets-per-action", type=int, default=1)
    parser.add_argument(
        "--stream-seeds", type=int, nargs="+", default=[285_101, 285_102, 285_103]
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    profile = pd.read_parquet(ROOT / "results/issue-284/subset_profile.parquet")
    selected = (
        profile.loc[
            profile["n"].isin(args.n_values)
            & profile["proposal_family"].isin(args.proposal_families)
        ]
        .sort_values(["issue", "n", "proposal_family", "subset_id"])
        .groupby(["issue", "n", "proposal_family"], as_index=False)
        .head(args.subsets_per_action)
        .copy()
    )
    selected["match_ids"] = selected["match_ids"].map(json.loads)
    probabilities = pd.read_parquet(
        args.issue209_results.resolve() / "market_only_probabilities.parquet"
    )
    values = pd.read_parquet(
        args.issue209_results.resolve() / "cell_value_distribution.parquet"
    )
    tensor = build_tensor()
    units = build_match_units(tensor)
    if tensor["issue_year"].ge(2024).any() or units["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ confirmation seal violated")
    if not units.index.equals(probabilities.index) or not units.index.equals(values.index):
        raise RuntimeError("#209 probability/value indexes are not aligned")
    winners = (
        tensor.loc[tensor["Y"].eq(1), ["issue", "match_idx", "SP_SETTLE"]]
        .drop_duplicates(["issue", "match_idx"])
        .assign(issue=lambda frame: frame["issue"].astype(str))
    )
    winner_sp = {
        str(issue): group.set_index(group["match_idx"].astype(str))["SP_SETTLE"].to_dict()
        for issue, group in winners.groupby("issue", sort=False)
    }
    units = units.loc[units["snapshot_kind"].eq("10h")].copy()
    units["issue"] = units["issue"].astype(str)
    selected_by_issue = {
        str(issue): group for issue, group in selected.groupby("issue", sort=False)
    }
    rows: list[dict[str, object]] = []
    exclusions: list[dict[str, object]] = []
    max_k = max(args.k_values)
    for issue_number, (issue, group) in enumerate(units.groupby("issue", sort=True), 1):
        subsets = selected_by_issue.get(str(issue))
        if subsets is None:
            continue
        indexes = group.index
        match_ids = group["match_idx"].astype(str).tolist()
        position = {match_id: offset for offset, match_id in enumerate(match_ids)}
        probability = probabilities.reindex(indexes)[list(OUTCOMES)].to_numpy(float)
        cell_value = values.reindex(indexes)[
            [f"ev_raw_{outcome}" for outcome in OUTCOMES]
        ].to_numpy(float)
        divergence = group[
            [f"eu_vs_line_divergence_{outcome}" for outcome in OUTCOMES]
        ].to_numpy(float)
        realized = np.array(
            [OUTCOME_TO_POSITION[str(outcome)] for outcome in group["realized_outcome"]],
            dtype=int,
        )
        sp_lookup = winner_sp.get(str(issue), {})
        winning_sp = np.array(
            [float(sp_lookup.get(match_id, np.nan)) for match_id in match_ids]
        )
        for subset in subsets.itertuples(index=False):
            local = np.array([position[str(match_id)] for match_id in subset.match_ids])
            local_probability = probability[local]
            local_value = cell_value[local]
            local_divergence = divergence[local]
            local_realized = realized[local]
            local_sp = winning_sp[local]
            if not np.isfinite(local_sp).all():
                exclusions.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(group["issue_year"].iloc[0]),
                        "n": int(subset.n),
                        "proposal_family": str(subset.proposal_family),
                        "subset_id": str(subset.subset_id),
                        "reason": "NONFINITE_WINNING_SP",
                    }
                )
                continue
            proposal = divergence_value_surface(
                local_value, local_probability, local_divergence
            )
            for stream_seed in args.stream_seeds:
                stream = build_subset_ticket_stream(
                    proposal,
                    local_probability,
                    generator="WEIGHTED_WR",
                    requested_unique=2 * max_k,
                    seed=derived_subset_seed(stream_seed, str(subset.subset_id)),
                )
                for k in args.k_values:
                    tickets = stream.outcome_positions[:k].astype(int)
                    distances = ticket_miss_distance(tickets, local_realized)
                    base = settle_unique_ticket_portfolio(
                        tickets,
                        realized_outcomes=local_realized,
                        winning_sp=local_sp,
                    )
                    near_miss_indexes = np.flatnonzero(distances == 1)
                    for rule in RULES:
                        protected_tickets = protect_ticket_portfolio(
                            tickets,
                            probability=local_probability,
                            divergence=local_divergence,
                            proposal_surface=proposal,
                            rule=rule,
                            protected_legs=1,
                            alternative_depth=1,
                            structure="SINGLE_FLIP",
                            seed=stream_seed,
                        )
                        protected = settle_unique_ticket_portfolio(
                            protected_tickets,
                            realized_outcomes=local_realized,
                            winning_sp=local_sp,
                        )
                        continuation = settle_unique_ticket_portfolio(
                            stream.outcome_positions[
                                : int(protected["unique_tickets"])
                            ].astype(int),
                            realized_outcomes=local_realized,
                            winning_sp=local_sp,
                        )
                        localized = 0
                        rescued = 0
                        for ticket_index in near_miss_indexes:
                            ticket = tickets[ticket_index]
                            missed_leg = int(
                                np.flatnonzero(ticket != local_realized)[0]
                            )
                            protected_leg = int(
                                chosen_protected_legs(
                                    ticket,
                                    probability=local_probability,
                                    divergence=local_divergence,
                                    proposal_surface=proposal,
                                    rule=rule,
                                    protected_legs=1,
                                    seed=derived_ticket_seed(
                                        stream_seed,
                                        int(ticket_index),
                                        tuple(int(value) for value in ticket),
                                    ),
                                )[0]
                            )
                            localized += protected_leg == missed_leg
                            if protected_leg == missed_leg:
                                alternative = ranked_alternative_outcomes(
                                    proposal[protected_leg],
                                    selected=int(ticket[protected_leg]),
                                )[0]
                                rescued += alternative == local_realized[missed_leg]
                        extra_stake = protected["stake_cny"] - base["stake_cny"]
                        rows.append(
                            {
                                "issue": str(issue),
                                "issue_year": int(group["issue_year"].iloc[0]),
                                "n": int(subset.n),
                                "k": int(k),
                                "proposal_family": str(subset.proposal_family),
                                "subset_id": str(subset.subset_id),
                                "stream_seed": int(stream_seed),
                                "rule": rule,
                                "base_stake_cny": base["stake_cny"],
                                "base_gross_cny": base["gross_cny"],
                                "base_pnl_cny": base["pnl_cny"],
                                "protected_stake_cny": protected["stake_cny"],
                                "protected_gross_cny": protected["gross_cny"],
                                "protected_pnl_cny": protected["pnl_cny"],
                                "extra_stake_cny": extra_stake,
                                "protection_lift_cny": protected["pnl_cny"]
                                - base["pnl_cny"],
                                "continuation_lift_cny": continuation["pnl_cny"]
                                - base["pnl_cny"],
                                "protection_minus_continuation_cny": protected[
                                    "pnl_cny"
                                ]
                                - continuation["pnl_cny"],
                                "near_miss_tickets": int(len(near_miss_indexes)),
                                "localized_near_miss_tickets": int(localized),
                                "rescued_near_miss_tickets": int(rescued),
                            }
                        )
        if issue_number % 50 == 0:
            print(f"processed issues={issue_number}", flush=True)
    panel = pd.DataFrame(rows)
    excluded = pd.DataFrame(exclusions)
    receipt = {
        "contract": "BJ-UNIFIED-NEAR-MISS-PROTECTION-001/v1-confirmation",
        "independent_unit": "ISSUE",
        "nested_units": ["subset_id", "stream_seed", "ticket"],
        "issues": int(panel["issue"].nunique()),
        "rows": int(len(panel)),
        "n_values": args.n_values,
        "k_values": args.k_values,
        "proposal_families": args.proposal_families,
        "stream_seeds": args.stream_seeds,
        "rules": list(RULES),
        "excluded_subsets": int(len(excluded)),
        "sealed_years_opened": [],
        "payout_coefficient": 0.65,
        "payout_application": "ONCE_PER_WINNING_COMPLETE_N_FOLD_TICKET",
    }
    _atomic_parquet(panel, output / "protection_confirmation_panel.parquet")
    _atomic_parquet(excluded, output / "protection_confirmation_exclusions.parquet")
    _atomic_json(receipt, output / "protection_confirmation_receipt.json")
    print(json.dumps(receipt, indent=2), flush=True)
    return 0


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
