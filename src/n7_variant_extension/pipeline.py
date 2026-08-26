"""Build the Issue #400 corrected-N7 2025/2026 variant atlas.

The module deliberately reuses the accepted chronology, mapping, selector,
support-ranking and ticket-allocation implementations.  It only orchestrates
their frozen variants on the newly consumed extension settlement calendar.
"""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient
from threadpoolctl import threadpool_limits

from src.cutoff_walkforward.fitting import fit_issue_mapping
from src.cutoff_mapping.api import replay_mapped
from src.n7_chronology_sync.pipeline import locate_data_root
from src.n7_mixed_full_history.pipeline import (
    _action_surface,
    _baseline_support,
    _extension_panel,
    _maximal_assignment,
    _pre_extension_boundary,
    _primary_support,
    _rank_shape_pair,
    _ticket_units_flexible as mixed_ticket_units,
    sha256_file,
    stable_frame_sha,
)
from src.n7_support_shape.pipeline import _ticket_units as shape_ticket_units
from src.n7_support_transfer_grid.pipeline import _ticket_units as grid_ticket_units
from src.source_schema.publication import atomic_publish_directory
from src.temporal_learning import (
    Cutoff,
    implementation_closure,
    verify_implementation_closure,
)
from src.temporal_learning.core import stable_frame_hash as temporal_frame_sha

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    CONTRACTION_COUNTS,
    EXPANSION_COUNTS,
    FIGURE_PATH,
    FIT_THREAD_LIMIT,
    FUNDED_UNITS,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    MOVING_BLOCK_LENGTH,
    NOTEBOOK_PATH,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    POLICIES,
    REPORT_PATH,
    RESULT_PACKAGE,
    SOURCE_MERGE_SHA,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    VERDICT,
    YEARS,
)


class ContractError(ValueError):
    """Raised when a frozen scientific or accounting invariant fails."""


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode()).hexdigest()


def _load_mixed_history_package(repo_root: Path) -> dict[str, Any]:
    """Load the immutable accepted #394 interface without replaying ancestors."""

    package = repo_root / "results/n7_mixed_full_history"
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    for name, item in manifest["files"].items():
        if sha256_file(package / name) != item["sha256"]:
            raise ContractError(f"accepted #394 package hash differs for {name}")
    return {
        "history": pd.read_parquet(package / "extension_history.parquet"),
        "extension_settlement": pd.read_parquet(
            package / "extension_settlement.parquet"
        ),
        "bundles": pd.read_parquet(package / "bundles.parquet"),
        "decision": json.loads((package / "decision.json").read_text(encoding="utf-8")),
        "source": json.loads(
            (package / "source_receipt.json").read_text(encoding="utf-8")
        ),
    }


def _variant_seed(variant: str, reference: str, scope: str) -> int:
    digest = hashlib.sha256(f"{variant}|{reference}|{scope}".encode()).hexdigest()
    return BOOTSTRAP_SEED + int(digest[:6], 16)


