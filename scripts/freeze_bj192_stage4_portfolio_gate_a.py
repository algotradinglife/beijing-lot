#!/usr/bin/env python3
"""Create #192's outcome-unexposed Stage-4 capital-portfolio Gate-A freeze.

The runner reads only hash-bound, outcome-unexposed lineage inputs: #170/#137
calendar and trace evidence, #145/#148/#151/#159/#167A allocation lineage, and
#193A pre-event regime features.  Accepted settled packages are bound by hash
only and are deliberately never parsed: Stage 4 cannot choose a sleeve from
historical returns.
"""

from __future__ import annotations

import argparse
import array
import ctypes
import csv
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence


CONTRACT = "BJ-HIST-N7-STRATEGY-ENSEMBLE-001"
VERSION = "bj192-gate-a-v8r1r1"
OUTCOME_BOUNDARY = (
    "Gate A is outcome-unexposed: no score, result, final/winning SP, payout, "
    "tax realization, ROI, net, gross, or settlement payload is read."
)
INITIAL_BANKROLL_YUAN = 100_000
TICKET_STAKE_YUAN = 2
POSITION_FRACTIONS = tuple(range(5, 101, 5))
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 192001
TARGET_EX_ANTE_VOLATILITY = 0.05
FROZEN_ALLOCATOR_SHA256 = (
    "5f8f5d75dd15758e62dd2a05f7b674cb12824b38ccba35cfee772e8904a8bd93"
)
FUNDING_MODES = (
    "NATIVE_REQUEST_CONTROL",
    "SCALED_NATIVE_REQUEST",
    "FIXED_100K_NOTIONAL",
    "COMPOUNDING_BANKROLL",
)

# A seed is local to one sleeve.  The bundle fixes the exact cross-sleeve
# pairing, so both identities are mandatory in every dynamic Gate-B table.
PATH_IDENTITY = (
    "portfolio_id",
    "mode",
    "position_fraction",
    "weight_method",
    "normalization_method",
    "deployment_replicate_bundle_id",
)
PORTFOLIO_LEVEL_TABLES = (
    "issue_ledger", "sleeve_funding_ledger", "capital_summary", "weight_history",
    "dependence", "dependence_panel", "intrinsic_native_dependence",
    "realized_funded_flow_dependence", "risk_decomposition", "stage_attribution",
    "portfolio_k_saturation", "holding_metrics", "rolling_window_metrics",
    "bootstrap_stability", "baseline_lift", "challenger_case",
    "all_pairs_risk_return_surface", "higher_order_pareto_frontier",
    "terminal_decision",
)


def repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
SOURCE_170 = ROOT / "results" / "bj170_gate_a_preoutcome_v2"
SOURCE_137 = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
SOURCE_176 = ROOT / "results" / "bj176_issue_equity_risk_v1"
SOURCE_190 = ROOT / "results" / "bj190_gate_b_sparse_divergence_v1"
SOURCE_193A = ROOT / "results" / "bj193_gate_a_preoutcome_v1"
SOURCE_193 = ROOT / "results" / "bj193_gate_b_regime_meta_policy_v2"
SOURCE_145 = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
SOURCE_148 = ROOT / "results" / "bj148_gate_a_preoutcome_v1"
SOURCE_151 = ROOT / "results" / "bj151_gate_a_preoutcome_v1"
SOURCE_159 = ROOT / "results" / "bj159_gate_a_preoutcome_v2r1"
SOURCE_167A = ROOT / "results" / "bj167_gate_a_strategy_atlas_v3r1"
SOURCE_167B = (
    ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1"
)
SOURCE_170B = ROOT / "results" / "bj170_gate_b_selector_allocator_stack_v1"
DEFAULT_OUTPUT = ROOT / "results" / "bj192_gate_a_preoutcome_v8r1r1"
SETTLED_IDENTITY_ONLY_PACKAGES = {
    "bj176_issue_equity_risk_v1",
    "bj190_gate_b_sparse_divergence_v1",
    "bj193_gate_b_regime_meta_policy_v2",
    "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
    "bj170_gate_b_selector_allocator_stack_v1",
}

EXPECTED_SOURCES = {
    "bj170_gate_a_preoutcome_v2": {
        "path": SOURCE_170,
        "manifest": "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87",
        "content": "adc4d0f96628c784149da998a20e8830cde26db4001fe457eaf9ca4b7bb74223",
        "role": "accepted outcome-unexposed sleeve identity, ticket and support freeze",
    },
    "bj137_gate_a_preoutcome_v2": {
        "path": SOURCE_137,
        "manifest": "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df",
        "content": "36d6afcc33a5b5ceb3e4a990bfe6ec05503be115270c3489f4973dc3a59dd236",
        "role": "accepted outcome-unexposed chronological issue census",
    },
    "bj176_issue_equity_risk_v1": {
        "path": SOURCE_176,
        "manifest": "39316952296c2349f5da2f963d43c0baf0d812fba4eea967536a8b80bd57d5ee",
        "content": "94188354baf01c68cb0ec0791248d3f8f03e31d4a7011db7b6b68e9797720f5c",
        "role": "accepted terminal three-sleeve settlement and holding-risk convention bridge; hash-only during Gate A",
    },
    "bj190_gate_b_sparse_divergence_v1": {
        "path": SOURCE_190,
        "manifest": "5685f25d9ce70a66b38b283f668d258d97dfe2e356c5bd45d9666400c6ab4554",
        "content": "5112dc652277a234fcb36687d59e2bd96bf8daeaaa1c9ddd06481923de909ce6",
        "role": "terminal eligibility decision only; excluded from sleeve catalog; hash-only during Gate A",
    },
    "bj193_gate_a_preoutcome_v1": {
        "path": SOURCE_193A,
        "manifest": "408e8aa69cf2d336f8b3b65b1c94b30a3456864af01517a78fc27b3f2bab0c45",
        "content": "9bf90d1553613cbb50770ea51deece1fb40cfb05a0ace9103ab62194faff3131",
        "role": "accepted outcome-unexposed Tier-C regime feature map and nested chronological regime-bin contract",
    },
    "bj193_gate_b_regime_meta_policy_v2": {
        "path": SOURCE_193,
        "manifest": "83b6c67fc91f59fcbf90895413c570225bbc34b18bf8d1d1c0f89634e9fce4d5",
        "content": "0c3a68e75dba540127ec5304e5b28aea73bc9dc191573682de9029efffc30e40",
        "role": "terminal interface/accounting lessons only; FULL_DYNAMIC_CHAIN excluded; hash-only during Gate A",
    },
    "bj145_gate_a_preoutcome_v8": {
        "path": SOURCE_145,
        "manifest": "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c",
        "content": "074c9b06c024a1db80b5b53cfc99a1bc164001b205fcd94a0c159daf445dab7f",
        "role": "accepted allocation mechanism/M/seed evidence; composable only with a complete selector trace",
    },
    "bj148_gate_a_preoutcome_v1": {
        "path": SOURCE_148,
        "manifest": "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6",
        "content": "dfd3ac234f95f28185a09a6bb2f69c3ff66ddb696ce1fe45a6a1215d932dcd0a",
        "role": "accepted dense-M support/seed evidence; no stable sweet spot, descriptive frontier only",
    },
    "bj151_gate_a_preoutcome_v1": {
        "path": SOURCE_151,
        "manifest": "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6",
        "content": "ac36bc2422d1afd22c3bb4bd680568401cbaec30e0d2006d13afcdfa141b89a5",
        "role": "accepted fixed-candidate reproduction identity/M/seed evidence; descriptive only",
    },
    "bj159_gate_a_preoutcome_v2r1": {
        "path": SOURCE_159,
        "manifest": "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325",
        "content": "4ec52432ec6c1779bab33b0c4bdc4e381b0ae7434228637c509970291ed7361e",
        "role": "accepted complete selected WOR N2–N10 chain identity/M/seed evidence",
    },
    "bj167_gate_a_strategy_atlas_v3r1": {
        "path": SOURCE_167A,
        "manifest": "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724",
        "content": "0806185a7a68b99fd2a6a465308d11e2886995f992bfa722adb287a4e6a4d147",
        "role": "accepted complete selector×allocation atlas identity/M/seed/support evidence",
    },
    "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1": {
        "path": SOURCE_167B,
        "manifest": "b3fa02f5cc2722932ff55fffb0bd9672508f6e78104cfb2458ad81c826f3b313",
        "content": "bfe29083b74d5d212555c261e888d6f5d4d5fd163b56e1876944d1f5d04aa5c7",
        "role": "accepted terminal atlas baseline ladder/evidence; hash-only during Gate A",
    },
    "bj170_gate_b_selector_allocator_stack_v1": {
        "path": SOURCE_170B,
        "manifest": "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512",
        "content": "75325aa0f60e277ad3fbf9d90116450833106bc3863b412ea3efcad9948a47b2",
        "role": "accepted exact three-way matched baseline bridge; hash-only during Gate A",
    },
}

SLEEVES = (
    (
        "BEST_FULL_FULL",
        "BEST_FULL",
        "FULL_ENUMERATED",
        "primary fixed upstream FULL control",
    ),
    (
        "MODEL_SOURCE_MODEL_CAP1_M512",
        "MODEL_SOURCE",
        "MODEL_CAP1_M512",
        "primary fixed upstream model sleeve",
    ),
    (
        "Q_SOURCE_Q_TOP_MASS_M192",
        "Q_SOURCE",
        "Q_TOP_MASS_M192",
        "primary fixed upstream Q sleeve",
    ),
)

# These are complete pre-outcome Stage-1→3 pipelines rather than a reopening
# of the #167 outcome surface.  The family-level M paths stay unresolved until
# Gate B's frozen strictly-prior selector runs; each row binds the exact source
# identities, role vectors, sampler and seed aggregation needed to construct
# the ticket multiset on that path.
EXPANDED_FAMILY_SPECS = (
    {
        "candidate_id": "BJ148_NOGATE_WR_DENSE_M",
        "source_package": "bj148_gate_a_preoutcome_v1",
        "identity_file": "common_support_identities.csv.gz",
        "role_file": "common_support_role_vectors.csv.gz",
        "plan_file": "sampling_plan.csv",
        "source_selector": "NO_GATE/RANK32_COMPLETE_ISSUE",
        "mechanism": "WR_DUPLICATE_STAKE",
        "weight_source": "Q_WEIGHT",
        "seed_aggregation": "ARITHMETIC_MEAN_OF_133001_133002_133003",
        "m_grid_file": "dense_m_grid.csv",
        "fixed_m_comparator": "16",
        "ticket_prefix_rule": "stable_uniform(bj137,WR,seed,exact identity signature,draw_index); draw positions 1..M are immutable ¥2 tax lots",
        "frontier_role": "COMPLETE_EXECUTABLE_DENSE_M_FAMILY",
    },
    {
        "candidate_id": "BJ148_NOGATE_WOR_DENSE_M",
        "source_package": "bj148_gate_a_preoutcome_v1",
        "identity_file": "common_support_identities.csv.gz",
        "role_file": "common_support_role_vectors.csv.gz",
        "plan_file": "sampling_plan.csv",
        "source_selector": "NO_GATE/RANK32_COMPLETE_ISSUE",
        "mechanism": "WOR_DISTINCT",
        "weight_source": "Q_WEIGHT",
        "seed_aggregation": "ARITHMETIC_MEAN_OF_133001_133002_133003",
        "m_grid_file": "dense_m_grid.csv",
        "fixed_m_comparator": "16",
        "ticket_prefix_rule": "exponential-key WOR rank under frozen bj137 stable_uniform; ranks 1..M are immutable ¥2 tax lots",
        "frontier_role": "COMPLETE_EXECUTABLE_DENSE_M_FAMILY",
    },
    {
        "candidate_id": "BJ151_NOGATE_K4_WR_DENSE_M",
        "source_package": "bj151_gate_a_preoutcome_v1",
        "identity_file": "candidate_identities.csv.gz",
        "role_file": "candidate_role_vectors.csv.gz",
        "plan_file": "sampling_plan.csv",
        "source_selector": "NO_GATE/K4_COMPLETE_ISSUE",
        "mechanism": "WR_DUPLICATE_STAKE",
        "weight_source": "Q_WEIGHT",
        "seed_aggregation": "ARITHMETIC_MEAN_OF_137001_137002_137003",
        "m_grid_file": "dense_m_grid.csv",
        "fixed_m_comparator": "16",
        "ticket_prefix_rule": "stable_uniform(bj137,WR,seed,exact identity signature,draw_index); draw positions 1..M are immutable ¥2 tax lots",
        "frontier_role": "COMPLETE_EXECUTABLE_DENSE_M_FAMILY",
    },
    {
        "candidate_id": "BJ151_NOGATE_K4_WOR_DENSE_M",
        "source_package": "bj151_gate_a_preoutcome_v1",
        "identity_file": "candidate_identities.csv.gz",
        "role_file": "candidate_role_vectors.csv.gz",
        "plan_file": "sampling_plan.csv",
        "source_selector": "NO_GATE/K4_COMPLETE_ISSUE",
        "mechanism": "WOR_DISTINCT",
        "weight_source": "Q_WEIGHT",
        "seed_aggregation": "ARITHMETIC_MEAN_OF_137001_137002_137003",
        "m_grid_file": "dense_m_grid.csv",
        "fixed_m_comparator": "16",
        "ticket_prefix_rule": "exponential-key WOR rank under frozen bj137 stable_uniform; ranks 1..M are immutable ¥2 tax lots",
        "frontier_role": "COMPLETE_EXECUTABLE_DENSE_M_FAMILY",
    },
    {
        "candidate_id": "BJ159_SELECTED_N7_WOR_M_CURVE",
        "source_package": "bj159_gate_a_preoutcome_v2r1",
        "identity_file": "identity_catalog.csv.gz[n=7]",
        "role_file": "role_vectors.csv.gz[n=7]",
        "plan_file": "sampling_plan.csv[n=7]",
        "source_selector": "ESP300_GM305_LOWP20_COMPLETE_ISSUE/N7",
        "mechanism": "WOR_DISTINCT",
        "weight_source": "Q_WEIGHT",
        "seed_aggregation": "ARITHMETIC_MEAN_OF_137001_137002_137003",
        "m_grid_file": "sampling_plan.csv nominal_M={32,64,128}",
        "fixed_m_comparator": "32",
        "ticket_prefix_rule": "exponential-key WOR rank under frozen bj137 stable_uniform; ranks 1..effective_M are immutable ¥2 tax lots",
        "frontier_role": "COMPLETE_EXECUTABLE_M_CURVE_FAMILY",
    },
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class FrozenAllocator:
    """Run the byte-frozen #145 C++ allocator without persistent build state.

    The allocation engine is authoritative for production tie cases.  The
    short-lived shared object is built under repository ``.scratch`` (never
    system ``/tmp``) and is not an input to, or retained by, the Gate-A
    package.  This lets a detached clone regenerate the MODEL all-M proof.
    """

    def __init__(self, root: Path = ROOT) -> None:
        source = root / "scripts" / "bj145_fast_alloc.cpp"
        if sha256_file(source) != FROZEN_ALLOCATOR_SHA256:
            raise RuntimeError("frozen allocator source hash drift")
        scratch = root / ".scratch"
        scratch.mkdir(exist_ok=True)
        self._build = tempfile.TemporaryDirectory(prefix="bj192-allocator-", dir=scratch)
        build = Path(self._build.name)
        library = build / "bj192_capped_prefix.so"
        wrapper = build / "bj192_capped_prefix.cpp"
        wrapper.write_text(
            "#include " + json.dumps(str(source)) + "\n"
            "extern \"C\" int bj192_capped_prefix_ranks_batch("
            "const double* weights_flat, int n_identity, int k, int maximum_m, int cap, int* ranks_flat) {\n"
            "  int failure = 0;\n"
            "  #pragma omp parallel for schedule(static)\n"
            "  for (int identity = 0; identity < n_identity; ++identity) {\n"
            "    int local_failure = 0;\n"
            "    const double* weights = weights_flat + static_cast<std::size_t>(identity) * k;\n"
            "    int* ranks = ranks_flat + static_cast<std::size_t>(identity) * k;\n"
            "    std::vector<int> prior(k, 0), counts;\n"
            "    std::fill(ranks, ranks + k, 0);\n"
            "    for (int m = 1; m <= maximum_m; ++m) {\n"
            "      capped_hamilton(weights, k, m, cap, counts);\n"
            "      int additions = 0;\n"
            "      for (int ordinal = 0; ordinal < k; ++ordinal) {\n"
            "        const int delta = counts[ordinal] - prior[ordinal];\n"
            "        if (delta < 0 || delta > 1) { local_failure = 1; continue; }\n"
            "        if (delta == 1) { ranks[ordinal] = m; ++additions; }\n"
            "      }\n"
            "      if (additions != 1) { local_failure = 2; continue; }\n"
            "      prior.swap(counts);\n"
            "    }\n"
            "    if (local_failure) {\n"
            "      #pragma omp critical\n"
            "      { if (failure < local_failure) failure = local_failure; }\n"
            "    }\n"
            "  }\n"
            "  return failure;\n"
            "}\n"
        )
        env = dict(os.environ, TMPDIR=self._build.name, TEMP=self._build.name, TMP=self._build.name)
        subprocess.run(
            ["g++", "-O3", "-std=c++17", "-fopenmp", "-shared", "-fPIC", str(wrapper), "-o", str(library)],
            check=True,
            env=env,
        )
        self.lib = ctypes.CDLL(str(library))
        self.lib.bj192_capped_prefix_ranks_batch.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int),
        ]

    @staticmethod
    def _pointer(values: array.array, c_type: object):
        return ctypes.cast(
            (c_type * len(values)).from_buffer(values), ctypes.POINTER(c_type)
        )

    def capped_prefix_ranks_batch(
        self, vectors: Sequence[Sequence[float]], maximum_m: int, cap: int
    ) -> list[list[int]]:
        if not vectors or any(len(weights) != 2187 for weights in vectors):
            raise RuntimeError("allocator weights must cover the canonical N7 space")
        weight_buffer = array.array("d", (weight for row in vectors for weight in row))
        ranks = array.array("i", [0]) * (len(vectors) * 2187)
        status = self.lib.bj192_capped_prefix_ranks_batch(
            self._pointer(weight_buffer, ctypes.c_double),
            len(vectors),
            2187,
            maximum_m,
            cap,
            self._pointer(ranks, ctypes.c_int),
        )
        if status:
            raise RuntimeError(f"native capped-prefix nesting failed: status={status}")
        return [list(ranks[offset : offset + 2187]) for offset in range(0, len(ranks), 2187)]


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        w.writeheader()
        w.writerows(rows)


def write_csv_gzip(
    path: Path, fields: list[str], rows: list[dict[str, object]]
) -> None:
    """Write a deterministic compressed CSV without creating a system temp file."""
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, newline="", encoding="utf-8") as text:
                writer = csv.DictWriter(
                    text, fieldnames=fields, lineterminator="\n", extrasaction="raise"
                )
                writer.writeheader()
                writer.writerows(rows)


def write_json_gzip(path: Path, value: object) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8") as text:
                json.dump(value, text, separators=(",", ":"), sort_keys=True)
                text.write("\n")


def canonical_scientific_sha256(path: Path) -> str:
    """Hash scientific bytes, not environment-specific gzip transport bytes."""
    digest = hashlib.sha256()
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as source:
            for block in iter(lambda: source.read(1 << 20), b""):
                digest.update(block)
    else:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1 << 20), b""):
                digest.update(block)
    return digest.hexdigest()


def verify_source(spec: dict[str, object]) -> dict[str, object]:
    path = Path(spec["path"])
    manifest_path, content_path = (
        path / "SHA256SUMS.json",
        path / "CONTENT_IDENTITY.json",
    )
    if (
        sha256_file(manifest_path) != spec["manifest"]
        or sha256_file(content_path) != spec["content"]
    ):
        raise RuntimeError(f"source hash drift: {path.name}")
    identity_only = path.name in SETTLED_IDENTITY_ONLY_PACKAGES
    if identity_only:
        # These prior accepted settlement packages are evidence bindings only.
        # Their identity/manifest documents are safe metadata; deliberately do
        # not enumerate, open, or hash a single outcome-bearing payload here.
        return {
            "package": path.name,
            "manifest_sha256": spec["manifest"],
            "content_identity_sha256": spec["content"],
            "payload_count": "NOT_READ_IDENTITY_BINDING_ONLY",
            "verification_mode": "SETTLED_IDENTITY_BINDING_ONLY",
            "role": spec["role"],
        }
    manifest = json.loads(manifest_path.read_text())
    actual = {
        p.name for p in path.iterdir() if p.is_file() and p.name != "SHA256SUMS.json"
    }
    if set(manifest) != actual:
        raise RuntimeError(f"source manifest coverage drift: {path.name}")
    for name, expected in manifest.items():
        if sha256_file(path / name) != expected:
            raise RuntimeError(f"source payload drift: {path.name}/{name}")
    return {
        "package": path.name,
        "manifest_sha256": spec["manifest"],
        "content_identity_sha256": spec["content"],
        "payload_count": len(manifest),
        "verification_mode": "PREOUTCOME_FULL_PAYLOAD_VERIFICATION",
        "role": spec["role"],
    }


