"""Issue #206 fixed-N7 ticket generation and conservative policy learning.

The module consumes only the promoted #205 control lane for controlling decisions.
The retrospective experimental lane is available to one explicitly non-promoted
ablation.  Generic estimation and sampling use scikit-learn, SciPy and NumPy;
custom code is limited to fixed-N7 identity, Beijing payout settlement, exact
integer ticket accounting and evidence packaging.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import itertools
import json
import math
from pathlib import Path
import shutil
from typing import Any, Iterable

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import bootstrap
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

OUTCOMES = ("3", "1", "0")
N = 7
STAKE_YUAN = 2.0
PAYOUT_FACTOR = 0.65
SEED = 206001
K_GRID = (16, 32, 64)
K_MAX = max(K_GRID)
VERSION = "bj206-fixed-n7-ticket-policy-v1"
LABEL_CUTOFF_YEAR = 2025
CONTROL_POLICY = "MARKET_Q_WOR"
LEARNED_POLICIES = ("LOGIT_Q_WOR", "MLP_Q_WOR", "MLP_EXPERIMENTAL_Q_WOR")
SCIENTIFIC_LOCK = Path("requirements.txt")

SAFE_COLUMNS = (
    "control_probability",
    "control_probability_source",
    "control_probability_source_grade",
    "control_probability_promoted",
    "predicted_final_sp",
    "predicted_final_sp_source",
    "sp_seed_std",
    "control_expected_gross",
    "control_expected_pre_tax_net",
    "control_displayed_scalar_utility",
)
BASE_FEATURES = (
    "control_probability_3",
    "control_probability_1",
    "control_probability_0",
    "predicted_final_sp_3",
    "predicted_final_sp_1",
    "predicted_final_sp_0",
    "sp_seed_std_3",
    "sp_seed_std_1",
    "sp_seed_std_0",
    "expected_sp",
    "market_entropy",
    "sp_cv",
)
EXPERIMENTAL_FEATURES = (
    "experimental_probability_3",
    "experimental_probability_1",
    "experimental_probability_0",
    "experimental_model_market_residual_3",
    "experimental_model_market_residual_1",
    "experimental_model_market_residual_0",
)


class TicketPolicyError(RuntimeError):
    """Contract or evidence generation failure."""


@dataclass(frozen=True)
class Inputs:
    value_matrix: Path
    schema: Path
    output: Path


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _environment() -> dict[str, str]:
    names = (
        "numpy",
        "pandas",
        "pyarrow",
        "scipy",
        "matplotlib",
        "scikit-learn",
        "joblib",
        "nbformat",
        "nbclient",
    )
    return {name: importlib.metadata.version(name) for name in names}


def ticket_identity(match_indices: Iterable[int], outcomes: Iterable[str]) -> str:
    pairs = sorted(zip(match_indices, outcomes, strict=True))
    if len(pairs) != N or len({match for match, _ in pairs}) != N:
        raise TicketPolicyError("ticket must contain exactly seven distinct matches")
    if any(code not in OUTCOMES for _, code in pairs):
        raise TicketPolicyError("ticket contains an invalid outcome code")
    return "|".join(f"{match}:{code}" for match, code in pairs)


def load_match_table(value_matrix: Path, schema_path: Path) -> pd.DataFrame:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    safe = schema.get("safe_control_interface", {})
    if (
        safe.get("probability") != "control_probability"
        or safe.get("probability_source") != "MARKET_ONLY"
        or safe.get("source_grade") != "FROZEN_SAFE_BASELINE"
        or safe.get("promoted") is not True
        or safe.get("joint_scorer") != "MARKET_INDEPENDENCE"
    ):
        raise TicketPolicyError("#205 safe-control interface is not the accepted baseline")
    frame = pd.read_parquet(value_matrix)
    required = {
        "issue",
        "year",
        "split",
        "match_idx",
        "outcome_code",
        *SAFE_COLUMNS,
        "experimental_probability",
        "experimental_probability_source_grade",
        "experimental_probability_promoted",
        "experimental_model_market_residual",
        "realized_outcome",
        "official_final_sp_label",
    }
    if not required.issubset(frame.columns):
        raise TicketPolicyError(
            f"#205 value matrix missing columns {sorted(required.difference(frame.columns))}"
        )
    key = ["issue", "match_idx", "outcome_code"]
    if frame.empty or frame.duplicated(key).any():
        raise TicketPolicyError("#205 value matrix is empty or has duplicate cells")
    if set(frame.outcome_code.astype(str)) != set(OUTCOMES):
        raise TicketPolicyError("outcome axis differs from 3/1/0")
    if set(frame.control_probability_source.astype(str)) != {"MARKET_ONLY"}:
        raise TicketPolicyError("non-market row entered the control lane")
    if set(frame.control_probability_source_grade.astype(str)) != {
        "FROZEN_SAFE_BASELINE"
    } or not frame.control_probability_promoted.astype(bool).all():
        raise TicketPolicyError("control provenance or promotion flag mismatch")
    if set(frame.experimental_probability_source_grade.astype(str)) != {
        "RETROSPECTIVE_PROXY_METHOD_CORRECTION"
    } or frame.experimental_probability_promoted.astype(bool).any():
        raise TicketPolicyError("experimental lane provenance/promotion mismatch")

    index = ["issue", "year", "split", "match_idx"]
    scalar = frame[index].drop_duplicates().sort_values(index).reset_index(drop=True)
    for source, prefix in (
        ("control_probability", "control_probability"),
        ("experimental_probability", "experimental_probability"),
        ("predicted_final_sp", "predicted_final_sp"),
        ("sp_seed_std", "sp_seed_std"),
        ("experimental_model_market_residual", "experimental_model_market_residual"),
        ("official_final_sp_label", "official_final_sp_label"),
    ):
        wide = frame.pivot(index=index, columns="outcome_code", values=source)
        wide = wide.reindex(columns=OUTCOMES)
        wide.columns = [f"{prefix}_{code}" for code in OUTCOMES]
        scalar = scalar.merge(wide.reset_index(), on=index, validate="one_to_one")
    realized = frame.loc[frame.realized_outcome.astype(bool), index + ["outcome_code"]]
    if realized.duplicated(index).any():
        raise TicketPolicyError("more than one realized outcome per match")
    scalar = scalar.merge(
        realized.rename(columns={"outcome_code": "realized_code"}),
        on=index,
        how="left",
        validate="one_to_one",
    )
    control = scalar[[f"control_probability_{c}" for c in OUTCOMES]].to_numpy(float)
    experimental = scalar[
        [f"experimental_probability_{c}" for c in OUTCOMES]
    ].to_numpy(float)
    control_valid = (
        np.isfinite(control).all(axis=1)
        & (control > 0).all(axis=1)
        & np.isclose(control.sum(axis=1), 1.0, atol=1e-10, rtol=0.0)
    )
    experimental_valid = (
        np.isfinite(experimental).all(axis=1)
        & (experimental > 0).all(axis=1)
        & np.isclose(experimental.sum(axis=1), 1.0, atol=1e-10, rtol=0.0)
    )
    explicitly_unsupported = np.isnan(control).all(axis=1) & np.isnan(experimental).all(axis=1)
    if not np.all((control_valid & experimental_valid) | explicitly_unsupported):
        raise TicketPolicyError("supported probability triplet is malformed")
    scalar = scalar.loc[control_valid & experimental_valid].copy().reset_index(drop=True)
    control = scalar[[f"control_probability_{c}" for c in OUTCOMES]].to_numpy(float)
    experimental = scalar[
        [f"experimental_probability_{c}" for c in OUTCOMES]
    ].to_numpy(float)
    sp = scalar[[f"predicted_final_sp_{c}" for c in OUTCOMES]].to_numpy(float)
    if not (np.isfinite(sp).all() and (sp > 0).all()):
        raise TicketPolicyError("predicted SP must be finite and positive")
    scalar["expected_sp"] = np.sum(control * sp, axis=1)
    scalar["market_entropy"] = -np.sum(control * np.log(control), axis=1)
    scalar["sp_cv"] = np.std(sp, axis=1) / np.mean(sp, axis=1)
    # Locked 2025+ labels remain physically present upstream but are unavailable here.
    locked = scalar.year.astype(int).ge(LABEL_CUTOFF_YEAR)
    scalar.loc[locked, "realized_code"] = pd.NA
    for code in OUTCOMES:
        scalar.loc[locked, f"official_final_sp_label_{code}"] = np.nan
    return scalar


def _features(matches: pd.DataFrame, *, experimental: bool) -> list[str]:
    return list(BASE_FEATURES + (EXPERIMENTAL_FEATURES if experimental else ()))


def _new_model(kind: str, *, experimental: bool, alpha: float = 0.001) -> Pipeline:
    features = _features(pd.DataFrame(), experimental=experimental)
    del features  # documents that feature shape is fixed by the caller
    if kind == "LOGIT":
        estimator = LogisticRegression(
            C=1.0,
            max_iter=500,
            random_state=SEED,
        )
    elif kind == "MLP":
        estimator = MLPClassifier(
            hidden_layer_sizes=(16,),
            activation="tanh",
            solver="adam",
            alpha=alpha,
            batch_size=256,
            learning_rate_init=0.003,
            max_iter=160,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=12,
            random_state=SEED,
        )
    else:
        raise TicketPolicyError(f"unknown model {kind}")
    return Pipeline([("scale", StandardScaler()), ("model", estimator)])


def _ordered_probability(model: Pipeline, x: pd.DataFrame) -> np.ndarray:
    raw = model.predict_proba(x)
    classes = [str(value) for value in model.named_steps["model"].classes_]
    order = [classes.index(code) for code in OUTCOMES]
    values = np.clip(raw[:, order], 1e-9, 1.0)
    return values / values.sum(axis=1, keepdims=True)


def fit_chronological_models(matches: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    labeled = matches.loc[
        matches.year.astype(int).lt(LABEL_CUTOFF_YEAR) & matches.realized_code.notna()
    ].copy()
    if set(labeled.split) != {"CV_2021", "CV_2022", "CV_2023"}:
        raise TicketPolicyError("expected chronological CV_2021/2022/2023 label folds")
    outputs: list[pd.DataFrame] = []
    selection_rows: list[dict[str, Any]] = []
    final_models: dict[str, Pipeline] = {}
    final_ranges: dict[str, dict[str, list[float]]] = {}

    specifications = (
        ("LOGIT", False, (0.001,)),
        ("MLP", False, (0.0003, 0.003)),
        ("MLP_EXPERIMENTAL", True, (0.0003, 0.003)),
    )
    for name, experimental, alphas in specifications:
        model_outputs: list[pd.DataFrame] = []
        features = _features(matches, experimental=experimental)
        train = labeled.loc[labeled.split.eq("CV_2021")]
        validation = labeled.loc[labeled.split.eq("CV_2022")]
        scores: list[tuple[float, float]] = []
        for alpha in alphas:
            model = _new_model(
                "MLP" if name.startswith("MLP") else "LOGIT",
                experimental=experimental,
                alpha=alpha,
            )
            model.fit(train[features], train.realized_code.astype(str))
            probability = _ordered_probability(model, validation[features])
            label_order = sorted(OUTCOMES)
            score = float(
                log_loss(
                    validation.realized_code.astype(str),
                    probability[:, [OUTCOMES.index(code) for code in label_order]],
                    labels=label_order,
                )
            )
            scores.append((score, alpha))
            selection_rows.append(
                {
                    "model": name,
                    "alpha": alpha,
                    "validation_log_loss": score,
                    "seed": SEED,
                    "selection_fold": "CV_2022",
                }
            )
        alpha = min(scores)[1]
        for inference_split, fit_splits in (
            ("CV_2022", ("CV_2021",)),
            ("CV_2023", ("CV_2021", "CV_2022")),
            ("LOCKED_TEST", ("CV_2021", "CV_2022", "CV_2023")),
        ):
            fit = labeled.loc[labeled.split.isin(fit_splits)]
            infer = matches.loc[matches.split.eq(inference_split)].copy()
            model = _new_model(
                "MLP" if name.startswith("MLP") else "LOGIT",
                experimental=experimental,
                alpha=alpha,
            )
            model.fit(fit[features], fit.realized_code.astype(str))
            probability = _ordered_probability(model, infer[features])
            for position, code in enumerate(OUTCOMES):
                infer[f"{name.lower()}_probability_{code}"] = probability[:, position]
            scaled = model.named_steps["scale"].transform(infer[features])
            infer[f"{name.lower()}_ood"] = np.max(np.abs(scaled), axis=1) > 6.0
            model_outputs.append(
                infer[
                    ["issue", "match_idx", "split"]
                    + [f"{name.lower()}_probability_{c}" for c in OUTCOMES]
                    + [f"{name.lower()}_ood"]
                ]
            )
            if inference_split == "LOCKED_TEST":
                final_models[name] = model
                final_ranges[name] = {
                    "feature_names": features,
                    "training_min": fit[features].min().astype(float).tolist(),
                    "training_max": fit[features].max().astype(float).tolist(),
                }
        outputs.append(pd.concat(model_outputs, ignore_index=True))
    predictions = matches.loc[matches.split.isin(["CV_2022", "CV_2023", "LOCKED_TEST"])].copy()
    for output in outputs:
        prediction_columns = [
            column
            for column in output.columns
            if column not in {"issue", "match_idx", "split"}
        ]
        if any(column in predictions.columns for column in prediction_columns):
            continue
        predictions = predictions.merge(
            output, on=["issue", "match_idx", "split"], how="left", validate="one_to_one"
        )
    return predictions, {
        "selection": pd.DataFrame(selection_rows),
        "models": final_models,
        "ranges": final_ranges,
    }


def _probability_matrix(matches: pd.DataFrame, prefix: str) -> np.ndarray:
    return matches[[f"{prefix}_{code}" for code in OUTCOMES]].to_numpy(float)


def temperature_probabilities(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    """Package-vectorized categorical temperature rule used as a simple control."""
    if temperature <= 0.0:
        raise TicketPolicyError("temperature must be positive")
    values = np.asarray(probabilities, dtype=float) ** (1.0 / temperature)
    return values / values.sum(axis=1, keepdims=True)


def _ticket_record(
    issue_matches: pd.DataFrame,
    positions: np.ndarray,
    outcome_indices: np.ndarray,
    *,
    probability_prefix: str,
) -> dict[str, Any]:
    chosen = issue_matches.iloc[positions]
    match_indices = chosen.match_idx.to_numpy(int)
    codes = np.asarray(OUTCOMES, dtype=object)[outcome_indices].astype(str)
    order = np.argsort(match_indices)
    match_indices = match_indices[order]
    codes = codes[order]
    outcome_indices = outcome_indices[order]
    chosen = chosen.iloc[order]
    probabilities = _probability_matrix(chosen, probability_prefix)[
        np.arange(N), outcome_indices
    ]
    predicted_sp = _probability_matrix(chosen, "predicted_final_sp")[
        np.arange(N), outcome_indices
    ]
    identity = ticket_identity(match_indices.tolist(), codes.tolist())
    expected_roi = float(PAYOUT_FACTOR * np.prod(probabilities) * np.prod(predicted_sp) - 1.0)
    realized_hit: bool | None
    realized_gross: float | None
    if chosen.realized_code.notna().all():
        realized_hit = bool(np.all(chosen.realized_code.astype(str).to_numpy() == codes))
        if realized_hit:
            official = _probability_matrix(chosen, "official_final_sp_label")[
                np.arange(N), outcome_indices
            ]
            realized_gross = float(STAKE_YUAN * PAYOUT_FACTOR * np.prod(official))
        else:
            realized_gross = 0.0
    else:
        realized_hit = None
        realized_gross = None
    return {
        "ticket_identity": identity,
        "match_indices": ",".join(str(value) for value in match_indices),
        "outcome_codes": "".join(codes),
        "source_probability_product": float(np.prod(probabilities)),
        "predicted_sp_product": float(np.prod(predicted_sp)),
        "expected_pre_tax_roi": expected_roi,
        "requested_stake_yuan": STAKE_YUAN,
        "realized_hit": realized_hit,
        "realized_gross_yuan": realized_gross,
    }


def weighted_tickets(
    issue_matches: pd.DataFrame,
    *,
    probability_prefix: str,
    count: int,
    seed: int,
    distinct: bool,
) -> list[dict[str, Any]]:
    """Use NumPy's maintained weighted sampler; enforce only N7 domain constraints."""
    if len(issue_matches) < N:
        return []
    rng = np.random.default_rng(seed)
    probabilities = _probability_matrix(issue_matches, probability_prefix)
    sp = _probability_matrix(issue_matches, "predicted_final_sp")
    q = probabilities * sp
    match_weight = q.sum(axis=1)
    match_weight = match_weight / match_weight.sum()
    outcome_weight = q / q.sum(axis=1, keepdims=True)
    tickets: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempts = 0
    limit = max(10_000, count * 200)
    while len(tickets) < count and attempts < limit:
        positions = rng.choice(len(issue_matches), size=N, replace=False, p=match_weight)
        outcome_indices = np.asarray(
            [rng.choice(3, p=outcome_weight[position]) for position in positions],
            dtype=int,
        )
        record = _ticket_record(
            issue_matches,
            positions,
            outcome_indices,
            probability_prefix=probability_prefix,
        )
        attempts += 1
        if distinct and record["ticket_identity"] in seen:
            continue
        seen.add(record["ticket_identity"])
        tickets.append(record)
    if len(tickets) != count:
        raise TicketPolicyError("bounded weighted sampler could not satisfy requested K")
    return tickets


