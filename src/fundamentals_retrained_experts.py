"""Fixed shallow diagnostic experts, fitted only through shared chronology.

No fetching or import-time writes. Inputs are numeric, label-free predictors
plus explicitly timed historical labels. Missing predictors abstain; no learned
imputation. Probabilities use Laplace-one smoothing of equal-weight leaf counts.
"""
from pathlib import Path
import hashlib
import pickle
import json

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text

from src.temporal_learning import (
    AvailabilityFilter, AvailabilityPolicy, Cutoff, PartitionPolicy,
    WeightingPolicy, prepare_learning_context, temporal_client,
)
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure


def tree_identity(tree):
    """Hash semantic sklearn state, excluding pickle padding bytes; no I/O."""
    state = tree.tree_.__getstate__()
    return stable_json_hash({"params": tree.get_params(), "nodes": state['nodes'].tolist(),
        "values": state['values'].tolist(), "classes": tree.classes_.tolist(),
        "features": tree.feature_names_in_.tolist()})


@temporal_client
def fit_experts(history, cutoff, *, features, training_issues, source_hashes,
                repository_root, depths, minimum_leaf, minimum_ess, bounds, seed, selection=None):
    """Return nominated independently fitted sklearn models and cutoff-bound machine receipts.

    history: DataFrame, unique (issue_code, slot, provider_id), binary targets
    draw_target/cover_target, issue_year and explicit availability timestamps.
    features: draw/high predictor lists; no label or result fields permitted.
    Policies are fixed caller inputs; no tuning or calibration is performed.
    Insufficient admitted data or invalid contracts raise ValueError. No I/O.
    """
    if not features or not set(features) <= {"draw", "high"} or set(depths) != set(features):
        raise ValueError("Explicit draw/high feature/depth policies required")
    if (len(bounds) != 2 or not 0 < bounds[0] < bounds[1] < 1 or
            minimum_leaf < 3 or minimum_ess < 2 or
            any(type(d) is not int or not 1 <= d <= 3 for d in depths.values())):
        raise ValueError("Invalid fixed tree policy")
    if not training_issues or cutoff.target_issue in training_issues:
        raise ValueError("Explicit prior training issues required")
    keys = ["issue_code", "slot", "provider_id"]
    if history[keys].isna().any().any() or history.duplicated(keys).any():
        raise ValueError("Unique complete identities required")
    forbidden = {"draw_target", "cover_target", "actual_home", "actual_away",
                 "scorable", "settlement", "result", "issue_year", "slot"}
    for columns in features.values():
        if not columns or len(set(columns)) != len(columns) or forbidden.intersection(columns):
            raise ValueError("Explicit label-free unique predictors required")
    if selection is not None:
        receipt = selection["receipt"]
        policy = dict(depths=depths, minimum_leaf=minimum_leaf, bounds=list(bounds))
        if (stable_json_hash(receipt) != selection["seal"] or
            selection["selected"] != receipt["selected_parameters"] or
            selection["selected"] != policy or
            selection["metrics"] != receipt["metrics"] or
            stable_json_hash(selection["oof"]) != receipt["oof_sha256"] or
            receipt["features"] != features or receipt["seed"] != seed or
            receipt["minimum_ess"] != minimum_ess or
            receipt["cutoff_identity"] != cutoff.identity or
            receipt["cutoff_ts"] != cutoff.cutoff_ts.isoformat() or
            receipt["issue_order"] != training_issues or
            any(source_hashes.get(k) != v for k, v in receipt["source_hashes"].items())):
            raise ValueError("CV selection binding mismatch")
    # Caller nominates the four source issues; common context owns chronology.
    source = history[history.issue_code.isin(training_issues)].copy()
    result = {"models": {}, "features": features, "leaves": {}, "receipt": {}}
    for name in features:
        context = prepare_learning_context(
            source, cutoff, source_hashes=source_hashes,
            repository_root=Path(repository_root),
            implementation_modules=(("src.fundamentals_retrained_experts", "src.fundamentals_cv_experts")
                                    if selection is not None else ("src.fundamentals_retrained_experts",)),
            implementation_distributions=("numpy", "pandas", "scikit-learn"),
            availability=AvailabilityFilter(
                AvailabilityPolicy.historical_proxy("FIXTURE_CUTOFF_PLUS_SIX_HOURS_DIAGNOSTIC"),
                data_available_column="data_available_ts"),
            intended_use="HISTORICAL_DIAGNOSTIC",
            partition_policy=PartitionPolicy("FIXED_PRIOR_FIT", 0, 0, 1),
            weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=minimum_ess),
        )
        admitted = context.partitions["fit"]
        eligible = np.ones(len(admitted), dtype=bool) if name == "draw" else admitted.handicap.abs().ge(2).to_numpy()
        x = admitted[features[name]].astype(float)
        complete = np.isfinite(x).all(axis=1).to_numpy()
        at = eligible & complete
        target = "draw_target" if name == "draw" else "cover_target"
        y = admitted.loc[at, target]
        if len(y) < max(minimum_ess, 2 * minimum_leaf) or y.isna().any() or not set(y).issubset({0, 1, False, True}) or y.nunique() != 2:
            raise ValueError("Insufficient valid binary expert training history")
        tree = DecisionTreeClassifier(max_depth=depths[name], min_samples_leaf=minimum_leaf,
                                      min_samples_split=2 * minimum_leaf, random_state=seed,
                                      criterion="gini", ccp_alpha=0)
        tree.fit(x.loc[at], y.astype(int))
        nodes = tree.apply(x.loc[at])
        leaves = {}
        for node in np.unique(nodes):
            positives = int(y.to_numpy()[nodes == node].sum())
            n = int((nodes == node).sum())
            leaves[int(node)] = {"n": n, "positive": positives, "probability": (positives + 1) / (n + 2)}
        result["models"][name] = tree
        result["leaves"][name] = leaves
        result["receipt"][name] = {
            **context.receipt.payload, "weight_ledger": context.weight_ledger.to_json(orient="records", date_format="iso"),
            "training_issues": sorted(set(admitted.loc[at, "issue_code"])),
            "expert_rows": int(at.sum()), "expert_ess": int(at.sum()),
            "scope_excluded": int((~eligible).sum()),
            "missing_predictors": int((eligible & ~complete).sum()),
            "features": features[name], "depth": depths[name], "minimum_leaf": minimum_leaf,
            "seed": seed, "bounds": list(bounds), "leaf_smoothing": "LAPLACE_ONE",
            "rules": export_text(tree, feature_names=features[name]),
            "model_sha256": tree_identity(tree),
            "leaves": leaves, "tuning": "CUTOFF_BOUND_CV" if selection is not None else "NONE_FIXED_POLICY",
            "selection": selection, "deployable": False,
        }
    result["bounds"] = list(bounds)
    result["cutoff"] = cutoff
    result["training_issues"] = list(training_issues)
    result["seal"] = stable_json_hash(result["receipt"])
    return result


