#!/usr/bin/env python3
"""Join frozen #286 manifests to development outcomes in a separate process."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue282.actions import PrototypeAction  # noqa: E402
from issue282.labels import materialize_action_labels  # noqa: E402
from issue286.settlement import MatchSettlement, parse_ticket_identity  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "results/issue-286")
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-286")
    parser.add_argument("--batch-size", type=int, default=200_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = args.manifest.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((manifest / "label_free_manifest_receipt.json").read_text())
    manifest_paths = {
        "base": manifest / "base_tickets.parquet",
        "candidate": manifest / "protection_candidates.parquet",
        "continuation": manifest / "continuation_tickets.parquet",
    }
    for name, path in manifest_paths.items():
        observed = _sha256(path)
        expected = receipt["manifest_sha256"][name]
        if observed != expected:
            raise RuntimeError(f"{name} manifest hash mismatch before settlement")
    print("manifest hashes verified; opening development settlement", flush=True)
    tensor = build_tensor()
    if tensor["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ settlement seal violated")
    winners = (
        tensor.loc[
            tensor["Y"].eq(1),
            ["issue", "match_idx", "realized_outcome", "SP_SETTLE"],
        ]
        .drop_duplicates(["issue", "match_idx"])
        .assign(issue=lambda frame: frame["issue"].astype(str))
    )
    settlement = {
        (str(row.issue), str(row.match_idx)): MatchSettlement(
            str(row.realized_outcome), float(row.SP_SETTLE)
        )
        for row in winners.itertuples(index=False)
    }
    units = build_match_units(tensor)
    probabilities = pd.read_parquet(
        ROOT / "results/issue-209/market_only_probabilities.parquet"
    )
    values = pd.read_parquet(ROOT / "results/issue-209/cell_value_distribution.parquet")
    formal_baseline = materialize_action_labels(
        units,
        probabilities,
        values,
        tensor,
        actions=(
            PrototypeAction(
                "ALL", "MARKET_PROBABILITY", 7, "TOP_VALUE", 8
            ),
        ),
        stream_seeds=(286_001,),
    )
    formal_baseline.to_parquet(
        output / "formal_baseline_n7_k8_market_top.parquet", index=False
    )
    base_first = (
        pd.read_parquet(
            manifest_paths["base"],
            columns=["issue", "issue_year", "subset_id", "action_key", "ticket_identity"],
        )
        .groupby(["issue", "issue_year", "subset_id", "action_key"], as_index=False)
        .first()
    )
    action_rows = []
    for row in base_first.itertuples(index=False):
        legs = parse_ticket_identity(row.ticket_identity)
        values = [settlement.get((str(row.issue), match_id)) for match_id, _ in legs]
        valid = all(
            value is not None
            and np.isfinite(value.winning_sp)
            and value.winning_sp > 0
            for value in values
        )
        typed = [value for value in values if value is not None]
        winning_identity = (
            "|".join(
                f"{match_id}:{value.realized_outcome}"
                for (match_id, _), value in zip(legs, typed, strict=True)
            )
            if valid
            else ""
        )
        gross = (
            2.0 * 0.65 * float(np.prod([value.winning_sp for value in typed]))
            if valid
            else 0.0
        )
        action_rows.append(
            {
                "issue": str(row.issue),
                "issue_year": int(row.issue_year),
                "subset_id": str(row.subset_id),
                "action_key": str(row.action_key),
                "settlement_valid": bool(valid),
                "winning_identity": winning_identity,
                "winning_ticket_gross_cny": gross,
            }
        )
    action_settlement = pd.DataFrame(action_rows)
    action_settlement.to_parquet(output / "action_settlement_map.parquet", index=False)
    action_index = action_settlement.set_index(
        ["issue", "subset_id", "action_key"]
    )[["settlement_valid", "winning_identity", "winning_ticket_gross_cny"]]
    shared_action_features = [
        "n",
        "k",
        "selector",
        "outcome_mode",
        "generator",
        "issue_match_count",
        "issue_probability_entropy_mean",
        "issue_probability_max_mean",
        "issue_divergence_abs_mean",
        "issue_divergence_abs_max",
        "issue_native_line_abs_mean",
        "issue_books_mean",
    ]
    specs = {
        "base": (
            "ticket_identity",
            [
                "ticket_index",
                "ticket_probability_product",
                "ticket_divergence_sum",
                *shared_action_features,
            ],
        ),
        "candidate": (
            "candidate_identity",
            [
                "candidate_rank",
                "parent_ticket_index",
                "protected_leg",
                "selected_outcome_position",
                "alternative_outcome_position",
                "selected_probability",
                "alternative_probability",
                "probability_delta",
                "selected_divergence",
                "alternative_divergence",
                "divergence_delta",
                "match_entropy",
                "proposal_margin_delta",
                "parent_ticket_probability_product",
                "candidate_probability_product",
                *shared_action_features,
            ],
        ),
        "continuation": ("ticket_identity", ["continuation_rank"]),
    }
    output_hashes = {}
    output_rows = {}
    for name, (identity_column, extra_keys) in specs.items():
        source = pq.ParquetFile(manifest_paths[name])
        destination = output / f"{name}_settlement_labels.parquet"
        temporary = destination.with_suffix(".tmp.parquet")
        writer = None
        count = 0
        try:
            columns = [
                "issue",
                "issue_year",
                "subset_id",
                "action_key",
                identity_column,
                *extra_keys,
            ]
            for batch in source.iter_batches(batch_size=args.batch_size, columns=columns):
                frame = batch.to_pandas()
                frame["issue"] = frame["issue"].astype(str)
                frame = frame.join(
                    action_index,
                    on=["issue", "subset_id", "action_key"],
                    validate="many_to_one",
                )
                valid = frame["settlement_valid"].fillna(False).to_numpy(bool)
                hit = valid & frame[identity_column].eq(frame["winning_identity"]).to_numpy()
                frame["hit"] = hit.astype(np.int8)
                frame["stake_cny"] = np.where(valid, 2.0, 0.0)
                frame["gross_cny"] = np.where(
                    hit, frame["winning_ticket_gross_cny"].to_numpy(float), 0.0
                )
                frame["pnl_cny"] = frame["gross_cny"] - frame["stake_cny"]
                frame = frame.drop(columns=["winning_identity", "winning_ticket_gross_cny"])
                table = pa.Table.from_pandas(frame, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
                writer.write_table(table)
                count += len(frame)
        finally:
            if writer is not None:
                writer.close()
        if writer is None:
            raise RuntimeError(f"no {name} settlement rows generated")
        temporary.replace(destination)
        output_hashes[name] = _sha256(destination)
        output_rows[name] = count
        print(f"settled {name} rows={count}", flush=True)
    settlement_receipt = {
        "contract": "BJ-UNIFIED-JOINT-PROTECTION-001/settlement-v1",
        "verified_manifest_sha256": receipt["manifest_sha256"],
        "settlement_rows": output_rows,
        "settlement_output_sha256": output_hashes,
        "development_years": sorted(int(value) for value in tensor["issue_year"].unique()),
        "sealed_years_opened": [],
        "ticket_stake_cny": 2.0,
        "payout_coefficient": 0.65,
        "payout_application": "ONCE_PER_WINNING_COMPLETE_N_FOLD",
        "invalid_action_count": int((~action_settlement["settlement_valid"]).sum()),
        "formal_baseline": "SALL_OMARKET_N7_TOP_VALUE_K8",
        "formal_baseline_rows": len(formal_baseline),
    }
    _atomic_json(settlement_receipt, output / "settlement_receipt.json")
    print(json.dumps(settlement_receipt, indent=2), flush=True)
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
