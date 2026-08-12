#!/usr/bin/env python3
"""Build the complete #145 outcome-code allocation-versus-target atlas.

The settlement ledger deliberately stores one row per issue/configuration.  This
additive report expands each settled configuration to all 2,187 canonical N7
codes, separating (a) target probability mass, (b) allocated ticket frequency,
and (c) actual outcome hits.  No candidate or allocation parameter is selected
from outcomes here; the Gate-A identity/role vectors remain the sole source of
weights and allocation order.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import gzip
import importlib.util
import json
import math
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


SCRIPT = Path(__file__).resolve()
ROOT = next(
    path
    for path in (SCRIPT.parent, *SCRIPT.parents)
    if (path / ".git").exists() and (path / "results").is_dir()
)
RUNNER_PATH = SCRIPT.parent / "settle_bj145_ticket_allocation_gate_b.py"
GATE_A = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
ARMS = ("PRIMARY_NO_GATE_K4", "SECONDARY_ESP300_GM290_K8")
K = 3**7
WEIGHTS = (
    "MODEL_P_CAL",
    "MARKET_WF_CAL",
    "BLEND_A25",
    "BLEND_A50",
    "BLEND_A75",
    "Q_WEIGHT",
)
MECHANISM_CODE = {
    "WR_DUPLICATE_STAKE": 0,
    "WOR_DISTINCT": 1,
    "RESIDUAL_SYSTEMATIC": 2,
    "CAPPED_REPEAT": 3,
    "DETERMINISTIC_TOP_MASS": 4,
    "FULL_ENUMERATED": 5,
}
FIELDS = (
    "scope",
    "scope_value",
    "arm_id",
    "weight_source",
    "mechanism",
    "sampling_role",
    "cap",
    "M",
    "seed",
    "ticket_code",
    "settled_issue_count",
    "identity_count",
    "draw_count",
    "target_mass_sum",
    "target_mass_mean",
    "allocated_draw_count",
    "realized_frequency",
    "frequency_delta",
    "actual_outcome_identity_count",
    "actual_outcome_hit_ticket_count",
    "actual_hit_frequency",
    "target_denominator_rule",
    "realized_denominator_rule",
    "actual_hit_rule",
)


def load_runner():
    spec = importlib.util.spec_from_file_location("bj145_marginal_runner", RUNNER_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("runner import unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_library(source: Path, output: Path) -> Path:
    if output.exists():
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        (
            "g++",
            "-O3",
            "-std=c++17",
            "-shared",
            "-fPIC",
            str(source),
            "-o",
            str(output),
        ),
        check=True,
    )
    return output


def fmt(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.12f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--library", type=Path, default=ROOT / ".scratch" / "bj145_code_marginals.so"
    )
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("invalid shard selection")
    runner = load_runner()
    engine, _, _ = runner.load_engine()
    outcomes = runner.load_outcomes()
    _, identities_by_issue, _, _ = runner.load_freeze(engine, outcomes)
    conn = sqlite3.connect(args.stage / "issue_allocation_index.sqlite")
    # Derive support directly from the completed settlement index so this
    # atlas follows the exact positive-stake denominator used by summaries.
    settled_instances: dict[str, set[str]] = defaultdict(set)
    for arm in ARMS:
        full_config = f"{arm}|Q_WEIGHT|FULL_ENUMERATED|FULL_CONTROL|NA|2187|NA"
        for payload, issue_instance in conn.execute(
            "SELECT payload,issue_instance FROM issue_rows WHERE config=?",
            (full_config,),
        ):
            row = json.loads(payload)
            if (
                row["settlement_status"] == "SETTLED"
                and float(row["planned_stake_yuan"]) > 0
            ):
                settled_instances[arm].add(issue_instance)
    identities = {
        arm: [
            identity
            for key, values in sorted(identities_by_issue.items())
            if key[0] == arm and key[1] in settled_instances[arm]
            for identity in values
            if identity.truth_index is not None
        ]
        for arm in ARMS
    }
    issue_counts = {
        arm: len({identity.issue_instance for identity in values})
        for arm, values in identities.items()
    }
    # The atlas is denominated on settled positive-stake support, not the
    # larger Gate-A availability cohort.  Missing canonical outcomes therefore
    # contribute no identity/draw mass here and remain separately reported in
    # the issue ledger and surface summaries.
    expected_ids = {"PRIMARY_NO_GATE_K4": 1016, "SECONDARY_ESP300_GM290_K8": 1528}
    expected_issues = {"PRIMARY_NO_GATE_K4": 254, "SECONDARY_ESP300_GM290_K8": 191}
    if {
        arm: len(values) for arm, values in identities.items()
    } != expected_ids or issue_counts != expected_issues:
        raise RuntimeError(
            f"settled identity support drift: ids={ {arm: len(values) for arm, values in identities.items()} }, issues={issue_counts}"
        )
    config_rows = list(
        conn.execute(
            "SELECT DISTINCT arm_id,weight_source,mechanism,sampling_role,cap,seed FROM issue_rows ORDER BY arm_id,weight_source,mechanism,cap,seed"
        )
    )
    groups: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
    for arm, weight, mechanism, role, cap, seed in config_rows:
        key = (arm, weight, mechanism, cap, seed)
        values = groups.setdefault(key, {"role": role, "ms": []})
        if values["role"] != role:
            raise RuntimeError(f"sampling-role drift for {key}")
        values["ms"].append(None)
    for arm, weight, mechanism, role, cap, seed in config_rows:
        key = (arm, weight, mechanism, cap, seed)
        row = conn.execute(
            "SELECT DISTINCT m_value FROM issue_rows WHERE arm_id=? AND weight_source=? AND mechanism=? AND cap=? AND seed=? ORDER BY m_value",
            (arm, weight, mechanism, cap, seed),
        ).fetchall()
        groups[key]["ms"] = [int(item[0]) for item in row]
    if len(config_rows) != 156:
        raise RuntimeError(f"configuration count drift: {len(config_rows)}")
    m_cell_count = sum(len(group["ms"]) for group in groups.values())
    if m_cell_count != 2892:
        raise RuntimeError(f"M-cell count drift: {m_cell_count}")
    ordered_groups = sorted(groups.items())
    selected_groups = [
        (index, key, group)
        for index, (key, group) in enumerate(ordered_groups)
        if index % args.shard_count == args.shard_index
    ]

    source = SCRIPT.parent / "bj145_fast_alloc.cpp"
    library = ctypes.CDLL(str(compile_library(source, args.library)))
    aggregate = library.bj145_code_aggregate_grid
    aggregate.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_char_p),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_longlong),
        ctypes.POINTER(ctypes.c_longlong),
        ctypes.POINTER(ctypes.c_longlong),
    ]
    aggregate.restype = None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = args.output.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = __import__("io").TextIOWrapper(zipped, newline="", encoding="utf-8")
    writer = csv.DictWriter(
        text, fieldnames=FIELDS, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    try:
        for index, key, group in selected_groups:
            arm, weight, mechanism, cap, seed = key
            cohort = identities[arm]
            n = len(cohort)
            ms = tuple(group["ms"])
            if not ms or mechanism not in MECHANISM_CODE:
                raise RuntimeError(f"invalid group: {key}")
            flat = (ctypes.c_double * (n * K))()
            truths = (ctypes.c_int * n)()
            signatures_bytes = []
            for row_index, identity in enumerate(cohort):
                vector = identity.weights(weight)
                for ordinal, value in enumerate(vector):
                    flat[row_index * K + ordinal] = value
                truths[row_index] = int(identity.truth_index)
                signatures_bytes.append(
                    ("|".join(role["match_id"] for role in identity.roles)).encode(
                        "utf-8"
                    )
                )
            signatures = (ctypes.c_char_p * n)(*signatures_bytes)
            m_array = (ctypes.c_int * len(ms))(*ms)
            cells = len(ms) * K
            allocated = (ctypes.c_longlong * cells)()
            actual_identity = (ctypes.c_longlong * cells)()
            actual_hit = (ctypes.c_longlong * cells)()
            cap_value = 0 if cap == "NA" else int(cap)
            seed_bytes = str(seed).encode("ascii")
            aggregate(
                flat,
                n,
                K,
                truths,
                signatures,
                MECHANISM_CODE[mechanism],
                cap_value,
                seed_bytes,
                m_array,
                len(ms),
                allocated,
                actual_identity,
                actual_hit,
            )
            target = [
                math.fsum(
                    float(identity.weights(weight)[ordinal]) for identity in cohort
                )
                for ordinal in range(K)
            ]
            for m_index, m in enumerate(ms):
                draw_count = n * m
                for ordinal in range(K):
                    target_sum = target[ordinal]
                    target_mean = target_sum / n
                    alloc_count = int(allocated[m_index * K + ordinal])
                    realized = alloc_count / draw_count if draw_count else None
                    delta = realized - target_mean if realized is not None else None
                    actual_ids = int(actual_identity[m_index * K + ordinal])
                    actual_hits = int(actual_hit[m_index * K + ordinal])
                    writer.writerow(
                        {
                            "scope": "ALL",
                            "scope_value": "ALL",
                            "arm_id": arm,
                            "weight_source": weight,
                            "mechanism": mechanism,
                            "sampling_role": group["role"],
                            "cap": cap,
                            "M": m,
                            "seed": seed,
                            "ticket_code": engine.ticket_code(ordinal),
                            "settled_issue_count": issue_counts[arm],
                            "identity_count": n,
                            "draw_count": draw_count,
                            "target_mass_sum": fmt(target_sum),
                            "target_mass_mean": fmt(target_mean),
                            "allocated_draw_count": alloc_count,
                            "realized_frequency": fmt(realized),
                            "frequency_delta": fmt(delta),
                            "actual_outcome_identity_count": actual_ids,
                            "actual_outcome_hit_ticket_count": actual_hits,
                            "actual_hit_frequency": fmt(
                                actual_hits / draw_count if draw_count else None
                            ),
                            "target_denominator_rule": "mean over settled positive-stake selected identities; complete 2,187-code space",
                            "realized_denominator_rule": "allocated ticket copies across the same settled positive-stake identities",
                            "actual_hit_rule": "truth-code identity count and allocated tickets matching canonical settled truth; never pooled across issues",
                        }
                    )
            if (len([item for item in selected_groups if item[0] <= index])) % 4 == 0:
                text.flush()
                print(
                    f"marginal shard {args.shard_index}: {len([item for item in selected_groups if item[0] <= index])}/{len(selected_groups)}",
                    flush=True,
                )
    finally:
        text.flush()
        text.detach()
        zipped.close()
        raw.close()
        conn.close()
    print(
        json.dumps(
            {
                "groups": len(selected_groups),
                "total_groups": len(groups),
                "total_m_cells": m_cell_count,
                "rows": sum(len(group["ms"]) for _, _, group in selected_groups) * K,
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
