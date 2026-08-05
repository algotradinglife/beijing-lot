#!/usr/bin/env python3
"""Exact three-stage Gate-B primitives for #193.

This module is intentionally separate from the superseded flattened #193
checkpoint.  It binds the merged Gate-A v1/v2 packages and exposes exact
issue-level Stage-1 supports/economics used by the chronological chain.
Outcome access starts only in the settlement functions below; catalog and
support construction remain the byte-frozen pre-event decisions.
"""
from __future__ import annotations

import csv
import ctypes
import gzip
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
GATE_A_V1 = ROOT / "results" / "bj193_gate_a_preoutcome_v1"
GATE_A_V2 = ROOT / "results" / "bj193_gate_a_chain_interface_v2"
OUTCOME_LEDGER = (
    ROOT / "results" / "bj190_gate_b_sparse_divergence_v1"
    / "canonical_outcome_ledger.csv.gz"
)
STAKE_PER_TICKET = 2.0
PAYOUT_FACTOR = 0.65
TAX_LINE_YUAN = 10_000.0
TAX_RATE = 0.20
FULL_TICKETS = 3**7
FULL_STAKE_YUAN = STAKE_PER_TICKET * FULL_TICKETS
STATUS_NO_BET = np.uint8(0)
STATUS_ACTIVE = np.uint8(1)
STATUS_UNAVAILABLE = np.uint8(2)


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_module(name: str, path: Path) -> object:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class Support:
    issue: str
    fold: str
    year: str
    identity: str
    ordered_match_ids: tuple[str, ...]
    source_portfolio_id: str

    def __post_init__(self) -> None:
        if len(self.ordered_match_ids) != 7 or len(set(self.ordered_match_ids)) != 7:
            raise ValueError("Stage-1 support must be exact ordered N7")


@dataclass(frozen=True)
class Outcome:
    issue: str
    result_code: str
    winning_sp: float


@dataclass
class StageStore:
    action_rows: list[dict[str, str]]
    issues: list[dict[str, str]]
    supports: dict[tuple[int, int], tuple[Support, ...]]
    status: np.ndarray
    stake: np.ndarray
    gross: np.ndarray
    tax: np.ndarray
    net: np.ndarray
    hit: np.ndarray


@dataclass
class StagePath:
    stage: str
    choices: np.ndarray
    model_by_issue: list[str]
    fallback_by_issue: np.ndarray
    model_receipts: list[dict[str, object]]
    screen_receipts: list[dict[str, object]]


@dataclass(frozen=True)
class Stage1Decision:
    issue_index: int
    action_index: int
    supports: tuple[Support, ...]
    output: dict[str, object]


@dataclass(frozen=True)
class DirectionSupport:
    support: Support
    output: dict[str, object]


@dataclass(frozen=True)
class Stage2Decision:
    issue_index: int
    action_index: int
    supports: tuple[DirectionSupport, ...]
    output: dict[str, object]


@dataclass
class ConditionalStore(StageStore):
    conditional_supports: dict[tuple[int, int], tuple[DirectionSupport, ...]]
    fallback_index: int
    comparator_net: np.ndarray
    comparator_stake: np.ndarray
    utility: np.ndarray
    utility_active: np.ndarray
    target_mode: str


@dataclass(frozen=True)
class MixedFeatureEncoder:
    projections: tuple[dict[str, str], ...]
    numeric_positions: tuple[int, ...]
    numeric_transform: object
    category_levels: dict[int, tuple[str, ...]]

    @classmethod
    def fit(
        cls,
        projections: Sequence[dict[str, str]],
        rows: Sequence[Mapping[str, object]],
        train: Sequence[int],
    ) -> "MixedFeatureEncoder":
        core = _core_module()
        numeric_positions = tuple(
            index for index, projection in enumerate(projections)
            if projection["dtype"] == "FLOAT64"
        )
        numeric = np.full((len(rows), len(numeric_positions)), np.nan)
        for issue_index, row in enumerate(rows):
            for column, projection_index in enumerate(numeric_positions):
                value = row.get(projections[projection_index]["projection_field"])
                if value not in (None, ""):
                    numeric[issue_index, column] = float(value)
        train_index = np.asarray(train, dtype=np.int64)
        transform = core.FeatureTransform.fit(numeric[train_index])
        category_levels: dict[int, tuple[str, ...]] = {}
        for index, projection in enumerate(projections):
            if projection["dtype"] not in {"CATEGORY", "CATEGORY_SET"}:
                continue
            observed: set[str] = set()
            for issue_index in train:
                value = rows[issue_index].get(projection["projection_field"])
                if projection["dtype"] == "CATEGORY_SET":
                    observed.update(str(item) for item in (value or ()) if str(item))
                elif value not in (None, ""):
                    observed.add(str(value))
            category_levels[index] = tuple(sorted(observed)) + ("__UNKNOWN__",)
        return cls(tuple(projections), numeric_positions, transform, category_levels)

    def apply(
        self, rows: Sequence[Mapping[str, object]], query: Sequence[int]
    ) -> np.ndarray:
        numeric_lookup = {
            projection_index: column
            for column, projection_index in enumerate(self.numeric_positions)
        }
        numeric = np.full((len(query), len(self.numeric_positions)), np.nan)
        for row_index, issue_index in enumerate(query):
            row = rows[issue_index]
            for projection_index, column in numeric_lookup.items():
                value = row.get(
                    self.projections[projection_index]["projection_field"]
                )
                if value not in (None, ""):
                    numeric[row_index, column] = float(value)
        encoded_numeric = self.numeric_transform.apply(numeric)
        columns: list[np.ndarray] = []
        for projection_index, projection in enumerate(self.projections):
            dtype = projection["dtype"]
            if dtype == "FLOAT64":
                column = numeric_lookup[projection_index]
                columns.extend(
                    [encoded_numeric[:, 2 * column], encoded_numeric[:, 2 * column + 1]]
                )
            elif dtype == "BOOLEAN":
                value = np.zeros(len(query), dtype=np.float64)
                missing = np.zeros(len(query), dtype=np.float64)
                for row_index, issue_index in enumerate(query):
                    raw = rows[issue_index].get(projection["projection_field"])
                    if raw in (None, ""):
                        missing[row_index] = 1.0
                    else:
                        value[row_index] = float(bool(raw))
                columns.extend([value, missing])
            elif dtype in {"CATEGORY", "CATEGORY_SET"}:
                levels = self.category_levels[projection_index]
                matrix = np.zeros((len(query), len(levels)), dtype=np.float64)
                known = {level: index for index, level in enumerate(levels[:-1])}
                for row_index, issue_index in enumerate(query):
                    raw = rows[issue_index].get(projection["projection_field"])
                    values = (
                        [str(item) for item in (raw or ()) if str(item)]
                        if dtype == "CATEGORY_SET" else [str(raw)]
                    )
                    matched = False
                    for value in values:
                        if value in known:
                            matrix[row_index, known[value]] = 1.0
                            matched = True
                    if not matched:
                        matrix[row_index, -1] = 1.0
                columns.extend(matrix[:, column] for column in range(matrix.shape[1]))
            else:
                raise RuntimeError(f"unsupported frozen feature dtype: {dtype}")
        return np.column_stack(columns)

    def group_columns(self) -> dict[str, list[int]]:
        group_by_field = {
            row["feature"]: row["group"]
            for row in read_csv(GATE_A_V1 / "feature_contract.csv")
        }
        groups: dict[str, list[int]] = defaultdict(list)
        at = 0
        for index, projection in enumerate(self.projections):
            if projection["dtype"] in {"FLOAT64", "BOOLEAN"}:
                width = 2
            else:
                width = len(self.category_levels[index])
            group = (
                group_by_field.get(projection["source_field"], "STAGE_UPSTREAM")
                if projection["source_scope"] == "COMMON_X_I"
                else "STAGE_UPSTREAM"
            )
            groups[group].extend(range(at, at + width))
            at += width
        pool_value: list[int] = []
        for group in ("POOL", "PROBABILITY", "SP_VALUE", "SELECTOR_CENSUS"):
            pool_value.extend(groups.get(group, ()))
        groups["POOL_VALUE"] = pool_value
        return dict(groups)


def _support(
    issue: str,
    fold: str,
    year: str,
    identity: str,
    match_ids: Sequence[str],
    portfolio: str,
) -> Support:
    return Support(
        issue=str(issue),
        fold=str(fold),
        year=str(year),
        identity=str(identity),
        ordered_match_ids=tuple(str(value) for value in match_ids),
        source_portfolio_id=str(portfolio),
    )


def load_issue_rows() -> list[dict[str, str]]:
    rows = read_csv(GATE_A_V1 / "issue_regime_features.csv.gz")
    if len(rows) != 344 or len({row["issue"] for row in rows}) != 344:
        raise RuntimeError("#193 canonical issue census drift")
    return rows


def load_stage_catalog(stage: int) -> list[dict[str, str]]:
    names = {
        1: "stage1_selection_catalog.csv.gz",
        2: "stage2_direction_catalog.csv.gz",
        3: "stage3_bet_catalog.csv.gz",
    }
    rows = read_csv(GATE_A_V2 / names[stage])
    expected = {1: 2_469, 2: 2_425, 3: 963}[stage]
    if len(rows) != expected or len({row["interface_action_key"] for row in rows}) != expected:
        raise RuntimeError(f"#193 Stage-{stage} catalog census drift")
    return rows


