"""Issue #208: dynamic N x K risk-conditioned parlay policy frontier.

Contract BJ-UNIFIED-DYNAMIC-N-001 / v3. Frozen preregistrations live in
docs/research/issue_208_protocol_log.md. This module binds constants,
action catalog, seeds and chronology.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Final

CONTRACT_VERSION: Final = "bj208-dynamic-nk-policy-v1"
PROTOCOL_VERSION: Final = "bj208-protocol-v1"
UPSTREAM_207_SHA: Final = (
    "90869a959dc1b972cd872ffe465d1009e29df75e"
)
UPSTREAM_207_PACKAGE: Final = "results/issue-207"
UPSTREAM_207_MANIFEST_SHA256: Final = (
    "48c11d971c20cb2239cd342ade4084bea484686bd106253c77a320ba7ae78ab6"
)
VALUE_MATRIX: Final = "results/issue-205/value_matrix.parquet"
VALUE_MATRIX_SHA256: Final = (
    "8fdace9c7249502456f8990137011847df9addae5ad633e61760c44b7ccde84b"
)
CAUSAL_TENSOR_PACKAGE: Final = "results/bj203_causal_tensor_v2"

N_GRID: Final = (4, 5, 6, 7, 8, 9, 10)
K_GRID: Final = (8, 16, 32)
OUTCOMES: Final = ("3", "1", "0")
TAX_FACTOR: Final = 0.65
TICKET_STAKE_YUAN: Final = 2
INITIAL_BANKROLL_YUAN: Final = 100_000.0

# Generator lanes (frozen panel derived from #205/#206/#207)
LANES: Final = ("MARKET_WR", "MARKET_WOR", "VALUE_WOR", "LEARNED_MLP")
STOCHASTIC_LANES: Final = ("MARKET_WR", "MARKET_WOR")
DETERMINISTIC_LANES: Final = ("VALUE_WOR", "LEARNED_MLP")

# Capital lanes
CAPITAL_LANES: Final = ("NATIVE_2_YUAN", "SIMPLE_ACTIVE")

# Frozen incumbent identity (from #207 CONTROLLING K8 panel)
INCUMBENT_N: Final = 7
INCUMBENT_K: Final = 8
INCUMBENT_LANE: Final = "MARKET_WOR"
INCUMBENT_CAPITAL: Final = "NATIVE_2_YUAN"

# #207's matched-reference sensitivity lane (reported, not incumbent)
REFERENCE_LANE: Final = "MARKET_WR"

DEVELOPMENT_SPLITS: Final = ("CV_2021", "CV_2022", "CV_2023")
FIT_SPLIT: Final = "CV_2021"
SELECTION_SPLIT: Final = "CV_2022"
TERMINAL_SPLIT: Final = "CV_2023"
EMBARGOED_SPLITS: Final = ("LOCKED_TEST",)
# Fold construction (PROTOCOL-LOG DELTA #208-1)
# Fold 1: train {CV_2021} -> test CV_2022
# Fold 2: train {CV_2021, CV_2022} -> test CV_2023
FOLDS: Final = (
    (("CV_2021",), "CV_2022"),
    (("CV_2021", "CV_2022"), "CV_2023"),
)

SEED_COUNT: Final = 16
MODEL_SEED: Final = 208001
NUISANCE_CANDIDATE_SEEDS: Final = (208101, 208102, 208103)


def seed_for(seed_index: int) -> int:
    """16 preregistered hash-derived seeds (protocol section 4)."""
    if not 1 <= seed_index <= SEED_COUNT:
        raise ValueError(f"seed index out of range: {seed_index}")
    payload = f"bj208-seed-{seed_index}".encode("utf-8")
    return int.from_bytes(sha256(payload).digest()[:8], "little")


ALL_SEEDS: Final = tuple(seed_for(i) for i in range(1, SEED_COUNT + 1))

# Learned ranker feature set (frozen from #206 LEARNED_MLP)
RANKER_FEATURES: Final = (
    "log_joint_probability",
    "log_sp_product",
    "expected_pre_tax_net",
    "mean_selected_probability",
    "min_selected_probability",
    "mean_selected_sp",
    "outcome_hhi",
    "match_rank_mean",
)

FORBIDDEN_INFERENCE_PARTS: Final = (
    "result", "score", "settlement", "winning_sp", "official_sp",
    "final_observed_sp", "payout", "tax", "roi", "profit", "hit",
    "realized_gross", "realized_hit", "official_final_sp_label",
    "realized_outcome", "post_issue", "gross_payout",
)


@dataclass(frozen=True)
class Action:
    n: int
    k: int
    lane: str
    capital: str

    def validate(self) -> None:
        if self.n not in N_GRID:
            raise ValueError(f"n out of grid: {self.n}")
        if self.k not in K_GRID:
            raise ValueError(f"k out of grid: {self.k}")
        if self.lane not in LANES:
            raise ValueError(f"lane unknown: {self.lane}")
        if self.capital not in CAPITAL_LANES:
            raise ValueError(f"capital lane unknown: {self.capital}")

    @property
    def key(self) -> str:
        return f"N{self.n}/K{self.k}/{self.lane}/{self.capital}"


def all_actions() -> tuple[Action, ...]:
    return tuple(
        Action(n=n, k=k, lane=lane, capital=capital)
        for n in N_GRID
        for k in K_GRID
        for lane in LANES
        for capital in CAPITAL_LANES
    )


def action_encoding(action: Action) -> list[float]:
    """Deterministic numeric action encoding for Q_theta(x, a)."""
    return [
        float(action.n),
        float(action.k),
        float(LANES.index(action.lane)),
        float(CAPITAL_LANES.index(action.capital)),
    ]


def forbidden_inference_names(values: object) -> list[str]:
    failures: list[str] = []
    for value in values:  # type: ignore[union-attr]
        name = str(value).lower()
        if any(part in name for part in FORBIDDEN_INFERENCE_PARTS):
            failures.append(str(value))
    return sorted(failures)


def as_action_dict() -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION,
        "n_grid": list(N_GRID),
        "k_grid": list(K_GRID),
        "lanes": list(LANES),
        "capital_lanes": list(CAPITAL_LANES),
        "stochastic_lanes": list(STOCHASTIC_LANES),
        "seeds": list(ALL_SEEDS),
        "folds": [
            {"train": list(train), "test": test} for train, test in FOLDS
        ],
        "incumbent": {
            "n": INCUMBENT_N,
            "k": INCUMBENT_K,
            "lane": INCUMBENT_LANE,
            "capital": INCUMBENT_CAPITAL,
        },
        "upstream_207_sha": UPSTREAM_207_SHA,
        "upstream_207_manifest_sha256": UPSTREAM_207_MANIFEST_SHA256,
        "value_matrix_sha256": VALUE_MATRIX_SHA256,
    }


__all__ = [
    "Action", "ALL_SEEDS", "CAPITAL_LANES", "CONTRACT_VERSION",
    "DEVELOPMENT_SPLITS", "DETERMINISTIC_LANES", "EMBARGOED_SPLITS",
    "FIT_SPLIT", "FOLDS", "FORBIDDEN_INFERENCE_PARTS", "INITIAL_BANKROLL_YUAN",
    "INCUMBENT_CAPITAL", "INCUMBENT_K", "INCUMBENT_LANE", "INCUMBENT_N",
    "K_GRID", "LANES", "MODEL_SEED", "N_GRID", "NUISANCE_CANDIDATE_SEEDS",
    "OUTCOMES", "PROTOCOL_VERSION", "RANKER_FEATURES", "REFERENCE_LANE",
    "SELECTION_SPLIT", "SEED_COUNT", "STOCHASTIC_LANES", "TAX_FACTOR",
    "TERMINAL_SPLIT", "TICKET_STAKE_YUAN", "UPSTREAM_207_MANIFEST_SHA256",
    "UPSTREAM_207_PACKAGE", "UPSTREAM_207_SHA", "VALUE_MATRIX",
    "VALUE_MATRIX_SHA256", "action_encoding", "all_actions", "as_action_dict",
    "forbidden_inference_names", "seed_for",
]
