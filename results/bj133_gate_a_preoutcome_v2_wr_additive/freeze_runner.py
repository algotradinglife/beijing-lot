#!/usr/bin/env python3
"""Freeze the additive #133 WR ticket-sampling control without outcomes.

This is deliberately a compact additive Gate-A package.  It binds the exact
accepted v1 allocation plan and expands every non-FULL plan over the original
three frozen seeds, replacing only its ticket sampling rule with independent
Q-weighted draws *with* replacement.  It never opens an outcome, SP, payout,
tax, settlement, or ROI source.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable


CONTRACT = "BJ-HIST-DIVERSIFIED-N7-ALLOCATOR-001"
VERSION = "bj133-gate-a-v2-wr-additive"
CONTENT_VERSION = "bj133-gate-a-v2-wr-additive-content-v1"
V1_MANIFEST = "1fff3f904fcb9a5efed231771880be8ae0603b0d8f3c7d0365937fcfe9985e79"
SEEDS = ("133001", "133002", "133003")


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
SOURCE = ROOT / "results" / "bj133_gate_a_preoutcome_v1"
OUTPUT = ROOT / "results" / "bj133_gate_a_preoutcome_v2_wr_additive"

PLAN_REQUIRED = {
    "config_id", "config_role", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance",
    "allocator_id", "allocator_family", "ticket_M", "probability_vector", "ticket_mechanism",
    "selected_identity_count", "selected_portfolio_ids", "selection_status", "planned_draw_count",
    "planned_stake_yuan", "outcome_boundary",
}
SAMPLER_FIELDS = (
    "config_id", "config_role", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance",
    "allocator_id", "allocator_family", "ticket_M", "probability_vector", "ticket_mechanism",
    "seed", "seed_role", "source_ticket_mechanism", "duplicate_policy", "selected_identity_count",
    "selected_portfolio_ids", "selection_status", "planned_draw_count", "planned_stake_yuan",
    "outcome_boundary",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verified_manifest(path: Path, expected: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected:
        raise RuntimeError("unaccepted Gate-A v1 manifest")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: sha256(item)
        for item in path.iterdir()
        if item.is_file() and item.name != manifest_path.name
    }
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError("Gate-A v1 manifest coverage drift")
    return declared


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def load_v1() -> tuple[dict[str, str], list[dict[str, str]]]:
    manifest = verified_manifest(SOURCE, V1_MANIFEST)
    card = json.loads((SOURCE / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_DIVERSIFIED_ALLOCATION_FREEZE":
        raise RuntimeError("unexpected Gate-A v1 card")
    with (SOURCE / "allocation_plan.csv").open(newline="", encoding="utf-8") as handle:
        plans = list(csv.DictReader(handle))
    if not plans or not PLAN_REQUIRED <= set(plans[0]):
        raise RuntimeError("Gate-A v1 allocation plan lacks required surface")
    if len(plans) != 20_880:
        raise RuntimeError(f"Gate-A v1 plan denominator drift: {len(plans)}")
    keys = {(row["config_id"], row["allocator_id"], row["issue_instance"]) for row in plans}
    if len(keys) != len(plans):
        raise RuntimeError("Gate-A v1 allocation-plan uniqueness drift")
    return manifest, plans


def freeze(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj133_gate_a_v2_", dir=output.parent))
    try:
        v1_manifest, plans = load_v1()
        rows: list[dict[str, object]] = []
        for plan in plans:
            if plan["ticket_mechanism"] == "EXACT_K4_FULL":
                continue
            if plan["ticket_mechanism"] != "Q_INFORMED_WOR_DISTINCT":
                raise RuntimeError("unexpected non-FULL Gate-A v1 sampler")
            for seed in SEEDS:
                rows.append({
                    "config_id": plan["config_id"], "config_role": plan["config_role"], "gate_id": plan["gate_id"],
                    "top_k_id": plan["top_k_id"], "issue": plan["issue"], "fold": plan["fold"], "year": plan["year"],
                    "issue_instance": plan["issue_instance"], "allocator_id": plan["allocator_id"],
                    "allocator_family": plan["allocator_family"], "ticket_M": plan["ticket_M"],
                    "probability_vector": plan["probability_vector"], "ticket_mechanism": "Q_INFORMED_WR_DUPLICATE_STAKE",
                    "seed": seed, "seed_role": "PRIMARY" if seed == SEEDS[0] else "SENSITIVITY",
                    "source_ticket_mechanism": plan["ticket_mechanism"],
                    "duplicate_policy": "EACH_INDEPENDENT_DRAW_IS_A_SEPARATE_Y2_TICKET_AND_TAX_UNIT",
                    "selected_identity_count": plan["selected_identity_count"], "selected_portfolio_ids": plan["selected_portfolio_ids"],
                    "selection_status": plan["selection_status"], "planned_draw_count": plan["planned_draw_count"],
                    "planned_stake_yuan": plan["planned_stake_yuan"],
                    "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted",
                })
        rows.sort(key=lambda row: (int(str(row["year"])), int(str(row["issue"])), str(row["gate_id"]), str(row["config_id"]), str(row["allocator_id"]), str(row["seed"])))
        if len(rows) != 46_980:
            raise RuntimeError(f"WR sampler denominator drift: {len(rows)}")
        source_keys = {
            (plan["config_id"], plan["allocator_id"], plan["issue_instance"])
            for plan in plans if plan["ticket_mechanism"] == "Q_INFORMED_WOR_DISTINCT"
        }
        wr_keys = {(str(row["config_id"]), str(row["allocator_id"]), str(row["issue_instance"])) for row in rows}
        if source_keys != wr_keys:
            raise RuntimeError("WR sampler does not exactly cover Gate-A v1 sampled arms")
        if {str(row["seed"]) for row in rows} != set(SEEDS):
            raise RuntimeError("WR sampler seed set drift")
        write_csv(stage / "wr_sampler_plan.csv", SAMPLER_FIELDS, rows)
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj133_gate_a_preoutcome_v1", "role": "accepted immutable complete-issue allocation and candidate freeze", "identity": "SHA256SUMS.json", "sha256": V1_MANIFEST, "rows": len(plans), "join_status": "all non-FULL Q_INFORMED_WOR_DISTINCT plans expand to the identical complete-issue/config/allocator/M/seed surface with WR only"},
        ])
        card = {
            "issue": 133,
            "contract": CONTRACT,
            "generator_version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_WR_DUPLICATE_STAKE_ADDITIVE_FREEZE",
            "v1_binding": {"path": "results/bj133_gate_a_preoutcome_v1", "manifest_sha256": V1_MANIFEST, "allocation_plan_sha256": v1_manifest["allocation_plan.csv"]},
            "frozen_arm": {
                "ticket_mechanism": "Q_INFORMED_WR_DUPLICATE_STAKE",
                "definition": "For each selected identity and frozen seed, M independent Q-weighted draws are made with replacement over its 3^7 ticket space. Every draw is a separate ¥2 ticket. Exact duplicate code vectors are retained as separate paid stakes and separate individual tax units.",
                "coverage": "Every non-FULL Gate-A v1 row, with identical complete-issue identities, gate, K, M, selected portfolio IDs, allocation status, and seed set.",
            },
            "controls_retained": ["Q_INFORMED_WOR_DISTINCT remains an unchanged v1 sensitivity arm", "Q_DELETE, MATCH_EXPOSURE and JACCARD allocation rows remain explicit controls on the same selected-identity surface", "EXACT_K4_FULL remains the v1 capital-normalized economic reference and is not resampled"],
            "outcome_boundary": "No test outcome, score, final/winning SP, settlement, payout, ROI, tax realization, or post-kickoff input is read or emitted.",
            "scope": "historical paper research only; no purchase, production, betting, or promotion authority.",
            "denominator": {"v1_allocation_rows": len(plans), "wr_sampler_rows": len(rows), "seed_set": list(SEEDS)},
        }
        (stage / "gate_a_v2_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "freeze_runner.py")
        (stage / "README.md").write_text(
            "# #133 Gate A v2 additive WR control\n\n"
            "This outcome-unexposed additive package binds accepted Gate-A v1 and freezes a with-replacement Q sampler for the exact same non-FULL allocation rows and seeds. "
            "Duplicate draws remain separate ¥2 tickets. Replay with `python3 freeze_runner.py --output <new-dir>`; staging occurs under `results/`, never `/tmp`.\n",
            encoding="utf-8",
        )
        content = {
            "contract_version": CONTENT_VERSION,
            "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {
            "output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"),
            "wr_sampler_rows": len(rows), "source_v1_manifest_sha256": V1_MANIFEST,
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