def _load_127_supports() -> dict[tuple[str, str], list[Support]]:
    grouped: dict[
        tuple[str, str, str, str, str], dict[int, str]
    ] = defaultdict(dict)
    path = (
        ROOT / "results" / "bj127_gate_a_preoutcome_v2"
        / "portfolio_role_assignments.csv.gz"
    )
    for row in read_csv(path):
        key = (
            row["variant_id"], row["issue"], row["fold"], row["year"],
            row["portfolio_id"],
        )
        rank = int(row["selection_rank"])
        if rank in grouped[key]:
            raise RuntimeError("#127 duplicate selection rank")
        grouped[key][rank] = row["match_id"]
    output: dict[tuple[str, str], list[Support]] = defaultdict(list)
    for (variant, issue, fold, year, portfolio), ranked in grouped.items():
        if sorted(ranked) != list(range(1, 8)):
            raise RuntimeError("#127 Stage-1 support rank drift")
        output[(variant, issue)].append(
            _support(
                issue, fold, year, portfolio,
                [ranked[index] for index in range(1, 8)], portfolio,
            )
        )
    for values in output.values():
        values.sort(key=lambda value: (value.source_portfolio_id, value.identity))
    return output


def _load_134_supports() -> tuple[
    dict[tuple[str, str], Support], dict[tuple[str, str], dict[str, str]]
]:
    package = ROOT / "results" / "bj134_gate_a_preoutcome_v2"
    scores = {
        (row["issue_instance"], row["portfolio_id"]): row
        for row in read_csv(package / "candidate_universe_scores.csv.gz")
    }
    output: dict[tuple[str, str], Support] = {}
    selected_scores: dict[tuple[str, str], dict[str, str]] = {}
    for row in read_csv(package / "selection_freeze.csv"):
        if row["policy_status"] != "SELECTED_PREOUTCOME":
            continue
        key = (row["arm"], row["issue"])
        support = _support(
            row["issue"], row["fold"], row["year"],
            row["selected_identity_fingerprint"],
            row["selected_match_ids"].split("|"), row["selected_portfolio_id"],
        )
        output[key] = support
        selected_scores[key] = scores[
            (row["issue_instance"], row["selected_portfolio_id"])
        ]
    return output, selected_scores


def _load_190_supports() -> dict[tuple[str, str], Support]:
    package = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    output: dict[tuple[str, str], Support] = {}
    for shard in range(1, 5):
        path = package / f"policy_issue_selection_freeze_part_{shard:02d}_of_04.csv.gz"
        for row in read_csv(path):
            if row["policy_status"] != "SELECTED_PREOUTCOME":
                continue
            key = (row["policy_id"], row["issue"])
            if key in output:
                raise RuntimeError("#190 duplicate policy/issue Stage-1 support")
            output[key] = _support(
                row["issue"], row["fold"], row["year"],
                row["selected_n7_identity_sha256"],
                json.loads(row["selected_match_ids_json"]),
                row["selected_n7_identity_sha256"],
            )
    return output


def build_stage1_supports(
    action_rows: Sequence[dict[str, str]],
    issues: Sequence[dict[str, str]],
) -> dict[tuple[int, int], tuple[Support, ...]]:
    by_issue = {row["issue"]: index for index, row in enumerate(issues)}
    s127 = _load_127_supports()
    s134, score134 = _load_134_supports()
    s190 = _load_190_supports()
    output: dict[tuple[int, int], tuple[Support, ...]] = {}
    for action_index, action in enumerate(action_rows):
        upstream = int(action["upstream_issue"])
        source_identity = action["source_identity"]
        parameters = json.loads(action["parameters_json"])
        for issue, issue_index in by_issue.items():
            supports: tuple[Support, ...] = ()
            if upstream == 127:
                supports = tuple(s127.get((source_identity, issue), ()))
            elif upstream == 134:
                arm = str(parameters.get("arm", source_identity))
                support = s134.get((arm, issue))
                if support is not None and action["source_file"] == "threshold_registry.csv":
                    score = score134[(arm, issue)]
                    value = float(score[str(parameters["metric"])])
                    threshold = float(parameters["threshold_value"])
                    passes = (
                        value >= threshold
                        if parameters["operator"] == ">="
                        else value <= threshold
                    )
                    if not passes:
                        support = None
                supports = () if support is None else (support,)
            elif upstream == 190:
                support = s190.get((source_identity, issue))
                supports = () if support is None else (support,)
            else:
                raise RuntimeError(f"unknown Stage-1 upstream issue: {upstream}")
            if supports:
                output[(action_index, issue_index)] = supports
    return output


def load_outcomes() -> dict[str, Outcome]:
    output: dict[str, Outcome] = {}
    for row in read_csv(OUTCOME_LEDGER):
        if row["availability_status"] != "TRUSTED" or row["has_trusted_settlement"] != "1":
            continue
        value = Outcome(
            issue=row["issue"], result_code=row["result_code"],
            winning_sp=float(row["winning_sp"]),
        )
        if value.result_code not in {"3", "1", "0"} or value.winning_sp <= 0:
            raise RuntimeError("invalid canonical outcome row")
        output[row["match_id"]] = value
    if len(output) != 100_906:
        raise RuntimeError("#190 canonical trusted outcome census drift")
    return output


def settle_full_support(
    support: Support, outcomes: Mapping[str, Outcome]
) -> dict[str, float | int | str]:
    missing = [match_id for match_id in support.ordered_match_ids if match_id not in outcomes]
    if missing:
        return {
            "status": "UNAVAILABLE", "stake": 0.0, "gross": 0.0,
            "tax": 0.0, "net": 0.0, "hit": 0,
            "missing_match_ids": "|".join(missing),
        }
    rows = [outcomes[match_id] for match_id in support.ordered_match_ids]
    if any(row.issue != support.issue for row in rows):
        raise RuntimeError("canonical outcome issue mismatch")
    payout = STAKE_PER_TICKET * PAYOUT_FACTOR * math.prod(
        row.winning_sp for row in rows
    )
    tax = payout * TAX_RATE if payout >= TAX_LINE_YUAN else 0.0
    return {
        "status": "ACTIVE", "stake": FULL_STAKE_YUAN, "gross": payout,
        "tax": tax, "net": payout - FULL_STAKE_YUAN, "hit": 1,
        "missing_match_ids": "",
    }


def build_stage1_store() -> StageStore:
    issues = load_issue_rows()
    actions = load_stage_catalog(1)
    supports = build_stage1_supports(actions, issues)
    outcomes = load_outcomes()
    shape = (len(actions), len(issues))
    arrays = {
        name: np.zeros(shape, dtype=np.float64)
        for name in ("stake", "gross", "tax", "net", "hit")
    }
    status = np.full(shape, STATUS_NO_BET, dtype=np.uint8)
    for key, support_rows in supports.items():
        settled = [settle_full_support(support, outcomes) for support in support_rows]
        if any(row["status"] == "UNAVAILABLE" for row in settled):
            status[key] = STATUS_UNAVAILABLE
            continue
        status[key] = STATUS_ACTIVE
        for name in arrays:
            arrays[name][key] = sum(float(row[name]) for row in settled)
    if np.any((status != STATUS_ACTIVE) & (arrays["stake"] != 0.0)):
        raise RuntimeError("Stage-1 zero-flow status carries stake")
    return StageStore(
        action_rows=list(actions), issues=issues, supports=supports,
        status=status, **arrays,
    )


def stage1_store_identity(store: StageStore) -> str:
    payload: dict[str, object] = {
        "contract": "BJ193_STAGE1_STATIC_FULL_SETTLEMENT_V2",
        "action_ids": [row["interface_action_key"] for row in store.action_rows],
        "issues": [row["issue"] for row in store.issues],
        "arrays": {},
    }
    arrays = payload["arrays"]
    assert isinstance(arrays, dict)
    for name in ("status", "stake", "gross", "tax", "net", "hit"):
        value = np.ascontiguousarray(getattr(store, name))
        arrays[name] = hashlib.sha256(value.tobytes()).hexdigest()
    return canonical_hash(payload)


def _core_module():
    import importlib.util
    import sys

    name = "bj193_gate_b_core_chain_v2"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "scripts" / "bj193_gate_b_core.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _stage1_raw_features(
    issues: Sequence[Mapping[str, str]],
) -> tuple[np.ndarray, dict[str, list[int]]]:
    projections = [
        row for row in read_csv(GATE_A_V2 / "stage_feature_projection.csv")
        if row["stage"] == "STAGE_1_SELECTION" and row["model_input"] == "True"
    ]
    projections.sort(key=lambda row: int(row["feature_ordinal"]))
    if len(projections) != 68 or any(row["dtype"] != "FLOAT64" for row in projections):
        raise RuntimeError("#193 Stage-1 projection contract drift")
    raw = np.full((len(issues), len(projections)), np.nan, dtype=np.float64)
    for issue_index, issue in enumerate(issues):
        for feature_index, projection in enumerate(projections):
            value = issue.get(projection["source_field"], "")
            if value not in (None, ""):
                raw[issue_index, feature_index] = float(value)
    group_by_field = {
        row["feature"]: row["group"]
        for row in read_csv(GATE_A_V1 / "feature_contract.csv")
    }
    groups: dict[str, list[int]] = defaultdict(list)
    for index, projection in enumerate(projections):
        groups[group_by_field[projection["source_field"]]].append(index)
    return raw, dict(groups)


