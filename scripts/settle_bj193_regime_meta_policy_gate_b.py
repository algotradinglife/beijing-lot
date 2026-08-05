#!/usr/bin/python3
"""Settle #193's frozen three-stage regime-conditioned N7 meta-policy.

Execution is split at an immutable replay checkpoint.  Gate-B v2 binds both
accepted Gate-A layers and executes selection, conditional direction and
conditional allocation as three separately screened/fitted chronological
models.  The historical flattened checkpoint code remains below only as
auditable implementation provenance and is not an executable v2 path.
"""
from __future__ import annotations

import argparse
import array
import csv
import ctypes
import gzip
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GATE_A = ROOT / "results" / "bj193_gate_a_preoutcome_v1"
GATE_A_V2 = ROOT / "results" / "bj193_gate_a_chain_interface_v2"
DEFAULT_CHECKPOINT = ROOT / ".scratch" / "bj193_gate_b_chain_checkpoint_v2"
DEFAULT_OUTPUT = ROOT / "results" / "bj193_gate_b_regime_meta_policy_v2"
EXPECTED_GATE_A_MANIFEST = (
    "408e8aa69cf2d336f8b3b65b1c94b30a3456864af01517a78fc27b3f2bab0c45"
)
EXPECTED_GATE_A_CONTENT = (
    "9bf90d1553613cbb50770ea51deece1fb40cfb05a0ace9103ab62194faff3131"
)
EXPECTED_GATE_A_V2_MANIFEST = (
    "6a44f4b1b355f5476328424bc8d92271d61d585643d40ca42bb56ffda1c43933"
)
EXPECTED_GATE_A_V2_CONTENT = (
    "a5f274f92edbff194be9ce60fa707196d20d255b608b08bf22c3f0d924bb7425"
)
EXPECTED_GATE_A_V2_PORTABLE = (
    "2bd83000fabf0a4817a31964a02c881562489651cc98143c716aa09ac8dd92bd"
)
CHECKPOINT_CONTRACT = "bj193-gate-b-three-stage-checkpoint-v2"
OUTPUT_CONTRACT = "bj193-gate-b-three-stage-regime-meta-policy-v2"
SCIENCE_CELLS = 963
ATLAS_SELECTOR_COUNT = 492
CANONICAL_ISSUE_COUNT = 344
REPLAY_CPP = ROOT / "scripts" / "bj193_exact_replay.cpp"
FROZEN_ALLOCATOR = ROOT / "scripts" / "bj145_fast_alloc.cpp"
EXPECTED_ALLOCATOR_SHA256 = (
    "5f8f5d75dd15758e62dd2a05f7b674cb12824b38ccba35cfee772e8904a8bd93"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C = load_module("bj193_core", ROOT / "scripts" / "bj193_gate_b_core.py")
V2 = load_module("bj193_chain_v2", ROOT / "scripts" / "bj193_chain_gate_b_v2.py")
R167 = load_module(
    "bj167_exact", ROOT / "scripts" / "settle_bj167_strategy_atlas_gate_b_exact.py"
)
S167 = load_module(
    "bj167_science", ROOT / "scripts" / "settle_bj167_scientific_stability_exact.py"
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_stage(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    while True:
        stage = target.with_name(f"{target.name}.stage-{uuid.uuid4().hex}")
        try:
            stage.mkdir()
            return stage
        except FileExistsError:
            continue


def atomic_publish(stage: Path, target: Path) -> None:
    if target.exists():
        raise RuntimeError(f"refusing to replace immutable target: {target}")
    os.replace(stage, target)


def verify_package(package: Path, manifest_sha256: str) -> dict[str, str]:
    manifest = package / "SHA256SUMS.json"
    if sha(manifest) != manifest_sha256:
        raise RuntimeError(f"manifest identity drift: {package}")
    payload = json.loads(manifest.read_text())
    for name, digest in payload.items():
        if sha(package / name) != digest:
            raise RuntimeError(f"payload identity drift: {package.name}/{name}")
    return payload


def verify_gate_a() -> dict[str, str]:
    payload = verify_package(GATE_A, EXPECTED_GATE_A_MANIFEST)
    if sha(GATE_A / "CONTENT_IDENTITY.json") != EXPECTED_GATE_A_CONTENT:
        raise RuntimeError("#193 Gate-A content identity drift")
    card = json.loads((GATE_A / "gate_a_card.json").read_text())
    if card["denominator"]["expanded_action_count"] != 483_501:
        raise RuntimeError("#193 frozen action denominator drift")
    if card["denominator"]["canonical_issue_count"] != CANONICAL_ISSUE_COUNT:
        raise RuntimeError("#193 canonical issue denominator drift")
    v2 = verify_package(GATE_A_V2, EXPECTED_GATE_A_V2_MANIFEST)
    if sha(GATE_A_V2 / "CONTENT_IDENTITY.json") != EXPECTED_GATE_A_V2_CONTENT:
        raise RuntimeError("#193 Gate-A v2 content identity drift")
    if sha(GATE_A_V2 / "PORTABLE_SHA256SUMS.json") != EXPECTED_GATE_A_V2_PORTABLE:
        raise RuntimeError("#193 Gate-A v2 portable identity drift")
    v2_card = json.loads((GATE_A_V2 / "gate_a_card.json").read_text())
    counts = v2_card["denominator"]
    expected = {
        "stage1_action_count": 2_469,
        "stage2_action_count": 2_425,
        "stage3_seed_agnostic_action_count": 963,
    }
    for field, value in expected.items():
        if int(counts[field]) != value:
            raise RuntimeError(f"#193 Gate-A v2 denominator drift: {field}")
    return {**payload, **{f"v2::{name}": digest for name, digest in v2.items()}}


def read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(path: Path, fields: Sequence[str], rows: Iterable[dict]) -> None:
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as binary:
        with __import__("io").TextIOWrapper(binary, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def science_cells() -> list[tuple[str, str, str, str, str]]:
    cells = S167.science_cells()
    if len(cells) != SCIENCE_CELLS:
        raise RuntimeError("#167 science-cell layout drift")
    return cells


def load_feature_rows() -> list[dict[str, str]]:
    rows = read_csv(GATE_A / "issue_regime_features.csv.gz")
    if len(rows) != CANONICAL_ISSUE_COUNT:
        raise RuntimeError("#193 issue feature count drift")
    if len({row["issue"] for row in rows}) != len(rows):
        raise RuntimeError("#193 canonical issue identity is not unique")
    return rows


def atlas_canonical_status(
    census: list[dict[str, str]],
    instance_status: dict[tuple[int, str], str],
    selector_idx: dict[str, int],
) -> dict[tuple[int, str], str]:
    """Fail closed after merging split OOS issue instances to canonical issue."""
    grouped: dict[tuple[int, str], list[str]] = defaultdict(list)
    selected: dict[tuple[int, str], int] = defaultdict(int)
    for row in census:
        si = selector_idx[row["selector_id"]]
        issue = row["issue"]
        key = (si, issue)
        selected[key] += int(row["selected_identity_count"])
        grouped[key].append(instance_status[(si, row["issue_instance"])])
    output: dict[tuple[int, str], str] = {}
    for key, statuses in grouped.items():
        if selected[key] == 0:
            output[key] = "NO_BET"
        elif "UNAVAILABLE_CANONICAL_OUTCOME" in statuses:
            output[key] = "UNAVAILABLE"
        else:
            output[key] = "ACTIVE"
    return output


def build_atlas_full_screen(
    features: list[dict[str, str]],
) -> tuple[
    list[dict[str, str]],
    dict[str, int],
    dict[str, list[dict]],
    dict[tuple[int, str], str],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Load exact supports and create all-492 selector-matched FULL controls."""
    R167.verify_ga()
    outcomes = R167.load_outcomes()
    selectors, selector_idx, *_ = R167.load_surface()
    supports, _by_instance, _order, _identity_count = R167.build_supports(
        outcomes, selector_idx
    )
    census = read_csv(R167.GA / "selector_census.csv")
    instance_status, _selected = R167.build_policy_status(census, supports, selector_idx)
    canonical_status = atlas_canonical_status(census, instance_status, selector_idx)
    issues = [row["issue"] for row in features]
    issue_idx = {issue: i for i, issue in enumerate(issues)}
    shape = (len(selectors), len(issues))
    net = np.zeros(shape, dtype=np.float64)
    stake = np.zeros(shape, dtype=np.float64)
    gross = np.zeros(shape, dtype=np.float64)
    tax = np.zeros(shape, dtype=np.float64)
    by_canonical: dict[str, list[dict]] = defaultdict(list)
    for support in supports.values():
        issue = support["issue_instance"].split("@", 1)[0]
        by_canonical[issue].append(support)
        if issue not in issue_idx or not support["available"]:
            continue
        ii = issue_idx[issue]
        for si in support["selectors"]:
            if canonical_status.get((si, issue)) != "ACTIVE":
                continue
            payout = float(support["payout"])
            stake[si, ii] += 4374.0
            gross[si, ii] += payout
            tax[si, ii] += payout * 0.20 if payout >= 10_000.0 else 0.0
            net[si, ii] += payout - 4374.0
    if len(selectors) != ATLAS_SELECTOR_COUNT or len(supports) != 36_830:
        raise RuntimeError("#167 source denominator drift")
    return (
        selectors,
        selector_idx,
        by_canonical,
        canonical_status,
        net,
        stake,
        gross,
        tax,
    )


def fold_issue_indices(
    features: list[dict[str, str]], test_year: int, outer: bool
) -> list[int]:
    cutoff = test_year if outer else test_year - 1
    return [
        i for i, row in enumerate(features)
        if int(row["year"]) < cutoff
    ]


def frozen_selector_union(
    features: list[dict[str, str]],
    selectors: list[dict[str, str]],
    full_net: np.ndarray,
    full_stake: np.ndarray,
) -> tuple[list[int], list[dict[str, object]]]:
    selector_ids = [row["selector_id"] for row in selectors]
    union: set[int] = set()
    rows: list[dict[str, object]] = []
    for test_year in range(2021, 2026):
        for phase, outer in (("INNER_TRAIN", False), ("OUTER_TRAIN", True)):
            issues = fold_issue_indices(features, test_year, outer)
            chosen = C.selector_rank(
                full_net, full_stake, selector_ids, issues, keep=16
            )
            union.update(chosen)
            for rank, si in enumerate(chosen, 1):
                st = full_stake[si, issues]
                rows.append(
                    {
                        "outer_fold": f"TEST_{test_year}",
                        "screen_phase": phase,
                        "selector_rank": rank,
                        "selector_index": si,
                        "selector_factor_id": selector_ids[si],
                        "active_issue_count": int(np.count_nonzero(st > 0.0)),
                        "stake_yuan": f"{float(st.sum()):.6f}",
                        "pre_tax_roi": (
                            f"{float(full_net[si, issues].sum() / st.sum()):.12f}"
                            if st.sum() else ""
                        ),
                    }
                )
    return sorted(union), rows


def compile_replay(stage: Path) -> tuple[ctypes.CDLL, Path]:
    if sha(FROZEN_ALLOCATOR) != EXPECTED_ALLOCATOR_SHA256:
        raise RuntimeError("frozen #145 allocator identity drift")
    target = stage / "bj193_exact_replay.so"
    command = [
        "g++", "-std=c++17", "-O3", "-fopenmp", "-fPIC", "-shared",
        str(REPLAY_CPP), "-o", str(target),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    library = ctypes.CDLL(str(target))
    pd = ctypes.POINTER(ctypes.c_double)
    pi = ctypes.POINTER(ctypes.c_int)
    pb = ctypes.POINTER(ctypes.c_ubyte)
    library.bj167_scientific_set_buffers.argtypes = (
        [pd] * 6 + [pb, pi] + [pd] * 7 + [pd] * 3 + [pi] * 2
        + [pd] * 4 + [pd] * 2 + [pi] + [pd] * 2 + [ctypes.c_int] * 3
    )
    library.bj193_set_seed_fold_buffers.argtypes = [
        pd, pd, ctypes.c_int, ctypes.c_int
    ]
    library.bj193_set_action_issue_buffers.argtypes = [pd] * 6
    library.bj193_begin_issue.argtypes = [ctypes.c_int] * 3
    library.bj193_end_issue.argtypes = []
    library.bj193_process_source.argtypes = [
        pd, ctypes.c_int, ctypes.c_char_p, ctypes.c_double,
        pi, ctypes.c_int, ctypes.c_int,
    ]
    library.bj167_scientific_add_structural.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_double,
    ]
    return library, target


def np_ptr(values: np.ndarray, kind=ctypes.c_double):
    return values.ctypes.data_as(ctypes.POINTER(kind))


def replay_atlas_selected(
    stage: Path,
    features: list[dict[str, str]],
    selectors: list[dict[str, str]],
    selector_union: list[int],
    by_canonical: dict[str, list[dict]],
    canonical_status: dict[tuple[int, str], str],
) -> dict[str, object]:
    """One exact native replay for the frozen union of retained selectors."""
    library, binary = compile_replay(stage)
    cells = science_cells()
    nselector = len(selector_union)
    nissue = len(features)
    total = nselector * len(cells)
    local_by_global = {global_i: local for local, global_i in enumerate(selector_union)}
    years = sorted({row["year"] for row in features})
    folds = sorted({row["outer_fold"] for row in features})
    year_idx = {value: i for i, value in enumerate(years)}
    fold_idx = {value: i for i, value in enumerate(folds)}

    arrays_dir = stage / "atlas167_arrays"
    arrays_dir.mkdir()
    issue_arrays: dict[str, np.memmap] = {}
    for name in ("net", "stake", "gross", "tax", "hit", "tax_line_hit"):
        issue_arrays[name] = np.lib.format.open_memmap(
            arrays_dir / f"{name}.npy", mode="w+", dtype="float64",
            shape=(total, nissue)
        )
    seed_shape = (nselector, 6, 2, 20, 100, len(folds))
    seed_net = np.lib.format.open_memmap(
        arrays_dir / "seed_fold_net.npy", mode="w+", dtype="float64",
        shape=seed_shape
    )
    seed_stake = np.lib.format.open_memmap(
        arrays_dir / "seed_fold_stake.npy", mode="w+", dtype="float64",
        shape=seed_shape
    )
    seed_net[:] = 0.0
    seed_stake[:] = 0.0

    zeros = lambda: np.zeros(total, dtype=np.float64)
    temporary = [zeros() for _ in range(6)]
    totals = [zeros() for _ in range(7)]
    mark = np.zeros(total, dtype=np.uint8)
    touched = np.zeros(total, dtype=np.int32)
    cumulative, peak, drawdown = zeros(), zeros(), zeros()
    miss = np.zeros(total, dtype=np.int32)
    longest = np.zeros(total, dtype=np.int32)
    year_net = np.zeros((total, len(years)), dtype=np.float64)
    year_stake = np.zeros_like(year_net)
    fold_net = np.zeros((total, len(folds)), dtype=np.float64)
    fold_stake = np.zeros_like(fold_net)
    largest = np.full(total, -math.inf, dtype=np.float64)
    largest_stake = zeros()
    largest_issue = np.full(total, -1, dtype=np.int32)
    full_issue_net = np.zeros((nselector, nissue), dtype=np.float64)
    full_issue_stake = np.zeros_like(full_issue_net)
    library.bj167_scientific_set_buffers(
        *(np_ptr(value) for value in temporary),
        np_ptr(mark, ctypes.c_ubyte), np_ptr(touched, ctypes.c_int),
        *(np_ptr(value) for value in totals),
        np_ptr(cumulative), np_ptr(peak), np_ptr(drawdown),
        np_ptr(miss, ctypes.c_int), np_ptr(longest, ctypes.c_int),
        np_ptr(year_net), np_ptr(year_stake),
        np_ptr(fold_net), np_ptr(fold_stake),
        np_ptr(largest), np_ptr(largest_stake),
        np_ptr(largest_issue, ctypes.c_int),
        np_ptr(full_issue_net), np_ptr(full_issue_stake),
        len(years), len(folds), nissue,
    )
    library.bj193_set_seed_fold_buffers(
        np_ptr(seed_net), np_ptr(seed_stake), nselector, len(folds)
    )
    library.bj193_set_action_issue_buffers(
        *(np_ptr(issue_arrays[name]) for name in (
            "net", "stake", "gross", "tax", "hit", "tax_line_hit"
        ))
    )

    for ii, feature in enumerate(features):
        issue = feature["issue"]
        library.bj193_begin_issue(
            ii, year_idx[feature["year"]], fold_idx[feature["outer_fold"]]
        )
        for support in by_canonical.get(issue, []):
            eligible = [
                local_by_global[si] for si in support["selectors"]
                if si in local_by_global
                and canonical_status.get((si, issue)) == "ACTIVE"
            ]
            if not eligible:
                continue
            occurrence = np.asarray(sorted(eligible), dtype=np.int32)
            signature = "|".join(support["mids"]).encode()
            for source_index, source in enumerate(R167.SOURCES):
                role = np.asarray(
                    [
                        value
                        for role_row in support["roles"]
                        for value in role_row["source"][source]
                    ],
                    dtype=np.float64,
                )
                library.bj193_process_source(
                    np_ptr(role), support["truth"], signature,
                    support["payout"], np_ptr(occurrence, ctypes.c_int),
                    len(occurrence), source_index,
                )
            p_leg, p_code, q_leg, q_code = R167.derive_delete(support["roles"])
            for local in occurrence:
                library.bj167_scientific_add_structural(
                    int(local), support["truth"], p_leg, p_code, q_leg, q_code,
                    support["payout"],
                )
        library.bj193_end_issue()
        if (ii + 1) % 10 == 0:
            print(f"#193 exact #167 replay {ii + 1}/{nissue}", flush=True)

    for value in issue_arrays.values():
        value.flush()
    seed_net.flush()
    seed_stake.flush()
    # The structural FULL cell must equal the independently assembled screen.
    for local in range(nselector):
        full = local * SCIENCE_CELLS + 960
        if not np.array_equal(issue_arrays["net"][full], full_issue_net[local]):
            raise RuntimeError("#167 replay FULL net control mismatch")
        if not np.array_equal(issue_arrays["stake"][full], full_issue_stake[local]):
            raise RuntimeError("#167 replay FULL stake control mismatch")
    # Pooled stochastic money must equal the exact sum of its 100 nuisance
    # replicates in each frozen OOS fold.
    for local in range(nselector):
        for source in range(6):
            for mechanism, offset in ((0, 0), (1, 20)):
                for mi in range(20):
                    at = local * SCIENCE_CELLS + source * 160 + offset + mi
                    for fi, fold in enumerate(folds):
                        take = np.array([
                            row["outer_fold"] == fold for row in features
                        ])
                        for field, seed_values in (
                            ("net", seed_net), ("stake", seed_stake)
                        ):
                            pooled = float(issue_arrays[field][at, take].sum())
                            by_seed = float(
                                seed_values[local, source, mechanism, mi, :, fi].sum()
                            )
                            if abs(pooled - by_seed) > 1e-8:
                                raise RuntimeError(
                                    f"seed pooling drift {local}/{source}/{mechanism}/"
                                    f"{mi}/{fold}/{field}: {pooled} != {by_seed}"
                                )
    return {
        "compiled_binary_sha256": sha(binary),
        "selector_union_count": nselector,
        "science_cell_count": len(cells),
        "action_issue_row_count": total * nissue,
        "seed_fold_value_count": int(np.prod(seed_shape)),
        "years": years,
        "folds": folds,
        "array_specs": {
            name: {
                "path": f"atlas167_arrays/{name}.npy",
                "shape": list(value.shape),
                "dtype": "float64",
            }
            for name, value in issue_arrays.items()
        } | {
            "seed_fold_net": {
                "path": "atlas167_arrays/seed_fold_net.npy",
                "shape": list(seed_shape), "dtype": "float64"
            },
            "seed_fold_stake": {
                "path": "atlas167_arrays/seed_fold_stake.npy",
                "shape": list(seed_shape), "dtype": "float64"
            },
        },
    }


def source_binding_rows() -> dict[str, dict[str, str]]:
    rows = read_csv(GATE_A / "source_binding.csv")
    return {row["package"]: row for row in rows}


def verify_gate_b_sources() -> dict[str, dict[str, str]]:
    bindings = source_binding_rows()
    required = (
        "bj167_gate_a_strategy_atlas_v3r1",
        "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
        "bj170_gate_a_preoutcome_v2",
        "bj170_gate_b_selector_allocator_stack_v1",
        "bj190_gate_a_preoutcome_v3r1",
        "bj190_gate_b_sparse_divergence_v1",
        "bj176_issue_equity_risk_v1",
    )
    output = {}
    for name in required:
        row = bindings[name]
        package = ROOT / "results" / name
        verify_package(package, row["manifest_sha256"])
        if sha(package / "CONTENT_IDENTITY.json") != row["content_identity_sha256"]:
            raise RuntimeError(f"source content identity drift: {name}")
        output[name] = {
            "manifest_sha256": row["manifest_sha256"],
            "content_identity_sha256": row["content_identity_sha256"],
        }
    # #167's canonical outcome ledger is transitive but is reopened by the
    # exact replay; bind it explicitly rather than relying on prose lineage.
    outcome = R167.OUTCOME_DIR
    verify_package(outcome, R167.EXPECTED_OUTCOME_MANIFEST)
    output[outcome.name] = {
        "manifest_sha256": R167.EXPECTED_OUTCOME_MANIFEST,
        "content_identity_sha256": (
            sha(outcome / "CONTENT_IDENTITY.json")
            if (outcome / "CONTENT_IDENTITY.json").exists()
            else ""
        ),
    }
    return output


def execution_snapshot() -> dict[str, str]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    return {
        "git_head": head,
        "runner_path": str(Path(__file__).relative_to(ROOT)),
        "runner_sha256": sha(Path(__file__)),
        "core_path": "scripts/bj193_gate_b_core.py",
        "core_sha256": sha(ROOT / "scripts" / "bj193_gate_b_core.py"),
        "native_wrapper_path": str(REPLAY_CPP.relative_to(ROOT)),
        "native_wrapper_sha256": sha(REPLAY_CPP),
        "frozen_allocator_path": str(FROZEN_ALLOCATOR.relative_to(ROOT)),
        "frozen_allocator_sha256": sha(FROZEN_ALLOCATOR),
    }


def package_manifest(stage: Path, contract: str, identity: dict) -> dict[str, str]:
    identity = {"contract": contract, **identity}
    (stage / "CONTENT_IDENTITY.json").write_text(
        json.dumps(identity, sort_keys=True, indent=2) + "\n"
    )
    payload = {}
    for path in sorted(stage.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            payload[str(path.relative_to(stage))] = sha(path)
    (stage / "SHA256SUMS.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n"
    )
    return payload


def build_replay_checkpoint(target: Path) -> None:
    verify_gate_a()
    source_bindings = verify_gate_b_sources()
    start = execution_snapshot()
    features = load_feature_rows()
    (
        selectors,
        _selector_idx,
        by_canonical,
        canonical_status,
        full_net,
        full_stake,
        full_gross,
        full_tax,
    ) = build_atlas_full_screen(features)
    selector_union, screen_rows = frozen_selector_union(
        features, selectors, full_net, full_stake
    )
    if not selector_union:
        raise RuntimeError("frozen selector union is empty")
    stage = unique_stage(target)
    try:
        issue_fields = [
            "issue_index", "issue", "year", "outer_fold", "issue_instance",
            "feature_cutoff_ts",
        ]
        issue_rows = [
            {
                "issue_index": i,
                **{field: row[field] for field in issue_fields[1:]},
            }
            for i, row in enumerate(features)
        ]
        write_csv(stage / "canonical_issue_order.csv", issue_fields, issue_rows)
        write_csv(
            stage / "selected_selector_union.csv",
            [
                "local_selector_index", "global_selector_index",
                "selector_factor_id", "family",
            ],
            [
                {
                    "local_selector_index": local,
                    "global_selector_index": global_i,
                    "selector_factor_id": selectors[global_i]["selector_id"],
                    "family": selectors[global_i]["family"],
                }
                for local, global_i in enumerate(selector_union)
            ],
        )
        write_csv(
            stage / "selector_screen_by_fold.csv",
            list(screen_rows[0]),
            screen_rows,
        )
        cells = science_cells()
        write_csv(
            stage / "atlas167_science_cells.csv",
            ["science_cell", "weight_source", "mechanism", "cap", "M", "seed_scope"],
            [
                {
                    "science_cell": index,
                    "weight_source": cell[0], "mechanism": cell[1],
                    "cap": cell[2], "M": cell[3], "seed_scope": cell[4],
                }
                for index, cell in enumerate(cells)
            ],
        )
        # Persist independently assembled FULL controls for all 492 selectors;
        # these are the complete frozen screen, not a selected-union shortcut.
        controls = stage / "atlas167_full_controls"
        controls.mkdir()
        for name, values in (
            ("net", full_net), ("stake", full_stake),
            ("gross", full_gross), ("tax", full_tax),
        ):
            np.save(controls / f"{name}.npy", values, allow_pickle=False)
        status_codes = {"NO_BET": 0, "ACTIVE": 1, "UNAVAILABLE": 2}
        selected_status = np.asarray(
            [
                [
                    status_codes[
                        canonical_status.get((global_i, feature["issue"]), "NO_BET")
                    ]
                    for feature in features
                ]
                for global_i in selector_union
            ],
            dtype=np.uint8,
        )
        np.save(
            controls / "selected_selector_status.npy",
            selected_status,
            allow_pickle=False,
        )
        replay_meta = replay_atlas_selected(
            stage, features, selectors, selector_union, by_canonical,
            canonical_status,
        )
        # The compiled object is evidence-addressed in replay_meta but is not a
        # portable scientific payload.
        (stage / "bj193_exact_replay.so").unlink()
        end = execution_snapshot()
        if start != end:
            raise RuntimeError("#193 replay executable identity changed in flight")
        metadata = {
            "contract": CHECKPOINT_CONTRACT,
            "gate_a": {
                "manifest_sha256": EXPECTED_GATE_A_MANIFEST,
                "content_identity_sha256": EXPECTED_GATE_A_CONTENT,
            },
            "source_bindings": source_bindings,
            "execution_start": start,
            "execution_end": end,
            "canonical_issue_count": len(features),
            "atlas_selector_count": len(selectors),
            "selector_union_count": len(selector_union),
            "selector_screen_count": len(screen_rows),
            "science_cells_per_selector": len(cells),
            "seed_semantics": (
                "100 exact frozen seeds are nuisance replicates; pooled money "
                "is divided by 100 before action economics"
            ),
            "replay": replay_meta,
        }
        (stage / "checkpoint_metadata.json").write_text(
            json.dumps(metadata, sort_keys=True, indent=2) + "\n"
        )
        payload = package_manifest(
            stage,
            CHECKPOINT_CONTRACT,
            {
                "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
                "canonical_issue_count": len(features),
                "atlas_selector_count": len(selectors),
                "selector_union_count": len(selector_union),
                "science_cells_per_selector": len(cells),
                "action_issue_row_count": replay_meta["action_issue_row_count"],
            },
        )
        metadata["payload_count"] = len(payload)
        atomic_publish(stage, target)
        print(
            json.dumps(
                {
                    "checkpoint": str(target),
                    "manifest_sha256": sha(target / "SHA256SUMS.json"),
                    "selector_union_count": len(selector_union),
                    "action_issue_row_count": replay_meta["action_issue_row_count"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
    except Exception:
        print(f"FAILED_STAGE={stage}", flush=True)
        raise


def preflight() -> None:
    manifests = verify_gate_a()
    store = V2.build_stage1_store()
    print(
        json.dumps(
            {
                "mode": "THREE_STAGE_V2_PREFLIGHT_NO_STAGE2_OR_STAGE3_REPLAY",
                "gate_a_v1_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
                "gate_a_v2_manifest_sha256": EXPECTED_GATE_A_V2_MANIFEST,
                "verified_payload_count": len(manifests),
                "canonical_issue_count": len(store.issues),
                "stage1_action_count": len(store.action_rows),
                "stage1_action_issue_count": int(store.status.size),
                "stage1_active_action_issue_count": int(
                    np.count_nonzero(store.status == V2.STATUS_ACTIVE)
                ),
                "stage1_unavailable_action_issue_count": int(
                    np.count_nonzero(store.status == V2.STATUS_UNAVAILABLE)
                ),
                "stage1_static_full_settlement_sha256": V2.stage1_store_identity(store),
                "next_boundary": "IMPLEMENT_HONEST_STAGE1_PATH_BEFORE_STAGE2_REPLAY",
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--replay-checkpoint", action="store_true")
    modes.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        preflight()
    elif args.replay_checkpoint:
        raise RuntimeError(
            "superseded flattened replay disabled; v2 chained checkpoint is not complete"
        )
    else:
        raise RuntimeError("finalizer implementation not yet available")


if __name__ == "__main__":
    main()