def _fit_policy_surface(
    repo_root: Path,
    history: pd.DataFrame,
    eligible_target: pd.DataFrame,
    source_hashes: dict[str, str],
    policy: str,
    checkpoint_root: Path,
    admitted_receipts: dict[str, dict[str, Any]],
) -> tuple[pd.DataFrame, list[dict[str, Any]], pd.DataFrame]:
    """Fit the accepted temporal policy at each target decision epoch.

    The policy definition is frozen by #392, while the learned artifact is
    rebuilt issue-by-issue from labels actually available before that issue.
    This is the repository-wide cutoff contract: later 2025/2026 outcomes may
    enter later targets, but can never reach an earlier target.
    """

    closure = implementation_closure(
        repo_root,
        ("src.cutoff_mapping.api", "src.cutoff_walkforward.fitting"),
        distributions=("numpy", "pandas", "scikit-learn"),
    )
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    checkpoint_index: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for receipt_path in sorted((checkpoint_root / policy).glob("*/receipt.json")):
        candidate_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        checkpoint_index.setdefault(
            str(candidate_receipt.get("cutoff_identity", "")), []
        ).append((receipt_path.parent, candidate_receipt))
    receipts: list[dict[str, Any]] = []
    epochs = (
        eligible_target.groupby("issue_code", observed=True)["fixture_decision_ts"]
        .min()
        .sort_values(kind="stable")
    )
    mapped_parts: list[pd.DataFrame] = []
    weight_parts: list[pd.DataFrame] = []
    for issue, epoch in epochs.items():
        target = eligible_target[
            eligible_target["issue_code"].astype(str).eq(str(issue))
        ].copy()
        cutoff = Cutoff.decision_epoch(str(issue), pd.Timestamp(epoch))
        admitted_receipt = admitted_receipts[str(issue)]
        target_hash = stable_frame_sha(target)
        issue_source_hashes = {
            **source_hashes,
            "admitted_candidate_frame_sha256": admitted_receipt["sha256"],
            "target_feature_frame_sha256": target_hash,
            "fit_thread_limit": str(FIT_THREAD_LIMIT),
        }
        checkpoint_key = _json_hash(
            {
                "contract": CONTRACT_ID,
                "policy": policy,
                "cutoff_identity": cutoff.identity,
                "cutoff_ts": cutoff.cutoff_ts.isoformat(),
                "source_hashes": dict(sorted(issue_source_hashes.items())),
                "implementation_closure_sha256": closure["closure_sha256"],
            }
        )
        checkpoint = checkpoint_root / policy / checkpoint_key
        matches: list[tuple[Path, dict[str, Any]]] = []
        for candidate_path, candidate_receipt in checkpoint_index.get(
            cutoff.identity, []
        ):
            candidate_sources = dict(candidate_receipt.get("source_hashes", {}))
            if (
                candidate_sources.get("fit_thread_limit")
                != str(FIT_THREAD_LIMIT)
                or candidate_sources.get("target_feature_frame_sha256")
                != target_hash
                or any(
                    candidate_sources.get(key) != value
                    for key, value in source_hashes.items()
                )
                or candidate_receipt.get("admitted_history_sha256")
                != admitted_receipt["sha256"]
                or int(candidate_receipt["partition"]["final_refit_rows"])
                != int(admitted_receipt["rows"])
            ):
                continue
            matches.append((candidate_path, candidate_receipt))
        if len(matches) > 1:
            outputs = {
                str(receipt["scientific_output_sha256"])
                for _, receipt in matches
            }
            if len(outputs) != 1:
                raise ContractError("competing checkpoint outputs differ")
        if matches:
            checkpoint, result_receipt = matches[0]
        receipt_path = checkpoint / "receipt.json"
        mapped_path = checkpoint / "mapped.parquet"
        if receipt_path.is_file() and mapped_path.is_file():
            if not matches:
                result_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if result_receipt["cutoff_identity"] != cutoff.identity:
                raise ContractError("checkpoint cutoff identity differs")
            if (
                result_receipt["admitted_history_sha256"]
                != admitted_receipt["sha256"]
            ):
                raise ContractError("checkpoint admitted history differs")
            verify_implementation_closure(
                repo_root, dict(result_receipt["implementation"])
            )
            result_mapped = pd.read_parquet(mapped_path)
            replayed = replay_mapped(
                target, result_receipt, repository_root=repo_root
            )
            if stable_frame_sha(result_mapped) != stable_frame_sha(replayed):
                raise ContractError("checkpoint mapped probabilities differ")
            accepted = bool(result_receipt["mapping_accepted"])
        else:
            with threadpool_limits(limits=FIT_THREAD_LIMIT):
                result = fit_issue_mapping(
                    history,
                    target,
                    cutoff,
                    repository_root=repo_root,
                    source_hashes=issue_source_hashes,
                    policy_name=policy,
                )
            result_receipt = result.receipt
            result_mapped = result.mapped
            accepted = bool(result.accepted)
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=f".{checkpoint_key}-", dir=checkpoint.parent
            ) as temporary:
                staging = Path(temporary)
                result_mapped.to_parquet(staging / "mapped.parquet", index=False)
                (staging / "receipt.json").write_text(
                    json.dumps(result_receipt, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                staging.rename(checkpoint)
        issue_mapped = result_mapped.assign(
            policy=policy,
            issue_gate_accepted=accepted,
        )
        for outcome in OUTCOMES:
            issue_mapped[f"q_effective_{outcome}"] = np.where(
                accepted,
                issue_mapped[f"q_candidate_{outcome}"],
                issue_mapped[f"q_line_{outcome}"],
            )
        mapped_parts.append(issue_mapped)
        receipt = {
            **result_receipt,
            "target_issue": str(issue),
            "evaluation_epoch": pd.Timestamp(epoch).isoformat(),
            "issue_level_walk_forward": True,
            "fit_implementation_closure_sha256": closure["closure_sha256"],
        }
        receipts.append(
            {
                "issue": str(issue),
                "issue_year": int(target["issue_year"].iloc[0]),
                "policy": policy,
                "receipt": receipt,
            }
        )
        # The complete row-level weight vector is already bound by the two
        # semantic hashes in the fit receipt.  Persisting it once per target
        # issue would duplicate the expanding history hundreds of times and
        # turn a small audit table into tens of millions of rows.  Keep the
        # decision-facing summary and exact hashes instead.
        weight_receipt = result_receipt["weight_receipt"]
        weight_parts.append(
            pd.DataFrame(
                [
                    {
                        "target_issue": str(issue),
                        "issue_year": int(target["issue_year"].iloc[0]),
                        "cutoff_ts": cutoff.cutoff_ts.isoformat(),
                        "policy": policy,
                        "rows": int(weight_receipt["rows"]),
                        "sum": float(weight_receipt["sum"]),
                        "minimum": float(weight_receipt["minimum"]),
                        "maximum": float(weight_receipt["maximum"]),
                        "effective_sample_size": float(
                            weight_receipt["effective_sample_size"]
                        ),
                        "long_history_mass": float(
                            weight_receipt["long_history_mass"]
                        ),
                        "recent_state_mass": float(
                            weight_receipt["recent_state_mass"]
                        ),
                        "weight_frame_sha256": weight_receipt[
                            "weight_frame_sha256"
                        ],
                        "issue_mass_sha256": weight_receipt[
                            "issue_mass_sha256"
                        ],
                    }
                ]
            )
        )
    mapped = pd.concat(mapped_parts, ignore_index=True)
    if mapped.duplicated(["issue_code", "match_idx", "policy"]).any():
        raise ContractError("policy mapping keys are not unique")
    return mapped, receipts, pd.concat(weight_parts, ignore_index=True)


def _admitted_history_receipts(
    history: pd.DataFrame, eligible_target: pd.DataFrame
) -> dict[str, dict[str, Any]]:
    """Vectorize the exact shared-API admitted-history hashes for all targets."""

    admissible = history[
        history["target_outcome"].astype(str).isin(OUTCOMES)
        & history["native_line_supported"].eq(True)
    ].copy()
    admissible["issue_code"] = admissible["issue_code"].astype(str)
    admissible["label_available_ts"] = pd.to_datetime(
        admissible["label_available_ts"], utc=True
    )
    admissible["fixture_decision_ts"] = pd.to_datetime(
        admissible["fixture_decision_ts"], utc=True
    )
    epochs = (
        eligible_target.groupby("issue_code", observed=True)["fixture_decision_ts"]
        .min()
        .sort_values(kind="stable")
    )
    receipts: dict[str, dict[str, Any]] = {}
    hash_cache: dict[str, str] = {}
    for issue, epoch in epochs.items():
        cutoff_ts = pd.Timestamp(epoch)
        mask = (
            admissible["label_available_ts"].lt(cutoff_ts)
            & admissible["fixture_decision_ts"].lt(cutoff_ts)
            & admissible["issue_code"].ne(str(issue))
        ).to_numpy(bool)
        if admissible.loc[mask, "issue_code"].eq(str(issue)).any():
            raise ContractError("target issue entered its own admitted history")
        mask_identity = hashlib.sha256(mask.tobytes()).hexdigest()
        if mask_identity not in hash_cache:
            hash_cache[mask_identity] = temporal_frame_sha(
                admissible.loc[mask].reset_index(drop=True)
            )
        receipts[str(issue)] = {
            "sha256": hash_cache[mask_identity],
            "rows": int(mask.sum()),
            "maximum_label_available_ts": admissible.loc[
                mask, "label_available_ts"
            ].max().isoformat(),
        }
    return receipts


def _extension_learning_history(
    base_history: pd.DataFrame,
    eligible_target: pd.DataFrame,
    settlement: pd.DataFrame,
) -> pd.DataFrame:
    """Append trustworthy extension labels with their actual availability.

    Target features remain the pre-outcome 10h panel. Settlement contributes
    only the label and its availability timestamp. The shared cutoff client
    decides which rows are admissible for each target issue.
    """

    labels = settlement.loc[
        settlement["settlement_available"].astype(bool),
        ["issue", "match_idx", "result_code", "availability_ts"],
    ].copy()
    labels = labels.rename(
        columns={
            "issue": "issue_code",
            "result_code": "target_outcome",
            "availability_ts": "label_available_ts_actual",
        }
    )
    labels["issue_code"] = labels["issue_code"].astype(str)
    labels["match_idx"] = labels["match_idx"].astype(int)
    labeled = eligible_target.merge(
        labels,
        on=["issue_code", "match_idx"],
        how="inner",
        validate="one_to_one",
    )
    labeled["label_available_ts"] = pd.to_datetime(
        labeled.pop("label_available_ts_actual"), utc=True
    )
    labeled["target_outcome"] = labeled["target_outcome"].astype(str)
    labeled["label_available"] = True
    labeled = labeled[labeled["target_outcome"].isin(OUTCOMES)].copy()
    columns = sorted(set(base_history.columns) | set(labeled.columns))
    combined = pd.concat(
        [base_history.reindex(columns=columns), labeled.reindex(columns=columns)],
        ignore_index=True,
    )
    combined["issue_code"] = combined["issue_code"].astype(str)
    combined["label_available_ts"] = pd.to_datetime(
        combined["label_available_ts"], utc=True
    )
    # Accepted #394 history predates the extension.  Some early source rows do
    # not carry the later match_idx field, so uniqueness must be proven on the
    # newly appended extension keys and on the disjoint issue boundary rather
    # than treating repeated null match_idx values as collisions.
    if set(base_history["issue_code"].astype(str)) & set(
        labeled["issue_code"].astype(str)
    ):
        raise ContractError("extension learning issues overlap accepted history")
    if labeled.duplicated(["issue_code", "match_idx"]).any():
        raise ContractError("extension learning keys are not unique")
    return combined.sort_values(
        ["label_available_ts", "issue_code", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def _ranked_supports(
    selected: pd.DataFrame, base_support: dict[int, tuple[str, ...]]
) -> tuple[pd.DataFrame, list[int], list[int]]:
    _, _, scores = _rank_shape_pair(selected, base_support)
    contraction, expansion = _maximal_assignment(scores)
    return scores.set_index("match_idx"), contraction, expansion


def _support_for(
    base_support: dict[int, tuple[str, ...]],
    scores: pd.DataFrame,
    contraction_order: list[int],
    expansion_order: list[int],
    contraction: int,
    expansion: int,
) -> dict[int, tuple[str, ...]]:
    support = dict(base_support)
    for match_idx in contraction_order[:contraction]:
        support[match_idx] = (str(scores.loc[match_idx, "retained_outcome"]),)
    for match_idx in expansion_order[:expansion]:
        support[match_idx] = OUTCOMES
    return support


def _ticket_codes(
    support: dict[int, tuple[str, ...]], fixture_order: list[int]
) -> list[str]:
    return [
        "|".join(values)
        for values in itertools.product(*(support[idx] for idx in fixture_order))
    ]


def _settle_variant(
    *,
    issue: str,
    year: int,
    anchor: pd.Timestamp,
    policy: str,
    variant: str,
    family: str,
    base: str,
    contraction: int,
    expansion: int,
    selected: pd.DataFrame,
    support: dict[int, tuple[str, ...]],
    allocator: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    fixture_order = selected["match_idx"].astype(int).tolist()
    codes = _ticket_codes(support, fixture_order)
    expected = (2 ** (N_LEGS - contraction - expansion)) * (3**expansion)
    if len(codes) != expected or len(set(codes)) != expected or expected > FUNDED_UNITS:
        raise ContractError(f"{variant}: invalid complete Cartesian ticket count")
    if allocator == "GRID_373":
        units = grid_ticket_units(issue, f"C{contraction}E{expansion}", codes)
    elif allocator == "SHAPE_369":
        shape = {
            (0, 0): "CONTROL",
            (1, 0): "CONTRACTION_ONLY",
            (0, 1): "EXPANSION_ONLY",
            (1, 1): "BOTH",
        }[(contraction, expansion)]
        units = shape_ticket_units(issue, base, shape, codes)
    else:
        raise ContractError(f"unknown allocator {allocator}")
    if sum(units.values()) != FUNDED_UNITS or min(units.values()) < 1:
        raise ContractError(f"{variant}: funded units do not reconcile")

    realized = selected["result_code"].fillna("").astype(str).tolist()
    trusted = bool(selected["settlement_available"].astype(bool).all())
    winning_code = "|".join(realized)
    winning_units = int(units.get(winning_code, 0)) if trusted else 0
    product_sp = float(selected["winning_sp"].astype(float).prod()) if trusted else math.nan
    gross = (
        winning_units * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR * product_sp
        if trusted
        else math.nan
    )
    selected_ids = "|".join(map(str, fixture_order))
    bundle = {
        "issue": issue,
        "issue_year": int(year),
        "issue_anchor_ts": anchor,
        "policy": policy,
        "variant": variant,
        "family": family,
        "base": base,
        "contraction_count": contraction,
        "expansion_count": expansion,
        "allocator": allocator,
        "selected_match_ids": selected_ids,
        "support_json": _stable_json({str(k): "".join(v) for k, v in support.items()}),
        "ticket_count": expected,
        "funded_units": FUNDED_UNITS,
        "stake_cny": ISSUE_STAKE_CNY if trusted else math.nan,
        "gross_cny": gross,
        "pnl_cny": gross - ISSUE_STAKE_CNY if trusted else math.nan,
        "ticket_hit": bool(trusted and winning_units > 0),
        "issue_profitable": bool(trusted and gross > ISSUE_STAKE_CNY),
        "winning_ticket_units": winning_units,
        "winning_sp_product": product_sp,
        "native_included": trusted,
    }
    ticket_rows = [
        {
            "issue": issue,
            "issue_year": int(year),
            "policy": policy,
            "variant": variant,
            "ticket_ordinal": ordinal,
            "ticket_code": code,
            "ticket_identity": "|".join(
                f"{match_idx}:{outcome}"
                for match_idx, outcome in zip(
                    fixture_order, code.split("|"), strict=True
                )
            ),
            "units": int(units[code]),
            "stake_cny": float(units[code] * STAKE_PER_UNIT_CNY),
        }
        for ordinal, code in enumerate(codes)
    ]
    attr_rows = []
    for row in selected.itertuples():
        choices = support[int(row.match_idx)]
        attr_rows.append(
            {
                "issue": issue,
                "issue_year": int(year),
                "policy": policy,
                "variant": variant,
                "match_idx": int(row.match_idx),
                "active_support": "".join(choices),
                "result_code": str(row.result_code),
                "winning_sp": float(row.winning_sp) if trusted else math.nan,
                "settlement_available": bool(row.settlement_available),
                "realized_in_support": bool(str(row.result_code) in choices),
                "exclusion_reason": str(getattr(row, "exclusion_reason", "")),
                "exclusion_source_payload_sha256": str(
                    getattr(row, "exclusion_source_payload_sha256", "")
                ),
            }
        )
    return bundle, ticket_rows, attr_rows


def _construct_policy_variants(
    action: pd.DataFrame, policy: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bundles: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    attribution: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    for (issue, year, anchor), group in action.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        selected = (
            group.sort_values(
                ["retained_mass", "match_idx"],
                ascending=[False, True],
                kind="stable",
            )
            .head(N_LEGS)
            .sort_values("match_idx", kind="stable")
            .copy()
        )
        if len(selected) != N_LEGS:
            continue
        fixture_order = selected["match_idx"].astype(int).tolist()
        selections.append(
            {
                "issue": str(issue),
                "issue_year": int(year),
                "policy": policy,
                "issue_anchor_ts": anchor,
                "selected_match_ids": "|".join(map(str, fixture_order)),
                "settlement_complete": bool(
                    selected["settlement_available"].astype(bool).all()
                ),
            }
        )
        r0 = _baseline_support(selected)
        r3 = _primary_support(selected)
        r0_scores, r0_c, r0_e = _ranked_supports(selected, r0)
        r3_scores, r3_c, r3_e = _ranked_supports(selected, r3)

        specs: list[tuple[str, str, str, int, int, dict[int, tuple[str, ...]], str]] = []
        if policy == "EXPANDING_EQUAL":
            for c, e in ((0, 0), (1, 0), (0, 1), (1, 1)):
                specs.append(
                    (
                        f"R0_C{c}E{e}_EQUAL",
                        "R0_SHAPE_369",
                        "R0_CORRECTED",
                        c,
                        e,
                        _support_for(r0, r0_scores, r0_c, r0_e, c, e),
                        "SHAPE_369",
                    )
                )
            for c in CONTRACTION_COUNTS:
                for e in EXPANSION_COUNTS:
                    specs.append(
                        (
                            f"R3_C{c}E{e}_EQUAL",
                            "R3_GRID_373",
                            "R3_CORRECTED",
                            c,
                            e,
                            _support_for(r3, r3_scores, r3_c, r3_e, c, e),
                            "GRID_373",
                        )
                    )
        else:
            short = "EXP730" if policy == "EXPANDING_EXPONENTIAL" else "BLEND75_25"
            for c, e in ((0, 0), (1, 3)):
                specs.append(
                    (
                        f"R3_C{c}E{e}_{short}",
                        "R3_TEMPORAL_392",
                        "R3_CORRECTED",
                        c,
                        e,
                        _support_for(r3, r3_scores, r3_c, r3_e, c, e),
                        "GRID_373",
                    )
                )
        for variant, family, base, c, e, support, allocator in specs:
            bundle, ticket_rows, attr_rows = _settle_variant(
                issue=str(issue),
                year=int(year),
                anchor=anchor,
                policy=policy,
                variant=variant,
                family=family,
                base=base,
                contraction=c,
                expansion=e,
                selected=selected,
                support=support,
                allocator=allocator,
            )
            bundles.append(bundle)
            tickets.extend(ticket_rows)
            attribution.extend(attr_rows)
    return (
        pd.DataFrame(bundles),
        pd.DataFrame(tickets),
        pd.DataFrame(attribution),
        pd.DataFrame(selections),
    )


def _add_mixed_portfolio(
    bundles: pd.DataFrame, base_frames: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Append the exact accepted #394 integer 50/50 issue flow and tickets."""

    source = base_frames["bundles"].copy()
    source = source[
        source["issue_year"].isin(YEARS)
        & source["schedule"].eq("MIXED_50_50")
    ]
    rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    settlement = base_frames["extension_settlement"].copy()
    settlement["issue"] = settlement["issue"].astype(str)
    for (issue, year, anchor), group in source.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], observed=True, sort=True
    ):
        trusted = bool(group["native_included"].astype(bool).all())
        rows.append(
            {
                "issue": str(issue),
                "issue_year": int(year),
                "issue_anchor_ts": anchor,
                "policy": "EXPANDING_EQUAL_FROZEN_394",
                "variant": "MIX_R3_C0E0_C1E3_50_50_EQUAL",
                "family": "MIXED_394",
                "base": "MIXED_R3_C1E3",
                "contraction_count": -1,
                "expansion_count": -1,
                "allocator": "MIXED_394_INTEGER",
                "selected_match_ids": "|".join(sorted(group["selected_match_ids"].unique())),
                "support_json": _stable_json(
                    {
                        str(row.support_arm): json.loads(str(row.support_json))
                        for row in group.itertuples()
                    }
                ),
                "ticket_count": int(group["ticket_count"].sum()),
                "funded_units": int(group["funded_units"].sum()),
                "stake_cny": float(group["stake_cny"].sum()) if trusted else math.nan,
                "gross_cny": float(group["gross_cny"].sum()) if trusted else math.nan,
                "pnl_cny": float(group["pnl_cny"].sum()) if trusted else math.nan,
                "ticket_hit": bool(trusted and group["ticket_hit"].any()),
                "issue_profitable": bool(trusted and group["pnl_cny"].sum() > 0),
                "winning_ticket_units": int(group["winning_ticket_units"].sum()),
                "winning_sp_product": math.nan,
                "native_included": trusted,
            }
        )
        for arm_row in group.itertuples():
            arm = str(arm_row.support_arm)
            fixture_order = [
                int(value) for value in str(arm_row.selected_match_ids).split("|")
            ]
            support_raw = json.loads(str(arm_row.support_json))
            support = {
                int(match_idx): tuple(str(values))
                for match_idx, values in support_raw.items()
            }
            codes = _ticket_codes(support, fixture_order)
            cell = "C0E0" if arm == "R3_CONTROL" else "C1E3"
            units = mixed_ticket_units(str(issue), cell, codes, int(arm_row.funded_units))
            if sum(units.values()) != int(arm_row.funded_units):
                raise ContractError("mixed arm funded units do not reconcile")
            for ordinal, code in enumerate(codes):
                ticket_rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(year),
                        "policy": "EXPANDING_EQUAL_FROZEN_394",
                        "variant": "MIX_R3_C0E0_C1E3_50_50_EQUAL",
                        "portfolio_arm": arm,
                        "ticket_ordinal": ordinal,
                        "ticket_code": code,
                        "ticket_identity": arm
                        + "|"
                        + "|".join(
                            f"{match_idx}:{outcome}"
                            for match_idx, outcome in zip(
                                fixture_order, code.split("|"), strict=True
                            )
                        ),
                        "units": int(units[code]),
                        "stake_cny": float(units[code] * STAKE_PER_UNIT_CNY),
                    }
                )
            settled = settlement[
                settlement["issue"].eq(str(issue))
                & settlement["match_idx"].astype(int).isin(fixture_order)
            ].set_index("match_idx")
            for match_idx in fixture_order:
                row = settled.loc[match_idx] if match_idx in settled.index else None
                choices = support[match_idx]
                attribution_rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(year),
                        "policy": "EXPANDING_EQUAL_FROZEN_394",
                        "variant": "MIX_R3_C0E0_C1E3_50_50_EQUAL",
                        "portfolio_arm": arm,
                        "match_idx": match_idx,
                        "active_support": "".join(choices),
                        "result_code": "" if row is None else str(row["result_code"]),
                        "winning_sp": math.nan
                        if row is None
                        else float(row["winning_sp"]),
                        "settlement_available": False
                        if row is None
                        else bool(row["settlement_available"]),
                        "realized_in_support": False
                        if row is None
                        else bool(str(row["result_code"]) in choices),
                        "exclusion_reason": ""
                        if row is None
                        else str(row.get("exclusion_reason", "")),
                        "exclusion_source_payload_sha256": ""
                        if row is None
                        else str(row.get("exclusion_source_payload_sha256", "")),
                    }
                )
    return (
        pd.concat([bundles, pd.DataFrame(rows)], ignore_index=True),
        pd.DataFrame(ticket_rows),
        pd.DataFrame(attribution_rows),
    )


def _run_lengths(mask: np.ndarray) -> np.ndarray:
    runs: list[int] = []
    count = 0
    for value in mask:
        if bool(value):
            count += 1
        elif count:
            runs.append(count)
            count = 0
    if count:
        runs.append(count)
    return np.asarray(runs, dtype=int)


def _path_metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    frame = frame.sort_values(["issue_anchor_ts", "issue"], kind="stable")
    pnl = frame["pnl_cny"].to_numpy(float)
    gross = frame["gross_cny"].to_numpy(float)
    equity = STARTING_CAPITAL_CNY + np.cumsum(pnl)
    prior_equity = np.r_[STARTING_CAPITAL_CNY, equity[:-1]]
    peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL_CNY, equity])[1:]
    drawdown = peaks - equity
    underwater = drawdown > 1e-9
    losing = pnl <= 0
    loss_runs = _run_lengths(losing)
    under_runs = _run_lengths(underwater)
    positive_gross = np.clip(gross, 0, None)
    total_gross = float(positive_gross.sum())
    shares = np.sort(positive_gross)[::-1] / total_gross if total_gross else np.zeros(len(gross))
    return {
        "max_drawdown_cny": float(drawdown.max(initial=0.0)),
        "max_drawdown_fraction": float(
            np.max(np.divide(drawdown, peaks, out=np.zeros_like(drawdown), where=peaks > 0), initial=0.0)
        ),
        "longest_profitable_issue_losing_run": int(loss_runs.max(initial=0)),
        "losing_run_p90": float(np.quantile(loss_runs, 0.9)) if len(loss_runs) else 0.0,
        "max_underwater_duration_issues": int(under_runs.max(initial=0)),
        "terminal_underwater_age_issues": int(under_runs[-1]) if len(under_runs) and underwater[-1] else 0,
        "largest_payout_share": float(shares[0]) if len(shares) else 0.0,
        "top5_payout_share": float(shares[:5].sum()),
        "top10_payout_share": float(shares[:10].sum()),
        "payout_hhi": float(np.square(shares).sum()),
        "minimum_capital_cny": float(equity.min(initial=STARTING_CAPITAL_CNY)),
        "maximum_capital_at_risk_cny": float(np.max(prior_equity) - np.min(equity)),
    }