def _transform_stage1(
    raw: np.ndarray,
    groups: Mapping[str, Sequence[int]],
    train: Sequence[int],
    query: Sequence[int],
) -> tuple[np.ndarray, np.ndarray, dict[str, list[int]]]:
    core = _core_module()
    train_index = np.asarray(train, dtype=np.int64)
    query_index = np.asarray(query, dtype=np.int64)
    transform = core.FeatureTransform.fit(raw[train_index])
    train_x = transform.apply(raw[train_index])
    query_x = transform.apply(raw[query_index])
    encoded = {
        group: [column for index in indices for column in (2 * int(index), 2 * int(index) + 1)]
        for group, indices in groups.items()
    }
    pool_value: list[int] = []
    for group in ("POOL", "PROBABILITY", "SP_VALUE", "SELECTOR_CENSUS"):
        pool_value.extend(encoded.get(group, ()))
    encoded["POOL_VALUE"] = pool_value
    return train_x, query_x, encoded


def _action_screen(
    store: StageStore,
    train: Sequence[int],
    keep: int,
    fallback: int,
) -> list[int]:
    core = _core_module()
    action_ids = [row["interface_action_key"] for row in store.action_rows]
    ranked = core.selector_rank(
        store.net, store.stake, action_ids, train, keep=keep
    )
    if fallback not in ranked:
        ranked.append(fallback)
    return ranked


