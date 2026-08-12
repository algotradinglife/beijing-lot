#!/usr/bin/env python3
"""Outcome-unexposed Gate-A freeze for #193's regime-conditioned N7 policy.

This runner binds accepted upstream artifacts, but it does not load any target
outcome ledger or settle an action.  The only terminal Gate-B payload parsed is
#190's PI-accepted identity handoff; a strict field allow-list keeps that
post-selection evidence in the ORACLE/EXPLORATORY namespace and out of Tier-C
features.  The large #167/#190 action surfaces are frozen factor-wise and given
a streaming expanded identity, so no grid cell is silently dropped.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, NamedTuple, Sequence


CONTRACT = "BJ-HIST-N7-REGIME-META-POLICY-001"
VERSION = "bj193-gate-a-preoutcome-v1"
REFERENCE_CAPITAL_YUAN = 220_000
BOOTSTRAP_DRAWS = 20_000
BOOTSTRAP_SEED = 193_001
ROLLING_WINDOWS = (5, 10, 20)
NAMESPACE_SCIENTIFIC_ROLES = {
    "ATLAS167": "COMPLETE_ACCEPTED_SELECTOR_ALLOCATION_ATLAS",
    "STACK170": "FIXED_SELECTION_ONLY_NON_ADDITIVITY_CONTEXT",
    "DIVERGENCE190": "DIRECTION_ONLY_USEFUL_WITH_BASELINE_AND_WEAK_MATCH_JOINT_CONTROLS",
}
DIVERGENCE_ARM_SCIENTIFIC_ROLES = {
    "B0_BEST_FULL": "CONTROLLING_BEST_FULL_BASELINE",
    "D_MATCH_ONLY_FULL": "WEAK_MATCH_ONLY_CONTROL",
    "D_DIRECTION_ONLY": "USEFUL_COVERAGE_LIMITED_DIRECTION_ONLY",
    "D_JOINT_SPARSE": "WEAK_JOINT_SPARSE_CONTROL",
}
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: no target result, final/winning SP, payout, tax "
    "realization, ROI, settlement, or post-cutoff evidence enters Tier-C "
    "features, transforms, action ranking, or tie-breaks"
)
ORACLE_BOUNDARY = (
    "ORACLE_DIAGNOSTIC_ONLY: post-selection identities and future realized "
    "outcomes may measure ceiling/regret only; they grant no Edge, promotion, "
    "portfolio-weight, betting, or production authority"
)


def repo_root() -> Path:
    for candidate in (
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
    ):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
DEFAULT_OUTPUT = ROOT / "results" / "bj193_gate_a_preoutcome_v1"


class SourceSpec(NamedTuple):
    issue: int
    package: str
    manifest_sha256: str
    content_sha256: str
    role: str
    access: str
    parsed_payloads: tuple[str, ...] = ()


SOURCE_SPECS = (
    SourceSpec(
        137,
        "bj137_gate_a_preoutcome_v2",
        "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df",
        "36d6afcc33a5b5ceb3e4a990bfe6ec05503be115270c3489f4973dc3a59dd236",
        "accepted issue chronology and original probability-sampling identities",
        "HASH_ONLY",
    ),
    SourceSpec(
        137,
        "bj137_gate_b_outcome_settlement_v3r1_reporting_correction",
        "7453eb917bc4b5422ac13f2d46af540c7c4ebb87a163d8f247b67a9615cd27c0",
        "17c8ee093c399e0693c139203a5fa2fc34a4d7f743cf50db2cd1f7ca9b23a19d",
        "terminal reporting lineage only",
        "HASH_ONLY",
    ),
    SourceSpec(
        145,
        "bj145_gate_a_preoutcome_v8",
        "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c",
        "074c9b06c024a1db80b5b53cfc99a1bc164001b205fcd94a0c159daf445dab7f",
        "accepted allocation mechanisms, M grid and target-safe eSP role vectors",
        "PARSED_OUTCOME_UNEXPOSED",
        ("m_grid.csv", "mechanism_contract.csv", "role_vectors.csv.gz"),
    ),
    SourceSpec(
        145,
        "bj145_gate_b_outcome_settlement_v2",
        "10d5a5082a175ddc965b01fb257e8e5c7e91a844d7ee823fd6d2ad5aeff84cc9",
        "e5ebb462028b3abc9979656de37138c5674b52f1830d1ab6ee093c670236cf5b",
        "terminal allocation evidence identity only",
        "HASH_ONLY",
    ),
    SourceSpec(
        148,
        "bj148_gate_a_preoutcome_v1",
        "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6",
        "dfd3ac234f95f28185a09a6bb2f69c3ff66ddb696ce1fe45a6a1215d932dcd0a",
        "accepted dense-M preregistration",
        "HASH_ONLY",
    ),
    SourceSpec(
        148,
        "bj148_gate_b_outcome_settlement_v1",
        "a60389f27f0373ea03300db5edf28aebb3a0e567e47e78ade860094413756467",
        "38c3325fba0eb02f8701e96ac7cdee4fe9d1aabf146a48b954a0cacf08764b5b",
        "terminal dense-M evidence identity only",
        "HASH_ONLY",
    ),
    SourceSpec(
        151,
        "bj151_gate_a_preoutcome_v1",
        "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6",
        "ac36bc2422d1afd22c3bb4bd680568401cbaec30e0d2006d13afcdfa141b89a5",
        "accepted fixed-candidate source",
        "HASH_ONLY",
    ),
    SourceSpec(
        151,
        "bj151_gate_b_outcome_settlement_v1",
        "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2",
        "3214868b35b74c7ebdefeea5041dc30af86caeaced6a2a877db46e6c7e63508e",
        "terminal three-seed bridge identity only",
        "HASH_ONLY",
    ),
    SourceSpec(
        159,
        "bj159_gate_a_preoutcome_v2r1",
        "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325",
        "4ec52432ec6c1779bab33b0c4bdc4e381b0ae7434228637c509970291ed7361e",
        "accepted cross-N/N7 transfer catalog",
        "HASH_ONLY",
    ),
    SourceSpec(
        159,
        "bj159_gate_b_outcome_settlement_v2r1",
        "17b42f65b834f2b5afff0e52795588f95340d76810f7faec75b193b6eecc4cc8",
        "7ba60fcc8fa99c620c019f6098e3d9e8b5bb112f6622799baffa9c6f2422cbaf",
        "terminal N7 M64 transfer identity only",
        "HASH_ONLY",
    ),
    SourceSpec(
        127,
        "bj127_gate_a_preoutcome_v2",
        "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da",
        "ac99388115df79c6c76b13f5d168ab9d3607b3db508c0a467025b1a7f79db29c",
        "accepted legacy matched FULL versus global single-code deletion baseline",
        "HASH_ONLY",
    ),
    SourceSpec(
        127,
        "bj127_gate_b_outcome_settlement_v1",
        "77712e25965faa6a13d6783032026eca146a3eba9b67462d9af3439c34cd8965",
        "dbce7701d14ff20b14e286856d997233227ebdd7b61e072747a6e56f12091226",
        "terminal legacy matched-policy evidence identity only",
        "HASH_ONLY",
    ),
    SourceSpec(
        167,
        "bj167_gate_a_strategy_atlas_v3r1",
        "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724",
        "0806185a7a68b99fd2a6a465308d11e2886995f992bfa722adb287a4e6a4d147",
        "complete 492 selector x 24,723 allocation outcome-unexposed atlas",
        "PARSED_OUTCOME_UNEXPOSED",
        ("selector_grid.csv", "allocation_grid.csv", "selector_census.csv"),
    ),
    SourceSpec(
        167,
        "bj167_gate_b_outcome_settlement_v2r3",
        "e604ac63a977a375acc4808eb822cd7272fe52dac9d16ff646894677d43a9668",
        "147e5d6f6debbcbb34be458d32a9fd848240ff01b8d67da0506fc707d0e68e4b",
        "accepted common-support ensemble incumbent bridge identity only",
        "HASH_ONLY",
    ),
    SourceSpec(
        167,
        "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
        "b3fa02f5cc2722932ff55fffb0bd9672508f6e78104cfb2458ad81c826f3b313",
        "bfe29083b74d5d212555c261e888d6f5d4d5fd163b56e1876944d1f5d04aa5c7",
        "terminal atlas evidence identity only",
        "HASH_ONLY",
    ),
    SourceSpec(
        170,
        "bj170_gate_a_preoutcome_v2",
        "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87",
        "adc4d0f96628c784149da998a20e8830cde26db4001fe457eaf9ca4b7bb74223",
        "accepted fixed 3x3 selector-allocation stack",
        "PARSED_OUTCOME_UNEXPOSED",
        ("selector_registry.csv", "allocation_registry.csv"),
    ),
    SourceSpec(
        170,
        "bj170_gate_b_selector_allocator_stack_v1",
        "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512",
        "75325aa0f60e277ad3fbf9d90116450833106bc3863b412ea3efcad9948a47b2",
        "terminal non-additivity/selection-only evidence identity",
        "HASH_ONLY",
    ),
    SourceSpec(
        176,
        "bj176_issue_equity_risk_v1",
        "39316952296c2349f5da2f963d43c0baf0d812fba4eea967536a8b80bd57d5ee",
        "94188354baf01c68cb0ec0791248d3f8f03e31d4a7011db7b6b68e9797720f5c",
        "accepted issue-equity risk conventions",
        "HASH_ONLY",
    ),
    SourceSpec(
        190,
        "bj190_gate_a_preoutcome_v3r1",
        "490579f7813d260d11965377462f7aa3b20161dd4672e2b42b600b493d24f1bc",
        "f88a3dc7d010c69e5a1e50274f979f62e95cec47702f0aa842e30d7ffb024cb8",
        "canonical 344-issue pre-event divergence feature source and 2,424-policy grid",
        "PARSED_OUTCOME_UNEXPOSED",
        ("issue_census.csv", "detector_grid.csv", "estimator_match_freeze.csv.gz"),
    ),
    SourceSpec(
        190,
        "bj190_gate_b_sparse_divergence_v1",
        "5685f25d9ce70a66b38b283f668d258d97dfe2e356c5bd45d9666400c6ab4554",
        "5112dc652277a234fcb36687d59e2bd96bf8daeaaa1c9ddd06481923de909ce6",
        "terminal 18-alias/10-economic-identity handoff; no realized metric is emitted or used by Tier C",
        "PARSED_ORACLE_IDENTITY_ALLOWLIST",
        ("strict_ev_candidate_freeze.json",),
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(
    path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(
                text, fieldnames=fields, lineterminator="\n", extrasaction="raise"
            )
            writer.writeheader()
            writer.writerows(rows)
            text.flush()
            text.detach()


def verify_sources() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for spec in SOURCE_SPECS:
        package = ROOT / "results" / spec.package
        manifest_path = package / "SHA256SUMS.json"
        content_path = package / "CONTENT_IDENTITY.json"
        if sha256_file(manifest_path) != spec.manifest_sha256:
            raise RuntimeError(f"source manifest drift: {spec.package}")
        if sha256_file(content_path) != spec.content_sha256:
            raise RuntimeError(f"source content drift: {spec.package}")
        declared = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name in spec.parsed_payloads:
            if name not in declared or sha256_file(package / name) != declared[name]:
                raise RuntimeError(f"parsed payload drift: {spec.package}/{name}")
        rows.append(
            {
                "issue": spec.issue,
                "package": spec.package,
                "manifest_sha256": spec.manifest_sha256,
                "content_identity_sha256": spec.content_sha256,
                "payload_count": len(declared),
                "role": spec.role,
                "access": spec.access,
                "parsed_payloads": "|".join(spec.parsed_payloads),
                "outcome_boundary": ORACLE_BOUNDARY
                if spec.access == "PARSED_ORACLE_IDENTITY_ALLOWLIST"
                else OUTCOME_BOUNDARY,
            }
        )
    return rows


def quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def fmt(value: float | int | None, places: int = 12) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{places}f}"


def entropy(probabilities: Sequence[float]) -> float:
    return -sum(value * math.log(value) for value in probabilities if value > 0)


def categorical_entropy(values: Sequence[str]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    return -sum((count / total) * math.log(count / total) for count in counts.values())


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def load_esp_features() -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Use the compact accepted #145 pre-event role vectors, never settlement."""
    package = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
    e_sp_by_issue_match: dict[str, dict[str, float]] = defaultdict(dict)
    portfolio_roles: dict[tuple[str, str], list[float]] = defaultdict(list)
    with gzip.open(
        package / "role_vectors.csv.gz", "rt", newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            if row["arm_id"] != "PRIMARY_NO_GATE_K4":
                continue
            issue = row["issue"]
            value = float(row["e_sp"])
            old = e_sp_by_issue_match[issue].get(row["match_id"])
            if old is not None and abs(old - value) > 1e-12:
                raise RuntimeError("eSP duplicate identity drift")
            e_sp_by_issue_match[issue][row["match_id"]] = value
            portfolio_roles[(issue, row["portfolio_id"])].append(value)
    gm_by_issue: dict[str, list[float]] = defaultdict(list)
    for (issue, _portfolio), values in portfolio_roles.items():
        if len(values) != 7:
            raise RuntimeError("N7 eSP role width drift")
        gm_by_issue[issue].append(
            math.exp(sum(math.log(value) for value in values) / 7)
        )
    return {
        issue: list(values.values()) for issue, values in e_sp_by_issue_match.items()
    }, dict(gm_by_issue)


def load_selector_census_features() -> dict[str, dict[str, int | float]]:
    package = ROOT / "results" / "bj167_gate_a_strategy_atlas_v3r1"
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(package / "selector_census.csv"):
        grouped[row["issue"]].append(row)
    output: dict[str, dict[str, int | float]] = {}
    for issue, rows in grouped.items():
        candidate_counts = [int(row["candidate_identity_count"] or 0) for row in rows]
        output[issue] = {
            "selector_total_count": len(rows),
            "selector_available_count": sum(
                row["selection_status"] == "AVAILABLE" for row in rows
            ),
            "selector_no_bet_count": sum(
                row["selection_status"] != "AVAILABLE" for row in rows
            ),
            "selector_candidate_identity_count_median": statistics.median(
                candidate_counts
            ),
            "selector_candidate_identity_count_max": max(candidate_counts, default=0),
        }
    return output


FEATURE_FIELDS = (
    "issue",
    "year",
    "outer_fold",
    "issue_instance",
    "feature_cutoff_ts",
    "eligible_match_count",
    "issue_pool_size",
    "league_count",
    "league_entropy",
    "line_minus2_count",
    "line_minus1_count",
    "line_zero_count",
    "line_plus1_count",
    "line_plus2_count",
    "line_other_count",
    "line_entropy",
    "kickoff_span_hours",
    "kickoff_delay_hours_q10",
    "kickoff_delay_hours_median",
    "kickoff_delay_hours_q90",
    "fundamental_p_min_q10",
    "fundamental_p_min_median",
    "fundamental_p_min_q90",
    "calibrated_p_min_q10",
    "calibrated_p_min_median",
    "calibrated_p_min_q90",
    "fundamental_entropy_mean",
    "calibrated_entropy_mean",
    "fundamental_concentration_mean",
    "calibrated_concentration_mean",
    "calibrated_lowp_tail_mass_mean",
    "market_expected_gross_mean",
    "market_expected_gross_sd",
    "market_odds_dispersion_mean",
    "market_uncertainty_mean",
    "market_uncertainty_q90",
    "abs_fundamental_delta_p_q50",
    "abs_fundamental_delta_p_q90",
    "abs_fundamental_delta_p_q99",
    "abs_fundamental_z_q90",
    "abs_line_residual_mu_q50",
    "abs_line_residual_mu_q90",
    "dp_count_ge_005",
    "dp_count_ge_0075",
    "dp_count_ge_010",
    "z_count_ge_100",
    "z_count_ge_150",
    "line_residual_count_ge_050",
    "line_residual_count_ge_075",
    "line_residual_count_ge_100",
    "dp_top7_margin_to_005",
    "dp_top7_margin_to_0075",
    "dp_top7_margin_to_010",
    "accepted_e_sp_match_count",
    "accepted_e_sp_q10",
    "accepted_e_sp_median",
    "accepted_e_sp_q90",
    "accepted_gm_e_sp_portfolio_count",
    "accepted_gm_e_sp_q10",
    "accepted_gm_e_sp_median",
    "accepted_gm_e_sp_q90",
    "gm_margin_to_290",
    "gm_margin_to_300",
    "gm_margin_to_305",
    "selector_total_count",
    "selector_available_count",
    "selector_no_bet_count",
    "selector_candidate_identity_count_median",
    "selector_candidate_identity_count_max",
    "missing_target_safe_probability_count",
    "missing_line_residual_count",
    "missing_accepted_e_sp_flag",
    "missing_selector_census_flag",
    "feature_row_sha256",
    "outcome_boundary",
)


def build_issue_features() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    gate = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    issue_rows = read_csv(gate / "issue_census.csv")
    matches: dict[str, list[dict[str, str]]] = defaultdict(list)
    with gzip.open(
        gate / "estimator_match_freeze.csv.gz", "rt", newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            matches[row["issue"]].append(row)
    e_sp_by_issue, gm_by_issue = load_esp_features()
    selector_by_issue = load_selector_census_features()
    output: list[dict[str, object]] = []
    for issue_row in issue_rows:
        issue = issue_row["issue"]
        rows = matches[issue]
        if len(rows) != int(issue_row["eligible_target_safe_match_count"]):
            raise RuntimeError(f"eligible match census drift: {issue}")
        cutoff = parse_ts(issue_row["feature_cutoff_ts"])
        fundamental_mins: list[float] = []
        calibrated_mins: list[float] = []
        fundamental_entropies: list[float] = []
        calibrated_entropies: list[float] = []
        fundamental_concentrations: list[float] = []
        calibrated_concentrations: list[float] = []
        lowp_tail: list[float] = []
        expected_gross: list[float] = []
        odds_dispersion: list[float] = []
        uncertainties: list[float] = []
        abs_dp: list[float] = []
        abs_z: list[float] = []
        abs_lr: list[float] = []
        delays: list[float] = []
        missing_probability = 0
        missing_lr = 0
        for row in rows:
            kickoff = parse_ts(row["kickoff_ts"])
            if kickoff < cutoff:
                raise RuntimeError(
                    f"feature cutoff after kickoff: {issue}/{row['match_id']}"
                )
            delays.append((kickoff - cutoff).total_seconds() / 3600)
            try:
                fp = [float(row[f"fundamental_p{code}"]) for code in (3, 1, 0)]
                cp = [float(row[f"calibrated_p{code}"]) for code in (3, 1, 0)]
                odds = [float(row[f"euro_1h_odds{code}"]) for code in (3, 1, 0)]
            except ValueError:
                missing_probability += 1
                continue
            fundamental_mins.append(min(fp))
            calibrated_mins.append(min(cp))
            fundamental_entropies.append(entropy(fp) / math.log(3))
            calibrated_entropies.append(entropy(cp) / math.log(3))
            fundamental_concentrations.append(sum(value * value for value in fp))
            calibrated_concentrations.append(sum(value * value for value in cp))
            lowp_tail.append(sum(value for value in cp if value < 0.20))
            expected_gross.append(
                sum(
                    probability * odd for probability, odd in zip(cp, odds, strict=True)
                )
            )
            odds_dispersion.append(statistics.pstdev(odds))
            uncertainties.append(float(row["market_uncertainty_proxy"]))
            abs_dp.append(
                max(abs(float(row[f"fundamental_delta_p{code}"])) for code in (3, 1, 0))
            )
            abs_z.append(
                max(abs(float(row[f"fundamental_z{code}"])) for code in (3, 1, 0))
            )
            if row["line_residual_status"] == "AVAILABLE" and row["line_residual_mu"]:
                abs_lr.append(abs(float(row["line_residual_mu"])))
            else:
                missing_lr += 1
        if not fundamental_mins:
            raise RuntimeError(f"issue has no usable pre-event probability: {issue}")
        line_counts = Counter(row["line_stratum"] for row in rows)
        league_values = [row["league"] for row in rows]
        top7 = sorted(abs_dp, reverse=True)[6] if len(abs_dp) >= 7 else None
        e_sp_values = e_sp_by_issue.get(issue, [])
        gm_values = gm_by_issue.get(issue, [])
        selector = selector_by_issue.get(issue, {})
        base: dict[str, object] = {
            "issue": issue,
            "year": issue_row["year"],
            "outer_fold": issue_row["fold"],
            "issue_instance": issue_row["issue_instance"],
            "feature_cutoff_ts": issue_row["feature_cutoff_ts"],
            "eligible_match_count": len(rows),
            "issue_pool_size": len(rows),
            "league_count": len(set(league_values)),
            "league_entropy": fmt(categorical_entropy(league_values)),
            "line_minus2_count": line_counts.get("-2", 0),
            "line_minus1_count": line_counts.get("-1", 0),
            "line_zero_count": line_counts.get("0", 0),
            "line_plus1_count": line_counts.get("+1", 0),
            "line_plus2_count": line_counts.get("+2", 0),
            "line_other_count": line_counts.get("OTHER", 0),
            "line_entropy": fmt(
                categorical_entropy([row["line_stratum"] for row in rows])
            ),
            "kickoff_span_hours": fmt(max(delays) - min(delays)),
            "kickoff_delay_hours_q10": fmt(quantile(delays, 0.10)),
            "kickoff_delay_hours_median": fmt(quantile(delays, 0.50)),
            "kickoff_delay_hours_q90": fmt(quantile(delays, 0.90)),
            "fundamental_p_min_q10": fmt(quantile(fundamental_mins, 0.10)),
            "fundamental_p_min_median": fmt(quantile(fundamental_mins, 0.50)),
            "fundamental_p_min_q90": fmt(quantile(fundamental_mins, 0.90)),
            "calibrated_p_min_q10": fmt(quantile(calibrated_mins, 0.10)),
            "calibrated_p_min_median": fmt(quantile(calibrated_mins, 0.50)),
            "calibrated_p_min_q90": fmt(quantile(calibrated_mins, 0.90)),
            "fundamental_entropy_mean": fmt(statistics.fmean(fundamental_entropies)),
            "calibrated_entropy_mean": fmt(statistics.fmean(calibrated_entropies)),
            "fundamental_concentration_mean": fmt(
                statistics.fmean(fundamental_concentrations)
            ),
            "calibrated_concentration_mean": fmt(
                statistics.fmean(calibrated_concentrations)
            ),
            "calibrated_lowp_tail_mass_mean": fmt(statistics.fmean(lowp_tail)),
            "market_expected_gross_mean": fmt(statistics.fmean(expected_gross)),
            "market_expected_gross_sd": fmt(statistics.pstdev(expected_gross)),
            "market_odds_dispersion_mean": fmt(statistics.fmean(odds_dispersion)),
            "market_uncertainty_mean": fmt(statistics.fmean(uncertainties)),
            "market_uncertainty_q90": fmt(quantile(uncertainties, 0.90)),
            "abs_fundamental_delta_p_q50": fmt(quantile(abs_dp, 0.50)),
            "abs_fundamental_delta_p_q90": fmt(quantile(abs_dp, 0.90)),
            "abs_fundamental_delta_p_q99": fmt(quantile(abs_dp, 0.99)),
            "abs_fundamental_z_q90": fmt(quantile(abs_z, 0.90)),
            "abs_line_residual_mu_q50": fmt(quantile(abs_lr, 0.50)),
            "abs_line_residual_mu_q90": fmt(quantile(abs_lr, 0.90)),
            "dp_count_ge_005": sum(value >= 0.05 for value in abs_dp),
            "dp_count_ge_0075": sum(value >= 0.075 for value in abs_dp),
            "dp_count_ge_010": sum(value >= 0.10 for value in abs_dp),
            "z_count_ge_100": sum(value >= 1.00 for value in abs_z),
            "z_count_ge_150": sum(value >= 1.50 for value in abs_z),
            "line_residual_count_ge_050": sum(value >= 0.50 for value in abs_lr),
            "line_residual_count_ge_075": sum(value >= 0.75 for value in abs_lr),
            "line_residual_count_ge_100": sum(value >= 1.00 for value in abs_lr),
            "dp_top7_margin_to_005": fmt(top7 - 0.05 if top7 is not None else None),
            "dp_top7_margin_to_0075": fmt(top7 - 0.075 if top7 is not None else None),
            "dp_top7_margin_to_010": fmt(top7 - 0.10 if top7 is not None else None),
            "accepted_e_sp_match_count": len(e_sp_values),
            "accepted_e_sp_q10": fmt(quantile(e_sp_values, 0.10)),
            "accepted_e_sp_median": fmt(quantile(e_sp_values, 0.50)),
            "accepted_e_sp_q90": fmt(quantile(e_sp_values, 0.90)),
            "accepted_gm_e_sp_portfolio_count": len(gm_values),
            "accepted_gm_e_sp_q10": fmt(quantile(gm_values, 0.10)),
            "accepted_gm_e_sp_median": fmt(quantile(gm_values, 0.50)),
            "accepted_gm_e_sp_q90": fmt(quantile(gm_values, 0.90)),
            "gm_margin_to_290": fmt(max(gm_values) - 2.90 if gm_values else None),
            "gm_margin_to_300": fmt(max(gm_values) - 3.00 if gm_values else None),
            "gm_margin_to_305": fmt(max(gm_values) - 3.05 if gm_values else None),
            "selector_total_count": selector.get("selector_total_count", 0),
            "selector_available_count": selector.get("selector_available_count", 0),
            "selector_no_bet_count": selector.get("selector_no_bet_count", 0),
            "selector_candidate_identity_count_median": fmt(
                selector.get("selector_candidate_identity_count_median")
                if selector
                else None
            ),
            "selector_candidate_identity_count_max": selector.get(
                "selector_candidate_identity_count_max", 0
            ),
            "missing_target_safe_probability_count": missing_probability,
            "missing_line_residual_count": missing_lr,
            "missing_accepted_e_sp_flag": int(not e_sp_values),
            "missing_selector_census_flag": int(not selector),
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        base["feature_row_sha256"] = canonical_hash(
            {
                key: base[key]
                for key in base
                if key not in {"feature_row_sha256", "outcome_boundary"}
            }
        )
        output.append(base)
    output.sort(key=lambda row: (row["feature_cutoff_ts"], int(row["issue"])))
    if len(output) != 344 or len({row["issue"] for row in output}) != 344:
        raise RuntimeError("canonical feature issue census drift")
    missingness = []
    for field in FEATURE_FIELDS:
        if field in {"feature_row_sha256", "outcome_boundary"}:
            continue
        missing = sum(row[field] == "" for row in output)
        missingness.append(
            {
                "feature": field,
                "row_count": len(output),
                "missing_count": missing,
                "missing_fraction": fmt(missing / len(output)),
                "missing_rule": "explicit blank plus dedicated source-coverage indicator; Tier C imputes training-fold median only",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return output, missingness


def build_action_catalogs() -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
    list[dict[str, object]],
]:
    atlas = ROOT / "results" / "bj167_gate_a_strategy_atlas_v3r1"
    stack = ROOT / "results" / "bj170_gate_a_preoutcome_v2"
    sparse = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    selectors: list[dict[str, object]] = []
    replay_allocations: list[dict[str, object]] = []
    causal_allocations: list[dict[str, object]] = []
    for row in read_csv(atlas / "selector_grid.csv"):
        selectors.append(
            {
                "namespace": "ATLAS167",
                "selector_factor_id": row["selector_id"],
                "source_package": atlas.name,
                "family": row["family"],
                "definition_json": canonical_json(row),
                "tier_c_eligibility": "CAUSAL_NESTED_ONLY",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    atlas_allocation_rows = read_csv(atlas / "allocation_grid.csv")
    atlas_groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(
        list
    )
    for row in atlas_allocation_rows:
        atlas_groups[
            (row["weight_source"], row["mechanism"], row["cap"], row["M"])
        ].append(row)
    atlas_choice_by_key: dict[tuple[str, str, str, str], str] = {}
    for key in sorted(atlas_groups):
        rows = sorted(atlas_groups[key], key=lambda row: (row["seed"], row["cell_id"]))
        weight_source, mechanism, cap, m_value = key
        identity = {
            "namespace": "ATLAS167",
            "weight_source": weight_source,
            "mechanism": mechanism,
            "cap": cap,
            "M": m_value,
        }
        choice_id = f"A167_{canonical_hash(identity)}"
        atlas_choice_by_key[key] = choice_id
        causal_allocations.append(
            {
                "namespace": "ATLAS167",
                "causal_allocation_factor_id": choice_id,
                "source_package": atlas.name,
                "weight_source": weight_source,
                "mechanism": mechanism,
                "repeat_mode": mechanism,
                "cap": cap,
                "M": m_value,
                "replicate_count": len(rows),
                "replicate_mode": "STOCHASTIC_FROZEN_SEED_ENSEMBLE"
                if len(rows) > 1
                else "DETERMINISTIC_SINGLETON",
                "frozen_seed_set_sha256": canonical_hash([row["seed"] for row in rows]),
                "replay_row_set_sha256": canonical_hash(
                    [row["cell_id"] for row in rows]
                ),
                "seed_aggregation_rule": "on the same issue/support use arithmetic mean replicate stake/gross/tax/net as the one strategy action economics; utility is mean net/mean stake, equivalently sum net/sum stake; deterministic singleton is identity",
                "within_seed_dispersion_required": len(rows) > 1,
                "selection_identity_json": canonical_json(identity),
                "scientific_role": NAMESPACE_SCIENTIFIC_ROLES["ATLAS167"],
                "tier_c_eligibility": "CAUSAL_NESTED_ONLY",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    for row in atlas_allocation_rows:
        key = (row["weight_source"], row["mechanism"], row["cap"], row["M"])
        replay_allocations.append(
            {
                "namespace": "ATLAS167",
                "replay_allocation_row_id": row["cell_id"],
                "causal_allocation_factor_id": atlas_choice_by_key[key],
                "source_package": atlas.name,
                "weight_source": row["weight_source"],
                "mechanism": row["mechanism"],
                "repeat_mode": row["mechanism"],
                "cap": row["cap"],
                "M": row["M"],
                "seed": row["seed"],
                "seed_role": row["seed_role"],
                "seed_selectable": False,
                "selection_identity_includes_seed": False,
                "definition_json": canonical_json(row),
                "scientific_role": NAMESPACE_SCIENTIFIC_ROLES["ATLAS167"],
                "tier_c_eligibility": "CAUSAL_NESTED_ONLY",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    for row in read_csv(stack / "selector_registry.csv"):
        selectors.append(
            {
                "namespace": "STACK170",
                "selector_factor_id": row["selector_alias"],
                "source_package": stack.name,
                "family": row["family"],
                "definition_json": canonical_json(row),
                "tier_c_eligibility": "FIXED_CONTEXT_COMPARATOR",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    for row in read_csv(stack / "allocation_registry.csv"):
        choice_id = row["allocation_arm"]
        identity = {
            "namespace": "STACK170",
            "weight_source": row["weight_source"],
            "mechanism": row["mechanism"],
            "cap": row["cap"],
            "M": row["M"],
        }
        causal_allocations.append(
            {
                "namespace": "STACK170",
                "causal_allocation_factor_id": choice_id,
                "source_package": stack.name,
                "weight_source": row["weight_source"],
                "mechanism": row["mechanism"],
                "repeat_mode": row["mechanism"],
                "cap": row["cap"],
                "M": row["M"],
                "replicate_count": 1,
                "replicate_mode": "DETERMINISTIC_SINGLETON",
                "frozen_seed_set_sha256": canonical_hash(["NA"]),
                "replay_row_set_sha256": canonical_hash([choice_id]),
                "seed_aggregation_rule": "deterministic singleton identity",
                "within_seed_dispersion_required": False,
                "selection_identity_json": canonical_json(identity),
                "scientific_role": NAMESPACE_SCIENTIFIC_ROLES["STACK170"],
                "tier_c_eligibility": "FIXED_CONTEXT_COMPARATOR",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
        replay_allocations.append(
            {
                "namespace": "STACK170",
                "replay_allocation_row_id": choice_id,
                "causal_allocation_factor_id": choice_id,
                "source_package": stack.name,
                "weight_source": row["weight_source"],
                "mechanism": row["mechanism"],
                "repeat_mode": row["mechanism"],
                "cap": row["cap"],
                "M": row["M"],
                "seed": "NA",
                "seed_role": "DETERMINISTIC",
                "seed_selectable": False,
                "selection_identity_includes_seed": False,
                "definition_json": canonical_json(row),
                "scientific_role": NAMESPACE_SCIENTIFIC_ROLES["STACK170"],
                "tier_c_eligibility": "FIXED_CONTEXT_COMPARATOR",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    for row in read_csv(sparse / "detector_grid.csv"):
        selectors.append(
            {
                "namespace": "DIVERGENCE190",
                "selector_factor_id": row["policy_id"],
                "source_package": sparse.name,
                "family": row["detector_family"],
                "definition_json": canonical_json(row),
                "tier_c_eligibility": "CAUSAL_NESTED_ONLY"
                if row["availability"] == "AVAILABLE"
                else "UNAVAILABLE_FROZEN",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    for arm in (
        "B0_BEST_FULL",
        "D_MATCH_ONLY_FULL",
        "D_DIRECTION_ONLY",
        "D_JOINT_SPARSE",
    ):
        identity = {
            "namespace": "DIVERGENCE190",
            "weight_source": "FROZEN_BY_BJ190",
            "mechanism": arm,
            "cap": "NA",
            "M": "2187",
        }
        causal_allocations.append(
            {
                "namespace": "DIVERGENCE190",
                "causal_allocation_factor_id": arm,
                "source_package": sparse.name,
                "weight_source": "FROZEN_BY_BJ190",
                "mechanism": arm,
                "repeat_mode": "FULL_OR_FROZEN_DIRECTIONAL_VECTOR",
                "cap": "NA",
                "M": "2187",
                "replicate_count": 1,
                "replicate_mode": "DETERMINISTIC_SINGLETON",
                "frozen_seed_set_sha256": canonical_hash(["DETERMINISTIC"]),
                "replay_row_set_sha256": canonical_hash([arm]),
                "seed_aggregation_rule": "deterministic singleton identity",
                "within_seed_dispersion_required": False,
                "selection_identity_json": canonical_json(identity),
                "scientific_role": DIVERGENCE_ARM_SCIENTIFIC_ROLES[arm],
                "tier_c_eligibility": "CAUSAL_NESTED_ONLY",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
        replay_allocations.append(
            {
                "namespace": "DIVERGENCE190",
                "replay_allocation_row_id": arm,
                "causal_allocation_factor_id": arm,
                "source_package": sparse.name,
                "weight_source": "FROZEN_BY_BJ190",
                "mechanism": arm,
                "repeat_mode": "FULL_OR_FROZEN_DIRECTIONAL_VECTOR",
                "cap": "NA",
                "M": "2187",
                "seed": "DETERMINISTIC",
                "seed_role": "DETERMINISTIC",
                "seed_selectable": False,
                "selection_identity_includes_seed": False,
                "definition_json": canonical_json(
                    {"arm": arm, "source": "bj190_gate_a_preoutcome_v3r1"}
                ),
                "scientific_role": DIVERGENCE_ARM_SCIENTIFIC_ROLES[arm],
                "tier_c_eligibility": "CAUSAL_NESTED_ONLY",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    selectors.sort(key=lambda row: (row["namespace"], row["selector_factor_id"]))
    replay_allocations.sort(
        key=lambda row: (row["namespace"], row["replay_allocation_row_id"])
    )
    causal_allocations.sort(
        key=lambda row: (row["namespace"], row["causal_allocation_factor_id"])
    )
    compositions: list[dict[str, object]] = []
    expanded = hashlib.sha256()
    counts: dict[str, int] = {}
    for namespace in ("ATLAS167", "STACK170", "DIVERGENCE190"):
        sids = [
            str(row["selector_factor_id"])
            for row in selectors
            if row["namespace"] == namespace
        ]
        aids = [
            str(row["causal_allocation_factor_id"])
            for row in causal_allocations
            if row["namespace"] == namespace
        ]
        replay_row_count = sum(
            row["namespace"] == namespace for row in replay_allocations
        )
        for sid in sids:
            for aid in aids:
                expanded.update(f"{namespace}\x1f{sid}\x1f{aid}\n".encode("utf-8"))
        count = len(sids) * len(aids)
        counts[namespace] = count
        compositions.append(
            {
                "namespace": namespace,
                "selector_factor_count": len(sids),
                "causal_allocation_factor_count": len(aids),
                "replay_allocation_row_count": replay_row_count,
                "expanded_action_count": count,
                "scientific_role": NAMESPACE_SCIENTIFIC_ROLES[namespace],
                "composition_rule": "exact Cartesian product within namespace only; no cross-namespace recombination",
                "tier_c_boundary": "all ranking/refit/tie-breaks use prior outer-train issues only",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    if counts != {"ATLAS167": 473_796, "STACK170": 9, "DIVERGENCE190": 9_696}:
        raise RuntimeError(f"expanded action census drift: {counts}")
    exploratory = build_postselection_registry()
    census = {
        "contract": CONTRACT,
        "version": VERSION,
        "factorized_not_shrunk": True,
        "namespace_counts": counts,
        "expanded_action_count": sum(counts.values()),
        "expanded_action_stream_sha256": expanded.hexdigest(),
        "selector_factor_count": len(selectors),
        "replay_allocation_row_count": len(replay_allocations),
        "causal_allocation_factor_count": len(causal_allocations),
        "atlas167_seed_agnostic_allocation_count": sum(
            row["namespace"] == "ATLAS167" for row in causal_allocations
        ),
        "atlas167_stochastic_allocation_count": sum(
            row["namespace"] == "ATLAS167" and row["replicate_count"] == 100
            for row in causal_allocations
        ),
        "atlas167_deterministic_allocation_count": sum(
            row["namespace"] == "ATLAS167" and row["replicate_count"] == 1
            for row in causal_allocations
        ),
        "seed_selectable": False,
        "action_identity_fields": [
            "namespace",
            "selector_factor_id",
            "causal_allocation_factor_id",
        ],
        "postselection_exploratory_alias_count": len(exploratory),
        "postselection_primary_economic_identity_count": len(
            {row["economic_identity_sha256"] for row in exploratory}
        ),
        "postselection_focus_cluster_alias_count": sum(
            row["focus_cluster"] == "Z100_K1_52_60_75_85" for row in exploratory
        ),
        "postselection_focus_cluster_primary_economic_identity_count": len(
            {
                row["economic_identity_sha256"]
                for row in exploratory
                if row["focus_cluster"] == "Z100_K1_52_60_75_85"
            }
        ),
        "cross_namespace_recombination": False,
        "outcome_boundary": OUTCOME_BOUNDARY,
    }
    if (
        census["postselection_exploratory_alias_count"] != 18
        or census["postselection_primary_economic_identity_count"] != 10
        or census["postselection_focus_cluster_alias_count"] != 12
        or census["postselection_focus_cluster_primary_economic_identity_count"] != 6
    ):
        raise RuntimeError("#190 exploratory identity handoff drift")
    if (
        census["replay_allocation_row_count"] != 24_730
        or census["causal_allocation_factor_count"] != 970
        or census["atlas167_seed_agnostic_allocation_count"] != 963
        or census["atlas167_stochastic_allocation_count"] != 240
        or census["atlas167_deterministic_allocation_count"] != 723
    ):
        raise RuntimeError("seed-agnostic allocation census drift")
    return (
        selectors,
        replay_allocations,
        causal_allocations,
        compositions,
        census,
        exploratory,
    )


def build_postselection_registry() -> list[dict[str, object]]:
    path = (
        ROOT
        / "results"
        / "bj190_gate_b_sparse_divergence_v1"
        / "strict_ev_candidate_freeze.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    source_rows = payload["performance_stable_coverage_limited_alias_rows"]
    allowed = (
        "policy_id",
        "arm",
        "detector_family",
        "estimator_variant",
        "threshold_rule",
        "top_k",
        "selected_issue_count",
        "line_stratum_count",
        "league_count",
        "economic_identity_sha256",
        "economic_representative",
        "economic_alias_count",
    )
    output: list[dict[str, object]] = []
    for source in source_rows:
        selected = {key: source[key] for key in allowed}
        focus_cluster = (
            "Z100_K1_52_60_75_85"
            if source["threshold_rule"] in {"Z_100", "DP050_Z100"}
            and str(source["top_k"]) == "1"
            and int(source["selected_issue_count"]) in {52, 60, 75, 85}
            else ""
        )
        output.append(
            {
                **selected,
                "focus_cluster": focus_cluster,
                "identity_semantics": "exact selected issue set + N7/ticket multiplicity identity + contribution vector",
                "tier": "ORACLE_DIAGNOSTIC_ONLY_POST_SELECTION_EXPLORATORY",
                "tier_c_use": "external historical prior only; cannot establish independent Edge or cross-line validity",
                "coverage_limit": "candidate-arm-own line stratum count is one (line 0)",
                "outcome_boundary": ORACLE_BOUNDARY,
            }
        )
    output.sort(key=lambda row: row["policy_id"])
    if (
        len(output) != 18
        or len({row["economic_identity_sha256"] for row in output}) != 10
    ):
        raise RuntimeError("post-selection allow-list census drift")
    if {int(row["line_stratum_count"]) for row in output} != {1}:
        raise RuntimeError("post-selection coverage boundary drift")
    focus = [row for row in output if row["focus_cluster"]]
    if len(focus) != 12 or len({row["economic_identity_sha256"] for row in focus}) != 6:
        raise RuntimeError("Z100/K1 52/60/75/85 focus-cluster identity drift")
    return output


def chronology_rows(
    features: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    by_year: dict[int, list[Mapping[str, object]]] = defaultdict(list)
    for row in features:
        by_year[int(row["year"])].append(row)
    rows: list[dict[str, object]] = []
    for test_year in range(2021, 2026):
        validation_year = test_year - 1
        outer_train = [
            row
            for year, values in by_year.items()
            if year < test_year
            for row in values
        ]
        inner_train = [
            row
            for year, values in by_year.items()
            if year < validation_year
            for row in values
        ]
        validation = by_year[validation_year]
        test = by_year[test_year]
        if len({row["year"] for row in outer_train}) < 2 or len(outer_train) < 60:
            raise RuntimeError("chronological warm-up contract drift")
        rows.append(
            {
                "outer_fold": f"TEST_{test_year}",
                "inner_validation_year": validation_year,
                "inner_train_issue_count": len(inner_train),
                "inner_validation_issue_count": len(validation),
                "outer_train_issue_count": len(outer_train),
                "outer_test_issue_count": len(test),
                "outer_train_last_cutoff_ts": max(
                    str(row["feature_cutoff_ts"]) for row in outer_train
                ),
                "outer_test_first_cutoff_ts": min(
                    str(row["feature_cutoff_ts"]) for row in test
                ),
                "inner_train_issue_sha256": canonical_hash(
                    [row["issue"] for row in inner_train]
                ),
                "inner_validation_issue_sha256": canonical_hash(
                    [row["issue"] for row in validation]
                ),
                "outer_train_issue_sha256": canonical_hash(
                    [row["issue"] for row in outer_train]
                ),
                "outer_test_issue_sha256": canonical_hash(
                    [row["issue"] for row in test]
                ),
                "fit_rule": "during tuning, feature transforms, regime bins, hyperparameters, action ranking and tie-breaks fit on inner-train only and score the next prior-year validation fold; after selection, refit the chosen family and its transforms on full outer-train before the untouched outer test",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return rows


def feature_contract_rows() -> list[dict[str, object]]:
    groups = {
        "POOL": ["eligible_match_count", "issue_pool_size"],
        "LEAGUE_LINE_TIME": [
            "league_count",
            "league_entropy",
            "line_minus2_count",
            "line_minus1_count",
            "line_zero_count",
            "line_plus1_count",
            "line_plus2_count",
            "line_other_count",
            "line_entropy",
            "kickoff_span_hours",
            "kickoff_delay_hours_q10",
            "kickoff_delay_hours_median",
            "kickoff_delay_hours_q90",
        ],
        "PROBABILITY": [
            name
            for name in FEATURE_FIELDS
            if name.startswith(
                (
                    "fundamental_p_",
                    "calibrated_p_",
                    "fundamental_entropy",
                    "calibrated_entropy",
                    "fundamental_concentration",
                    "calibrated_concentration",
                    "calibrated_lowp",
                )
            )
        ],
        "SP_VALUE": [
            "market_expected_gross_mean",
            "market_expected_gross_sd",
            "market_odds_dispersion_mean",
            "accepted_e_sp_match_count",
            "accepted_e_sp_q10",
            "accepted_e_sp_median",
            "accepted_e_sp_q90",
            "accepted_gm_e_sp_portfolio_count",
            "accepted_gm_e_sp_q10",
            "accepted_gm_e_sp_median",
            "accepted_gm_e_sp_q90",
            "gm_margin_to_290",
            "gm_margin_to_300",
            "gm_margin_to_305",
        ],
        "UNCERTAINTY_DIVERGENCE": [
            name
            for name in FEATURE_FIELDS
            if name.startswith(
                (
                    "market_uncertainty",
                    "abs_fundamental",
                    "abs_line_residual",
                    "dp_count",
                    "z_count",
                    "line_residual_count",
                    "dp_top7",
                )
            )
        ],
        "SELECTOR_CENSUS": [
            name for name in FEATURE_FIELDS if name.startswith("selector_")
        ],
        "MISSINGNESS": [name for name in FEATURE_FIELDS if name.startswith("missing_")],
    }
    source_for = {
        "POOL": "bj190_gate_a_preoutcome_v3r1/issue_census+estimator_match_freeze",
        "LEAGUE_LINE_TIME": "bj190_gate_a_preoutcome_v3r1/estimator_match_freeze",
        "PROBABILITY": "bj190_gate_a_preoutcome_v3r1/estimator_match_freeze",
        "SP_VALUE": "bj190 target-safe EURO + bj145 accepted predicted-SP/eSP role vectors",
        "UNCERTAINTY_DIVERGENCE": "bj190_gate_a_preoutcome_v3r1/estimator_match_freeze",
        "SELECTOR_CENSUS": "bj167_gate_a_strategy_atlas_v3r1/selector_census",
        "MISSINGNESS": "deterministic source-coverage flags",
    }
    rows = []
    for group, fields in groups.items():
        for field in fields:
            rows.append(
                {
                    "feature": field,
                    "group": group,
                    "source": source_for[group],
                    "as_of_rule": "source row feature_cutoff_ts; kickoff must be >= cutoff; historical state embargo inherited from source",
                    "transformation_fit_rule": "during tuning, numeric median imputation and 1/99 winsorization fit on inner-train only; after model selection refit on full outer-train; add missing flag; never fit on validation, outer-test or full sample",
                    "missingness_rule": "blank is preserved in freeze; Tier C uses outer-train median and explicit missing indicator",
                    "causal_namespace": "TIER_C_PRE_EVENT",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    return rows


def model_grid_rows() -> list[dict[str, object]]:
    specs: list[tuple[str, dict[str, object], int]] = []
    specs.append(
        (
            "PRIOR_ONLY_FIXED",
            {"action_rank": "outer-train mean utility", "min_support": 20},
            0,
        )
    )
    for bins in (2, 3, 4):
        for leaf in (10, 20):
            specs.append(
                ("BINNED_REGIME_RULE", {"quantile_bins": bins, "min_leaf": leaf}, 1)
            )
    for depth in (1, 2, 3):
        for leaf in (10, 20, 40):
            specs.append(
                (
                    "SHALLOW_TREE",
                    {
                        "max_depth": depth,
                        "min_leaf": leaf,
                        "criterion": "squared_error",
                    },
                    2,
                )
            )
    for penalty in (0.01, 0.1, 1.0):
        for monotone in ("POOL_VALUE", "UNCERTAINTY_DIVERGENCE"):
            specs.append(
                (
                    "MONOTONE_REGULARIZED_SCORE",
                    {"l2": penalty, "monotone_feature_group": monotone},
                    2,
                )
            )
    for neighbors in (5, 10, 20, 40):
        for weighting in ("UNIFORM", "INVERSE_DISTANCE"):
            specs.append(
                (
                    "NEAREST_HISTORICAL_REGIME",
                    {"k": neighbors, "weighting": weighting},
                    2,
                )
            )
    rows = []
    for family, parameters, complexity in specs:
        rows.append(
            {
                "model_id": f"{family}_{canonical_hash(parameters)[:12]}",
                "family": family,
                "parameters_json": canonical_json(parameters),
                "complexity_rank": complexity,
                "feature_fit": "inner-train during hyperparameter tuning; full outer-train only after selection; never validation, outer-test or full sample",
                "hyperparameter_selection": "inner prior-year validation; tie lower complexity then lexical model_id",
                "action_selection": "predicted utility improvement must be >0 versus strongest prior-only comparator; otherwise fallback",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return rows


def comparator_rows() -> list[dict[str, object]]:
    return [
        {
            "comparator_id": "STATIC_BEST_FULL_FULL",
            "ordinal": 1,
            "definition": "#170 BEST_FULL selector S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1 x FULL_ENUMERATED M2187",
            "role": "controlling accepted static selection baseline; weak namespaces cannot demote it",
            "support": "native and strict matched",
            "selection_boundary": "fixed before #193",
        },
        {
            "comparator_id": "PRIOR_ONLY_BEST_FIXED",
            "ordinal": 2,
            "definition": "best fixed factorized action on outer-train utility; min 20 active training issues",
            "role": "strongest matched prior-only comparator",
            "support": "native and strict matched",
            "selection_boundary": "outer-train only",
        },
        {
            "comparator_id": "DYNAMIC_M_ONLY",
            "ordinal": 3,
            "definition": "freeze selector/allocator/repeat mode to static baseline and vary M only",
            "role": "M attribution",
            "support": "matched",
            "selection_boundary": "nested chronological",
        },
        {
            "comparator_id": "DYNAMIC_REPEAT_ONLY",
            "ordinal": 4,
            "definition": "freeze selector/weight/M and vary WR/WOR/residual/cap/top-mass only",
            "role": "repeat-mode attribution",
            "support": "matched",
            "selection_boundary": "nested chronological",
        },
        {
            "comparator_id": "DYNAMIC_SELECTOR_ONLY",
            "ordinal": 5,
            "definition": "freeze allocator/repeat/M and vary selector only",
            "role": "selector attribution",
            "support": "matched",
            "selection_boundary": "nested chronological",
        },
        {
            "comparator_id": "DYNAMIC_ALLOCATOR_ONLY",
            "ordinal": 6,
            "definition": "freeze selector/M and vary weight/allocator only",
            "role": "allocator attribution",
            "support": "matched",
            "selection_boundary": "nested chronological",
        },
        {
            "comparator_id": "FULL_REGIME_TUPLE",
            "ordinal": 7,
            "definition": "nested regime-conditioned selector x allocator x repeat_mode x M",
            "role": "full causal Tier-C candidate",
            "support": "native and strict common",
            "selection_boundary": "nested chronological with fallback",
        },
        {
            "comparator_id": "LEAKY_ORACLE_CEILING",
            "ordinal": 8,
            "definition": "best realized per-issue utility over identical action set",
            "role": "ceiling and regret only",
            "support": "same available action support",
            "selection_boundary": ORACLE_BOUNDARY,
        },
    ]


def action_learning_execution_contract() -> dict[str, object]:
    return {
        "contract": "BJ193_ACTION_LEARNING_EXECUTION_V1",
        "selection_unit": "seed-agnostic (namespace, selector_factor_id, causal_allocation_factor_id)",
        "replay_unit": "exact frozen seed row retained in allocation_action_catalog.csv.gz",
        "forbidden_choice_inputs": [
            "seed",
            "seed_role",
            "replay_allocation_row_id",
            "realized outcome/SP/payout/tax/ROI from validation or test",
        ],
        "seed_aggregation": {
            "required_replicates": "exact replay_row_set_sha256 and frozen_seed_set_sha256 from causal_allocation_catalog.csv",
            "issue_identity": "namespace + selector + causal allocator + canonical issue",
            "availability": "if any required frozen replicate is unavailable or missing, the entire seed-agnostic issue-action is UNAVAILABLE and excluded from fit/ranking; never encode missing seed as losing stake",
            "economics": "arithmetic mean replicate stake/gross/tax/net on identical issue/support represents one randomized-strategy action; never sum seed stakes as purchased exposure; deterministic singleton is identity",
            "target": "seed-aggregated issue utility = mean replicate pre-tax net / mean replicate stake, equivalently sum net / sum stake; blank when mean stake is zero",
            "ordering": "sort exact numeric seed then replay row identity before accumulation",
            "ranking_boundary": "aggregate before selector screening, allocator screening, model fitting, policy choice, oracle, regret or promotion",
            "dispersion": "publish replicate-level ROI mean, sample SD, MCSE, q05/q50/q95, minimum, maximum and positive fraction separately; never optimize them except as a reported stability diagnostic",
        },
        "model_topology": {
            "kind": "ONE_ACTION_SPECIFIC_MODEL_PER_RETAINED_SEED_AGNOSTIC_ACTION",
            "regime_inputs": "feature_contract.csv TIER_C_PRE_EVENT only",
            "action_inputs": "none inside fitted model; action identity is fixed by deterministic hierarchical screening",
            "target": "seed-aggregated issue utility = aggregate pre-tax net / aggregate stake",
            "loss": "unweighted mean squared error across active settled training issues for that action",
            "minimum_action_support": 20,
            "zero_stake": "exclude from model fit and keep explicit NO_BET zero-flow in policy path",
            "tax": "pre-tax target is primary; tax-adjusted values are reporting-only",
        },
        "hierarchical_screen": {
            "timing": "run on inner-train only during tuning; after model-family selection rerun identically on full outer-train before outer-test refit",
            "ATLAS167": {
                "selector_reference_allocator": {
                    "weight_source": "NA",
                    "mechanism": "FULL_ENUMERATED",
                    "cap": "NA",
                    "M": "2187",
                },
                "selector_score": "aggregate sum pre-tax net / sum stake over active settled screen issues; minimum 20; higher is better",
                "selector_keep": 16,
                "allocator_score": "for each retained selector, exhaust all 963 seed-agnostic allocators and use aggregate sum pre-tax net / sum stake; minimum 20; higher is better",
                "allocator_keep_per_selector": 64,
                "mandatory_additions": "FULL_ENUMERATED M2187 and B167 Q_WEIGHT/WOR_DISTINCT/M64 for every retained selector when supported, plus STATIC_BEST_FULL_FULL",
            },
            "STACK170": "retain all 3x3 fixed contextual actions",
            "DIVERGENCE190": "retain every AVAILABLE selector crossed with all four deterministic arms; weak arms remain controls and cannot demote STATIC_BEST_FULL_FULL",
            "rank_ties": [
                "larger active support",
                "lower native stake",
                "lexical seed-agnostic action identity",
            ],
            "no_early_stop": True,
        },
        "nested_fit": {
            "inner_train": "fit transforms, hierarchical screen and one action-specific model for each retained action",
            "inner_validation": "simulate one policy path using only pre-event availability and predictions",
            "primary_validation_score": "sum chosen-action pre_tax_net_yuan / sum chosen-action stake_yuan; blank/invalid when total stake is zero",
            "validation_ties": [
                "lower maximum issue drawdown_yuan",
                "lower total native stake_yuan",
                "lower model complexity_rank",
                "lexical model_id",
            ],
            "outer_refit": "select one model configuration, rerun screen on full outer-train, refit transforms and action models on full outer-train, then evaluate untouched outer-test",
            "random_state": 193_001,
            "randomized_subsampling": False,
        },
        "choice_and_oracle": {
            "causal_support": "retained seed-agnostic actions that are pre-event AVAILABLE on the issue plus mandatory comparators",
            "causal_choice": "highest predicted utility above strongest matched prior-only comparator; otherwise deterministic fallback",
            "paired_oracle": "highest realized seed-aggregated utility over the exact same causal support for that fold/issue",
            "global_oracle": "optional ceiling over the complete pre-event-available seed-aggregated catalog; label separately and never use as paired regret denominator",
            "seed_identity_allowed": False,
            "tie_breaks": [
                "higher utility",
                "lower native stake",
                "lower complexity",
                "lexical seed-agnostic action identity",
            ],
        },
        "streaming": {
            "sort_order": "namespace, selector_factor_id, causal_allocation_factor_id, canonical issue",
            "screen_implementation": "complete streaming pass with fixed-size exact top-K heaps; compare full tie tuple; no sampling, adaptive pruning or outcome-dependent early stopping",
            "chunk_invariance": "output identity and scores must be byte-identical for chunk sizes 1, 17, 256 and 4096",
            "memory_boundary": "may stream issue-action rows; must not shrink any frozen source catalog or seed ensemble",
        },
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def holding_contract() -> dict[str, object]:
    return {
        "contract": "BJ193_ISSUE_LEVEL_HOLDING_FEASIBILITY_V1",
        "controlling_unit": "chronologically ordered canonical issue",
        "reference_capital_yuan": REFERENCE_CAPITAL_YUAN,
        "capital_convention": "fixed reporting capital; no reinvestment; not a stake cap or action eligibility gate",
        "flow_status": {
            "ACTIVE": "use frozen native stake/gross/net",
            "NO_BET": "explicit zero stake/gross/net",
            "UNAVAILABLE": "explicit zero stake/gross/net; never a loss",
        },
        "sequences": {
            "CALENDAR": "retain every canonical issue; zero-flow rows break negative-P&L and calendar miss streaks",
            "ACTIVE_BET": "drop NO_BET/UNAVAILABLE before streak and rolling-window calculations",
        },
        "negative_pnl": "pre_tax_net_yuan < 0 exactly; zero is not negative",
        "zero_payout_miss": "ACTIVE row with gross_pre_tax_yuan == 0; zero-flow rows are not misses",
        "rolling_windows": list(ROLLING_WINDOWS),
        "rolling_metrics": "evaluate every contiguous 5/10/20 window; report negative-sum frequency, worst net, worst ROI=sum(net)/sum(stake) with blank if zero stake, and exact start/end issue; choose earliest chronology window on ties; compute separately for CALENDAR and ACTIVE_BET",
        "equity": "equity_t = reference_capital + cumulative sum(pre_tax_net_yuan); running_peak includes initial capital",
        "drawdown": "drawdown_yuan = running_peak-equity; drawdown_pct=drawdown_yuan/running_peak",
        "drawdown_episode": "peak_sequence_index is the earliest index establishing the episode peak; onset is the first later index with equity below that peak; trough is the earliest maximum-drawdown index; recovery is the first later index with equity >= the episode peak",
        "drawdown_duration_to_trough_issues": "trough_sequence_index - peak_sequence_index",
        "time_under_water_issues": "recovery_sequence_index - peak_sequence_index when recovered; otherwise last_sequence_index - peak_sequence_index + 1",
        "recovery_issues": "recovery_sequence_index - trough_sequence_index when recovered; blank when unrecovered",
        "duration_sequence_boundary": "derive indices independently after constructing CALENDAR and ACTIVE_BET sequences; never reuse calendar indices for active-bet metrics",
        "recovery": "report median, p90 and maximum recovery_issues over recovered episodes plus unrecovered count",
        "major_episode": "every positive-drawdown episode; chart labels top ten by drawdown_yuan plus all unrecovered",
        "bootstrap": "paired common circular moving-block issue bootstrap; block lengths 5/10/20; shared draws across actions; no row permutation inside a block",
        "scorecard_rule": "compare causal policy to STATIC_BEST_FULL_FULL and PRIOR_ONLY_BEST_FIXED on ROI, loss/miss streaks, rolling losses, drawdown magnitude/duration, and recovery; any deterioration is an explicit trade-off",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def _max_streak(rows: Sequence[Mapping[str, object]], predicate) -> int:
    best = current = 0
    for row in rows:
        current = current + 1 if predicate(row) else 0
        best = max(best, current)
    return best


def _rolling_metrics(
    rows: Sequence[Mapping[str, object]], window: int
) -> dict[str, object]:
    windows = []
    for start in range(max(0, len(rows) - window + 1)):
        selected = rows[start : start + window]
        net = sum(float(row["net"]) for row in selected)
        stake = sum(float(row["stake"]) for row in selected)
        roi = net / stake if stake else None
        windows.append(
            {
                "start_index": start,
                "start_issue": selected[0]["issue"],
                "end_issue": selected[-1]["issue"],
                "net_yuan": net,
                "stake_yuan": stake,
                "roi": roi,
            }
        )
    if not windows:
        return {
            "window_length": window,
            "window_count": 0,
            "negative_sum_count": 0,
            "negative_sum_frequency": "",
            "worst_net_yuan": "",
            "worst_roi": "",
            "worst_start_issue": "",
            "worst_end_issue": "",
        }
    worst = min(
        windows,
        key=lambda row: (
            row["net_yuan"],
            float("inf") if row["roi"] is None else row["roi"],
            row["start_index"],
        ),
    )
    negative_count = sum(row["net_yuan"] < 0 for row in windows)
    return {
        "window_length": window,
        "window_count": len(windows),
        "negative_sum_count": negative_count,
        "negative_sum_frequency": fmt(negative_count / len(windows)),
        "worst_net_yuan": fmt(worst["net_yuan"]),
        "worst_roi": fmt(worst["roi"]),
        "worst_start_issue": worst["start_issue"],
        "worst_end_issue": worst["end_issue"],
    }


def _drawdown_episodes(
    rows: Sequence[Mapping[str, object]], sequence_basis: str
) -> list[dict[str, object]]:
    equity = float(REFERENCE_CAPITAL_YUAN)
    peak_equity = equity
    peak_index = -1
    peak_issue = "INITIAL_CAPITAL"
    episode: dict[str, object] | None = None
    output: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        equity += float(row["net"])
        drawdown = peak_equity - equity
        if episode is None and drawdown > 0:
            episode = {
                "sequence_basis": sequence_basis,
                "peak_issue": peak_issue,
                "peak_sequence_index": peak_index,
                "onset_issue": row["issue"],
                "onset_sequence_index": index,
                "trough_issue": row["issue"],
                "trough_sequence_index": index,
                "drawdown_yuan": drawdown,
            }
        elif episode is not None and drawdown > float(episode["drawdown_yuan"]):
            episode["trough_issue"] = row["issue"]
            episode["trough_sequence_index"] = index
            episode["drawdown_yuan"] = drawdown
        if episode is not None and equity >= peak_equity:
            trough_index = int(episode["trough_sequence_index"])
            episode.update(
                {
                    "recovery_issue": row["issue"],
                    "recovery_sequence_index": index,
                    "drawdown_duration_to_trough_issues": trough_index
                    - int(episode["peak_sequence_index"]),
                    "time_under_water_issues": index
                    - int(episode["peak_sequence_index"]),
                    "recovery_issues": index - trough_index,
                    "recovered_flag": True,
                }
            )
            output.append(episode)
            episode = None
            peak_equity = equity
            peak_index = index
            peak_issue = str(row["issue"])
        elif episode is None and equity > peak_equity:
            peak_equity = equity
            peak_index = index
            peak_issue = str(row["issue"])
    if episode is not None:
        trough_index = int(episode["trough_sequence_index"])
        episode.update(
            {
                "recovery_issue": "",
                "recovery_sequence_index": "",
                "drawdown_duration_to_trough_issues": trough_index
                - int(episode["peak_sequence_index"]),
                "time_under_water_issues": len(rows)
                - int(episode["peak_sequence_index"]),
                "recovery_issues": "",
                "recovered_flag": False,
            }
        )
        output.append(episode)
    return output


def holding_path_metrics(
    flows: Sequence[Mapping[str, object]], sequence_basis: str
) -> dict[str, object]:
    if sequence_basis not in {"CALENDAR", "ACTIVE_BET"}:
        raise ValueError(f"unknown sequence basis: {sequence_basis}")
    rows = (
        list(flows)
        if sequence_basis == "CALENDAR"
        else [row for row in flows if row["status"] == "ACTIVE"]
    )
    return {
        "sequence_basis": sequence_basis,
        "row_count": len(rows),
        "max_negative_pnl_streak": _max_streak(rows, lambda row: float(row["net"]) < 0),
        "max_zero_payout_miss_streak": _max_streak(
            rows,
            lambda row: row["status"] == "ACTIVE" and float(row["gross"]) == 0,
        ),
        "rolling_windows": [
            _rolling_metrics(rows, window) for window in ROLLING_WINDOWS
        ],
        "drawdown_episodes": _drawdown_episodes(rows, sequence_basis),
        "ending_equity_yuan": float(REFERENCE_CAPITAL_YUAN)
        + sum(float(row["net"]) for row in rows),
    }


def holding_fixture() -> dict[str, object]:
    flow_values = [
        ("A", "ACTIVE", 100.0, 80.0, -20.0),
        ("B", "NO_BET", 0.0, 0.0, 0.0),
        ("C", "ACTIVE", 100.0, 0.0, -100.0),
        ("D", "ACTIVE", 100.0, 220.0, 120.0),
        ("E", "ACTIVE", 100.0, 150.0, 50.0),
        ("F", "UNAVAILABLE", 0.0, 0.0, 0.0),
        ("G", "ACTIVE", 100.0, 70.0, -30.0),
        ("H", "ACTIVE", 100.0, 130.0, 30.0),
        ("I", "ACTIVE", 100.0, 120.0, 20.0),
        ("J", "NO_BET", 0.0, 0.0, 0.0),
        ("K", "ACTIVE", 100.0, 60.0, -40.0),
        ("L", "ACTIVE", 100.0, 80.0, -20.0),
        ("M", "ACTIVE", 100.0, 110.0, 10.0),
        ("N", "ACTIVE", 100.0, 105.0, 5.0),
        ("O", "ACTIVE", 100.0, 85.0, -15.0),
        ("P", "UNAVAILABLE", 0.0, 0.0, 0.0),
        ("Q", "ACTIVE", 100.0, 110.0, 10.0),
        ("R", "ACTIVE", 100.0, 75.0, -25.0),
        ("S", "ACTIVE", 100.0, 105.0, 5.0),
        ("T", "ACTIVE", 100.0, 0.0, -100.0),
        ("U", "NO_BET", 0.0, 0.0, 0.0),
        ("V", "ACTIVE", 100.0, 0.0, -100.0),
        ("W", "ACTIVE", 100.0, 105.0, 5.0),
        ("X", "ACTIVE", 100.0, 95.0, -5.0),
        ("Y", "ACTIVE", 100.0, 100.0, 0.0),
    ]
    flows = [
        {"issue": issue, "status": status, "stake": stake, "gross": gross, "net": net}
        for issue, status, stake, gross, net in flow_values
    ]
    computed = {
        basis: holding_path_metrics(flows, basis)
        for basis in ("CALENDAR", "ACTIVE_BET")
    }
    expected = {
        "CALENDAR": {
            "sequence_basis": "CALENDAR",
            "row_count": 25,
            "max_negative_pnl_streak": 2,
            "max_zero_payout_miss_streak": 1,
            "rolling_windows": [
                {
                    "window_length": 5,
                    "window_count": 21,
                    "negative_sum_count": 14,
                    "negative_sum_frequency": "0.666666666667",
                    "worst_net_yuan": "-220.000000000000",
                    "worst_roi": "-0.550000000000",
                    "worst_start_issue": "R",
                    "worst_end_issue": "V",
                },
                {
                    "window_length": 10,
                    "window_count": 16,
                    "negative_sum_count": 10,
                    "negative_sum_frequency": "0.625000000000",
                    "worst_net_yuan": "-225.000000000000",
                    "worst_roi": "-0.281250000000",
                    "worst_start_issue": "O",
                    "worst_end_issue": "X",
                },
                {
                    "window_length": 20,
                    "window_count": 6,
                    "negative_sum_count": 6,
                    "negative_sum_frequency": "1.000000000000",
                    "worst_net_yuan": "-250.000000000000",
                    "worst_roi": "-0.156250000000",
                    "worst_start_issue": "F",
                    "worst_end_issue": "Y",
                },
            ],
            "drawdown_episodes": [
                {
                    "sequence_basis": "CALENDAR",
                    "peak_issue": "INITIAL_CAPITAL",
                    "peak_sequence_index": -1,
                    "onset_issue": "A",
                    "onset_sequence_index": 0,
                    "trough_issue": "C",
                    "trough_sequence_index": 2,
                    "drawdown_yuan": 120.0,
                    "recovery_issue": "D",
                    "recovery_sequence_index": 3,
                    "drawdown_duration_to_trough_issues": 3,
                    "time_under_water_issues": 4,
                    "recovery_issues": 1,
                    "recovered_flag": True,
                },
                {
                    "sequence_basis": "CALENDAR",
                    "peak_issue": "E",
                    "peak_sequence_index": 4,
                    "onset_issue": "G",
                    "onset_sequence_index": 6,
                    "trough_issue": "G",
                    "trough_sequence_index": 6,
                    "drawdown_yuan": 30.0,
                    "recovery_issue": "H",
                    "recovery_sequence_index": 7,
                    "drawdown_duration_to_trough_issues": 2,
                    "time_under_water_issues": 3,
                    "recovery_issues": 1,
                    "recovered_flag": True,
                },
                {
                    "sequence_basis": "CALENDAR",
                    "peak_issue": "I",
                    "peak_sequence_index": 8,
                    "onset_issue": "K",
                    "onset_sequence_index": 10,
                    "trough_issue": "V",
                    "trough_sequence_index": 21,
                    "drawdown_yuan": 270.0,
                    "recovery_issue": "",
                    "recovery_sequence_index": "",
                    "drawdown_duration_to_trough_issues": 13,
                    "time_under_water_issues": 17,
                    "recovery_issues": "",
                    "recovered_flag": False,
                },
            ],
            "ending_equity_yuan": 219_800.0,
        },
        "ACTIVE_BET": {
            "sequence_basis": "ACTIVE_BET",
            "row_count": 20,
            "max_negative_pnl_streak": 2,
            "max_zero_payout_miss_streak": 2,
            "rolling_windows": [
                {
                    "window_length": 5,
                    "window_count": 16,
                    "negative_sum_count": 11,
                    "negative_sum_frequency": "0.687500000000",
                    "worst_net_yuan": "-215.000000000000",
                    "worst_roi": "-0.430000000000",
                    "worst_start_issue": "R",
                    "worst_end_issue": "W",
                },
                {
                    "window_length": 10,
                    "window_count": 11,
                    "negative_sum_count": 7,
                    "negative_sum_frequency": "0.636363636364",
                    "worst_net_yuan": "-270.000000000000",
                    "worst_roi": "-0.270000000000",
                    "worst_start_issue": "K",
                    "worst_end_issue": "V",
                },
                {
                    "window_length": 20,
                    "window_count": 1,
                    "negative_sum_count": 1,
                    "negative_sum_frequency": "1.000000000000",
                    "worst_net_yuan": "-200.000000000000",
                    "worst_roi": "-0.100000000000",
                    "worst_start_issue": "A",
                    "worst_end_issue": "Y",
                },
            ],
            "drawdown_episodes": [
                {
                    "sequence_basis": "ACTIVE_BET",
                    "peak_issue": "INITIAL_CAPITAL",
                    "peak_sequence_index": -1,
                    "onset_issue": "A",
                    "onset_sequence_index": 0,
                    "trough_issue": "C",
                    "trough_sequence_index": 1,
                    "drawdown_yuan": 120.0,
                    "recovery_issue": "D",
                    "recovery_sequence_index": 2,
                    "drawdown_duration_to_trough_issues": 2,
                    "time_under_water_issues": 3,
                    "recovery_issues": 1,
                    "recovered_flag": True,
                },
                {
                    "sequence_basis": "ACTIVE_BET",
                    "peak_issue": "E",
                    "peak_sequence_index": 3,
                    "onset_issue": "G",
                    "onset_sequence_index": 4,
                    "trough_issue": "G",
                    "trough_sequence_index": 4,
                    "drawdown_yuan": 30.0,
                    "recovery_issue": "H",
                    "recovery_sequence_index": 5,
                    "drawdown_duration_to_trough_issues": 1,
                    "time_under_water_issues": 2,
                    "recovery_issues": 1,
                    "recovered_flag": True,
                },
                {
                    "sequence_basis": "ACTIVE_BET",
                    "peak_issue": "I",
                    "peak_sequence_index": 6,
                    "onset_issue": "K",
                    "onset_sequence_index": 7,
                    "trough_issue": "V",
                    "trough_sequence_index": 16,
                    "drawdown_yuan": 270.0,
                    "recovery_issue": "",
                    "recovery_sequence_index": "",
                    "drawdown_duration_to_trough_issues": 10,
                    "time_under_water_issues": 14,
                    "recovery_issues": "",
                    "recovered_flag": False,
                },
            ],
            "ending_equity_yuan": 219_800.0,
        },
    }
    return {
        "synthetic_only": True,
        "flows": flows,
        "computed": computed,
        "expected": expected,
    }


def output_schema() -> dict[str, object]:
    return {
        "raw": {
            "issue_seed_replay_settlement.csv.gz": [
                "namespace",
                "selector_factor_id",
                "replay_allocation_row_id",
                "causal_allocation_factor_id",
                "seed",
                "issue",
                "status",
                "stake_yuan",
                "gross_pre_tax_yuan",
                "pre_tax_net_yuan",
            ],
            "issue_action_settlement.csv.gz": [
                "action_identity",
                "issue",
                "status",
                "required_replicate_count",
                "settled_replicate_count",
                "aggregation_rule",
                "stake_yuan",
                "gross_pre_tax_yuan",
                "tax_yuan",
                "pre_tax_net_yuan",
                "tax_adjusted_net_yuan",
            ],
            "issue_policy_choice.csv.gz": [
                "policy_id",
                "issue",
                "chosen_action_identity",
                "choice_as_of_ts",
                "train_end_issue",
                "fallback_reason",
            ],
            "issue_equity_timeseries.csv.gz": [
                "policy_id",
                "sequence_basis",
                "issue",
                "chronology_index",
                "status",
                "stake_yuan",
                "gross_pre_tax_yuan",
                "pre_tax_net_yuan",
                "cumulative_equity_yuan",
                "running_peak_yuan",
                "drawdown_yuan",
                "drawdown_pct",
                "negative_pnl_flag",
                "zero_payout_miss_flag",
            ],
        },
        "holding": {
            "streak_metrics.csv": [
                "policy_id",
                "fold",
                "sequence_basis",
                "max_negative_pnl_streak",
                "max_zero_payout_miss_streak",
            ],
            "rolling_loss_windows.csv": [
                "policy_id",
                "fold",
                "sequence_basis",
                "window_length",
                "window_count",
                "negative_pnl_probability",
                "worst_net_yuan",
                "worst_roi",
                "worst_start_issue",
                "worst_end_issue",
            ],
            "drawdown_episodes.csv": [
                "policy_id",
                "sequence_basis",
                "peak_issue",
                "onset_issue",
                "trough_issue",
                "recovery_issue",
                "drawdown_yuan",
                "drawdown_pct",
                "peak_sequence_index",
                "onset_sequence_index",
                "trough_sequence_index",
                "recovery_sequence_index",
                "drawdown_duration_to_trough_issues",
                "time_under_water_issues",
                "recovery_issues",
                "recovered_flag",
            ],
            "recovery_summary.csv": [
                "policy_id",
                "sequence_basis",
                "episode_count",
                "recovered_count",
                "unrecovered_count",
                "median_recovery_issues",
                "p90_recovery_issues",
                "max_recovery_issues",
            ],
            "holding_feasibility_scorecard.csv": [
                "candidate_policy",
                "comparator",
                "support",
                "roi",
                "max_loss_streak",
                "max_miss_streak",
                "rolling_5_loss_probability",
                "rolling_10_loss_probability",
                "rolling_20_loss_probability",
                "max_drawdown_yuan",
                "max_drawdown_pct",
                "max_drawdown_duration_issues",
                "max_recovery_issues",
                "tradeoff_disposition",
            ],
        },
        "science": {
            "oracle_regret.csv.gz": [
                "issue",
                "oracle_action",
                "causal_action",
                "oracle_utility",
                "causal_utility",
                "regret",
                "namespace",
            ],
            "performance_summary.csv": [
                "policy_id",
                "support",
                "stake_yuan",
                "pre_tax_roi",
                "tax_adjusted_roi",
                "sharpe",
                "sortino",
                "calmar",
                "turnover",
                "action_switch_count",
            ],
            "stability_year_fold_loyo.csv": [
                "policy_id",
                "view",
                "included_value",
                "excluded_value",
                "stake_yuan",
                "pre_tax_roi",
                "max_drawdown_yuan",
                "max_loss_streak",
            ],
            "bootstrap_paired_20000.csv": [
                "candidate",
                "comparator",
                "metric",
                "mean",
                "ci_low",
                "ci_high",
                "probability_improvement",
            ],
            "within_seed_dispersion.csv": [
                "namespace",
                "selector_factor_id",
                "causal_allocation_factor_id",
                "fold",
                "active_issue_count",
                "replicate_count",
                "seed_roi_mean",
                "seed_roi_sample_sd",
                "seed_roi_mcse",
                "seed_roi_q05",
                "seed_roi_q50",
                "seed_roi_q95",
                "seed_roi_min",
                "seed_roi_max",
                "positive_seed_fraction",
            ],
            "handoff_dynamic_sleeves.csv": [
                "sleeve_id",
                "action_namespace",
                "nested_rule",
                "native_support",
                "common_support",
                "holding_disposition",
                "eligibility_for_192",
                "independent_ev_required",
            ],
            "failure_attribution.csv": [
                "policy_id",
                "failure_code",
                "oracle_opportunity_present",
                "causal_mapping_stable",
                "support_sufficient",
                "action_noise_excessive",
                "causal_outperformance_present",
                "evidence",
                "disposition",
            ],
        },
        "failure_code_enum": [
            "NO_ORACLE_OPPORTUNITY",
            "UNSTABLE_REGIME_TO_ACTION_MAPPING",
            "INSUFFICIENT_SUPPORT",
            "EXCESSIVE_ACTION_SPACE_NOISE",
            "CAUSAL_GENERALIZATION_FAILURE",
            "NO_FAILURE",
        ],
        "aggregate_economics_rule": "stochastic seed rows are nuisance replicates: publish arithmetic mean replicate stake/gross/tax/net as one action; never sum seed stakes as purchased exposure",
        "blank_rules": "ROI is blank for zero stake; no-bet/unavailable remain explicit zero-flow rows; no missing value is encoded as zero loss",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def chart_rows() -> list[dict[str, object]]:
    charts = [
        (
            "FEATURE_REGIME_MAP",
            "issue_regime_features",
            "probability/SP distributions, entropy, concentration, line/league/time and missingness",
        ),
        (
            "ACTION_PERFORMANCE_HEATMAP",
            "issue_action_settlement",
            "selector x allocator x repeat_mode x M by regime",
        ),
        (
            "PARTIAL_DEPENDENCE",
            "issue_policy_choice",
            "interpretable rule/tree response and complexity-matched controls",
        ),
        (
            "STATIC_DYNAMIC_M_CURVES",
            "issue_action_settlement",
            "complete accepted M curves and nested selected-M path",
        ),
        (
            "CHOICE_FREQUENCY",
            "issue_policy_choice",
            "WR/WOR/selector/allocator/M choices by regime and year",
        ),
        (
            "ORACLE_CAUSAL_REGRET",
            "oracle_regret",
            "oracle ceiling, causal utility and regret decomposition",
        ),
        (
            "WITHIN_SEED_DISPERSION",
            "within_seed_dispersion",
            "nuisance-replicate ROI SD, MCSE, quantiles, extrema and positive fraction; never a selectable seed surface",
        ),
        (
            "EQUITY_DRAWDOWN",
            "issue_equity_timeseries",
            "issue-level equity, peak, drawdown and NO_BET zero-flow rows",
        ),
        (
            "ROLLING_LOSS_WINDOWS",
            "rolling_loss_windows",
            "calendar/active 5/10/20 negative-window probability and worst windows",
        ),
        (
            "STREAK_DISTRIBUTION",
            "streak_metrics",
            "negative-P&L and zero-payout miss streak bootstrap/fold distributions",
        ),
        (
            "DRAWDOWN_RECOVERY",
            "drawdown_episodes",
            "peak/trough/recovery identities, duration and time under water",
        ),
        (
            "STABILITY_CONCENTRATION",
            "stability_year_fold_loyo",
            "YEAR/FOLD/LOYO, ex-largest issue/year and payout concentration",
        ),
        (
            "HOLDING_SCORECARD",
            "holding_feasibility_scorecard",
            "causal versus static and prior-only investor holding trade-offs",
        ),
    ]
    return [
        {
            "chart_id": chart,
            "source_table": source,
            "required_semantics": semantics,
            "publication_stage": "GATE_B",
            "chart_source_required": True,
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        for chart, source, semantics in charts
    ]


def bootstrap_contract() -> dict[str, object]:
    return {
        "draws": BOOTSTRAP_DRAWS,
        "seed": BOOTSTRAP_SEED,
        "paired_unit": "canonical issue on matched support",
        "economics_bootstrap": "shared iid issue-index resample for additive ROI/lift metrics",
        "path_bootstrap": "shared circular moving-block resample preserving within-block chronology",
        "path_block_lengths": list(ROLLING_WINDOWS),
        "draw_sharing": "one deterministic draw matrix per support; identical indices for every candidate-comparator target",
        "interval": "two-sided percentile 2.5/97.5; one-sided promotion lower bound reported separately",
        "loyo": "exact leave-one-calendar-year-out; no bootstrap substitution",
        "exclusions": "ex-largest payout issue and year, signed largest positive issue/year, and all year/regime exclusions",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def decision_contract() -> dict[str, object]:
    return {
        "selectable_action_identity": "namespace + selector_factor_id + causal_allocation_factor_id; never seed or replay row identity",
        "utility": "seed-aggregated pre_tax_net_yuan/stake_yuan for active issue; NO_BET and UNAVAILABLE utility=0; tax-adjusted is reference only",
        "seed_aggregation": "exact frozen seeds aggregate before every fit, rank, choice, oracle, regret or promotion test; within-seed dispersion is separate",
        "oracle_action": "maximum realized seed-aggregated utility on the exact same causal available support; tie lower native stake, then lexical seed-agnostic action identity",
        "causal_action": "maximum outer-train-fitted predicted seed-aggregated utility; require predicted improvement >0 over strongest prior-only comparator or use fallback",
        "regret": "oracle utility minus selected causal utility on identical issue/action availability",
        "fallback": "STATIC_BEST_FULL_FULL when history/support is insufficient; otherwise PRIOR_ONLY_BEST_FIXED; a weak namespace cannot force action",
        "minimum_history": "60 prior canonical issues, at least two prior calendar years, and 20 active training rows per candidate action",
        "tie_breaks": [
            "higher predicted utility",
            "lower outer-train downside deviation",
            "lower native stake",
            "lower complexity",
            "lexical action identity",
        ],
        "promotion": "causal candidate must beat strongest matched prior-only comparator, survive YEAR/LOYO/regime and ex-largest exclusions, avoid one-payout dependence, and improve at least one holding metric without unacceptable deterioration",
        "oracle_restriction": ORACLE_BOUNDARY,
        "seed_identity_prohibition": "seed ID is a nuisance replicate and is forbidden as regime feature, choice dimension, tie-break, oracle action or promotion identity",
        "strict_independent_ev": "required only for materially positive/promotable causal candidate",
        "authority": "paper research only; no betting, purchase, production, portfolio-weight or selector-release authority",
    }


def accepted_baseline_rows() -> list[dict[str, object]]:
    common = {
        "outcome_boundary": OUTCOME_BOUNDARY,
    }
    return [
        {
            "baseline_id": "STATIC_BEST_FULL_FULL",
            "source_gate_a_package": "bj170_gate_a_preoutcome_v2",
            "source_gate_a_manifest": "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87",
            "source_gate_b_package": "bj170_gate_b_selector_allocator_stack_v1",
            "source_gate_b_manifest": "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512",
            "selector": "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1",
            "allocator": "FULL_ENUMERATED",
            "repeat_mode": "FULL_ENUMERATED",
            "M": 2187,
            "seed_scope": "DETERMINISTIC",
            "role": "CONTROLLING_STATIC_BASELINE",
            "decision_boundary": "accepted BEST_FULL ladder; not demoted by weak transfer namespaces",
            **common,
        },
        {
            "baseline_id": "B167_COMMON_SUPPORT_Q_WOR_M64",
            "source_gate_a_package": "bj167_gate_a_strategy_atlas_v3r1",
            "source_gate_a_manifest": "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724",
            "source_gate_b_package": "bj167_gate_b_outcome_settlement_v2r3",
            "source_gate_b_manifest": "e604ac63a977a375acc4808eb822cd7272fe52dac9d16ff646894677d43a9668",
            "selector": "S1_NO_GATE_K4",
            "allocator": "Q_WEIGHT",
            "repeat_mode": "WOR_DISTINCT",
            "M": 64,
            "seed_scope": "ENSEMBLE_100",
            "role": "ATLAS_INCUMBENT_BRIDGE",
            "decision_boundary": "accepted common-support discovery bridge; no promotion",
            **common,
        },
        {
            "baseline_id": "B137_151_THREE_SEED",
            "source_gate_a_package": "bj151_gate_a_preoutcome_v1",
            "source_gate_a_manifest": "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6",
            "source_gate_b_package": "bj151_gate_b_outcome_settlement_v1",
            "source_gate_b_manifest": "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2",
            "selector": "S1_NO_GATE_K4",
            "allocator": "Q_WEIGHT",
            "repeat_mode": "WOR_DISTINCT",
            "M": 64,
            "seed_scope": "137001|137002|137003",
            "role": "DISCOVERY_DIAGNOSTIC",
            "decision_boundary": "three exact source seeds; not an accepted Edge",
            **common,
        },
        {
            "baseline_id": "B127_LEGACY",
            "source_gate_a_package": "bj127_gate_a_preoutcome_v2",
            "source_gate_a_manifest": "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da",
            "source_gate_b_package": "bj127_gate_b_outcome_settlement_v1",
            "source_gate_b_manifest": "77712e25965faa6a13d6783032026eca146a3eba9b67462d9af3439c34cd8965",
            "selector": "ESP300_GM305_LOWP20",
            "allocator": "PRUNE_ONE_GLOBAL_P_MIN",
            "repeat_mode": "DETERMINISTIC_GLOBAL_DELETE",
            "M": 1458,
            "seed_scope": "DETERMINISTIC",
            "role": "LEGACY_REFERENCE",
            "decision_boundary": "historical matched FULL/prune reference; not promoted or recomputed in Gate A",
            **common,
        },
        {
            "baseline_id": "B159_N7_M64_TRANSFER",
            "source_gate_a_package": "bj159_gate_a_preoutcome_v2r1",
            "source_gate_a_manifest": "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325",
            "source_gate_b_package": "bj159_gate_b_outcome_settlement_v2r1",
            "source_gate_b_manifest": "17b42f65b834f2b5afff0e52795588f95340d76810f7faec75b193b6eecc4cc8",
            "selector": "selected-WOR",
            "allocator": "NA",
            "repeat_mode": "WOR_DISTINCT",
            "M": 64,
            "seed_scope": "N7",
            "role": "CROSS_N_TRANSFER_DIAGNOSTIC",
            "decision_boundary": "N7/M64 transfer only; not an accepted Edge",
            **common,
        },
        {
            "baseline_id": "NO_BET_ZERO_FLOW",
            "source_gate_a_package": "bj193_gate_a_preoutcome_v1",
            "source_gate_a_manifest": "SELF_CONTENT_BOUND",
            "source_gate_b_package": "",
            "source_gate_b_manifest": "",
            "selector": "NO_BET",
            "allocator": "NO_BET",
            "repeat_mode": "NO_BET",
            "M": 0,
            "seed_scope": "DETERMINISTIC",
            "role": "FAIL_CLOSED_FALLBACK",
            "decision_boundary": "zero stake/gross/net; never encoded as a loss",
            **common,
        },
    ]


def package_identity(stage: Path, controls: Mapping[str, object]) -> tuple[str, str]:
    payloads = {
        path.name: sha256_file(path)
        for path in sorted(stage.iterdir(), key=lambda item: item.name)
        if path.is_file()
        and path.name not in {"CONTENT_IDENTITY.json", "SHA256SUMS.json"}
    }
    content = {
        "contract": CONTRACT,
        "version": VERSION,
        "controls": dict(controls),
        "payloads": payloads,
    }
    (stage / "CONTENT_IDENTITY.json").write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        path.name: sha256_file(path)
        for path in sorted(stage.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (stage / "SHA256SUMS.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return sha256_file(stage / "SHA256SUMS.json"), sha256_file(
        stage / "CONTENT_IDENTITY.json"
    )


def validate_stage(stage: Path) -> None:
    manifest = json.loads((stage / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name
        for path in stage.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if set(manifest) != actual:
        raise RuntimeError("manifest coverage drift")
    for name, digest in manifest.items():
        if sha256_file(stage / name) != digest:
            raise RuntimeError(f"payload hash drift: {name}")
    card = json.loads((stage / "gate_a_card.json").read_text(encoding="utf-8"))
    if card["status"] != "READY_FOR_PI_REVIEW_NO_GATE_B_AUTHORITY":
        raise RuntimeError("Gate-A state drift")
    if card["denominator"]["canonical_issue_count"] != 344:
        raise RuntimeError("feature census drift")
    if card["denominator"]["expanded_action_count"] != 483_501:
        raise RuntimeError("action surface shrinkage")


def build(output: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"immutable output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        sources = verify_sources()
        features, missingness = build_issue_features()
        (
            selectors,
            replay_allocations,
            causal_allocations,
            compositions,
            action_census,
            exploratory,
        ) = build_action_catalogs()
        chronology = chronology_rows(features)
        feature_contract = feature_contract_rows()
        models = model_grid_rows()
        comparators = comparator_rows()
        holding = holding_contract()
        fixture = holding_fixture()
        if fixture["computed"] != fixture["expected"]:
            raise RuntimeError("holding-definition fixture drift")

        write_csv(stage / "source_binding.csv", tuple(sources[0]), sources)
        write_gzip(stage / "issue_regime_features.csv.gz", FEATURE_FIELDS, features)
        write_csv(
            stage / "feature_contract.csv", tuple(feature_contract[0]), feature_contract
        )
        write_csv(
            stage / "feature_missingness_census.csv", tuple(missingness[0]), missingness
        )
        write_gzip(
            stage / "selector_action_catalog.csv.gz", tuple(selectors[0]), selectors
        )
        write_gzip(
            stage / "allocation_action_catalog.csv.gz",
            tuple(replay_allocations[0]),
            replay_allocations,
        )
        write_csv(
            stage / "causal_allocation_catalog.csv",
            tuple(causal_allocations[0]),
            causal_allocations,
        )
        write_csv(
            stage / "action_namespace_composition.csv",
            tuple(compositions[0]),
            compositions,
        )
        (stage / "action_catalog_census.json").write_text(
            json.dumps(action_census, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_csv(
            stage / "postselection_exploratory_registry.csv",
            tuple(exploratory[0]),
            exploratory,
        )
        write_csv(
            stage / "chronological_nested_folds.csv", tuple(chronology[0]), chronology
        )
        write_csv(stage / "model_family_grid.csv", tuple(models[0]), models)
        write_csv(stage / "comparator_registry.csv", tuple(comparators[0]), comparators)
        write_csv(
            stage / "chart_schema_registry.csv", tuple(chart_rows()[0]), chart_rows()
        )
        (stage / "oracle_causal_decision_contract.json").write_text(
            json.dumps(decision_contract(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (stage / "action_learning_execution_contract.json").write_text(
            json.dumps(action_learning_execution_contract(), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (stage / "holding_feasibility_contract.json").write_text(
            json.dumps(holding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / "holding_definition_fixture.json").write_text(
            json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / "output_schema_contract.json").write_text(
            json.dumps(output_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (stage / "bootstrap_contract.json").write_text(
            json.dumps(bootstrap_contract(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (stage / "freeze_runner.py").write_bytes(Path(__file__).read_bytes())

        baseline_rows = accepted_baseline_rows()
        write_csv(
            stage / "accepted_baseline_ladder.csv",
            tuple(baseline_rows[0]),
            baseline_rows,
        )

        card = {
            "contract": CONTRACT,
            "version": VERSION,
            "issue": 193,
            "stage": "GATE_A_OUTCOME_UNEXPOSED",
            "status": "READY_FOR_PI_REVIEW_NO_GATE_B_AUTHORITY",
            "outcome_access": False,
            "parent_issue": 192,
            "denominator": {
                "canonical_issue_count": len(features),
                "tier_c_feature_count": len(feature_contract),
                "feature_matrix_column_count": len(FEATURE_FIELDS),
                "feature_missingness_row_count": len(missingness),
                "source_package_count": len(sources),
                "selector_factor_count": action_census["selector_factor_count"],
                "replay_allocation_row_count": action_census[
                    "replay_allocation_row_count"
                ],
                "causal_allocation_factor_count": action_census[
                    "causal_allocation_factor_count"
                ],
                "atlas167_seed_agnostic_allocation_count": action_census[
                    "atlas167_seed_agnostic_allocation_count"
                ],
                "atlas167_stochastic_allocation_count": action_census[
                    "atlas167_stochastic_allocation_count"
                ],
                "atlas167_deterministic_allocation_count": action_census[
                    "atlas167_deterministic_allocation_count"
                ],
                "expanded_action_count": action_census["expanded_action_count"],
                "atlas167_action_count": action_census["namespace_counts"]["ATLAS167"],
                "stack170_action_count": action_census["namespace_counts"]["STACK170"],
                "divergence190_action_count": action_census["namespace_counts"][
                    "DIVERGENCE190"
                ],
                "postselection_alias_count": 18,
                "postselection_primary_economic_identity_count": 10,
                "postselection_focus_cluster_alias_count": action_census[
                    "postselection_focus_cluster_alias_count"
                ],
                "postselection_focus_cluster_primary_economic_identity_count": action_census[
                    "postselection_focus_cluster_primary_economic_identity_count"
                ],
                "chronological_outer_fold_count": len(chronology),
                "model_grid_count": len(models),
                "comparator_count": len(comparators),
                "chart_schema_count": len(chart_rows()),
            },
            "evidence_tiers": {
                "TIER_C": "causal pre-event nested chronological only",
                "TIER_O": ORACLE_BOUNDARY,
            },
            "holding_feasibility": {
                "controlling_unit": "issue",
                "sequence_bases": ["CALENDAR", "ACTIVE_BET"],
                "rolling_windows": list(ROLLING_WINDOWS),
                "hard_deliverable": True,
            },
            "action_identity": {
                "factorized_not_shrunk": True,
                "seed_selectable": False,
                "seed_aggregation_economics": "arithmetic mean replicate stake/gross/tax/net represents one randomized strategy; never summed seed exposure",
                "expanded_action_stream_sha256": action_census[
                    "expanded_action_stream_sha256"
                ],
                "cross_namespace_recombination": False,
                "M_boundary": "use only each accepted upstream namespace's frozen M grid; M=2187 is the accepted N7 full-ticket-space identity, not an arbitrary bankroll cap or rejection gate; no new M extrapolation in Gate A",
            },
            "gate_b_authorized": False,
            "production_authority": False,
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        (stage / "gate_a_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        readme = f"""# #193 Gate A — regime-conditioned dynamic N7 meta-policy\n\nThis immutable package freezes the outcome-unexposed contract only. It contains {len(features)} canonical issue feature rows and preserves every accepted replay row while making seeds nuisance replicates: 24,723 #167 seed rows collapse to 963 seed-agnostic allocator choices. The causal/oracle surface is 492×963 #167 actions, 3×3 #170 actions, and 2,424×4 #190 actions ({action_census["expanded_action_count"]:,} total). Seed identity is forbidden from features, action choice, tie-breaks and oracle selection; stochastic economics are aggregated across the exact frozen seed ensemble before ranking, with dispersion reported separately. No Gate-B settlement was run.\n\nThe #190 terminal handoff remains exactly 18 post-selection exploratory aliases / 10 primary economic identities. Twelve aliases / six primary identities form the explicitly labeled Z100/K1 52/60/75/85-issue focus cluster. These rows are isolated in `ORACLE_DIAGNOSTIC_ONLY_POST_SELECTION_EXPLORATORY`; all have one candidate-arm line stratum and cannot support cross-line or production claims. Direction-only remains useful but coverage-limited; match-only and joint-sparse arms remain weak controls.\n\nTier C uses five prior-year outer tests (2021–2025), nested prior-year model selection, inner-train-only tuning transforms, full-outer-train refit after selection, deterministic hierarchical screening, action-specific models and exact fallback/tie rules. Tier O uses the same seed-aggregated action support and is a leaked ceiling/regret diagnostic only.\n\nIssue-level holding feasibility is controlling. Gate B must retain NO_BET/unavailable as zero-flow calendar rows and publish calendar plus active-bet streaks, every rolling 5/10/20 window, issue-level drawdown duration/time under water, recovered and unrecovered episodes, and the holding scorecard. The accepted M grids are scientific action identities, not budget gates; M=2187 is the accepted full N7 ticket space.\n\nPaper research only; no betting, purchase, production, portfolio-weight or selector-release authority.\n"""
        (stage / "README.md").write_text(readme, encoding="utf-8")
        controls = {
            "source_manifest_hashes": {
                row["package"]: row["manifest_sha256"] for row in sources
            },
            "canonical_issue_count": len(features),
            "expanded_action_count": action_census["expanded_action_count"],
            "expanded_action_stream_sha256": action_census[
                "expanded_action_stream_sha256"
            ],
            "postselection_alias_count": 18,
            "postselection_primary_economic_identity_count": 10,
            "postselection_focus_cluster_alias_count": action_census[
                "postselection_focus_cluster_alias_count"
            ],
            "postselection_focus_cluster_primary_economic_identity_count": action_census[
                "postselection_focus_cluster_primary_economic_identity_count"
            ],
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "rolling_windows": list(ROLLING_WINDOWS),
            "gate_b_authorized": False,
            "production_authority": False,
        }
        manifest_hash, content_hash = package_identity(stage, controls)
        validate_stage(stage)
        os.replace(stage, output)
        return {
            "output": str(output),
            "manifest_sha256": manifest_hash,
            "content_identity_sha256": content_hash,
            "payload_count": len(json.loads((output / "SHA256SUMS.json").read_text())),
            "canonical_issue_count": len(features),
            "expanded_action_count": action_census["expanded_action_count"],
            "postselection_alias_count": 18,
            "postselection_primary_economic_identity_count": 10,
            "postselection_focus_cluster_alias_count": action_census[
                "postselection_focus_cluster_alias_count"
            ],
            "postselection_focus_cluster_primary_economic_identity_count": action_census[
                "postselection_focus_cluster_primary_economic_identity_count"
            ],
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
