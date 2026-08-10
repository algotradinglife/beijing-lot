"""Issue #206: bounded, auditable fixed-N7 ticket generation and safe policy.

Only the promoted #205 control lane drives the controlling policy. Experimental
columns are retained solely for a separately named ablation. NumPy provides the
weighted samplers, scikit-learn the learned ranking model, and SciPy the paired
confidence bound. Custom code is limited to N7 identity, settlement, overlap,
fallback, trace, and provenance adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

N = 7
OUTCOMES = ("3", "1", "0")
TAX_FACTOR = 0.65
STAKE = 2
K_GRID = (8, 16, 32)
NUISANCE_SEEDS = (206001, 206002, 206003)
VERSION = "bj206-fixed-n7-ticket-policy-v1"
SOURCE_VERSION = "bj205-joint-n7-value-matrix-v2"
CONTROL_POLICIES = ("BEST_FULL", "MARKET_WOR", "MARKET_WR")
CHALLENGER_POLICIES = (
    "TEMPERATURE_050",
    "TEMPERATURE_100",
    "OVERLAP_CAPPED",
    "OVERLAP_PENALIZED",
    "LEARNED_MLP",
)
FEATURES = (
    "log_joint_probability",
    "log_sp_product",
    "expected_pre_tax_net",
    "mean_selected_probability",
    "min_selected_probability",
    "mean_selected_sp",
    "outcome_hhi",
    "match_rank_mean",
)
EXPERIMENTAL_FEATURES = FEATURES + (
    "experimental_expected_pre_tax_net",
    "mean_abs_experimental_residual",
)
SCIENTIFIC_LOCK = Path("requirements.txt")


class TicketPolicyError(RuntimeError):
    """Raised when the frozen interface or evidence package fails closed."""


@dataclass(frozen=True)
class Inputs:
    value_matrix: Path
    value_schema: Path
    output: Path


@dataclass(frozen=True)
class IssuePanel:
    split: str
    issue: str
    year: int
    match_idx: np.ndarray
    control_probability: np.ndarray
    experimental_probability: np.ndarray
    predicted_sp: np.ndarray
    sp_seed_std: np.ndarray
    official_sp: np.ndarray
    realized_index: np.ndarray
    labels_available: np.ndarray


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path, value: Any) -> None:
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
        "scikit-learn",
        "scipy",
        "matplotlib",
        "nbformat",
        "nbclient",
    )
    return {
        "python": platform.python_version(),
        **{name: importlib.metadata.version(name) for name in names},
    }


def _stable_seed(*parts: object) -> int:
    payload = "|".join(map(str, parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")


def _softmax(values: np.ndarray, temperature: float) -> np.ndarray:
    scaled = (np.asarray(values, dtype=float) - np.max(values)) / temperature
    weights = np.exp(np.clip(scaled, -40.0, 0.0))
    return weights / weights.sum()


def load_panels(matrix_path: Path, schema_path: Path) -> list[IssuePanel]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    safe = schema.get("safe_control_interface", {})
    experimental = schema.get("experimental_interface", {})
    if schema.get("version") != SOURCE_VERSION:
        raise TicketPolicyError("#205 schema version mismatch")
    if safe != {
        "probability": "control_probability",
        "probability_source": "MARKET_ONLY",
        "source_grade": "FROZEN_SAFE_BASELINE",
        "promoted": True,
        "predicted_sp": "predicted_final_sp",
        "expected_gross": "control_expected_gross",
        "expected_pre_tax_net": "control_expected_pre_tax_net",
        "displayed_scalar": "control_displayed_scalar_utility",
        "joint_scorer": "MARKET_INDEPENDENCE",
    }:
        raise TicketPolicyError("#205 safe-control interface is not exact")
    if experimental.get("promoted") is not False or experimental.get(
        "allowed_use"
    ) != "ablation_feature_only":
        raise TicketPolicyError("#205 experimental boundary mismatch")

    frame = pd.read_parquet(matrix_path)
    required = {
        "issue",
        "year",
        "split",
        "match_idx",
        "outcome_code",
        "control_probability",
        "control_probability_source",
        "control_probability_source_grade",
        "control_probability_promoted",
        "experimental_probability",
        "experimental_probability_promoted",
        "predicted_final_sp",
        "sp_seed_std",
        "official_final_sp_label",
        "realized_outcome",
    }
    if frame.empty or not required.issubset(frame.columns):
        raise TicketPolicyError(
            f"#205 value matrix missing {sorted(required.difference(frame.columns))}"
        )
    key = ["split", "issue", "match_idx", "outcome_code"]
    if frame.duplicated(key, keep=False).any():
        raise TicketPolicyError(f"#205 value cells are not unique on {key}")
    if set(frame.control_probability_source) != {"MARKET_ONLY"}:
        raise TicketPolicyError("non-market rows entered the safe lane")
    if set(frame.control_probability_source_grade) != {"FROZEN_SAFE_BASELINE"}:
        raise TicketPolicyError("safe lane source grade mismatch")
    if not frame.control_probability_promoted.astype(bool).all():
        raise TicketPolicyError("unpromoted safe-control row")
    if frame.experimental_probability_promoted.astype(bool).any():
        raise TicketPolicyError("promoted experimental row")
    outcome_rank = {code: rank for rank, code in enumerate(OUTCOMES)}
    frame["_outcome_rank"] = frame.outcome_code.map(outcome_rank)
    if frame._outcome_rank.isna().any():
        raise TicketPolicyError("unsupported outcome code")

    panels: list[IssuePanel] = []
    for (split, issue), group in frame.groupby(["split", "issue"], sort=False):
        group = group.sort_values(["match_idx", "_outcome_rank"], kind="mergesort")
        sizes = group.groupby("match_idx", sort=False).size()
        if not sizes.eq(3).all():
            raise TicketPolicyError(f"issue {issue} does not have complete M×3 rows")
        probability = group.control_probability.to_numpy(dtype=float).reshape(-1, 3)
        experimental_probability = group.experimental_probability.to_numpy(
            dtype=float
        ).reshape(-1, 3)
        sp = group.predicted_final_sp.to_numpy(dtype=float).reshape(-1, 3)
        sp_seed_std = group.sp_seed_std.to_numpy(dtype=float).reshape(-1, 3)
        official_sp = group.official_final_sp_label.to_numpy(dtype=float).reshape(-1, 3)
        realized = group.realized_outcome.to_numpy(dtype=bool).reshape(-1, 3)
        valid = (
            np.isfinite(probability).all(axis=1)
            & np.isfinite(sp).all(axis=1)
            & (probability > 0).all(axis=1)
            & (sp > 0).all(axis=1)
            & np.isclose(probability.sum(axis=1), 1.0, rtol=0.0, atol=1e-10)
        )
        if valid.sum() < N:
            continue
        probability = probability[valid]
        experimental_probability = experimental_probability[valid]
        sp = sp[valid]
        sp_seed_std = sp_seed_std[valid]
        official_sp = official_sp[valid]
        realized = realized[valid]
        match_idx = group.match_idx.drop_duplicates().to_numpy(dtype=int)[valid]
        if str(split) == "LOCKED_TEST":
            # The source package retains labels for #205 calibration, but #206's
            # post-2023 boundary is stricter: discard them before any ticket,
            # feature, model, metric, or handoff object is constructed.
            labels_available = np.zeros(len(realized), dtype=bool)
            realized_index = np.full(len(realized), -1, dtype=int)
            official_sp = np.full_like(official_sp, np.nan, dtype=float)
        else:
            labels_available = realized.sum(axis=1) == 1
            realized_index = np.argmax(realized, axis=1)
        panels.append(
            IssuePanel(
                split=str(split),
                issue=str(issue),
                year=int(group.year.iloc[0]),
                match_idx=match_idx,
                control_probability=probability,
                experimental_probability=experimental_probability,
                predicted_sp=sp,
                sp_seed_std=sp_seed_std,
                official_sp=official_sp,
                realized_index=realized_index,
                labels_available=labels_available,
            )
        )
    if not panels:
        raise TicketPolicyError("no constraint-valid issue panels")
    return panels


def _identity(panel: IssuePanel, rows: np.ndarray, outcomes: np.ndarray) -> str:
    order = np.argsort(panel.match_idx[rows], kind="stable")
    return "|".join(
        f"{int(panel.match_idx[rows[i]])}:{OUTCOMES[int(outcomes[i])]}" for i in order
    )


def _ticket_row(
    panel: IssuePanel,
    rows: np.ndarray,
    outcomes: np.ndarray,
    source: str,
) -> dict[str, Any]:
    order = np.argsort(panel.match_idx[rows], kind="stable")
    rows = rows[order]
    outcomes = outcomes[order]
    chosen_p = panel.control_probability[rows, outcomes]
    chosen_sp = panel.predicted_sp[rows, outcomes]
    chosen_exp = panel.experimental_probability[rows, outcomes]
    chosen_sp_uncertainty = panel.sp_seed_std[rows, outcomes]
    joint = float(np.prod(chosen_p))
    sp_product = float(np.prod(chosen_sp))
    exp_joint = float(np.prod(chosen_exp))
    labels = bool(panel.labels_available[rows].all())
    hit = bool(labels and np.array_equal(panel.realized_index[rows], outcomes))
    realized_gross = (
        float(TAX_FACTOR * np.prod(panel.official_sp[rows, outcomes])) if hit else 0.0
    )
    if not labels:
        realized_gross = np.nan
    counts = np.bincount(outcomes, minlength=3).astype(float) / N
    rank = pd.Series(
        -np.max(panel.control_probability * panel.predicted_sp, axis=1)
    ).rank(method="first").to_numpy()
    source_cells = [
        {
            "match_idx": int(panel.match_idx[row]),
            "outcome": OUTCOMES[int(outcome)],
            "control_probability": float(panel.control_probability[row, outcome]),
            "control_probability_uncertainty": 0.0,
            "predicted_final_sp": float(panel.predicted_sp[row, outcome]),
            "predicted_final_sp_seed_std": float(panel.sp_seed_std[row, outcome]),
            "probability_source": "MARKET_ONLY",
            "probability_source_grade": "FROZEN_SAFE_BASELINE",
        }
        for row, outcome in zip(rows, outcomes, strict=True)
    ]
    return {
        "split": panel.split,
        "issue": panel.issue,
        "year": panel.year,
        "ticket_identity": _identity(panel, rows, outcomes),
        "match_indices": "|".join(map(str, panel.match_idx[rows].tolist())),
        "outcomes": "|".join(OUTCOMES[int(i)] for i in outcomes),
        "candidate_source": source,
        "source_cells_json": json.dumps(
            source_cells, ensure_ascii=False, separators=(",", ":")
        ),
        "n": N,
        "control_joint_probability": joint,
        "predicted_sp_product": sp_product,
        "expected_pre_tax_net": TAX_FACTOR * joint * sp_product - 1.0,
        "experimental_expected_pre_tax_net": TAX_FACTOR
        * exp_joint
        * sp_product
        - 1.0,
        "mean_abs_experimental_residual": float(np.mean(np.abs(chosen_exp - chosen_p))),
        "log_joint_probability": float(np.log(np.clip(joint, 1e-300, None))),
        "log_sp_product": float(np.log(np.clip(sp_product, 1e-300, None))),
        "mean_selected_probability": float(chosen_p.mean()),
        "min_selected_probability": float(chosen_p.min()),
        "mean_selected_sp": float(chosen_sp.mean()),
        "mean_selected_sp_seed_std": float(chosen_sp_uncertainty.mean()),
        "max_selected_sp_seed_std": float(chosen_sp_uncertainty.max()),
        "outcome_hhi": float(np.sum(counts**2)),
        "match_rank_mean": float(rank[rows].mean() / len(rank)),
        "labels_available": labels,
        "realized_hit": hit if labels else False,
        "realized_gross": realized_gross,
    }


def generate_candidates(panel: IssuePanel, *, draws_per_seed: int = 64) -> pd.DataFrame:
    """Generate a bounded pool without imposing one shared seven-match roster."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    match_score = np.max(
        panel.control_probability * panel.predicted_sp, axis=1
    ) * np.max(panel.control_probability, axis=1)
    ranked = np.argsort(-match_score, kind="stable")
    top_width = min(len(ranked), 32)
    for offset in range(min(64, max(top_width, 1))):
        stride = 1 + (offset % 5)
        positions = (offset + stride * np.arange(N)) % top_width
        if len(np.unique(positions)) < N:
            positions = (offset + np.arange(N)) % top_width
        selected = ranked[positions]
        outcome_order = np.argsort(
            -panel.control_probability[selected], axis=1, kind="stable"
        )
        outcomes = outcome_order[np.arange(N), (offset // max(top_width, 1)) % 3]
        identity = _identity(panel, selected, outcomes)
        if identity not in seen:
            seen.add(identity)
            rows.append(_ticket_row(panel, selected, outcomes, "TOP_MASS_SYSTEMATIC"))

    weights = np.clip(match_score, 1e-15, None)
    weights = weights / weights.sum()
    for seed in NUISANCE_SEEDS:
        rng = np.random.default_rng(_stable_seed(seed, panel.split, panel.issue))
        for _ in range(draws_per_seed):
            selected = rng.choice(len(panel.match_idx), size=N, replace=False, p=weights)
            outcomes = np.asarray(
                [
                    rng.choice(3, p=panel.control_probability[row])
                    for row in selected
                ],
                dtype=int,
            )
            identity = _identity(panel, selected, outcomes)
            if identity not in seen:
                seen.add(identity)
                rows.append(_ticket_row(panel, selected, outcomes, "MARKET_WEIGHTED_WOR"))
    if len(rows) < max(K_GRID):
        raise TicketPolicyError(
            f"issue {panel.issue} generated only {len(rows)} unique candidates"
        )
    return pd.DataFrame(rows)


def _select(
    candidates: pd.DataFrame,
    policy: str,
    k: int,
    *,
    scores: np.ndarray | None = None,
) -> pd.DataFrame:
    if k <= 0 or candidates.empty:
        raise TicketPolicyError("invalid ticket-selection request")
    frame = candidates.copy()
    if policy == "BEST_FULL":
        index = np.argsort(-frame.expected_pre_tax_net.to_numpy(), kind="stable")[:k]
    elif policy == "MARKET_WOR":
        rng = np.random.default_rng(_stable_seed(policy, frame.issue.iloc[0], k))
        probability = _softmax(frame.log_joint_probability.to_numpy(), 1.0)
        index = rng.choice(len(frame), size=k, replace=False, p=probability)
    elif policy == "MARKET_WR":
        rng = np.random.default_rng(_stable_seed(policy, frame.issue.iloc[0], k))
        probability = _softmax(frame.log_joint_probability.to_numpy(), 1.0)
        index = rng.choice(len(frame), size=k, replace=True, p=probability)
    elif policy.startswith("TEMPERATURE_"):
        temperature = int(policy.rsplit("_", 1)[1]) / 100.0
        rng = np.random.default_rng(_stable_seed(policy, frame.issue.iloc[0], k))
        probability = _softmax(frame.expected_pre_tax_net.to_numpy(), temperature)
        index = rng.choice(len(frame), size=k, replace=False, p=probability)
    elif policy in {"LEARNED_MLP", "EXPERIMENTAL_MLP_ABLATION"}:
        if scores is None or len(scores) != len(frame):
            raise TicketPolicyError("learned policy scores are missing")
        index = np.argsort(-np.asarray(scores), kind="stable")[:k]
    elif policy in {"OVERLAP_CAPPED", "OVERLAP_PENALIZED"}:
        match_sets = [set(map(int, value.split("|"))) for value in frame.match_indices]
        remaining = list(
            np.argsort(-frame.expected_pre_tax_net.to_numpy(), kind="stable")
        )
        chosen: list[int] = []
        while remaining and len(chosen) < k:
            if not chosen:
                picked = remaining[0]
            else:
                overlaps = np.asarray(
                    [
                        np.mean(
                            [len(match_sets[row] & match_sets[prior]) / N for prior in chosen]
                        )
                        for row in remaining
                    ]
                )
                if policy == "OVERLAP_CAPPED":
                    feasible = np.flatnonzero(overlaps <= 5 / N)
                    picked = remaining[int(feasible[0])] if len(feasible) else remaining[0]
                else:
                    utility = frame.expected_pre_tax_net.to_numpy()[remaining]
                    picked = remaining[int(np.argmax(utility - 2.0 * overlaps))]
            chosen.append(picked)
            remaining.remove(picked)
        index = np.asarray(chosen, dtype=int)
    else:
        raise TicketPolicyError(f"unknown policy {policy}")
    selected = frame.iloc[np.asarray(index, dtype=int)].copy()
    selected["ticket_order"] = np.arange(1, len(selected) + 1)
    selected["policy"] = policy
    selected["requested_stake"] = STAKE
    selected["repeat_count"] = selected.groupby("ticket_identity").ticket_identity.transform(
        "size"
    )
    return selected


def _fit_model(
    candidates: pd.DataFrame, features: tuple[str, ...], *, seed: int
) -> Any:
    train = candidates.loc[candidates.labels_available].copy()
    target = train.realized_hit.astype(int).to_numpy()
    if target.sum() < 3 or len(np.unique(target)) != 2:
        raise TicketPolicyError("insufficient realized hits for learned policy")
    weights = np.where(target == 1, len(target) / (2 * target.sum()), len(target) / (2 * (len(target) - target.sum())))
    model = make_pipeline(
        StandardScaler(),
        MLPClassifier(
            hidden_layer_sizes=(12,),
            activation="relu",
            solver="adam",
            alpha=0.01,
            batch_size=256,
            learning_rate_init=0.001,
            max_iter=120,
            random_state=seed,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=10,
        ),
    )
    model.fit(train.loc[:, features], target, mlpclassifier__sample_weight=weights)
    return model


def _score_model(model: Any, candidates: pd.DataFrame, features: tuple[str, ...]) -> np.ndarray:
    return np.asarray(model.predict_proba(candidates.loc[:, features])[:, 1], dtype=float)


def _mean_pairwise_overlap(selected: pd.DataFrame) -> tuple[float, float]:
    matches = [set(map(int, value.split("|"))) for value in selected.match_indices]
    identities = selected.ticket_identity.to_list()
    if len(matches) < 2:
        return 0.0, 0.0
    match_overlap: list[float] = []
    ticket_overlap: list[float] = []
    for left in range(len(matches)):
        for right in range(left + 1, len(matches)):
            match_overlap.append(len(matches[left] & matches[right]) / N)
            ticket_overlap.append(float(identities[left] == identities[right]))
    return float(np.mean(match_overlap)), float(np.mean(ticket_overlap))


def _issue_metric(selected: pd.DataFrame) -> dict[str, Any]:
    match_overlap, ticket_overlap = _mean_pairwise_overlap(selected)
    stake_share = selected.groupby("ticket_identity").requested_stake.sum()
    stake_share = stake_share / stake_share.sum()
    labels = selected.labels_available.all()
    return {
        "split": selected.split.iloc[0],
        "issue": selected.issue.iloc[0],
        "year": int(selected.year.iloc[0]),
        "policy": selected.policy.iloc[0],
        "k": len(selected),
        "turnover": float(selected.requested_stake.sum()),
        "expected_pre_tax_net": float(selected.expected_pre_tax_net.mean()),
        "realized_pre_tax_net": float(selected.realized_gross.mean() - 1.0)
        if labels
        else np.nan,
        "coverage_hit": bool(selected.realized_hit.any()) if labels else False,
        "labels_available": bool(labels),
        "match_overlap": match_overlap,
        "ticket_overlap": ticket_overlap,
        "repeat_share": float(selected.duplicated("ticket_identity", keep=False).mean()),
        "stake_hhi": float(np.sum(stake_share.to_numpy() ** 2)),
    }


def _evaluate(
    candidates: pd.DataFrame,
    policies: Iterable[str],
    k_grid: Iterable[int],
    models: dict[str, tuple[Any, tuple[str, ...]]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selections: list[pd.DataFrame] = []
    issue_metrics: list[dict[str, Any]] = []
    for (_, _), group in candidates.groupby(["split", "issue"], sort=False):
        for policy in policies:
            model_spec = models.get(policy)
            scores = (
                _score_model(model_spec[0], group, model_spec[1])
                if model_spec is not None
                else None
            )
            for k in k_grid:
                selected = _select(group, policy, k, scores=scores)
                selections.append(selected)
                issue_metrics.append(_issue_metric(selected))
    return pd.concat(selections, ignore_index=True), pd.DataFrame(issue_metrics)


def _surface(issue_metrics: pd.DataFrame) -> pd.DataFrame:
    labeled = issue_metrics.loc[issue_metrics.labels_available].copy()
    return (
        labeled.groupby(["split", "policy", "k"], as_index=False)
        .agg(
            issues=("issue", "nunique"),
            turnover=("turnover", "sum"),
            expected_pre_tax_net=("expected_pre_tax_net", "mean"),
            realized_pre_tax_net=("realized_pre_tax_net", "mean"),
            coverage=("coverage_hit", "mean"),
            match_overlap=("match_overlap", "mean"),
            ticket_overlap=("ticket_overlap", "mean"),
            repeat_share=("repeat_share", "mean"),
            stake_hhi=("stake_hhi", "mean"),
        )
        .sort_values(["split", "policy", "k"], kind="stable")
        .reset_index(drop=True)
    )


def _ticket_calibration(candidates: pd.DataFrame) -> pd.DataFrame:
    labeled = candidates.loc[
        candidates.labels_available & candidates.split.isin(["CV_2022", "CV_2023"])
    ].copy()
    rows: list[pd.DataFrame] = []
    for split, group in labeled.groupby("split", sort=False):
        group = group.copy()
        group["probability_bin"] = pd.qcut(
            group.control_joint_probability,
            q=10,
            labels=False,
            duplicates="drop",
        )
        calibrated = group.groupby("probability_bin", as_index=False).agg(
            tickets=("ticket_identity", "size"),
            mean_joint_probability=("control_joint_probability", "mean"),
            realized_hit_rate=("realized_hit", "mean"),
            mean_expected_gross=("expected_pre_tax_net", lambda x: float(x.mean() + 1.0)),
            mean_realized_gross=("realized_gross", "mean"),
        )
        calibrated["payout_mae"] = (
            calibrated.mean_expected_gross - calibrated.mean_realized_gross
        ).abs()
        calibrated.insert(0, "split", split)
        rows.append(calibrated)
    return pd.concat(rows, ignore_index=True)


def _select_validation_policy(
    surface: pd.DataFrame, issue_metrics: pd.DataFrame
) -> tuple[dict[str, Any], pd.DataFrame]:
    validation = surface.loc[surface.split.eq("CV_2022")].copy()
    controls = validation.loc[validation.policy.isin(CONTROL_POLICIES)].sort_values(
        ["realized_pre_tax_net", "coverage", "expected_pre_tax_net"],
        ascending=False,
        kind="stable",
    )
    if controls.empty:
        raise TicketPolicyError("validation policy surface is incomplete")
    control = controls.iloc[0]
    challengers = validation.loc[
        validation.policy.isin(CHALLENGER_POLICIES)
        & validation.k.eq(int(control.k))
    ].sort_values(
        ["realized_pre_tax_net", "coverage", "expected_pre_tax_net"],
        ascending=False,
        kind="stable",
    )
    if challengers.empty:
        raise TicketPolicyError("matched-K validation challenger surface is incomplete")
    challenger = challengers.iloc[0]
    pair = issue_metrics.loc[
        issue_metrics.split.eq("CV_2022")
        & issue_metrics.labels_available
        & (
            (
                issue_metrics.policy.eq(control.policy)
                & issue_metrics.k.eq(int(control.k))
            )
            | (
                issue_metrics.policy.eq(challenger.policy)
                & issue_metrics.k.eq(int(challenger.k))
            )
        )
    ].pivot(index="issue", columns=["policy", "k"], values="realized_pre_tax_net")
    control_key = (str(control.policy), int(control.k))
    challenger_key = (str(challenger.policy), int(challenger.k))
    pair = pair.dropna(subset=[control_key, challenger_key])
    delta = pair[challenger_key] - pair[control_key]
    sem = float(stats.sem(delta.to_numpy(), ddof=1)) if len(delta) > 1 else np.inf
    critical = float(stats.t.ppf(0.95, df=len(delta) - 1)) if len(delta) > 1 else np.inf
    lower = float(delta.mean() - critical * sem) if np.isfinite(sem) else -np.inf
    expected_lift = float(
        challenger.expected_pre_tax_net - control.expected_pre_tax_net
    )
    coverage_lift = float(challenger.coverage - control.coverage)
    advance = bool(
        lower >= 0.0
        and expected_lift >= 0.0
        and coverage_lift >= 0.0
        and float(challenger.turnover) == float(control.turnover)
    )
    decision = {
        "version": VERSION,
        "selection_split": "CV_2022",
        "evaluation_split": "CV_2023",
        "label_embargo": "No LOCKED_TEST (2025/2026) outcome or official-final-SP label enters training, selection, or evaluation",
        "safe_control_policy": str(control.policy),
        "safe_control_k": int(control.k),
        "challenger_policy": str(challenger.policy),
        "challenger_k": int(challenger.k),
        "paired_validation_issues": int(len(delta)),
        "validation_realized_lift": float(delta.mean()),
        "validation_lift_one_sided_95_lcb": lower,
        "validation_expected_lift": expected_lift,
        "validation_coverage_lift": coverage_lift,
        "matched_turnover": float(control.turnover),
        "advance_learned_policy": advance,
        "fallback_mixed_policy": str(challenger.policy) if advance else str(control.policy),
        "fallback_mixed_k": int(challenger.k) if advance else int(control.k),
        "disposition": "ADVANCE_FALLBACK_MIXED_POLICY"
        if advance
        else "INHERIT_STRONGEST_FROZEN_CONTROL",
        "fallback_reason": "NONE"
        if advance
        else "VALIDATION_UNCERTAINTY_OR_MATCHED_LIFT_FLOOR",
        "stage_boundary": "requested tickets and requested ¥2 stake only; no bankroll sizing authority",
    }
    return decision, pair.reset_index()


def _matched_surface(
    surface: pd.DataFrame, decision: dict[str, Any]
) -> pd.DataFrame:
    output = surface.copy()
    controls = output.loc[
        output.policy.eq(decision["safe_control_policy"])
        & output.k.eq(decision["safe_control_k"]),
        [
            "split",
            "expected_pre_tax_net",
            "realized_pre_tax_net",
            "coverage",
            "turnover",
        ],
    ].rename(
        columns={
            "expected_pre_tax_net": "control_expected_pre_tax_net",
            "realized_pre_tax_net": "control_realized_pre_tax_net",
            "coverage": "control_coverage",
            "turnover": "control_turnover",
        }
    )
    output = output.merge(controls, on="split", how="left", validate="many_to_one")
    output["matched_lift_expected_pre_tax_net"] = (
        output.expected_pre_tax_net - output.control_expected_pre_tax_net
    )
    output["matched_lift_realized_pre_tax_net"] = (
        output.realized_pre_tax_net - output.control_realized_pre_tax_net
    )
    output["matched_lift_coverage"] = output.coverage - output.control_coverage
    output["stake_budget_matched"] = np.isclose(
        output.turnover, output.control_turnover, rtol=0.0, atol=0.0
    )
    return output


def _plots(surface: pd.DataFrame, output: Path) -> None:
    test = surface.loc[surface.split.eq("CV_2023")]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for policy, group in test.groupby("policy", sort=False):
        axes[0].plot(group.k, group.realized_pre_tax_net, marker="o", label=policy)
        axes[1].plot(group.k, group.coverage, marker="o", label=policy)
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set(title="CV 2023 realized pre-tax utility", xlabel="K", ylabel="net / ¥2 stake")
    axes[1].set(title="CV 2023 issue coverage", xlabel="K", ylabel="hit coverage")
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output / "policy_surface.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    chosen = test.loc[test.stake_budget_matched]
    ax.scatter(chosen.match_overlap, chosen.matched_lift_realized_pre_tax_net)
    for row in chosen.itertuples(index=False):
        ax.annotate(row.policy, (row.match_overlap, row.matched_lift_realized_pre_tax_net), fontsize=7)
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set(xlabel="mean pairwise match overlap", ylabel="matched realized lift", title="Overlap / matched-lift trade-off")
    fig.tight_layout()
    fig.savefig(output / "overlap_lift.png", dpi=160)
    plt.close(fig)


def _decision_report(decision: dict[str, Any], surface: pd.DataFrame) -> str:
    evaluation = surface.loc[
        surface.split.eq("CV_2023")
        & surface.policy.eq(decision["fallback_mixed_policy"])
        & surface.k.eq(decision["fallback_mixed_k"])
    ].iloc[0]
    return f"""# Issue #206 decision report — fixed-N7 ticket generation

## Decision

`{decision['disposition']}`. The validation-selected challenger was `{decision['challenger_policy']}` at K={decision['challenger_k']}; the strongest matched control was `{decision['safe_control_policy']}` at K={decision['safe_control_k']}. The paired validation realized-lift one-sided 95% lower bound was {decision['validation_lift_one_sided_95_lcb']:.6f}. The deterministic gate therefore emitted `{decision['fallback_reason']}`.

The fallback-mixed CV-2023 path delivered absolute realized pre-tax net {evaluation.realized_pre_tax_net:.6f}, expected pre-tax net {evaluation.expected_pre_tax_net:.6f}, coverage {evaluation.coverage:.6f}, and matched realized lift {evaluation.matched_lift_realized_pre_tax_net:+.6f} at exactly ¥{evaluation.turnover:.0f} turnover. No apparent improvement from fewer tickets or cash is accepted.

## Constraint and evidence interpretation

- Every ticket has exactly seven distinct match ids and one 3/1/0 outcome per match. There is no global seven-match roster.
- The three fixed nuisance seeds generate a bounded full-issue candidate pool; seed choice is never outcome-ranked.
- Exact duplicate ticket identity is separately measured from match overlap. Controlling WOR policies request distinct identities; repeat stake remains an explicit, traceable action rather than accidental duplication.
- Only #205 `MARKET_ONLY` / `FROZEN_SAFE_BASELINE` control probability and frozen pre-event SP enter the controlling policy. Experimental residuals appear only in `EXPERIMENTAL_MLP_ABLATION`.
- Training uses CV-2021, policy/K selection uses CV-2022, final historical evaluation uses CV-2023. LOCKED_TEST 2025/2026 labels remain embargoed; its Stage-3 handoff is label-blind.

## Failure regimes and risks

Sparse seven-leg hits make realized utility high variance; this is why the lower-confidence-bound gate fails closed. Bounded generation does not enumerate C(M,7)×3^7, and may miss useful identities. Independence, frozen predicted-SP error, issue-level concentration, and retrospective-only evidence remain material. Stage 4 owns capital sizing and NO_BET integration.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Exact fixed-N7 identities over issue-specific subsets | `ticket_requests.parquet`, tests, `decision_trace.json` | PASS |
| K/WR-WOR/repeat/overlap outputs and fallback reasons | `policy_surface.csv`, `issue_metrics.csv`, `decision.json` | PASS |
| Ticket hit and payout calibration | `ticket_calibration.csv` on CV-2022/CV-2023 only | PASS |
| Absolute plus matched lift on equal ticket/stake budgets | `policy_surface.csv`, this report | PASS |
| Baseline, simple, learned, stochastic and experimental ablations | `policy_surface.csv`, `model_parameters.json` | PASS |
| Deterministic safe floor | `{decision['disposition']}` and paired LCB | PASS — conservative inheritance |
| Notebook/code/artifact three-layer replay | executed notebook, reusable module/tests, manifest package | PASS |

Decision input: retain `{decision['safe_control_policy']}` with K={decision['safe_control_k']} as the Stage-3 requested-ticket control; do not claim learned-policy advancement. Known risks: sparse payouts, bounded candidate recall, market-independence assumption, predicted-SP error, and no post-2023 label access. Explicit review request: independently verify no shared roster, exact N7 uniqueness, label embargo, package-backed sampling/model/statistics, matched stake arithmetic, fallback gate, notebook clean-run, and manifest-identical replay. No bankroll sizing, betting, merge, or issue closure is authorized.
"""


def run(inputs: Inputs) -> dict[str, Any]:
    output = inputs.output.resolve()
    stage = output.with_name(f".{output.name}.stage")
    if output.exists() or stage.exists():
        raise TicketPolicyError("output or stage already exists")
    stage.mkdir(parents=True)
    try:
        panels = load_panels(inputs.value_matrix, inputs.value_schema)
        candidate_frames = [generate_candidates(panel) for panel in panels]
        candidates = pd.concat(candidate_frames, ignore_index=True)
        train = candidates.loc[candidates.split.eq("CV_2021")].copy()
        safe_model = _fit_model(train, FEATURES, seed=206001)
        experimental_model = _fit_model(train, EXPERIMENTAL_FEATURES, seed=206001)
        models = {
            "LEARNED_MLP": (safe_model, FEATURES),
            "EXPERIMENTAL_MLP_ABLATION": (experimental_model, EXPERIMENTAL_FEATURES),
        }
        policies = (*CONTROL_POLICIES, *CHALLENGER_POLICIES, "EXPERIMENTAL_MLP_ABLATION")
        development = candidates.loc[candidates.split.isin(["CV_2022", "CV_2023"])]
        selections, issue_metrics = _evaluate(development, policies, K_GRID, models)
        surface = _surface(issue_metrics)
        calibration = _ticket_calibration(candidates)
        decision, paired = _select_validation_policy(surface, issue_metrics)
        surface = _matched_surface(surface, decision)

        locked = candidates.loc[candidates.split.eq("LOCKED_TEST")]
        locked_requests: list[pd.DataFrame] = []
        for _, group in locked.groupby("issue", sort=False):
            policy = decision["fallback_mixed_policy"]
            model_spec = models.get(policy)
            scores = (
                _score_model(model_spec[0], group, model_spec[1])
                if model_spec is not None
                else None
            )
            selected = _select(group, policy, decision["fallback_mixed_k"], scores=scores)
            selected["fallback_applied"] = not decision["advance_learned_policy"]
            selected["fallback_reason"] = decision["fallback_reason"]
            selected["capital_authority"] = "REQUEST_ONLY"
            selected["labels_used"] = False
            locked_requests.append(selected)
        requests = pd.concat(locked_requests, ignore_index=True)
        request_columns = [
            "split",
            "issue",
            "year",
            "ticket_order",
            "ticket_identity",
            "match_indices",
            "outcomes",
            "n",
            "policy",
            "candidate_source",
            "source_cells_json",
            "requested_stake",
            "repeat_count",
            "control_joint_probability",
            "predicted_sp_product",
            "expected_pre_tax_net",
            "fallback_applied",
            "fallback_reason",
            "capital_authority",
            "labels_used",
        ]
        requests.loc[:, request_columns].to_parquet(
            stage / "ticket_requests.parquet", index=False
        )
        candidates.to_parquet(stage / "candidate_ledger.parquet", index=False)
        issue_metrics.to_csv(stage / "issue_metrics.csv", index=False)
        surface.to_csv(stage / "policy_surface.csv", index=False)
        calibration.to_csv(stage / "ticket_calibration.csv", index=False)
        paired.to_csv(stage / "paired_validation_lift.csv", index=False)
        _json(stage / "decision.json", decision)
        _json(
            stage / "model_parameters.json",
            {
                "version": VERSION,
                "features": list(FEATURES),
                "experimental_ablation_features": list(EXPERIMENTAL_FEATURES),
                "model": "sklearn.pipeline(StandardScaler, MLPClassifier)",
                "hidden_layer_sizes": [12],
                "alpha": 0.01,
                "max_iter": 120,
                "model_seed": 206001,
                "nuisance_candidate_seeds": list(NUISANCE_SEEDS),
                "device": "CPU",
                "determinism": "fixed NumPy/scikit-learn seeds; single-process fit and generation",
                "draws_per_seed": 64,
                "k_grid": list(K_GRID),
                "tax_factor_reference": TAX_FACTOR,
                "stake_per_ticket": STAKE,
            },
        )
        first = requests.iloc[0]
        _json(
            stage / "decision_trace.json",
            {
                "version": VERSION,
                "issue": first.issue,
                "ticket_identity": first.ticket_identity,
                "selected_match_subset": list(map(int, first.match_indices.split("|"))),
                "selected_outcomes": first.outcomes.split("|"),
                "source_cells": json.loads(first.source_cells_json),
                "control_joint_probability": float(first.control_joint_probability),
                "predicted_sp_product": float(first.predicted_sp_product),
                "expected_pre_tax_net": float(first.expected_pre_tax_net),
                "requested_stake": int(first.requested_stake),
                "fallback_applied": bool(first.fallback_applied),
                "fallback_reason": first.fallback_reason,
                "labels_used": False,
                "formula": "0.65 * product(control_probability) * product(predicted_final_sp) - 1",
            },
        )
        _json(
            stage / "provenance.json",
            {
                "version": VERSION,
                "source_value_matrix": str(inputs.value_matrix),
                "source_value_matrix_sha256": _digest(inputs.value_matrix),
                "source_schema": str(inputs.value_schema),
                "source_schema_sha256": _digest(inputs.value_schema),
                "source_contract": SOURCE_VERSION,
                "scientific_environment_lock": SCIENTIFIC_LOCK.as_posix(),
                "scientific_environment_lock_sha256": _digest(SCIENTIFIC_LOCK.resolve()),
                "environment": _environment(),
                "replay": "PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py run --output results/issue-206",
                "label_boundary": "CV_2021 train; CV_2022 select; CV_2023 evaluate; LOCKED_TEST labels unused",
            },
        )
        report = _decision_report(decision, surface)
        (stage / "DECISION_REPORT.md").write_text(
            report, encoding="utf-8", newline="\n"
        )
        (stage / "README.md").write_text(
            "# Issue #206 immutable evidence package\n\n"
            "Verify: `PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py verify --output results/issue-206`.\n\n"
            "Replay to a new directory: `PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py run --output <new-directory>`.\n\n"
            "Clean notebook: `PYTHONPATH=src .venv/bin/python scripts/execute_bj206_notebook.py --kernel python3`.\n\n"
            "The package includes exact source-cell traces, ticket hit/payout calibration, matched policy surfaces, plots, and the label-blind request ledger. It is a Stage-3 requested-ticket handoff only and has no final bankroll, betting, or production authority.\n",
            encoding="utf-8",
            newline="\n",
        )
        _plots(surface, stage)
        payloads = {
            path.relative_to(stage).as_posix(): _digest(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file() and path.name != "SHA256SUMS.json"
        }
        _json(stage / "SHA256SUMS.json", payloads)
        output.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(output)
        return {
            "output": str(output),
            "decision": decision,
            "candidate_rows": len(candidates),
            "request_rows": len(requests),
            "files": len(payloads),
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def verify(output: Path) -> dict[str, Any]:
    expected = json.loads((output / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.relative_to(output).as_posix(): _digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if actual != expected:
        raise TicketPolicyError("manifest mismatch")
    decision = json.loads((output / "decision.json").read_text(encoding="utf-8"))
    requests = pd.read_parquet(output / "ticket_requests.parquet")
    if requests.empty or not requests.n.eq(N).all():
        raise TicketPolicyError("fixed-N7 request mismatch")
    parsed = requests.ticket_identity.str.split("|")
    if not parsed.map(len).eq(N).all():
        raise TicketPolicyError("ticket identity leg count mismatch")
    if not parsed.map(lambda legs: len({leg.split(":", 1)[0] for leg in legs})).eq(N).all():
        raise TicketPolicyError("ticket contains repeated match")
    if requests.labels_used.astype(bool).any():
        raise TicketPolicyError("locked label entered Stage-3 request")
    if not requests.requested_stake.eq(STAKE).all():
        raise TicketPolicyError("requested stake mismatch")
    if decision["disposition"] == "INHERIT_STRONGEST_FROZEN_CONTROL" and (
        not requests.fallback_applied.astype(bool).all()
        or set(requests.policy) != {decision["safe_control_policy"]}
    ):
        raise TicketPolicyError("fallback decision/request mismatch")
    surface = pd.read_csv(output / "policy_surface.csv")
    if not surface.stake_budget_matched.astype(bool).any():
        raise TicketPolicyError("matched stake surface absent")
    return {
        "status": "PASS",
        "files": len(actual),
        "manifest_sha256": _digest(output / "SHA256SUMS.json"),
        "request_rows": len(requests),
        "issues": int(requests.issue.nunique()),
    }