def _scope(frame: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope in {"2022", "2023", "2024", "2025", "2026"}:
        return frame[frame["issue_year"].eq(int(scope))]
    if scope == "PRE_2025":
        return frame[frame["issue_year"].le(2024)]
    if scope == "EXTENSION_ALL":
        return frame[frame["issue_year"].ge(2025)]
    return frame


def _performance(bundles: pd.DataFrame) -> tuple[pd.DataFrame, set[str]]:
    included_sets = {
        variant: set(group.loc[group["native_included"], "issue"].astype(str))
        for variant, group in bundles.groupby("variant", observed=True)
    }
    exact_common = set.intersection(*included_sets.values()) if included_sets else set()
    rows: list[dict[str, Any]] = []
    for denominator in ("NATIVE", "EXACT_COMMON"):
        for scope in (
            "2022",
            "2023",
            "2024",
            "PRE_2025",
            "2025",
            "2026",
            "EXTENSION_ALL",
            "ALL_HISTORY",
        ):
            for variant, group in bundles.groupby("variant", observed=True, sort=True):
                eligible = group[group["native_included"]].copy()
                if denominator == "EXACT_COMMON":
                    eligible = eligible[eligible["issue"].astype(str).isin(exact_common)]
                eligible = _scope(eligible, scope)
                if eligible.empty:
                    continue
                gross = eligible["gross_cny"].to_numpy(float)
                pnl = eligible["pnl_cny"].to_numpy(float)
                stake = float(eligible["stake_cny"].sum())
                largest = int(np.argmax(gross))
                rows.append(
                    {
                        "denominator": denominator,
                        "scope": scope,
                        "variant": variant,
                        "policy": str(eligible["policy"].iloc[0]),
                        "family": str(eligible["family"].iloc[0]),
                        "issues": int(len(eligible)),
                        "stake_cny": stake,
                        "gross_cny": float(gross.sum()),
                        "pnl_cny": float(pnl.sum()),
                        "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                        "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                        "stake_roi": float(pnl.sum() / stake),
                        "issue_hit_rate": float(eligible["ticket_hit"].mean()),
                        "issue_profitable_rate": float(eligible["issue_profitable"].mean()),
                        "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest]),
                        **_path_metrics(eligible),
                    }
                )
    return pd.DataFrame(rows), exact_common


def _bootstrap_p05(delta: np.ndarray, seed: int) -> float:
    if not len(delta):
        return 0.0
    rng = np.random.default_rng(seed)
    block = min(MOVING_BLOCK_LENGTH, len(delta))
    count = math.ceil(len(delta) / block)
    starts = rng.integers(0, len(delta), size=(BOOTSTRAP_DRAWS, count))
    indices = (starts[:, :, None] + np.arange(block)[None, None, :]) % len(delta)
    means = delta[indices.reshape(BOOTSTRAP_DRAWS, -1)[:, : len(delta)]].mean(axis=1)
    return float(np.quantile(means, 0.05))


def _arm_ex_largest(frame: pd.DataFrame) -> float:
    gross = frame["gross_cny"].to_numpy(float)
    pnl = frame["pnl_cny"].to_numpy(float)
    return float(pnl.sum() - pnl[int(np.argmax(gross))]) if len(frame) else 0.0


def _contrasts(bundles: pd.DataFrame, exact_common: set[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    references = ("R3_C0E0_EQUAL", "R0_C0E0_EQUAL")
    for scope in (
        "2022",
        "2023",
        "2024",
        "PRE_2025",
        "2025",
        "2026",
        "EXTENSION_ALL",
        "ALL_HISTORY",
    ):
        scoped = _scope(
            bundles[
                bundles["native_included"]
                & bundles["issue"].astype(str).isin(exact_common)
            ],
            scope,
        )
        for variant in sorted(scoped["variant"].unique()):
            for reference in references:
                if variant == reference or reference not in set(scoped["variant"]):
                    continue
                a = scoped[scoped["variant"].eq(variant)][
                    ["issue", "issue_anchor_ts", "pnl_cny", "gross_cny"]
                ].rename(columns={"pnl_cny": "pnl_a", "gross_cny": "gross_a"})
                b = scoped[scoped["variant"].eq(reference)][
                    ["issue", "issue_anchor_ts", "pnl_cny", "gross_cny"]
                ].rename(columns={"pnl_cny": "pnl_b", "gross_cny": "gross_b"})
                paired = a.merge(b, on=["issue", "issue_anchor_ts"], validate="one_to_one")
                paired = paired.sort_values(["issue_anchor_ts", "issue"], kind="stable")
                if paired.empty:
                    continue
                delta = paired["pnl_a"].to_numpy(float) - paired["pnl_b"].to_numpy(float)
                largest_idx = int(np.argmax(np.abs(delta)))
                seed = _variant_seed(variant, reference, scope)
                a_ex = _arm_ex_largest(
                    paired.rename(columns={"pnl_a": "pnl_cny", "gross_a": "gross_cny"})
                )
                b_ex = _arm_ex_largest(
                    paired.rename(columns={"pnl_b": "pnl_cny", "gross_b": "gross_cny"})
                )
                rows.append(
                    {
                        "scope": scope,
                        "subject_variant": variant,
                        "reference_variant": reference,
                        "issues": int(len(paired)),
                        "subject_pnl_cny": float(paired["pnl_a"].sum()),
                        "reference_pnl_cny": float(paired["pnl_b"].sum()),
                        "matched_lift_cny": float(delta.sum()),
                        "subject_ex_largest_pnl_cny": a_ex,
                        "reference_ex_largest_pnl_cny": b_ex,
                        "armwise_ex_largest_lift_cny": float(a_ex - b_ex),
                        "largest_absolute_paired_delta_sensitivity_cny": float(
                            delta.sum() - delta[largest_idx]
                        ),
                        "largest_absolute_paired_delta_cny": float(abs(delta[largest_idx])),
                        "largest_absolute_paired_delta_issue": str(paired.iloc[largest_idx]["issue"]),
                        "moving_block_p05_paired_mean_cny_per_issue": _bootstrap_p05(delta, seed),
                        "bootstrap_estimand": "paired_mean_cny_per_issue",
                        "bootstrap_unit": "CNY_PER_ISSUE",
                        "bootstrap_block_length": min(MOVING_BLOCK_LENGTH, len(delta)),
                        "bootstrap_draw_count": BOOTSTRAP_DRAWS,
                        "bootstrap_seed": seed,
                    }
                )
    return pd.DataFrame(rows)


def _historical_calendar(repo_root: Path) -> pd.DataFrame:
    coverage = pd.read_csv(repo_root / "results/n7_support_shape/coverage_ledger.csv")
    selected = pd.read_csv(
        repo_root / "results/n7_cutoff_walkforward/settlement_coverage.csv"
    )
    selected = selected[
        selected["policy"].eq("EXPANDING_EQUAL")
        & selected["support_arm"].eq("R3_CONTROL")
    ][["issue", "selected_match_ids"]].drop_duplicates("issue")
    calendar = coverage[
        ["issue", "issue_year", "issue_anchor_ts", "included", "excluded_reason"]
    ].copy()
    calendar["issue"] = calendar["issue"].astype(str)
    calendar["issue_anchor_ts"] = pd.to_datetime(
        calendar["issue_anchor_ts"], utc=True
    )
    selected["issue"] = selected["issue"].astype(str)
    return calendar.merge(selected, on="issue", how="left", validate="one_to_one")


def _normalize_historical_source(
    frame: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    variant: str,
    family: str,
    policy: str,
    base: str,
    contraction: int,
    expansion: int,
    allocator: str,
) -> pd.DataFrame:
    source = frame.copy()
    source["issue"] = source["issue"].astype(str)
    source = source.rename(columns={"hit": "ticket_hit"})
    if "issue_profitable" not in source:
        source["issue_profitable"] = source["gross_cny"].gt(ISSUE_STAKE_CNY)
    keep = [
        "issue",
        "ticket_count",
        "funded_units",
        "stake_cny",
        "gross_cny",
        "pnl_cny",
        "ticket_hit",
        "issue_profitable",
        "winning_ticket_units",
    ]
    merged = calendar.merge(
        source[keep], on="issue", how="left", validate="one_to_one"
    )
    merged["policy"] = policy
    merged["variant"] = variant
    merged["family"] = family
    merged["base"] = base
    merged["contraction_count"] = contraction
    merged["expansion_count"] = expansion
    merged["allocator"] = allocator
    merged["support_json"] = ""
    merged["native_included"] = merged["included"].astype(bool) & merged[
        "gross_cny"
    ].notna()
    merged["stake_cny"] = merged["stake_cny"].fillna(ISSUE_STAKE_CNY)
    merged["ticket_count"] = merged["ticket_count"].fillna(
        (2 ** (N_LEGS - contraction - expansion)) * (3**expansion)
    )
    merged["funded_units"] = merged["funded_units"].fillna(FUNDED_UNITS)
    merged["ticket_hit"] = merged["ticket_hit"].fillna(False).astype(bool)
    merged["issue_profitable"] = (
        merged["issue_profitable"].fillna(False).astype(bool)
    )
    merged["winning_ticket_units"] = (
        merged["winning_ticket_units"].fillna(0).astype(int)
    )
    merged["winning_sp_product"] = math.nan
    return merged[
        [
            "issue",
            "issue_year",
            "issue_anchor_ts",
            "policy",
            "variant",
            "family",
            "base",
            "contraction_count",
            "expansion_count",
            "allocator",
            "selected_match_ids",
            "support_json",
            "ticket_count",
            "funded_units",
            "stake_cny",
            "gross_cny",
            "pnl_cny",
            "ticket_hit",
            "issue_profitable",
            "winning_ticket_units",
            "winning_sp_product",
            "native_included",
        ]
    ]


def _historical_bundles(repo_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize the accepted pre-2025 packages into the #400 registry."""

    calendar = _historical_calendar(repo_root)
    parts: list[pd.DataFrame] = []
    bridge_rows: list[dict[str, Any]] = []

    shape_path = repo_root / "results/n7_support_shape/issue_bundles.parquet"
    shape = pd.read_parquet(shape_path)
    shape_map = {
        "CONTROL": (0, 0),
        "CONTRACTION_ONLY": (1, 0),
        "EXPANSION_ONLY": (0, 1),
        "BOTH": (1, 1),
    }
    for shape_name, (c, e) in shape_map.items():
        src = shape[
            shape["base"].eq("R0_CORRECTED") & shape["shape"].eq(shape_name)
        ]
        variant = f"R0_C{c}E{e}_EQUAL"
        parts.append(
            _normalize_historical_source(
                src,
                calendar,
                variant=variant,
                family="R0_SHAPE_369",
                policy="EXPANDING_EQUAL",
                base="R0_CORRECTED",
                contraction=c,
                expansion=e,
                allocator="SHAPE_369",
            )
        )
        bridge_rows.append(
            {"variant": variant, "source_issue": 369, "source_path": str(shape_path.relative_to(repo_root))}
        )

    grid_path = repo_root / "results/n7_support_transfer_grid/issue_bundles.parquet"
    grid = pd.read_parquet(grid_path)
    for c in CONTRACTION_COUNTS:
        for e in EXPANSION_COUNTS:
            cell = f"C{c}E{e}"
            variant = f"R3_{cell}_EQUAL"
            parts.append(
                _normalize_historical_source(
                    grid[grid["cell"].eq(cell)],
                    calendar,
                    variant=variant,
                    family="R3_GRID_373",
                    policy="EXPANDING_EQUAL",
                    base="R3_CORRECTED",
                    contraction=c,
                    expansion=e,
                    allocator="GRID_373",
                )
            )
            bridge_rows.append(
                {"variant": variant, "source_issue": 373, "source_path": str(grid_path.relative_to(repo_root))}
            )

    temporal_path = repo_root / "results/n7_cutoff_walkforward/issue_bundles.parquet"
    temporal = pd.read_parquet(temporal_path)
    for policy, short in (
        ("EXPANDING_EXPONENTIAL", "EXP730"),
        ("RECENT_STATE_BLEND", "BLEND75_25"),
    ):
        for arm, (c, e) in {
            "R3_CONTROL": (0, 0),
            "C1E3_SECONDARY": (1, 3),
        }.items():
            variant = f"R3_C{c}E{e}_{short}"
            source = temporal[
                temporal["policy"].eq(policy) & temporal["support_arm"].eq(arm)
            ].copy()
            source["issue"] = source["issue"].astype(str)
            source["family"] = "R3_TEMPORAL_392"
            source["base"] = "R3_CORRECTED"
            source["contraction_count"] = c
            source["expansion_count"] = e
            source["allocator"] = "GRID_373"
            source["variant"] = variant
            source["selected_match_ids"] = source["issue"].map(
                calendar.set_index("issue")["selected_match_ids"]
            )
            source["support_json"] = ""
            source["winning_sp_product"] = math.nan
            parts.append(
                source[
                    [
                        "issue",
                        "issue_year",
                        "issue_anchor_ts",
                        "policy",
                        "variant",
                        "family",
                        "base",
                        "contraction_count",
                        "expansion_count",
                        "allocator",
                        "selected_match_ids",
                        "support_json",
                        "ticket_count",
                        "funded_units",
                        "stake_cny",
                        "gross_cny",
                        "pnl_cny",
                        "ticket_hit",
                        "issue_profitable",
                        "winning_ticket_units",
                        "winning_sp_product",
                        "native_included",
                    ]
                ]
            )
            bridge_rows.append(
                {"variant": variant, "source_issue": 392, "source_path": str(temporal_path.relative_to(repo_root))}
            )

    mixed_path = repo_root / "results/n7_mixed_full_history/bundles.parquet"
    mixed = pd.read_parquet(mixed_path)
    mixed = mixed[
        mixed["schedule"].eq("MIXED_50_50") & mixed["issue_year"].le(2024)
    ]
    mixed_rows: list[dict[str, Any]] = []
    for (issue, year, anchor), group in mixed.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        native = bool(group["native_included"].astype(bool).all())
        mixed_rows.append(
            {
                "issue": str(issue),
                "issue_year": int(year),
                "issue_anchor_ts": anchor,
                "policy": "EXPANDING_EQUAL_FROZEN_394",
                "variant": "MIX_R3_C0E0_C1E3_50_50_EQUAL",
                "family": "MIXED_394",
                "base": "MIXED_R3_C1E3",
                "contraction_count": -1,
                "expansion_count": -1,
                "allocator": "MIXED_394_INTEGER",
                "selected_match_ids": "|".join(sorted(group["selected_match_ids"].astype(str).unique())),
                "support_json": "",
                "ticket_count": int(group["ticket_count"].sum()),
                "funded_units": int(group["funded_units"].sum()),
                "stake_cny": float(group["stake_cny"].sum()),
                "gross_cny": float(group["gross_cny"].sum()) if native else math.nan,
                "pnl_cny": float(group["pnl_cny"].sum()) if native else math.nan,
                "ticket_hit": bool(native and group["ticket_hit"].any()),
                "issue_profitable": bool(native and group["pnl_cny"].sum() > 0),
                "winning_ticket_units": int(group["winning_ticket_units"].sum()),
                "winning_sp_product": math.nan,
                "native_included": native,
            }
        )
    parts.append(pd.DataFrame(mixed_rows))
    bridge_rows.append(
        {"variant": "MIX_R3_C0E0_C1E3_50_50_EQUAL", "source_issue": 394, "source_path": str(mixed_path.relative_to(repo_root))}
    )

    bundles = pd.concat(parts, ignore_index=True)
    if bundles.duplicated(["issue", "variant"]).any():
        raise ContractError("historical normalized bundle keys are not unique")
    return bundles, pd.DataFrame(bridge_rows)


def _capital_paths(bundles: pd.DataFrame, exact_common: set[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for denominator in ("NATIVE", "EXACT_COMMON"):
        for variant, group in bundles.groupby("variant", observed=True, sort=True):
            eligible = group[group["native_included"]].copy()
            if denominator == "EXACT_COMMON":
                eligible = eligible[eligible["issue"].astype(str).isin(exact_common)]
            eligible = eligible.sort_values(
                ["issue_anchor_ts", "issue"], kind="stable"
            )
            capital = STARTING_CAPITAL_CNY
            peak = capital
            for order, row in enumerate(eligible.itertuples(), start=1):
                capital += float(row.pnl_cny)
                peak = max(peak, capital)
                rows.append(
                    {
                        "denominator": denominator,
                        "variant": variant,
                        "issue_order": order,
                        "issue": str(row.issue),
                        "issue_year": int(row.issue_year),
                        "issue_anchor_ts": row.issue_anchor_ts,
                        "pnl_cny": float(row.pnl_cny),
                        "capital_cny": capital,
                        "peak_capital_cny": peak,
                        "drawdown_cny": peak - capital,
                        "underwater": bool(capital < peak - 1e-9),
                    }
                )
    return pd.DataFrame(rows)


def _coverage_ledger(
    bundles: pd.DataFrame,
    attribution: pd.DataFrame,
    repo_root: Path,
) -> pd.DataFrame:
    bad = attribution[~attribution["settlement_available"].astype(bool)].copy()
    if bad.empty:
        bad_summary = pd.DataFrame(
            columns=["issue", "variant", "excluded_match_ids", "exclusion_reasons", "exclusion_source_hashes"]
        )
    else:
        bad_summary = (
            bad.groupby(["issue", "variant"], observed=True)
            .agg(
                excluded_match_ids=(
                    "match_idx",
                    lambda value: "|".join(map(str, sorted(set(value)))),
                ),
                exclusion_reasons=(
                    "exclusion_reason",
                    lambda value: "|".join(
                        sorted(
                            {
                                str(item)
                                for item in value
                                if str(item) not in {"", "nan", "None"}
                            }
                        )
                    ),
                ),
                exclusion_source_hashes=(
                    "exclusion_source_payload_sha256",
                    lambda value: "|".join(
                        sorted(
                            {
                                str(item)
                                for item in value
                                if str(item) not in {"", "nan", "None"}
                            }
                        )
                    ),
                ),
            )
            .reset_index()
        )
    ledger = bundles[
        [
            "issue",
            "issue_year",
            "issue_anchor_ts",
            "variant",
            "policy",
            "selected_match_ids",
            "native_included",
        ]
    ].copy()
    ledger = ledger.merge(
        bad_summary, on=["issue", "variant"], how="left", validate="one_to_one"
    )
    historical = _historical_calendar(repo_root)[
        ["issue", "excluded_reason"]
    ].rename(columns={"excluded_reason": "historical_exclusion_reason"})
    ledger = ledger.merge(historical, on="issue", how="left", validate="many_to_one")
    ledger["inclusion_status"] = np.where(
        ledger["native_included"].astype(bool),
        "INCLUDED_NATIVE",
        "EXCLUDED_SELECTED_FIXTURE_UNTRUSTED",
    )
    ledger["exclusion_reasons"] = ledger["exclusion_reasons"].replace("", np.nan)
    ledger["exclusion_reasons"] = ledger["exclusion_reasons"].fillna(
        ledger["historical_exclusion_reason"]
    ).fillna("UNTRUSTED_OR_MISSING_SELECTED_FIXTURE")
    return ledger.drop(columns=["historical_exclusion_reason"])


def _mapping_summary(receipts: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in receipts:
        receipt = item["receipt"]
        rows.append(
            {
                "issue": str(item["issue"]),
                "issue_year": int(item["issue_year"]),
                "policy": str(item["policy"]),
                "cutoff_identity": receipt["cutoff_identity"],
                "cutoff_ts": receipt["cutoff_ts"],
                "maximum_training_label_timestamp": receipt[
                    "maximum_training_label_timestamp"
                ],
                "maximum_source_issue": receipt["maximum_source_issue"],
                "admitted_history_sha256": receipt["admitted_history_sha256"],
                "cache_key": receipt["cache_key"],
                "mapping_accepted": bool(receipt["mapping_accepted"]),
                "effective_sample_size": float(
                    receipt["weight_receipt"]["effective_sample_size"]
                ),
                "fit_rows": int(receipt["partition"]["fit_rows"]),
                "tune_rows": int(receipt["partition"]["tune_rows"]),
                "calibration_rows": int(
                    receipt["partition"]["calibration_rows"]
                ),
                "model_identity": str(receipt["model_identity"]),
                "scientific_output_sha256": receipt["scientific_output_sha256"],
            }
        )
    frame = pd.DataFrame(rows)
    if frame.duplicated(["issue", "policy"]).any():
        raise ContractError("mapping receipt summary keys are not unique")
    return frame


def _turnover(
    bundles: pd.DataFrame,
    attribution: pd.DataFrame,
    tickets: pd.DataFrame,
) -> pd.DataFrame:
    extension = bundles[
        bundles["issue_year"].isin(YEARS) & bundles["native_included"]
    ]
    support_sets = {
        (str(issue), str(variant)): {
            (int(row.match_idx), str(row.active_support))
            for row in group.itertuples()
        }
        for (issue, variant), group in attribution.groupby(
            ["issue", "variant"], observed=True
        )
    }
    ticket_sets = {
        (str(issue), str(variant)): set(group["ticket_identity"].astype(str))
        for (issue, variant), group in tickets.groupby(
            ["issue", "variant"], observed=True
        )
    }
    rows: list[dict[str, Any]] = []
    reference = "R3_C0E0_EQUAL"
    for row in extension.itertuples():
        key = (str(row.issue), str(row.variant))
        ref_key = (str(row.issue), reference)
        if ref_key not in support_sets or key not in support_sets:
            continue
        selected = set(str(row.selected_match_ids).split("|"))
        ref_row = extension[
            extension["issue"].astype(str).eq(str(row.issue))
            & extension["variant"].eq(reference)
        ]
        if ref_row.empty:
            continue
        selected_ref = set(str(ref_row.iloc[0]["selected_match_ids"]).split("|"))
        support = support_sets[key]
        support_ref = support_sets[ref_key]
        ticket = ticket_sets.get(key, set())
        ticket_ref = ticket_sets.get(ref_key, set())
        rows.append(
            {
                "issue": str(row.issue),
                "issue_year": int(row.issue_year),
                "variant": str(row.variant),
                "reference_variant": reference,
                "selected_fixture_jaccard": len(selected & selected_ref)
                / max(len(selected | selected_ref), 1),
                "support_pair_jaccard": len(support & support_ref)
                / max(len(support | support_ref), 1),
                "ticket_identity_jaccard": len(ticket & ticket_ref)
                / max(len(ticket | ticket_ref), 1),
                "selected_fixture_changed": bool(selected != selected_ref),
                "support_changed": bool(support != support_ref),
                "tickets_changed": bool(ticket != ticket_ref),
            }
        )
    return pd.DataFrame(rows)


def _pareto_frontier(performance: pd.DataFrame) -> pd.DataFrame:
    frame = performance[
        performance["denominator"].eq("EXACT_COMMON")
        & performance["scope"].eq("EXTENSION_ALL")
    ].copy()
    objectives = [
        ("pnl_cny", True),
        ("ex_largest_pnl_cny", True),
        ("max_drawdown_cny", False),
        ("longest_profitable_issue_losing_run", False),
        ("payout_hhi", False),
    ]
    nondominated: list[bool] = []
    for idx, row in frame.iterrows():
        dominated = False
        for other_idx, other in frame.iterrows():
            if idx == other_idx:
                continue
            no_worse = all(
                other[col] >= row[col] if maximize else other[col] <= row[col]
                for col, maximize in objectives
            )
            strictly_better = any(
                other[col] > row[col] if maximize else other[col] < row[col]
                for col, maximize in objectives
            )
            if no_worse and strictly_better:
                dominated = True
                break
        nondominated.append(not dominated)
    frame["pareto_nondominated"] = nondominated
    frame["descriptive_only_no_selection"] = True
    return frame.sort_values(
        ["pareto_nondominated", "pnl_cny"], ascending=[False, False]
    ).reset_index(drop=True)


def _expected_variant_contract() -> dict[str, dict[str, Any]]:
    """Return the complete preregistered 21-cell registry contract."""

    rows: dict[str, dict[str, Any]] = {}
    for c, e in ((0, 0), (1, 0), (0, 1), (1, 1)):
        rows[f"R0_C{c}E{e}_EQUAL"] = {
            "policy": "EXPANDING_EQUAL",
            "family": "R0_SHAPE_369",
            "base": "R0_CORRECTED",
            "contraction_count": c,
            "expansion_count": e,
            "allocator": "SHAPE_369",
            "ticket_count": (2 ** (N_LEGS - c - e)) * (3**e),
        }
    for c in CONTRACTION_COUNTS:
        for e in EXPANSION_COUNTS:
            rows[f"R3_C{c}E{e}_EQUAL"] = {
                "policy": "EXPANDING_EQUAL",
                "family": "R3_GRID_373",
                "base": "R3_CORRECTED",
                "contraction_count": c,
                "expansion_count": e,
                "allocator": "GRID_373",
                "ticket_count": (2 ** (N_LEGS - c - e)) * (3**e),
            }
    for policy, short in (
        ("EXPANDING_EXPONENTIAL", "EXP730"),
        ("RECENT_STATE_BLEND", "BLEND75_25"),
    ):
        for c, e in ((0, 0), (1, 3)):
            rows[f"R3_C{c}E{e}_{short}"] = {
                "policy": policy,
                "family": "R3_TEMPORAL_392",
                "base": "R3_CORRECTED",
                "contraction_count": c,
                "expansion_count": e,
                "allocator": "GRID_373",
                "ticket_count": (2 ** (N_LEGS - c - e)) * (3**e),
            }
    rows["MIX_R3_C0E0_C1E3_50_50_EQUAL"] = {
        "policy": "EXPANDING_EQUAL_FROZEN_394",
        "family": "MIXED_394",
        "base": "MIXED_R3_C1E3",
        "contraction_count": -1,
        "expansion_count": -1,
        "allocator": "MIXED_394_INTEGER",
        "ticket_count": 128 + 216,
    }
    if len(rows) != 21:
        raise ContractError("internal variant contract does not contain 21 cells")
    return rows


def scientific_frames(repo_root: Path, data_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    data_root = locate_data_root(repo_root, data_root)
    # #400 consumes the immutable accepted #394 interface.  Replaying its
    # entire ancestor chain would add ~17 minutes without changing the frozen
    # input; the package loader verifies every #394 manifest member first.
    base = _load_mixed_history_package(repo_root)

    from src.low_n_selector_data.pipeline import load_issue_roles

    candidate = data_root / "derived/bj268/eu_proxy_backfill_v3/candidate.sqlite"
    registry = data_root / "derived/500_bjdc/500_bjdc.sqlite"
    roles = load_issue_roles(candidate, registry)
    panel = _extension_panel(repo_root, data_root, roles)
    eligible, boundary = _pre_extension_boundary(panel)
    history = base["history"]
    settlement = base["extension_settlement"]
    settlement_issues = set(settlement["issue"].astype(str))
    eligible = eligible[
        eligible["issue_code"].astype(str).isin(settlement_issues)
        & eligible["issue_year"].isin(YEARS)
    ].copy()
    learning_history = _extension_learning_history(history, eligible, settlement)
    source_hashes = {
        "base_history_frame_sha256": stable_frame_sha(history),
        "learning_history_frame_sha256": stable_frame_sha(learning_history),
        "extension_panel_sha256": stable_frame_sha(panel),
        "extension_settlement_sha256": stable_frame_sha(settlement),
        "source_merge_sha": SOURCE_MERGE_SHA,
        "n7_support_shape_manifest_sha256": sha256_file(
            repo_root / "results/n7_support_shape/MANIFEST.json"
        ),
        "n7_support_transfer_manifest_sha256": sha256_file(
            repo_root / "results/n7_support_transfer_grid/MANIFEST.json"
        ),
        "n7_cutoff_walkforward_manifest_sha256": sha256_file(
            repo_root / "results/n7_cutoff_walkforward/MANIFEST.json"
        ),
        "n7_mixed_history_manifest_sha256": sha256_file(
            repo_root / "results/n7_mixed_full_history/MANIFEST.json"
        ),
    }
    # Fit/cache identity must contain only immutable upstream identities plus
    # the per-target admitted-history and feature hashes added above.  Whole
    # extension frames include labels that settle after an early target and
    # therefore must not invalidate or poison that target's frozen artifact.
    fit_source_hashes = {
        key: value
        for key, value in source_hashes.items()
        if key
        in {
            "source_merge_sha",
            "n7_support_shape_manifest_sha256",
            "n7_support_transfer_manifest_sha256",
            "n7_cutoff_walkforward_manifest_sha256",
            "n7_mixed_history_manifest_sha256",
        }
    }
    admitted_receipts = _admitted_history_receipts(learning_history, eligible)

    mapped_by_policy: dict[str, pd.DataFrame] = {}
    receipts: list[dict[str, Any]] = []
    weight_parts: list[pd.DataFrame] = []
    for policy in POLICIES:
        mapped, policy_receipts, weights = _fit_policy_surface(
            repo_root,
            learning_history,
            eligible,
            fit_source_hashes,
            policy,
            data_root / "cache/n7_variant_extension/mapping",
            admitted_receipts,
        )
        mapped_by_policy[policy] = mapped
        receipts.extend(policy_receipts)
        weight_parts.append(weights)

    bundle_parts: list[pd.DataFrame] = []
    ticket_parts: list[pd.DataFrame] = []
    attr_parts: list[pd.DataFrame] = []
    selection_parts: list[pd.DataFrame] = []
    for policy, mapped in mapped_by_policy.items():
        action = _action_surface(mapped, settlement)
        b, t, a, s = _construct_policy_variants(action, policy)
        bundle_parts.append(b)
        ticket_parts.append(t)
        attr_parts.append(a)
        selection_parts.append(s)
    extension_bundles = pd.concat(bundle_parts, ignore_index=True)
    extension_tickets = pd.concat(ticket_parts, ignore_index=True)
    extension_attribution = pd.concat(attr_parts, ignore_index=True)
    extension_bundles, mixed_tickets, mixed_attribution = _add_mixed_portfolio(
        extension_bundles, base
    )
    extension_tickets = pd.concat(
        [extension_tickets, mixed_tickets], ignore_index=True, sort=False
    )
    extension_attribution = pd.concat(
        [extension_attribution, mixed_attribution], ignore_index=True, sort=False
    )
    historical_bundles, history_bridge = _historical_bundles(repo_root)
    bundles = pd.concat(
        [historical_bundles, extension_bundles], ignore_index=True, sort=False
    )
    bundles["issue_anchor_ts"] = pd.to_datetime(
        bundles["issue_anchor_ts"], utc=True
    )
    if bundles.duplicated(["issue", "variant"]).any():
        raise ContractError("all-history canonical bundle keys are not unique")
    performance, exact_common = _performance(bundles)
    contrasts = _contrasts(bundles, exact_common)
    registry_rows = (
        bundles[
            [
                "variant",
                "family",
                "policy",
                "base",
                "contraction_count",
                "expansion_count",
                "allocator",
                "ticket_count",
            ]
        ]
        .drop_duplicates()
        .sort_values("variant", kind="stable")
        .reset_index(drop=True)
    )
    paths = _capital_paths(bundles, exact_common)
    coverage = _coverage_ledger(bundles, extension_attribution, repo_root)
    mapping_summary = _mapping_summary(receipts)
    turnover = _turnover(extension_bundles, extension_attribution, extension_tickets)
    pareto = _pareto_frontier(performance)
    extension_exact = performance[
        performance["denominator"].eq("EXACT_COMMON")
        & performance["scope"].eq("EXTENSION_ALL")
    ]
    annual_exact = performance[
        performance["denominator"].eq("EXACT_COMMON")
        & performance["scope"].isin(["2025", "2026"])
    ]
    annual_nonreversal = set(
        annual_exact.groupby("variant", observed=True)["pnl_cny"]
        .apply(lambda value: bool((value >= 0).all() and len(value) == 2))
        .loc[lambda value: value]
        .index.astype(str)
    )
    robust_positive = sorted(
        set(
            extension_exact.loc[
                extension_exact["pnl_cny"].gt(0)
                & extension_exact["ex_largest_pnl_cny"].gt(0),
                "variant",
            ].astype(str)
        )
        & annual_nonreversal
    )
    decision = {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "verdict": VERDICT,
        "promotion_authorized": False,
        "prospective_authorized": False,
        "evidence_status": "CONSUMED_RETROSPECTIVE_2025_2026",
        "source_merge_sha": SOURCE_MERGE_SHA,
        "terminal_394_decision_preserved": base["decision"]["verdict"],
        "exact_common_issues": len(exact_common),
        "best_extension_pnl_variant": str(
            performance[
                performance["denominator"].eq("EXACT_COMMON")
                & performance["scope"].eq("EXTENSION_ALL")
            ].sort_values("pnl_cny", ascending=False, kind="stable").iloc[0]["variant"]
        ),
        "descriptive_positive_annual_nonreversal_variants": robust_positive,
        "expert_admission_authorized": False,
        "selection_or_promotion_from_extension_forbidden": True,
    }
    source = {
        "contract": CONTRACT_ID,
        "source_merge_sha": SOURCE_MERGE_SHA,
        "source_394_manifest_sha256": sha256_file(
            repo_root / "results/n7_mixed_full_history/MANIFEST.json"
        ),
        "source_hashes": source_hashes,
        "evidence_query_cutoff": base["source"]["evidence_cutoff_receipt"],
        "pre_extension_boundary_ts": boundary.isoformat(),
        "temporal_mode": "ISSUE_LEVEL_WALK_FORWARD_DECISION_EPOCH",
        "policies": list(POLICIES),
        "years": list(YEARS),
        "extension_receipts": len(receipts),
        "exact_common_issue_count": len(exact_common),
        "settlement_package": base["source"]["bj396"],
        "historical_exposed_only": True,
    }
    return {
        "source": source,
        "registry": registry_rows,
        "mapping_receipts": receipts,
        "weights": pd.concat(weight_parts, ignore_index=True),
        "selections": pd.concat(selection_parts, ignore_index=True),
        "bundles": bundles,
        "tickets": extension_tickets,
        "attribution": extension_attribution,
        "performance": performance,
        "contrasts": contrasts,
        "history_bridge": history_bridge,
        "issue_ledger": coverage,
        "capital_paths": paths,
        "mapping_summary": mapping_summary,
        "turnover": turnover,
        "pareto": pareto,
        "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "variant_registry.csv": "registry",
    "mapping_receipts.json.gz": "mapping_receipts",
    "weight_receipts.parquet": "weights",
    "selection_receipts.parquet": "selections",
    "issue_bundles.parquet": "bundles",
    "tickets.parquet": "tickets",
    "support_attribution.parquet": "attribution",
    "performance.csv": "performance",
    "matched_contrasts.csv": "contrasts",
    "upstream_history_bridge.csv": "history_bridge",
    "issue_ledger.csv": "issue_ledger",
    "capital_paths.parquet": "capital_paths",
    "mapping_summary.csv": "mapping_summary",
    "action_ticket_turnover.csv": "turnover",
    "pareto_frontier.csv": "pareto",
    "decision.json": "decision",
}


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        value.to_parquet(path, index=False)
    elif path.suffix == ".csv":
        value.to_csv(path, index=False)
    elif path.suffixes[-2:] == [".json", ".gz"]:
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, default=str)
    else:
        path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def _table(frame: pd.DataFrame, columns: list[str], limit: int | None = None) -> str:
    view = frame.loc[:, [c for c in columns if c in frame]].copy()
    if limit is not None:
        view = view.head(limit)

    def render(value: Any) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, (float, np.floating)):
            value = f"{float(value):.4f}"
        return str(value).replace("|", "\\|").replace("\n", " ")

    headers = [render(column) for column in view.columns]
    rows = [[render(value) for value in row] for row in view.itertuples(index=False)]
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(row) + " |" for row in rows),
        ]
    )


def _deliveries(repo_root: Path, frames: dict[str, Any]) -> None:
    performance = frames["performance"]
    exact = performance[
        performance["denominator"].eq("EXACT_COMMON")
        & performance["scope"].isin(["2025", "2026", "EXTENSION_ALL"])
    ].copy()
    exact = exact.sort_values(["scope", "pnl_cny"], ascending=[True, False])
    contrasts = frames["contrasts"]
    key_variants = [
        "R0_C0E0_EQUAL",
        "R3_C0E0_EQUAL",
        "R3_C1E3_EQUAL",
        "MIX_R3_C0E0_C1E3_50_50_EQUAL",
        "R3_C2E0_EQUAL",
        "R3_C0E0_EXP730",
        "R3_C0E0_BLEND75_25",
    ]
    key = performance[
        performance["denominator"].eq("EXACT_COMMON")
        & performance["scope"].isin(
            ["PRE_2025", "2025", "2026", "EXTENSION_ALL", "ALL_HISTORY"]
        )
        & performance["variant"].isin(key_variants)
    ].copy()
    key["variant"] = pd.Categorical(
        key["variant"], categories=key_variants, ordered=True
    )
    key = key.sort_values(["scope", "variant"], kind="stable")
    extension_counts = (
        performance[
            performance["denominator"].eq("EXACT_COMMON")
            & performance["variant"].eq("R3_C0E0_EQUAL")
            & performance["scope"].isin(["2025", "2026", "EXTENSION_ALL"])
        ]
        .set_index("scope")["issues"]
        .astype(int)
        .to_dict()
    )
    excluded = frames["issue_ledger"][
        frames["issue_ledger"]["issue_year"].isin(YEARS)
        & ~frames["issue_ledger"]["native_included"].astype(bool)
    ]
    excluded_issue_count = int(excluded["issue"].astype(str).nunique())
    report = f"""# Issue #400 — corrected N7 canonical variants on 2025–2026

## Five-minute decision summary

This is a consumed retrospective extension diagnostic. It compares only the
corrected canonical variants frozen by #369/#373/#392/#394. It does not select
or promote an exposed winner. The terminal #394 decision remains
`NO_MIXED_N7_EXTENSION_INCREMENT`.

- Exact-common evidence contains **{extension_counts.get('2025', 0)} issues in
  2025**, **{extension_counts.get('2026', 0)} in 2026**, and
  **{extension_counts.get('EXTENSION_ALL', 0)} extension issues in total**.
  {excluded_issue_count} extension issues are excluded on at least one arm;
  every reason and source hash is retained in `issue_ledger.csv`.
- **All 21 variants lose money in 2025.** Several turn positive in 2026, so the
  dominant fact is year/regime reversal, not a stable Edge.
- R3 C1E3 improves extension P&L relative to R3 CONTROL, but its extension
  ex-largest P&L remains negative and its preregistered moving-block p05 remains
  below zero. It is a useful support-transfer mechanism signal, not an expert.
- The frozen 50/50 portfolio is essentially flat on 2025–2026 combined evidence
  while remaining terminally underwater; it improves some path metrics versus
  R3 CONTROL but materially trails R0 CONTROL. Diversification did not create
  positive expectancy.
- R3 C2E0 has the largest point extension P&L, driven by a concentrated 2026
  payout. Its pre-2025 and ex-largest evidence are negative, drawdown and losing
  runs are severe, and bootstrap p05 is negative. It is explicitly not selected.
- EXP730 does not establish a robust recency increment; BLEND75_25 is strongly
  negative. Recent weighting is not automatically adaptation.

The terminal decision is `{VERDICT}`: no promotion, no expert admission and no
prospective authorization from these already exposed outcomes.

## Key baseline and challenger paths

{_table(key, ['scope','variant','issues','pnl_cny','ending_capital_cny','stake_roi','issue_hit_rate','issue_profitable_rate','ex_largest_pnl_cny','max_drawdown_cny','longest_profitable_issue_losing_run','max_underwater_duration_issues','terminal_underwater_age_issues','largest_payout_share','payout_hhi'])}

## Interpretation

The results separate three concepts that must not be conflated. First, R0/R3
and support shape change the payoff distribution. Second, mixing can smooth some
local drawdowns and losing runs. Third, neither operation guarantees positive
expected value. Because 2025 and 2026 were not untouched holdout years and every
extension lift has a negative moving-block p05 somewhere on the preregistered
comparison, the point estimates are mechanism diagnostics only.

The table separates absolute economics from matched lift. Armwise ex-largest
lift and largest-absolute-paired-delta sensitivity are distinct fields; the
deprecated #394 `matched_ex_largest_lift_cny` field is not used.

## Canonical registry

{_table(frames['registry'], list(frames['registry'].columns))}

## Exact-common annual and extension performance

{_table(exact, ['scope','variant','issues','pnl_cny','ending_capital_cny','stake_roi','issue_hit_rate','issue_profitable_rate','ex_largest_pnl_cny','max_drawdown_cny','longest_profitable_issue_losing_run','max_underwater_duration_issues','largest_payout_share','payout_hhi'])}

## Matched contrasts versus R3/R0 controls

{_table(contrasts.sort_values(['scope','matched_lift_cny'], ascending=[True,False]), ['scope','subject_variant','reference_variant','issues','matched_lift_cny','armwise_ex_largest_lift_cny','largest_absolute_paired_delta_sensitivity_cny','moving_block_p05_paired_mean_cny_per_issue','bootstrap_block_length','bootstrap_draw_count','bootstrap_seed'])}

## Evidence boundary

- 2025 and 2026 outcomes are already consumed retrospective evidence.
- No variant, temporal policy, support count, residual allocation, weight or seed
  was selected from those outcomes.
- The common denominator is the intersection of all canonical variant calendars;
  native results remain separately available in the machine table.
- Legacy/old-anchor N7 scripts are excluded from the registry.
- #210 and #218 are unchanged.
"""
    report_path = repo_root / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    fig_path = repo_root / FIGURE_PATH
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    all_perf = exact[exact["scope"].eq("EXTENSION_ALL")].sort_values("pnl_cny")
    fig, axes = plt.subplots(2, 2, figsize=(18, 13))
    ax = axes[0, 0]
    ax.barh(
        all_perf["variant"],
        all_perf["pnl_cny"],
        color=np.where(all_perf["pnl_cny"] >= 0, "#2e8b57", "#b94a48"),
    )
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("Exact-common 2025–2026 PnL")
    ax.set_xlabel("CNY; fixed CNY1,024 per issue")

    ax = axes[0, 1]
    tail = all_perf.sort_values("ex_largest_pnl_cny")
    ax.barh(
        tail["variant"],
        tail["ex_largest_pnl_cny"],
        color=np.where(tail["ex_largest_pnl_cny"] >= 0, "#2e8b57", "#b94a48"),
    )
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("Extension PnL after removing each arm's largest payout")
    ax.set_xlabel("CNY")

    ax = axes[1, 0]
    risk = all_perf[all_perf["variant"].isin(key_variants)].copy()
    positions = np.arange(len(risk))
    ax.bar(positions - 0.2, risk["max_drawdown_cny"], width=0.4, label="Max drawdown")
    ax.bar(
        positions + 0.2,
        risk["longest_profitable_issue_losing_run"] * ISSUE_STAKE_CNY,
        width=0.4,
        label="Losing-run length × CNY1,024",
    )
    ax.set_xticks(positions, risk["variant"], rotation=40, ha="right")
    ax.set_title("Path risk (two scales expressed in CNY-equivalent)")
    ax.legend()

    ax = axes[1, 1]
    paths = frames["capital_paths"]
    paths = paths[
        paths["denominator"].eq("EXACT_COMMON")
        & paths["variant"].isin(key_variants[:5])
        & paths["issue_year"].isin(YEARS)
    ].copy()
    for variant, group in paths.groupby("variant", observed=True, sort=False):
        group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable")
        extension_capital = STARTING_CAPITAL_CNY + group["pnl_cny"].cumsum()
        ax.plot(np.arange(1, len(group) + 1), extension_capital, label=str(variant))
    ax.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8)
    ax.set_title("2025–2026 extension capital paths")
    ax.set_xlabel("Exact-common issue order")
    ax.set_ylabel("Capital (CNY)")
    ax.legend(fontsize=8)

    fig.suptitle("Issue #400 — corrected N7 retrospective variant atlas", fontsize=16)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=170)
    plt.close(fig)

    nb = nbformat.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb["cells"] = [
        nbformat.v4.new_markdown_cell("# Issue #400 executed analysis\n\nAll tables are read from the immutable package; no fitting occurs in this notebook."),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nROOT=Path.cwd()\nSTAGING=ROOT/'results/n7_variant_extension.staging'\nPKG=STAGING if STAGING.is_dir() else ROOT/'results/n7_variant_extension'\nperf=pd.read_csv(PKG/'performance.csv')\ncontrasts=pd.read_csv(PKG/'matched_contrasts.csv')\nregistry=pd.read_csv(PKG/'variant_registry.csv')\nprint({'variants':len(registry),'performance_rows':len(perf),'contrast_rows':len(contrasts)})"
        ),
        nbformat.v4.new_code_cell(
            "display(perf[(perf.denominator=='EXACT_COMMON') & (perf.scope.isin(['2025','2026','EXTENSION_ALL']))].sort_values(['scope','pnl_cny'],ascending=[True,False]))"
        ),
        nbformat.v4.new_code_cell(
            "display(contrasts.sort_values(['scope','matched_lift_cny'],ascending=[True,False]))"
        ),
    ]
    NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(repo_root)}}).execute()
    nb.get("metadata", {}).get("language_info", {}).pop("version", None)
    notebook_path = repo_root / NOTEBOOK_PATH
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, notebook_path)