def top_mass_tickets(
    issue_matches: pd.DataFrame,
    *,
    probability_prefix: str,
    count: int,
) -> list[dict[str, Any]]:
    """Deterministic bounded top-mass search over the best eight issue matches."""
    if len(issue_matches) < N:
        return []
    probabilities = _probability_matrix(issue_matches, probability_prefix)
    sp = _probability_matrix(issue_matches, "predicted_final_sp")
    q = probabilities * sp
    top = np.argsort(-q.sum(axis=1), kind="stable")[: min(8, len(issue_matches))]
    scored: dict[str, tuple[float, dict[str, Any]]] = {}
    for positions_tuple in itertools.combinations(top.tolist(), N):
        positions = np.asarray(positions_tuple, dtype=int)
        local = q[positions]
        order = np.argsort(-local, axis=1, kind="stable")
        variants = [order[:, 0].copy()]
        for leg in range(N):
            for alternative in (1, 2):
                variant = order[:, 0].copy()
                variant[leg] = order[leg, alternative]
                variants.append(variant)
        for outcome_indices in variants:
            record = _ticket_record(
                issue_matches,
                positions,
                outcome_indices,
                probability_prefix=probability_prefix,
            )
            score = float(np.prod(local[np.arange(N), outcome_indices]))
            previous = scored.get(record["ticket_identity"])
            if previous is None or score > previous[0]:
                scored[record["ticket_identity"]] = (score, record)
    selected = sorted(scored.values(), key=lambda item: (-item[0], item[1]["ticket_identity"]))
    if len(selected) < count:
        raise TicketPolicyError("bounded top-mass universe has fewer tickets than K")
    return [record for _, record in selected[:count]]


