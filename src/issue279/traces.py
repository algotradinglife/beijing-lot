"""Pre-outcome 2023 decision traces for Issue #279 diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from issue209.contract import SEEDS
from issue209.dynamic_policy import ActionSpec, generate_tickets

OUTCOMES = ("3", "1", "0")
PAYOUT_COEFFICIENT = 0.65
TICKET_STAKE = 2.0
TRACE_FORBIDDEN = {
    "Y",
    "realized_outcome",
    "SP_SETTLE",
    "settlement_sp",
    "winning_sp",
    "R_RAW",
    "payout",
    "mean_pnl",
    "utility_bps",
}


def _derived_seed(seed: int, issue: str, action_key: str) -> int:
    payload = f"{seed}:{issue}:{action_key}".encode("utf-8")
    value = 2166136261
    for byte in payload:
        value = (value ^ byte) * 16777619 & 0xFFFFFFFF
    return int(value)


def _assert_pre_outcome(frame: pd.DataFrame, name: str) -> None:
    forbidden = TRACE_FORBIDDEN.intersection(frame.columns)
    if forbidden:
        raise ValueError(f"{name} contains settlement fields: {sorted(forbidden)}")


def build_topb_action_trace(
    predictions: pd.DataFrame,
    chosen: pd.DataFrame,
    *,
    top_b: int = 5,
) -> pd.DataFrame:
    """Persist the highest scored action alternatives available before outcome."""

    if top_b <= 0:
        raise ValueError("top_b must be positive")
    calibration = predictions[predictions["temporal_role"].eq("calibration")].copy()
    calibration = calibration.sort_values(
        ["issue", "predicted_risk_score", "action_key"],
        ascending=[True, False, True],
    )
    calibration["predicted_rank"] = calibration.groupby("issue").cumcount() + 1
    chosen_keys = chosen[["issue", "action_key"]].copy()
    chosen_keys["issue"] = chosen_keys["issue"].astype(str)
    calibration["issue"] = calibration["issue"].astype(str)
    chosen_index = pd.MultiIndex.from_frame(chosen_keys)
    calibration_index = pd.MultiIndex.from_frame(calibration[["issue", "action_key"]])
    trace = calibration[
        calibration["predicted_rank"].le(top_b) | calibration_index.isin(chosen_index)
    ].copy()
    selected = chosen[["issue", "action_key"]].assign(chosen_action=True)
    trace = trace.merge(selected, on=["issue", "action_key"], how="left")
    trace["chosen_action"] = trace["chosen_action"].fillna(False).astype(bool)
    _assert_pre_outcome(trace, "top-B action trace")
    return trace.reset_index(drop=True)


def build_cell_trace(
    units: pd.DataFrame,
    probabilities: pd.DataFrame,
    values: pd.DataFrame,
    *,
    issues: set[str],
    horizon: str = "10h",
) -> pd.DataFrame:
    """Long M×3 cell trace containing inference-time probability/value fields."""

    mask = units["snapshot_kind"].eq(horizon) & units["issue"].astype(str).isin(issues)
    safe_units = units.loc[
        mask,
        [
            "issue",
            "match_idx",
            "issue_year",
            "snapshot_kind",
            "native_handicap_line",
            "n_available_books",
            "mapping_accepted",
            *[f"eu_vs_line_divergence_{c}" for c in OUTCOMES],
        ],
    ].copy()
    prob = probabilities.reindex(safe_units.index)
    value = values.reindex(safe_units.index)
    rows: list[pd.DataFrame] = []
    for outcome in OUTCOMES:
        cell = safe_units[
            [
                "issue",
                "match_idx",
                "issue_year",
                "snapshot_kind",
                "native_handicap_line",
                "n_available_books",
                "mapping_accepted",
            ]
        ].copy()
        cell["outcome_code"] = outcome
        cell["probability"] = prob[outcome].to_numpy(dtype=float)
        cell["cell_value"] = value[f"ev_raw_{outcome}"].to_numpy(dtype=float)
        cell["value_q10"] = value[f"value_q10_{outcome}"].to_numpy(dtype=float)
        cell["value_q90"] = value[f"value_q90_{outcome}"].to_numpy(dtype=float)
        cell["divergence"] = safe_units[
            f"eu_vs_line_divergence_{outcome}"
        ].to_numpy(dtype=float)
        cell["predicted_sp_proxy"] = np.divide(
            cell["cell_value"],
            cell["probability"],
            out=np.full(len(cell), np.nan),
            where=cell["probability"].to_numpy() > 0,
        )
        rows.append(cell)
    trace = pd.concat(rows, ignore_index=True)
    trace["cell_value_rank"] = trace.groupby("issue")["cell_value"].rank(
        method="first", ascending=False
    )
    trace["match_best_value"] = trace.groupby(["issue", "match_idx"])[
        "cell_value"
    ].transform("max")
    trace["match_value_rank"] = trace.groupby("issue")["match_best_value"].rank(
        method="dense", ascending=False
    )
    _assert_pre_outcome(trace, "cell trace")
    return trace.sort_values(
        ["issue", "match_value_rank", "match_idx", "cell_value_rank"]
    ).reset_index(drop=True)


@dataclass(frozen=True)
class TicketTraceBundle:
    tickets: pd.DataFrame
    legs: pd.DataFrame
    issue_summary: pd.DataFrame


def build_ticket_traces(
    units: pd.DataFrame,
    probabilities: pd.DataFrame,
    values: pd.DataFrame,
    chosen: pd.DataFrame,
    *,
    fixed_action: ActionSpec = ActionSpec(7, 8, "TOP_VALUE"),
    horizon: str = "10h",
    seeds: tuple[int, ...] = SEEDS,
) -> TicketTraceBundle:
    """Materialize chosen and fixed-control tickets without settlement fields."""

    selected = chosen.copy()
    selected["issue"] = selected["issue"].astype(str)
    chosen_by_issue = selected.set_index("issue")
    unit_h = units[
        units["snapshot_kind"].eq(horizon)
        & units["issue"].astype(str).isin(set(chosen_by_issue.index))
    ]
    ticket_rows: list[dict[str, object]] = []
    leg_rows: list[dict[str, object]] = []
    for issue, group in unit_h.groupby("issue", sort=True):
        issue_text = str(issue)
        index = group.index
        match_ids = group["match_idx"].to_numpy(dtype=int)
        ev = values.reindex(index)[[f"ev_raw_{c}" for c in OUTCOMES]].to_numpy(
            dtype=float
        )
        probs = probabilities.reindex(index)[list(OUTCOMES)].to_numpy(dtype=float)
        row = chosen_by_issue.loc[issue_text]
        chosen_action = ActionSpec(int(row["n"]), int(row["k"]), str(row["generator"]))
        for arm, action in (("chosen", chosen_action), ("fixed", fixed_action)):
            if action.generator == "NO_BET":
                continue
            if action.n > len(group):
                continue
            for base_seed in seeds:
                derived_seed = _derived_seed(base_seed, issue_text, action.key)
                ticket_matches, ticket_outcomes = generate_tickets(
                    ev, probs, action, seed=derived_seed
                )
                for ticket_index, (match_pos, outcome_pos) in enumerate(
                    zip(ticket_matches, ticket_outcomes)
                ):
                    cell_prob = probs[match_pos, outcome_pos]
                    cell_value = ev[match_pos, outcome_pos]
                    cell_sp = np.divide(
                        cell_value,
                        cell_prob,
                        out=np.full(len(match_pos), np.nan),
                        where=cell_prob > 0,
                    )
                    ticket_probability = float(np.prod(cell_prob))
                    ticket_sp = float(np.prod(cell_sp))
                    expected_net = TICKET_STAKE * (
                        PAYOUT_COEFFICIENT * ticket_probability * ticket_sp - 1.0
                    )
                    identities = [
                        f"{int(match_ids[m])}:{OUTCOMES[int(o)]}"
                        for m, o in zip(match_pos, outcome_pos)
                    ]
                    ticket_rows.append(
                        {
                            "issue": issue_text,
                            "issue_year": int(group["issue_year"].iloc[0]),
                            "arm": arm,
                            "action_key": action.key,
                            "n": action.n,
                            "k_requested": action.k,
                            "generator": action.generator,
                            "base_seed": int(base_seed),
                            "derived_seed": int(derived_seed),
                            "ticket_index": int(ticket_index),
                            "ticket_identity": "|".join(identities),
                            "predicted_win_probability": ticket_probability,
                            "predicted_sp_product": ticket_sp,
                            "predicted_expected_net_cny2": expected_net,
                        }
                    )
                    for position, (m, o) in enumerate(zip(match_pos, outcome_pos)):
                        leg_rows.append(
                            {
                                "issue": issue_text,
                                "issue_year": int(group["issue_year"].iloc[0]),
                                "arm": arm,
                                "action_key": action.key,
                                "base_seed": int(base_seed),
                                "derived_seed": int(derived_seed),
                                "ticket_index": int(ticket_index),
                                "leg_position": int(position),
                                "match_idx": int(match_ids[m]),
                                "outcome_code": OUTCOMES[int(o)],
                                "probability": float(probs[m, o]),
                                "cell_value": float(ev[m, o]),
                                "predicted_sp_proxy": float(cell_sp[position]),
                            }
                        )
    tickets = pd.DataFrame(ticket_rows)
    legs = pd.DataFrame(leg_rows)
    _assert_pre_outcome(tickets, "ticket trace")
    _assert_pre_outcome(legs, "leg trace")
    summary = _summarize_structural_difference(tickets, legs)
    return TicketTraceBundle(tickets=tickets, legs=legs, issue_summary=summary)


def _summarize_structural_difference(
    tickets: pd.DataFrame, legs: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for issue, issue_legs in legs.groupby("issue", sort=True):
        issue_tickets = tickets[tickets["issue"].eq(issue)]
        by_arm = {arm: group for arm, group in issue_legs.groupby("arm")}
        ticket_by_arm = {arm: group for arm, group in issue_tickets.groupby("arm")}
        if not {"chosen", "fixed"}.issubset(by_arm):
            continue
        chosen = by_arm["chosen"]
        fixed = by_arm["fixed"]
        chosen_matches = set(chosen["match_idx"])
        fixed_matches = set(fixed["match_idx"])
        match_union = chosen_matches | fixed_matches
        match_jaccard = len(chosen_matches & fixed_matches) / max(len(match_union), 1)
        chosen_legs = set(zip(chosen["match_idx"], chosen["outcome_code"]))
        fixed_legs = set(zip(fixed["match_idx"], fixed["outcome_code"]))
        leg_union = chosen_legs | fixed_legs
        leg_jaccard = len(chosen_legs & fixed_legs) / max(len(leg_union), 1)
        chosen_tickets = set(ticket_by_arm["chosen"]["ticket_identity"])
        fixed_tickets = set(ticket_by_arm["fixed"]["ticket_identity"])
        ticket_union = chosen_tickets | fixed_tickets
        ticket_jaccard = len(chosen_tickets & fixed_tickets) / max(
            len(ticket_union), 1
        )
        shared = chosen_matches & fixed_matches
        disagreement = []
        for match in shared:
            chosen_mode = chosen.loc[chosen["match_idx"].eq(match), "outcome_code"].mode()
            fixed_mode = fixed.loc[fixed["match_idx"].eq(match), "outcome_code"].mode()
            if len(chosen_mode) and len(fixed_mode):
                disagreement.append(chosen_mode.iloc[0] != fixed_mode.iloc[0])
        rows.append(
            {
                "issue": str(issue),
                "chosen_unique_matches": len(chosen_matches),
                "fixed_unique_matches": len(fixed_matches),
                "match_set_jaccard": float(match_jaccard),
                "leg_identity_jaccard": float(leg_jaccard),
                "ticket_identity_jaccard": float(ticket_jaccard),
                "shared_match_modal_outcome_disagreement": (
                    float(np.mean(disagreement)) if disagreement else np.nan
                ),
                "selection_structure_changed": bool(match_jaccard < 1.0),
                "outcome_structure_changed": bool(leg_jaccard < 1.0),
            }
        )
    return pd.DataFrame(rows).sort_values("issue").reset_index(drop=True)
