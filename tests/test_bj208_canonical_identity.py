"""Adversarial ticket-identity tests for Issue #208 C1 closure."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from parlay_policy.census import IssuePanel
from parlay_policy.contract import ALL_SEEDS
from parlay_policy.tickets import (
    TicketBuildError,
    _identity,
    _rows_to_frame,
    generate_candidate_pool,
    select_tickets,
)
from parlay_policy.verify import verify_nk_semantics


def _panel(m: int = 10) -> IssuePanel:
    probability = np.tile(np.array([0.55, 0.30, 0.15]), (m, 1))
    predicted_sp = np.tile(np.array([1.8, 3.2, 6.0]), (m, 1))
    realized = np.zeros((m, 3), dtype=bool)
    realized[:, 0] = True
    match_idx = np.arange(100, 100 + m, dtype=int)
    return IssuePanel(
        split="CV_2023",
        issue="23999",
        year=2023,
        match_idx=match_idx,
        control_probability=probability,
        experimental_probability=probability.copy(),
        predicted_sp=predicted_sp,
        sp_seed_std=np.zeros((m, 3)),
        official_sp=predicted_sp.copy(),
        realized=realized,
        labels_available=True,
        match_ids=match_idx.astype(str),
    )


def test_leg_permutation_has_one_canonical_identity_and_serialization():
    panel = _panel()
    selected = np.array([4, 1, 7, 2])
    outcomes = np.array([0, 2, 1, 0])
    permutation = np.array([2, 0, 3, 1])

    first = _identity(panel, selected, outcomes)
    second = _identity(panel, selected[permutation], outcomes[permutation])
    assert first == second

    rows = _rows_to_frame(
        panel,
        [selected, selected[permutation]],
        [outcomes, outcomes[permutation]],
        ["A", "B"],
    )
    assert rows.ticket_identity.nunique() == 1
    assert rows.match_indices.nunique() == 1
    assert rows.outcomes.nunique() == 1
    assert rows.iloc[0].match_indices == "101|102|104|107"
    assert rows.iloc[0].outcomes == "0|3|3|1"


def test_generated_candidate_pool_is_semantically_unique():
    pool = generate_candidate_pool(_panel(), 4, draws_per_seed=48)
    assert pool.ticket_identity.is_unique
    paired = pool.apply(
        lambda row: tuple(
            sorted(
                zip(
                    str(row.match_indices).split("|"),
                    str(row.outcomes).split("|"),
                    strict=True,
                )
            )
        ),
        axis=1,
    )
    assert paired.is_unique


def test_non_wr_lane_rejects_duplicate_candidate_identity():
    pool = generate_candidate_pool(_panel(), 4, draws_per_seed=48)
    alias = pool.iloc[[0]].copy()
    matches = str(alias.iloc[0].match_indices).split("|")
    outcomes = str(alias.iloc[0].outcomes).split("|")
    reversed_pairs = list(reversed(list(zip(matches, outcomes, strict=True))))
    alias.loc[:, "match_indices"] = "|".join(pair[0] for pair in reversed_pairs)
    alias.loc[:, "outcomes"] = "|".join(pair[1] for pair in reversed_pairs)
    alias.loc[:, "ticket_identity"] = "f" * 64
    duplicated = pd.concat([pool, alias], ignore_index=True)
    with pytest.raises(TicketBuildError, match="semantic duplicate"):
        select_tickets(
            duplicated,
            "MARKET_WOR",
            8,
            seed=ALL_SEEDS[0],
        )


def test_verifier_rejects_order_alias_in_wor_bundle():
    issue = "23999"
    matches = [101, 102, 104, 107]
    outcomes = ["0", "3", "3", "1"]
    canonical_payload = "|".join(
        f"{issue}:{match_idx}:{outcome}"
        for match_idx, outcome in zip(matches, outcomes, strict=True)
    )
    canonical_identity = hashlib.sha256(
        canonical_payload.encode("utf-8")
    ).hexdigest()
    reversed_pairs = list(reversed(list(zip(matches, outcomes, strict=True))))
    noncanonical_payload = "|".join(
        f"{issue}:{match_idx}:{outcome}"
        for match_idx, outcome in reversed_pairs
    )
    noncanonical_identity = hashlib.sha256(
        noncanonical_payload.encode("utf-8")
    ).hexdigest()
    rows = pd.DataFrame(
        {
            "split": ["CV_2023", "CV_2023"],
            "issue": [issue, issue],
            "n": [4, 4],
            "k": [2, 2],
            "lane": ["MARKET_WOR", "MARKET_WOR"],
            "seed": [ALL_SEEDS[0], ALL_SEEDS[0]],
            "ticket_identity": [canonical_identity, noncanonical_identity],
            "match_indices": [
                "|".join(map(str, matches)),
                "|".join(str(pair[0]) for pair in reversed_pairs),
            ],
            "outcomes": [
                "|".join(outcomes),
                "|".join(pair[1] for pair in reversed_pairs),
            ],
        }
    )
    failures = verify_nk_semantics(rows)
    assert failures
    assert any("canonical" in failure or "semantic duplicate" in failure for failure in failures)