def source_inputs() -> tuple[
    list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]
]:
    """Return full calendar requests, strict-common flags and chronology.

    Capital feasibility is defined on all 348 canonical issues, including each
    sleeve's frozen NO_BET rows.  The 177 issue strict-common view is carried
    as a flag for matched attribution only; it never truncates the bankroll
    path.
    """
    selectors = {
        r["selector_alias"]: r for r in read_csv(SOURCE_170 / "selector_registry.csv")
    }
    arms = {
        r["allocation_arm"]: r for r in read_csv(SOURCE_170 / "allocation_registry.csv")
    }
    wanted = {
        (alias, arm): (sleeve, rationale) for sleeve, alias, arm, rationale in SLEEVES
    }
    planned = {
        (r["issue_instance"], r["selector_alias"], r["allocation_arm"]): r
        for r in read_csv(SOURCE_170 / "planned_issue_stake.csv")
        if (r["selector_alias"], r["allocation_arm"]) in wanted
    }
    membership = {
        r["issue_instance"]
        for r in read_csv(SOURCE_170 / "support_issue_membership.csv")
        if r["support_view_id"] == "THREE_WAY_ALL"
    }
    chronology = {
        r["issue_instance"]: r for r in read_csv(SOURCE_137 / "issue_census.csv")
    }
    if len(chronology) != 348 or len(membership) != 177 or membership - set(chronology):
        raise RuntimeError("canonical calendar/three-way support mismatch")
    rows: list[dict[str, str]] = []
    for c in chronology.values():
        for (alias, arm), (sleeve, rationale) in wanted.items():
            p = planned.get((c["issue_instance"], alias, arm))
            if p is None:
                raise RuntimeError(
                    f"missing frozen planned stake: {c['issue_instance']} {alias}/{arm}"
                )
            if (p["issue_instance"], p["selector_id"]) != (
                c["issue_instance"],
                selectors[alias]["selector_id"],
            ):
                raise RuntimeError("frozen request identity mismatch")
            rows.append(
                {
                    "issue": c["issue"],
                    "year": c["year"],
                    "fold": c["fold"],
                    "issue_instance": c["issue_instance"],
                    "first_kickoff_ts": c["first_kickoff_ts"],
                    "strict_three_way_common": "1"
                    if c["issue_instance"] in membership
                    else "0",
                    "sleeve_id": sleeve,
                    "selector_alias": alias,
                    "selector_id": selectors[alias]["selector_id"],
                    "allocation_arm": arm,
                    "M": arms[arm]["M"],
                    "mechanism": arms[arm]["mechanism"],
                    "cap": arms[arm]["cap"],
                    "weight_source": arms[arm]["weight_source"],
                    "native_policy_status": p["policy_status"],
                    "settlement_availability_state": "OUTCOME_UNEXPOSED_PENDING_GATE_B",
                    "native_requested_ticket_count": p["planned_ticket_count"],
                    "native_requested_stake_yuan": p["planned_stake_yuan"],
                    "selected_identity_count": p["selected_identity_count"],
                    "rationale": rationale,
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    rows.sort(
        key=lambda r: (r["first_kickoff_ts"], r["issue_instance"], r["sleeve_id"])
    )
    for i, row in enumerate(rows):
        row["calendar_index"] = i // len(SLEEVES)
    calendar = [dict(r) for r in rows if r["sleeve_id"] == SLEEVES[0][0]]
    return rows, calendar, list(chronology.values())


def regime_binding(calendar: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Map every #192 calendar issue to #193's pre-event feature interface.

    #193 intentionally keeps the canonical-year namespace separate from #137's
    OOS namespace.  Matching is therefore the immutable (issue, year) key,
    never a permissive string rewrite.  A missing #193 feature row remains an
    explicit zero-flow regime state rather than a fabricated median feature.
    """
    features = read_csv_gzip(SOURCE_193A / "issue_regime_features.csv.gz")
    by_key = {(row["issue"], row["year"]): row for row in features}
    if len(by_key) != len(features):
        raise RuntimeError("non-unique #193 pre-event regime feature key")
    rows: list[dict[str, object]] = []
    for row in calendar:
        key = (row["issue"], row["year"])
        feature = by_key.get(key)
        if feature is None:
            rows.append(
                {
                    "calendar_index": row["calendar_index"],
                    "issue": row["issue"],
                    "year": row["year"],
                    "issue_instance": row["issue_instance"],
                    "source_issue_instance": "",
                    "regime_source_key": "MISSING_PRE_EVENT_FEATURE_VECTOR",
                    "regime_panel_id": "REGIME_FALLBACK_MISSING_FEATURE_VECTOR",
                    "feature_row_sha256": "",
                    "feature_cutoff_ts": "",
                    "regime_score": "",
                    "regime_algorithm_id": "REGIME_WF_PRE_EVENT_TERCILES_V1",
                    "regime_label": "FALLBACK_MISSING",
                    "prior_training_feature_count": 0,
                    "prior_training_feature_sha256": "",
                    "regime_bin_lower": "",
                    "regime_bin_upper": "",
                    "regime_fallback": "MISSING_PRE_EVENT_FEATURE_VECTOR",
                    "regime_status": "MISSING_PRE_EVENT_FEATURE_VECTOR",
                    "missing_rule": "retain zero-flow calendar row; do not impute a regime label or reuse a future/fold-wide value",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
            continue
        score = (
            float(feature["league_entropy"])
            + float(feature["line_entropy"])
            + float(feature["market_uncertainty_mean"])
        )
        rows.append(
            {
                "calendar_index": row["calendar_index"],
                "issue": row["issue"],
                "year": row["year"],
                "issue_instance": row["issue_instance"],
                "source_issue_instance": feature["issue_instance"],
                "regime_source_key": feature["feature_row_sha256"],
                "regime_panel_id": "PENDING_STRICTLY_PRIOR_REGIME_LABEL",
                "feature_row_sha256": feature["feature_row_sha256"],
                "feature_cutoff_ts": feature["feature_cutoff_ts"],
                "regime_score": f"{score:.12f}",
                "regime_algorithm_id": "REGIME_WF_PRE_EVENT_TERCILES_V1",
                "regime_label": "PENDING",
                "prior_training_feature_count": 0,
                "prior_training_feature_sha256": "",
                "regime_bin_lower": "",
                "regime_bin_upper": "",
                "regime_fallback": "",
                "regime_status": "PRE_EVENT_FEATURE_VECTOR_AVAILABLE",
                "missing_rule": "#193 nested fit may use only prior-train transforms/bins; no current/future/fold-wide bin fit",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    prior: list[dict[str, object]] = []
    for row in rows:
        if row["regime_status"] != "PRE_EVENT_FEATURE_VECTOR_AVAILABLE":
            continue
        row["prior_training_feature_count"] = len(prior)
        row["prior_training_feature_sha256"] = canonical_hash(
            [
                {
                    "issue_instance": str(item["issue_instance"]),
                    "feature_row_sha256": str(item["feature_row_sha256"]),
                    "regime_score": str(item["regime_score"]),
                }
                for item in prior
            ]
        )
        if len(prior) < 52:
            row["regime_label"] = "FALLBACK_INSUFFICIENT_PRIOR_52"
            row["regime_panel_id"] = "REGIME_FALLBACK_INSUFFICIENT_PRIOR_52"
            row["regime_fallback"] = "INSUFFICIENT_PRIOR_PRE_EVENT_FEATURES"
        else:
            scores = sorted(float(item["regime_score"]) for item in prior)
            low_cut = scores[(len(scores) - 1) // 3]
            high_cut = scores[(2 * (len(scores) - 1)) // 3]
            score = float(row["regime_score"])
            label = "LOW" if score <= low_cut else "MID" if score <= high_cut else "HIGH"
            row["regime_label"] = label
            row["regime_panel_id"] = f"REGIME_WF_PRE_EVENT_TERCILES_V1_{label}"
            row["regime_bin_lower"] = "-inf" if label == "LOW" else f"{low_cut:.12f}"
            row["regime_bin_upper"] = f"{low_cut:.12f}" if label == "LOW" else f"{high_cut:.12f}" if label == "MID" else "+inf"
        prior.append(row)
    if len(rows) != len(calendar) or len({row["issue_instance"] for row in rows}) != len(calendar):
        raise RuntimeError("#193 regime map calendar coverage drift")
    available = [row for row in rows if row["regime_status"] == "PRE_EVENT_FEATURE_VECTOR_AVAILABLE"]
    binding = {
        "source_package": SOURCE_193A.name,
        "source_file": "issue_regime_features.csv.gz",
        "source_file_sha256": sha256_file(SOURCE_193A / "issue_regime_features.csv.gz"),
        "source_content_identity_sha256": EXPECTED_SOURCES[SOURCE_193A.name]["content"],
        "join_key": "(issue,year) exact; #137 OOS and #193 canonical instance suffixes are intentionally non-identical",
        "calendar_issue_count": len(rows),
        "available_feature_count": len(available),
        "missing_feature_count": len(rows) - len(available),
        "map_sha256": canonical_hash(
            [{key: str(value) for key, value in row.items()} for row in rows]
        ),
        "regime_definition": "REGIME_WF_PRE_EVENT_TERCILES_V1: score=league_entropy+line_entropy+market_uncertainty_mean from #193 Tier-C pre-event feature rows; exact expanding-prior terciles after 52 available prior feature rows, otherwise explicit fallback. No outcome is used for transform, bin, tie-break or label.",
        "missing_fallback": "MISSING_PRE_EVENT_FEATURE_VECTOR is its own panel id; no label, return, loss or pseudo-feature is imputed",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }
    return rows, binding


def stage_attribution_contract(traces: list[dict[str, object]]) -> dict[str, object]:
    """Freeze what may be attributed without re-splicing upstream stages."""
    return {
        "key": [
            *PATH_IDENTITY,
            "calendar_index",
            "issue_instance",
            "sleeve_id",
            "stage_id",
        ],
        "stages": {
            "STAGE_1_SELECTION": "immutable selector trace only; realized contribution is NOT_IDENTIFIABLE_WITHOUT_SPLICE",
            "STAGE_2_DIRECTION": "immutable direction/role trace only; realized contribution is NOT_IDENTIFIABLE_WITHOUT_SPLICE",
            "STAGE_3_TICKET_CONSTRUCTION": "immutable allocation digest/ticket multiplicity only; realized contribution is NOT_IDENTIFIABLE_WITHOUT_SPLICE",
            "STAGE_4_POSITIONING": "exactly identifiable: native request, normalization multiplier, weight target, rounded funded tickets, retained cash and resulting same-ticket funding delta",
        },
        "upstream_trace_registry_sha256": canonical_hash(traces),
        "allowed_exact_fields": [
            "native_requested_ticket_count",
            "normalization_multiplier",
            "portfolio_weight",
            "actual_ticket_count",
            "retained_cash_yuan",
            "same_ticket_stage4_funding_delta_yuan",
        ],
        "prohibited": "do not recreate selection/direction/ticket counterfactuals or assign their P&L contribution without an immutable source contribution bridge",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def sleeve_trace_registry(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Bind the inherited Stage-1→3 trace, without reading its settlement.

    #170's identity freeze holds the upstream selection/direction identity and
    # its allocation digest holds the ticket-construction multiplicities.  A
    #192 sleeve may resize only those exact trace elements, never substitute a
    #new selection, result code, or ticket vector.
    """
    common_issues = {r["issue_instance"] for r in rows}
    identities = read_csv_gzip(SOURCE_170 / "identity_freeze.csv.gz")
    allocations = read_csv_gzip(SOURCE_170 / "identity_allocation_digest.csv.gz")
    result: list[dict[str, object]] = []
    for sleeve, alias, arm, _ in SLEEVES:
        ids = [
            r
            for r in identities
            if r["selector_alias"] == alias and r["issue_instance"] in common_issues
        ]
        allocs = [
            r
            for r in allocations
            if r["selector_alias"] == alias
            and r["allocation_arm"] == arm
            and r["issue_instance"] in common_issues
        ]
        ids.sort(
            key=lambda r: (
                r["issue_instance"],
                r["portfolio_id"],
                r["source_identity_row_sha256"],
            )
        )
        allocs.sort(
            key=lambda r: (r["issue_instance"], r["portfolio_id"], r["counts_sha256"])
        )
        validate_trace_keys(ids, allocs, sleeve)
        requests = [r for r in rows if r["sleeve_id"] == sleeve]
        result.append(
            {
                "sleeve_id": sleeve,
                "selector_alias": alias,
                "allocation_arm": arm,
                "stage_1_3_trace_status": "COMPLETE_INHERITED_FROZEN",
                "source_identity_count": len(ids),
                "source_allocation_count": len(allocs),
                "source_identity_trace_sha256": canonical_hash(
                    [r["source_identity_row_sha256"] for r in ids]
                ),
                "source_ticket_trace_sha256": canonical_hash(
                    [r["counts_sha256"] for r in allocs]
                ),
                "native_requested_ticket_count": sum(
                    int(r["native_requested_ticket_count"]) for r in requests
                ),
                "native_requested_stake_yuan": sum(
                    int(r["native_requested_stake_yuan"]) for r in requests
                ),
                "trace_rule": "Stage 4 may only size down/abstain from these inherited selection→direction→ticket traces.",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return result


def validate_trace_keys(
    identities: list[dict[str, str]], allocations: list[dict[str, str]], sleeve_id: str
) -> None:
    """Reject same-count but non-identical upstream trace rows."""
    if not identities or not allocations:
        raise RuntimeError(f"empty inherited trace: {sleeve_id}")

    def key(row: dict[str, str]) -> tuple[str, str]:
        return (row["issue_instance"], row["portfolio_id"])

    id_by_key = {key(row): row for row in identities}
    allocation_by_key = {key(row): row for row in allocations}
    if len(id_by_key) != len(identities) or len(allocation_by_key) != len(allocations):
        raise RuntimeError(f"non-unique inherited trace key: {sleeve_id}")
    if id_by_key.keys() != allocation_by_key.keys():
        raise RuntimeError(f"inherited trace key mismatch: {sleeve_id}")
    for trace_key, identity in id_by_key.items():
        allocation = allocation_by_key[trace_key]
        if identity["selector_alias"] != allocation["selector_alias"]:
            raise RuntimeError(f"selector mismatch in inherited trace: {sleeve_id}")
        if identity["support_key_sha256"] != allocation["support_key_sha256"]:
            raise RuntimeError(f"support mismatch in inherited trace: {sleeve_id}")


def read_csv_gzip(path: Path) -> list[dict[str, str]]:
    import gzip

    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values())
    if total <= 0.0 or not math.isfinite(total):
        n = len(weights)
        return {key: 1.0 / n for key in sorted(weights)}
    return {key: max(0.0, value) / total for key, value in weights.items()}


def equal_weights(sleeves: list[str]) -> tuple[dict[str, float], str]:
    return ({sleeve: 1.0 / len(sleeves) for sleeve in sleeves}, "EQUAL_WEIGHT")


def active_common_history(
    history: list[dict[str, float | None]], sleeves: list[str]
) -> list[dict[str, float]]:
    """Keep only full sleeve observations with positive actual stake.

    Gate B supplies `None` rather than 0 for a NO_BET/unavailable sleeve.
    Zero flow remains in the capital calendar but is not an active return
    observation for the 52-observation estimator.
    """
    active = [
        {s: float(row[s]) for s in sleeves}
        for row in history
        if all(row.get(s) is not None for s in sleeves)
    ]
    return active[-52:]


def covariance_matrix(
    observations: list[dict[str, float]], sleeves: list[str], shrinkage: float = 0.10
) -> list[list[float]]:
    n = len(observations)
    if n < 2:
        raise ValueError("insufficient observations")
    means = {s: sum(row[s] for row in observations) / n for s in sleeves}
    sample = [
        [
            sum((row[a] - means[a]) * (row[b] - means[b]) for row in observations)
            / (n - 1)
            for b in sleeves
        ]
        for a in sleeves
    ]
    # Deterministic diagonal shrinkage makes the matrix well-conditioned but
    # does not conceal a zero/singular data condition: callers still fallback.
    return [
        [
            (1.0 - shrinkage) * sample[i][j]
            + (shrinkage * sample[i][i] if i == j else 0.0)
            for j in range(len(sleeves))
        ]
        for i in range(len(sleeves))
    ]


def project_simplex(values: list[float]) -> list[float]:
    """Project a finite vector onto the long-only unit simplex.

    This is the deterministic Duchi et al. threshold projection.  Keeping it
    here (rather than relying on a platform optimiser) freezes both the
    long-only constraint and the tie behaviour of the two covariance-based
    allocation methods.
    """
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("nonfinite simplex input")
    ordered = sorted(values, reverse=True)
    running = 0.0
    rho = -1
    for index, value in enumerate(ordered, 1):
        running += value
        if value - (running - 1.0) / index > 0.0:
            rho = index
    if rho < 1:
        raise ValueError("simplex projection has no positive support")
    theta = (sum(ordered[:rho]) - 1.0) / rho
    projected = [max(0.0, value - theta) for value in values]
    total = sum(projected)
    if total <= 0.0 or not math.isfinite(total):
        raise ValueError("invalid simplex projection")
    return [value / total for value in projected]


def covariance_times(
    covariance: list[list[float]], weights: list[float]
) -> list[float]:
    return [
        sum(covariance[row][column] * weights[column] for column in range(len(weights)))
        for row in range(len(weights))
    ]


def projected_covariance_weights(
    method: str, covariance: list[list[float]], vols: list[float]
) -> tuple[list[float], bool]:
    """Return the contract's deterministic long-only covariance allocation.

    Both objectives use fixed-order projected-gradient descent, a declared
    1e-12 L1 convergence tolerance and at most 5,000 iterations.  The
    backtracking schedule is deterministic and rejects a non-improving step;
    callers then use the frozen equal-weight fallback.
    """
    n = len(vols)
    weights = [1.0 / n] * n

    def objective(candidate: list[float]) -> float:
        sigma_w = covariance_times(covariance, candidate)
        variance = sum(candidate[index] * sigma_w[index] for index in range(n))
        if variance <= 1e-24 or not math.isfinite(variance):
            return math.inf
        if method == "PRIOR_MINIMUM_VARIANCE":
            return variance
        numerator = sum(candidate[index] * vols[index] for index in range(n))
        if numerator <= 1e-24 or not math.isfinite(numerator):
            return math.inf
        # Minimising log(volatility) - log(weighted individual volatility)
        # is exactly maximum diversification under the simplex constraint.
        return 0.5 * math.log(variance) - math.log(numerator)

    previous = objective(weights)
    if not math.isfinite(previous):
        return weights, False
    # Covariance entries are issue-return variances, typically far below one.
    # Scale the initial projected-gradient step to the actual matrix norm;
    # an absolute floor of one would make a 1e-12 convergence contract
    # unattainably slow for ordinary return units.
    scale = max(
        1e-12,
        max(sum(abs(value) for value in row) for row in covariance),
    )
    for _ in range(5000):
        sigma_w = covariance_times(covariance, weights)
        variance = sum(weights[index] * sigma_w[index] for index in range(n))
        if variance <= 1e-24 or not math.isfinite(variance):
            return weights, False
        if method == "PRIOR_MINIMUM_VARIANCE":
            gradient = [2.0 * value for value in sigma_w]
        elif method == "PRIOR_MAXIMUM_DIVERSIFICATION":
            numerator = sum(weights[index] * vols[index] for index in range(n))
            if numerator <= 1e-24 or not math.isfinite(numerator):
                return weights, False
            gradient = [
                sigma_w[index] / variance - vols[index] / numerator
                for index in range(n)
            ]
        else:
            raise ValueError(f"unknown covariance allocator: {method}")
        # The diversification-ratio gradient is dimensionless and can be
        # much larger than the covariance entries.  Scale that objective by
        # its current infinity norm; minimum variance retains matrix-norm
        # scaling.  Both choices are deterministic and are only initial
        # steps for the fixed backtracking schedule below.
        step = (
            1.0 / max(1e-12, max(abs(value) for value in gradient))
            if method == "PRIOR_MAXIMUM_DIVERSIFICATION"
            else 1.0 / scale
        )
        candidate = weights
        candidate_objective = previous
        for _ in range(60):
            trial = project_simplex(
                [weights[index] - step * gradient[index] for index in range(n)]
            )
            trial_objective = objective(trial)
            if math.isfinite(trial_objective) and trial_objective <= previous + 1e-15:
                candidate = trial
                candidate_objective = trial_objective
                break
            step *= 0.5
        else:
            return weights, False
        if (
            sum(abs(candidate[index] - weights[index]) for index in range(n))
            <= 1e-12
            or abs(candidate_objective - previous) <= 1e-12
        ):
            return candidate, True
        weights, previous = candidate, candidate_objective
    return weights, False


def dynamic_weights(
    method: str, history: list[dict[str, float | None]], sleeves: list[str]
) -> tuple[dict[str, float], str]:
    """Exact prior-only model used by Gate B; never inspect the current issue."""
    if method == "EQUAL_WEIGHT":
        return equal_weights(sleeves)
    observations = active_common_history(history, sleeves)
    if len(observations) < 52:
        return (*equal_weights(sleeves)[0:1], "FALLBACK_INSUFFICIENT_52_COMMON_ACTIVE")
    try:
        covariance = covariance_matrix(observations, sleeves)
        vols = {s: math.sqrt(max(0.0, covariance[i][i])) for i, s in enumerate(sleeves)}
        if any(not math.isfinite(v) or v <= 1e-12 for v in vols.values()):
            return (*equal_weights(sleeves)[0:1], "FALLBACK_ZERO_OR_NONFINITE_VOL")
        if method == "PRIOR_INVERSE_VOL":
            return normalize({s: 1.0 / vols[s] for s in sleeves}), "PRIOR_INVERSE_VOL"
        if method == "PRIOR_DRAWDOWN_AWARE":
            penalties: dict[str, float] = {}
            for s in sleeves:
                equity = peak = 1.0
                max_drawdown = 0.0
                for row in observations:
                    equity *= 1.0 + row[s]
                    peak = max(peak, equity)
                    max_drawdown = max(max_drawdown, 1.0 - equity / peak)
                penalties[s] = max_drawdown
            return normalize(
                {s: 1.0 / (vols[s] * (1.0 + penalties[s])) for s in sleeves}
            ), "PRIOR_DRAWDOWN_AWARE"
        if method in {
            "PRIOR_MINIMUM_VARIANCE",
            "PRIOR_MAXIMUM_DIVERSIFICATION",
        }:
            weights, converged = projected_covariance_weights(
                method, covariance, [vols[s] for s in sleeves]
            )
            if not converged:
                return (*equal_weights(sleeves)[0:1], "FALLBACK_COVARIANCE_NO_CONVERGENCE")
            return normalize(dict(zip(sleeves, weights))), method
        if method != "PRIOR_ERC":
            raise ValueError(f"unknown weight method: {method}")
        weights = [1.0 / len(sleeves)] * len(sleeves)
        for _ in range(5000):
            marginal = [
                sum(covariance[i][j] * weights[j] for j in range(len(sleeves)))
                for i in range(len(sleeves))
            ]
            contributions = [weights[i] * marginal[i] for i in range(len(sleeves))]
            total = sum(contributions)
            if total <= 1e-15 or any(
                x <= 0.0 or not math.isfinite(x) for x in contributions
            ):
                return (*equal_weights(sleeves)[0:1], "FALLBACK_ERC_NONPOSITIVE_RISK")
            target = total / len(sleeves)
            if max(abs(x - target) for x in contributions) <= 1e-12:
                return normalize(dict(zip(sleeves, weights))), "PRIOR_ERC"
            weights = list(
                normalize(
                    {
                        s: weights[i] * target / contributions[i]
                        for i, s in enumerate(sleeves)
                    }
                ).values()
            )
        return (*equal_weights(sleeves)[0:1], "FALLBACK_ERC_NO_CONVERGENCE")
    except (ArithmeticError, ValueError, OverflowError):
        return (*equal_weights(sleeves)[0:1], "FALLBACK_SINGULAR_COVARIANCE")


def allocate_integer_tickets(
    mode: str,
    fraction: float,
    preissue_bankroll_yuan: int,
    native_ticket_caps: dict[str, int],
    weights: dict[str, float],
    atomic_ticket_blocks: dict[str, bool] | None = None,
) -> dict[str, object]:
    """Freeze the simultaneous, capped integer ticket allocator.

    Atomic sleeves (currently ``FULL_ENUMERATED``) are whole-native blocks.
    We first derive the ordinary capped continuous target over *all* sleeves.
    We then enumerate feasible atomic subsets and choose the one whose
    resulting executable integer allocation is closest to that target.  This
    makes whole-FULL safety compatible with the declared portfolio weights:
    affordability alone can never cause FULL to consume the budget first.
    """
    if mode not in FUNDING_MODES:
        raise ValueError(f"unknown funding mode: {mode}")
    if not 0.0 < fraction <= 1.0 or preissue_bankroll_yuan < 0:
        raise ValueError("invalid fraction or preissue bankroll")
    cap_total = sum(max(0, value) for value in native_ticket_caps.values())
    if mode == "NATIVE_REQUEST_CONTROL":
        if fraction != 1.0:
            raise ValueError("NATIVE_REQUEST_CONTROL requires fraction=1.0")
        mode_notional = cap_total * TICKET_STAKE_YUAN
    elif mode == "SCALED_NATIVE_REQUEST":
        mode_notional = fraction * cap_total * TICKET_STAKE_YUAN
    elif mode == "FIXED_100K_NOTIONAL":
        mode_notional = fraction * INITIAL_BANKROLL_YUAN
    else:
        mode_notional = fraction * preissue_bankroll_yuan
    budget_yuan = min(mode_notional, float(preissue_bankroll_yuan))
    budget_tickets = int(math.floor(budget_yuan / TICKET_STAKE_YUAN))
    caps = {sleeve: max(0, value) for sleeve, value in native_ticket_caps.items()}
    assigned = {s: 0 for s in sorted(caps)}
    atomic_ticket_blocks = atomic_ticket_blocks or {}
    if set(atomic_ticket_blocks) - set(native_ticket_caps):
        raise ValueError("atomic policy supplied for an unknown sleeve")
    reasons: set[str] = set()
    if cap_total == 0:
        reasons.add("NO_BET_NATIVE_ZERO_REQUEST")
    if budget_tickets == 0 and cap_total:
        reasons.add("NO_BET_BUDGET_LT_TICKET")
    requested = min(budget_tickets, cap_total)
    if budget_tickets < int(math.ceil(mode_notional / TICKET_STAKE_YUAN)):
        reasons.add("SCALED_BY_PREISSUE_BANKROLL")
    if requested < cap_total and cap_total:
        reasons.add("SCALED_BY_MODE_NOTIONAL")
    atomic = [
        sleeve
        for sleeve in sorted(assigned)
        if atomic_ticket_blocks.get(sleeve, False) and caps[sleeve] > 0
    ]
    target = capped_continuous_targets(requested, caps, weights)
    feasible: list[tuple[tuple[object, ...], dict[str, int], tuple[str, ...]]] = []
    for mask in range(1 << len(atomic)):
        selected = tuple(atomic[index] for index in range(len(atomic)) if mask & (1 << index))
        atomic_total = sum(caps[sleeve] for sleeve in selected)
        if atomic_total > requested:
            continue
        candidate = {sleeve: (caps[sleeve] if sleeve in selected else 0) for sleeve in assigned}
        flexible_caps = {
            sleeve: caps[sleeve]
            for sleeve in assigned
            if sleeve not in atomic
        }
        candidate.update(
            capped_integer_waterfill(
                requested - atomic_total, flexible_caps, weights
            )
        )
        actual = sum(candidate.values())
        # The primary objective is distance from the declared continuous
        # portfolio target; retained cash and a lexical subset signature make
        # otherwise indistinguishable choices deterministic.
        objective = (
            round(sum(abs(candidate[sleeve] - target[sleeve]) for sleeve in candidate), 12),
            requested - actual,
            tuple(selected),
        )
        feasible.append((objective, candidate, selected))
    if not feasible:
        raise RuntimeError("no feasible atomic funding subset")
    _, assigned, selected_atomic = min(feasible, key=lambda item: item[0])
    for sleeve in atomic:
        if sleeve not in selected_atomic:
            if caps[sleeve] > requested:
                reasons.add("ATOMIC_BLOCK_UNFUNDED_RETAIN_OR_REALLOCATE_CASH")
            else:
                reasons.add("ATOMIC_BLOCK_EXCLUDED_BY_TARGET_OBJECTIVE")
    actual_tickets = sum(assigned.values())
    if actual_tickets < min(budget_tickets, cap_total) and cap_total:
        reasons.add("CAPACITY_EXHAUSTED_RETAIN_CASH")
    if (
        any(
            assigned[s] == native_ticket_caps[s] and native_ticket_caps[s] > 0
            for s in assigned
        )
        and actual_tickets < cap_total
    ):
        reasons.add("CAP_BOUND_WATERFILL")
    actual_stake = actual_tickets * TICKET_STAKE_YUAN
    return {
        "mode_notional_yuan": mode_notional,
        "issue_budget_yuan": budget_yuan,
        "requested_ticket_count": cap_total,
        "continuous_target_ticket_count_by_sleeve": target,
        "actual_ticket_count_by_sleeve": assigned,
        "selected_atomic_blocks": list(selected_atomic),
        "allocation_distance_l1_tickets": sum(
            abs(assigned[sleeve] - target[sleeve]) for sleeve in assigned
        ),
        "actual_total_stake_yuan": actual_stake,
        "retained_cash_yuan": preissue_bankroll_yuan - actual_stake,
        "reason_codes": "|".join(sorted(reasons)) or "FUNDED_AS_REQUESTED",
    }


def capped_continuous_targets(
    ticket_budget: int, caps: dict[str, int], weights: dict[str, float]
) -> dict[str, float]:
    """Continuous capped-water-fill reference for the atomic subset objective."""
    result = {sleeve: 0.0 for sleeve in sorted(caps)}
    remaining = float(min(ticket_budget, sum(caps.values())))
    while remaining > 1e-12:
        free = [
            sleeve
            for sleeve in sorted(result)
            if result[sleeve] < caps[sleeve] - 1e-12
        ]
        if not free:
            break
        normalized = normalize({sleeve: weights.get(sleeve, 0.0) for sleeve in free})
        proposed = {
            sleeve: min(caps[sleeve] - result[sleeve], remaining * normalized[sleeve])
            for sleeve in free
        }
        placed = sum(proposed.values())
        if placed <= 1e-12:
            break
        for sleeve, increment in proposed.items():
            result[sleeve] += increment
        remaining -= placed
    return result


def capped_integer_waterfill(
    ticket_budget: int, caps: dict[str, int], weights: dict[str, float]
) -> dict[str, int]:
    """Deterministic integer capped water-fill over the supplied sleeves only."""
    assigned = {sleeve: 0 for sleeve in sorted(caps)}
    remaining = min(ticket_budget, sum(caps.values()))
    while remaining:
        free = [sleeve for sleeve in sorted(assigned) if assigned[sleeve] < caps[sleeve]]
        if not free:
            break
        normalized = normalize({sleeve: weights.get(sleeve, 0.0) for sleeve in free})
        quotas = {
            sleeve: min(caps[sleeve] - assigned[sleeve], remaining * normalized[sleeve])
            for sleeve in free
        }
        increments = {
            sleeve: min(caps[sleeve] - assigned[sleeve], int(math.floor(quotas[sleeve])))
            for sleeve in free
        }
        placed = sum(increments.values())
        if placed == 0:
            winner = sorted(
                free,
                key=lambda sleeve: (
                    -(quotas[sleeve] - math.floor(quotas[sleeve])), sleeve
                ),
            )[0]
            increments[winner] = 1
            placed = 1
        for sleeve, count in increments.items():
            assigned[sleeve] += count
        remaining -= placed
    return assigned


def normalization_contract() -> dict[str, object]:
    """Freeze the pre-weight capital/risk layer used by Gate B.

    This is deliberately separate from the long-only sleeve weights: a change
    in funding/abstention cannot be represented as intrinsic diversification.
    """
    return {
        "ordering": [
            "frozen native request/capacity",
            "strictly-prior provisional target weights",
            "strictly-prior covariance and portfolio volatility",
            "portfolio-level normalization multiplier",
            "mode/bankroll issue budget and integer ticket funding",
        ],
        "leverage": {
            "prohibited": True,
            "maximum_multiplier": 1.0,
            "reason": "normalization may resize down but never create exposure above the frozen native request",
        },
        "prior_volatility_estimator": {
            "return": "native/fixed-capital pre-tax sleeve return on strictly-prior common active issue rows only",
            "minimum_common_active_observations": 52,
            "covariance": "unbiased sample covariance then 10% diagonal shrinkage",
            "portfolio_volatility": "sqrt(w' Sigma w)",
            "volatility_floor": 1e-12,
            "input_identity": "weight_method, covariance_sleeve_order and covariance_input_sha256 are persisted on every executable normalization row; covariance is interpreted only in that declared sleeve order",
        },
        "methods": {
            "UNIT_CAPITAL": "multiplier=1; issue risk_budget_yuan=pre-normalization mode/bankroll budget; executable reference",
            "EQUAL_CAPITAL": "multiplier=1; equal target capital across currently active sleeves before capped integer water-fill; executable only with EQUAL_WEIGHT, otherwise explicit INAPPLICABLE_METHOD_WEIGHT_COMBINATION",
            "UNIT_EX_ANTE_VOL_CAPPED_5PCT": "multiplier=min(1, 0.05/ex_ante_portfolio_volatility); this is a 5% target capped at one, not unconstrained unit-vol scaling; executable after 52 valid prior common-active observations",
            "RAW_UNNORMALIZED_CONTROL": "multiplier=1; reports frozen native-capital exposure without volatility targeting; diagnostic/control, not an Edge or risk-adjusted promotion claim",
        },
        "fallback": {
            "trigger": "fewer than 52 common active observations, nonfinite/nonpositive covariance, or nonfinite portfolio volatility",
            "method": "UNIT_CAPITAL",
            "multiplier": 1.0,
            "status": "FALLBACK_UNIT_CAPITAL_INSUFFICIENT_PRIOR_RISK_HISTORY",
        },
        "gate_b_ledger": {
            "required_issue_fields": [
                "normalization_method",
                "weight_method",
                "normalization_status",
                "normalization_executable",
                "covariance_sleeve_order_json",
                "covariance_input_sha256",
                "ex_ante_volatility",
                "target_volatility",
                "realized_capital_multiplier",
                "risk_budget_yuan",
                "pre_normalization_mode_notional_yuan",
                "normalized_mode_notional_yuan",
            ],
            "reconciliation": "normalized_mode_notional=min(pre_normalization_mode_notional×realized_capital_multiplier, frozen native requested stake, preissue bankroll); actual funded stake is then exact integer water-fill and may be lower only from caps/atomicity/rounding/cash",
        },
    }


def normalization_state(
    method: str,
    native_requested_stake_yuan: float,
    preissue_bankroll_yuan: float,
    mode_notional_yuan: float,
    weight_method: str,
    provisional_weights: dict[str, float],
    covariance_sleeve_order: Sequence[str],
    covariance: list[list[float]] | None,
    prior_common_active_observation_count: int,
) -> dict[str, object]:
    """Execute the frozen pre-funding normalization pipeline.

    Weights are deliberately inputs: they must be produced by the strictly
    prior allocator before portfolio volatility can be defined.  The function
    returns only a capped-down capital budget, never leverage or a hidden
    post-outcome weight optimisation.
    """
    base_notional = max(
        0.0,
        min(float(native_requested_stake_yuan), float(preissue_bankroll_yuan), float(mode_notional_yuan)),
    )
    if method not in {
        "UNIT_CAPITAL",
        "EQUAL_CAPITAL",
        "UNIT_EX_ANTE_VOL_CAPPED_5PCT",
        "RAW_UNNORMALIZED_CONTROL",
    }:
        raise ValueError(f"unknown normalization method: {method}")
    ordered = list(covariance_sleeve_order)
    covariance_identity = canonical_hash(
        {
            "covariance_sleeve_order": ordered,
            "covariance": covariance,
        }
    )

    def result(
        status: str,
        volatility: float | None,
        multiplier: float,
        executable: bool = True,
    ) -> dict[str, object]:
        return {
            "normalization_method": method,
            "weight_method": weight_method,
            "normalization_status": status,
            "normalization_executable": executable,
            "covariance_sleeve_order_json": json.dumps(ordered, separators=(",", ":")),
            "covariance_input_sha256": covariance_identity,
            "ex_ante_volatility": volatility,
            "target_volatility": TARGET_EX_ANTE_VOLATILITY,
            "realized_capital_multiplier": multiplier,
            "pre_normalization_mode_notional_yuan": base_notional,
            "risk_budget_yuan": base_notional * multiplier,
            "normalized_mode_notional_yuan": base_notional * multiplier,
        }

    if (
        len(ordered) != len(set(ordered))
        or set(ordered) != set(provisional_weights)
    ):
        return result("INAPPLICABLE_COVARIANCE_SLEEVE_ORDER", None, 0.0, False)
    values = [float(provisional_weights[name]) for name in ordered]
    if (
        not values
        or any(not math.isfinite(value) or value < 0.0 for value in values)
        or not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-12)
    ):
        return result("FALLBACK_UNIT_CAPITAL_INVALID_PROVISIONAL_WEIGHTS", None, 1.0)
    equal_active = all(
        math.isclose(value, values[0], rel_tol=0.0, abs_tol=1e-12)
        for value in values
    )
    if method == "EQUAL_CAPITAL" and (
        weight_method != "EQUAL_WEIGHT" or not equal_active
    ):
        return result("INAPPLICABLE_METHOD_WEIGHT_COMBINATION", None, 0.0, False)
    if method != "UNIT_EX_ANTE_VOL_CAPPED_5PCT":
        status = (
            "EQUAL_CAPITAL_EQUAL_ACTIVE_WEIGHTS"
            if method == "EQUAL_CAPITAL"
            else "UNIT_CAPITAL_MULTIPLIER_ONE"
        )
        return result(status, None, 1.0)
    if prior_common_active_observation_count < 52:
        status = "FALLBACK_UNIT_CAPITAL_INSUFFICIENT_PRIOR_RISK_HISTORY"
        volatility = None
    elif (
        covariance is None
        or len(covariance) != len(values)
        or any(len(row) != len(values) for row in covariance)
        or any(not math.isfinite(value) for row in covariance for value in row)
    ):
        status = "FALLBACK_UNIT_CAPITAL_NONFINITE_COVARIANCE"
        volatility = None
    else:
        variance = sum(
            values[i] * covariance[i][j] * values[j]
            for i in range(len(values))
            for j in range(len(values))
        )
        if not math.isfinite(variance) or variance <= 1e-24:
            status = "FALLBACK_UNIT_CAPITAL_ZERO_OR_NONFINITE_VOLATILITY"
            volatility = None
        else:
            volatility = math.sqrt(variance)
            multiplier = min(1.0, TARGET_EX_ANTE_VOLATILITY / volatility)
            return result(
                "TARGET_CAPPED_NO_LEVERAGE"
                if multiplier == 1.0
                else "TARGET_SCALED_DOWN",
                volatility,
                multiplier,
            )
    return result(status, volatility, 1.0)


def funding_contract() -> dict[str, object]:
    return {
        "initial_bankroll_yuan": INITIAL_BANKROLL_YUAN,
        "ticket_stake_yuan": TICKET_STAKE_YUAN,
        "position_budget_fractions": [x / 100 for x in POSITION_FRACTIONS],
        "modes": {
            "NATIVE_REQUEST_CONTROL": "fraction must equal 1; mode_notional=sum(native requested ticket caps) × ¥2, reduced only for a current-bankroll shortfall",
            "SCALED_NATIVE_REQUEST": "exploratory only: mode_notional=fraction × sum(native requested ticket caps) × ¥2; never an accepted native baseline",
            "FIXED_100K_NOTIONAL": "mode_notional=fraction × ¥100,000; notional does not reinvest",
            "COMPOUNDING_BANKROLL": "mode_notional=fraction × preissue bankroll",
        },
        "integer_allocator": {
            "normalization_precondition": "apply normalization_contract ordering before this allocator; this allocator never estimates volatility or silently adds leverage",
            "universal_budget": "issue_budget=min(mode_notional, preissue_bankroll); ticket_budget=floor(issue_budget/¥2)",
            "raw_ticket_target": "iterative normalized sleeve weight × remaining ticket budget, hard-capped at native requested tickets",
            "atomic_blocks": "FULL_ENUMERATED is funded only as its complete native ticket block. First derive capped continuous targets across every sleeve. Enumerate feasible whole-atomic subsets; for each, water-fill only prefix-executable sleeves, then select the allocation minimizing (L1 distance from the continuous target, retained tickets, lexical included-block tuple). An excluded atomic block is NO_BET; residual is reallocated only to executable prefixes or retained as cash. Affordability alone never gives FULL priority over its target weight.",
            "rounding": "each water-fill pass floors capped quotas, then gives one residual ticket to largest fractional quota; ties sleeve_id ascending",
            "cap_bound_leftover": "remove sleeves at native cap and repeat weighted water-fill until no ticket budget or no capacity; retain any unspendable cash",
            "minimum": "budget under ¥2 or all native requests zero is NO_BET, zero flow not a loss",
            "concurrency": "all sleeve tickets for an issue are funded before that issue's outcomes; no payout recycling, deposit, loan, or top-up",
            "invariants": [
                "actual_total_stake <= preissue_bankroll",
                "actual_ticket_count_by_sleeve <= native_requested_ticket_count",
                "retained_cash=preissue_bankroll-actual_total_stake >= 0",
            ],
            "reason_codes": [
                "FUNDED_AS_REQUESTED",
                "SCALED_BY_MODE_NOTIONAL",
                "SCALED_BY_PREISSUE_BANKROLL",
                "CAP_BOUND_WATERFILL",
                "CAPACITY_EXHAUSTED_RETAIN_CASH",
                "NO_BET_NATIVE_ZERO_REQUEST",
                "NO_BET_BUDGET_LT_TICKET",
                "ATOMIC_BLOCK_UNFUNDED_RETAIN_OR_REALLOCATE_CASH",
                "ATOMIC_BLOCK_EXCLUDED_BY_TARGET_OBJECTIVE",
            ],
            "gate_b_requirement": "settle each allocated ticket with native per-ticket tax; fail closed if no exact ticket-level settlement bridge exists",
        },
    }


def methodology_contract() -> dict[str, object]:
    return {
        "membership": "all pairs across the full eligible complete catalog; all nonempty subsets of the locked three-sleeve H1 panel and of the preregistered robust higher-order shortlist. Every dynamic family retains its exact source M curve and strictly-prior selector; no Stage 1–3 selection, direction, ticket, seed, or support construction changes",
        "attribution": {
            "upstream": "retain each inherited Stage-1→3 sleeve path unchanged at native request; absent an immutable upstream contribution bridge its realised P&L attribution is NOT_IDENTIFIABLE_WITHOUT_SPLICE",
            "stage4": "exactly attribute only size/downscale/cash/weight/rounding effects against the same frozen tickets and native-request control",
            "covariance": "covariance can explain variance/drawdown/tail-risk changes but never adds net yuan: portfolio P&L must equal the exact sum of funded sleeve P&L",
        },
        "normalization": normalization_contract(),
        "dependence_layers": {
            "intrinsic_native": "native or fixed-capital matched-support sleeve returns before Stage-4 funding/abstention; this is the only layer that may be called intrinsic diversification",
            "realized_funded_flow": "actual Stage-4 ticket-funded yuan flow, including cash and NO_BET. Lower correlation caused by abstention/support truncation/retained cash is funding behavior, never intrinsic diversification",
            "risk_decomposition": "publish marginal/Euler variance contribution, matched drawdown/tail comparison, capital utilization, retained cash, rounding and exposure-size effects separately; no covariance-as-P&L field",
        },
        "regime_and_stage_interface": {
            "source": "regime_map.csv binds every #192 calendar key to #193 Gate-A pre-event feature evidence",
            "regime_bins": "learned regime bins/labels are fitted only inside strictly-prior train observations and carry prior_training_input_sha256; missing source rows remain MISSING_PRE_EVENT_FEATURE_VECTOR",
            "stage_attribution": "stage_attribution_contract.json prohibits unbound Stage 1–3 counterfactual splices and permits only exact Stage-4 funding attribution",
        },
        "weight_model": {
            "issue_return": "pre-tax sleeve net / actual sleeve stake; only actual stake > ¥0 produces an active observation",
            "history": "strictly prior chronological full-calendar issues. NO_BET/unavailable stays a zero-flow path row but is absent from active-return samples. Dynamic methods require 52 most-recent common active observations for every participating sleeve.",
            "covariance": "unbiased sample covariance of 52 common active issue returns, then 10% diagonal shrinkage",
            "constraints": "long-only weights, each >=0, sum exactly 1; current issue is never in history",
            "PRIOR_INVERSE_VOL": "w_i ∝ 1/vol_i, vol_i=sqrt(shrunk covariance_ii); vol floor 1e-12",
            "PRIOR_ERC": "start equal; multiplicative risk-contribution iteration w_i←normalize(w_i×target_RC/RC_i), max 5000 iterations, convergence max|RC-target|<=1e-12",
            "PRIOR_DRAWDOWN_AWARE": "w_i ∝ 1/(vol_i×(1+max prior common-active compounded drawdown_i))",
            "fallbacks": [
                "under 52 common active observations",
                "zero/nonfinite volatility",
                "singular/nonpositive ERC risk contributions",
                "ERC no convergence",
            ],
            "fallback_action": "EQUAL_WEIGHT with explicit per-issue fallback reason",
        },
        "weight_methods": [
            "EQUAL_WEIGHT",
            "PRIOR_INVERSE_VOL",
            "PRIOR_ERC",
            "PRIOR_DRAWDOWN_AWARE",
            "PRIOR_MINIMUM_VARIANCE",
            "PRIOR_MAXIMUM_DIVERSIFICATION",
        ],
        "additional_prior_allocators": {
            "PRIOR_MINIMUM_VARIANCE": "long-only minimum w'Σw on the same 52 strictly-prior common-active observations and 10% shrunk covariance; deterministic projected-gradient tolerance 1e-12, max 5000; fallback EQUAL_WEIGHT on nonfinite/nonconvergence",
            "PRIOR_MAXIMUM_DIVERSIFICATION": "maximize (w'vol)/sqrt(w'Σw) under long-only simplex constraints using the same strictly-prior covariance; deterministic projected-gradient tolerance 1e-12, max 5000; fallback EQUAL_WEIGHT on nonfinite/nonconvergence",
        },
        "M_rule": "H1 retains upstream fixed FULL=2187, MODEL=512 and Q=192. Expanded #148/#151/#159 families use only their materialized source M grids and the separate strictly-prior M-selection contract; no full-sample or test-period outcome can choose M. FULL is indivisible; every partial allocation requires its family prefix rule or abstains.",
        "primary_hypothesis": {
            "id": "RETROSPECTIVE_REPRODUCTION_R1_FIXED_THREE_SLEEVE_EQUAL_NATIVE",
            "candidate": "#170 BEST_FULL_FULL + MODEL_SOURCE_MODEL_CAP1_M512 + Q_SOURCE_Q_TOP_MASS_M192",
            "mode": "NATIVE_REQUEST_CONTROL",
            "position_fraction": 1.0,
            "weights": "EQUAL_WEIGHT",
            "normalization_method": "UNIT_CAPITAL",
            "comparison": "absolute pre-tax ¥100k path plus matched lift versus B170 BEST_FULL/FULL on exact common support and actual funding convention",
            "decision": "retrospective reproduction only: same-window positive or max-T-adjusted results are hypothesis-generating and cannot advance the accepted ladder; advancement requires genuinely held-out or forward validation plus strict PI review",
        },
        "multiplicity": {
            "frontier_status": "the locked three-sleeve retrospective reproduction and every parameter cell are descriptive/hypothesis-generating; raw Pareto or best-cell rank is never Edge evidence",
            "families": [
                "catalog_sleeve_family",
                "portfolio_membership",
                "weight_method",
                "normalization_method",
                "capital_mode",
                "position_fraction",
            ],
            "positive_inference": "20,000 paired stationary-block bootstrap max-T family-wise adjusted lower bounds at alpha=0.05; test all candidate-minus-control lifts within each frozen family",
            "winner_rule": "screen all cells, but no same-window result advances the ladder; a future genuinely held-out/forward candidate must pass the frozen family-wise rule and strict matched PI review",
            "negative_rule": "negative/no-promotion results report full frontier and may use proportionate descriptive evidence",
        },
        "sequential_inference": {
            "primary_estimand": "original strict chronological walk-forward replay; recompute weights, funding, cash, equity, drawdown and all state inside every replay",
            "path_bootstrap": "paired stationary block bootstrap, 20,000 replicates, expected block length 12 issues, seed 192001, each candidate/control shares exact resampled blocks and replays the complete state machine",
            "moving_block_sensitivity": "paired moving block bootstrap, block lengths 6, 12 and 20 chronological issues; full state replay",
            "iid_diagnostic": "IID issue bootstrap is ROI-only diagnostic and must not support bankroll, drawdown, recovery, dynamic-weight or compounded-growth claims",
        },
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "draw": "common deterministic issue-resample matrix paired across every portfolio",
        },
        "stability": ["YEAR", "FOLD", "LOYO", "EX_LARGEST_ISSUE", "EX_LARGEST_YEAR", "REGIME"],
        "gate_b_outputs": [
            "per_issue_paths",
            "ending_capital",
            "fundability",
            "first_unfundable",
            "drawdown",
            "time_under_water",
            "recovery",
            "ruin",
            "covariance_attribution",
            "pre_tax_primary_tax_reference",
            "standalone_m_curve",
            "selected_m_path",
            "dependence_panel",
            "portfolio_k_saturation",
        ],
        "chart_sources": [
            "chart_source_issue_equity_paths.csv.gz",
            "capital_utilization_frontier",
            "risk_return_frontier",
            "chart_source_dependence_panel.csv",
            "weight_history",
            "fundability_waterfall",
            "bootstrap_and_stability",
            "chart_source_standalone_m_curve.csv.gz",
            "chart_source_selected_m_path.csv.gz",
            "chart_source_portfolio_k_saturation.csv",
        ],
        "challenger_case": [
            "survivor/winner catalog selection",
            "parameter-search/multiple-comparison luck",
            "outcome/oracle leakage",
            "native versus exact-common support",
            "fewer bets/turnover/retained cash",
            "ex-post covariance/weight fitting",
            "single issue/year/payout cluster",
            "simpler-control explanation",
            "descriptive frontier overstated as Edge",
        ],
    }


def expanded_sleeve_catalog() -> list[dict[str, object]]:
    """Materialize the non-H1 executable Stage-1→3 sleeve families.

    The catalog deliberately stores all available source M values, rather than
    a historical winner.  Gate B chooses a per-issue M only through the frozen
    strictly-prior rule in :func:`m_selection_contract`.
    """
    catalog: list[dict[str, object]] = []
    for spec in EXPANDED_FAMILY_SPECS:
        source = Path(EXPECTED_SOURCES[spec["source_package"]]["path"])
        identity_name = str(spec["identity_file"]).split("[")[0]
        role_name = str(spec["role_file"]).split("[")[0]
        plan_name = str(spec["plan_file"]).split("[")[0]
        identities = read_csv_gzip(source / identity_name)
        roles = read_csv_gzip(source / role_name)
        plans = read_csv(source / plan_name)
        if spec["source_package"] == "bj159_gate_a_preoutcome_v2r1":
            identities = [row for row in identities if row["n"] == "7"]
            roles = [row for row in roles if row["n"] == "7"]
            plans = [row for row in plans if row["n"] == "7"]
            m_grid = sorted({int(row["nominal_M"]) for row in plans})
        else:
            mechanism = str(spec["mechanism"])
            target = (
                "Q_INFORMED_WR_DUPLICATE_STAKE"
                if mechanism == "WR_DUPLICATE_STAKE"
                else "Q_INFORMED_WOR_DISTINCT"
            )
            plans = [
                row
                for row in plans
                if row.get("ticket_mechanism") == target
            ]
            m_grid = sorted({int(row["M"]) for row in plans})
        if not identities or len(roles) != len(identities) * 7 or not m_grid:
            raise RuntimeError(f"incomplete executable sleeve family: {spec['candidate_id']}")
        seed_scope = sorted({str(row.get("seed", "NA")) for row in plans})
        catalog.append(
            {
                **spec,
                "source_identity_payload_sha256": sha256_file(source / identity_name),
                "source_role_payload_sha256": sha256_file(source / role_name),
                "source_plan_payload_sha256": sha256_file(source / plan_name),
                "identity_count": len(identities),
                "role_row_count": len(roles),
                "available_M_grid": ";".join(str(value) for value in m_grid),
                "available_M_grid_sha256": canonical_hash(m_grid),
                "seed_scope": ";".join(seed_scope),
                "native_ticket_identity": "exact source identity + frozen seed/replicate + ordinal or draw rank under ticket_prefix_rule",
                "tax_lot_identity": "candidate_id:issue_instance:portfolio_or_identity_id:seed_or_aggregate_replica:draw_or_rank",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return catalog


def bj145_allocation_candidate_registry() -> list[dict[str, object]]:
    """Deduplicate #145's complete selector×allocator candidates pre-outcome.

    #145 carries an arm-specific selection trace in every plan row: #151 for
    PRIMARY_NO_GATE_K4 and #137 for SECONDARY_ESP300_GM290_K8.  It is not an
    allocator-only splice.  A candidate is a frozen (arm, weight source,
    mechanism, repeat cap) family; M and nuisance seed remain a declared
    within-family curve selected only by :func:`m_selection_contract`.
    """
    source = SOURCE_145
    arm_sources = {
        "PRIMARY_NO_GATE_K4": (SOURCE_151, "bj151_gate_a_preoutcome_v1", "candidate_identities.csv.gz", "NO_GATE", 4),
        "SECONDARY_ESP300_GM290_K8": (SOURCE_137, "bj137_gate_a_preoutcome_v2", "n7_identities.csv.gz", "ESP300_GM290", 8),
    }
    selector_rows: dict[str, dict[tuple[str, str], list[dict[str, str]]]] = {}
    for arm, (path, _, identity_file, _, _) in arm_sources.items():
        grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
        for identity in read_csv_gzip(path / identity_file):
            grouped.setdefault((identity["issue_instance"], identity["gate_id"]), []).append(identity)
        selector_rows[arm] = grouped
    plans = read_csv_gzip(source / "allocation_plan.csv.gz")
    support_rows: dict[str, list[dict[str, str]]] = {arm: [] for arm in arm_sources}
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in plans:
        arm = row["arm_id"]
        if arm not in arm_sources:
            raise RuntimeError(f"unknown #145 arm: {arm}")
        _, expected_package, _, gate_id, top_k = arm_sources[arm]
        if row["source_package"] != f"results/{expected_package}" or row["gate_id"] != gate_id:
            raise RuntimeError(f"#145 arm/source mismatch: {arm} {row['plan_id']}")
        if row["selection_status"] == "AVAILABLE":
            identities = selector_rows[arm].get((row["issue_instance"], gate_id), [])
            identities = sorted(identities, key=lambda identity: int(identity["participation_rank"]))[:top_k]
            selected = [identity["portfolio_id"] for identity in identities]
            if len(selected) != int(row["selected_identity_count"]) or canonical_hash(selected) != row["selected_portfolio_ids_sha256"]:
                raise RuntimeError(f"#145 selector identity join failed: {arm} {row['plan_id']}")
        support_rows[arm].append({
            "issue_instance": row["issue_instance"],
            "selection_status": row["selection_status"],
            "selected_identity_count": row["selected_identity_count"],
            "selected_portfolio_ids_sha256": row["selected_portfolio_ids_sha256"],
        })
        if row["selection_status"] != "AVAILABLE":
            continue
        key = (row["arm_id"], row["weight_source"], row["mechanism"], row["cap"])
        groups.setdefault(key, []).append(row)
    support_hashes = {
        arm: canonical_hash(sorted({canonical_hash(row) for row in arm_rows}))
        for arm, arm_rows in support_rows.items()
    }
    result: list[dict[str, object]] = []
    for key, rows in sorted(groups.items()):
        arm, weight_source, mechanism, cap = key
        candidate_id = "BJ145_" + "_".join(
            value.replace("_", "-") for value in key
        )
        m_grid = sorted({int(row["M"]) for row in rows})
        seeds = sorted({row["seed"] for row in rows})
        issues = sorted({row["issue_instance"] for row in rows})
        plan_ids = sorted(row["plan_id"] for row in rows)
        # FULL does not depend on an upstream weight vector.  Retain one
        # canonical family and label the remaining weight-source aliases, so
        # the Stage-4 frontier never manufactures duplicate FULL controls.
        economic_key = (arm, "FULL_ENUMERATED", "NA") if mechanism == "FULL_ENUMERATED" else key
        _, source_name, identity_file, gate_id, top_k = arm_sources[arm]
        result.append(
            {
                "candidate_id": candidate_id,
                "economic_key": "|".join(economic_key),
                "source_package": "bj145_gate_a_preoutcome_v8",
                "selector_source_package": source_name,
                "selector_identity_file": identity_file,
                "selector_gate_id": gate_id,
                "selector_top_k": top_k,
                "source_plan_file": "allocation_plan.csv.gz",
                "source_identity_file": "identity_catalog.csv.gz",
                "source_plan_payload_sha256": sha256_file(source / "allocation_plan.csv.gz"),
                "source_identity_payload_sha256": sha256_file(source / "identity_catalog.csv.gz"),
                "arm_id": arm,
                "weight_source": weight_source,
                "mechanism": mechanism,
                "cap": cap,
                "available_M_grid": ";".join(str(value) for value in m_grid),
                "available_M_grid_sha256": canonical_hash(m_grid),
                "fixed_m_comparator": min(m_grid),
                "seed_scope": ";".join(seeds),
                "issue_instance_count": len(issues),
                "support_348_hash": support_hashes[arm],
                "plan_row_count": len(rows),
                "plan_id_set_sha256": canonical_hash(plan_ids),
                "support_adapter": "unique exact arm-specific selector join validated at Gate A by (arm_id, issue_instance, gate_id, participation_rank<=top_k, selected_portfolio_ids_sha256); Gate B must fail closed on any mismatch",
                "native_ticket_identity": "#145 accepted frozen allocation engine + plan_id + selected_portfolio_ids_sha256 + mechanism/cap/M/seed; repeats are independent ¥2 tax lots",
                "ticket_prefix_rule": "WHOLE_NATIVE_OR_NO_BET_PENDING_MECHANISM_SPECIFIC_NESTED_PREFIX_PROOF",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    canonical: dict[str, str] = {}
    for row in result:
        canonical.setdefault(str(row["economic_key"]), str(row["candidate_id"]))
        row["economic_decision"] = (
            "ELIGIBLE_COMPLETE_NONREDUNDANT"
            if canonical[str(row["economic_key"])] == row["candidate_id"]
            else "DUPLICATE_ECONOMIC_IDENTITY"
        )
        row["canonical_candidate_id"] = canonical[str(row["economic_key"])]
    return result


def _m_values(value: object) -> set[int]:
    return {int(item) for item in str(value).split(";") if item}


ROLE_VECTOR_FIELDS = (
    "gate_id", "portfolio_id", "issue", "fold", "year", "issue_instance",
    "match_id", "match_idx", "kickoff_ts", "selection_rank", "is_candidate",
    "e_sp", "p_min", "predicted_sp3", "predicted_sp1", "predicted_sp0",
    "p_model3", "p_model1", "p_model0", "p_market_raw3", "p_market_raw1",
    "p_market_raw0", "p_market_cal3", "p_market_cal1", "p_market_cal0",
    "p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0", "p_blend_a50_3",
    "p_blend_a50_1", "p_blend_a50_0", "p_blend_a75_3", "p_blend_a75_1",
    "p_blend_a75_0", "q_weight3", "q_weight1", "q_weight0",
    "p_min_delete_match_id", "p_min_delete_code", "q_min_delete_match_id",
    "q_min_delete_code",
)


def role_vector_digest(rows: Sequence[dict[str, str]]) -> str:
    """Digest the source-role namespace and all purchase-relevant values."""
    if len(rows) != 7:
        raise RuntimeError(f"expected seven role rows, got {len(rows)}")
    canonical_rows: list[dict[str, str]] = []
    for row in sorted(rows, key=lambda value: int(value["selection_rank"])):
        missing = [field for field in ROLE_VECTOR_FIELDS if field not in row]
        if missing:
            raise RuntimeError(f"role vector missing fields: {missing}")
        canonical_rows.append({field: row[field] for field in ROLE_VECTOR_FIELDS})
    return canonical_hash(canonical_rows)


def primary_k4_role_evidence() -> tuple[int, str, str, str]:
    """Prove #145 PRIMARY Q uses #151's exact role namespace/vector.

    A sampler plan can agree while the underlying probability role vector
    drifts.  This check binds each seven-leg vector and the frozen #145
    allocation/RNG implementation before cross-catalog aliasing is allowed.
    """
    b151: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in read_csv_gzip(SOURCE_151 / "candidate_role_vectors.csv.gz"):
        if row["gate_id"] == "NO_GATE":
            b151.setdefault((row["issue_instance"], row["portfolio_id"]), []).append(row)
    b145: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in read_csv_gzip(SOURCE_145 / "role_vectors.csv.gz"):
        if (
            row["arm_id"] == "PRIMARY_NO_GATE_K4"
            and row["source_package"] == "results/bj151_gate_a_preoutcome_v1"
            and row["gate_id"] == "NO_GATE"
            and row["top_k_id"] == "K4"
        ):
            b145.setdefault((row["issue_instance"], row["portfolio_id"]), []).append(row)
    evidence: list[dict[str, str]] = []
    for key, b145_rows in sorted(b145.items()):
        b151_rows = b151.get(key)
        if b151_rows is None:
            raise RuntimeError(f"#145 role vector absent from #151: {key}")
        left, right = role_vector_digest(b145_rows), role_vector_digest(b151_rows)
        if left != right:
            raise RuntimeError(f"#145/#151 role vector mismatch: {key}")
        evidence.append({
            "issue_instance": key[0],
            "portfolio_id": key[1],
            "role_vector_sha256": left,
            "bj145_source_role_sha256": canonical_hash(
                sorted(row["source_role_sha256"] for row in b145_rows)
            ),
        })
    if not evidence:
        raise RuntimeError("empty #145/#151 role-vector overlap")
    binding = json.loads((SOURCE_145 / "allocation_binding.json").read_text())
    engine_sha = sha256_file(SOURCE_145 / str(binding["module_file"]))
    if engine_sha != str(binding["module_sha256"]):
        raise RuntimeError("#145 allocation/RNG implementation hash drift")
    return (
        len(evidence),
        canonical_hash(evidence),
        engine_sha,
        sha256_file(SOURCE_145 / "allocation_binding.json"),
    )


def _primary_k4_overlap_evidence(
    allocation: dict[str, object], b151_candidate: str
) -> tuple[int, str, list[int], str, str]:
    """Prove the #145 PRIMARY Q rows are #151 ticket-stream aliases.

    The two Gate-A packages have different plan identifiers, so plan-id
    inequality is not economic independence.  Their exact purchase-relevant
    inputs must agree on every common (issue, M, seed) row: selector identity,
    ticket mechanism, draw count and stake.  The non-overlapping #145 M values
    extend the canonical family's frozen M curve rather than creating another
    portfolio sleeve.
    """
    mechanism = str(allocation["mechanism"])
    source_mechanism = {
        "WR_DUPLICATE_STAKE": "Q_INFORMED_WR_DUPLICATE_STAKE",
        "WOR_DISTINCT": "Q_INFORMED_WOR_DISTINCT",
    }.get(mechanism)
    if source_mechanism is None:
        raise ValueError(f"not a #151 overlap mechanism: {mechanism}")
    b151_rows = {
        (row["issue_instance"], row["M"], row["seed"]): row
        for row in read_csv(SOURCE_151 / "sampling_plan.csv")
        if row["ticket_mechanism"] == source_mechanism
        and row["gate_id"] == "NO_GATE"
        and row["top_k_id"] == "K4"
    }
    b145_rows = [
        row
        for row in read_csv_gzip(SOURCE_145 / "allocation_plan.csv.gz")
        if row["arm_id"] == "PRIMARY_NO_GATE_K4"
        and row["weight_source"] == "Q_WEIGHT"
        and row["mechanism"] == mechanism
        and row["selection_status"] == "AVAILABLE"
    ]
    common_m = sorted(_m_values(allocation["available_M_grid"]) & {
        int(row["M"]) for row in b151_rows.values()
    })
    evidence: list[dict[str, str]] = []
    for row in b145_rows:
        if int(row["M"]) not in common_m:
            continue
        key = (row["issue_instance"], row["M"], row["seed"])
        source = b151_rows.get(key)
        if source is None:
            raise RuntimeError(f"missing #151 overlap source row: {key}")
        fields = (
            "selection_status",
            "selected_portfolio_ids_sha256",
            "M",
            "seed",
            "ticket_space_k",
            "planned_draw_count",
            "planned_stake_yuan",
        )
        if any(row[field] != source[field] for field in fields):
            raise RuntimeError(f"#145/#151 economic overlap mismatch: {key}")
        evidence.append({field: row[field] for field in fields} | {
            "issue_instance": row["issue_instance"],
            "source_mechanism": source_mechanism,
            "canonical_candidate_id": b151_candidate,
        })
    if not evidence:
        raise RuntimeError(f"empty #145/#151 overlap evidence: {b151_candidate}")
    role_count, role_digest, engine_sha, binding_sha = primary_k4_role_evidence()
    return len(evidence), canonical_hash(
        sorted(
            evidence,
            key=lambda record: json.dumps(record, sort_keys=True, separators=(",", ":")),
        )
    ), common_m, role_digest, canonical_hash(
        {
            "role_vector_record_count": role_count,
            "allocator_engine_sha256": engine_sha,
            "allocator_rng_binding_sha256": binding_sha,
        }
    )


def economic_family_registry(
    expanded: list[dict[str, object]], allocation_candidates: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Bind all complete sources to distinct purchasable economic families."""
    records: list[dict[str, object]] = []
    for sleeve, _, _, _ in SLEEVES:
        records.append({
            "candidate_id": sleeve,
            "economic_family_id": f"ECON_{sleeve}",
            "canonical_candidate_id": sleeve,
            "source_kind": "H1_FIXED",
            "available_M_grid": "2187" if sleeve == "BEST_FULL_FULL" else "512" if sleeve.startswith("MODEL_") else "192",
            "source_decision": "ELIGIBLE_COMPLETE_NONREDUNDANT",
            "family_status": "CANONICAL_PRIMARY_FRONTIER",
            "exact_overlap_status": "UNIQUE_ECONOMIC_FAMILY",
            "exact_overlap_evidence_sha256": "",
            "exact_overlap_record_count": 0,
        })
    for family in expanded:
        candidate_id = str(family["candidate_id"])
        records.append({
            "candidate_id": candidate_id,
            "economic_family_id": f"ECON_{candidate_id}",
            "canonical_candidate_id": candidate_id,
            "source_kind": "EXPANDED_COMPLETE",
            "available_M_grid": family["available_M_grid"],
            "source_decision": "ELIGIBLE_COMPLETE_NONREDUNDANT",
            "family_status": "CANONICAL_PRIMARY_FRONTIER",
            "exact_overlap_status": "UNIQUE_ECONOMIC_FAMILY",
            "exact_overlap_evidence_sha256": "",
            "exact_overlap_record_count": 0,
        })
    for candidate in allocation_candidates:
        candidate_id = str(candidate["candidate_id"])
        canonical = str(candidate["canonical_candidate_id"])
        records.append({
            "candidate_id": candidate_id,
            "economic_family_id": f"ECON_{canonical}",
            "canonical_candidate_id": canonical,
            "source_kind": "BJ145_ALLOCATION",
            "available_M_grid": candidate["available_M_grid"],
            "source_decision": candidate["economic_decision"],
            "family_status": "CANONICAL_PRIMARY_FRONTIER" if candidate_id == canonical else "INTERNAL_ALLOCATION_ALIAS_EXCLUDED",
            "exact_overlap_status": "UNIQUE_WITHIN_BJ145" if candidate_id == canonical else "BJ145_INTERNAL_ALIAS",
            "exact_overlap_evidence_sha256": "",
            "exact_overlap_record_count": 0,
        })
    by_candidate = {str(row["candidate_id"]): row for row in records}
    for mechanism, b151_candidate in (
        ("WR_DUPLICATE_STAKE", "BJ151_NOGATE_K4_WR_DENSE_M"),
        ("WOR_DISTINCT", "BJ151_NOGATE_K4_WOR_DENSE_M"),
    ):
        aliases = [
            candidate
            for candidate in allocation_candidates
            if candidate["arm_id"] == "PRIMARY_NO_GATE_K4"
            and candidate["weight_source"] == "Q_WEIGHT"
            and candidate["mechanism"] == mechanism
        ]
        if len(aliases) != 1:
            raise RuntimeError(f"expected one #145 primary Q overlap alias: {mechanism}")
        alias = aliases[0]
        count, digest, common_m, role_digest, allocator_digest = _primary_k4_overlap_evidence(alias, b151_candidate)
        canonical_record = by_candidate[b151_candidate]
        family_id = str(canonical_record["economic_family_id"])
        alias_record = by_candidate[str(alias["candidate_id"])]
        alias_record.update({
            "economic_family_id": family_id,
            "canonical_candidate_id": b151_candidate,
            "family_status": "EXACT_CROSS_CATALOG_ALIAS_EXCLUDED",
            "exact_overlap_status": "EXACT_BJ151_PRIMARY_Q_K4_ALIAS",
            "exact_overlap_evidence_sha256": digest,
            "exact_overlap_record_count": count,
            "common_M_grid": ";".join(str(value) for value in common_m),
            "source_role_vector_evidence_sha256": role_digest,
            "allocator_rng_identity_sha256": allocator_digest,
        })
        canonical_record.update({
            "exact_overlap_status": "CANONICAL_WITH_BJ145_PRIMARY_Q_K4_ALIAS",
            "exact_overlap_evidence_sha256": digest,
            "exact_overlap_record_count": count,
            "source_role_vector_evidence_sha256": role_digest,
            "allocator_rng_identity_sha256": allocator_digest,
        })
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in records:
        grouped.setdefault(str(row["economic_family_id"]), []).append(row)
    for family_id, members in grouped.items():
        union_m = sorted({m for row in members for m in _m_values(row["available_M_grid"])})
        member_ids = sorted(str(row["candidate_id"]) for row in members)
        canonical = next(
            row for row in members if row["candidate_id"] == row["canonical_candidate_id"]
        )
        for row in members:
            row["family_member_candidate_ids_sha256"] = canonical_hash(member_ids)
            row["family_union_M_grid"] = ";".join(str(value) for value in union_m)
            row["family_union_M_grid_sha256"] = canonical_hash(union_m)
            row["pairwise_and_k_rule"] = (
                "same economic_family_id rows are aliases: only canonical_candidate_id "
                "may enter primary pairwise/higher-order/K frontier; aliases remain "
                "lineage/reproduction diagnostics and cannot add stake or multiplicity"
            )
            row["canonical_candidate_id"] = canonical["candidate_id"]
            row.setdefault("common_M_grid", "")
            row.setdefault("source_role_vector_evidence_sha256", "")
            row.setdefault("allocator_rng_identity_sha256", "")
    return sorted(records, key=lambda row: str(row["candidate_id"]))


def m_selection_contract(expanded: list[dict[str, object]]) -> dict[str, object]:
    return {
        "selection_scope": "each family independently; complete chronological calendar; current issue and all future outcomes forbidden",
        "minimum_prior_active_issues": 52,
        "training_score": "prior-only aggregate pre-tax net / prior-only aggregate actual stake on the family native support; blank/zero-stake M values cannot win",
        "tie_break": "higher score, then lower M, then candidate_id lexicographic, then frozen seed-aggregate id",
        "fallback": "before 52 active observations use fixed_m_comparator; never select by full-sample ROI, winning year, payout, or test-period result",
        "seed_rule": "arithmetic seed mean is permitted only in strictly-prior training to select M. Gate-B deployment never averages payouts/stakes before capital allocation: it replays each frozen seed path as a separate complete bankroll state machine and reports the across-seed distribution. No seed may be selected from outcomes; an all-seed purchase is allowed only with explicit multiplied stake.",
        "fixed_m_comparator": [
            {
                "candidate_id": row["candidate_id"],
                "M": row["fixed_m_comparator"],
                "available_M_grid": row["available_M_grid"],
            }
            for row in expanded
        ],
        "all_M_curve": "publish every available M in available_M_grid on the exact source support; dynamic path and fixed-M comparator are both mandatory",
        "nested_loyo_sensitivity": "for each held-out year, re-run the same selector on earlier years only; if no earlier 52-active history exists use fixed_m_comparator",
    }


def replicate_bundle_registry(
    expanded: list[dict[str, object]],
    allocation_candidates: list[dict[str, object]],
    economic_families: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Freeze cross-sleeve stochastic deployment pairing before outcomes.

    Bundle ordinal is an ex ante nuisance replicate, never an optimisation
    dimension.  Each stochastic family cycles through its own sorted frozen
    seed scope; deterministic families use the literal DETERMINISTIC token.
    A portfolio must replay every selected bundle separately and only then
    report a nonselectable bundle distribution.
    """
    sources = {
        str(row["candidate_id"]): row for row in expanded + allocation_candidates
    }
    canonical = sorted(
        {
            str(row["canonical_candidate_id"])
            for row in economic_families
            if row["family_status"] != "EXACT_CROSS_CATALOG_ALIAS_EXCLUDED"
        }
    )
    seed_scopes: dict[str, list[str]] = {}
    for candidate_id in canonical:
        source = sources.get(candidate_id)
        raw = str(source.get("seed_scope", "NA")) if source else "NA"
        values = sorted(value for value in raw.split(";") if value and value != "NA")
        seed_scopes[candidate_id] = values or ["DETERMINISTIC"]
    count = max(len(values) for values in seed_scopes.values())
    rows: list[dict[str, object]] = []
    for ordinal in range(1, count + 1):
        mapping = {
            candidate_id: seeds[(ordinal - 1) % len(seeds)]
            for candidate_id, seeds in sorted(seed_scopes.items())
        }
        rows.append(
            {
                "deployment_replicate_bundle_id": f"BUNDLE_ORDINAL_{ordinal:03d}",
                "bundle_ordinal": ordinal,
                "candidate_seed_map_json": json.dumps(mapping, sort_keys=True, separators=(",", ":")),
                "candidate_seed_map_sha256": canonical_hash(mapping),
                "economic_family_count": len(mapping),
                "composition_rule": "ordinal pairing over each family sorted frozen seed scope; deterministic sleeves map to DETERMINISTIC",
                "support_rule": "a portfolio uses exactly this map for all included stochastic sleeves; missing/unavailable member makes that bundle issue row explicit NO_BET/UNAVAILABLE, never a loss or substituted seed",
                "aggregation_rule": "all bundle paths are replayed separately; distributions are reported after complete state-machine replay and no bundle is selectable",
            }
        )
    return rows


def eligibility_ledger(
    expanded: list[dict[str, object]] | None = None,
    allocation_candidates: list[dict[str, object]] | None = None,
    economic_families: list[dict[str, object]] | None = None,
) -> list[dict[str, str]]:
    expanded = expanded or expanded_sleeve_catalog()
    allocation_candidates = allocation_candidates or bj145_allocation_candidate_registry()
    economic_families = economic_families or economic_family_registry(
        expanded, allocation_candidates
    )
    rows = [
        {
            "candidate_id": sleeve,
            "source_package": "bj170_gate_a_preoutcome_v2",
            "identity_source": "identity_freeze.csv.gz + identity_allocation_digest.csv.gz",
            "inherited_M_seed_support": "M fixed by arm; deterministic/no-seed as declared",
            "decision": "ELIGIBLE_COMPLETE_NONREDUNDANT",
            "frontier_role": "LOCKED_RETROSPECTIVE_REPRODUCTION_SLEEVE",
            "reason": "complete frozen Stage-1→3 selection/direction/ticket trace; exact requested tickets and M bound",
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        for sleeve, _, _, _ in SLEEVES
    ]
    rows.extend(
        {
            "candidate_id": str(family["candidate_id"]),
            "source_package": str(family["source_package"]),
            "identity_source": f"{family['identity_file']} + {family['role_file']} + {family['plan_file']}",
            "inherited_M_seed_support": f"M={family['available_M_grid']}; {family['seed_aggregation']}",
            "decision": "ELIGIBLE_COMPLETE_NONREDUNDANT",
            "frontier_role": str(family["frontier_role"]),
            "reason": "complete outcome-unexposed identity, seven-role vector, sampler plan, M grid, replicate aggregation and deterministic ticket/tax-lot identity rule are materialized in executable_sleeve_family_catalog.csv",
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        for family in expanded
    )
    rows.extend(
        {
            "candidate_id": str(candidate["candidate_id"]),
            "source_package": (
                "bj145_gate_a_preoutcome_v8 + "
                f"{candidate['selector_source_package']}"
            ),
            "identity_source": (
                "allocation_plan.csv.gz + identity_catalog.csv.gz; "
                f"{candidate['selector_source_package']}/"
                f"{candidate['selector_identity_file']} selector adapter"
            ),
            "inherited_M_seed_support": f"M={candidate['available_M_grid']}; seed={candidate['seed_scope']}",
            "decision": str(candidate["economic_decision"]),
            "frontier_role": "COMPLETE_ALLOCATION_FAMILY" if candidate["economic_decision"] == "ELIGIBLE_COMPLETE_NONREDUNDANT" else "DUPLICATE_ALLOCATION_ALIAS",
            "reason": (
                "complete outcome-unexposed arm-specific selector trace is "
                "referenced by every #145 plan row and exact-joined on "
                "(arm_id, issue_instance, gate_id, participation_rank<=top_k); "
                "candidate is deduplicated only by exact pre-outcome economic "
                "ticket identity"
            ),
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        for candidate in allocation_candidates
    )
    rows.extend(
        [
            {
                "candidate_id": "BJ137_COMPLETE_ISSUE_Q_SAMPLING",
                "source_package": "bj137_gate_a_preoutcome_v2",
                "identity_source": "n7_identities.csv.gz + sampler_plan.csv",
                "inherited_M_seed_support": "frozen complete-issue sampling M/seed plan",
                "decision": "DUPLICATE_ECONOMIC_IDENTITY",
                "frontier_role": "LINEAGE_ONLY",
                "reason": "the full #137 primitive surface is represented by the materialized #148/#151 exact descendant pipeline families; it is not independently re-spliced into Stage 4",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ148_DENSE_M_COMMON_SUPPORT_SOURCE",
                "source_package": "bj148_gate_a_preoutcome_v1",
                "identity_source": "common_support_identities.csv.gz + sampling_plan.csv",
                "inherited_M_seed_support": "dense M grid and frozen three-seed sampling plan",
                "decision": "DUPLICATE_ECONOMIC_IDENTITY",
                "frontier_role": "LINEAGE_ONLY",
                "reason": "materialized as BJ148_NOGATE_WR_DENSE_M and BJ148_NOGATE_WOR_DENSE_M; this source row remains provenance, not a duplicate sleeve",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ151_FIXED_CANDIDATE_REPRODUCTION_SOURCE",
                "source_package": "bj151_gate_a_preoutcome_v1",
                "identity_source": "candidate_identities.csv.gz + sampling_plan.csv",
                "inherited_M_seed_support": "fixed candidate dense-M plus frozen seed plan",
                "decision": "DUPLICATE_ECONOMIC_IDENTITY",
                "frontier_role": "LINEAGE_ONLY",
                "reason": "materialized as BJ151_NOGATE_K4_WR_DENSE_M and BJ151_NOGATE_K4_WOR_DENSE_M; this source row remains provenance, not a duplicate sleeve",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ159_SELECTED_WOR_N2_N10_SOURCE",
                "source_package": "bj159_gate_a_preoutcome_v2r1",
                "identity_source": "identity_catalog.csv.gz + sampling_plan.csv",
                "inherited_M_seed_support": "N2–N10, M={32,64,128}, seeds 137001–137003",
                "decision": "DUPLICATE_ECONOMIC_IDENTITY",
                "frontier_role": "LINEAGE_ONLY",
                "reason": "N=7 is materialized as BJ159_SELECTED_N7_WOR_M_CURVE; N≠7 has a different ticket space and is outside the N7-only issue contract",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ167_SELECTOR_ALLOCATION_ATLAS",
                "source_package": "bj167_gate_a_strategy_atlas_v3r1",
                "identity_source": "selector_identities shards + allocation_grid.csv",
                "inherited_M_seed_support": "full frozen selector/allocation M/seed/support surface",
                "decision": "SEMANTICS_OR_M_CURVE_ONLY",
                "frontier_role": "AUTHORITATIVE_SHORTLIST_SOURCE",
                "reason": "the broad atlas supplies selector/allocation semantics, while Gate A retains only complete trace descendants listed in the executable catalog; no outcome-ranked atlas cell becomes eligible by default",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ176_THREE_SLEEVE_RISK_BRIDGE",
                "source_package": "bj176_issue_equity_risk_v1",
                "identity_source": "three fixed #170 sleeves only",
                "inherited_M_seed_support": "BEST_FULL/FULL, MODEL/M512, Q/M192",
                "decision": "DUPLICATE_ECONOMIC_IDENTITY",
                "frontier_role": "RISK_BASELINE_BRIDGE",
                "reason": "accepted settled risk convention bridge, not an independently selected sleeve",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ190_SPARSE_DIVERGENCE",
                "source_package": "bj190_gate_b_sparse_divergence_v1",
                "identity_source": "terminal identity only",
                "inherited_M_seed_support": "as terminal package",
                "decision": "INCOMPLETE_STAGE1_3_TRACE",
                "frontier_role": "EXCLUDED",
                "reason": "the Gate-A sparse selector/direction records do not include an accepted complete ticket-construction trace on the #192 common calendar; terminal return is not used as an eligibility reason",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ193_FULL_DYNAMIC_CHAIN",
                "source_package": "bj193_gate_b_regime_meta_policy_v2",
                "identity_source": "terminal identity only",
                "inherited_M_seed_support": "as terminal package",
                "decision": "INCOMPLETE_STAGE1_3_TRACE",
                "frontier_role": "EXCLUDED",
                "reason": "the accepted interface package records action compatibility but does not provide an immutable per-issue executable ticket/tax-lot trace for one fixed Stage-1→3 sleeve; terminal return is not used as an eligibility reason",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
        ]
    )
    family_by_candidate = {
        str(family["candidate_id"]): family for family in economic_families
    }
    for row in rows:
        family = family_by_candidate.get(row["candidate_id"])
        if family is None:
            row["economic_family_id"] = "NOT_A_PRIMARY_ECONOMIC_FAMILY"
            row["canonical_candidate_id"] = row["candidate_id"]
            row["economic_family_frontier_status"] = "LINEAGE_OR_EXCLUDED"
            row["economic_family_overlap_evidence_sha256"] = ""
        else:
            row["economic_family_id"] = str(family["economic_family_id"])
            row["canonical_candidate_id"] = str(family["canonical_candidate_id"])
            row["economic_family_frontier_status"] = str(family["family_status"])
            row["economic_family_overlap_evidence_sha256"] = str(
                family["exact_overlap_evidence_sha256"]
            )
    return rows


def baseline_registry() -> list[dict[str, object]]:
    return [
        {
            "baseline_id": "B167_BEST_FULL_NATIVE_LADDER_HEAD",
            "source_package": "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
            "source_gate_a_binding": "bj167_gate_a_strategy_atlas_v3r1",
            "source_gate_b_binding": "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
            "identity": "BEST_FULL/FULL_ENUMERATED",
            "support_context": "NATIVE_BEST_FULL",
            "pre_tax_roi": -0.0947,
            "role": "ACCEPTED_LADDER_HEAD_CONTEXT",
            "comparison_rule": "context only; never substitute for exact matched-support lift",
        },
        {
            "baseline_id": "B170_BEST_FULL_THREE_WAY_BRIDGE",
            "source_package": "bj170_gate_b_selector_allocator_stack_v1",
            "source_gate_a_binding": "bj170_gate_a_preoutcome_v2",
            "source_gate_b_binding": "bj170_gate_b_selector_allocator_stack_v1",
            "identity": "BEST_FULL/FULL_ENUMERATED",
            "support_context": "THREE_WAY_ALL",
            "pre_tax_roi": -0.0909,
            "role": "EXACT_THREE_WAY_MATCHED_BRIDGE",
            "comparison_rule": "candidate and control must share exact issue support, capital mode, fraction, preissue bankroll and actual funding convention",
        },
        {
            "baseline_id": "MATCHED_STRONGEST_STANDALONE",
            "source_package": "GATE_B_DERIVED",
            "source_gate_a_binding": "GATE_A_FROZEN_SOURCE_BINDINGS",
            "source_gate_b_binding": "GATE_B_DERIVED",
            "identity": "max standalone on candidate exact support",
            "support_context": "CANDIDATE_EXACT_SUPPORT",
            "pre_tax_roi": "DERIVED_GATE_B",
            "role": "MANDATORY_MATCHED_CONTROL",
            "comparison_rule": "candidate-minus-control published with absolute metrics",
        },
        {
            "baseline_id": "MATCHED_EQUAL_WEIGHT",
            "source_package": "GATE_B_DERIVED",
            "source_gate_a_binding": "GATE_A_FROZEN_SOURCE_BINDINGS",
            "source_gate_b_binding": "GATE_B_DERIVED",
            "identity": "same sleeves, equal weights",
            "support_context": "CANDIDATE_EXACT_SUPPORT",
            "pre_tax_roi": "DERIVED_GATE_B",
            "role": "MANDATORY_MATCHED_CONTROL",
            "comparison_rule": "candidate-minus-control published with absolute metrics",
        },
    ]


def frontier_contract(
    eligibility: list[dict[str, str]], economic_families: list[dict[str, object]]
) -> dict[str, object]:
    """Define the complete, immutable Gate-B sleeve frontier without settling it.

    A historical source-family row is lineage evidence, not permission to reopen
    an upstream search.  The three #170 paths remain the locked retrospective
    H1 panel; independently complete #148/#151/#159 families add their full
    predeclared M curves without selecting an outcome-ranked atlas cell.
    """
    eligible_source = {
        row["candidate_id"]
        for row in eligibility
        if row["decision"] == "ELIGIBLE_COMPLETE_NONREDUNDANT"
    }
    canonical_families = [
        row
        for row in economic_families
        if row["candidate_id"] == row["canonical_candidate_id"]
        and any(
            member["candidate_id"] in eligible_source
            and member["economic_family_id"] == row["economic_family_id"]
            for member in economic_families
        )
    ]
    canonical_ids = {str(row["canonical_candidate_id"]) for row in canonical_families}
    h1_ids = [sleeve for sleeve, _, _, _ in SLEEVES]
    complete = [candidate_id for candidate_id in h1_ids if candidate_id in canonical_ids]
    complete.extend(sorted(canonical_ids - set(complete)))
    return {
        "eligible_candidate_sources": complete,
        "eligible_source_count": len(eligible_source),
        "eligible_economic_family_count": len(complete),
        "economic_family_registry": "economic_family_registry.csv",
        "materialization_rule": (
            "Gate B materializes every eligible economic family's frozen union M curve and "
            "strictly-prior M-selection path, then enumerates all pairs across the "
            "subsets. Higher-order combinations are exhaustive for the preregistered "
            "robust shortlist and descriptive elsewhere; no outcome-ranked source cell "
            "may enter after Gate A."
        ),
        "component_rule": (
            "BJ145 is an allocation-engine contract only; it cannot create a new "
            "Stage-4 selector or overwrite a retained complete pipeline tuple."
        ),
        "comparison_rule": (
            "Each portfolio row includes absolute pre-tax capital/path results and "
            "matched lifts to B167/B170 where exact support and funding permit, "
            "strongest standalone on its exact support, and equal-weight same sleeves."
        ),
        "screening_rule": (
            "The full materialized frontier is retrospective/descriptive. Raw rank, "
            "raw Pareto membership or a best descriptive cell cannot be reported as "
            "Edge; a positive same-window result is hypothesis-generating and needs "
            "genuinely held-out/forward validation before any ladder review."
        ),
        "pairwise_surface": [
            [left, right]
            for index, left in enumerate(complete)
            for right in complete[index + 1 :]
        ],
        "robust_higher_order_shortlist": [
            "BEST_FULL_FULL|MODEL_SOURCE_MODEL_CAP1_M512|Q_SOURCE_Q_TOP_MASS_M192",
            "BJ148_NOGATE_WR_DENSE_M|BJ148_NOGATE_WOR_DENSE_M|BJ151_NOGATE_K4_WR_DENSE_M|BJ151_NOGATE_K4_WOR_DENSE_M|BJ159_SELECTED_N7_WOR_M_CURVE",
        ],
        "higher_order_rule": "all nonempty subsets of the H1 panel; all nonempty subsets of each robust-shortlist row after prior-only M selection; no post-outcome membership choice. Same-economic-family aliases are excluded before pairing/K enumeration and remain lineage/reproduction diagnostics only.",
        "portfolio_k_saturation": "for every ordered robust shortlist, publish K=1..len(shortlist) equal-weight and each prior-only allocator path; report marginal candidate-minus-K-1 capital, risk, covariance, HHI and retained-cash changes. K is never selected by same-window outcomes.",
        "m_curve_and_path_tables": "for each family publish the full frozen M curve, fixed-M comparator, strictly-prior selected-M path, and nested-LOYO selected-M path, separately for each deployment seed path.",
        "excluded_source_records": [
            {
                "candidate_id": row["candidate_id"],
                "decision": row["decision"],
                "reason": row["reason"],
            }
            for row in eligibility
            if row["frontier_role"] == "EXCLUDED"
        ],
        "cross_catalog_aliases": [
            {
                "candidate_id": row["candidate_id"],
                "canonical_candidate_id": row["canonical_candidate_id"],
                "economic_family_id": row["economic_family_id"],
                "overlap_evidence_sha256": row["exact_overlap_evidence_sha256"],
                "overlap_record_count": row["exact_overlap_record_count"],
            }
            for row in economic_families
            if row["family_status"] == "EXACT_CROSS_CATALOG_ALIAS_EXCLUDED"
        ],
    }


def role_product_weights(rows: list[dict[str, str]], source: str) -> list[float]:
    """Expand seven frozen role probabilities into canonical base-3 ticket order."""
    if len(rows) != 7:
        raise RuntimeError("expected exactly seven frozen role rows")
    values = [1.0]
    for role in sorted(rows, key=lambda row: int(row["selection_rank"])):
        values = [
            prior * float(role[f"{source}{code}"])
            for prior in values
            for code in ("3", "1", "0")
        ]
    if len(values) != 2187 or sum(values) <= 0.0:
        raise RuntimeError("invalid frozen seven-leg ticket weights")
    return values


def model_nested_prefix_audit(
    chosen: dict[tuple[str, str, str], dict[str, str]],
    role_by_key: dict[tuple[str, str, str], list[dict[str, str]]],
) -> dict[str, object]:
    """Regenerate MODEL/cap=1 prefixes with the byte-frozen native engine."""
    model_keys = sorted(
        key
        for key, allocation in chosen.items()
        if key[0] == "MODEL_SOURCE"
        and allocation["allocation_arm"] == "MODEL_CAP1_M512"
    )
    allocator = FrozenAllocator()
    try:
        vectors = [role_product_weights(role_by_key[key], "p_model") for key in model_keys]
        try:
            all_ranks = allocator.capped_prefix_ranks_batch(vectors, 512, 1)
        except RuntimeError as error:
            raise RuntimeError(f"MODEL all-M native prefix proof failed: {error}") from error
        rows: list[dict[str, object]] = []
        for key, ranks in zip(model_keys, all_ranks):
            nested = True
            first_failure = ""
            allocation = chosen[key]
            if nested:
                prior = [1 if rank else 0 for rank in ranks]
                digest = hashlib.sha256(
                    json.dumps(prior, separators=(",", ":")).encode()
                ).hexdigest()
                if digest != allocation["counts_sha256"]:
                    raise RuntimeError(
                        "MODEL all-M native digest mismatch: "
                        f"{key[1]}/{key[2]}"
                    )
            rows.append(
                {
                    "issue_instance": key[1],
                    "portfolio_id": key[2],
                    "nested": nested,
                    "first_failure": first_failure,
                    "rank_by_ordinal": ranks,
                    "M512_counts_sha256": allocation["counts_sha256"],
                }
            )
    finally:
        allocator._build.cleanup()
    return {
        "engine_sha256": FROZEN_ALLOCATOR_SHA256,
        "maximum_M": 512,
        "rows": rows,
        "generation": "detached-clone reproducible frozen C++ replay",
    }


def prefix_registry() -> tuple[
    list[dict[str, object]], list[dict[str, object]], dict[str, object]
]:
    """Create executable pre-outcome ticket-prefix and global tax-lot bindings.

    Q's accepted deterministic top-mass source has a nested priority order. FULL
    remains a whole-native block.  MODEL's cap-one allocator remains whole-native
    until an all-M nestedness proof is supplied; this fail-closed disposition
    prevents Stage 4 from choosing an unbound partial ticket set.
    """
    identities = read_csv_gzip(SOURCE_170 / "identity_freeze.csv.gz")
    allocation = read_csv_gzip(SOURCE_170 / "identity_allocation_digest.csv.gz")
    roles = read_csv_gzip(SOURCE_170 / "role_vector_freeze.csv.gz")
    role_by_key: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in roles:
        role_by_key.setdefault(
            (row["selector_alias"], row["issue_instance"], row["portfolio_id"]), []
        ).append(row)
    identity_by_key = {
        (row["selector_alias"], row["issue_instance"], row["portfolio_id"]): row
        for row in identities
    }
    chosen = {
        (row["selector_alias"], row["issue_instance"], row["portfolio_id"]): row
        for row in allocation
        if (row["selector_alias"], row["allocation_arm"])
        in {(alias, arm) for _, alias, arm, _ in SLEEVES}
    }
    audit = model_nested_prefix_audit(chosen, role_by_key)
    if (
        audit.get("engine_sha256") != FROZEN_ALLOCATOR_SHA256
        or audit.get("maximum_M") != 512
    ):
        raise RuntimeError("MODEL nested-prefix audit binding drift")
    model_audit = {
        (row["issue_instance"], row["portfolio_id"]): row for row in audit["rows"]
    }
    expected_model_keys = {
        (issue_instance, portfolio_id)
        for (alias, issue_instance, portfolio_id), row in chosen.items()
        if alias == "MODEL_SOURCE" and row["allocation_arm"] == "MODEL_CAP1_M512"
    }
    if set(model_audit) != expected_model_keys:
        raise RuntimeError("MODEL nested-prefix audit identity coverage drift")
    policy_rows: list[dict[str, object]] = []
    q_orders: dict[str, list[tuple[dict[str, str], list[int], str]]] = {}
    model_orders: dict[str, list[tuple[dict[str, str], list[int], str]]] = {}
    for key, allocation_row in sorted(chosen.items()):
        alias, issue_instance, portfolio_id = key
        identity = identity_by_key[key]
        sleeve_id = next(
            sleeve
            for sleeve, a, arm, _ in SLEEVES
            if a == alias and arm == allocation_row["allocation_arm"]
        )
        mechanism = allocation_row["mechanism"]
        native_m = int(allocation_row["M"])
        if mechanism == "DETERMINISTIC_TOP_MASS":
            weights = role_product_weights(role_by_key[key], "q_weight")
            order = sorted(
                range(2187), key=lambda ordinal: (-weights[ordinal], ordinal)
            )
            prefix = order[:native_m]
            counts = [0] * 2187
            for ordinal in prefix:
                counts[ordinal] += 1
            source_digest = hashlib.sha256(
                json.dumps(counts, separators=(",", ":")).encode()
            ).hexdigest()
            if source_digest != allocation_row["counts_sha256"]:
                raise RuntimeError(
                    f"Q prefix/native digest mismatch: {issue_instance}/{portfolio_id}"
                )
            priority_digest = canonical_hash(prefix)
            q_orders.setdefault(issue_instance, []).append(
                (identity, prefix, priority_digest)
            )
            status = "NESTED_PREFIX_VERIFIED"
            rule = "weight descending, canonical ticket ordinal ascending tie-break"
        elif mechanism == "CAPPED_REPEAT" and allocation_row["cap"] == "1":
            audit_row = model_audit.get((issue_instance, portfolio_id))
            if audit_row and audit_row["nested"]:
                ranks = [int(value) for value in audit_row["rank_by_ordinal"]]
                if len(ranks) != 2187 or sorted(
                    value for value in ranks if value
                ) != list(range(1, 513)):
                    raise RuntimeError("MODEL nested-prefix audit ranks are invalid")
                priority_digest = canonical_hash(ranks)
                status = "NESTED_PREFIX_VERIFIED_M1_TO_M512"
                rule = "accepted frozen CAPPED_REPEAT cap=1 allocation rank at every M=1..512"
                model_orders.setdefault(issue_instance, []).append(
                    (
                        identity,
                        [
                            ordinal
                            for _, ordinal in sorted(
                                (rank, ordinal)
                                for ordinal, rank in enumerate(ranks)
                                if rank
                            )
                        ],
                        priority_digest,
                    )
                )
            else:
                priority_digest = ""
                status = "WHOLE_NATIVE_OR_NO_BET_PENDING_ALL_M_NESTEDNESS_AUDIT"
                rule = "no partial prefix is executable until every M=1..512 native allocation is proven nested"
        elif mechanism == "FULL_ENUMERATED":
            priority_digest = ""
            status = "WHOLE_NATIVE_OR_NO_BET"
            rule = "FULL_ENUMERATED has no partial-FULL semantics"
        else:
            raise RuntimeError(f"unexpected retained allocation mechanism: {mechanism}")
        policy_rows.append(
            {
                "sleeve_id": sleeve_id,
                "issue_instance": issue_instance,
                "portfolio_id": portfolio_id,
                "selector_rank": identity["selector_rank"],
                "mechanism": mechanism,
                "native_M": native_m,
                "native_counts_sha256": allocation_row["counts_sha256"],
                "priority_order_sha256": priority_digest,
                "prefix_status": status,
                "within_identity_rule": rule,
                "accepted_allocator_sha256": allocation_row["allocator_sha256"],
                "tax_lot_rule": "each emitted global ticket rank is one immutable ¥2 tax lot",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    global_rows: list[dict[str, object]] = []
    for issue_instance, members in sorted(q_orders.items()):
        # Round-robin over frozen selector rank, with portfolio id as the stable
        # tie-break.  Every identity keeps its own deterministic top-mass prefix.
        ordered = sorted(
            members,
            key=lambda item: (int(item[0]["selector_rank"]), item[0]["portfolio_id"]),
        )
        rank = 0
        for within_rank in range(1, 193):
            for identity, prefix, priority_digest in ordered:
                rank += 1
                global_rows.append(
                    {
                        "sleeve_id": "Q_SOURCE_Q_TOP_MASS_M192",
                        "issue_instance": issue_instance,
                        "global_ticket_rank": rank,
                        "portfolio_id": identity["portfolio_id"],
                        "within_identity_ticket_rank": within_rank,
                        "ticket_ordinal": prefix[within_rank - 1],
                        "native_multiplicity_unit": 1,
                        "tax_lot_id": f"Q_SOURCE_Q_TOP_MASS_M192:{issue_instance}:{rank}",
                        "priority_order_sha256": priority_digest,
                        "inter_identity_rule": "round_robin(selector_rank,portfolio_id); within identity deterministic top-mass priority",
                        "outcome_boundary": OUTCOME_BOUNDARY,
                    }
                )
    for issue_instance, members in sorted(model_orders.items()):
        if len(members) != 1:
            raise RuntimeError(
                "MODEL retained sleeve must have exactly one identity per issue"
            )
        identity, prefix, priority_digest = members[0]
        for rank, ordinal in enumerate(prefix, 1):
            global_rows.append(
                {
                    "sleeve_id": "MODEL_SOURCE_MODEL_CAP1_M512",
                    "issue_instance": issue_instance,
                    "global_ticket_rank": rank,
                    "portfolio_id": identity["portfolio_id"],
                    "within_identity_ticket_rank": rank,
                    "ticket_ordinal": ordinal,
                    "native_multiplicity_unit": 1,
                    "tax_lot_id": f"MODEL_SOURCE_MODEL_CAP1_M512:{issue_instance}:{rank}",
                    "priority_order_sha256": priority_digest,
                    "inter_identity_rule": "K1 single identity; native CAPPED_REPEAT cap=1 nested rank",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    q_rows = [
        row for row in global_rows if row["sleeve_id"] == "Q_SOURCE_Q_TOP_MASS_M192"
    ]
    if sum(row["native_multiplicity_unit"] for row in q_rows) != sum(
        int(row["native_M"])
        for row in policy_rows
        if row["sleeve_id"] == "Q_SOURCE_Q_TOP_MASS_M192"
    ):
        raise RuntimeError("Q global prefix reconciliation failed")
    return policy_rows, global_rows, audit


def output_schema() -> dict[str, object]:
    """Manifest-covered Gate-B deliverable schema and equations."""
    def path_key(*suffix: str) -> list[str]:
        return [*PATH_IDENTITY, *suffix]
    return {
        "issue_ledger": {
            "key": path_key("calendar_index", "issue_instance"),
            "fields": [
                "preissue_bankroll_yuan",
                "normalization_method",
                "normalization_status",
                "ex_ante_volatility",
                "target_volatility",
                "realized_capital_multiplier",
                "risk_budget_yuan",
                "pre_normalization_mode_notional_yuan",
                "normalized_mode_notional_yuan",
                "mode_notional_yuan",
                "issue_budget_yuan",
                "requested_stake_yuan",
                "actual_stake_yuan",
                "scaled_stake_yuan",
                "skipped_stake_yuan",
                "retained_cash_yuan",
                "reason_codes",
                "pre_tax_gross_yuan",
                "pre_tax_net_yuan",
                "tax_yuan",
                "postissue_bankroll_yuan",
                "ruin_flag",
            ],
            "formulas": [
                "actual_stake=sum(actual ticket count)×¥2",
                "normalization follows normalization_contract.json before weights/budget/integer funding; multiplier is <=1 and all fallbacks are explicit",
                "for a prefix-executable sleeve, funded_prefix_length is the actual allocated global ticket count and funded_tax_lot_sha256=SHA256(canonical ordered tax_lot_id list for ranks 1..length); for WHOLE_NATIVE_OR_NO_BET, length is native ticket count or zero and digest binds the entire inherited native allocation digest or an empty canonical list",
                "a nonzero FULL_ENUMERATED allocation must equal its complete native count; partial FULL is a Gate-B fail-closed error",
                "postissue_bankroll=preissue_bankroll+pre_tax_net",
                "turnover=cumulative actual_stake",
                "all sleeve flows in an issue fund concurrently",
            ],
        },
        "sleeve_funding_ledger": {
            "key": path_key("calendar_index", "issue_instance", "sleeve_id"),
            "fields": ["requested_native_ticket_count", "actual_ticket_count", "funded_prefix_length", "funded_global_rank_start", "funded_global_rank_end", "funded_ticket_list_sha256", "funded_tax_lot_sha256", "prefix_execution_status", "atomic_or_no_bet_reason", "actual_stake_yuan"],
            "formulas": ["one row per sleeve; (portfolio issue actual_stake)=sum(sleeve funding actual_stake) exactly", "WHOLE_NATIVE_OR_NO_BET requires actual_ticket_count in {0, requested_native_ticket_count}; otherwise fail closed", "a prefix row must reference its manifest-covered issue-global ordered tax-lot stream"],
        },
        "capital_summary": {
            "key": path_key(),
            "fields": [
                "starting_bankroll_yuan",
                "ending_bankroll_yuan",
                "minimum_bankroll_yuan",
                "minimum_required_start_yuan",
                "fundable_issue_count",
                "first_unfundable_issue",
                "scaled_stake_yuan",
                "skipped_stake_yuan",
                "cash_yuan",
                "turnover_yuan",
                "pre_tax_roi",
                "tax_adjusted_roi",
                "cumulative_pre_tax_roi",
                "capital_growth",
                "capital_turnover",
                "capital_growth_audit_delta",
                "ruin_flag",
            ],
            "formulas": [
                "minimum_bankroll=min(preissue_bankroll,postissue_bankroll) over full 348 calendar",
                "minimum_required_start is smallest b found by deterministic integer-yuan bisection only for NATIVE_REQUEST_CONTROL and FIXED_100K_NOTIONAL, whose requested ticket capacities are independent of b; blank/NOT_MONOTONE for COMPOUNDING_BANKROLL",
                "ruin_flag=1 iff any postissue_bankroll < ¥2 while a positive native request exists",
                "pre_tax_roi=sum(pre_tax_net)/sum(actual_stake); blank if zero actual stake",
                "capital_growth=ending_bankroll_yuan/100000-1; capital_turnover=turnover_yuan/100000; for FIXED_100K_NOTIONAL capital_growth=cumulative_pre_tax_roi×capital_turnover and capital_growth_audit_delta is that difference",
            ],
        },
        "weight_history": {
            "key": path_key("calendar_index", "issue_instance", "sleeve_id"),
            "fields": [
                "portfolio_id",
                "issue_instance",
                "weight_method",
                "sleeve_id",
                "weight",
                "history_active_observation_count",
                "estimator_status",
                "fallback_reason",
                "covariance_hash",
            ],
            "formulas": [
                "weights use only issues strictly before issue_instance",
                "fallback_rate=count(non-primary estimator_status)/348",
                "NO_BET/unavailable excluded from active observation but retained as capital zero flow",
            ],
        },
        "dependence": {
            "key": path_key("sleeve_left", "sleeve_right"),
            "fields": [
                "portfolio_id",
                "sleeve_left",
                "sleeve_right",
                "prior_covariance",
                "prior_correlation",
                "pearson_correlation",
                "spearman_rank_correlation",
                "rolling_correlation_20",
                "payout_overlap_count",
                "hit_overlap_count",
                "contribution_hhi",
                "downside_correlation",
                "tail_co_loss_count",
                "full_calendar_zero_flow_count",
                "union_active_count",
                "intersection_active_count",
                "full_calendar_joint_loss_rate",
                "union_active_joint_loss_rate",
                "intersection_active_joint_loss_rate",
                "concurrent_issue_count",
                "portfolio_pnl_reconciliation_yuan",
            ],
            "formulas": [
                "full-calendar denominator is all 348 chronological rows with zero flow retained; union-active has either sleeve actual stake>0; intersection-active has both actual stake>0. Publish all three counts and joint-loss rates; never infer diversification from the intersection alone",
                "downside_correlation=corr(min(r_left,0),min(r_right,0)) is reported separately for full-calendar-zero-flow, union-active and intersection-active; blank for <2/nonpositive variance",
                "tail_co_loss_count=count both returns in their own prior 10% lower tail on each declared denominator",
                "portfolio_pnl_reconciliation_yuan=portfolio pre-tax net-sum(actual funded sleeve pre-tax nets) and must equal zero within numerical tolerance; covariance never contributes additional P&L",
                "Pearson/rank/rolling metrics are computed on each declared full-calendar, union-active, and intersection-active denominator; blank for fewer than two observations or zero variance. HHI=sum(issue contribution share²), blank when gross contribution is zero.",
            ],
        },
        "dependence_panel": {
            "key": path_key(
                "economic_family_left",
                "economic_family_right",
                "denominator_id",
                "panel_type",
                "panel_id",
                "window_issues",
                "exclusion_id",
                "metric",
            ),
            "fields": [
                "value",
                "observation_count",
                "active_observation_count",
                "undefined_reason",
                "first_calendar_index",
                "last_calendar_index",
            ],
            "formulas": [
                "denominator_id is one of FULL_CALENDAR_ZERO_FLOW, UNION_ACTIVE or INTERSECTION_ACTIVE; no denominator is implied by a blank value",
                "panel_type is OVERALL, ROLLING, YEAR, REGIME, LOYO, EX_LARGEST_ISSUE or EX_LARGEST_YEAR; panel_id identifies the exact window/year/regime/exclusion set",
                "metric includes Pearson, Spearman, downside correlation, payout overlap, hit overlap, contribution HHI, tail co-loss and joint loss rate; blank/undefined fields carry an explicit undefined_reason",
                "same economic_family_id is prohibited from a primary diversification panel; alias comparisons are separately labeled LINEAGE_REPRODUCTION_ONLY",
            ],
        },
        "intrinsic_native_dependence": {
            "key": path_key(
                "economic_family_left", "economic_family_right",
                "denominator_id", "panel_type", "panel_id", "window_issues",
                "exclusion_id", "metric",
            ),
            "fields": [
                "native_return_basis", "value", "observation_count",
                "undefined_reason", "matched_support_hash",
            ],
            "formulas": [
                "uses unchanged Stage-1→3 native/fixed-capital matched-support returns before any Stage-4 funding, abstention or retained cash",
                "must be labeled INTRINSIC_NATIVE only; blank when an exact native return bridge is unavailable",
            ],
        },
        "realized_funded_flow_dependence": {
            "key": path_key(
                "economic_family_left", "economic_family_right",
                "denominator_id", "panel_type", "panel_id", "window_issues",
                "exclusion_id", "metric",
            ),
            "fields": [
                "value", "observation_count", "cash_flow_count",
                "no_bet_flow_count", "undefined_reason",
            ],
            "formulas": [
                "uses actual Stage-4 funded yuan flows including retained cash and NO_BET zero-flow rows",
                "never label this layer intrinsic diversification or use its correlation change as an Edge claim",
            ],
        },
        "risk_decomposition": {
            "key": path_key("calendar_index", "issue_instance", "economic_family_id"),
            "fields": [
                "marginal_variance_contribution", "euler_variance_contribution",
                "matched_drawdown_delta_yuan", "matched_tail_loss_delta_yuan",
                "capital_utilization_yuan", "retained_cash_yuan",
                "rounding_delta_yuan", "exposure_size_delta_yuan",
                "portfolio_pnl_reconciliation_yuan", "undefined_reason",
            ],
            "formulas": [
                "Euler contribution=w_i*(Sigma*w)_i on the same strictly-prior covariance as the weight estimator; blank when covariance is unavailable",
                "matched drawdown/tail deltas are risk diagnostics, not P&L attribution; portfolio P&L reconciliation is exact funded-sleeve sum",
            ],
        },
        "stage_attribution": {
            "key": path_key("calendar_index", "issue_instance", "sleeve_id", "stage_id"),
            "fields": [
                "attribution_status", "upstream_trace_sha256",
                "native_requested_ticket_count", "normalization_multiplier",
                "portfolio_weight", "actual_ticket_count", "retained_cash_yuan",
                "same_ticket_stage4_funding_delta_yuan", "undefined_reason",
            ],
            "formulas": [
                "STAGE_1_SELECTION/STAGE_2_DIRECTION/STAGE_3_TICKET_CONSTRUCTION are NOT_IDENTIFIABLE_WITHOUT_SPLICE unless immutable upstream contribution evidence is named",
                "STAGE_4_POSITIONING is exact only for the same frozen tickets and attributes sizing, normalization, weighting, integer rounding and cash",
            ],
        },
        "regime_map": {
            "key": ["calendar_index", "issue_instance"],
            "fields": [
                "source_issue_instance", "regime_source_key", "regime_panel_id",
                "feature_row_sha256", "feature_cutoff_ts", "regime_score",
                "regime_algorithm_id", "regime_label", "prior_training_feature_count",
                "prior_training_feature_sha256", "regime_bin_lower", "regime_bin_upper",
                "regime_fallback", "regime_status", "missing_rule",
            ],
            "formulas": [
                "exact (issue,year) bridge from #192 OOS issue namespace to #193 canonical pre-event feature namespace",
                "learned regime labels/bins must be fitted strictly-prior and recorded in selected_m_path/dependence panels with their training-input hash; missing rows remain their own explicit panel",
            ],
        },
        "standalone_m_curve": {
            "key": [
                "economic_family_id",
                "canonical_candidate_id",
                "M",
                "deployment_replicate_bundle_id",
                "deployment_seed",
                "support_hash",
            ],
            "fields": [
                "candidate_aliases_sha256",
                "requested_ticket_count",
                "actual_ticket_count",
                "pre_tax_net_yuan",
                "pre_tax_roi",
                "selection_eligible",
                "undefined_reason",
            ],
            "formulas": [
                "one row for every frozen union-M value and deployment seed on its exact support; aliases sharing an economic_family_id write one canonical row and are not separately purchased",
                "pre_tax_roi=sum(net)/sum(actual stake), blank with explicit undefined_reason when actual stake is zero",
            ],
        },
        "selected_m_path": {
            "key": [
                "economic_family_id",
                "deployment_replicate_bundle_id",
                "deployment_seed",
                "calendar_index",
                "issue_instance",
                "selection_variant",
            ],
            "fields": [
                "support_hash",
                "prior_training_start_calendar_index",
                "prior_training_end_calendar_index",
                "prior_active_issue_count",
                "prior_training_input_sha256",
                "selected_M",
                "fixed_M_comparator",
                "fallback_reason",
                "nested_loyo_held_out_year",
            ],
            "formulas": [
                "selection_variant is WALK_FORWARD or NESTED_LOYO; every selection uses only chronological prior outcomes inside the Gate-B replay and never current/future issue data",
                "before 52 active observations selected_M=fixed_M_comparator with explicit fallback_reason",
            ],
        },
        "portfolio_k_saturation": {
            "key": path_key(
                "ordered_shortlist_id", "K", "economic_family_set_sha256"
            ),
            "fields": [
                "candidate_aliases_sha256",
                "ending_bankroll_yuan",
                "pre_tax_roi",
                "max_drawdown_yuan",
                "contribution_hhi",
                "retained_cash_yuan",
                "marginal_vs_K_minus_1_yuan",
                "undefined_reason",
            ],
            "formulas": [
                "ordered_shortlist_id is frozen in frontier_contract; K uses the first K distinct economic families only",
                "same-family aliases may not increase K, stake, multiplicity, diversification attribution or marginal contribution",
                "every available K/method/mode/fraction/bundle row is written even if no-bet or negative; a multi-sleeve portfolio uses only deployment_replicate_bundle_id plus its frozen candidate_seed_map_sha256, never a fabricated singular deployment seed",
            ],
        },
        "holding_metrics": {
            "key": path_key(),
            "fields": [
                "portfolio_id",
                "mode",
                "position_fraction",
                "ending_bankroll_yuan",
                "max_drawdown_yuan",
                "max_drawdown_fraction",
                "drawdown_duration_issues",
                "time_under_water_issues",
                "recovery_issue",
                "recovery_episode_count",
                "recovery_duration_median_issues",
                "recovery_duration_tail_95_issues",
                "recovery_duration_max_issues",
                "unrecovered_episode_count",
                "loss_streak_calendar",
                "loss_streak_active",
                "miss_streak_calendar",
                "miss_streak_active",
                "rolling_window_metrics_sha256",
                "ruin_flag",
                "near_ruin_flag",
                "sharpe",
                "sortino",
                "calmar",
            ],
            "formulas": [
                "loss=pre_tax_net<0; miss=actual_stake>0 and pre_tax_gross=0; calendar streak includes zero-flow rows, active streak skips zero-flow rows",
                "W=5/10/20 rolling results are emitted exclusively through rolling_window_metrics, which carries each window identity/P&L/ROI and separately keyed count, probability, worst-window and distribution records. Never discard winning issues inside a window",
                "drawdown=running equity peak minus postissue bankroll; duration/time-under-water count chronological issues below peak; recovery is first later issue reaching former peak, blank if absent",
                "near_ruin_flag=1 iff min bankroll < ¥2×max native issue ticket count; sharpe=mean calendar bank return/sample sd×sqrt(issue frequency/year), sortino divides by downside RMS, calmar=annualized compounded bank return/max drawdown fraction; blank where denominator zero",
                "recovery episodes begin on a new running-peak breach and end at first later recovery to that peak; report median, 95th percentile, maximum, and unrecovered count on full chronology",
            ],
        },
        "rolling_window_metrics": {
            "key": path_key(
                "window_size_issues", "record_type", "window_start_calendar_index",
                "window_end_calendar_index", "distribution_statistic"
            ),
            "fields": [
                "window_pre_tax_net_yuan", "window_actual_stake_yuan",
                "window_pre_tax_roi", "is_negative", "window_count",
                "negative_window_count", "negative_window_probability",
                "worst_window_id", "worst_window_pre_tax_net_yuan",
                "worst_window_pre_tax_roi", "distribution_value", "undefined_reason",
            ],
            "formulas": [
                "record_type=WINDOW writes every trailing full-calendar window; record_type=SUMMARY writes count, negative probability and worst identity/P&L/ROI; record_type=DISTRIBUTION writes each frozen statistic such as MIN/P05/P50/P95/MAX. W is exactly one of 5, 10 or 20 and zero-flow issues remain chronological observations.",
                "window_pre_tax_roi=sum(window pre-tax net)/sum(window actual stake), blank with undefined_reason when window stake is zero; no later outcome can select the reported worst window or distribution statistic.",
            ],
        },
        "bootstrap_stability": {
            "key": [
                "portfolio_id",
                "target_id",
                "paired_control_id",
                "economic_family_id",
                "mode",
                "position_fraction",
                "weight_method",
                "normalization_method",
                "deployment_replicate_bundle_id",
                "denominator_id",
                "panel_type",
                "panel_id",
                "metric",
            ],
            "fields": [
                "target_id",
                "paired_control_id",
                "economic_family_id",
                "bootstrap_replicates",
                "bootstrap_seed",
                "paired_growth_delta_low",
                "denominator_id",
                "panel_type",
                "panel_id",
                "metric",
                "value",
                "YEAR",
                "FOLD",
                "LOYO",
                "EX_LARGEST_ISSUE",
                "EX_LARGEST_YEAR",
                "REGIME",
                "fallback_rate",
            ],
            "formulas": [
                "YEAR/FOLD replays retain chronological order within subset; LOYO removes every issue from one year then recomputes state; ex-largest issue/year removes the largest signed pre-tax-net contributor (year aggregates first); decision panels use same full-calendar zero-flow convention"
            ],
        },
        "baseline_lift": {
            "key": path_key(
                "candidate_id", "control_id", "support_hash", "actual_funding_hash"
            ),
            "fields": [
                "candidate_id",
                "control_id",
                "support_hash",
                "mode",
                "position_fraction",
                "actual_funding_hash",
                "absolute_ending_bankroll_yuan",
                "absolute_pre_tax_roi",
                "candidate_minus_control_bankroll_yuan",
                "candidate_minus_control_pre_tax_roi",
                "ladder_decision",
            ],
            "formulas": [
                "all comparisons require identical issue support, mode, fraction, starting capital, available bankroll and actual funding convention",
                "publish absolute path and lift together; blank lift if exact matching is impossible",
                "ladder_decision=ADVANCES only after strict matched PI terminal review",
            ],
        },
        "challenger_case": {
            "key": path_key("alternative_explanation", "test_id"),
            "fields": [
                "candidate_id",
                "alternative_explanation",
                "test_id",
                "result",
                "decision_impact",
            ],
            "formulas": [
                "each headline candidate receives survivor/search, leakage, support, turnover/cash, covariance fitting, largest issue/year, payout cluster and simple-control tests",
                "cash-only smoothing is separately labeled risk reduction, never diversification edge",
            ],
        },
        "all_pairs_risk_return_surface": {
            "key": path_key("economic_family_set_sha256", "pair_id"),
            "fields": ["pre_tax_roi", "sharpe", "sortino", "calmar", "max_drawdown_yuan", "capital_growth", "capital_turnover", "tax_adjusted_roi", "support_hash", "undefined_reason"],
            "formulas": ["write every frozen pair/mode/fraction/weight/normalization/bundle row; zero stake retains blank ROI and an explicit reason; Sharpe/Sortino/Calmar use exactly holding_metrics full-calendar definitions and retain their undefined reason"],
        },
        "higher_order_pareto_frontier": {
            "key": path_key("economic_family_set_sha256", "frontier_id"),
            "fields": ["pre_tax_roi", "capital_growth", "max_drawdown_yuan", "contribution_hhi", "tax_adjusted_roi", "dominance_status", "support_hash"],
            "formulas": ["frontier is computed only from the manifest-covered all-pairs/higher-order surface; aliases cannot create an additional point"],
        },
        "terminal_decision": {
            "key": path_key("decision_id"),
            "fields": ["candidate_id", "decision", "capital_weights_json", "capital_weights_sha256", "failure_regimes_json", "negative_result_reason", "next_validation_step", "strict_ev_status", "support_hash", "bootstrap_target_id"],
            "formulas": ["every primary path writes a terminal decision, the actual frozen capital weights, all failed regimes and a next validation step; an absent row is a Gate-B completeness failure rather than an implicit no-bet"],
        },
        "chart_source_contract": {
            "path_identity": list(PATH_IDENTITY),
            "rule": "every portfolio-level chart source propagates the complete path identity; seed-local curve charts additionally carry deployment_seed and family-level charts carry economic_family_id/support_hash",
            "completeness": "a missing required chart-source row, a duplicate complete key, or a chart row without a matching ledger key is a Gate-B fail-closed schema error",
            "columns": {
                "chart_source_issue_equity_paths.csv.gz": path_key("calendar_index", "issue_instance", "preissue_bankroll_yuan", "postissue_bankroll_yuan", "pre_tax_net_yuan", "actual_stake_yuan"),
                "chart_source_rolling_windows.csv": path_key("window_size_issues", "record_type", "window_start_calendar_index", "window_end_calendar_index", "distribution_statistic", "window_pre_tax_net_yuan", "window_pre_tax_roi"),
                "chart_source_all_pairs_risk_return.csv": path_key("economic_family_set_sha256", "pair_id", "pre_tax_roi", "sharpe", "sortino", "calmar", "max_drawdown_yuan"),
                "chart_source_terminal_decision.csv": path_key("decision_id", "candidate_id", "decision", "capital_weights_sha256", "next_validation_step"),
            },
        },
        "portfolio_cross_table_join_contract": {
            "path_identity": list(PATH_IDENTITY),
            "portfolio_level_tables": list(PORTFOLIO_LEVEL_TABLES),
            "uniqueness_rule": "each table has exactly one row per complete key; a duplicate is a fail-closed Gate-B error",
            "joins": [
                {
                    "left": "issue_ledger",
                    "right": "sleeve_funding_ledger",
                    "key": [*PATH_IDENTITY, "calendar_index", "issue_instance"],
                    "rule": "every funded sleeve row joins one issue ledger row and sleeve actual stake sums exactly to issue actual stake",
                },
                {
                    "left": "issue_ledger",
                    "right": "rolling_window_metrics",
                    "key": list(PATH_IDENTITY),
                    "rule": "all rolling windows are derived only from the identical complete chronological issue path",
                },
                {
                    "left": "capital_summary",
                    "right": "baseline_lift",
                    "key": list(PATH_IDENTITY),
                    "rule": "each absolute path/control lift shares one exact path identity and actual funding hash",
                },
                {
                    "left": "all_pairs_risk_return_surface",
                    "right": "terminal_decision",
                    "key": list(PATH_IDENTITY),
                    "rule": "terminal decisions cite only cells materialized in the same path identity and exact support",
                },
            ],
        },
        "chart_sources": [
            "chart_source_issue_equity_paths.csv.gz",
            "chart_source_capital_frontier.csv",
            "chart_source_risk_return.csv",
            "chart_source_dependence.csv",
            "chart_source_dependence_panel.csv",
            "chart_source_intrinsic_native_dependence.csv",
            "chart_source_realized_funded_flow_dependence.csv",
            "chart_source_risk_decomposition.csv",
            "chart_source_stage_attribution.csv",
            "chart_source_weight_history.csv.gz",
            "chart_source_fundability.csv",
            "chart_source_bootstrap_stability.csv",
            "chart_source_standalone_m_curve.csv.gz",
            "chart_source_selected_m_path.csv.gz",
            "chart_source_portfolio_k_saturation.csv",
            "chart_source_rolling_windows.csv",
            "chart_source_all_pairs_risk_return.csv",
            "chart_source_higher_order_pareto.csv",
            "chart_source_terminal_decision.csv",
        ],
    }


def validate_portfolio_schema(schema: dict[str, object]) -> None:
    """Fail closed if Gate-B tables or chart sources can lose a path identity."""
    for table in PORTFOLIO_LEVEL_TABLES:
        table_schema = schema.get(table)
        if not isinstance(table_schema, dict):
            raise RuntimeError(f"missing portfolio-level schema: {table}")
        key = table_schema.get("key")
        if not isinstance(key, list) or len(key) != len(set(key)):
            raise RuntimeError(f"non-unique key schema: {table}")
        if any(field not in key for field in PATH_IDENTITY):
            raise RuntimeError(f"path identity missing from {table}")
    if "deployment_seed" in schema["portfolio_k_saturation"]["key"]:
        raise RuntimeError("portfolio_k_saturation cannot invent a singular seed")
    if "capital_mode" in schema["baseline_lift"]["key"]:
        raise RuntimeError("baseline_lift must use declared mode path identity")
    if not {"sharpe", "sortino", "calmar"} <= set(
        schema["all_pairs_risk_return_surface"]["fields"]
    ):
        raise RuntimeError("all-pairs risk metrics incomplete")
    if not {
        "capital_weights_json", "failure_regimes_json", "next_validation_step"
    } <= set(schema["terminal_decision"]["fields"]):
        raise RuntimeError("terminal decision schema incomplete")
    if "window_size_issues" not in schema["rolling_window_metrics"]["key"]:
        raise RuntimeError("rolling windows need an explicit W key")
    chart_contract = schema["chart_source_contract"]
    for name, columns in chart_contract["columns"].items():
        if any(field not in columns for field in PATH_IDENTITY):
            raise RuntimeError(f"chart path identity missing: {name}")
    joins = schema["portfolio_cross_table_join_contract"]["joins"]
    if not joins or any(join["key"][: len(PATH_IDENTITY)] != list(PATH_IDENTITY) for join in joins):
        raise RuntimeError("cross-table path joins incomplete")


def funded_prefix_ledger_contract(
    expanded: list[dict[str, object]], economic_families: list[dict[str, object]]
) -> dict[str, object]:
    """Bind Gate-B's exact funded ticket subset before any outcome join."""
    family_by_candidate = {
        str(row["candidate_id"]): str(row["economic_family_id"])
        for row in economic_families
    }
    records = [
        {
            "sleeve_or_family_id": "BEST_FULL_FULL",
            "economic_family_id": family_by_candidate["BEST_FULL_FULL"],
            "prefix_policy": "WHOLE_NATIVE_OR_NO_BET",
            "native_ticket_identity_source": "bj170 identity_allocation_digest.csv.gz",
            "funded_tax_lot_rule": "zero lots or all 2187 canonical ordinals for every inherited identity; partial allocation is forbidden",
        },
        {
            "sleeve_or_family_id": "MODEL_SOURCE_MODEL_CAP1_M512",
            "economic_family_id": family_by_candidate["MODEL_SOURCE_MODEL_CAP1_M512"],
            "prefix_policy": "NESTED_PREFIX_VERIFIED_M1_TO_M512",
            "native_ticket_identity_source": "ticket_prefix_registry.csv.gz + model_cap1_nested_prefix_audit.json.gz",
            "funded_tax_lot_rule": "take global ranks 1..funded_prefix_length and hash their ordered tax_lot_id values",
        },
        {
            "sleeve_or_family_id": "Q_SOURCE_Q_TOP_MASS_M192",
            "economic_family_id": family_by_candidate["Q_SOURCE_Q_TOP_MASS_M192"],
            "prefix_policy": "NESTED_PREFIX_VERIFIED_GLOBAL_ROUND_ROBIN",
            "native_ticket_identity_source": "ticket_prefix_registry.csv.gz",
            "funded_tax_lot_rule": "take global ranks 1..funded_prefix_length and hash their ordered tax_lot_id values",
        },
    ]
    for row in expanded:
        source = (
            f"{row['source_package']}/{row['identity_file']} + "
            f"{row['role_file']} + {row['plan_file']}"
            if "identity_file" in row
            else f"{row['source_package']}/{row['source_identity_file']} + {row['source_plan_file']}"
        )
        records.append(
            {
                "sleeve_or_family_id": row["candidate_id"],
                "economic_family_id": family_by_candidate[str(row["candidate_id"])],
                "prefix_policy": "WHOLE_NATIVE_OR_NO_BET_PENDING_MECHANISM_SPECIFIC_NESTED_PREFIX_PROOF",
                "native_ticket_identity_source": source,
                "funded_tax_lot_rule": (
                    "WHOLE_NATIVE_OR_NO_BET: before a new immutable package supplies "
                    "this exact family/issue/M/seed global ticket stream and nested "
                    "proof, actual funded count is exactly zero or the complete native "
                    "request; Gate B must not take a first prefix, split, interleave or "
                    "infer a tax-lot order from this textual source"
                ),
            }
        )
    return {
        "key": [
            *PATH_IDENTITY,
            "calendar_index",
            "issue_instance",
            "sleeve_or_family_id",
        ],
        "fields": [
            "native_ticket_count",
            "funded_prefix_length",
            "funded_global_rank_start",
            "funded_global_rank_end",
            "funded_tax_lot_sha256",
            "prefix_execution_status",
        ],
        "atomic_funding_rule": "BEST_FULL_FULL is atomic. Any expanded record with WHOLE_NATIVE_OR_NO_BET_PENDING_MECHANISM_SPECIFIC_NESTED_PREFIX_PROOF is also atomic: before proof, its actual funded count is exactly zero or complete native request. Gate B must fail closed rather than take a first prefix, infer an order, interleave, or split a nonnested allocation. Rows sharing economic_family_id are aliases and may not be cofunded.",
        "records": records,
    }


def write_package(output: Path) -> None:
    bindings = {name: verify_source(spec) for name, spec in EXPECTED_SOURCES.items()}
    rows, calendar, _ = source_inputs()
    traces = sleeve_trace_registry(rows)
    regime_rows, regime_contract = regime_binding(calendar)
    attribution_contract = stage_attribution_contract(traces)
    expanded = expanded_sleeve_catalog()
    allocation_candidates = bj145_allocation_candidate_registry()
    economic_families = economic_family_registry(expanded, allocation_candidates)
    bundles = replicate_bundle_registry(expanded, allocation_candidates, economic_families)
    eligibility = eligibility_ledger(expanded, allocation_candidates, economic_families)
    m_selector = m_selection_contract(expanded + allocation_candidates)
    funded_prefix_contract = funded_prefix_ledger_contract(
        expanded + allocation_candidates, economic_families
    )
    baselines = baseline_registry()
    frontier = frontier_contract(eligibility, economic_families)
    prefix_policies, prefix_rows, model_audit_payload = prefix_registry()
    if not all(row["nested"] for row in model_audit_payload["rows"]):
        raise RuntimeError("MODEL partial-prefix audit did not pass every identity")
    schemas = output_schema()
    validate_portfolio_schema(schemas)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        fields = list(rows[0])
        write_csv(stage / "frozen_native_sleeve_requests.csv", fields, rows)
        cal_fields = [
            "calendar_index",
            "issue",
            "year",
            "fold",
            "issue_instance",
            "first_kickoff_ts",
            "strict_three_way_common",
            "outcome_boundary",
        ]
        write_csv(
            stage / "full_calendar.csv",
            cal_fields,
            [{k: r[k] for k in cal_fields} for r in calendar],
        )
        write_csv(
            stage / "strict_three_way_calendar.csv",
            cal_fields,
            [
                {k: r[k] for k in cal_fields}
                for r in calendar
                if r["strict_three_way_common"] == "1"
            ],
        )
        write_csv(stage / "regime_map.csv", list(regime_rows[0]), regime_rows)
        (stage / "regime_binding.json").write_text(
            json.dumps(regime_contract, indent=2, sort_keys=True) + "\n"
        )
        (stage / "stage_attribution_contract.json").write_text(
            json.dumps(attribution_contract, indent=2, sort_keys=True) + "\n"
        )
        (stage / "normalization_contract.json").write_text(
            json.dumps(normalization_contract(), indent=2, sort_keys=True) + "\n"
        )
        catalog = []
        for sleeve, alias, arm, rationale in SLEEVES:
            example = next(r for r in rows if r["sleeve_id"] == sleeve)
            catalog.append(
                {
                    k: example[k]
                    for k in [
                        "sleeve_id",
                        "selector_alias",
                        "selector_id",
                        "allocation_arm",
                        "M",
                        "mechanism",
                        "cap",
                        "weight_source",
                    ]
                }
                | {"rationale": rationale, "outcome_boundary": OUTCOME_BOUNDARY}
            )
        write_csv(stage / "sleeve_catalog.csv", list(catalog[0]), catalog)
        write_csv(
            stage / "executable_sleeve_family_catalog.csv",
            list(expanded[0]),
            expanded,
        )
        write_csv(
            stage / "bj145_allocation_candidate_registry.csv",
            list(allocation_candidates[0]),
            allocation_candidates,
        )
        write_csv(
            stage / "economic_family_registry.csv",
            list(economic_families[0]),
            economic_families,
        )
        write_csv(
            stage / "replicate_bundle_registry.csv",
            list(bundles[0]),
            bundles,
        )
        (stage / "m_selection_contract.json").write_text(
            json.dumps(m_selector, indent=2, sort_keys=True) + "\n"
        )
        (stage / "funded_prefix_ledger_contract.json").write_text(
            json.dumps(funded_prefix_contract, indent=2, sort_keys=True) + "\n"
        )
        write_csv(stage / "sleeve_trace_registry.csv", list(traces[0]), traces)
        write_csv(
            stage / "sleeve_eligibility_ledger.csv", list(eligibility[0]), eligibility
        )
        write_csv(stage / "baseline_registry.csv", list(baselines[0]), baselines)
        (stage / "frontier_contract.json").write_text(
            json.dumps(frontier, indent=2, sort_keys=True) + "\n"
        )
        write_csv(
            stage / "ticket_prefix_policy_registry.csv",
            list(prefix_policies[0]),
            prefix_policies,
        )
        write_csv_gzip(
            stage / "ticket_prefix_registry.csv.gz",
            list(prefix_rows[0]),
            prefix_rows,
        )
        write_json_gzip(
            stage / "model_cap1_nested_prefix_audit.json.gz", model_audit_payload
        )
        (stage / "funding_algorithm.json").write_text(
            json.dumps(funding_contract(), indent=2, sort_keys=True) + "\n"
        )
        (stage / "inference_contract.json").write_text(
            json.dumps(
                {
                    "primary_hypothesis": methodology_contract()["primary_hypothesis"],
                    "multiplicity": methodology_contract()["multiplicity"],
                    "sequential_inference": methodology_contract()[
                        "sequential_inference"
                    ],
                    "challenger_case": methodology_contract()["challenger_case"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (stage / "output_schema.json").write_text(
            json.dumps(schemas, indent=2, sort_keys=True) + "\n"
        )
        card = {
            "contract": CONTRACT,
            "version": VERSION,
            "issue": 192,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_STAGE4_CAPITAL_PORTFOLIO_FREEZE",
            "outcome_boundary": OUTCOME_BOUNDARY,
            "source_binding": bindings,
            "regime_binding": regime_contract,
            "stage_attribution_contract": attribution_contract,
            "normalization_contract": normalization_contract(),
            "sleeve_catalog": catalog,
            "executable_sleeve_family_catalog": expanded,
            "bj145_allocation_candidate_registry": allocation_candidates,
            "economic_family_registry": economic_families,
            "replicate_bundle_registry": bundles,
            "m_selection_contract": m_selector,
            "funded_prefix_ledger_contract": funded_prefix_contract,
            "sleeve_trace_registry": traces,
            "eligibility_ledger": eligibility,
            "frontier_contract": frontier,
            "ticket_prefix_contract": {
                "policy_registry": "ticket_prefix_policy_registry.csv",
                "global_tax_lot_registry": "ticket_prefix_registry.csv.gz",
                "Q_global_interleave": "round_robin by frozen selector_rank then portfolio_id; every Q identity retains deterministic top-mass priority",
                "MODEL_partial_rule": "whole-native or NO_BET unless the policy registry carries a verified all-M nested-prefix proof",
                "MODEL_audit": "model_cap1_nested_prefix_audit.json.gz; all 234 frozen identities replayed against accepted allocator for M=1..512",
                "FULL_partial_rule": "whole-native or NO_BET; no partial FULL identity",
                "global_tax_lot_count": len(prefix_rows),
                "Q_global_tax_lot_rows": sum(
                    row["sleeve_id"] == "Q_SOURCE_Q_TOP_MASS_M192"
                    for row in prefix_rows
                ),
                "MODEL_global_tax_lot_rows": sum(
                    row["sleeve_id"] == "MODEL_SOURCE_MODEL_CAP1_M512"
                    for row in prefix_rows
                ),
            },
            "baseline_registry": baselines,
            "full_calendar": {
                "source": "#137 canonical census/#170 all three frozen request rows",
                "issue_count": len(calendar),
                "chronological_sort": "first_kickoff_ts, issue_instance",
                "zero_flow": "retain NO_BET and Gate-B unavailable rows as zero flow; neither is a loss",
            },
            "strict_three_way_calendar": {
                "source": "#170 THREE_WAY_ALL",
                "issue_count": sum(
                    r["strict_three_way_common"] == "1" for r in calendar
                ),
                "usage": "matched attribution only; never truncate capital/holding paths",
            },
            "funding_contract": funding_contract(),
            "methodology_contract": methodology_contract(),
            "output_schema": schemas,
            "denominator": {
                "calendar_issue_count": len(calendar),
                "strict_three_way_issue_count": sum(
                    r["strict_three_way_common"] == "1" for r in calendar
                ),
                "regime_feature_available_issue_count": regime_contract[
                    "available_feature_count"
                ],
                "regime_feature_missing_issue_count": regime_contract[
                    "missing_feature_count"
                ],
                "native_sleeve_request_rows": len(rows),
                "locked_h1_sleeve_count": len(catalog),
                "expanded_complete_family_count": len(expanded),
                "bj145_complete_allocation_candidate_count": len(allocation_candidates),
                "eligible_economic_family_count": frontier[
                    "eligible_economic_family_count"
                ],
                "deployment_replicate_bundle_count": len(bundles),
                "catalog_identity_count": len(eligibility),
                "eligible_exploratory_family_count": len(expanded),
                "eligible_complete_source_count": frontier["eligible_source_count"],
                "ticket_prefix_policy_rows": len(prefix_policies),
                "all_global_tax_lot_rows": len(prefix_rows),
                "Q_global_tax_lot_rows": sum(
                    row["sleeve_id"] == "Q_SOURCE_Q_TOP_MASS_M192"
                    for row in prefix_rows
                ),
                "position_fraction_count": len(POSITION_FRACTIONS),
            },
            "gate_b_status": "NOT_RUN_AND_NOT_AUTHORIZED_PENDING_PI_GATE_A_ACCEPTANCE",
            "promotion_boundary": "Historical results cannot authorize purchase, betting, production or promotion. Any candidate requires PI review plus independent held-out/forward validation.",
        }
        (stage / "gate_a_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n"
        )
        (stage / "README.md").write_text(
            "# #192 Gate A\n\nImmutable outcome-unexposed Stage-4 capital portfolio freeze.  See `gate_a_card.json`.\n"
        )
        # Canonical scientific hashes decode gzip transport before hashing, so
        # they remain stable across compatible gzip/zlib implementations.  The
        # archive transport hashes retain byte-level auditability of this exact
        # package.  SHA256SUMS covers the identity document and every payload
        # (but cannot recursively cover itself).
        archive_transport_payload = {
            p.name: sha256_file(p) for p in sorted(stage.iterdir()) if p.is_file()
        }
        canonical_scientific_payload = {
            p.name: canonical_scientific_sha256(p)
            for p in sorted(stage.iterdir())
            if p.is_file()
        }
        content = {
            "contract": CONTRACT,
            "version": VERSION,
            "canonical_scientific_payload_sha256": canonical_scientific_payload,
            "canonical_scientific_identity_sha256": canonical_hash(
                canonical_scientific_payload
            ),
            "archive_transport_payload_sha256": archive_transport_payload,
            "archive_transport_contract": {
                "gzip": "gzip.GzipFile(filename='', mtime=0)",
                "manifest": "SHA256SUMS.json is the byte-level archive transport manifest",
                "scientific_identity": "gzip payloads are SHA-256 hashed after decompression",
            },
        }
        (stage / "CONTENT_IDENTITY.json").write_text(
            json.dumps(content, indent=2, sort_keys=True) + "\n"
        )
        manifest = {
            p.name: sha256_file(p) for p in sorted(stage.iterdir()) if p.is_file()
        }
        (stage / "SHA256SUMS.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        if output.exists():
            raise RuntimeError(f"refusing to overwrite immutable output: {output}")
        os.replace(stage, output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args()
    write_package(args.output.resolve())


if __name__ == "__main__":
    main()
