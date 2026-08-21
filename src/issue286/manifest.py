"""Label-free ticket and single-flip candidate construction for Issue #286.

This module intentionally has no dependency on settlement loaders.  Its public
functions accept only pre-event probability/divergence surfaces and frozen
subset identities.  Outcomes and final SP are joined by ``issue286.settlement``
after the emitted manifest has been hashed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from issue282.labels import divergence_value_surface
from issue284.labels import build_subset_ticket_stream

OUTCOMES = ("3", "1", "0")
SELECTORS = ("UNIFORM", "DIVERGENCE_WEIGHTED")
OUTCOME_MODES = ("MARKET_PROBABILITY", "DIVERGENCE_VALUE")
GENERATORS = ("TOP_VALUE", "WEIGHTED_WR")


@dataclass(frozen=True)
class JointBaseAction:
    """One fixed pre-event base-ticket action before protection is chosen."""

    n: int
    k: int
    selector: str
    outcome_mode: str
    generator: str
    stream_seed: int

    def __post_init__(self) -> None:
        if self.n not in (7, 8, 9):
            raise ValueError("N must be one of 7, 8, 9")
        if self.k not in (16, 64):
            raise ValueError("K must be 16 or 64")
        if self.selector not in SELECTORS:
            raise ValueError(f"unsupported selector: {self.selector}")
        if self.outcome_mode not in OUTCOME_MODES:
            raise ValueError(f"unsupported outcome mode: {self.outcome_mode}")
        if self.generator not in GENERATORS:
            raise ValueError(f"unsupported generator: {self.generator}")

    @property
    def key(self) -> str:
        return (
            f"S{self.selector}_O{self.outcome_mode}_N{self.n}_"
            f"{self.generator}_K{self.k}"
        )


def prepare_horizon_surface(
    inference_view: pd.DataFrame, *, horizon: str = "10h"
) -> pd.DataFrame:
    """Pivot the #238 long pre-event view to one row per issue/match.

    The returned frame contains no outcome, hit, final-SP or settlement field.
    Duplicate cells are rejected instead of silently selecting a row.
    """

    required = {
        "issue_code",
        "match_idx",
        "snapshot_kind",
        "issue_year",
        "outcome_code",
        "q_eu_bjline",
        "q_line_only_control",
        "eu_vs_line_divergence",
        "mapping_accepted",
        "native_handicap_line",
        "n_available_books",
    }
    missing = sorted(required - set(inference_view.columns))
    if missing:
        raise ValueError(f"inference view missing columns: {missing}")
    forbidden = {
        "Y",
        "R_RAW",
        "SP_SETTLE",
        "winning_sp",
        "realized_outcome",
        "result_code",
    }
    present = sorted(forbidden & set(inference_view.columns))
    if present:
        raise ValueError(f"label-free input contains settlement columns: {present}")
    long = inference_view.loc[
        inference_view["snapshot_kind"].eq(horizon), list(required)
    ].copy()
    long["issue"] = long.pop("issue_code").astype(str)
    long["outcome_code"] = long["outcome_code"].astype(str)
    duplicate = long.duplicated(["issue", "match_idx", "outcome_code"], keep=False)
    if duplicate.any():
        raise ValueError("duplicate issue/match/outcome cells at frozen horizon")
    key = ["issue", "match_idx"]
    shared = long.groupby(key, as_index=False).agg(
        issue_year=("issue_year", "first"),
        mapping_accepted=("mapping_accepted", "min"),
        native_handicap_line=("native_handicap_line", "first"),
        n_available_books=("n_available_books", "first"),
    )
    wide = long.pivot(
        index=key,
        columns="outcome_code",
        values=["q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence"],
    )
    wide.columns = [f"{name}_{outcome}" for name, outcome in wide.columns]
    wide = wide.reset_index()
    surface = shared.merge(wide, on=key, how="inner", validate="one_to_one")
    needed = [
        f"{channel}_{outcome}"
        for channel in (
            "q_eu_bjline",
            "q_line_only_control",
            "eu_vs_line_divergence",
        )
        for outcome in OUTCOMES
    ]
    return surface.dropna(subset=needed).sort_values(key).reset_index(drop=True)


def build_action_manifest(
    issue_surface: pd.DataFrame,
    *,
    match_ids: list[str],
    subset_id: str,
    action: JointBaseAction,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build base, unique single-flip, and continuation identities.

    The stream is generated to ``2*K``.  The first K identities are the base;
    the next K form the exact same-stream unprotected continuation control.
    Every base ticket exposes both alternatives for every leg.  Candidate
    identities already present in the base are removed, and remaining flips
    are deduplicated across all parents before any funding decision.
    """

    if len(match_ids) != action.n:
        raise ValueError("frozen subset must contain exactly N match IDs")
    issues = issue_surface["issue"].astype(str).unique()
    if len(issues) != 1:
        raise ValueError("issue_surface must contain exactly one Beijing issue")
    full_probability = _market_probability(issue_surface)
    full_divergence = issue_surface[
        [f"eu_vs_line_divergence_{outcome}" for outcome in OUTCOMES]
    ].to_numpy(float)
    context = _issue_context(issue_surface, full_probability, full_divergence)
    local = issue_surface.copy()
    local["match_key"] = local["match_idx"].astype(str)
    local = local.set_index("match_key").reindex([str(value) for value in match_ids])
    if local.isna().all(axis=1).any():
        raise ValueError("frozen subset references a missing pre-event match")
    probability = _market_probability(local)
    divergence = local[
        [f"eu_vs_line_divergence_{outcome}" for outcome in OUTCOMES]
    ].to_numpy(float)
    proposal = (
        probability
        if action.outcome_mode == "MARKET_PROBABILITY"
        else divergence_value_surface(probability, probability, divergence)
    )
    requested = min(2 * action.k, 3**action.n)
    stream = build_subset_ticket_stream(
        proposal,
        probability,
        generator=action.generator,
        requested_unique=requested,
        seed=_derived_seed(action.stream_seed, str(local["issue"].iloc[0]), action.key),
    )
    outcomes = stream.outcome_positions
    if len(outcomes) < action.k:
        raise ValueError("ticket stream cannot supply the requested base K")
    base_outcomes = outcomes[: action.k]
    issue = str(local["issue"].iloc[0])
    year = int(local["issue_year"].iloc[0])
    base_identity = {
        _identity(match_ids, row) for row in base_outcomes
    }
    base_rows: list[dict[str, object]] = []
    for ticket_index, row in enumerate(base_outcomes):
        selected_probability = probability[np.arange(action.n), row]
        selected_divergence = divergence[np.arange(action.n), row]
        base_rows.append(
            {
                "issue": issue,
                "issue_year": year,
                "subset_id": subset_id,
                "action_key": action.key,
                "n": action.n,
                "k": action.k,
                "selector": action.selector,
                "outcome_mode": action.outcome_mode,
                "generator": action.generator,
                "stream_seed": int(action.stream_seed),
                "ticket_index": ticket_index,
                "ticket_identity": _identity(match_ids, row),
                "match_ids": _compact_json(match_ids),
                "outcome_positions": _compact_json(row.tolist()),
                "ticket_probability_product": float(np.prod(selected_probability)),
                "ticket_divergence_sum": float(np.sum(selected_divergence)),
                **context,
            }
        )
    candidate_by_identity: dict[str, dict[str, object]] = {}
    entropy = -np.sum(
        np.where(probability > 0, probability * np.log(probability), 0.0), axis=1
    )
    for ticket_index, row in enumerate(base_outcomes):
        selected_probability = probability[np.arange(action.n), row]
        selected_divergence = divergence[np.arange(action.n), row]
        for leg in range(action.n):
            alternatives = [value for value in range(3) if value != int(row[leg])]
            for alternative in alternatives:
                flipped = row.copy()
                flipped[leg] = alternative
                identity = _identity(match_ids, flipped)
                if identity in base_identity:
                    continue
                alt_probability = float(probability[leg, alternative])
                selected_proposal = float(proposal[leg, row[leg]])
                alt_proposal = float(proposal[leg, alternative])
                record = {
                    "issue": issue,
                    "issue_year": year,
                    "subset_id": subset_id,
                    "action_key": action.key,
                    "n": action.n,
                    "k": action.k,
                    "selector": action.selector,
                    "outcome_mode": action.outcome_mode,
                    "generator": action.generator,
                    "stream_seed": int(action.stream_seed),
                    "candidate_identity": identity,
                    "parent_ticket_index": ticket_index,
                    "protected_leg": leg,
                    "protected_match_id": str(match_ids[leg]),
                    "selected_outcome_position": int(row[leg]),
                    "alternative_outcome_position": int(alternative),
                    "selected_probability": float(selected_probability[leg]),
                    "alternative_probability": alt_probability,
                    "probability_delta": alt_probability
                    - float(selected_probability[leg]),
                    "selected_divergence": float(selected_divergence[leg]),
                    "alternative_divergence": float(divergence[leg, alternative]),
                    "divergence_delta": float(divergence[leg, alternative])
                    - float(selected_divergence[leg]),
                    "match_entropy": float(entropy[leg]),
                    "proposal_margin_delta": alt_proposal - selected_proposal,
                    "parent_ticket_probability_product": float(
                        np.prod(selected_probability)
                    ),
                    "candidate_probability_product": float(
                        np.prod(
                            np.where(
                                np.arange(action.n) == leg,
                                alt_probability,
                                selected_probability,
                            )
                        )
                    ),
                    **context,
                }
                prior = candidate_by_identity.get(identity)
                if prior is None or _candidate_priority(record) > _candidate_priority(prior):
                    candidate_by_identity[identity] = record
    continuation_rows = []
    for rank, row in enumerate(outcomes[action.k : 2 * action.k], start=1):
        identity = _identity(match_ids, row)
        if identity in base_identity:
            raise AssertionError("distinct continuation stream overlaps its base prefix")
        continuation_rows.append(
            {
                "issue": issue,
                "issue_year": year,
                "subset_id": subset_id,
                "action_key": action.key,
                "continuation_rank": rank,
                "ticket_identity": identity,
            }
        )
    base = pd.DataFrame(base_rows)
    candidates = pd.DataFrame(candidate_by_identity.values())
    if not candidates.empty:
        candidates = candidates.sort_values("candidate_identity").reset_index(drop=True)
        candidates["candidate_rank"] = np.arange(1, len(candidates) + 1)
        candidates["within_action_candidate_weight"] = 1.0 / len(candidates)
    continuation = pd.DataFrame(continuation_rows)
    return base, candidates, continuation


