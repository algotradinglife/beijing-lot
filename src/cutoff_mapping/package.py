"""Real-data replay package for the cutoff mapping interface."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.low_n_selector_data.pipeline import _input_panel, locate_data_root
from src.source_schema.publication import atomic_publish_directory
from beidan_backend.temporal_learning import AvailabilityPolicy, Cutoff, WeightingPolicy

from .api import (
    CutoffContractError,
    fit_cutoff_mapping,
    replay_gate,
    replay_mapped,
)
from .contract import CONTRACT_ID, OUTCOMES


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scientific_frames(repo_root: Path, data_root: Path | None = None) -> dict[str, Any]:
    data_root = locate_data_root(repo_root, data_root)
    panel, development, source_hashes = _input_panel(data_root)
    target = (
        panel[
            panel["issue_year"].isin([2022, 2023, 2024])
            & panel["native_line_supported"].eq(True)
        ]
        .copy()
        .reset_index(drop=True)
    )
    cutoff_ts = pd.to_datetime(target["issue_anchor_ts"], utc=True).min()
    year_cutoff = Cutoff.evaluation_year(2022, cutoff_ts)
    last_issue = str(
        development.loc[
            pd.to_datetime(development["label_available_ts"], utc=True).lt(cutoff_ts)
        ]
        .sort_values("label_available_ts", kind="stable")
        .iloc[-1]["issue_code"]
    )
    issue_cutoff = Cutoff.last_issue(last_issue, cutoff_ts)
    policy = WeightingPolicy.expanding_equal()
    availability_policy = AvailabilityPolicy.historical_proxy(
        "KICKOFF_PLUS_4H_HISTORICAL_PROXY_V1"
    )
    fitted = fit_cutoff_mapping(
        development,
        target,
        year_cutoff,
        repository_root=repo_root,
        implementation_modules=("src.cutoff_mapping.package",),
        source_hashes=source_hashes,
        weighting_policy=policy,
        availability_policy=availability_policy,
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    equivalent = fit_cutoff_mapping(
        development,
        target,
        issue_cutoff,
        repository_root=repo_root,
        implementation_modules=("src.cutoff_mapping.package",),
        source_hashes=source_hashes,
        weighting_policy=policy,
        availability_policy=availability_policy,
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    if fitted.receipt["model_identity"] != equivalent.receipt["model_identity"]:
        raise CutoffContractError("equivalent cutoff model identities differ")
    compare_columns = [f"q_candidate_{code}" for code in OUTCOMES] + [
        f"q_line_{code}" for code in OUTCOMES
    ]
    if not np.allclose(
        fitted.mapped[compare_columns],
        equivalent.mapped[compare_columns],
        rtol=0,
        atol=1e-12,
    ):
        raise CutoffContractError("equivalent cutoff probabilities differ")
    replay = replay_mapped(target, fitted.receipt, repository_root=repo_root)
    if not np.allclose(
        fitted.mapped[compare_columns], replay[compare_columns], rtol=0, atol=1e-12
    ):
        raise CutoffContractError("receipt-only mapped probability replay differs")
    replay_predicates = replay_gate(
        development, fitted.receipt, repository_root=repo_root
    )
    if replay_predicates != fitted.receipt["gate_predicates"]:
        raise CutoffContractError("receipt-only gate replay differs")

    accepted = pd.read_parquet(
        repo_root / "results/low_n_selector_data/features/selector_cells.parquet"
    )
    accepted = accepted[accepted["issue_year"].isin([2022, 2023, 2024])]
    pivot = accepted.pivot(
        index=["issue", "issue_year", "match_idx"],
        columns="outcome_code",
        values=["q_candidate", "q_line"],
    ).reset_index()
    pivot.columns = [
        column
        if isinstance(column, str)
        else (column[0] if not column[1] else f"{column[0]}_{column[1]}")
        for column in pivot.columns
    ]
    current = fitted.mapped.rename(columns={"issue_code": "issue"})
    parity = current.merge(
        pivot,
        on=["issue", "issue_year", "match_idx"],
        suffixes=("_382", "_354"),
        validate="one_to_one",
    )
    for prefix in ["q_candidate", "q_line"]:
        for code in OUTCOMES:
            parity[f"exact_{prefix}_{code}"] = np.isclose(
                parity[f"{prefix}_{code}_382"],
                parity[f"{prefix}_{code}_354"],
                rtol=0,
                atol=1e-12,
            )
    exact_columns = [name for name in parity if name.startswith("exact_")]
    parity["exact_354"] = parity[exact_columns].all(axis=1)
    equivalence = pd.DataFrame(
        [
            {
                "year_cutoff_identity": year_cutoff.identity,
                "last_issue_cutoff_identity": issue_cutoff.identity,
                "cutoff_ts": cutoff_ts.isoformat(),
                "same_model_identity": fitted.receipt["model_identity"]
                == equivalent.receipt["model_identity"],
                "same_scientific_output": fitted.receipt["scientific_output_sha256"]
                == equivalent.receipt["scientific_output_sha256"],
                "cache_keys_distinct": fitted.receipt["cache_key"]
                != equivalent.receipt["cache_key"],
            }
        ]
    )
    source = {
        "contract": CONTRACT_ID,
        "source_hashes": source_hashes,
        "accepted_354_manifest_sha256": sha256_file(
            repo_root / "results/low_n_selector_data/MANIFEST.json"
        ),
        "target_rows": len(target),
        "target_issues": int(target["issue_code"].nunique()),
        "evaluation_years": [2022, 2023, 2024],
        "implementation": fitted.receipt["implementation"],
        "availability": fitted.receipt["availability"],
    }
    decision = {
        "contract": CONTRACT_ID,
        "verdict": "CUTOFF_MAPPING_INTERFACE_READY",
        "mapping_accepted": fitted.accepted,
        "exact_354_rows": int(parity["exact_354"].sum()),
        "parity_rows": len(parity),
        "equivalent_cutoffs_same_science": bool(
            equivalence["same_scientific_output"].iloc[0]
        ),
        "cache_keys_cutoff_bound": bool(equivalence["cache_keys_distinct"].iloc[0]),
        "future_consumers_must_pass_cutoff_explicitly": True,
    }
    return {
        "source": source,
        "receipt": fitted.receipt,
        "mapped": fitted.mapped,
        "weights": fitted.weights,
        "parity": parity,
        "equivalence": equivalence,
        "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "mapping_receipt.json": "receipt",
    "mapped_probabilities.parquet": "mapped",
    "accepted_354_parity.parquet": "parity",
    "weight_ledger.parquet": "weights",
    "equivalent_cutoff_receipt.csv": "equivalence",
    "decision.json": "decision",
}

DELIVERY_FILES = (
    "docs/research/Issue-382-Cutoff-Learning.md",
    "notebooks/research/cutoff-learning/Issue-382-Cutoff-Learning.ipynb",
    "docs/research/temporal-function-inventory.csv",
    "docs/research/templates/cutoff-learning-contract.md",
    "docs/research/templates/cutoff-learning-review.md",
)


def _write(path: Path, value: Any) -> None:
    if isinstance(value, pd.DataFrame):
        if path.suffix == ".parquet":
            value.to_parquet(path, index=False)
        else:
            value.to_csv(path, index=False)
    else:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def build_package(
    repo_root: Path,
    target: Path,
    explicit_data_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    frames = scientific_frames(repo_root, data_root)

    def populate(staging: Path) -> None:
        for relative, key in PACKAGE_FILES.items():
            _write(staging / relative, frames[key])
        manifest = {
            "contract": CONTRACT_ID,
            "files": {
                name: {
                    "sha256": sha256_file(staging / name),
                    "bytes": (staging / name).stat().st_size,
                }
                for name in sorted(PACKAGE_FILES)
            },
            "implementation": {
                "api.py": sha256_file(Path(__file__).with_name("api.py")),
                "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
                "package.py": sha256_file(Path(__file__)),
                "temporal_learning/core.py": sha256_file(
                    repo_root / "packages/beidan/inst/python/beidan_backend/temporal_learning/core.py"
                ),
                "temporal_learning/example_selector.py": sha256_file(
                    repo_root / "packages/beidan/inst/python/beidan_backend/temporal_learning/example_selector.py"
                ),
            },
            "deliveries": {
                name: sha256_file(repo_root / name) for name in DELIVERY_FILES
            },
        }
        (staging / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    atomic_publish_directory(target.resolve(), populate, force=force)
    return frames["decision"]


def verify_package(
    repo_root: Path, target: Path, explicit_data_root: Path | None = None
) -> dict[str, bool]:
    repo_root, target = repo_root.resolve(), target.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    manifest = _read_json(target / "MANIFEST.json")
    if manifest.get("contract") != CONTRACT_ID or set(manifest.get("files", {})) != set(
        PACKAGE_FILES
    ):
        raise CutoffContractError("manifest contract/file set mismatch")
    for relative, item in manifest["files"].items():
        if (
            not (target / relative).is_file()
            or sha256_file(target / relative) != item["sha256"]
        ):
            raise CutoffContractError(f"manifest mismatch: {relative}")
    expected_implementation = {
        "api.py": sha256_file(Path(__file__).with_name("api.py")),
        "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
        "package.py": sha256_file(Path(__file__)),
        "temporal_learning/core.py": sha256_file(
            repo_root / "packages/beidan/inst/python/beidan_backend/temporal_learning/core.py"
        ),
        "temporal_learning/example_selector.py": sha256_file(
            repo_root / "packages/beidan/inst/python/beidan_backend/temporal_learning/example_selector.py"
        ),
    }
    if manifest.get("implementation") != expected_implementation:
        raise CutoffContractError("implementation hashes differ")
    expected_deliveries = {
        name: sha256_file(repo_root / name) for name in DELIVERY_FILES
    }
    if manifest.get("deliveries") != expected_deliveries:
        raise CutoffContractError("delivery hashes differ")
    expected = scientific_frames(repo_root, data_root)
    for relative, key in PACKAGE_FILES.items():
        path, value = target / relative, expected[key]
        if isinstance(value, pd.DataFrame):
            actual = (
                pd.read_parquet(path)
                if path.suffix == ".parquet"
                else pd.read_csv(path)
            )
            try:
                pd.testing.assert_frame_equal(
                    actual,
                    value.reset_index(drop=True),
                    check_dtype=False,
                    check_exact=True,
                )
            except AssertionError as error:
                raise CutoffContractError(
                    f"scientific frame mismatch: {relative}"
                ) from error
        elif _read_json(path) != value:
            raise CutoffContractError(f"receipt mismatch: {relative}")
    receipt = expected["receipt"]
    if not pd.Timestamp(receipt["maximum_training_label_timestamp"]) < pd.Timestamp(
        receipt["cutoff_ts"]
    ):
        raise CutoffContractError("receipt training timestamp crosses cutoff")
    if (
        expected["equivalence"]["same_scientific_output"].dtype != bool
        or not expected["equivalence"]["same_scientific_output"].all()
    ):
        raise CutoffContractError("equivalent cutoff science differs")
    if not expected["equivalence"]["cache_keys_distinct"].all():
        raise CutoffContractError("cache key is not cutoff-bound")
    return {
        "manifest": True,
        "strict_prior_window": True,
        "derived_partitions": True,
        "gate_replay": True,
        "probability_replay": True,
        "equivalent_cutoff_science": True,
        "cache_cutoff_bound": True,
        "accepted_354_parity": True,
        "implementation_bound": True,
        "deliveries_bound": True,
    }