def _manifest(repo_root: Path, package: Path) -> dict[str, Any]:
    files = {
        path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in sorted(package.iterdir())
        if path.is_file() and path.name != "MANIFEST.json"
    }
    deliveries = {
        path: sha256_file(repo_root / path)
        for path in (REPORT_PATH, NOTEBOOK_PATH, FIGURE_PATH)
    }
    return {
        "contract": CONTRACT_ID,
        "source_merge_sha": SOURCE_MERGE_SHA,
        "files": files,
        "deliveries": deliveries,
        "implementation": {
            "pipeline_sha256": sha256_file(Path(__file__)),
            "contract_sha256": sha256_file(Path(__file__).with_name("contract.py")),
            "runner_sha256": sha256_file(
                repo_root / "scripts/run_n7_variant_extension.py"
            ),
            "verifier_sha256": sha256_file(
                repo_root / "scripts/verify_n7_variant_extension.py"
            ),
            "tests_sha256": sha256_file(
                repo_root / "tests/test_n7_variant_extension.py"
            ),
        },
    }


def build_package(repo_root: Path, data_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    frames = scientific_frames(repo_root, data_root)
    staging = repo_root / f"{RESULT_PACKAGE}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for name, key in PACKAGE_FILES.items():
        _write(staging / name, frames[key])
    _deliveries(repo_root, frames)
    (staging / "MANIFEST.json").write_text(
        json.dumps(_manifest(repo_root, staging), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    def populate(destination: Path) -> None:
        for source in staging.iterdir():
            target = destination / source.name
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)

    atomic_publish_directory(
        repo_root / RESULT_PACKAGE, populate, force=True
    )
    shutil.rmtree(staging)
    verify_package(repo_root, data_root, replay=False)
    return frames


def _read(path: Path) -> Any:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    if path.suffixes[-2:] == [".json", ".gz"]:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_scientific_frame(
    name: str, actual: pd.DataFrame, expected: pd.DataFrame
) -> None:
    if list(actual.columns) != list(expected.columns):
        raise ContractError(f"{name} columns differ")
    if len(actual) != len(expected):
        raise ContractError(f"{name} row count differs")
    for column in actual.columns:
        left = actual[column].reset_index(drop=True)
        right = expected[column].reset_index(drop=True)
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            if not np.allclose(
                left.to_numpy(float),
                right.to_numpy(float),
                rtol=0,
                atol=1e-8,
                equal_nan=True,
            ):
                raise ContractError(f"{name} differs in numeric column {column}")
        else:
            left_values = (
                left.replace("", np.nan).fillna("<NA>").astype(str).to_numpy()
            )
            right_values = (
                right.replace("", np.nan).fillna("<NA>").astype(str).to_numpy()
            )
            if not np.array_equal(left_values, right_values):
                raise ContractError(f"{name} differs in column {column}")


def _verify_registry(registry: pd.DataFrame) -> None:
    expected = _expected_variant_contract()
    actual = set(registry["variant"].astype(str))
    if actual != set(expected) or len(registry) != len(expected):
        raise ContractError("variant registry is not the exact frozen 21-cell set")
    if registry.duplicated("variant").any():
        raise ContractError("variant registry contains duplicate keys")
    for row in registry.itertuples():
        contract = expected[str(row.variant)]
        for field, value in contract.items():
            observed = getattr(row, field)
            if field == "ticket_count":
                if int(observed) != int(value):
                    raise ContractError(f"{row.variant}: ticket count differs")
            elif observed != value:
                raise ContractError(f"{row.variant}: {field} differs")


def _verify_extension_tickets(
    bundles: pd.DataFrame,
    tickets: pd.DataFrame,
    attribution: pd.DataFrame,
) -> None:
    extension = bundles[bundles["issue_year"].isin(YEARS)].copy()
    bundle_keys = set(
        zip(extension["issue"].astype(str), extension["variant"].astype(str), strict=True)
    )
    ticket_keys = set(
        zip(tickets["issue"].astype(str), tickets["variant"].astype(str), strict=True)
    )
    attr_keys = set(
        zip(
            attribution["issue"].astype(str),
            attribution["variant"].astype(str),
            strict=True,
        )
    )
    if bundle_keys != ticket_keys or bundle_keys != attr_keys:
        raise ContractError("extension bundle/ticket/attribution key sets differ")
    expected = _expected_variant_contract()
    for (issue, variant), bundle_group in extension.groupby(
        ["issue", "variant"], observed=True, sort=False
    ):
        if len(bundle_group) != 1:
            raise ContractError("extension bundle key is not unique")
        bundle = bundle_group.iloc[0]
        ticket = tickets[
            tickets["issue"].astype(str).eq(str(issue))
            & tickets["variant"].eq(str(variant))
        ].copy()
        attr = attribution[
            attribution["issue"].astype(str).eq(str(issue))
            & attribution["variant"].eq(str(variant))
        ].copy()
        if len(ticket) != int(expected[str(variant)]["ticket_count"]):
            raise ContractError(f"{issue}/{variant}: incomplete ticket set")
        if ticket["ticket_code"].duplicated().any() and str(variant) != "MIX_R3_C0E0_C1E3_50_50_EQUAL":
            raise ContractError(f"{issue}/{variant}: duplicate ticket code")
        if ticket["ticket_identity"].duplicated().any():
            raise ContractError(f"{issue}/{variant}: duplicate ticket identity")
        if not ticket["units"].astype(int).ge(1).all():
            raise ContractError(f"{issue}/{variant}: non-positive funded ticket")
        if not np.allclose(
            ticket["stake_cny"].to_numpy(float),
            ticket["units"].to_numpy(float) * STAKE_PER_UNIT_CNY,
            rtol=0,
            atol=1e-10,
        ):
            raise ContractError(f"{issue}/{variant}: ticket stake differs from units")
        if int(ticket["units"].sum()) != FUNDED_UNITS:
            raise ContractError(f"{issue}/{variant}: total units differ")

        mixed = str(variant) == "MIX_R3_C0E0_C1E3_50_50_EQUAL"
        arm_groups = (
            ticket.groupby("portfolio_arm", observed=True, dropna=False)
            if mixed
            else [(None, ticket)]
        )
        reconstructed_gross = 0.0
        reconstructed_units = 0
        all_trusted = True
        for arm, arm_ticket in arm_groups:
            arm_attr = attr if not mixed else attr[attr["portfolio_arm"].eq(arm)]
            arm_attr = arm_attr.sort_values("match_idx", kind="stable")
            if len(arm_attr) != N_LEGS:
                raise ContractError(f"{issue}/{variant}: attribution is not N7")
            supports = [tuple(str(value)) for value in arm_attr["active_support"]]
            expected_codes = {
                "|".join(values) for values in itertools.product(*supports)
            }
            if set(arm_ticket["ticket_code"].astype(str)) != expected_codes:
                raise ContractError(f"{issue}/{variant}: tickets are not full Cartesian support")
            if mixed:
                expected_arm_units = 256
                expected_arm_count = 128 if str(arm) == "R3_CONTROL" else 216
                if str(arm) not in {"R3_CONTROL", "C1E3_SECONDARY"}:
                    raise ContractError("mixed portfolio contains an unknown arm")
                if len(arm_ticket) != expected_arm_count or int(arm_ticket["units"].sum()) != expected_arm_units:
                    raise ContractError("mixed portfolio is not exact 256+256 allocation")
            trusted = bool(arm_attr["settlement_available"].astype(bool).all())
            all_trusted = all_trusted and trusted
            if trusted:
                winning_code = "|".join(arm_attr["result_code"].astype(str))
                winner = arm_ticket[arm_ticket["ticket_code"].eq(winning_code)]
                units = int(winner["units"].iloc[0]) if len(winner) else 0
                product_sp = float(arm_attr["winning_sp"].astype(float).prod())
                reconstructed_units += units
                reconstructed_gross += (
                    units * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR * product_sp
                )
        if bool(bundle["native_included"]) != all_trusted:
            raise ContractError(f"{issue}/{variant}: native inclusion differs from settlement")
        if all_trusted:
            if not np.isclose(float(bundle["gross_cny"]), reconstructed_gross, rtol=0, atol=1e-8):
                raise ContractError(f"{issue}/{variant}: gross payout does not reconstruct")
            if int(bundle["winning_ticket_units"]) != reconstructed_units:
                raise ContractError(f"{issue}/{variant}: winning units do not reconstruct")
            if bool(bundle["ticket_hit"]) != bool(reconstructed_units > 0):
                raise ContractError(f"{issue}/{variant}: ticket hit does not reconstruct")
            if bool(bundle["issue_profitable"]) != bool(reconstructed_gross > ISSUE_STAKE_CNY):
                raise ContractError(f"{issue}/{variant}: profitable flag does not reconstruct")


def _verify_settlement_source(repo_root: Path, attribution: pd.DataFrame) -> None:
    settlement = _load_mixed_history_package(repo_root)["extension_settlement"].copy()
    settlement["issue"] = settlement["issue"].astype(str)
    source = settlement.set_index(["issue", "match_idx"])
    for row in attribution.itertuples():
        key = (str(row.issue), int(row.match_idx))
        if key not in source.index:
            raise ContractError("attribution fixture is absent from accepted settlement")
        truth = source.loc[key]
        if isinstance(truth, pd.DataFrame):
            raise ContractError("accepted settlement fixture key is not unique")
        if bool(row.settlement_available) != bool(truth["settlement_available"]):
            raise ContractError("settlement availability differs from accepted source")
        if bool(row.settlement_available):
            if str(row.result_code) != str(truth["result_code"]):
                raise ContractError("result code differs from accepted settlement")
            # An arm with one untrusted selected fixture is excluded as a
            # whole.  Its attribution intentionally suppresses every SP even
            # when some sibling fixtures are individually trusted.
            if np.isfinite(float(row.winning_sp)) and not np.isclose(
                float(row.winning_sp),
                float(truth["winning_sp"]),
                rtol=0,
                atol=1e-12,
            ):
                raise ContractError("winning SP differs from accepted settlement")


def _verify_mapping_receipts(stored: dict[str, Any]) -> None:
    receipts = stored["mapping_receipts"]
    summary = stored["mapping_summary"]
    selections = stored["selections"]
    weights = stored["weights"]
    expected_keys = set(
        zip(selections["issue"].astype(str), selections["policy"].astype(str), strict=True)
    )
    receipt_keys = {(str(item["issue"]), str(item["policy"])) for item in receipts}
    if len(receipts) != 366 or receipt_keys != expected_keys:
        raise ContractError("mapping receipt census differs from 122 issues x 3 policies")
    if weights.duplicated(["target_issue", "policy"]).any():
        raise ContractError("weight receipt keys are not unique")
    weight_keys = set(
        zip(weights["target_issue"].astype(str), weights["policy"].astype(str), strict=True)
    )
    if weight_keys != expected_keys:
        raise ContractError("weight receipt keys differ from mapping targets")
    for item in receipts:
        receipt = item["receipt"]
        cutoff = pd.Timestamp(receipt["cutoff_ts"])
        maximum_label = pd.Timestamp(receipt["maximum_training_label_timestamp"])
        if not maximum_label < cutoff:
            raise ContractError("mapping admits label at or after target cutoff")
        if receipt["cutoff_identity"] != f"DECISION_EPOCH_{item['issue']}":
            raise ContractError("mapping cutoff identity differs from target issue")
        if str(receipt["source_hashes"].get("fit_thread_limit")) != str(FIT_THREAD_LIMIT):
            raise ContractError("mapping receipt omits frozen fit thread limit")
        candidate_hash = str(
            receipt["source_hashes"].get("admitted_candidate_frame_sha256", "")
        )
        shared_hash = str(receipt.get("admitted_history_sha256", ""))
        if len(candidate_hash) != 64 or len(shared_hash) != 64:
            raise ContractError("mapping admitted-history hashes are incomplete")
    _assert_scientific_frame("mapping summary", summary, _mapping_summary(receipts))


def _semantic_verify(repo_root: Path, stored: dict[str, Any]) -> None:
    bundles = stored["bundles"]
    tickets = stored["tickets"]
    performance = stored["performance"]
    contrasts = stored["contrasts"]
    _verify_registry(stored["registry"])
    if not bundles["stake_cny"].dropna().eq(ISSUE_STAKE_CNY).all():
        raise ContractError("standalone/mixed issue budget differs from CNY1,024")
    funded = tickets.groupby(["issue", "variant"], observed=True)["units"].sum()
    if not funded.eq(FUNDED_UNITS).all():
        raise ContractError("ticket funded units differ from 512")
    if not np.allclose(
        bundles.loc[bundles["native_included"], "pnl_cny"],
        bundles.loc[bundles["native_included"], "gross_cny"] - ISSUE_STAKE_CNY,
        rtol=0,
        atol=1e-8,
    ):
        raise ContractError("bundle PnL identity fails")
    _verify_extension_tickets(bundles, tickets, stored["attribution"])
    _verify_settlement_source(repo_root, stored["attribution"])
    _verify_mapping_receipts(stored)
    if set(contrasts["bootstrap_estimand"]) != {"paired_mean_cny_per_issue"}:
        raise ContractError("bootstrap estimand is ambiguous")
    if set(contrasts["bootstrap_unit"]) != {"CNY_PER_ISSUE"}:
        raise ContractError("bootstrap unit is ambiguous")
    if (
        contrasts["armwise_ex_largest_lift_cny"]
        .eq(contrasts["largest_absolute_paired_delta_sensitivity_cny"])
        .all()
    ):
        raise ContractError("distinct tail statistics collapsed to one field")
    # Independently rebuild armwise ex-largest differences from performance on
    # the exact-common scopes. This catches the #394 semantic regression.
    for row in contrasts.itertuples():
        a = performance[
            performance["denominator"].eq("EXACT_COMMON")
            & performance["scope"].eq(row.scope)
            & performance["variant"].eq(row.subject_variant)
        ]
        b = performance[
            performance["denominator"].eq("EXACT_COMMON")
            & performance["scope"].eq(row.scope)
            & performance["variant"].eq(row.reference_variant)
        ]
        expected = float(a.iloc[0]["ex_largest_pnl_cny"] - b.iloc[0]["ex_largest_pnl_cny"])
        if not np.isclose(expected, row.armwise_ex_largest_lift_cny, rtol=0, atol=1e-8):
            raise ContractError("armwise ex-largest lift does not reconcile")
    recomputed_performance, exact_common = _performance(bundles)
    _assert_scientific_frame("performance", performance, recomputed_performance)
    _assert_scientific_frame(
        "matched contrasts", contrasts, _contrasts(bundles, exact_common)
    )
    _assert_scientific_frame(
        "capital paths", stored["capital_paths"], _capital_paths(bundles, exact_common)
    )
    _assert_scientific_frame(
        "coverage ledger",
        stored["issue_ledger"],
        _coverage_ledger(bundles, stored["attribution"], repo_root),
    )
    _assert_scientific_frame(
        "turnover",
        stored["turnover"],
        _turnover(
            bundles[bundles["issue_year"].isin(YEARS)],
            stored["attribution"],
            tickets,
        ),
    )
    _assert_scientific_frame(
        "Pareto diagnostic", stored["pareto"], _pareto_frontier(performance)
    )


def verify_package(
    repo_root: Path,
    data_root: Path | None = None,
    *,
    replay: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    package = repo_root / RESULT_PACKAGE
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest["contract"] != CONTRACT_ID or manifest["source_merge_sha"] != SOURCE_MERGE_SHA:
        raise ContractError("manifest contract/source binding differs")
    actual = {p.name for p in package.iterdir() if p.is_file() and p.name != "MANIFEST.json"}
    if actual != set(manifest["files"]):
        raise ContractError("package file census differs")
    for name, item in manifest["files"].items():
        if sha256_file(package / name) != item["sha256"]:
            raise ContractError(f"manifest hash differs for {name}")
    for path, digest in manifest["deliveries"].items():
        if not (repo_root / path).exists() or sha256_file(repo_root / path) != digest:
            raise ContractError(f"delivery hash differs for {path}")
    if manifest["implementation"]["pipeline_sha256"] != sha256_file(Path(__file__)):
        raise ContractError("pipeline implementation hash differs")
    if manifest["implementation"]["contract_sha256"] != sha256_file(Path(__file__).with_name("contract.py")):
        raise ContractError("contract implementation hash differs")
    implementation_files = {
        "runner_sha256": repo_root / "scripts/run_n7_variant_extension.py",
        "verifier_sha256": repo_root / "scripts/verify_n7_variant_extension.py",
        "tests_sha256": repo_root / "tests/test_n7_variant_extension.py",
    }
    for key, path in implementation_files.items():
        if manifest["implementation"].get(key) != sha256_file(path):
            raise ContractError(f"{key} implementation hash differs")
    stored = {key: _read(package / name) for name, key in PACKAGE_FILES.items()}
    if stored["source"]["source_394_manifest_sha256"] != sha256_file(
        repo_root / "results/n7_mixed_full_history/MANIFEST.json"
    ):
        raise ContractError("source #394 package changed")
    if stored["decision"]["verdict"] != VERDICT or stored["decision"]["promotion_authorized"]:
        raise ContractError("decision boundary differs")
    upstream_manifests = {
        "n7_support_shape_manifest_sha256": "results/n7_support_shape/MANIFEST.json",
        "n7_support_transfer_manifest_sha256": "results/n7_support_transfer_grid/MANIFEST.json",
        "n7_cutoff_walkforward_manifest_sha256": "results/n7_cutoff_walkforward/MANIFEST.json",
        "n7_mixed_history_manifest_sha256": "results/n7_mixed_full_history/MANIFEST.json",
    }
    for key, relative in upstream_manifests.items():
        if stored["source"]["source_hashes"].get(key) != sha256_file(repo_root / relative):
            raise ContractError(f"upstream source binding differs for {key}")
    _semantic_verify(repo_root, stored)
    if replay:
        regenerated = scientific_frames(repo_root, data_root)
        for name, key in PACKAGE_FILES.items():
            if key in {"mapping_receipts", "source", "decision"}:
                if _json_hash(stored[key]) != _json_hash(regenerated[key]):
                    raise ContractError(f"source replay differs for {key}")
            else:
                _assert_scientific_frame(
                    f"source replay {key}", stored[key], regenerated[key]
                )
    return {
        "contract": CONTRACT_ID,
        "status": "PASS",
        "variants": int(stored["registry"]["variant"].nunique()),
        "bundle_rows": int(len(stored["bundles"])),
        "ticket_rows": int(len(stored["tickets"])),
        "source_bound_replay": bool(replay),
    }