def residual_tickets(
    issue_matches: pd.DataFrame,
    *,
    count: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Hamilton integer allocation over a package-sampled 32-ticket base sleeve."""
    base_count = min(32, count)
    base = weighted_tickets(
        issue_matches,
        probability_prefix="control_probability",
        count=base_count,
        seed=seed,
        distinct=True,
    )
    weights = np.asarray(
        [max(1e-15, (row["expected_pre_tax_roi"] + 1.0)) for row in base], dtype=float
    )
    quota = count * weights / weights.sum()
    allocation = np.floor(quota).astype(int)
    remainder = count - int(allocation.sum())
    if remainder:
        priority = np.argsort(-(quota - allocation), kind="stable")[:remainder]
        allocation[priority] += 1
    return [row.copy() for row, copies in zip(base, allocation, strict=True) for _ in range(copies)]


def overlap_control_tickets(
    issue_matches: pd.DataFrame,
    *,
    count: int,
    seed: int,
    mode: str,
) -> list[dict[str, Any]]:
    """Greedy capped/penalized overlap controls on a fixed weighted proposal pool."""
    proposals = weighted_tickets(
        issue_matches,
        probability_prefix="control_probability",
        count=count * 4,
        seed=seed,
        distinct=True,
    )
    match_sets = [set(str(row["match_indices"]).split(",")) for row in proposals]
    selected: list[int] = []
    remaining = set(range(len(proposals)))
    while len(selected) < count:
        candidates: list[tuple[float, str, int]] = []
        for index in remaining:
            overlap = (
                max(len(match_sets[index] & match_sets[prior]) / N for prior in selected)
                if selected
                else 0.0
            )
            expected_mass = max(1e-15, float(proposals[index]["expected_pre_tax_roi"]) + 1.0)
            if mode == "CAP":
                if overlap > 5.0 / 7.0:
                    continue
                score = math.log(expected_mass)
            elif mode == "PENALTY":
                score = math.log(expected_mass) - 0.5 * overlap
            else:
                raise TicketPolicyError(f"unknown overlap control {mode}")
            candidates.append((score, str(proposals[index]["ticket_identity"]), index))
        if not candidates:
            raise TicketPolicyError(f"{mode} overlap control cannot satisfy K={count}")
        chosen = max(candidates, key=lambda item: (item[0], item[1]))[2]
        selected.append(chosen)
        remaining.remove(chosen)
    return [proposals[index] for index in selected]


def best_full_roster(issue_matches: pd.DataFrame) -> pd.DataFrame | None:
    """Accepted BEST_FULL selector: LOWP20 anchor, ESP290 companions, GM300."""
    if len(issue_matches) < N:
        return None
    p = _probability_matrix(issue_matches, "control_probability")
    candidates = issue_matches[["match_idx", "expected_sp"]].copy()
    candidates["p_min"] = p.min(axis=1)
    anchors = candidates.loc[candidates.p_min.le(0.20)].sort_values(
        ["p_min", "expected_sp", "match_idx"], ascending=[True, False, True]
    )
    for anchor_index in anchors.index:
        companions = candidates.loc[
            (candidates.index != anchor_index) & candidates.expected_sp.ge(2.90)
        ].sort_values(["expected_sp", "match_idx"], ascending=[False, True])
        if len(companions) < 6:
            continue
        selected_index = [anchor_index, *companions.index[:6].tolist()]
        selected = issue_matches.loc[selected_index].sort_values("match_idx")
        gm = float(np.exp(np.log(selected.expected_sp.to_numpy(float)).mean()))
        if gm >= 3.0:
            return selected
    return None


def legacy_full_metric(issue_matches: pd.DataFrame) -> dict[str, Any]:
    roster = best_full_roster(issue_matches)
    if roster is None:
        return {"status": "NO_BET_BEST_FULL", "tickets": 0, "stake_yuan": 0.0}
    p = _probability_matrix(roster, "control_probability")
    sp_pred = _probability_matrix(roster, "predicted_final_sp")
    expected_gross = STAKE_YUAN * PAYOUT_FACTOR * float(np.prod(np.sum(p * sp_pred, axis=1)))
    result: dict[str, Any] = {
        "status": "BEST_FULL_FULL",
        "tickets": 3**N,
        "stake_yuan": STAKE_YUAN * 3**N,
        "expected_roi": expected_gross / (STAKE_YUAN * 3**N) - 1.0,
        "match_indices": ",".join(str(value) for value in roster.match_idx.astype(int)),
    }
    if roster.realized_code.notna().all():
        realized_indices = np.asarray([OUTCOMES.index(str(code)) for code in roster.realized_code])
        official = _probability_matrix(roster, "official_final_sp_label")
        realized_gross = STAKE_YUAN * PAYOUT_FACTOR * float(
            np.prod(official[np.arange(N), realized_indices])
        )
        result["realized_gross_yuan"] = realized_gross
        result["realized_roi"] = realized_gross / result["stake_yuan"] - 1.0
    else:
        result["realized_gross_yuan"] = np.nan
        result["realized_roi"] = np.nan
    return result


def _seed(issue: Any, policy: str) -> int:
    payload = f"{SEED}|{issue}|{policy}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def generate_policy_ledger(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = matches.copy()
    market = _probability_matrix(matches, "control_probability")
    for name, temperature in (("market_temp075", 0.75), ("market_temp125", 1.25)):
        transformed = temperature_probabilities(market, temperature)
        for position, code in enumerate(OUTCOMES):
            matches[f"{name}_probability_{code}"] = transformed[:, position]
    rows: list[dict[str, Any]] = []
    full_rows: list[dict[str, Any]] = []
    specifications = (
        (CONTROL_POLICY, "control_probability", "WOR"),
        ("MARKET_TEMP075_Q_WOR", "market_temp075_probability", "WOR"),
        ("MARKET_TEMP125_Q_WOR", "market_temp125_probability", "WOR"),
        ("MARKET_Q_WR", "control_probability", "WR"),
        ("MARKET_TOP_MASS", "control_probability", "TOP"),
        ("MARKET_RESIDUAL", "control_probability", "RESIDUAL"),
        ("MARKET_OVERLAP_CAP_Q_WOR", "control_probability", "CAP"),
        ("MARKET_OVERLAP_PENALIZED_Q_WOR", "control_probability", "PENALTY"),
        ("LOGIT_Q_WOR", "logit_probability", "WOR"),
        ("MLP_Q_WOR", "mlp_probability", "WOR"),
        ("MLP_EXPERIMENTAL_Q_WOR", "mlp_experimental_probability", "WOR"),
    )
    for (issue, split), group in matches.groupby(["issue", "split"], sort=True):
        group = group.sort_values("match_idx").reset_index(drop=True)
        full = legacy_full_metric(group)
        full.update({"issue": issue, "year": int(group.year.iloc[0]), "split": split})
        full_rows.append(full)
        for policy, prefix, mechanism in specifications:
            if mechanism == "TOP":
                tickets = top_mass_tickets(group, probability_prefix=prefix, count=K_MAX)
            elif mechanism == "RESIDUAL":
                tickets = []
            elif mechanism in {"CAP", "PENALTY"}:
                tickets = overlap_control_tickets(
                    group,
                    count=K_MAX,
                    seed=_seed(issue, policy),
                    mode=mechanism,
                )
            else:
                tickets = weighted_tickets(
                    group,
                    probability_prefix=prefix,
                    count=K_MAX,
                    seed=_seed(issue, policy),
                    distinct=mechanism == "WOR",
                )
            for k in K_GRID:
                selected_tickets = (
                    residual_tickets(group, count=k, seed=_seed(issue, f"{policy}|{k}"))
                    if mechanism == "RESIDUAL"
                    else tickets[:k]
                )
                for rank, record in enumerate(selected_tickets, start=1):
                    row = record.copy()
                    row.update(
                        {
                            "issue": issue,
                            "year": int(group.year.iloc[0]),
                            "split": split,
                            "policy": policy,
                            "mechanism": mechanism,
                            "K": k,
                            "ticket_rank": rank,
                        }
                    )
                    rows.append(row)
    ledger = pd.DataFrame(rows)
    if ledger.empty:
        raise TicketPolicyError("candidate generation produced no tickets")
    return ledger, pd.DataFrame(full_rows)


def _issue_policy_metrics(ledger: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keys = ["issue", "year", "split", "policy", "K"]
    for key, group in ledger.groupby(keys, sort=True):
        issue, year, split, policy, k = key
        counts = group.ticket_identity.value_counts()
        exposures: dict[str, int] = {}
        for value in group.match_indices:
            for match in str(value).split(","):
                exposures[match] = exposures.get(match, 0) + 1
        pair_denominator = math.comb(len(group), 2) if len(group) > 1 else 1
        pair_intersection = sum(math.comb(value, 2) for value in exposures.values())
        row: dict[str, Any] = {
            "issue": issue,
            "year": int(year),
            "split": split,
            "policy": policy,
            "K": int(k),
            "tickets": len(group),
            "stake_yuan": float(group.requested_stake_yuan.sum()),
            "distinct_tickets": int(len(counts)),
            "repeat_tickets": int(len(group) - len(counts)),
            "ticket_coverage": float(len(counts) / len(group)),
            "unique_matches": len(exposures),
            "mean_pair_match_overlap_share": float(pair_intersection / pair_denominator / N),
            "ticket_stake_hhi": float(np.square(counts.to_numpy(float) / len(group)).sum()),
            "expected_roi": float(group.expected_pre_tax_roi.mean()),
        }
        if group.realized_gross_yuan.notna().all():
            gross = float(group.realized_gross_yuan.sum())
            row.update(
                {
                    "realized_gross_yuan": gross,
                    "realized_roi": gross / row["stake_yuan"] - 1.0,
                    "hits": int(group.realized_hit.astype(bool).sum()),
                    "hit_coverage": float(group.realized_hit.astype(bool).any()),
                }
            )
        else:
            row.update(
                {
                    "realized_gross_yuan": np.nan,
                    "realized_roi": np.nan,
                    "hits": np.nan,
                    "hit_coverage": np.nan,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _turnover_vs_control(ledger: pd.DataFrame, policy: str, k: int, split: str) -> float:
    values: list[float] = []
    subset = ledger.loc[ledger.split.eq(split) & ledger.K.eq(k)]
    for issue, group in subset.groupby("issue"):
        control = group.loc[group.policy.eq(CONTROL_POLICY)].ticket_identity.value_counts()
        candidate = group.loc[group.policy.eq(policy)].ticket_identity.value_counts()
        identities = control.index.union(candidate.index)
        c = control.reindex(identities, fill_value=0).to_numpy(float) / k
        p = candidate.reindex(identities, fill_value=0).to_numpy(float) / k
        values.append(float(0.5 * np.abs(c - p).sum()))
    return float(np.mean(values)) if values else np.nan


def summarize_surface(ledger: pd.DataFrame, issue_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (split, policy, k), group in issue_metrics.groupby(["split", "policy", "K"], sort=True):
        row: dict[str, Any] = {
            "split": split,
            "policy": policy,
            "K": int(k),
            "issues": int(group.issue.nunique()),
            "tickets": int(group.tickets.sum()),
            "stake_yuan": float(group.stake_yuan.sum()),
            "expected_roi": float(np.average(group.expected_roi, weights=group.stake_yuan)),
            "ticket_coverage": float(group.ticket_coverage.mean()),
            "mean_unique_matches": float(group.unique_matches.mean()),
            "mean_pair_match_overlap_share": float(group.mean_pair_match_overlap_share.mean()),
            "mean_ticket_stake_hhi": float(group.ticket_stake_hhi.mean()),
            "repeat_tickets": int(group.repeat_tickets.sum()),
            "turnover_vs_control": _turnover_vs_control(ledger, policy, int(k), str(split)),
        }
        settled = group.realized_roi.notna()
        if settled.all():
            gross = float(group.realized_gross_yuan.sum())
            stake = float(group.stake_yuan.sum())
            issue_gross = group.realized_gross_yuan.to_numpy(float)
            total_gross = issue_gross.sum()
            row.update(
                {
                    "realized_roi": gross / stake - 1.0,
                    "hits": int(group.hits.sum()),
                    "issue_hit_coverage": float(group.hit_coverage.mean()),
                    "gross_hhi": float(np.square(issue_gross / total_gross).sum())
                    if total_gross > 0
                    else np.nan,
                }
            )
        else:
            row.update(
                {"realized_roi": np.nan, "hits": np.nan, "issue_hit_coverage": np.nan, "gross_hhi": np.nan}
            )
        rows.append(row)
    surface = pd.DataFrame(rows)
    control = surface.loc[surface.policy.eq(CONTROL_POLICY), ["split", "K", "expected_roi", "realized_roi", "ticket_coverage"]].rename(
        columns={
            "expected_roi": "control_expected_roi",
            "realized_roi": "control_realized_roi",
            "ticket_coverage": "control_ticket_coverage",
        }
    )
    surface = surface.merge(control, on=["split", "K"], validate="many_to_one")
    surface["matched_lift_expected_roi_vs_control"] = surface.expected_roi - surface.control_expected_roi
    surface["matched_lift_realized_roi_vs_control"] = surface.realized_roi - surface.control_realized_roi
    surface["matched_lift_ticket_coverage_vs_control"] = surface.ticket_coverage - surface.control_ticket_coverage
    return surface


def _select_policy(surface: pd.DataFrame, issue_metrics: pd.DataFrame) -> dict[str, Any]:
    validation = surface.loc[
        surface.split.eq("CV_2022") & surface.policy.isin(LEARNED_POLICIES)
    ].copy()
    validation["negative_regret"] = np.maximum(
        0.0, validation.control_realized_roi - validation.realized_roi
    )
    validation["penalized_utility"] = validation.realized_roi - validation.negative_regret
    selected = validation.sort_values(
        ["penalized_utility", "expected_roi", "policy", "K"],
        ascending=[False, False, True, True],
    ).iloc[0]
    policy = str(selected.policy)
    k = int(selected.K)
    matched = issue_metrics.loc[
        issue_metrics.split.eq("CV_2022")
        & issue_metrics.K.eq(k)
        & issue_metrics.policy.isin([CONTROL_POLICY, policy])
    ].pivot(index="issue", columns="policy", values="realized_roi")
    difference = (matched[policy] - matched[CONTROL_POLICY]).to_numpy(float)
    if len(difference) < 2 or np.allclose(difference, difference[0]):
        low = high = float(difference.mean())
    else:
        interval = bootstrap(
            (difference,),
            np.mean,
            n_resamples=999,
            confidence_level=0.95,
            method="basic",
            rng=np.random.default_rng(SEED),
        ).confidence_interval
        low, high = float(interval.low), float(interval.high)
    enabled = bool(
        low > 0.0 and float(selected.matched_lift_expected_roi_vs_control) > 0.0
    )
    return {
        "selected_policy": policy,
        "selected_K": k,
        "selection_split": "CV_2022",
        "selection_seed": SEED,
        "penalized_utility": float(selected.penalized_utility),
        "validation_realized_lift": float(selected.matched_lift_realized_roi_vs_control),
        "validation_expected_lift": float(selected.matched_lift_expected_roi_vs_control),
        "validation_lift_ci95": [low, high],
        "learned_gate_enabled": enabled,
        "global_fallback_reason": "NONE" if enabled else "VALIDATION_LCB_NOT_POSITIVE",
    }


def build_fallback_mixed(
    ledger: pd.DataFrame,
    matches: pd.DataFrame,
    selection: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    policy = selection["selected_policy"]
    k = int(selection["selected_K"])
    prefix = policy.removesuffix("_Q_WOR").lower()
    ood_column = f"{prefix}_ood"
    rows: list[pd.DataFrame] = []
    trace: list[dict[str, Any]] = []
    for (issue, split), issue_matches in matches.groupby(["issue", "split"], sort=True):
        candidate = ledger.loc[
            ledger.issue.eq(issue)
            & ledger.split.eq(split)
            & ledger.policy.eq(policy)
            & ledger.K.eq(k)
        ].copy()
        control = ledger.loc[
            ledger.issue.eq(issue)
            & ledger.split.eq(split)
            & ledger.policy.eq(CONTROL_POLICY)
            & ledger.K.eq(k)
        ].copy()
        candidate_expected = float(candidate.expected_pre_tax_roi.mean())
        control_expected = float(control.expected_pre_tax_roi.mean())
        ood_share = float(issue_matches[ood_column].astype(bool).mean())
        reason = "NONE"
        use_learned = bool(selection["learned_gate_enabled"])
        if not use_learned:
            reason = str(selection["global_fallback_reason"])
        elif len(candidate) != k:
            use_learned = False
            reason = "INFEASIBLE_K"
        elif ood_share > 0.20:
            use_learned = False
            reason = "OOD_SHARE_GT_20PCT"
        elif candidate_expected <= control_expected:
            use_learned = False
            reason = "EXPECTED_UTILITY_NOT_ABOVE_CONTROL"
        chosen = candidate if use_learned else control
        chosen = chosen.copy()
        chosen["policy"] = "FALLBACK_MIXED"
        chosen["source_policy"] = policy if use_learned else CONTROL_POLICY
        chosen["fallback_applied"] = not use_learned
        chosen["fallback_reason"] = reason
        rows.append(chosen)
        trace.append(
            {
                "issue": issue,
                "split": split,
                "selected_policy": policy,
                "requested_K": k,
                "candidate_expected_roi": candidate_expected,
                "control_expected_roi": control_expected,
                "ood_share": ood_share,
                "fallback_applied": not use_learned,
                "fallback_reason": reason,
                "ticket_identity_sha256": hashlib.sha256(
                    "\n".join(chosen.ticket_identity).encode()
                ).hexdigest(),
            }
        )
    return pd.concat(rows, ignore_index=True), pd.DataFrame(trace)


def _plots(surface: pd.DataFrame, output: Path) -> None:
    test = surface.loc[surface.split.eq("CV_2023")]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for policy, group in test.groupby("policy"):
        axes[0].plot(group.K, group.realized_roi, marker="o", label=policy)
        axes[1].plot(group.K, group.ticket_coverage, marker="o", label=policy)
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set(title="Held-out realized ROI by K", xlabel="K tickets", ylabel="ROI")
    axes[1].set(title="Distinct-ticket coverage by K", xlabel="K tickets", ylabel="coverage")
    axes[0].legend(fontsize=7)
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output / "parameter_performance.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for policy, group in test.groupby("policy"):
        axes[0].plot(group.K, group.mean_pair_match_overlap_share, marker="o", label=policy)
        axes[1].plot(group.K, group.mean_ticket_stake_hhi, marker="o", label=policy)
    axes[0].set(title="Match overlap", xlabel="K tickets", ylabel="mean pair overlap / 7")
    axes[1].set(title="Ticket stake concentration", xlabel="K tickets", ylabel="HHI")
    axes[0].legend(fontsize=7)
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output / "overlap_concentration.png", dpi=160)
    plt.close(fig)


def _decision(selection: dict[str, Any], surface: pd.DataFrame, trace: pd.DataFrame) -> dict[str, Any]:
    k = int(selection["selected_K"])
    test = surface.loc[surface.split.eq("CV_2023") & surface.K.eq(k)]
    control = test.loc[test.policy.eq(CONTROL_POLICY)].iloc[0]
    fallback = test.loc[test.policy.eq("FALLBACK_MIXED")].iloc[0]
    utility_lift = float(fallback.realized_roi - control.realized_roi)
    coverage_lift = float(fallback.ticket_coverage - control.ticket_coverage)
    no_worse = utility_lift >= -1e-12
    gain = utility_lift > 0.0 or coverage_lift > 0.0
    advance = bool(no_worse and gain)
    locked_trace = trace.loc[trace.split.eq("LOCKED_TEST")]
    return {
        "version": VERSION,
        **selection,
        "evaluation_split": "CV_2023",
        "label_boundary": "year < 2025 only; 2025-04+ labels are nulled before inference",
        "fallback_mixed_test_realized_roi": float(fallback.realized_roi),
        "matched_control_test_realized_roi": float(control.realized_roi),
        "fallback_mixed_test_realized_lift": utility_lift,
        "fallback_mixed_test_ticket_coverage_lift": coverage_lift,
        "fallback_mixed_no_worse": no_worse,
        "preregistered_gain_present": gain,
        "locked_fallback_issues": int(locked_trace.fallback_applied.sum()),
        "locked_issues": int(len(locked_trace)),
        "disposition": "ADVANCE_FALLBACK_MIXED" if advance else "INHERIT_MATCHED_MARKET_CONTROL",
        "inherited_policy": None if advance else f"{CONTROL_POLICY}_K{k}",
        "stage_3_handoff_only": True,
        "final_capital_authority": False,
    }


def verify(output: Path) -> dict[str, Any]:
    expected = json.loads((output / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.relative_to(output).as_posix(): _digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if expected != actual:
        raise TicketPolicyError("manifest mismatch")
    decision = json.loads((output / "decision.json").read_text(encoding="utf-8"))
    ledger = pd.read_parquet(output / "ticket_ledger.parquet")
    sizes = ledger.groupby(["issue", "split", "policy", "K"]).size()
    expected_sizes = sizes.index.get_level_values("K").to_numpy(int)
    if not np.array_equal(sizes.to_numpy(int), expected_sizes):
        raise TicketPolicyError("ticket count differs from K")
    for identity in ledger.ticket_identity:
        parts = str(identity).split("|")
        if len(parts) != N or len({part.split(":", 1)[0] for part in parts}) != N:
            raise TicketPolicyError("invalid ticket identity in artifact")
    locked = ledger.year.astype(int).ge(LABEL_CUTOFF_YEAR)
    if ledger.loc[locked, "realized_gross_yuan"].notna().any():
        raise TicketPolicyError("2025+ settlement label entered ticket artifact")
    trace = pd.read_csv(output / "fallback_trace.csv")
    fallback = ledger.loc[ledger.policy.eq("FALLBACK_MIXED") & ledger.fallback_applied.astype(bool)]
    control = ledger.loc[ledger.policy.eq(CONTROL_POLICY)]
    for (issue, split), group in fallback.groupby(["issue", "split"]):
        k = int(group.K.iloc[0])
        expected_ids = control.loc[
            control.issue.eq(issue) & control.split.eq(split) & control.K.eq(k),
            "ticket_identity",
        ].tolist()
        if group.ticket_identity.tolist() != expected_ids:
            raise TicketPolicyError("fallback tickets do not exactly copy matched control")
    return {
        "status": "PASS",
        "files": len(actual),
        "tickets": len(ledger),
        "issues": int(ledger.issue.nunique()),
        "fallback_trace_rows": len(trace),
        "manifest_sha256": _digest(output / "SHA256SUMS.json"),
        "disposition": decision["disposition"],
    }


def run(inputs: Inputs) -> dict[str, Any]:
    output = inputs.output.resolve()
    if output.exists():
        raise TicketPolicyError(f"immutable output already exists: {output}")
    stage = output.with_name(f".{output.name}.stage")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        matches = load_match_table(inputs.value_matrix, inputs.schema)
        predictions, model_info = fit_chronological_models(matches)
        ledger, full = generate_policy_ledger(predictions)
        issue_metrics = _issue_policy_metrics(ledger)
        surface = summarize_surface(ledger, issue_metrics)
        selection = _select_policy(surface, issue_metrics)
        fallback, trace = build_fallback_mixed(ledger, predictions, selection)
        ledger = pd.concat([ledger, fallback], ignore_index=True)
        issue_metrics = _issue_policy_metrics(ledger)
        surface = summarize_surface(ledger, issue_metrics)
        decision = _decision(selection, surface, trace)

        ledger.to_parquet(stage / "ticket_ledger.parquet", index=False, compression="zstd")
        issue_metrics.to_parquet(stage / "issue_policy_metrics.parquet", index=False, compression="zstd")
        surface.to_csv(stage / "policy_surface.csv", index=False, float_format="%.12g")
        full.to_csv(stage / "best_full_full_control.csv", index=False, float_format="%.12g")
        trace.to_csv(stage / "fallback_trace.csv", index=False, float_format="%.12g")
        model_info["selection"].to_csv(stage / "model_selection.csv", index=False, float_format="%.12g")
        joblib.dump(model_info["models"], stage / "models.joblib", compress=3)
        _write_json(stage / "feature_support.json", model_info["ranges"])
        _write_json(stage / "decision.json", decision)
        _write_json(
            stage / "policy_contract.json",
            {
                "version": VERSION,
                "n": N,
                "stake_yuan_per_ticket": STAKE_YUAN,
                "payout_factor": PAYOUT_FACTOR,
                "k_grid": list(K_GRID),
                "ticket_identity": "seven sorted distinct match_idx:outcome_code pairs",
                "action_universe": "each ticket independently selects seven distinct matches from the full issue pool",
                "repeat_semantics": "duplicate identity rows are explicit repeat-stake actions",
                "control": CONTROL_POLICY,
                "legacy_control": "BEST_FULL_FULL (2,187 identities on accepted selector)",
                "temperature_controls": [0.75, 1.25],
                "overlap_controls": {
                    "cap": "maximum pair match-overlap share 5/7",
                    "penalty": "0.5 times maximum prior match-overlap share",
                },
                "learned_models": list(LEARNED_POLICIES),
                "experimental_boundary": "MLP_EXPERIMENTAL_Q_WOR is ablation-only and never a promoted probability source",
                "gate": "validation issue-bootstrap lower bound > 0, expected lift > 0, OOD share <= 20%, feasible exact K",
                "stage_3_output": "requested tickets and ¥2 stake only; no bankroll or final capital authority",
            },
        )
        representative = trace.sort_values(["split", "issue"]).iloc[0]
        _write_json(
            stage / "inference_trace.json",
            {
                **representative.to_dict(),
                "safe_probability_source": "MARKET_ONLY",
                "safe_probability_source_grade": "FROZEN_SAFE_BASELINE",
                "joint_scorer": "MARKET_INDEPENDENCE",
                "formula": "0.65 * product(source_probability) * product(predicted_pre_event_sp) - 1",
                "label_fields_used_for_inference": [],
            },
        )
        _write_json(
            stage / "provenance.json",
            {
                "source_value_matrix": str(inputs.value_matrix),
                "source_value_matrix_sha256": _digest(inputs.value_matrix),
                "source_schema": str(inputs.schema),
                "source_schema_sha256": _digest(inputs.schema),
                "source_contract": "bj205-joint-n7-value-matrix-v2 safe-control interface",
                "environment": _environment(),
                "scientific_environment_lock": SCIENTIFIC_LOCK.as_posix(),
                "scientific_environment_lock_sha256": _digest(SCIENTIFIC_LOCK.resolve()),
                "seed": SEED,
                "determinism": "scikit-learn and NumPy fixed random_state; CPU",
                "artifact_format": "CSV/JSON/Parquet/joblib/PNG",
                "replay": "PYTHONPATH=src .venv/bin/python scripts/run_bj206_ticket_policy.py run --output results/issue-206",
            },
        )
        _plots(surface, stage)
        report = f"""# Issue #206 decision report — fixed-N7 ticket policy learning

## Decision

`{decision['disposition']}`. The prior-only CV_2022 selection chose `{selection['selected_policy']}` with K={selection['selected_K']}. Its issue-block bootstrap 95% realized-ROI lift interval versus the matched `{CONTROL_POLICY}` was [{selection['validation_lift_ci95'][0]:+.4f}, {selection['validation_lift_ci95'][1]:+.4f}]. The deterministic learned gate was {'enabled' if selection['learned_gate_enabled'] else 'disabled'}, so unsupported issues route byte-exactly to the matched market control.

On held-out CV_2023 (the last label-eligible fold), fallback-mixed realized ROI was {decision['fallback_mixed_test_realized_roi']:+.4f} versus {decision['matched_control_test_realized_roi']:+.4f}; matched lift was {decision['fallback_mixed_test_realized_lift']:+.4f}. Distinct-ticket coverage lift was {decision['fallback_mixed_test_ticket_coverage_lift']:+.4f}. The policy therefore {'meets' if decision['disposition'] == 'ADVANCE_FALLBACK_MIXED' else 'does not meet'} the preregistered no-worse-plus-gain rule.

## Absolute and matched evidence

`policy_surface.csv` reports absolute expected/realized ROI, issue hit coverage, ticket coverage, match overlap, ticket-stake HHI, gross HHI, repeats and turnover. It also reports matched lifts against the same issue/K/stake `{CONTROL_POLICY}`. `BEST_FULL_FULL` is reported separately at 2,187 tickets (¥4,374) and is never presented as capital-matched to smaller K.

## Controls and ablations

- Safe controls: accepted `BEST_FULL_FULL` and full-pool `MARKET_Q_WOR` on the promoted #205 market/SP interface.
- Simple controls: market temperature 0.75/1.25, market WR, deterministic bounded top mass and Hamilton residual integer allocation.
- Risk-preference controls: the same market proposal family with a tunable 5/7 overlap cap or 0.5 overlap penalty, always compared at matched K/stake; neither is treated as a universal rule.
- Learned controls: package-backed multinomial logistic regression and scikit-learn MLP. The residual-channel MLP is explicitly retrospective, non-promoted and ablation-only.
- Every ticket selects its own seven-match subset from the complete issue pool. There is no inherited first-seven roster.

## Failure regimes and risks

Sparse seven-leg hits make realized utility noisy; CV_2022 selection is separated from held-out CV_2023 evaluation. The OOD gate uses standardized feature support and falls back above 20% issue-level OOD. 2025/2026 label and official-SP fields are nulled before inference, so locked rows provide requested tickets only. Top-mass search is intentionally bounded to the eight highest issue match weights; it is a control, not proof of global combinatorial optimality. `joblib` artifacts are version-bound to the frozen environment.

## Stage-3 handoff

`ticket_ledger.parquet` preserves ticket identity, selected match subset, outcomes, source probability product, predicted-SP product, expected utility, repeat rows, fallback reason and requested ¥2 stake. It grants no Stage-4 bankroll or final-capital authority.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Exact N=7 and per-ticket independent subset | `policy_contract.json`, verifier, ticket ledger | PASS |
| K/WR/WOR/repeat/overlap and fallback trace | `policy_surface.csv`, `fallback_trace.csv` | PASS |
| Absolute plus matched same-stake lift | `policy_surface.csv` | PASS |
| Chronology; no 2025-04+ label read | fold models, nulled locked labels, verifier/tests | PASS |
| Simple/package baseline before neural | logistic/market controls then sklearn MLP | PASS |
| Fallback-mixed no worse plus preregistered gain | `decision.json` | {'PASS' if decision['disposition'] == 'ADVANCE_FALLBACK_MIXED' else 'FAIL — inherit matched market control'} |
| Notebook/code/artifact layers | issue notebook, `src/ticket_policy`, this package | PASS |

Decision input: {'advance the fallback-mixed Stage-3 request policy' if decision['disposition'] == 'ADVANCE_FALLBACK_MIXED' else 'inherit the matched market-weighted control at the selected K'}; retain BEST_FULL/FULL as the unequal-capital absolute control. Known risks: sparse payouts, bounded top-mass search, historical support shift and version-bound model serialization. Explicit review request: independently replay the notebook/package; mutate all 2025+ labels; verify exact ticket constraints, matched stake, control-copy fallback bytes, model chronology, overlap/repeat accounting and the conservative disposition. No merge, issue closure, betting or capital sizing is requested.
"""
        (stage / "DECISION_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
        (stage / "README.md").write_text(
            "# Issue #206 evidence package\n\n"
            "Replay: `PYTHONPATH=src .venv/bin/python scripts/run_bj206_ticket_policy.py run --output <new-directory>`.\n\n"
            "Verify: `PYTHONPATH=src .venv/bin/python scripts/run_bj206_ticket_policy.py verify --output results/issue-206`.\n\n"
            "Notebook: `PYTHONPATH=src .venv/bin/python scripts/execute_bj206_notebook.py --kernel python3`.\n\n"
            "This is a Stage-3 requested-ticket/¥2-stake handoff only; it has no bankroll or final-capital authority.\n",
            encoding="utf-8",
            newline="\n",
        )
        payloads = {
            path.relative_to(stage).as_posix(): _digest(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file() and path.name != "SHA256SUMS.json"
        }
        _write_json(stage / "SHA256SUMS.json", payloads)
        output.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(output)
        verified = verify(output)
        return {**verified, "output": str(output), "decision": decision}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