def _stage_predictions(
    store: StageStore,
    raw: np.ndarray,
    groups: Mapping[str, Sequence[int]],
    model: Mapping[str, str],
    actions: Sequence[int],
    train: Sequence[int],
    query: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    core = _core_module()
    train_index = np.asarray(train, dtype=np.int64)
    train_x, query_x, encoded_groups = _transform_stage1(
        raw, groups, train, query
    )
    stake = store.stake[np.ix_(actions, train_index)].T
    net = store.net[np.ix_(actions, train_index)].T
    active = (
        store.status[np.ix_(actions, train_index)].T == STATUS_ACTIVE
    ) & (stake > 0.0)
    utility = np.divide(net, stake, out=np.zeros_like(net), where=stake > 0.0)
    parameters = json.loads(model["parameters_json"])
    predicted = core.predict_model(
        model["family"], parameters, train_x, query_x, utility, active,
        encoded_groups, train_weight=stake,
    )
    prior = core.prior_predictions(
        utility, active, len(query), train_weight=stake
    )
    return predicted, prior


def _choose_stage_actions(
    store: StageStore,
    actions: Sequence[int],
    query: Sequence[int],
    predicted: np.ndarray,
    prior: np.ndarray,
    fallback: int,
    family: str,
) -> tuple[list[int], list[bool]]:
    action_ids = [store.action_rows[index]["interface_action_key"] for index in actions]
    fallback_local = actions.index(fallback)
    query_index = np.asarray(query, dtype=np.int64)
    available = (
        store.status[np.ix_(actions, query_index)].T == STATUS_ACTIVE
    ) & (store.stake[np.ix_(actions, query_index)].T > 0.0)
    stake = store.stake[np.ix_(actions, query_index)].T
    chosen: list[int] = []
    used_fallback: list[bool] = []
    if family == "PRIOR_ONLY_FIXED":
        for row_index in range(len(query)):
            candidates = [
                index for index in range(len(actions))
                if available[row_index, index] and math.isfinite(float(prior[row_index, index]))
            ]
            if not candidates:
                chosen.append(fallback)
                used_fallback.append(True)
                continue
            candidates.sort(
                key=lambda index: (
                    -float(prior[row_index, index]),
                    float(stake[row_index, index]), action_ids[index],
                )
            )
            selected = actions[candidates[0]]
            chosen.append(selected)
            used_fallback.append(selected == fallback)
        return chosen, used_fallback
    core = _core_module()
    local = core.choose_actions(
        predicted, available, action_ids, stake,
        [1] * len(actions), prior, fallback_local,
    )
    for index in local:
        selected = actions[index]
        chosen.append(selected)
        used_fallback.append(selected == fallback)
    return chosen, used_fallback


def _choice_flows(
    store: StageStore, choices: Sequence[int], query: Sequence[int]
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for action, issue in zip(choices, query, strict=True):
        active = (
            store.status[action, issue] == STATUS_ACTIVE
            and store.stake[action, issue] > 0.0
        )
        rows.append(
            {
                "stake": float(store.stake[action, issue]) if active else 0.0,
                "gross": float(store.gross[action, issue]) if active else 0.0,
                "tax": float(store.tax[action, issue]) if active else 0.0,
                "net": float(store.net[action, issue]) if active else 0.0,
            }
        )
    return rows


def _validation_key(
    flows: Sequence[Mapping[str, float]], model: Mapping[str, str]
) -> tuple[float, float, float, int, str]:
    core = _core_module()
    stake = sum(row["stake"] for row in flows)
    net = sum(row["net"] for row in flows)
    roi = net / stake if stake else -math.inf
    holding = core.holding_metrics(flows, reference_capital=1_000_000.0)
    return (
        -roi, float(holding["max_drawdown_yuan"]), stake,
        int(model["complexity_rank"]), model["stage_model_id"],
    )


def build_honest_stage1_path(store: StageStore) -> StagePath:
    """Generate fixed-within-year honest Stage-1 OOF choices for 2019-2025."""
    models = [
        row for row in read_csv(GATE_A_V2 / "stage_model_grid.csv")
        if row["stage"] == "STAGE_1_SELECTION"
    ]
    if len(models) != 30:
        raise RuntimeError("#193 Stage-1 model grid drift")
    raw, groups = _stage1_raw_features(store.issues)
    fallback_candidates = [
        index for index, row in enumerate(store.action_rows)
        if row["upstream_issue"] == "134" and row["source_identity"] == "MARKET_BEST_FULL"
    ]
    if len(fallback_candidates) != 1:
        raise RuntimeError("#193 Stage-1 static fallback identity drift")
    fallback = fallback_candidates[0]
    choices = np.full(len(store.issues), fallback, dtype=np.int32)
    fallback_flags = np.ones(len(store.issues), dtype=bool)
    model_by_issue = ["INSUFFICIENT_HISTORY_STATIC_FALLBACK"] * len(store.issues)
    model_receipts: list[dict[str, object]] = []
    screen_receipts: list[dict[str, object]] = []
    years = np.asarray([int(row["year"]) for row in store.issues])
    for test_year in range(2021, 2026):
        inner_train = np.flatnonzero(years < test_year - 1).tolist()
        validation = np.flatnonzero(years == test_year - 1).tolist()
        outer_train = np.flatnonzero(years < test_year).tolist()
        outer_test = np.flatnonzero(years == test_year).tolist()
        inner_actions = _action_screen(store, inner_train, 16, fallback)
        eligible_models = models
        if len(inner_train) < 60 or len({store.issues[i]["year"] for i in inner_train}) < 2:
            eligible_models = [
                row for row in models if row["family"] == "PRIOR_ONLY_FIXED"
            ]
        candidates = []
        for model in eligible_models:
            predicted, prior = _stage_predictions(
                store, raw, groups, model, inner_actions, inner_train, validation
            )
            selected, _ = _choose_stage_actions(
                store, inner_actions, validation, predicted, prior, fallback,
                model["family"],
            )
            flows = _choice_flows(store, selected, validation)
            candidates.append((_validation_key(flows, model), model))
        candidates.sort(key=lambda value: value[0])
        selected_model = candidates[0][1]
        outer_actions = _action_screen(store, outer_train, 16, fallback)
        predicted, prior = _stage_predictions(
            store, raw, groups, selected_model, outer_actions, outer_train, outer_test
        )
        selected, used_fallback = _choose_stage_actions(
            store, outer_actions, outer_test, predicted, prior, fallback,
            selected_model["family"],
        )
        for issue, action, flag in zip(outer_test, selected, used_fallback, strict=True):
            choices[issue] = action
            fallback_flags[issue] = flag
            model_by_issue[issue] = selected_model["stage_model_id"]
        for phase, actions in (("INNER_TRAIN", inner_actions), ("OUTER_TRAIN", outer_actions)):
            for rank, action in enumerate(actions, 1):
                screen_receipts.append(
                    {
                        "outer_fold": f"TEST_{test_year}", "stage": "STAGE_1_SELECTION",
                        "screen_phase": phase, "rank": rank,
                        "action_identity": store.action_rows[action]["interface_action_key"],
                        "mandatory_fallback": action == fallback,
                    }
                )
        model_receipts.append(
            {
                "outer_fold": f"TEST_{test_year}", "stage": "STAGE_1_SELECTION",
                "selected_model_id": selected_model["stage_model_id"],
                "selected_family": selected_model["family"],
                "inner_train_issue_count": len(inner_train),
                "inner_validation_issue_count": len(validation),
                "outer_train_issue_count": len(outer_train),
                "outer_test_issue_count": len(outer_test),
                "inner_screen_action_count": len(inner_actions),
                "outer_screen_action_count": len(outer_actions),
                "validation_pre_tax_roi": -candidates[0][0][0],
            }
        )
    return StagePath(
        stage="STAGE_1_SELECTION", choices=choices,
        model_by_issue=model_by_issue, fallback_by_issue=fallback_flags,
        model_receipts=model_receipts, screen_receipts=screen_receipts,
    )


def stage_path_identity(path: StagePath, store: StageStore) -> str:
    return canonical_hash(
        {
            "stage": path.stage,
            "choices": [
                store.action_rows[int(index)]["interface_action_key"]
                for index in path.choices
            ],
            "models": path.model_by_issue,
            "fallback": [bool(value) for value in path.fallback_by_issue],
            "model_receipts": path.model_receipts,
            "screen_receipts": path.screen_receipts,
        }
    )


def write_stage_path(path: StagePath, store: StageStore, target: Path) -> str:
    identity = stage_path_identity(path, store)
    payload = {
        "contract": "BJ193_STAGE_PATH_CHECKPOINT_V2",
        "stage": path.stage,
        "action_keys": [
            store.action_rows[int(index)]["interface_action_key"]
            for index in path.choices
        ],
        "model_by_issue": path.model_by_issue,
        "fallback_by_issue": [bool(value) for value in path.fallback_by_issue],
        "model_receipts": path.model_receipts,
        "screen_receipts": path.screen_receipts,
        "stage_path_identity_sha256": identity,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(target.name + ".stage")
    staged.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    staged.replace(target)
    return identity


def read_stage_path(target: Path, store: StageStore) -> StagePath:
    payload = json.loads(target.read_text())
    if payload["contract"] != "BJ193_STAGE_PATH_CHECKPOINT_V2":
        raise RuntimeError("Stage path checkpoint contract drift")
    lookup = {
        row["interface_action_key"]: index
        for index, row in enumerate(store.action_rows)
    }
    choices = np.asarray(
        [lookup[key] for key in payload["action_keys"]], dtype=np.int32
    )
    path = StagePath(
        stage=payload["stage"], choices=choices,
        model_by_issue=list(payload["model_by_issue"]),
        fallback_by_issue=np.asarray(payload["fallback_by_issue"], dtype=bool),
        model_receipts=list(payload["model_receipts"]),
        screen_receipts=list(payload["screen_receipts"]),
    )
    if stage_path_identity(path, store) != payload["stage_path_identity_sha256"]:
        raise RuntimeError("Stage path checkpoint identity mismatch")
    return path


def _stage1_candidate_score_lookup() -> dict[tuple[str, str, str], list[float]]:
    """Outcome-unexposed selected-support score summaries for Stage-2 X_i."""
    output: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    package127 = ROOT / "results" / "bj127_gate_a_preoutcome_v2"
    for row in read_csv(package127 / "portfolio_role_assignments.csv.gz"):
        output[("127", row["variant_id"], row["issue"])].append(
            float(row["e_sp"])
        )
    package134 = ROOT / "results" / "bj134_gate_a_preoutcome_v2"
    for row in read_csv(package134 / "selection_freeze.csv"):
        if row["policy_status"] == "SELECTED_PREOUTCOME" and row["selected_score"]:
            output[("134", row["arm"], row["issue"])].append(
                float(row["selected_score"])
            )
    package190 = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    for shard in range(1, 5):
        for row in read_csv(
            package190 / f"policy_issue_selection_freeze_part_{shard:02d}_of_04.csv.gz"
        ):
            if row["policy_status"] == "SELECTED_PREOUTCOME":
                output[("190", row["policy_id"], row["issue"])].append(
                    float(row["strongest_magnitude"])
                )
    return dict(output)


def build_stage1_decisions(
    store: StageStore, path: StagePath
) -> list[Stage1Decision]:
    scores = _stage1_candidate_score_lookup()
    decisions: list[Stage1Decision] = []
    for issue_index, action_value in enumerate(path.choices):
        action_index = int(action_value)
        action = store.action_rows[action_index]
        issue = store.issues[issue_index]
        supports = store.supports.get((action_index, issue_index), ())
        parameters = json.loads(action["parameters_json"])
        score_values = scores.get(
            (action["upstream_issue"], action["source_identity"], issue["issue"]),
            [],
        )
        selector_family = {
            "127": "BJ127_SELECTOR_VARIANT",
            "134": "BJ134_FUNDAMENTAL_OVERLAY",
            "190": str(parameters.get("detector_family", "BJ190_SPARSE_DIVERGENCE")),
        }[action["upstream_issue"]]
        active = (
            store.status[action_index, issue_index] == STATUS_ACTIVE
            and bool(supports)
        )
        payload: dict[str, object] = {
            "contract": "BJ193_STAGE1_SELECTION_OUTPUT_V2",
            "issue": issue["issue"],
            "issue_instance": issue["issue_instance"],
            "stage_id": "STAGE_1_SELECTION",
            "stage_version": "BJ193_THREE_STAGE_INTERFACE_V2",
            "model_id": path.model_by_issue[issue_index],
            "source_action_identity": action["interface_action_key"],
            "availability": "ACTIVE" if active else "UNAVAILABLE",
            "abstention_flag": not active,
            "fallback_flag": bool(path.fallback_by_issue[issue_index]),
            "reason_code": (
                "PRIOR_ONLY_FALLBACK"
                if path.fallback_by_issue[issue_index]
                else "MODEL_CHOICE"
            ),
            "selector_family": selector_family,
            "selector_parameters": parameters,
            "selected_supports": [
                {
                    "identity": support.identity,
                    "source_portfolio_id": support.source_portfolio_id,
                    "ordered_match_ids": list(support.ordered_match_ids),
                }
                for support in supports
            ],
            "candidate_scores": [format(value, ".12f") for value in score_values],
            "selected_match_count": sum(len(value.ordered_match_ids) for value in supports),
            "support_count": len(supports),
        }
        payload["output_sha256"] = canonical_hash(payload)
        decisions.append(
            Stage1Decision(issue_index, action_index, supports, payload)
        )
    return decisions


def _direction_adapter() -> object:
    return load_module(
        "bj193_frozen_conditional_chain_adapter",
        GATE_A_V2 / "conditional_chain_adapter.py",
    )


def _load_needed_estimators(
    decisions: Sequence[Stage1Decision],
) -> dict[str, dict[str, str]]:
    needed = {
        match_id
        for decision in decisions
        for support in decision.supports
        for match_id in support.ordered_match_ids
    }
    output: dict[str, dict[str, str]] = {}
    source = (
        ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
        / "estimator_match_freeze.csv.gz"
    )
    with gzip.open(source, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            match_id = row["match_id"]
            if match_id in needed:
                if match_id in output:
                    raise RuntimeError("duplicate #190 estimator match identity")
                output[match_id] = row
    return output


def _allow_all_direction(
    support: Support, stage1_output_sha256: str
) -> dict[str, object]:
    per_match = [
        {
            "match_id": match_id,
            "match_idx": index + 1,
            "estimator_source": "ALLOW_ALL_CONTROL",
            "estimator_identity_sha256": canonical_hash(
                {"control": "ALLOW_ALL", "issue": support.issue, "match_id": match_id}
            ),
            "estimator_component_identity_sha256": {},
            "probability_3_1_0": ["1.000000000000"] * 3,
            "allowed_codes": ["3", "1", "0"],
            "direction_weight_3_1_0": ["1.000000000000"] * 3,
            "favored_code": "",
            "omitted_code": "",
            "magnitude": "0.000000000000",
            "abs_z": "0.000000000000",
            "protection_flag": False,
            "threshold_pass": True,
        }
        for index, match_id in enumerate(support.ordered_match_ids)
    ]
    payload: dict[str, object] = {
        "adapter_version": "BJ193_ALLOW_ALL_CONTROL_V1",
        "adapter_sha256": canonical_hash("BJ193_ALLOW_ALL_CONTROL_V1"),
        "derived_direction_action_sha256": canonical_hash(
            {"control": "ALLOW_ALL", "support": support.identity}
        ),
        "upstream_policy_id": "B0_BEST_FULL",
        "stage1_output_sha256": stage1_output_sha256,
        "ordered_match_ids": list(support.ordered_match_ids),
        "status": "ACTIVE",
        "reason_code": "ALLOW_ALL_FALLBACK",
        "per_match": per_match,
        "ranked_direction_match_ids": list(support.ordered_match_ids),
        "strongest_match_id": "",
        "delete_leg_index_zero_based": None,
        "omitted_code": "",
        "ticket_support_size": FULL_TICKETS,
    }
    payload["direction_output_sha256"] = canonical_hash(payload)
    return payload


def settle_direction_support(
    support: Support,
    direction: Mapping[str, object],
    outcomes: Mapping[str, Outcome],
) -> dict[str, float | int | str]:
    status = str(direction["status"])
    if status != "ACTIVE":
        return {
            "status": status, "stake": 0.0, "gross": 0.0,
            "tax": 0.0, "net": 0.0, "hit": 0,
        }
    if any(match_id not in outcomes for match_id in support.ordered_match_ids):
        return {
            "status": "UNAVAILABLE", "stake": 0.0, "gross": 0.0,
            "tax": 0.0, "net": 0.0, "hit": 0,
        }
    allowed_by_match = {
        str(row["match_id"]): {str(code) for code in row["allowed_codes"]}
        for row in direction["per_match"]  # type: ignore[index]
    }
    if set(allowed_by_match) != set(support.ordered_match_ids):
        raise RuntimeError("direction support does not preserve Stage-1 matches")
    positive_support = int(direction["ticket_support_size"])
    stake = STAKE_PER_TICKET * positive_support
    hit = int(all(
        outcomes[match_id].result_code in allowed_by_match[match_id]
        for match_id in support.ordered_match_ids
    ))
    gross = (
        STAKE_PER_TICKET * PAYOUT_FACTOR * math.prod(
            outcomes[match_id].winning_sp for match_id in support.ordered_match_ids
        )
        if hit else 0.0
    )
    tax = gross * TAX_RATE if gross >= TAX_LINE_YUAN else 0.0
    return {
        "status": "ACTIVE", "stake": stake, "gross": gross,
        "tax": tax, "net": gross - stake, "hit": hit,
    }


def _apply_stage2_action(
    action: Mapping[str, str],
    decision: Stage1Decision,
    estimators: Mapping[str, Mapping[str, object]],
    adapter_sha256: str,
) -> tuple[DirectionSupport, ...]:
    if action["scientific_role"] == "STATIC_ALLOW_ALL_OUTCOME_CODES_CONTROL":
        return tuple(
            DirectionSupport(
                support,
                _allow_all_direction(
                    support, str(decision.output["output_sha256"])
                ),
            )
            for support in decision.supports
        )
    policy = json.loads(action["parameters_json"])
    policy["policy_id"] = action["source_identity"]
    policy["availability"] = action["availability"]
    adapter = _direction_adapter()
    return tuple(
        DirectionSupport(
            support,
            adapter.apply_direction_adapter(
                support.ordered_match_ids,
                estimators,
                policy,
                stage1_output_sha256=str(decision.output["output_sha256"]),
                adapter_sha256=adapter_sha256,
            ),
        )
        for support in decision.supports
    )


def build_stage2_store(
    stage1_store: StageStore,
    stage1_path: StagePath,
) -> tuple[ConditionalStore, list[Stage1Decision]]:
    decisions = build_stage1_decisions(stage1_store, stage1_path)
    actions = load_stage_catalog(2)
    fallback = [
        index for index, row in enumerate(actions)
        if row["scientific_role"] == "STATIC_ALLOW_ALL_OUTCOME_CODES_CONTROL"
    ]
    if len(fallback) != 1:
        raise RuntimeError("Stage-2 ALLOW_ALL fallback identity drift")
    fallback_index = fallback[0]
    estimators = _load_needed_estimators(decisions)
    adapter_path = GATE_A_V2 / "conditional_chain_adapter.py"
    adapter_sha256 = hashlib.sha256(adapter_path.read_bytes()).hexdigest()
    outcomes = load_outcomes()
    shape = (len(actions), len(decisions))
    arrays = {
        name: np.zeros(shape, dtype=np.float64)
        for name in ("stake", "gross", "tax", "net", "hit")
    }
    status = np.full(shape, STATUS_UNAVAILABLE, dtype=np.uint8)
    for issue_index, decision in enumerate(decisions):
        if not decision.supports:
            continue
        for action_index, action in enumerate(actions):
            rows = _apply_stage2_action(
                action, decision, estimators, adapter_sha256
            )
            settled = [
                settle_direction_support(row.support, row.output, outcomes)
                for row in rows
            ]
            statuses = {str(row["status"]) for row in settled}
            key = (action_index, issue_index)
            if "UNAVAILABLE" in statuses:
                status[key] = STATUS_UNAVAILABLE
                continue
            if "NO_BET" in statuses:
                status[key] = STATUS_NO_BET
                continue
            status[key] = STATUS_ACTIVE
            for name in arrays:
                arrays[name][key] = sum(float(row[name]) for row in settled)
    comparator_net = arrays["net"][fallback_index].copy()
    comparator_stake = arrays["stake"][fallback_index].copy()
    utility = np.full(shape, np.nan, dtype=np.float64)
    utility_active = (
        (status == STATUS_ACTIVE)
        & (arrays["stake"] > 0.0)
        & (status[fallback_index][None, :] == STATUS_ACTIVE)
        & (comparator_stake[None, :] > 0.0)
    )
    candidate_roi = np.divide(
        arrays["net"], arrays["stake"],
        out=np.zeros(shape, dtype=np.float64), where=arrays["stake"] > 0.0,
    )
    comparator_roi = np.divide(
        comparator_net, comparator_stake,
        out=np.zeros_like(comparator_net), where=comparator_stake > 0.0,
    )
    utility[utility_active] = (
        candidate_roi - comparator_roi[None, :]
    )[utility_active]
    store = ConditionalStore(
        action_rows=actions,
        issues=stage1_store.issues,
        supports={},
        status=status,
        stake=arrays["stake"], gross=arrays["gross"], tax=arrays["tax"],
        net=arrays["net"], hit=arrays["hit"],
        conditional_supports={}, fallback_index=fallback_index,
        comparator_net=comparator_net, comparator_stake=comparator_stake,
        utility=utility, utility_active=utility_active,
        target_mode="CONDITIONAL_LIFT",
    )
    return store, decisions


def _stage_feature_projections(stage: str) -> list[dict[str, str]]:
    rows = [
        row for row in read_csv(GATE_A_V2 / "stage_feature_projection.csv")
        if row["stage"] == stage and row["model_input"] == "True"
    ]
    rows.sort(key=lambda row: int(row["feature_ordinal"]))
    return rows


def stage2_feature_rows(
    issues: Sequence[Mapping[str, str]],
    decisions: Sequence[Stage1Decision],
) -> list[dict[str, object]]:
    projections = _stage_feature_projections("STAGE_2_DIRECTION")
    output: list[dict[str, object]] = []
    for issue, decision in zip(issues, decisions, strict=True):
        stage1 = decision.output
        values = [float(value) for value in stage1["candidate_scores"]]
        row: dict[str, object] = {}
        for projection in projections:
            field = projection["projection_field"]
            if projection["source_scope"] == "COMMON_X_I":
                row[field] = issue.get(projection["source_field"], "")
            elif field == "stage1_selected_match_count":
                row[field] = stage1["selected_match_count"]
            elif field == "stage1_support_count":
                row[field] = stage1["support_count"]
            elif field == "stage1_candidate_score_min":
                row[field] = min(values) if values else None
            elif field == "stage1_candidate_score_median":
                row[field] = float(np.median(values)) if values else None
            elif field == "stage1_candidate_score_max":
                row[field] = max(values) if values else None
            elif field == "stage1_selector_family":
                row[field] = stage1["selector_family"]
            elif field == "stage1_source_action_identity":
                row[field] = stage1["source_action_identity"]
            elif field == "stage1_availability":
                row[field] = stage1["availability"]
            elif field == "stage1_fallback_flag":
                row[field] = stage1["fallback_flag"]
            elif field == "stage1_reason_code":
                row[field] = stage1["reason_code"]
            else:
                raise RuntimeError(f"unmapped Stage-2 projection: {field}")
        output.append(row)
    return output


def _conditional_screen(
    store: ConditionalStore,
    train: Sequence[int],
    keep: int,
) -> list[int]:
    rows: list[tuple[float, int, float, str, int]] = []
    index = np.asarray(train, dtype=np.int64)
    for action, identity in enumerate(
        row["interface_action_key"] for row in store.action_rows
    ):
        active = store.utility_active[action, index]
        support = int(np.count_nonzero(active))
        native_stake = float(store.stake[action, index][active].sum())
        if support >= 20 and native_stake > 0.0:
            candidate_roi = float(
                store.net[action, index][active].sum() / native_stake
            )
            if store.target_mode == "CONDITIONAL_LIFT":
                baseline_stake = float(store.comparator_stake[index][active].sum())
                baseline_roi = float(
                    store.comparator_net[index][active].sum() / baseline_stake
                )
                score = candidate_roi - baseline_roi
            elif store.target_mode == "ABSOLUTE_UTILITY":
                score = candidate_roi
            else:
                raise RuntimeError("unknown conditional target mode")
        else:
            score = -math.inf
        rows.append((score, support, native_stake, identity, action))
    rows.sort(key=lambda row: (-row[0], -row[1], row[2], row[3]))
    selected = [row[-1] for row in rows[:keep]]
    if store.fallback_index not in selected:
        selected.append(store.fallback_index)
    return selected


def _conditional_predictions(
    store: ConditionalStore,
    feature_rows: Sequence[Mapping[str, object]],
    projections: Sequence[dict[str, str]],
    model: Mapping[str, str],
    actions: Sequence[int],
    train: Sequence[int],
    query: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    core = _core_module()
    encoder = MixedFeatureEncoder.fit(projections, feature_rows, train)
    train_x = encoder.apply(feature_rows, train)
    query_x = encoder.apply(feature_rows, query)
    train_index = np.asarray(train, dtype=np.int64)
    utility = store.utility[np.ix_(actions, train_index)].T
    active = store.utility_active[np.ix_(actions, train_index)].T
    stake = store.stake[np.ix_(actions, train_index)].T
    parameters = json.loads(model["parameters_json"])
    predicted = core.predict_model(
        model["family"], parameters, train_x, query_x, utility, active,
        encoder.group_columns(), train_weight=stake,
    )
    prior = core.prior_predictions(
        utility, active, len(query), train_weight=stake
    )
    return predicted, prior


def _conditional_choice(
    store: ConditionalStore,
    actions: Sequence[int],
    query: Sequence[int],
    predicted: np.ndarray,
    prior: np.ndarray,
    family: str,
) -> tuple[list[int], list[bool]]:
    query_index = np.asarray(query, dtype=np.int64)
    available = store.utility_active[np.ix_(actions, query_index)].T
    stake = store.stake[np.ix_(actions, query_index)].T
    ids = [store.action_rows[action]["interface_action_key"] for action in actions]
    fallback_local = actions.index(store.fallback_index)
    if family == "PRIOR_ONLY_FIXED":
        chosen: list[int] = []
        fallback: list[bool] = []
        for row_index in range(len(query)):
            eligible = [
                index for index in range(len(actions))
                if available[row_index, index]
                and math.isfinite(float(prior[row_index, index]))
            ]
            if not eligible:
                selected = store.fallback_index
            else:
                eligible.sort(key=lambda index: (
                    -float(prior[row_index, index]),
                    float(stake[row_index, index]), ids[index],
                ))
                selected = actions[eligible[0]]
            chosen.append(selected)
            fallback.append(selected == store.fallback_index)
        return chosen, fallback
    local = _core_module().choose_actions(
        predicted, available, ids, stake, [1] * len(actions), prior,
        fallback_local,
    )
    chosen = [actions[index] for index in local]
    return chosen, [value == store.fallback_index for value in chosen]


def _conditional_validation_key(
    store: ConditionalStore,
    choices: Sequence[int],
    query: Sequence[int],
    model: Mapping[str, str],
) -> tuple[float, float, float, int, str]:
    selected = _choice_flows(store, choices, query)
    baseline = _choice_flows(
        store, [store.fallback_index] * len(query), query
    )
    selected_stake = sum(row["stake"] for row in selected)
    baseline_stake = sum(row["stake"] for row in baseline)
    selected_roi = (
        sum(row["net"] for row in selected) / selected_stake
        if selected_stake else -math.inf
    )
    baseline_roi = (
        sum(row["net"] for row in baseline) / baseline_stake
        if baseline_stake else -math.inf
    )
    lift = selected_roi - baseline_roi
    holding = _core_module().holding_metrics(
        selected, reference_capital=1_000_000.0
    )
    return (
        -lift, float(holding["max_drawdown_yuan"]), selected_stake,
        int(model["complexity_rank"]), model["stage_model_id"],
    )


def build_honest_stage2_path(
    store: ConditionalStore,
    decisions: Sequence[Stage1Decision],
) -> StagePath:
    stage = "STAGE_2_DIRECTION"
    models = [
        row for row in read_csv(GATE_A_V2 / "stage_model_grid.csv")
        if row["stage"] == stage
    ]
    if len(models) != 30:
        raise RuntimeError("#193 Stage-2 model grid drift")
    projections = _stage_feature_projections(stage)
    feature_rows = stage2_feature_rows(store.issues, decisions)
    choices = np.full(len(store.issues), store.fallback_index, dtype=np.int32)
    fallback_flags = np.ones(len(store.issues), dtype=bool)
    model_by_issue = ["INSUFFICIENT_HISTORY_ALLOW_ALL_FALLBACK"] * len(store.issues)
    model_receipts: list[dict[str, object]] = []
    screen_receipts: list[dict[str, object]] = []
    years = np.asarray([int(row["year"]) for row in store.issues])
    for test_year in range(2021, 2026):
        inner_train = np.flatnonzero(years < test_year - 1).tolist()
        validation = np.flatnonzero(years == test_year - 1).tolist()
        outer_train = np.flatnonzero(years < test_year).tolist()
        outer_test = np.flatnonzero(years == test_year).tolist()
        inner_actions = _conditional_screen(store, inner_train, 64)
        eligible_models = models
        if len(inner_train) < 60 or len({store.issues[i]["year"] for i in inner_train}) < 2:
            eligible_models = [
                row for row in models if row["family"] == "PRIOR_ONLY_FIXED"
            ]
        candidates = []
        for model in eligible_models:
            predicted, prior = _conditional_predictions(
                store, feature_rows, projections, model, inner_actions,
                inner_train, validation,
            )
            selected, _ = _conditional_choice(
                store, inner_actions, validation, predicted, prior,
                model["family"],
            )
            candidates.append(
                (_conditional_validation_key(store, selected, validation, model), model)
            )
        candidates.sort(key=lambda value: value[0])
        selected_model = candidates[0][1]
        outer_actions = _conditional_screen(store, outer_train, 64)
        predicted, prior = _conditional_predictions(
            store, feature_rows, projections, selected_model, outer_actions,
            outer_train, outer_test,
        )
        selected, flags = _conditional_choice(
            store, outer_actions, outer_test, predicted, prior,
            selected_model["family"],
        )
        for issue, action, flag in zip(outer_test, selected, flags, strict=True):
            choices[issue] = action
            fallback_flags[issue] = flag
            model_by_issue[issue] = selected_model["stage_model_id"]
        for phase, actions in (("INNER_TRAIN", inner_actions), ("OUTER_TRAIN", outer_actions)):
            for rank, action in enumerate(actions, 1):
                screen_receipts.append({
                    "outer_fold": f"TEST_{test_year}", "stage": stage,
                    "screen_phase": phase, "rank": rank,
                    "action_identity": store.action_rows[action]["interface_action_key"],
                    "mandatory_fallback": action == store.fallback_index,
                })
        model_receipts.append({
            "outer_fold": f"TEST_{test_year}", "stage": stage,
            "selected_model_id": selected_model["stage_model_id"],
            "selected_family": selected_model["family"],
            "inner_train_issue_count": len(inner_train),
            "inner_validation_issue_count": len(validation),
            "outer_train_issue_count": len(outer_train),
            "outer_test_issue_count": len(outer_test),
            "inner_screen_action_count": len(inner_actions),
            "outer_screen_action_count": len(outer_actions),
            "validation_pre_tax_lift": -candidates[0][0][0],
        })
    return StagePath(
        stage=stage, choices=choices, model_by_issue=model_by_issue,
        fallback_by_issue=fallback_flags, model_receipts=model_receipts,
        screen_receipts=screen_receipts,
    )


def build_stage2_decisions(
    store: ConditionalStore,
    path: StagePath,
    stage1_decisions: Sequence[Stage1Decision],
) -> list[Stage2Decision]:
    estimators = _load_needed_estimators(stage1_decisions)
    adapter_sha256 = hashlib.sha256(
        (GATE_A_V2 / "conditional_chain_adapter.py").read_bytes()
    ).hexdigest()
    output: list[Stage2Decision] = []
    for issue_index, (stage1, action_value) in enumerate(
        zip(stage1_decisions, path.choices, strict=True)
    ):
        action_index = int(action_value)
        action = store.action_rows[action_index]
        supports = _apply_stage2_action(
            action, stage1, estimators, adapter_sha256
        )
        statuses = {str(value.output["status"]) for value in supports}
        if not supports or "UNAVAILABLE" in statuses:
            availability = "UNAVAILABLE"
        elif "NO_BET" in statuses:
            availability = "NO_BET"
        else:
            availability = "ACTIVE"
        payload: dict[str, object] = {
            "contract": "BJ193_STAGE2_DIRECTION_OUTPUT_V2",
            "issue": store.issues[issue_index]["issue"],
            "issue_instance": store.issues[issue_index]["issue_instance"],
            "stage_id": "STAGE_2_DIRECTION",
            "stage_version": "BJ193_THREE_STAGE_INTERFACE_V2",
            "model_id": path.model_by_issue[issue_index],
            "source_action_identity": action["interface_action_key"],
            "availability": availability,
            "abstention_flag": availability != "ACTIVE",
            "fallback_flag": bool(path.fallback_by_issue[issue_index]),
            "reason_code": (
                "ALLOW_ALL_FALLBACK"
                if path.fallback_by_issue[issue_index]
                else "MODEL_CHOICE"
            ),
            "stage1_output_sha256": stage1.output["output_sha256"],
            "stage1_selected_supports": stage1.output["selected_supports"],
            "derived_direction_action_sha256": action.get(
                "derived_interface_identity_sha256", ""
            ),
            "direction_adapter_version": (
                "BJ193_ALLOW_ALL_CONTROL_V1"
                if action_index == store.fallback_index
                else "bj193-conditional-chain-adapter-v4"
            ),
            "direction_adapter_sha256": adapter_sha256,
            "upstream_190_policy_id": action["source_identity"],
            "support_outputs": [value.output for value in supports],
            "support_count": len(supports),
        }
        payload["output_sha256"] = canonical_hash(payload)
        output.append(Stage2Decision(issue_index, action_index, supports, payload))
    return output


STAGE3_WEIGHT_SOURCES = (
    "MODEL_P_CAL", "MARKET_WF_CAL", "BLEND_A25", "BLEND_A50",
    "BLEND_A75", "Q_WEIGHT", "NA",
)
STAGE3_MECHANISM_CODE = {
    "WR_DUPLICATE_STAKE": 0,
    "WOR_DISTINCT": 1,
    "RESIDUAL_SYSTEMATIC": 2,
    "CAPPED_REPEAT": 3,
    "DETERMINISTIC_TOP_MASS": 4,
    "FULL_ENUMERATED": 5,
    "P_MIN_GLOBAL_DELETE": 6,
    "Q_MIN_GLOBAL_DELETE": 7,
}


def _load_stage3_weights(
    stage1_decisions: Sequence[Stage1Decision],
) -> dict[str, dict[str, str]]:
    needed = {
        match_id
        for decision in stage1_decisions
        for support in decision.supports
        for match_id in support.ordered_match_ids
    }
    output: dict[str, dict[str, str]] = {}
    source = GATE_A_V2 / "stage3_complete_match_weight_registry.csv.gz"
    with gzip.open(source, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            match_id = row["match_id"]
            if match_id in needed:
                if match_id in output:
                    raise RuntimeError("duplicate complete Stage-3 match weight")
                output[match_id] = row
    return output


def _stage3_compatibility() -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv(GATE_A_V2 / "stage1_stage3_coverage_registry.csv.gz")
    output = {
        (
            row["stage1_interface_action_key"],
            row["stage3_compatibility_class_key"],
        ): row
        for row in rows
    }
    if len(output) != 17_283:
        raise RuntimeError("Stage1xStage3 compatibility registry drift")
    return output


def _compile_stage3_native() -> ctypes.CDLL:
    source = ROOT / "scripts" / "bj193_chain_allocator.cpp"
    frozen = ROOT / "scripts" / "bj145_fast_alloc.cpp"
    expected = "5f8f5d75dd15758e62dd2a05f7b674cb12824b38ccba35cfee772e8904a8bd93"
    frozen_sha = hashlib.sha256(frozen.read_bytes()).hexdigest()
    gate_a_engine_sha = hashlib.sha256(
        (GATE_A_V2 / "bj145_allocation_engine.py").read_bytes()
    ).hexdigest()
    if gate_a_engine_sha != "5b1ac6631ce22a447d883d514ed73e6795584c89d514e6be7562b2fd91bfa4ce":
        raise RuntimeError("frozen Python allocator drift")
    if frozen_sha != expected:
        raise RuntimeError("accepted native allocator source drift")
    build = ROOT / ".scratch" / "bj193_gate_b_v2"
    build.mkdir(parents=True, exist_ok=True)
    identity = canonical_hash({
        "wrapper": hashlib.sha256(source.read_bytes()).hexdigest(),
        "native": frozen_sha,
    })
    library = build / f"bj193_chain_allocator_{identity[:16]}.so"
    if not library.exists():
        subprocess.run(
            [
                "g++", "-std=c++17", "-O3", "-fPIC", "-shared",
                "-fopenmp", "-I", str(ROOT / "scripts"), str(source),
                "-o", str(library),
            ],
            check=True,
        )
    module = ctypes.CDLL(str(library))
    pd = ctypes.POINTER(ctypes.c_double)
    pi = ctypes.POINTER(ctypes.c_int)
    pb = ctypes.POINTER(ctypes.c_ubyte)
    pc = ctypes.POINTER(ctypes.c_char_p)
    module.bj193_chain_profile_actions.argtypes = [
        pd, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_double,
        pi, pi, pi, pi, pc, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        pb, pd, pd, pd, pd, pd,
    ]
    module.bj193_chain_profile_actions.restype = None
    return module


def _np_pointer(value: np.ndarray, ctype: object) -> object:
    return value.ctypes.data_as(ctypes.POINTER(ctype))


def _truth_and_payout(
    support: Support, outcomes: Mapping[str, Outcome]
) -> tuple[int, float] | None:
    if any(match_id not in outcomes for match_id in support.ordered_match_ids):
        return None
    truth = 0
    for match_id in support.ordered_match_ids:
        truth = truth * 3 + ("3", "1", "0").index(
            outcomes[match_id].result_code
        )
    payout = STAKE_PER_TICKET * PAYOUT_FACTOR * math.prod(
        outcomes[match_id].winning_sp for match_id in support.ordered_match_ids
    )
    return truth, payout


def _original_structural_delete_truth(
    support: Support,
    role_by_match: Mapping[str, Mapping[str, str]],
    truth: int,
) -> tuple[int, int] | None:
    """Exact #167 P/Q control where all seven #137 role rows exist.

    The accepted v2 compatibility registry incorrectly classifies these two
    controls as unit-weight NA actions.  Until PI binds the correction, this
    helper is deliberately unavailable on incomplete #190 supports rather
    than inventing a substitute.
    """
    if any(match_id not in role_by_match for match_id in support.ordered_match_ids):
        return None
    roles = [role_by_match[match_id] for match_id in support.ordered_match_ids]
    model_fields = ("p_model3", "p_model1", "p_model0")
    q_fields = ("q_weight3", "q_weight1", "q_weight0")
    p_leg = min(
        range(7),
        key=lambda leg: (
            min(float(roles[leg][field]) for field in model_fields), leg
        ),
    )
    p_code = min(
        range(3), key=lambda code: (float(roles[p_leg][model_fields[code]]), code)
    )
    q_leg, q_code = min(
        ((leg, code) for leg in range(7) for code in range(3)),
        key=lambda item: (
            float(roles[item[0]][q_fields[item[1]]]), item[0], item[1]
        ),
    )
    digits = []
    value = truth
    for _ in range(7):
        digits.append(value % 3)
        value //= 3
    digits.reverse()
    return int(digits[p_leg] != p_code), int(digits[q_leg] != q_code)


def _stage3_native_action_arrays(
    actions: Sequence[Mapping[str, str]],
    issue: str,
    stage1_output_sha256: str,
    stage2_output_sha256: str,
) -> tuple[
    np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[bytes], np.ndarray
]:
    adapter = _direction_adapter()
    source = np.full(len(actions), -1, dtype=np.int32)
    mechanism = np.zeros(len(actions), dtype=np.int32)
    requested_m = np.zeros(len(actions), dtype=np.int32)
    caps = np.zeros(len(actions), dtype=np.int32)
    signatures: list[bytes] = []
    class_keys: list[str] = []
    for index, action in enumerate(actions):
        parameters = json.loads(action["parameters_json"])
        weight_source = str(parameters["weight_source"])
        source[index] = STAGE3_WEIGHT_SOURCES.index(weight_source)
        mechanism[index] = STAGE3_MECHANISM_CODE[str(parameters["mechanism"])]
        requested_m[index] = int(
            1458 if parameters["M"] == "NA" else parameters["M"]
        )
        caps[index] = int(
            0 if parameters["cap"] == "NA" else parameters["cap"]
        )
        signatures.append(
            adapter.stage3_replay_signature(
                issue=issue,
                stage1_output_sha256=stage1_output_sha256,
                stage2_output_sha256=stage2_output_sha256,
                derived_stage3_action_sha256=parameters[
                    "derived_bet_action_sha256"
                ],
            ).encode()
        )
        class_keys.append(str(parameters["compatibility_class_key"]))
    encoded = (ctypes.c_char_p * len(signatures))(*signatures)
    return source, mechanism, requested_m, caps, signatures, encoded


def _profile_stage3_support(
    native: ctypes.CDLL,
    actions: Sequence[Mapping[str, str]],
    support: DirectionSupport,
    stage1: Stage1Decision,
    stage2: Stage2Decision,
    role_by_match: Mapping[str, Mapping[str, str]],
    outcomes: Mapping[str, Outcome],
    compatibility: Mapping[tuple[str, str], Mapping[str, str]],
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    count = len(actions)
    status = np.full(count, STATUS_UNAVAILABLE, dtype=np.uint8)
    values = {
        name: np.zeros(count, dtype=np.float64)
        for name in ("gross", "stake", "tax", "net", "hit")
    }
    if support.output["status"] == "UNAVAILABLE":
        return status, values
    if support.output["status"] == "NO_BET":
        for action_index, action in enumerate(actions):
            parameters = json.loads(action["parameters_json"])
            row = compatibility[
                (
                    str(stage1.output["source_action_identity"]),
                    str(parameters["compatibility_class_key"]),
                )
            ]
            if row["compatibility_status"] == "COMPATIBLE":
                status[action_index] = STATUS_NO_BET
        return status, values
    truth_payout = _truth_and_payout(support.support, outcomes)
    if truth_payout is None:
        return status, values
    truth, payout = truth_payout
    adapter = _direction_adapter()
    direction_rows = support.output["per_match"]
    weights = np.zeros((len(STAGE3_WEIGHT_SOURCES), FULL_TICKETS), dtype=np.float64)
    vector_available: dict[str, bool] = {}
    for source_index, weight_source in enumerate(STAGE3_WEIGHT_SOURCES):
        combined = adapter.combine_stage2_and_stage3_weights(
            support.support.ordered_match_ids,
            direction_rows,
            role_by_match,
            weight_source,
        )
        if combined["status"] != "ACTIVE":
            vector_available[weight_source] = False
            continue
        vector = adapter.canonical_ticket_weight_vector(
            combined["per_match_weight_3_1_0"]
        )
        weights[source_index] = np.asarray(vector, dtype=np.float64)
        vector_available[weight_source] = True
    structural = _original_structural_delete_truth(
        support.support, role_by_match, truth
    )
    p_allowed, q_allowed = structural if structural is not None else (0, 0)
    source, mechanism, requested_m, caps, _signature_bytes, encoded = (
        _stage3_native_action_arrays(
            actions,
            support.support.issue,
            str(stage1.output["output_sha256"]),
            str(stage2.output["output_sha256"]),
        )
    )
    native_status = np.zeros(count, dtype=np.uint8)
    native.bj193_chain_profile_actions(
        _np_pointer(np.ascontiguousarray(weights), ctypes.c_double),
        len(STAGE3_WEIGHT_SOURCES), FULL_TICKETS, truth, payout,
        _np_pointer(source, ctypes.c_int),
        _np_pointer(mechanism, ctypes.c_int),
        _np_pointer(requested_m, ctypes.c_int),
        _np_pointer(caps, ctypes.c_int),
        encoded, count, p_allowed, 1458, q_allowed, 1458,
        _np_pointer(native_status, ctypes.c_ubyte),
        *(_np_pointer(values[name], ctypes.c_double) for name in (
            "gross", "stake", "tax", "net", "hit"
        )),
    )
    for action_index, action in enumerate(actions):
        parameters = json.loads(action["parameters_json"])
        row = compatibility[
            (
                str(stage1.output["source_action_identity"]),
                str(parameters["compatibility_class_key"]),
            )
        ]
        weight_source = str(parameters["weight_source"])
        mechanism_name = str(parameters["mechanism"])
        if row["compatibility_status"] != "COMPATIBLE":
            continue
        if not vector_available.get(weight_source, False):
            continue
        if mechanism_name in {"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"} and structural is None:
            # Fail closed pending the PI correction requested on #193.
            continue
        status[action_index] = (
            STATUS_ACTIVE if native_status[action_index] else STATUS_NO_BET
        )
    for name in values:
        values[name][status != STATUS_ACTIVE] = 0.0
    return status, values


def build_stage3_store(
    stage1_store: StageStore,
    stage1_decisions: Sequence[Stage1Decision],
    stage2_decisions: Sequence[Stage2Decision],
) -> ConditionalStore:
    actions = load_stage_catalog(3)
    fallback = [
        index for index, row in enumerate(actions)
        if json.loads(row["parameters_json"])["mechanism"] == "FULL_ENUMERATED"
    ]
    if len(fallback) != 1:
        raise RuntimeError("Stage-3 FULL fallback identity drift")
    fallback_index = fallback[0]
    role_by_match = _load_stage3_weights(stage1_decisions)
    outcomes = load_outcomes()
    compatibility = _stage3_compatibility()
    native = _compile_stage3_native()
    shape = (len(actions), len(stage1_decisions))
    arrays = {
        name: np.zeros(shape, dtype=np.float64)
        for name in ("stake", "gross", "tax", "net", "hit")
    }
    status = np.full(shape, STATUS_UNAVAILABLE, dtype=np.uint8)
    for issue_index, (stage1, stage2) in enumerate(
        zip(stage1_decisions, stage2_decisions, strict=True)
    ):
        if not stage2.supports:
            continue
        support_results = [
            _profile_stage3_support(
                native, actions, support, stage1, stage2, role_by_match,
                outcomes, compatibility,
            )
            for support in stage2.supports
        ]
        for action_index in range(len(actions)):
            states = [result[0][action_index] for result in support_results]
            key = (action_index, issue_index)
            if any(value == STATUS_UNAVAILABLE for value in states):
                status[key] = STATUS_UNAVAILABLE
            elif any(value == STATUS_NO_BET for value in states):
                status[key] = STATUS_NO_BET
            else:
                status[key] = STATUS_ACTIVE
                for name in arrays:
                    arrays[name][key] = sum(
                        result[1][name][action_index] for result in support_results
                    )
    comparator_net = arrays["net"][fallback_index].copy()
    comparator_stake = arrays["stake"][fallback_index].copy()
    utility_active = (status == STATUS_ACTIVE) & (arrays["stake"] > 0.0)
    utility = np.divide(
        arrays["net"], arrays["stake"],
        out=np.full(shape, np.nan), where=utility_active,
    )
    return ConditionalStore(
        action_rows=actions, issues=stage1_store.issues, supports={},
        status=status, stake=arrays["stake"], gross=arrays["gross"],
        tax=arrays["tax"], net=arrays["net"], hit=arrays["hit"],
        conditional_supports={}, fallback_index=fallback_index,
        comparator_net=comparator_net, comparator_stake=comparator_stake,
        utility=utility, utility_active=utility_active,
        target_mode="ABSOLUTE_UTILITY",
    )


def stage3_feature_rows(
    issues: Sequence[Mapping[str, str]],
    stage1_decisions: Sequence[Stage1Decision],
    stage2_decisions: Sequence[Stage2Decision],
) -> list[dict[str, object]]:
    projections = _stage_feature_projections("STAGE_3_BET")
    base_stage2 = stage2_feature_rows(issues, stage1_decisions)
    output: list[dict[str, object]] = []
    for issue, stage1, stage2, inherited in zip(
        issues, stage1_decisions, stage2_decisions, base_stage2, strict=True
    ):
        all_matches = [
            row
            for support in stage2.supports
            if support.output["status"] == "ACTIVE"
            for row in support.output["per_match"]
        ]
        strongest = (
            max(
                all_matches,
                key=lambda row: (
                    float(row["magnitude"]),
                    -int(row["match_idx"]),
                    -int(str(row["match_id"])),
                ),
            )
            if all_matches else None
        )
        support_outputs = [support.output for support in stage2.supports]
        omitted = sorted({
            str(value["omitted_code"])
            for value in support_outputs if value.get("omitted_code") not in (None, "")
        })
        delete_legs = sorted({
            int(value["delete_leg_index_zero_based"])
            for value in support_outputs
            if value.get("delete_leg_index_zero_based") is not None
        })
        estimator_sources = sorted({
            str(row["estimator_source"]) for row in all_matches
        })
        row: dict[str, object] = {}
        for projection in projections:
            field = projection["projection_field"]
            if field in inherited:
                row[field] = inherited[field]
            elif projection["source_scope"] == "COMMON_X_I":
                row[field] = issue.get(projection["source_field"], "")
            elif field == "stage2_direction_status":
                row[field] = stage2.output["availability"]
            elif field == "stage2_strongest_magnitude":
                row[field] = float(strongest["magnitude"]) if strongest else None
            elif field == "stage2_strongest_abs_z":
                row[field] = float(strongest["abs_z"]) if strongest else None
            elif field == "stage2_omitted_code":
                row[field] = "|".join(omitted) if omitted else ""
            elif field == "stage2_delete_leg_index":
                row[field] = delete_legs[0] if len(delete_legs) == 1 else None
            elif field == "stage2_positive_ticket_support":
                row[field] = sum(
                    int(value.get("ticket_support_size", 0))
                    for value in support_outputs
                )
            elif field == "stage2_estimator_source_set":
                row[field] = estimator_sources
            elif field == "stage2_protection_count":
                row[field] = sum(
                    int(bool(match.get("protection_flag")))
                    for match in all_matches
                )
            elif field == "stage2_fallback_flag":
                row[field] = stage2.output["fallback_flag"]
            elif field == "stage2_reason_code":
                row[field] = stage2.output["reason_code"]
            else:
                raise RuntimeError(f"unmapped Stage-3 projection: {field}")
        output.append(row)
    return output


def build_honest_stage3_path(
    store: ConditionalStore,
    stage1_decisions: Sequence[Stage1Decision],
    stage2_decisions: Sequence[Stage2Decision],
) -> StagePath:
    stage = "STAGE_3_BET"
    models = [
        row for row in read_csv(GATE_A_V2 / "stage_model_grid.csv")
        if row["stage"] == stage
    ]
    if len(models) != 30:
        raise RuntimeError("#193 Stage-3 model grid drift")
    projections = _stage_feature_projections(stage)
    feature_rows = stage3_feature_rows(
        store.issues, stage1_decisions, stage2_decisions
    )
    choices = np.full(len(store.issues), store.fallback_index, dtype=np.int32)
    fallback_flags = np.ones(len(store.issues), dtype=bool)
    model_by_issue = ["INSUFFICIENT_HISTORY_FULL_FALLBACK"] * len(store.issues)
    model_receipts: list[dict[str, object]] = []
    screen_receipts: list[dict[str, object]] = []
    years = np.asarray([int(row["year"]) for row in store.issues])
    for test_year in range(2021, 2026):
        inner_train = np.flatnonzero(years < test_year - 1).tolist()
        validation = np.flatnonzero(years == test_year - 1).tolist()
        outer_train = np.flatnonzero(years < test_year).tolist()
        outer_test = np.flatnonzero(years == test_year).tolist()
        inner_actions = _conditional_screen(store, inner_train, 64)
        eligible_models = models
        if len(inner_train) < 60 or len({store.issues[i]["year"] for i in inner_train}) < 2:
            eligible_models = [
                row for row in models if row["family"] == "PRIOR_ONLY_FIXED"
            ]
        candidates = []
        for model in eligible_models:
            predicted, prior = _conditional_predictions(
                store, feature_rows, projections, model, inner_actions,
                inner_train, validation,
            )
            selected, _ = _conditional_choice(
                store, inner_actions, validation, predicted, prior,
                model["family"],
            )
            candidates.append(
                (_conditional_validation_key(store, selected, validation, model), model)
            )
        candidates.sort(key=lambda value: value[0])
        selected_model = candidates[0][1]
        outer_actions = _conditional_screen(store, outer_train, 64)
        predicted, prior = _conditional_predictions(
            store, feature_rows, projections, selected_model, outer_actions,
            outer_train, outer_test,
        )
        selected, flags = _conditional_choice(
            store, outer_actions, outer_test, predicted, prior,
            selected_model["family"],
        )
        for issue, action, flag in zip(outer_test, selected, flags, strict=True):
            choices[issue] = action
            fallback_flags[issue] = flag
            model_by_issue[issue] = selected_model["stage_model_id"]
        for phase, actions in (("INNER_TRAIN", inner_actions), ("OUTER_TRAIN", outer_actions)):
            for rank, action in enumerate(actions, 1):
                screen_receipts.append({
                    "outer_fold": f"TEST_{test_year}", "stage": stage,
                    "screen_phase": phase, "rank": rank,
                    "action_identity": store.action_rows[action]["interface_action_key"],
                    "mandatory_fallback": action == store.fallback_index,
                })
        model_receipts.append({
            "outer_fold": f"TEST_{test_year}", "stage": stage,
            "selected_model_id": selected_model["stage_model_id"],
            "selected_family": selected_model["family"],
            "inner_train_issue_count": len(inner_train),
            "inner_validation_issue_count": len(validation),
            "outer_train_issue_count": len(outer_train),
            "outer_test_issue_count": len(outer_test),
            "inner_screen_action_count": len(inner_actions),
            "outer_screen_action_count": len(outer_actions),
            "validation_pre_tax_lift": -candidates[0][0][0],
        })
    return StagePath(
        stage=stage, choices=choices, model_by_issue=model_by_issue,
        fallback_by_issue=fallback_flags, model_receipts=model_receipts,
        screen_receipts=screen_receipts,
    )
