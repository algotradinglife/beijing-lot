"""Explicit development-only label loader for the #203 package.

Importing this module is an intentional privilege boundary.  The default
``unified_tensor`` package and its inference loader do not import it.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .contract import CONTRACT_VERSION, HELDOUT_ISSUES, OUTCOME_ORDER, cell_join_key


class LabelContractError(RuntimeError):
    """Raised when development labels fail their physical/join contract."""


LABEL_COLUMNS = (
    "cell_join_key",
    "issue",
    "issue_instance",
    "match_id",
    "outcome_code",
    "result_code",
    "is_winner",
    "final_sp",
    "final_sp_available",
    "winning_zero_return_units",
    "payout_factor",
    "payout_after_65_units",
    "tax_rate",
    "tax_cliff_gross_yuan",
    "tax_realized_yuan",
    "tax_realized_available",
    "settlement_status",
    "settlement_quality",
    "settlement_source",
)


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_development_labels(package: str | Path) -> pd.DataFrame:
    expanded = Path(package).expanduser()
    if expanded.is_symlink():
        raise LabelContractError("label package root must not be a symlink")
    root = expanded.resolve()
    namespace = root if root.name == "labels" else root / "labels"
    if namespace.is_symlink():
        raise LabelContractError("label namespace root must not be a symlink")
    manifest_path = namespace / "MANIFEST.json"
    if manifest_path.is_symlink():
        raise LabelContractError("label manifest must be a regular package file")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LabelContractError("missing or invalid label manifest") from exc
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise LabelContractError("unsupported label contract version")
    if manifest.get("namespace") != "development_only_settlement_labels":
        raise LabelContractError("label namespace declaration is invalid")
    if manifest.get("heldout_label_status") != "ABSENT_BY_CONTRACT":
        raise LabelContractError("held-out label embargo is not declared")
    if manifest.get("heldout_issues") != list(HELDOUT_ISSUES):
        raise LabelContractError("held-out label identity declaration drift")
    payload = namespace / "development_labels.parquet"
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise LabelContractError("label manifest files are invalid")
    namespace_paths = list(namespace.rglob("*"))
    if any(path.is_symlink() for path in namespace_paths):
        raise LabelContractError("label namespace must not contain symlinks")
    actual_files = {
        path.relative_to(namespace).as_posix()
        for path in namespace_paths
        if path.is_file() and path.name != "MANIFEST.json"
    }
    if set(files) != {payload.name} or actual_files != {payload.name}:
        raise LabelContractError("label file census does not match contract")
    if not payload.is_file() or files.get(payload.name) != _digest(payload):
        raise LabelContractError("development label payload hash mismatch")
    labels = pd.read_parquet(payload)
    if tuple(labels.columns) != LABEL_COLUMNS:
        raise LabelContractError("development label schema does not match contract")
    if not labels["cell_join_key"].is_unique:
        raise LabelContractError("development label join keys are not unique")
    for column in ("is_winner", "final_sp_available", "tax_realized_available"):
        if labels[column].dtype != np.dtype("bool"):
            raise LabelContractError(f"label Boolean dtype drift: {column}")
    if labels["issue"].astype(str).isin(HELDOUT_ISSUES).any():
        raise LabelContractError("held-out labels were opened or emitted")
    if not bool(
        labels.apply(
            lambda row: str(row.issue_instance).startswith(
                f"{row.issue}@CANONICAL_"
            ),
            axis=1,
        ).all()
    ):
        raise LabelContractError("label issue instance does not bind issue")
    if not bool(labels["outcome_code"].astype(str).isin(OUTCOME_ORDER).all()):
        raise LabelContractError("label outcome code is invalid")
    match_groups = labels.groupby(
        ["issue_instance", "match_id"], sort=False, dropna=False
    )
    if not bool(match_groups.size().eq(len(OUTCOME_ORDER)).all()):
        raise LabelContractError("each labeled match must contain three outcome cells")
    outcome_sequences = match_groups["outcome_code"].agg(
        lambda values: tuple(values.astype(str))
    )
    if not bool(outcome_sequences.map(lambda value: value == OUTCOME_ORDER).all()):
        raise LabelContractError("label cells do not follow canonical 3,1,0 order")
    for field in (
        "issue", "result_code", "settlement_status", "settlement_quality",
        "settlement_source",
    ):
        if not bool(match_groups[field].nunique(dropna=False).eq(1).all()):
            raise LabelContractError(f"match label field is inconsistent: {field}")
    numeric = {
        column: pd.to_numeric(labels[column], errors="coerce").to_numpy(dtype=float)
        for column in (
            "final_sp", "winning_zero_return_units", "payout_factor",
            "payout_after_65_units", "tax_rate", "tax_cliff_gross_yuan",
            "tax_realized_yuan",
        )
    }
    if not np.allclose(numeric["payout_factor"], 0.65, rtol=0, atol=1e-12):
        raise LabelContractError("payout factor must equal 0.65 exactly once")
    if not np.allclose(numeric["tax_rate"], 0.20, rtol=0, atol=1e-12):
        raise LabelContractError("tax rate contract drift")
    if not np.allclose(
        numeric["tax_cliff_gross_yuan"], 10_000.0, rtol=0, atol=1e-12
    ):
        raise LabelContractError("tax cliff contract drift")
    final_sp_available = labels["final_sp_available"].to_numpy(dtype=bool)
    if not np.array_equal(
        final_sp_available,
        np.isfinite(numeric["final_sp"]) & (numeric["final_sp"] > 0),
    ):
        raise LabelContractError("final-SP availability mask is inconsistent")
    tax_available = labels["tax_realized_available"].to_numpy(dtype=bool)
    if bool(tax_available.any()) or bool(
        np.isfinite(numeric["tax_realized_yuan"]).any()
    ):
        raise LabelContractError("cell labels cannot realize ticket-level tax")
    trusted = labels["settlement_status"].astype(str).eq("SETTLED_TRUSTED")
    allowed_statuses = {
        "SETTLED_TRUSTED",
        "UNAVAILABLE_CANONICAL_SETTLEMENT",
    }
    if not bool(labels["settlement_status"].astype(str).isin(allowed_statuses).all()):
        raise LabelContractError("settlement status is outside the contract")
    if not bool(
        labels.loc[trusted, "settlement_quality"].astype(str).eq("trusted").all()
    ):
        raise LabelContractError("trusted settlement quality is inconsistent")
    untrusted = ~trusted.to_numpy(dtype=bool)
    winner = labels["is_winner"].to_numpy(dtype=bool)
    expected_winner = (
        trusted
        & labels["outcome_code"].astype(str).eq(labels["result_code"].astype(str))
    ).to_numpy(dtype=bool)
    if not np.array_equal(winner, expected_winner):
        raise LabelContractError("winner flag does not match trusted result identity")
    trusted_values = trusted.to_numpy(dtype=bool)
    losing_trusted = trusted_values & ~winner
    if bool(
        (numeric["winning_zero_return_units"][losing_trusted] != 0.0).any()
    ):
        raise LabelContractError("trusted losing cells must have zero return")
    if bool(
        (~np.isfinite(numeric["winning_zero_return_units"][winner])).any()
        or (numeric["winning_zero_return_units"][winner] <= 0).any()
    ):
        raise LabelContractError("trusted winning cells must have positive return")
    if bool(
        labels.loc[untrusted, "result_code"].astype(str).ne("").any()
        or final_sp_available[untrusted].any()
        or np.isfinite(numeric["final_sp"][untrusted]).any()
        or np.isfinite(numeric["winning_zero_return_units"][untrusted]).any()
        or np.isfinite(numeric["payout_after_65_units"][untrusted]).any()
        or winner[untrusted].any()
    ):
        raise LabelContractError("unavailable settlement rows must not carry targets")
    trusted_winners = (
        labels.assign(_trusted_winner=winner & trusted.to_numpy(dtype=bool))
        .groupby(["issue_instance", "match_id"], sort=False)["_trusted_winner"]
        .sum()
    )
    trusted_matches = (
        match_groups["settlement_status"]
        .first()
        .eq("SETTLED_TRUSTED")
    )
    if not bool((trusted_winners[trusted_matches] == 1).all()):
        raise LabelContractError("trusted match must have exactly one winning cell")
    expected_payout = numeric["winning_zero_return_units"] * 0.65
    comparable = np.isfinite(expected_payout) | np.isfinite(
        numeric["payout_after_65_units"]
    )
    if not np.allclose(
        numeric["payout_after_65_units"][comparable],
        expected_payout[comparable],
        rtol=0,
        atol=1e-12,
        equal_nan=True,
    ):
        raise LabelContractError("0.65 payout is not applied exactly once")
    for row in labels.itertuples(index=False):
        expected = cell_join_key(
            str(row.issue_instance), str(row.match_id), str(row.outcome_code)
        )
        if str(row.cell_join_key) != expected:
            raise LabelContractError("label join key does not bind exact identity")
        settled = str(row.settlement_status) == "SETTLED_TRUSTED"
        if settled and str(row.result_code) not in OUTCOME_ORDER:
            raise LabelContractError("trusted settlement lacks canonical result")
    return labels


def bind_development_labels(
    inference_identity: pd.DataFrame, labels: pd.DataFrame
) -> pd.DataFrame:
    """Fail closed unless labels cover exactly the development cell identities."""

    required = {"cell_join_key", "split", "issue", "match_id", "outcome_code"}
    if not required.issubset(inference_identity.columns):
        raise LabelContractError("inference identity is incomplete")
    development = inference_identity[
        inference_identity["split"].astype(str).eq("development")
    ]
    if development["cell_join_key"].astype(str).tolist() != labels[
        "cell_join_key"
    ].astype(str).tolist():
        raise LabelContractError(
            "development labels do not exactly cover ordered inference identities"
        )
    return development.merge(
        labels,
        on=["cell_join_key", "issue", "match_id", "outcome_code"],
        how="inner",
        validate="one_to_one",
        suffixes=("", "_label"),
        sort=False,
    )