def frame_digest(frame: pd.DataFrame) -> str:
    """Stable digest of a manifest table independent of parquet metadata."""

    ordered = frame.sort_index(axis=1).sort_values(list(frame.columns), kind="stable")
    payload = ordered.to_json(orient="records", double_precision=15)
    return hashlib.sha256(payload.encode()).hexdigest()


def _market_probability(local: pd.DataFrame) -> np.ndarray:
    mapped = local["mapping_accepted"].astype(bool).to_numpy()
    eu = local[[f"q_eu_bjline_{outcome}" for outcome in OUTCOMES]].to_numpy(float)
    line = local[
        [f"q_line_only_control_{outcome}" for outcome in OUTCOMES]
    ].to_numpy(float)
    probability = np.where(mapped[:, None], eu, line)
    probability = np.clip(np.nan_to_num(probability, nan=0.0), 0.0, None)
    total = probability.sum(axis=1, keepdims=True)
    return np.divide(
        probability,
        total,
        out=np.full_like(probability, 1.0 / 3.0),
        where=total > 0,
    )


def _issue_context(
    local: pd.DataFrame, probability: np.ndarray, divergence: np.ndarray
) -> dict[str, float]:
    return {
        "issue_match_count": float(len(local)),
        "issue_probability_entropy_mean": float(
            np.mean(-np.sum(np.where(probability > 0, probability * np.log(probability), 0), axis=1))
        ),
        "issue_probability_max_mean": float(np.max(probability, axis=1).mean()),
        "issue_divergence_abs_mean": float(np.abs(divergence).mean()),
        "issue_divergence_abs_max": float(np.abs(divergence).max()),
        "issue_native_line_abs_mean": float(
            np.abs(local["native_handicap_line"].to_numpy(float)).mean()
        ),
        "issue_books_mean": float(local["n_available_books"].to_numpy(float).mean()),
    }


def _identity(match_ids: list[str], outcomes: np.ndarray) -> str:
    return "|".join(
        f"{match_id}:{OUTCOMES[int(outcome)]}"
        for match_id, outcome in zip(match_ids, outcomes, strict=True)
    )


def _compact_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


def _candidate_priority(record: dict[str, object]) -> tuple[float, float, int, int]:
    return (
        float(record["candidate_probability_product"]),
        float(record["proposal_margin_delta"]),
        -int(record["parent_ticket_index"]),
        -int(record["protected_leg"]),
    )


def _derived_seed(seed: int, issue: str, action_key: str) -> int:
    payload = f"{seed}|{issue}|{action_key}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