from src.temporal_learning.replay import prediction_scope

def predict_experts(artifact, frame, cutoff):
    """Predict from frozen models; target inputs never contain outcome columns.

    cutoff is the actual target decision epoch. Training/earlier predictions
    automatically warn and carry replay scope; no flag is required.
    Missing numeric predictors yield INSUFFICIENT_FEATURES, outside high-margin
    scope yields NOT_APPLICABLE. Returns a DataFrame, with no file side effects.
    """
    if stable_json_hash(artifact["receipt"]) != artifact["seal"]:
        raise ValueError("Frozen receipt changed")
    if not isinstance(cutoff, Cutoff) or cutoff.target_issue is None:
        raise ValueError("Explicit target decision cutoff required")
    if frame.duplicated(["issue_code", "slot", "provider_id"]).any() or not frame.issue_code.eq(cutoff.target_issue).all():
        raise ValueError("Target identity mismatch")
    scope = prediction_scope(cutoff, artifact["training_issues"], artifact["cutoff"])
    out = frame[["issue_code", "slot", "provider_id"]].copy()
    for name in artifact["features"]:
        if tree_identity(artifact["models"][name]) != artifact["receipt"][name]["model_sha256"]:
            raise ValueError("Frozen model changed")
        if artifact["leaves"][name] != artifact["receipt"][name]["leaves"] or artifact["features"][name] != artifact["receipt"][name]["features"] or artifact["bounds"] != artifact["receipt"][name]["bounds"]:
            raise ValueError("Frozen prediction policy changed")
        x = frame[artifact["features"][name]].astype(float)
        eligible = np.ones(len(frame), dtype=bool) if name == "draw" else frame.handicap.abs().ge(2).to_numpy()
        complete = np.isfinite(x).all(axis=1).to_numpy()
        ready = eligible & complete
        p = np.full(len(frame), np.nan)
        if ready.any():
            p[ready] = [artifact["leaves"][name][int(n)]["probability"] for n in artifact["models"][name].apply(x.loc[ready])]
        low, high = artifact["bounds"]
        out[name + "_probability"] = p
        out[name + "_signal"] = np.where(~eligible, "NOT_APPLICABLE", np.where(~complete, "INSUFFICIENT_FEATURES",
            np.where(p <= low, "NEGATIVE", np.where(p >= high, "POSITIVE", "ABSTAIN"))))
    out["evaluation_scope"] = scope
    binding = dict(evaluation_scope=scope, model_cutoff_ts=artifact["cutoff"].cutoff_ts.isoformat(),
                   deployable=False, cutoff_identity=cutoff.identity, cutoff_ts=cutoff.cutoff_ts.isoformat(),
                   model_seal=artifact["seal"], experts=list(artifact["features"]),
                   prediction_sha256=stable_json_hash(out.to_json(orient="records")))
    out.attrs["prediction_receipt"] = binding
    out.attrs["prediction_seal"] = stable_json_hash(binding)
    return out


