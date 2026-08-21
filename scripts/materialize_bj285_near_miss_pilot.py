#!/usr/bin/env python3
"""Materialize the thin N9/K64 near-miss and single-flip protection pilot."""

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
from issue284.labels import (  # noqa: E402
    build_subset_ticket_stream,
    derived_subset_seed,
)
from issue285.protection import (  # noqa: E402
    PROTECTION_RULES,
    chosen_protected_legs,
    derived_ticket_seed,
    protect_ticket_portfolio,
    ranked_alternative_outcomes,
    settle_unique_ticket_portfolio,
    ticket_miss_distance,
)

OUTCOMES = ("3", "1", "0")
OUTCOME_TO_POSITION = {outcome: position for position, outcome in enumerate(OUTCOMES)}


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
    parser.add_argument("--n", type=int, default=9)
    parser.add_argument("--k", type=int, default=64)
    parser.add_argument("--proposal-family", default="DIVERGENCE_WEIGHTED")
    parser.add_argument("--subsets-per-issue", type=int, default=1)
    parser.add_argument("--stream-seeds", type=int, nargs="+", default=[284_501])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    profile = pd.read_parquet(ROOT / "results/issue-284/subset_profile.parquet")
    selected = (
        profile.loc[
            profile["n"].eq(args.n)
            & profile["proposal_family"].eq(args.proposal_family)
        ]
        .sort_values(["issue", "subset_id"])
        .groupby("issue", as_index=False)
        .head(args.subsets_per_issue)
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
        raise RuntimeError("2024+ near-miss seal violated")
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
    ticket_rows: list[dict[str, object]] = []
    protection_rows: list[dict[str, object]] = []
    attribution_rows: list[dict[str, object]] = []
    exclusion_rows: list[dict[str, object]] = []
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
            proposal = divergence_value_surface(
                local_value, local_probability, local_divergence
            )
            local_realized = realized[local]
            local_sp = winning_sp[local]
            if not np.isfinite(local_sp).all():
                missing_legs = np.flatnonzero(~np.isfinite(local_sp))
                exclusion_rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(group["issue_year"].iloc[0]),
                        "subset_id": str(subset.subset_id),
                        "reason": "NONFINITE_WINNING_SP",
                        "missing_match_ids": json.dumps(
                            [str(subset.match_ids[leg]) for leg in missing_legs]
                        ),
                    }
                )
                continue
            entropy = -np.sum(
                np.where(
                    local_probability > 0,
                    local_probability * np.log(local_probability),
                    0.0,
                ),
                axis=1,
            )
            for stream_seed in args.stream_seeds:
                stream = build_subset_ticket_stream(
                    proposal,
                    local_probability,
                    generator="WEIGHTED_WR",
                    requested_unique=2 * args.k,
                    seed=derived_subset_seed(stream_seed, str(subset.subset_id)),
                )
                tickets = stream.outcome_positions[: args.k].astype(int)
                distances = ticket_miss_distance(tickets, local_realized)
                base = settle_unique_ticket_portfolio(
                    tickets,
                    realized_outcomes=local_realized,
                    winning_sp=local_sp,
                )
                for ticket_index, (ticket, distance) in enumerate(
                    zip(tickets, distances, strict=True)
                ):
                    missed = np.flatnonzero(ticket != local_realized)
                    unique_leg = int(missed[0]) if len(missed) == 1 else -1
                    if unique_leg >= 0:
                        selected_outcome = int(ticket[unique_leg])
                        alternatives = ranked_alternative_outcomes(
                            proposal[unique_leg], selected=selected_outcome
                        )
                        best_other = float(
                            np.max(np.delete(proposal[unique_leg], selected_outcome))
                        )
                        row_detail = {
                            "unique_missed_leg": unique_leg,
                            "unique_missed_match_id": str(subset.match_ids[unique_leg]),
                            "selected_outcome": OUTCOMES[selected_outcome],
                            "realized_outcome": OUTCOMES[local_realized[unique_leg]],
                            "selected_probability": local_probability[
                                unique_leg, selected_outcome
                            ],
                            "selected_divergence": local_divergence[
                                unique_leg, selected_outcome
                            ],
                            "match_entropy": entropy[unique_leg],
                            "model_margin": proposal[unique_leg, selected_outcome]
                            - best_other,
                            "alternative_1": OUTCOMES[alternatives[0]],
                            "alternative_2": OUTCOMES[alternatives[1]],
                            "alternative_1_rescues": alternatives[0]
                            == local_realized[unique_leg],
                            "alternative_2_rescues": alternatives[1]
                            == local_realized[unique_leg],
                        }
                    else:
                        row_detail = {
                            "unique_missed_leg": -1,
                            "unique_missed_match_id": "",
                            "selected_outcome": "",
                            "realized_outcome": "",
                            "selected_probability": np.nan,
                            "selected_divergence": np.nan,
                            "match_entropy": np.nan,
                            "model_margin": np.nan,
                            "alternative_1": "",
                            "alternative_2": "",
                            "alternative_1_rescues": False,
                            "alternative_2_rescues": False,
                        }
                    ticket_rows.append(
                        {
                            "issue": str(issue),
                            "issue_year": int(group["issue_year"].iloc[0]),
                            "subset_id": str(subset.subset_id),
                            "stream_seed": stream_seed,
                            "ticket_index": ticket_index,
                            "ticket_identity": "".join(OUTCOMES[value] for value in ticket),
                            "n": args.n,
                            "k": args.k,
                            "miss_distance": int(distance),
                            "miss_bucket": str(distance) if distance < 3 else "3+",
                            **row_detail,
                        }
                    )
                for rule in PROTECTION_RULES:
                    for ticket_index in np.flatnonzero(distances == 1):
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
                        alternative = ranked_alternative_outcomes(
                            proposal[protected_leg],
                            selected=int(ticket[protected_leg]),
                        )[0]
                        attribution_rows.append(
                            {
                                "issue": str(issue),
                                "issue_year": int(group["issue_year"].iloc[0]),
                                "subset_id": str(subset.subset_id),
                                "stream_seed": stream_seed,
                                "ticket_index": int(ticket_index),
                                "rule": rule,
                                "unique_missed_leg": missed_leg,
                                "protected_leg": protected_leg,
                                "protects_unique_missed_leg": protected_leg
                                == missed_leg,
                                "alternative_outcome": OUTCOMES[alternative],
                                "alternative_rescues": protected_leg == missed_leg
                                and alternative == local_realized[missed_leg],
                            }
                        )
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
                    continuation_tickets = stream.outcome_positions[
                        : int(protected["unique_tickets"])
                    ].astype(int)
                    continuation = settle_unique_ticket_portfolio(
                        continuation_tickets,
                        realized_outcomes=local_realized,
                        winning_sp=local_sp,
                    )
                    protection_rows.append(
                        {
                            "issue": str(issue),
                            "issue_year": int(group["issue_year"].iloc[0]),
                            "subset_id": str(subset.subset_id),
                            "stream_seed": stream_seed,
                            "n": args.n,
                            "k": args.k,
                            "rule": rule,
                            "protected_legs": 1,
                            "alternative_depth": 1,
                            "structure": "SINGLE_FLIP",
                            "base_unique_tickets": base["unique_tickets"],
                            "protected_unique_tickets": protected["unique_tickets"],
                            "extra_unique_tickets": protected["unique_tickets"]
                            - base["unique_tickets"],
                            "base_hit_count": base["hit_count"],
                            "protected_hit_count": protected["hit_count"],
                            "portfolio_rescued": base["hit_count"] == 0
                            and protected["hit_count"] > 0,
                            "base_stake_cny": base["stake_cny"],
                            "protected_stake_cny": protected["stake_cny"],
                            "extra_stake_cny": protected["stake_cny"]
                            - base["stake_cny"],
                            "base_gross_cny": base["gross_cny"],
                            "protected_gross_cny": protected["gross_cny"],
                            "rescued_gross_cny": protected["gross_cny"]
                            - base["gross_cny"],
                            "base_pnl_cny": base["pnl_cny"],
                            "protected_pnl_cny": protected["pnl_cny"],
                            "protection_lift_cny": protected["pnl_cny"]
                            - base["pnl_cny"],
                            "continuation_unique_tickets": continuation[
                                "unique_tickets"
                            ],
                            "continuation_stake_cny": continuation["stake_cny"],
                            "continuation_gross_cny": continuation["gross_cny"],
                            "continuation_pnl_cny": continuation["pnl_cny"],
                            "continuation_lift_cny": continuation["pnl_cny"]
                            - base["pnl_cny"],
                            "protection_minus_continuation_cny": protected["pnl_cny"]
                            - continuation["pnl_cny"],
                            "near_miss_tickets": int((distances == 1).sum()),
                        }
                    )
        if issue_number % 100 == 0:
            print(f"processed issues={issue_number}", flush=True)
    tickets = pd.DataFrame(ticket_rows)
    protections = pd.DataFrame(protection_rows)
    attributions = pd.DataFrame(attribution_rows)
    exclusions = pd.DataFrame(exclusion_rows)
    receipt = {
        "contract": "BJ-UNIFIED-NEAR-MISS-PROTECTION-001/v1-thin-pilot",
        "issues": int(protections["issue"].nunique()),
        "ticket_rows": int(len(tickets)),
        "protection_rows": int(len(protections)),
        "near_miss_attribution_rows": int(len(attributions)),
        "excluded_subsets": int(len(exclusions)),
        "excluded_issues": int(exclusions["issue"].nunique()) if len(exclusions) else 0,
        "exclusion_rule": "SUBSET_EXCLUDED_IF_ANY_REALIZED_WINNING_SP_IS_NONFINITE",
        "n": args.n,
        "k": args.k,
        "proposal_family": args.proposal_family,
        "outcome_mode": "DIVERGENCE_VALUE",
        "generator": "WEIGHTED_WR",
        "subsets_per_issue": args.subsets_per_issue,
        "stream_seeds": args.stream_seeds,
        "rules": list(PROTECTION_RULES),
        "protected_legs": 1,
        "alternative_depth": 1,
        "structure": "SINGLE_FLIP",
        "payout_coefficient": 0.65,
        "payout_application": "ONCE_PER_WINNING_COMPLETE_N_FOLD_TICKET",
        "sealed_years_opened": [],
    }
    _atomic_parquet(tickets, output / "near_miss_ticket_ledger.parquet")
    _atomic_parquet(protections, output / "protection_pilot_ledger.parquet")
    _atomic_parquet(
        attributions, output / "near_miss_protection_attribution.parquet"
    )
    _atomic_parquet(exclusions, output / "protection_pilot_exclusions.parquet")
    _atomic_json(receipt, output / "near_miss_pilot_receipt.json")
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