def predict_frozen_file(model_path, frame, cutoff, *, repository_root):
    """Read this project's trusted internal pickle after SHA/code/source checks.

    Companion .json is the freeze receipt; both are read only. This is not an
    import interface for external/untrusted pickle files. Returns predictions.
    """
    path = Path(model_path)
    receipt = json.loads(path.with_suffix('.json').read_text())
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt['model_sha256']:
        raise ValueError('Frozen file changed')
    for expert in receipt['receipt'].values():
        verify_implementation_closure(Path(repository_root), expert['implementation'])
        for source, expected in expert['source_hashes'].items():
            source_path = Path(source)
            if not source_path.is_absolute():
                source_path = Path(repository_root) / source_path
            if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected:
                raise ValueError('Frozen training source changed')
    artifact = pickle.loads(raw)
    if artifact['seal'] != receipt['seal']:
        raise ValueError('Frozen file receipt mismatch')
    return predict_experts(artifact, frame, cutoff)


def save_frozen_experts(artifact, directory):
    """Publish an immutable trusted-local model directory; reject existing paths.

    Writes model.pkl and its JSON receipt atomically as one directory. Returns
    model path. Artifact policies and trees must match the sealed receipt.
    """
    import os
    import tempfile
    import shutil
    if stable_json_hash(artifact["receipt"]) != artifact["seal"]:
        raise ValueError("Frozen receipt changed")
    for name, receipt in artifact["receipt"].items():
        if (tree_identity(artifact["models"][name]) != receipt["model_sha256"] or
            artifact["features"][name] != receipt["features"] or
            artifact["leaves"][name] != receipt["leaves"] or
            artifact["bounds"] != receipt["bounds"]):
            raise ValueError("Frozen prediction policy changed")
    path = Path(directory)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".expert-", dir=path.parent))
    try:
        raw = pickle.dumps(artifact, protocol=5)
        (temporary / "model.pkl").write_bytes(raw)
        (temporary / "model.json").write_text(json.dumps(dict(
            receipt=artifact["receipt"], seal=artifact["seal"],
            model_sha256=hashlib.sha256(raw).hexdigest()), indent=2))
        os.rename(temporary, path)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return path / "model.pkl"


def combine_expert_predictions(predictions, cutoff):
    """Join draw/high DataFrames one-to-one for the existing R fusion interface.

    Input mapping must contain both experts with identical target fixture keys.
    No fitting, filling absent rows, or I/O. Returns issue_code/slot/provider_id
    and each expert's probability/signal columns. Caller retains model receipts.
    """
    if not isinstance(cutoff, Cutoff) or cutoff.target_issue is None:
        raise ValueError("Explicit target cutoff required")
    if set(predictions) != {"draw", "high"}:
        raise ValueError("Both independently nominated experts required")
    keys = ["issue_code", "slot", "provider_id"]
    tables = []
    allowed = {"POSITIVE", "NEGATIVE", "ABSTAIN", "NOT_APPLICABLE", "INSUFFICIENT_FEATURES"}
    for name in ("draw", "high"):
        frame = predictions[name]
        if (frame[keys].isna().any().any() or frame.duplicated(keys).any() or
                not frame.issue_code.eq(cutoff.target_issue).all()):
            raise ValueError("Unique target identities required")
        probability = frame[name + "_probability"]
        signal = frame[name + "_signal"]
        ready = signal.isin(["POSITIVE", "NEGATIVE", "ABSTAIN"])
        if (not signal.isin(allowed).all() or
                not probability[ready].between(0, 1).all() or
                not np.isfinite(probability[ready]).all() or
                not probability[~ready].isna().all()):
            raise ValueError("Invalid probability/signal contract")
        binding = frame.attrs.get("prediction_receipt", {})
        if (not binding or stable_json_hash(binding) != frame.attrs.get("prediction_seal") or
                binding.get("cutoff_identity") != cutoff.identity or
                binding.get("cutoff_ts") != cutoff.cutoff_ts.isoformat() or
                name not in binding.get("experts", []) or not binding.get("model_seal") or
                binding.get("prediction_sha256") != stable_json_hash(frame.to_json(orient="records"))):
            raise ValueError("Prediction cutoff/model binding mismatch")
        tables.append(frame[keys + [name + "_probability", name + "_signal"]])
    joined = tables[0].merge(tables[1], on=keys, how="outer", validate="one_to_one", indicator=True)
    if not joined["_merge"].eq("both").all():
        raise ValueError("Expert fixture scopes differ")
    joined = joined.drop(columns="_merge")
    joined.attrs["expert_receipts"] = {name: frame.attrs["prediction_receipt"] for name, frame in predictions.items()}
    return joined
