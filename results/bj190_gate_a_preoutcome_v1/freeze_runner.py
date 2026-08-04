#!/usr/bin/env python3
"""Freeze Issue #190's outcome-unexposed sparse-divergence Gate A."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any


ISSUE = 190
CONTRACT = "BJ-HIST-SPARSE-DIVERGENCE-N7-001"
VERSION = "bj190-gate-a-preoutcome-v1"
BASE_MAIN_COMMIT = "7b3c55fd6a490a3e4147b94b7df944535b80b88f"
FULL_TICKETS = 3**7
FULL_STAKE_YUAN = 2 * FULL_TICKETS
COHORT_ISSUES = 348
PARTICIPATING_ISSUES = 189
CANDIDATE_IDENTITIES = 424
UNIQUE_MATCHES = 1558
SOURCE_DB_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
SOURCE_180_CORE_SHA256 = "4d65b08609162644394dfe83e632073ad092b9bfd058dc74368b9ceef4908890"
SOURCE_180_RUNNER_SHA256 = "f715dfb3ea976cc311fea6aacf79c648fce0209d79b071cd9233e769978994fc"
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: target score/result/final-or-winning SP/payout/tax/ROI/"
    "settlement fields are forbidden; historical scores enter the accepted #180 state only "
    "under its frozen kickoff <= issue cutoff - 180 minute embargo"
)
FORBIDDEN_TARGET_FIELDS = {
    "score",
    "fthg",
    "ftag",
    "result",
    "result_label",
    "result_code",
    "winning_sp",
    "final_sp",
    "official_sp_3",
    "official_sp_1",
    "official_sp_0",
    "payout",
    "tax",
    "roi",
    "settlement",
}
CODE_ORDER = ("3", "1", "0")
LINE_STRATA = ("-2", "-1", "0", "+1", "+2", "OTHER")
DIRECTION_STRATA = ("3", "1", "0", "UNAVAILABLE")


SOURCE_PACKAGES = {
    "134_gate_a": (
        "bj134_gate_a_preoutcome_v3",
        "0a7e4d673e7fc5fd4832c91e3b519afe5a2bc3211b99f4c95f57c691921b65fd",
        "3fe014f3decdbd589cdded52d8a9b2bac0f3cb988c2ae8e15cf79314a02eede1",
        "NUMERIC_OUTCOME_UNEXPOSED_INPUT",
    ),
    "134_gate_b": (
        "bj134_gate_b_fundamental_overlay_v1",
        "6a08c310cd5999a8c615d85ac85cdce55f584a19a4b263dd638b682018975e44",
        "f92e7b8a14814f2d665da03c3ab7ca0ddea790773ddb0d28ed562ca177a3eb05",
        "TERMINAL_IDENTITY_HASH_ONLY",
    ),
    "167_gate_a": (
        "bj167_gate_a_strategy_atlas_v3r1",
        "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724",
        "0806185a7a68b99fd2a6a465308d11e2886995f992bfa722adb287a4e6a4d147",
        "INCUMBENT_CONTRACT_HASH_ONLY",
    ),
    "167_gate_b": (
        "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
        "b3fa02f5cc2722932ff55fffb0bd9672508f6e78104cfb2458ad81c826f3b313",
        "bfe29083b74d5d212555c261e888d6f5d4d5fd163b56e1876944d1f5d04aa5c7",
        "TERMINAL_IDENTITY_HASH_ONLY",
    ),
    "170_gate_a": (
        "bj170_gate_a_preoutcome_v2",
        "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87",
        "adc4d0f96628c784149da998a20e8830cde26db4001fe457eaf9ca4b7bb74223",
        "INCUMBENT_IDENTITY_HASH_ONLY",
    ),
    "170_gate_b": (
        "bj170_gate_b_selector_allocator_stack_v1",
        "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512",
        "75325aa0f60e277ad3fbf9d90116450833106bc3863b412ea3efcad9948a47b2",
        "TERMINAL_IDENTITY_HASH_ONLY",
    ),
    "179_gate_a": (
        "bj179_gate_a_preoutcome_v2",
        "5839f5c03c94ef903472b64fffa3ad1462ec006717875d0a3903ecdfdc2aa056",
        "2e8314f00b8774501ecf0ed2cb6ede73a9e7a60c7422dd5dc0d464e1470b740b",
        "NUMERIC_OUTCOME_UNEXPOSED_INPUT",
    ),
    "179_gate_b": (
        "bj179_gate_b_hierarchical_league_v1",
        "7005e78ae132bea4231ba245cb23d5480a387215c441d237299668c36d305a30",
        "23bf54cc47f036bae11a1bbbcade49fdd34b32ca42cbce5aa15c52d51c21297a",
        "TERMINAL_IDENTITY_HASH_ONLY",
    ),
    "180_gate_a": (
        "bj180_gate_a_preoutcome_v2",
        "96cbd2565f5d1f837700e476d7a7412225677581b5e4448a4f9bfac4c9220835",
        "6a0abe9cb36198dae11a5da06679d22b786cdf49f3619e6e34d7782f29915288",
        "NUMERIC_OUTCOME_UNEXPOSED_INPUT",
    ),
    "180_gate_b": (
        "bj180_gate_b_team_matchup_v1",
        "9f48b29325d817ce873bd1430be459c9e70ad052064f8e03e02ccbc1d8bc6fcf",
        "d9b41dec45c1c6215755d9dad8774e00fc0f19f564ee6ef8bf2387cb8d309108",
        "TERMINAL_IDENTITY_HASH_ONLY",
    ),
}

SOURCE_86 = {
    "gate_a_package": "bj86_gate_a_preoutcome_v3_1",
    "gate_a_manifest_sha256": "1c3fd6148001c42efe2c33c9f1b7f592f4ed11cbe903ca8546c4c9571aeaef64",
    "gate_a_runner_sha256": "dcc5912c0e8040a829367e3bcc559a82e08a632e5bdc1a833b5ee9380e1ffb26",
    "gate_b_recovery_package": "bj86_gate_b_streaming_summary_recovery_v1",
    "gate_b_recovery_manifest_sha256": "0dee918ddcf67ee441abe6ff9387418ca92b4c1e587b8595cf4ebbaec9d898b2",
    "accepted_head": "ecc545359a392cee344cf2161ba382ef697c1767",
    "merge_commit": "8af13de640101d3cf64f663e5689a0db52d1d0d2",
    "access": "HASH_BINDING_AND_NONDUPLICATION_PRIOR_ONLY",
    "durability": "large prediction package intentionally external; exact manifest receipts retained",
}


def repo_root() -> Path:
    source = Path(__file__).resolve()
    for candidate in (source.parent, *source.parents, Path.cwd(), *Path.cwd().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
DEFAULT_OUTPUT = ROOT / "results" / "bj190_gate_a_preoutcome_v1"
DB_REPOSITORY_PATH = Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite")

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

try:
    import bj190_sparse_divergence_core as core190
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bj190_sparse_core as core190  # type: ignore[no-redef]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module loader unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def locate_database() -> Path:
    for base in (ROOT, *ROOT.parents):
        candidate = base / DB_REPOSITORY_PATH
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("canonical source database unavailable")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise RuntimeError(f"cannot write empty CSV: {path.name}")
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise RuntimeError(f"cannot write empty gzip CSV: {path.name}")
    fieldnames = list(rows[0])
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
            writer = csv.DictWriter(text, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            text.flush()
            text.detach()


class GzipRowSink:
    """Bounded-memory deterministic gzip CSV sink."""

    def __init__(self, path: Path) -> None:
        self.raw = path.open("wb")
        self.compressed = gzip.GzipFile(
            filename="", mode="wb", fileobj=self.raw, mtime=0
        )
        self.text = io.TextIOWrapper(self.compressed, encoding="utf-8", newline="")
        self.writer: csv.DictWriter[str] | None = None
        self.fieldnames: list[str] | None = None
        self.count = 0

    def emit(self, row: Mapping[str, object]) -> None:
        if self.writer is None:
            self.fieldnames = list(row)
            self.writer = csv.DictWriter(
                self.text, fieldnames=self.fieldnames, lineterminator="\n"
            )
            self.writer.writeheader()
        elif list(row) != self.fieldnames:
            raise RuntimeError("streaming CSV field order drift")
        self.writer.writerow(row)
        self.count += 1

    def close(self) -> None:
        if self.writer is None:
            raise RuntimeError("cannot close empty streaming CSV")
        self.text.flush()
        self.text.detach()
        self.compressed.close()
        self.raw.close()


def compact(value: float | int | str | None) -> object:
    if value is None:
        return ""
    return f"{value:.12f}" if isinstance(value, float) else value


def verify_manifest(directory: Path, expected_manifest: str, *, full: bool) -> None:
    manifest_path = directory / "SHA256SUMS.json"
    content_path = directory / "CONTENT_IDENTITY.json"
    if sha256_file(manifest_path) != expected_manifest:
        raise RuntimeError(f"source manifest hash drift: {directory.name}")
    if full:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, expected in manifest.items():
            path = directory / name
            if not path.is_file() or sha256_file(path) != expected:
                raise RuntimeError(f"source payload drift: {directory.name}/{name}")
    if not content_path.is_file():
        raise RuntimeError(f"source content identity unavailable: {directory.name}")


def verify_sources() -> list[dict[str, object]]:
    rows = []
    for source_id, (package, manifest, content, access) in SOURCE_PACKAGES.items():
        directory = ROOT / "results" / package
        full = access == "NUMERIC_OUTCOME_UNEXPOSED_INPUT"
        verify_manifest(directory, manifest, full=full)
        if sha256_file(directory / "CONTENT_IDENTITY.json") != content:
            raise RuntimeError(f"source content identity hash drift: {package}")
        rows.append(
            {
                "source_id": source_id,
                "package": package,
                "manifest_sha256": manifest,
                "content_identity_sha256": content,
                "access": access,
                "full_payload_rehash": int(full),
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    if sha256_file(ROOT / "scripts" / "bj180_team_matchup_core.py") != SOURCE_180_CORE_SHA256:
        raise RuntimeError("accepted #180 core hash drift")
    if sha256_file(ROOT / "scripts" / "freeze_bj180_team_matchup_gate_a.py") != SOURCE_180_RUNNER_SHA256:
        raise RuntimeError("accepted #180 runner hash drift")
    return rows


def verify_external_86_if_present() -> None:
    candidates = [
        ROOT / "results",
        ROOT.parent.parent / "results",
        Path("/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/strategy/results"),
    ]
    for base in candidates:
        gate_a = base / str(SOURCE_86["gate_a_package"]) / "SHA256SUMS.json"
        recovery = base / str(SOURCE_86["gate_b_recovery_package"]) / "SHA256SUMS.json"
        if gate_a.is_file() and recovery.is_file():
            if sha256_file(gate_a) != SOURCE_86["gate_a_manifest_sha256"]:
                raise RuntimeError("#86 external Gate-A receipt drift")
            if sha256_file(recovery) != SOURCE_86["gate_b_recovery_manifest_sha256"]:
                raise RuntimeError("#86 external Gate-B recovery receipt drift")
            return


def canonical_role_by_match(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    fields = (
        "p_model3",
        "p_model1",
        "p_model0",
        "p_market_cal3",
        "p_market_cal1",
        "p_market_cal0",
        "q_weight3",
        "q_weight1",
        "q_weight0",
        "e_sp",
    )
    output: dict[str, Mapping[str, str]] = {}
    for row in rows:
        match_id = row["match_id"]
        if match_id in output and any(output[match_id][field] != row[field] for field in fields):
            raise RuntimeError(f"role-vector probability drift: {match_id}")
        output.setdefault(match_id, row)
    if len(output) != UNIQUE_MATCHES:
        raise RuntimeError(f"canonical role denominator drift: {len(output)}")
    return output


def predicted_prices(role: Mapping[str, str]) -> tuple[float, float, float]:
    probability = [float(role[f"p_model{code}"]) for code in CODE_ORDER]
    q = [float(role["e_sp"]) * float(role[f"q_weight{code}"]) for code in CODE_ORDER]
    return tuple(q[index] / probability[index] for index in range(3))  # type: ignore[return-value]


def code_features(delta: Mapping[str, float]) -> dict[str, object]:
    favored = min(CODE_ORDER, key=lambda code: (-float(delta[code]), CODE_ORDER.index(code)))
    omitted = min(CODE_ORDER, key=lambda code: (float(delta[code]), CODE_ORDER.index(code)))
    extreme = min(CODE_ORDER, key=lambda code: (-abs(float(delta[code])), CODE_ORDER.index(code)))
    return {
        "favored_code": favored,
        "omitted_code": omitted,
        "extreme_code": extreme,
        "extreme_sign": "POSITIVE" if delta[extreme] >= 0 else "NEGATIVE",
        "magnitude": abs(float(delta[extreme])),
    }


def dispersion_se(bucket: str) -> float:
    return {"D_LOW": 0.06, "D_MID": 0.10, "D_HIGH": 0.16}[bucket]


def line_stratum(value: object) -> str:
    number = float(value)
    rounded = round(number)
    if abs(number - rounded) <= 1e-9 and rounded in {-2, -1, 0, 1, 2}:
        return f"+{rounded}" if rounded > 0 else str(rounded)
    return "OTHER"


def build_latent_and_estimator_freeze(
    database: Path,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """Replay the accepted #180 target-safe state and expose its latent calls."""

    runner180 = load_module(
        "bj190_accepted_180_runner",
        ROOT / "scripts" / "freeze_bj180_team_matchup_gate_a.py",
    )
    accepted_core = runner180.load_core()
    source = runner180.load_sources()
    roles = list(source["roles"])
    candidates = list(source["candidates"])
    source_selection = list(source["selection"])
    cutoffs, by_match_cutoff = runner180.issue_cutoffs(roles, accepted_core)
    targets = runner180.read_target_rows(database, set(by_match_cutoff))
    accepted180 = {
        row["match_id"]: row
        for row in read_gzip(
            ROOT / "results" / "bj180_gate_a_preoutcome_v2" / "match_probability_freeze.csv.gz"
        )
    }
    accepted179 = {
        row["match_id"]: row
        for row in read_gzip(
            ROOT / "results" / "bj179_gate_a_preoutcome_v2" / "match_probability_freeze.csv.gz"
        )
    }
    canonical_roles = canonical_role_by_match(roles)
    if not (
        len(accepted180)
        == len(accepted179)
        == len(canonical_roles)
        == len(targets)
        == UNIQUE_MATCHES
    ):
        raise RuntimeError("accepted probability denominator drift")

    targets_by_cutoff: dict[object, list[int]] = defaultdict(list)
    for match_id, cutoff in by_match_cutoff.items():
        targets_by_cutoff[cutoff].append(match_id)
    state = accepted_core.TeamMatchupState()
    maximum_cutoff = max(targets_by_cutoff)
    history = iter(runner180.historical_rows(database, maximum_cutoff.isoformat(sep=" ")))
    pending = next(history, None)
    latent_rows: list[dict[str, object]] = []
    estimator_rows: list[dict[str, object]] = []

    for cutoff in sorted(targets_by_cutoff):
        while pending is not None and runner180.history_row_is_available(
            accepted_core.parse_ts(pending["kickoff_ts"]), cutoff
        ):
            state.update(pending)
            pending = next(history, None)
        summary = state.summary()
        for match_id in sorted(targets_by_cutoff[cutoff]):
            target = targets[match_id]
            accepted_row = accepted180[str(match_id)]
            market_row = accepted179[str(match_id)]
            role = canonical_roles[str(match_id)]
            if FORBIDDEN_TARGET_FIELDS.intersection(target):
                raise RuntimeError(f"target projection exposes forbidden field: {match_id}")

            families, diagnostics, captured = core190.capture_family_latents(
                state, target, cutoff, accepted_core
            )
            family_distributions: dict[str, dict[int, float]] = {}
            for family in core190.FAMILY_ORDER:
                raw_home, raw_away, handicap, max_goals = captured[family]
                effective_home = min(6.0, max(0.08, raw_home))
                effective_away = min(6.0, max(0.08, raw_away))
                prior = core190.poisson_difference_distribution(
                    effective_home, effective_away, max_goals=max_goals
                )
                distribution = (
                    core190.h2h_difference_distribution(state, target, prior)
                    if family == "H2H_PRIOR"
                    else prior
                )
                family_distributions[family] = distribution
                mapped = core190.mapped_probabilities(distribution, handicap)
                accepted = tuple(
                    float(accepted_row[f"family_{family.lower()}_p{code}"])
                    for code in CODE_ORDER
                )
                error = core190.probability_reconciliation_error(mapped, accepted)
                if error > core190.RECONCILIATION_TOLERANCE:
                    raise RuntimeError(
                        f"#180 family reconciliation drift {match_id}/{family}: {error}"
                    )
                latent_rows.append(
                    {
                        "match_id": match_id,
                        "issue": target["issue"],
                        "match_idx": target["match_idx"],
                        "year": target["year"],
                        "league": target["league"],
                        "feature_cutoff_ts": cutoff.isoformat(sep=" "),
                        "estimator": family,
                        "mapping_type": "EMPIRICAL_H2H_PLUS_12_POISSON_PRIOR"
                        if family == "H2H_PRIOR"
                        else "INDEPENDENT_POISSON_TRUNCATED",
                        "lambda_home_raw_call": compact(raw_home),
                        "lambda_away_raw_call": compact(raw_away),
                        "lambda_home_effective": compact(effective_home),
                        "lambda_away_effective": compact(effective_away),
                        "raw_expected_margin_lambda_difference": compact(
                            effective_home - effective_away
                        ),
                        "distribution_expected_margin": compact(
                            core190.expected_margin(distribution)
                        ),
                        "handicap_line_norm": compact(handicap),
                        "max_goals_inclusive": max_goals,
                        "tail_policy": "exclude joint goal cells where either score > 12; normalize retained mass",
                        "score_difference_min": -max_goals,
                        "score_difference_max": max_goals,
                        "score_difference_distribution_json": core190.canonical_json(
                            core190.distribution_payload(distribution)
                        ).decode(),
                        "mapped_p3": compact(mapped[0]),
                        "mapped_p1": compact(mapped[1]),
                        "mapped_p0": compact(mapped[2]),
                        "accepted_p3": accepted_row[f"family_{family.lower()}_p3"],
                        "accepted_p1": accepted_row[f"family_{family.lower()}_p1"],
                        "accepted_p0": accepted_row[f"family_{family.lower()}_p0"],
                        "max_abs_reconciliation_error": compact(error),
                        "reconciliation_status": "PASS",
                        "detector_role": "PURE_TEAM_COMPONENT_ABLATION",
                        "outcome_boundary": OUTCOME_BOUNDARY,
                    }
                )

            t1_weights = accepted_core.CONFIGURATIONS[accepted_core.PRIMARY_CONFIG][
                "weights"
            ]
            t1_lambda_home, t1_lambda_away = core190.weighted_family_intensities(
                captured, t1_weights
            )
            raw_expected_margin = t1_lambda_home - t1_lambda_away
            line_residual_mu = raw_expected_margin + float(
                target["handicap_line_norm"]
            )
            component_margins = {
                family: min(6.0, max(0.08, float(captured[family][0])))
                - min(6.0, max(0.08, float(captured[family][1])))
                for family in core190.FAMILY_ORDER
            }
            margin_uncertainty = math.sqrt(
                math.fsum(
                    float(t1_weights[family])
                    * (component_margins[family] - raw_expected_margin) ** 2
                    for family in core190.FAMILY_ORDER
                )
                + 1.0 / (int(diagnostics["min_history_n"]) + 12.0)
            )
            line_residual_z = line_residual_mu / max(1e-12, margin_uncertainty)

            primary = tuple(
                float(accepted_row[f"team_primary_p{code}"]) for code in CODE_ORDER
            )
            primary_distribution = core190.group_mass_calibrated_distribution(
                family_distributions,
                accepted_core.CONFIGURATIONS[accepted_core.PRIMARY_CONFIG]["weights"],
                primary,
                float(target["handicap_line_norm"]),
            )
            primary_mapped = core190.mapped_probabilities(
                primary_distribution, float(target["handicap_line_norm"])
            )
            primary_error = core190.probability_reconciliation_error(
                primary_mapped, primary
            )
            if primary_error > core190.RECONCILIATION_TOLERANCE:
                raise RuntimeError(f"#180 primary reconciliation drift {match_id}")
            latent_rows.append(
                {
                    "match_id": match_id,
                    "issue": target["issue"],
                    "match_idx": target["match_idx"],
                    "year": target["year"],
                    "league": target["league"],
                    "feature_cutoff_ts": cutoff.isoformat(sep=" "),
                    "estimator": "T1_DEEP_TEAM",
                    "mapping_type": "GROUP_MASS_CALIBRATED_TEAM_LOG_POOL",
                    "lambda_home_raw_call": compact(t1_lambda_home),
                    "lambda_away_raw_call": compact(t1_lambda_away),
                    "lambda_home_effective": compact(t1_lambda_home),
                    "lambda_away_effective": compact(t1_lambda_away),
                    "raw_expected_margin_lambda_difference": compact(
                        raw_expected_margin
                    ),
                    "distribution_expected_margin": compact(
                        core190.expected_margin(primary_distribution)
                    ),
                    "handicap_line_norm": target["handicap_line_norm"],
                    "max_goals_inclusive": core190.MAX_GOALS,
                    "tail_policy": "weighted family score-difference log-pool shape; within-code masses rescaled to accepted p3/p1/p0",
                    "score_difference_min": -core190.MAX_GOALS,
                    "score_difference_max": core190.MAX_GOALS,
                    "score_difference_distribution_json": core190.canonical_json(
                        core190.distribution_payload(primary_distribution)
                    ).decode(),
                    "mapped_p3": compact(primary_mapped[0]),
                    "mapped_p1": compact(primary_mapped[1]),
                    "mapped_p0": compact(primary_mapped[2]),
                    "accepted_p3": accepted_row["team_primary_p3"],
                    "accepted_p1": accepted_row["team_primary_p1"],
                    "accepted_p0": accepted_row["team_primary_p0"],
                    "max_abs_reconciliation_error": compact(primary_error),
                    "reconciliation_status": "PASS",
                    "detector_role": "FUNDAMENTAL_INDEPENDENT_CONTROLLING",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )

            fundamental = {
                code: float(accepted_row[f"team_primary_p{code}"])
                for code in CODE_ORDER
            }
            calibrated = {
                code: float(market_row[f"market_p{code}"]) for code in CODE_ORDER
            }
            price_complete = int(market_row["target_beijing_pred_sp_source_complete"])
            price_values: tuple[float, float, float] | None = None
            consensus: dict[str, float] | None = None
            if price_complete:
                price_values = predicted_prices(role)
                consensus_vector = core190.no_vig_from_prices(price_values)
                consensus = dict(zip(CODE_ORDER, consensus_vector, strict=True))
            fund_delta = (
                {code: fundamental[code] - consensus[code] for code in CODE_ORDER}
                if consensus
                else None
            )
            calibrated_delta = (
                {code: calibrated[code] - consensus[code] for code in CODE_ORDER}
                if consensus
                else None
            )
            market_se = dispersion_se(market_row["market_signature_dispersion"])
            history_n = int(diagnostics["min_history_n"])
            training_n = int(market_row["training_raw_league_n"])
            fund_z: dict[str, float] = {}
            calibrated_z: dict[str, float] = {}
            if consensus and fund_delta and calibrated_delta:
                for code in CODE_ORDER:
                    fund_model_se = math.sqrt(
                        fundamental[code] * (1.0 - fundamental[code]) / (history_n + 12.0)
                    )
                    calibrated_model_se = math.sqrt(
                        calibrated[code] * (1.0 - calibrated[code]) / (training_n + 24.0)
                    )
                    fund_z[code] = fund_delta[code] / math.hypot(fund_model_se, market_se)
                    calibrated_z[code] = calibrated_delta[code] / math.hypot(
                        calibrated_model_se, market_se
                    )
            fund_features = code_features(fund_delta) if fund_delta else {}
            calibrated_features = code_features(calibrated_delta) if calibrated_delta else {}
            price_identity = (
                core190.canonical_hash(
                    {
                        "source_package": "bj179_gate_a_preoutcome_v2",
                        "match_id": str(match_id),
                        "prices": [f"{value:.12f}" for value in price_values or ()],
                        "source_complete": price_complete,
                    }
                )
                if price_complete
                else ""
            )
            estimator_rows.append(
                {
                    "match_id": match_id,
                    "issue": target["issue"],
                    "match_idx": target["match_idx"],
                    "year": target["year"],
                    "fold": f"OOS_{target['year']}",
                    "issue_instance": f"{target['issue']}@OOS_{target['year']}",
                    "kickoff_ts": target["kickoff_ts"],
                    "feature_cutoff_ts": cutoff.isoformat(sep=" "),
                    "league": target["league"],
                    "home_team_id": target["home_team_id"],
                    "away_team_id": target["away_team_id"],
                    "native_handicap_line": compact(float(target["handicap_line_norm"])),
                    "line_stratum": line_stratum(target["handicap_line_norm"]),
                    "history_training_rows": summary["training_rows"],
                    "min_history_n": history_n,
                    "market_signature_breadth": market_row["market_signature_breadth"],
                    "market_signature_dispersion": market_row["market_signature_dispersion"],
                    "market_uncertainty_proxy": compact(market_se),
                    "target_safe_price_status": "AVAILABLE" if consensus else "UNAVAILABLE",
                    "target_safe_price_unavailable_reason": ""
                    if consensus
                    else "FROZEN_BJ_PREDICTED_SP_SOURCE_INCOMPLETE",
                    "target_safe_price_identity": price_identity,
                    "predicted_sp3": compact(price_values[0]) if price_values else "",
                    "predicted_sp1": compact(price_values[1]) if price_values else "",
                    "predicted_sp0": compact(price_values[2]) if price_values else "",
                    **{
                        f"consensus_p{code}": compact(consensus[code]) if consensus else ""
                        for code in CODE_ORDER
                    },
                    **{f"fundamental_p{code}": compact(fundamental[code]) for code in CODE_ORDER},
                    **{f"calibrated_p{code}": compact(calibrated[code]) for code in CODE_ORDER},
                    **{
                        f"fundamental_delta_p{code}": compact(fund_delta[code]) if fund_delta else ""
                        for code in CODE_ORDER
                    },
                    **{
                        f"calibrated_delta_p{code}": compact(calibrated_delta[code])
                        if calibrated_delta
                        else ""
                        for code in CODE_ORDER
                    },
                    **{
                        f"fundamental_z{code}": compact(fund_z[code]) if fund_z else ""
                        for code in CODE_ORDER
                    },
                    **{
                        f"calibrated_z{code}": compact(calibrated_z[code])
                        if calibrated_z
                        else ""
                        for code in CODE_ORDER
                    },
                    "fundamental_favored_code": fund_features.get("favored_code", ""),
                    "fundamental_omitted_code": fund_features.get("omitted_code", ""),
                    "fundamental_extreme_code": fund_features.get("extreme_code", ""),
                    "fundamental_extreme_sign": fund_features.get("extreme_sign", ""),
                    "fundamental_abs_delta_p": compact(fund_features.get("magnitude"))
                    if fund_features
                    else "",
                    "fundamental_abs_z": compact(
                        max((abs(value) for value in fund_z.values()), default=math.nan)
                    )
                    if fund_z
                    else "",
                    "calibrated_favored_code": calibrated_features.get("favored_code", ""),
                    "calibrated_omitted_code": calibrated_features.get("omitted_code", ""),
                    "calibrated_extreme_code": calibrated_features.get("extreme_code", ""),
                    "calibrated_extreme_sign": calibrated_features.get("extreme_sign", ""),
                    "calibrated_abs_delta_p": compact(calibrated_features.get("magnitude"))
                    if calibrated_features
                    else "",
                    "calibrated_abs_z": compact(
                        max((abs(value) for value in calibrated_z.values()), default=math.nan)
                    )
                    if calibrated_z
                    else "",
                    "fundamental_lambda_home": compact(t1_lambda_home),
                    "fundamental_lambda_away": compact(t1_lambda_away),
                    "fundamental_expected_raw_margin": compact(raw_expected_margin),
                    "line_residual_mu": compact(line_residual_mu),
                    "line_residual_direction": "HOME_SIDE"
                    if line_residual_mu > 1e-15
                    else "AWAY_SIDE"
                    if line_residual_mu < -1e-15
                    else "ON_LINE",
                    "abs_line_residual_mu": compact(abs(line_residual_mu)),
                    "fundamental_margin_uncertainty_proxy": compact(
                        margin_uncertainty
                    ),
                    "line_residual_z": compact(line_residual_z),
                    "consensus_expected_raw_margin": "",
                    "delta_mu": "",
                    "delta_mu_status": "UNAVAILABLE_MARKET_3WAY_DOES_NOT_IDENTIFY_RAW_MARGIN",
                    "fundamental_distribution_estimator": "T1_DEEP_TEAM_GROUP_MASS_RECONCILED_LOG_POOL",
                    "fundamental_expected_margin_method": "TEAM_PRIMARY_WEIGHTED_COMPONENT_POISSON_INTENSITIES",
                    "fundamental_single_poisson_status": "UNAVAILABLE_LOG_POOL_IS_NOT_ONE_POISSON_CALL",
                    "consensus_mapping": "NO_VIG_INVERSE_FROZEN_PREDICTED_BJ_SP",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )

    if len(estimator_rows) != UNIQUE_MATCHES:
        raise RuntimeError(f"estimator denominator drift: {len(estimator_rows)}")
    if len(latent_rows) != UNIQUE_MATCHES * (len(core190.FAMILY_ORDER) + 1):
        raise RuntimeError(f"latent denominator drift: {len(latent_rows)}")
    if any(float(row["max_abs_reconciliation_error"]) > core190.RECONCILIATION_TOLERANCE for row in latent_rows):
        raise RuntimeError("latent reconciliation tolerance failure")
    return latent_rows, estimator_rows, roles, candidates, source_selection


def threshold_rules() -> list[dict[str, object]]:
    rows = [
        {
            "threshold_rule": f"DP_{int(round(value * 1000)):03d}",
            "abs_delta_p_min": value,
            "abs_z_min": 0.0,
        }
        for value in (0.0, 0.025, 0.050, 0.075, 0.100, 0.150)
    ]
    rows.extend(
        {
            "threshold_rule": f"Z_{int(round(value * 100)):03d}",
            "abs_delta_p_min": 0.0,
            "abs_z_min": value,
        }
        for value in (0.5, 1.0, 1.5, 2.0)
    )
    rows.extend(
        [
            {
                "threshold_rule": "DP050_Z100",
                "abs_delta_p_min": 0.050,
                "abs_z_min": 1.0,
            },
            {
                "threshold_rule": "DP075_Z150",
                "abs_delta_p_min": 0.075,
                "abs_z_min": 1.5,
            },
        ]
    )
    return rows


def build_detector_grid() -> list[dict[str, object]]:
    variants = (
        "FUNDAMENTAL_INDEPENDENT",
        "CALIBRATED_MARKET_ESTIMATOR",
        "UNION",
        "MODEL_AGREEMENT",
    )
    rows: list[dict[str, object]] = []
    for variant in variants:
        for threshold in threshold_rules():
            for top_k in ("1", "2", "4", "ALL"):
                for min_history in (0, 10, 20):
                    for coverage in (
                        "TARGET_SAFE_PRICE",
                        "BROAD_MARKET_AND_TARGET_SAFE_PRICE",
                    ):
                        for uncertainty in ("NONE", "MAX_0.12"):
                            descriptor = {
                                "detector_family": "DELTA_P",
                                "estimator_variant": variant,
                                **threshold,
                                "top_k": top_k,
                                "min_history_n": min_history,
                                "coverage_gate": coverage,
                                "uncertainty_gate": uncertainty,
                            }
                            rows.append(
                                {
                                    "policy_id": "DP_" + core190.canonical_hash(descriptor)[:20],
                                    **descriptor,
                                    "abs_delta_mu_min": "",
                                    "abs_line_residual_mu_min": "",
                                    "availability": "AVAILABLE",
                                    "unavailable_reason": "",
                                    "tie_break": "identity mean retained magnitude desc, retained count desc, inherited source rank asc, portfolio_id asc; match magnitude desc, match_id asc",
                                    "no_bet_rule": "zero qualifying frozen identity => zero tickets and zero stake",
                                    "outcome_boundary": OUTCOME_BOUNDARY,
                                }
                            )
    for threshold in (0.0, 0.25, 0.50, 0.75, 1.0):
        for top_k in ("1", "2", "4", "ALL"):
            for min_history in (0, 10, 20):
                descriptor = {
                    "detector_family": "LINE_RESIDUAL_MU",
                    "estimator_variant": "FUNDAMENTAL_INDEPENDENT",
                    "threshold_rule": f"LRMU_{int(round(threshold * 100)):03d}",
                    "abs_delta_p_min": "",
                    "abs_z_min": 0.0,
                    "top_k": top_k,
                    "min_history_n": min_history,
                    "coverage_gate": "TARGET_SAFE_PRICE",
                    "uncertainty_gate": "NONE",
                    "abs_delta_mu_min": "",
                    "abs_line_residual_mu_min": threshold,
                }
                rows.append(
                    {
                        "policy_id": "LR_" + core190.canonical_hash(descriptor)[:20],
                        **descriptor,
                        "availability": "AVAILABLE",
                        "unavailable_reason": "",
                        "tie_break": "identity mean retained absolute line residual desc, retained count desc, inherited source rank asc, portfolio_id asc; match magnitude desc, match_id asc",
                        "no_bet_rule": "zero qualifying frozen identity => zero tickets and zero stake",
                        "outcome_boundary": OUTCOME_BOUNDARY,
                    }
                )
    for threshold in (0.0, 0.25, 0.50, 0.75, 1.0):
        for top_k in ("1", "2", "4", "ALL"):
            for min_history in (0, 10, 20):
                descriptor = {
                    "detector_family": "DELTA_MU",
                    "estimator_variant": "FUNDAMENTAL_INDEPENDENT",
                    "threshold_rule": f"DMU_{int(round(threshold * 100)):03d}",
                    "abs_delta_p_min": "",
                    "abs_z_min": "",
                    "top_k": top_k,
                    "min_history_n": min_history,
                    "coverage_gate": "TARGET_SAFE_PRICE",
                    "uncertainty_gate": "NONE",
                    "abs_delta_mu_min": threshold,
                    "abs_line_residual_mu_min": "",
                }
                rows.append(
                    {
                        "policy_id": "DM_" + core190.canonical_hash(descriptor)[:20],
                        **descriptor,
                        "availability": "DIAGNOSTIC_UNAVAILABLE",
                        "unavailable_reason": "HANDICAP_CONSENSUS_RAW_MARGIN_NOT_IDENTIFIABLE_FROM_TARGET_SAFE_THREE_WAY_PRICES",
                        "tie_break": "not applicable",
                        "no_bet_rule": "unavailable detector executes zero tickets and zero stake",
                        "outcome_boundary": OUTCOME_BOUNDARY,
                    }
                )
    if len(rows) != 2424 or len({row["policy_id"] for row in rows}) != len(rows):
        raise RuntimeError(f"detector grid drift: {len(rows)}")
    return rows


def _float(row: Mapping[str, object], field: str) -> float | None:
    value = row.get(field)
    return None if value in (None, "") else float(value)


def detector_metric(
    row: Mapping[str, object], variant: str, detector_family: str
) -> dict[str, object] | None:
    if row["target_safe_price_status"] != "AVAILABLE":
        return None

    if detector_family == "LINE_RESIDUAL_MU":
        value = float(row["line_residual_mu"])
        if abs(value) <= 1e-15:
            return None
        favored = "3" if value > 0 else "0"
        omitted = "0" if value > 0 else "3"
        return {
            "favored_code": favored,
            "omitted_code": omitted,
            "extreme_code": favored,
            "extreme_sign": 1,
            "magnitude": abs(value),
            "abs_z": abs(float(row["line_residual_z"])),
            "delta": {},
            "z": {},
            "estimator_source": "FUNDAMENTAL_T1_DEEP_TEAM_LINE_RESIDUAL",
        }
    if detector_family != "DELTA_P":
        raise RuntimeError(f"unavailable detector reached execution: {detector_family}")

    def one(prefix: str) -> dict[str, object]:
        delta = {code: float(row[f"{prefix}_delta_p{code}"]) for code in CODE_ORDER}
        z = {code: float(row[f"{prefix}_z{code}"]) for code in CODE_ORDER}
        features = code_features(delta)
        features.update(
            {
                "abs_z": max(abs(value) for value in z.values()),
                "delta": delta,
                "z": z,
                "estimator_source": prefix.upper(),
            }
        )
        return features

    fundamental = one("fundamental")
    calibrated = one("calibrated")
    if variant == "FUNDAMENTAL_INDEPENDENT":
        return fundamental
    if variant == "CALIBRATED_MARKET_ESTIMATOR":
        return calibrated
    if variant == "UNION":
        return min(
            (fundamental, calibrated),
            key=lambda metric: (
                -float(metric["magnitude"]),
                0 if metric["estimator_source"] == "FUNDAMENTAL" else 1,
            ),
        )
    if variant == "MODEL_AGREEMENT":
        if (
            fundamental["favored_code"] != calibrated["favored_code"]
            or fundamental["omitted_code"] != calibrated["omitted_code"]
        ):
            return None
        weaker = min(
            (fundamental, calibrated), key=lambda metric: float(metric["magnitude"])
        )
        features = dict(weaker)
        features["magnitude"] = min(
            float(fundamental["magnitude"]), float(calibrated["magnitude"])
        )
        features["abs_z"] = min(
            float(fundamental["abs_z"]), float(calibrated["abs_z"])
        )
        features["estimator_source"] = "STRICT_MODEL_AGREEMENT_NO_BLEND"
        return features
    raise RuntimeError(f"unknown estimator variant: {variant}")


def metric_passes(
    row: Mapping[str, object], metric: Mapping[str, object], policy: Mapping[str, object]
) -> bool:
    if float(metric["magnitude"]) <= 1e-15:
        return False
    if policy["detector_family"] == "DELTA_P":
        if float(metric["magnitude"]) + 1e-15 < float(
            policy["abs_delta_p_min"]
        ):
            return False
    elif policy["detector_family"] == "LINE_RESIDUAL_MU":
        if float(metric["magnitude"]) + 1e-15 < float(
            policy["abs_line_residual_mu_min"]
        ):
            return False
    else:
        raise RuntimeError(f"unavailable policy reached execution: {policy['policy_id']}")
    if float(metric["abs_z"]) + 1e-15 < float(policy["abs_z_min"]):
        return False
    if int(row["min_history_n"]) < int(policy["min_history_n"]):
        return False
    if (
        policy["coverage_gate"] == "BROAD_MARKET_AND_TARGET_SAFE_PRICE"
        and row["market_signature_breadth"] != "B05_19"
    ):
        return False
    if policy["uncertainty_gate"] == "MAX_0.12" and float(
        row["market_uncertainty_proxy"]
    ) > 0.12:
        return False
    return True


def retained_metrics(
    match_ids: Sequence[str],
    estimator_by_match: Mapping[str, Mapping[str, object]],
    policy: Mapping[str, object],
) -> list[dict[str, object]] | None:
    rows = []
    for match_id in match_ids:
        source = estimator_by_match[match_id]
        metric = detector_metric(
            source,
            str(policy["estimator_variant"]),
            str(policy["detector_family"]),
        )
        if metric is not None and metric_passes(source, metric, policy):
            rows.append({"match_id": match_id, "match_row": source, **metric})
    rows.sort(key=lambda row: (-float(row["magnitude"]), int(row["match_id"])))
    if policy["top_k"] == "ALL":
        return rows or None
    required = int(policy["top_k"])
    return rows[:required] if len(rows) >= required else None


def build_candidate_membership(
    roles: Sequence[Mapping[str, str]],
    candidates: Sequence[Mapping[str, str]],
) -> tuple[
    list[dict[str, object]],
    dict[str, list[dict[str, object]]],
    dict[tuple[str, str], list[str]],
]:
    candidate_by_key = {
        (row["issue_instance"], row["portfolio_id"]): row for row in candidates
    }
    by_key: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in roles:
        by_key[(row["issue_instance"], row["portfolio_id"])].append(row)
    if set(by_key) != set(candidate_by_key):
        raise RuntimeError("candidate role membership key drift")
    output = []
    by_issue: dict[str, list[dict[str, object]]] = defaultdict(list)
    membership: dict[tuple[str, str], list[str]] = {}
    for key, candidate in sorted(candidate_by_key.items()):
        frozen_roles = sorted(by_key[key], key=lambda row: int(row["selection_rank"]))
        if len(frozen_roles) != 7:
            raise RuntimeError(f"candidate role count drift: {key}")
        match_ids = [row["match_id"] for row in frozen_roles]
        membership[key] = match_ids
        candidate_entry = {
            "issue": candidate["issue"],
            "year": candidate["year"],
            "fold": candidate["fold"],
            "issue_instance": candidate["issue_instance"],
            "portfolio_id": candidate["portfolio_id"],
            "source_selector_rank": int(candidate["source_selector_rank"]),
            "identity_fingerprint": candidate["identity_fingerprint"],
            "selected_match_ids": "|".join(match_ids),
        }
        by_issue[candidate["issue_instance"]].append(candidate_entry)
        for role in frozen_roles:
            output.append(
                {
                    **candidate_entry,
                    "match_id": role["match_id"],
                    "match_idx": role["match_idx"],
                    "selection_rank": role["selection_rank"],
                    "kickoff_ts": role["kickoff_ts"],
                    "role_probability_identity_sha256": core190.canonical_hash(
                        {
                            field: role[field]
                            for field in (
                                "p_model3",
                                "p_model1",
                                "p_model0",
                                "p_market_cal3",
                                "p_market_cal1",
                                "p_market_cal0",
                                "q_weight3",
                                "q_weight1",
                                "q_weight0",
                                "e_sp",
                            )
                        }
                    ),
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    if len(output) != CANDIDATE_IDENTITIES * 7 or len(by_issue) != PARTICIPATING_ISSUES:
        raise RuntimeError("candidate membership denominator drift")
    for values in by_issue.values():
        values.sort(key=lambda row: (int(row["source_selector_rank"]), row["portfolio_id"]))
    return output, by_issue, membership


def build_policy_forecasts(
    detector_grid: Sequence[Mapping[str, object]],
    estimator_rows: Sequence[Mapping[str, object]],
    candidates_by_issue: Mapping[str, Sequence[Mapping[str, object]]],
    membership: Mapping[tuple[str, str], Sequence[str]],
    source_selection: Sequence[Mapping[str, str]],
    selection_output: Path,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    int,
]:
    estimator_by_match = {str(row["match_id"]): row for row in estimator_rows}
    b0_rows = [row for row in source_selection if row["arm"] == "B0_BEST_FULL"]
    if len(b0_rows) != COHORT_ISSUES:
        raise RuntimeError("B0 issue census drift")
    issue_census = {row["issue_instance"]: row for row in b0_rows}
    b0_selected = {
        row["issue_instance"]: row["selected_portfolio_id"]
        for row in b0_rows
        if row["policy_status"] == "SELECTED_PREOUTCOME"
    }
    if len(b0_selected) != PARTICIPATING_ISSUES:
        raise RuntimeError("B0 participating issue drift")

    selection_sink = GzipRowSink(selection_output)
    forecast_rows: list[dict[str, object]] = []
    strata_rows: list[dict[str, object]] = []
    for policy in detector_grid:
        if policy["availability"] != "AVAILABLE":
            forecast_rows.append(
                {
                    "policy_id": policy["policy_id"],
                    "detector_family": policy["detector_family"],
                    "estimator_variant": policy["estimator_variant"],
                    "threshold_rule": policy["threshold_rule"],
                    "top_k": policy["top_k"],
                    "min_history_n": policy["min_history_n"],
                    "coverage_gate": policy["coverage_gate"],
                    "uncertainty_gate": policy["uncertainty_gate"],
                    "cohort_issue_count": COHORT_ISSUES,
                    "source_candidate_issue_count": PARTICIPATING_ISSUES,
                    "selected_issue_count": 0,
                    "no_bet_issue_count": COHORT_ISSUES,
                    "selected_identity_count": 0,
                    "selected_retained_match_count": 0,
                    "identity_changed_from_b0_count": 0,
                    "b0_direction_available_issue_count": 0,
                    "factorial_common_issue_count": 0,
                    "native_planned_stake_yuan": 0,
                    "matched_equal_budget_stake_yuan": 0,
                    "forecast_status": "DIAGNOSTIC_UNAVAILABLE",
                    "unavailable_reason": policy["unavailable_reason"],
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
            for line in LINE_STRATA:
                for direction in DIRECTION_STRATA:
                    strata_rows.append(
                        {
                            "policy_id": policy["policy_id"],
                            "line_stratum": line,
                            "direction_stratum": direction,
                            "selected_match_count": 0,
                            "selected_issue_count": 0,
                            "forecast_status": "DIAGNOSTIC_UNAVAILABLE",
                            "outcome_boundary": OUTCOME_BOUNDARY,
                        }
                    )
            continue

        selected_issues = 0
        retained_match_count = 0
        changed_count = 0
        b0_direction_count = 0
        common_count = 0
        line_direction_matches: Counter[tuple[str, str]] = Counter()
        line_direction_issues: dict[tuple[str, str], set[str]] = defaultdict(set)

        for issue_instance in sorted(candidates_by_issue):
            candidates = candidates_by_issue[issue_instance]
            evaluated: list[
                tuple[Mapping[str, object], list[dict[str, object]], float]
            ] = []
            for candidate in candidates:
                retained = retained_metrics(
                    membership[(issue_instance, str(candidate["portfolio_id"]))],
                    estimator_by_match,
                    policy,
                )
                if retained:
                    score = math.fsum(float(row["magnitude"]) for row in retained) / len(
                        retained
                    )
                    evaluated.append((candidate, retained, score))
            selected: Mapping[str, object] | None = None
            selected_retained: list[dict[str, object]] = []
            selected_score: float | None = None
            if evaluated:
                selected, selected_retained, selected_score = min(
                    evaluated,
                    key=lambda item: (
                        -item[2],
                        -len(item[1]),
                        int(item[0]["source_selector_rank"]),
                        str(item[0]["portfolio_id"]),
                    ),
                )
            b0_portfolio = b0_selected[issue_instance]
            b0_retained = retained_metrics(
                membership[(issue_instance, b0_portfolio)], estimator_by_match, policy
            )
            if b0_retained:
                b0_direction_count += 1
            if selected is not None:
                selected_issues += 1
                retained_match_count += len(selected_retained)
                if str(selected["portfolio_id"]) != b0_portfolio:
                    changed_count += 1
                if b0_retained:
                    common_count += 1
                strongest = selected_retained[0]
                for retained in selected_retained:
                    source_row = retained["match_row"]
                    key = (
                        str(source_row["line_stratum"]),
                        str(retained["favored_code"]),
                    )
                    line_direction_matches[key] += 1
                    line_direction_issues[key].add(issue_instance)
                selection_sink.emit(
                    {
                        "policy_id": policy["policy_id"],
                        "issue": selected["issue"],
                        "year": selected["year"],
                        "fold": selected["fold"],
                        "issue_instance": issue_instance,
                        "policy_status": "SELECTED_PREOUTCOME",
                        "selected_portfolio_id": selected["portfolio_id"],
                        "selected_identity_fingerprint": selected["identity_fingerprint"],
                        "inherited_b0_portfolio_id": b0_portfolio,
                        "identity_changed_from_b0": int(
                            str(selected["portfolio_id"]) != b0_portfolio
                        ),
                        "eligible_candidate_identity_count": len(evaluated),
                        "detector_identity_score": compact(selected_score),
                        "retained_match_count": len(selected_retained),
                        "retained_match_ids": "|".join(
                            str(row["match_id"]) for row in selected_retained
                        ),
                        "strongest_match_id": strongest["match_id"],
                        "strongest_magnitude": compact(float(strongest["magnitude"])),
                        "strongest_abs_z": compact(float(strongest["abs_z"])),
                        "strongest_favored_code": strongest["favored_code"],
                        "strongest_omitted_code": strongest["omitted_code"],
                        "strongest_estimator_source": strongest["estimator_source"],
                        "b0_direction_status": "AVAILABLE" if b0_retained else "NO_SIGNAL",
                        "b0_direction_match_id": b0_retained[0]["match_id"]
                        if b0_retained
                        else "",
                        "b0_direction_favored_code": b0_retained[0]["favored_code"]
                        if b0_retained
                        else "",
                        "b0_direction_omitted_code": b0_retained[0]["omitted_code"]
                        if b0_retained
                        else "",
                        "full_ticket_count": FULL_TICKETS,
                        "directional_ticket_count": FULL_TICKETS,
                        "equal_budget_stake_yuan": FULL_STAKE_YUAN,
                        "outcome_boundary": OUTCOME_BOUNDARY,
                    }
                )
            else:
                census = issue_census[issue_instance]
                selection_sink.emit(
                    {
                        "policy_id": policy["policy_id"],
                        "issue": census["issue"],
                        "year": census["year"],
                        "fold": census["fold"],
                        "issue_instance": issue_instance,
                        "policy_status": "NO_BET_FROZEN",
                        "selected_portfolio_id": "",
                        "selected_identity_fingerprint": "",
                        "inherited_b0_portfolio_id": b0_portfolio,
                        "identity_changed_from_b0": 0,
                        "eligible_candidate_identity_count": 0,
                        "detector_identity_score": "",
                        "retained_match_count": 0,
                        "retained_match_ids": "",
                        "strongest_match_id": "",
                        "strongest_magnitude": "",
                        "strongest_abs_z": "",
                        "strongest_favored_code": "",
                        "strongest_omitted_code": "",
                        "strongest_estimator_source": "",
                        "b0_direction_status": "AVAILABLE" if b0_retained else "NO_SIGNAL",
                        "b0_direction_match_id": b0_retained[0]["match_id"]
                        if b0_retained
                        else "",
                        "b0_direction_favored_code": b0_retained[0]["favored_code"]
                        if b0_retained
                        else "",
                        "b0_direction_omitted_code": b0_retained[0]["omitted_code"]
                        if b0_retained
                        else "",
                        "full_ticket_count": 0,
                        "directional_ticket_count": 0,
                        "equal_budget_stake_yuan": 0,
                        "outcome_boundary": OUTCOME_BOUNDARY,
                    }
                )

        forecast_rows.append(
            {
                "policy_id": policy["policy_id"],
                "detector_family": policy["detector_family"],
                "estimator_variant": policy["estimator_variant"],
                "threshold_rule": policy["threshold_rule"],
                "top_k": policy["top_k"],
                "min_history_n": policy["min_history_n"],
                "coverage_gate": policy["coverage_gate"],
                "uncertainty_gate": policy["uncertainty_gate"],
                "cohort_issue_count": COHORT_ISSUES,
                "source_candidate_issue_count": PARTICIPATING_ISSUES,
                "selected_issue_count": selected_issues,
                "no_bet_issue_count": COHORT_ISSUES - selected_issues,
                "selected_identity_count": selected_issues,
                "selected_retained_match_count": retained_match_count,
                "identity_changed_from_b0_count": changed_count,
                "b0_direction_available_issue_count": b0_direction_count,
                "factorial_common_issue_count": common_count,
                "native_planned_stake_yuan": selected_issues * FULL_STAKE_YUAN,
                "matched_equal_budget_stake_yuan": common_count * FULL_STAKE_YUAN,
                "forecast_status": "AVAILABLE",
                "unavailable_reason": "",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
        for line in LINE_STRATA:
            for direction in DIRECTION_STRATA:
                key = (line, direction)
                strata_rows.append(
                    {
                        "policy_id": policy["policy_id"],
                        "line_stratum": line,
                        "direction_stratum": direction,
                        "selected_match_count": line_direction_matches[key],
                        "selected_issue_count": len(line_direction_issues[key]),
                        "forecast_status": "AVAILABLE",
                        "outcome_boundary": OUTCOME_BOUNDARY,
                    }
                )

    available_policy_count = sum(row["availability"] == "AVAILABLE" for row in detector_grid)
    selection_sink.close()
    if selection_sink.count != available_policy_count * PARTICIPATING_ISSUES:
        raise RuntimeError(f"policy selection denominator drift: {selection_sink.count}")
    if len(forecast_rows) != len(detector_grid):
        raise RuntimeError("policy forecast denominator drift")
    if len(strata_rows) != len(detector_grid) * len(LINE_STRATA) * len(DIRECTION_STRATA):
        raise RuntimeError("line-direction forecast denominator drift")
    return forecast_rows, strata_rows, selection_sink.count


def build_issue_census(source_selection: Sequence[Mapping[str, str]]) -> list[dict[str, object]]:
    rows = []
    for source in sorted(
        (row for row in source_selection if row["arm"] == "B0_BEST_FULL"),
        key=lambda row: (int(row["year"]), int(row["issue"])),
    ):
        rows.append(
            {
                "issue": source["issue"],
                "year": source["year"],
                "fold": source["fold"],
                "issue_instance": source["issue_instance"],
                "source_candidate_identity_count": source["candidate_identity_count"],
                "source_b0_status": source["policy_status"],
                "source_b0_portfolio_id": source["selected_portfolio_id"],
                "source_b0_identity_fingerprint": source["selected_identity_fingerprint"],
                "full_ticket_count": source["ticket_count"],
                "full_planned_stake_yuan": source["planned_stake_yuan"],
                "sparse_no_bet_semantics": "zero qualifying policy => 0 tickets, 0 stake, not a loss",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    if len(rows) != COHORT_ISSUES:
        raise RuntimeError("issue census denominator drift")
    return rows


def build_estimator_registry() -> list[dict[str, object]]:
    return [
        {
            "estimator": "FUNDAMENTAL_INDEPENDENT",
            "frozen_source": "#180 T1_DEEP_TEAM / TEAM_PRIMARY",
            "p_vector": "team_primary_p3/p1/p0",
            "expected_margin": "TEAM_PRIMARY-weighted mean of seven accepted effective lambda_home minus weighted lambda_away",
            "score_distribution": "family score-difference log-pool shape with within-code masses reconciled exactly to T1_DEEP_TEAM p3/p1/p0",
            "independence_status": "STRICT_PAST_TEAM_MATCH_STATE_ONLY",
            "detector_role": "CONTROLLING",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        {
            "estimator": "PURE_TEAM_COMPONENT_ABLATIONS",
            "frozen_source": "#180 seven T1_DEEP_TEAM component calls",
            "p_vector": "family_<name>_p3/p1/p0",
            "expected_margin": "component effective lambda_home-lambda_away",
            "score_distribution": "independent Poisson or H2H empirical plus 12-Poisson prior",
            "independence_status": "STRICT_PAST_TEAM_MATCH_STATE_ONLY",
            "detector_role": "DIAGNOSTIC_NOT_CONTROLLING",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        {
            "estimator": "CALIBRATED_MARKET_ESTIMATOR",
            "frozen_source": "#179 market_p = accepted calibrated market vector",
            "p_vector": "market_p3/p1/p0",
            "expected_margin": "UNAVAILABLE_MARKET_DERIVED_THREE_WAY_VECTOR",
            "score_distribution": "UNAVAILABLE",
            "independence_status": "MARKET_DERIVED_NOT_INDEPENDENT",
            "detector_role": "CONTROLLING_SEPARATE_VIEW",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        {
            "estimator": "HANDICAP_CONSENSUS",
            "frozen_source": "#179 target-safe predicted BJ SP identity plus native handicap",
            "p_vector": "normalized inverse predicted_sp3/predicted_sp1/predicted_sp0",
            "expected_margin": "UNAVAILABLE_THREE_WAY_PRICES_DO_NOT_IDENTIFY_RAW_MARGIN",
            "score_distribution": "UNAVAILABLE_NON_IDENTIFIABLE_WITHOUT_EXTRA_MODEL",
            "independence_status": "CONSENSUS_PRICE_VIEW",
            "detector_role": "CONTROLLING_COMPARATOR",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        {
            "estimator": "MODEL_AGREEMENT",
            "frozen_source": "strict intersection of FUNDAMENTAL_INDEPENDENT and CALIBRATED_MARKET_ESTIMATOR",
            "p_vector": "no blend; both favored and omitted codes must agree",
            "expected_margin": "UNAVAILABLE_BECAUSE_CONSENSUS_MARGIN_UNAVAILABLE",
            "score_distribution": "not applicable",
            "independence_status": "INTERSECTION_NOT_BLEND",
            "detector_role": "CONTROLLING_VARIANT",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
    ]


def build_estimator_provenance_registry() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    independent_features = {
        "LATENT_STRENGTH": "chronological team attack/defence EWMA and Elo",
        "HOME_AWAY_SPLIT": "chronological role-specific attack/defence EWMA",
        "ROLLING_FORM": "prior ten-match points",
        "REST_CONGESTION": "prior timestamps and prior-match counts",
        "OPPONENT_ADJUSTMENT": "prior opponent-adjusted goal residual state",
        "TEAM_INITIALIZATION": "league goal prior and team transition shrink",
        "H2H_PRIOR": "prior meetings with alpha-12 Poisson shrink",
    }
    for family, definition in independent_features.items():
        rows.append(
            {
                "estimator": "FUNDAMENTAL_INDEPENDENT",
                "source_branch": "#180 T1_DEEP_TEAM",
                "feature_family": family,
                "feature_definition": definition,
                "uses_market_input": 0,
                "uses_target_outcome": 0,
                "native_handicap_use": "POST_SCORE_GENERATION_STATE_MAPPING_ONLY",
                "detector_eligible": 1,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    for family in (
        "EURO_CALIBRATION",
        "ASIAN_CALIBRATION",
        "BEIJING_SP_CALIBRATION",
        "BJ_HANDICAP_REGIME",
        "LIQUIDITY_DRIFT",
    ):
        rows.append(
            {
                "estimator": "CALIBRATED_MARKET_ESTIMATOR",
                "source_branch": "#179 and #180 TL market-derived diagnostics",
                "feature_family": family,
                "feature_definition": "accepted chronological market-derived calibration feature",
                "uses_market_input": 1,
                "uses_target_outcome": 0,
                "native_handicap_use": "MARKET_CALIBRATION_AND_STATE_MAPPING",
                "detector_eligible": 1,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    rows.append(
        {
            "estimator": "HANDICAP_CONSENSUS",
            "source_branch": "#179 target-safe predicted BJ SP",
            "feature_family": "TARGET_SAFE_PREDICTED_BJ_SP_AND_NATIVE_LINE",
            "feature_definition": "no-vig inverse predicted 3/1/0 prices; line is capital boundary",
            "uses_market_input": 1,
            "uses_target_outcome": 0,
            "native_handicap_use": "CONSENSUS_BOUNDARY",
            "detector_eligible": 0,
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
    )
    independent = [
        row for row in rows if row["estimator"] == "FUNDAMENTAL_INDEPENDENT"
    ]
    forbidden = ("EURO", "ASIAN", "BJ_SP", "LIQUIDITY", "MARKET", "TL_")
    if len(independent) != len(core190.FAMILY_ORDER):
        raise RuntimeError("independent feature-family denominator drift")
    for row in independent:
        serialized = " ".join(
            str(row[field])
            for field in ("source_branch", "feature_family", "feature_definition")
        ).upper()
        if int(row["uses_market_input"]) or any(token in serialized for token in forbidden):
            raise RuntimeError("market-derived feature leaked into independent estimator")
    return rows


def build_attribution_arms() -> list[dict[str, object]]:
    accounting = core190.directional_ticket_accounting()
    return [
        {
            "arm": "B0_BEST_FULL",
            "match_identity": "accepted #134/#167/#170 BEST_FULL identity",
            "direction_rule": "NONE",
            "ticket_construction": "FULL_ENUMERATED",
            "ticket_count": FULL_TICKETS,
            "unique_ticket_count": FULL_TICKETS,
            "planned_stake_yuan": FULL_STAKE_YUAN,
            "attribution": "INCUMBENT",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        {
            "arm": "D_MATCH_ONLY_FULL",
            "match_identity": "sparse divergence selected frozen candidate identity",
            "direction_rule": "NONE",
            "ticket_construction": "FULL_ENUMERATED",
            "ticket_count": FULL_TICKETS,
            "unique_ticket_count": FULL_TICKETS,
            "planned_stake_yuan": FULL_STAKE_YUAN,
            "attribution": "MATCH_SELECTION_ONLY",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        {
            "arm": "D_DIRECTION_ONLY",
            "match_identity": "accepted B0 identity on the policy's eligible issue support",
            "direction_rule": "delete most-negative code at strongest eligible B0 leg; residual repeats by joint estimator probability",
            "ticket_construction": "ONE_CODE_DELETE_PLUS_DETERMINISTIC_RESIDUAL_REPEAT",
            "ticket_count": accounting["executed_ticket_count"],
            "unique_ticket_count": accounting["one_code_deleted_unique_ticket_count"],
            "planned_stake_yuan": accounting["planned_stake_yuan"],
            "attribution": "DIRECTION_ONLY_FACTORIAL_CELL",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        {
            "arm": "D_JOINT_SPARSE",
            "match_identity": "sparse divergence selected frozen candidate identity",
            "direction_rule": "same directional construction as D_DIRECTION_ONLY",
            "ticket_construction": "ONE_CODE_DELETE_PLUS_DETERMINISTIC_RESIDUAL_REPEAT",
            "ticket_count": accounting["executed_ticket_count"],
            "unique_ticket_count": accounting["one_code_deleted_unique_ticket_count"],
            "planned_stake_yuan": accounting["planned_stake_yuan"],
            "attribution": "MATCH_X_DIRECTION_FACTORIAL_CELL",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
    ]


def bootstrap_matrix_sha256(issue_count: int) -> str:
    rng = random.Random(190001)
    digest = hashlib.sha256()
    for _ in range(20_000):
        draw = [rng.getrandbits(64) for _ in range(issue_count)]
        digest.update(core190.canonical_json(draw))
        digest.update(b"\n")
    return digest.hexdigest()


def chronology_bootstrap_contract(issue_census: Sequence[Mapping[str, object]]) -> dict[str, object]:
    years = sorted({int(row["year"]) for row in issue_census})
    return {
        "chronology": {
            "issue_order": "year asc, integer issue asc, issue_instance asc",
            "folds": [f"OOS_{year}" for year in years],
            "loyo": [f"EXCLUDE_{year}" for year in years],
            "target_history_boundary": "accepted #180 expanding history with inclusive 180-minute completion embargo",
        },
        "bootstrap": {
            "method": "paired issue-level nonparametric resample on each pairwise-common support",
            "draws": 20_000,
            "seed": 190001,
            "rng": "Python random.Random MT19937",
            "master_issue_count": len(issue_census),
            "master_draw_matrix_sha256": bootstrap_matrix_sha256(len(issue_census)),
            "support_mapping": "for support size n, map each common uint64 u to floor(u*n/2^64); same u matrix for every target and both candidate/matched B0",
        },
        "stability": [
            "YEAR",
            "FOLD",
            "LOYO",
            "EX_LARGEST_ISSUE",
            "EX_LARGEST_YEAR",
            "DRAWDOWN",
            "ISSUE_GROSS_HHI",
        ],
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def output_schema_contract() -> dict[str, object]:
    return {
        "gate_b_row_keys": ["policy_id", "issue_instance", "arm"],
        "native_support_metrics": [
            "selected_issue_count",
            "ticket_count",
            "stake_yuan",
            "gross_payout_yuan",
            "net_pre_tax_yuan",
            "pre_tax_roi",
            "tax_reference_yuan",
        ],
        "matched_support_metrics": [
            "common_issue_count",
            "equal_budget_stake_yuan",
            "candidate_pre_tax_roi",
            "matched_b0_pre_tax_roi",
            "candidate_minus_b0_lift",
        ],
        "zero_stake_roi": "blank, never zero and never a loss",
        "tax": "reference only; per winning CNY2 ticket, no issue/person aggregation",
        "required_reports": [
            "full threshold-to-coverage-to-performance curve",
            "delta scatter/density and divergence calibration buckets",
            "line/direction/league/year coverage",
            "four-arm factorial decomposition",
            "YEAR/FOLD/LOYO/ex-largest/bootstrap/drawdown/HHI",
            "failure taxonomy and concrete next-step recommendation",
        ],
        "promotion_rule": "positive absolute pre-tax ROI AND positive matched-B0 lift AND multi-year/league/line stability AND strict independent EV",
        "baseline_rule": "do not demote accepted -9.47% ladder unless replacement is proven on required support",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def source_binding(source_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "issue": ISSUE,
        "contract": CONTRACT,
        "version": VERSION,
        "base_main_commit": BASE_MAIN_COMMIT,
        "database": {
            "path": str(DB_REPOSITORY_PATH),
            "sha256": SOURCE_DB_SHA256,
            "target_projection": [
                "match_id",
                "issue",
                "match_idx",
                "kickoff_ts",
                "year",
                "league",
                "home_team_id",
                "away_team_id",
                "handicap_line_norm",
            ],
            "forbidden_target_fields": sorted(FORBIDDEN_TARGET_FIELDS),
        },
        "source_86": SOURCE_86,
        "packages": {
            str(row["source_id"]): {
                "package": row["package"],
                "manifest_sha256": row["manifest_sha256"],
                "content_identity_sha256": row["content_identity_sha256"],
                "access": row["access"],
            }
            for row in source_rows
        },
        "accepted_180_core": {
            "path": "scripts/bj180_team_matchup_core.py",
            "sha256": SOURCE_180_CORE_SHA256,
            "derivation": "instrument exact existing T1_DEEP_TEAM component poisson_handicap call sites; accepted file remains unmodified",
            "independent_branch": "T1_DEEP_TEAM / TEAM_PRIMARY only",
            "excluded_market_derived_branches": [
                "#179 hierarchical league configurations",
                "#180 TL1_TEAM_LEAGUE",
                "#180 TL_CFG_CONSERVATIVE",
                "#180 TL_CFG_RESPONSIVE",
                "all TL ablations",
            ],
        },
        "accepted_180_runner": {
            "path": "scripts/freeze_bj180_team_matchup_gate_a.py",
            "sha256": SOURCE_180_RUNNER_SHA256,
        },
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def gate_a_card(
    estimator_rows: Sequence[Mapping[str, object]],
    latent_rows: Sequence[Mapping[str, object]],
    detector_grid: Sequence[Mapping[str, object]],
    forecasts: Sequence[Mapping[str, object]],
    selection_row_count: int,
) -> dict[str, object]:
    available = [row for row in forecasts if row["forecast_status"] == "AVAILABLE"]
    delta_p_available = [
        row for row in available if row["detector_family"] == "DELTA_P"
    ]
    line_residual_available = [
        row for row in available if row["detector_family"] == "LINE_RESIDUAL_MU"
    ]
    selected_counts = [int(row["selected_issue_count"]) for row in available]
    line_counts = Counter(str(row["line_stratum"]) for row in estimator_rows)
    return {
        "issue": ISSUE,
        "contract": CONTRACT,
        "version": VERSION,
        "stage": "GATE_A_OUTCOME_UNEXPOSED",
        "status": "READY_FOR_PI_REVIEW_NO_GATE_B_AUTHORITY",
        "cohort": {
            "issue_count": COHORT_ISSUES,
            "participating_issue_count": PARTICIPATING_ISSUES,
            "frozen_no_bet_issue_count": COHORT_ISSUES - PARTICIPATING_ISSUES,
            "candidate_identity_count": CANDIDATE_IDENTITIES,
            "candidate_role_count": CANDIDATE_IDENTITIES * 7,
            "unique_match_count": UNIQUE_MATCHES,
        },
        "expected_margin_resolution": {
            "fundamental_source": "#180 T1_DEEP_TEAM / TEAM_PRIMARY pure-team branch",
            "fundamental_margin_method": "accepted TEAM_PRIMARY-weighted component effective lambda_home minus lambda_away",
            "line_residual_definition": "fundamental_expected_raw_margin + handicap_line_norm",
            "latent_reconciliation_rows": len(latent_rows),
            "max_abs_reconciliation_error": compact(
                max(float(row["max_abs_reconciliation_error"]) for row in latent_rows)
            ),
            "tolerance": core190.RECONCILIATION_TOLERANCE,
            "consensus_margin_status": "UNAVAILABLE_NON_IDENTIFIABLE",
            "delta_mu_status": "DIAGNOSTIC_UNAVAILABLE_ALL_MATCHES",
            "delta_p_status": "CONTROLLING",
            "line_residual_mu_status": "CONTROLLING_SEPARATE_AXIS",
        },
        "target_safe_price": {
            "available_match_count": sum(
                row["target_safe_price_status"] == "AVAILABLE" for row in estimator_rows
            ),
            "unavailable_match_count": sum(
                row["target_safe_price_status"] != "AVAILABLE" for row in estimator_rows
            ),
            "mapping": "no-vig inverse frozen predicted BJ SP",
        },
        "native_line_coverage": {line: line_counts[line] for line in LINE_STRATA},
        "native_line_limitation": "the exact frozen complete-issue candidate universe has only line 0; -2/-1/+1/+2 strata remain frozen with zero forecast coverage",
        "detector_grid": {
            "policy_count": len(detector_grid),
            "available_delta_p_policy_count": len(delta_p_available),
            "available_line_residual_policy_count": len(line_residual_available),
            "unavailable_delta_mu_policy_count": len(detector_grid) - len(available),
            "policy_issue_selection_row_count": selection_row_count,
            "minimum_selected_issue_count": min(selected_counts),
            "maximum_selected_issue_count": max(selected_counts),
            "zero_candidate_policy_count": sum(value == 0 for value in selected_counts),
        },
        "arms": [
            "B0_BEST_FULL",
            "D_MATCH_ONLY_FULL",
            "D_DIRECTION_ONLY",
            "D_JOINT_SPARSE",
        ],
        "accounting": {
            "all_selected_arms_ticket_count": FULL_TICKETS,
            "all_selected_arms_stake_yuan": FULL_STAKE_YUAN,
            "no_bet_ticket_count": 0,
            "no_bet_stake_yuan": 0,
            "pre_tax_primary": True,
            "tax_reference_only": True,
        },
        "outcome_access": False,
        "gate_b_authorized": False,
        "production_authority": False,
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def assert_gate_a_schema(
    named_rows: Mapping[str, Sequence[Mapping[str, object]]]
) -> None:
    for name, rows in named_rows.items():
        if not rows:
            raise RuntimeError(f"empty required Gate-A table: {name}")
        fields = {str(field).lower() for field in rows[0]}
        forbidden = fields.intersection(FORBIDDEN_TARGET_FIELDS)
        if forbidden:
            raise RuntimeError(f"Gate-A table {name} exposes forbidden fields: {forbidden}")
        for row in rows:
            if set(row) != set(rows[0]):
                raise RuntimeError(f"Gate-A table schema drift: {name}")


def manifest_for(directory: Path) -> dict[str, str]:
    excluded = {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}
    return {
        path.name: sha256_file(path)
        for path in sorted(directory.iterdir(), key=lambda value: value.name)
        if path.is_file() and path.name not in excluded
    }


def atomic_generate(output: Path, database: Path) -> dict[str, object]:
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        if sha256_file(database) != SOURCE_DB_SHA256:
            raise RuntimeError("source database hash drift")
        source_rows = verify_sources()
        verify_external_86_if_present()
        latent_rows, estimator_rows, roles, candidates, source_selection = (
            build_latent_and_estimator_freeze(database)
        )
        membership_rows, candidates_by_issue, membership = build_candidate_membership(
            roles, candidates
        )
        detector_grid = build_detector_grid()
        forecasts, strata, selection_count = build_policy_forecasts(
            detector_grid,
            estimator_rows,
            candidates_by_issue,
            membership,
            source_selection,
            stage / "policy_issue_selection_freeze.csv.gz",
        )
        issue_census = build_issue_census(source_selection)
        estimators = build_estimator_registry()
        estimator_provenance = build_estimator_provenance_registry()
        arms = build_attribution_arms()
        assert_gate_a_schema(
            {
                "latent": latent_rows,
                "estimator": estimator_rows,
                "membership": membership_rows,
                "grid": detector_grid,
                "forecast": forecasts,
                "strata": strata,
                "census": issue_census,
                "estimators": estimators,
                "estimator_provenance": estimator_provenance,
                "arms": arms,
                "sources": source_rows,
            }
        )

        write_gzip(stage / "poisson_latent_reconciliation.csv.gz", latent_rows)
        write_gzip(stage / "estimator_match_freeze.csv.gz", estimator_rows)
        write_gzip(stage / "candidate_membership_freeze.csv.gz", membership_rows)
        write_csv(stage / "detector_grid.csv", detector_grid)
        write_gzip(stage / "coverage_forecast.csv.gz", forecasts)
        write_gzip(stage / "line_direction_forecast.csv.gz", strata)
        write_csv(stage / "issue_census.csv", issue_census)
        write_csv(stage / "estimator_registry.csv", estimators)
        write_csv(
            stage / "estimator_provenance_registry.csv", estimator_provenance
        )
        write_csv(stage / "attribution_arm_registry.csv", arms)
        write_csv(stage / "source_census.csv", source_rows)
        write_json(stage / "directional_ticket_contract.json", core190.directional_ticket_accounting())
        write_json(
            stage / "chronology_bootstrap_contract.json",
            chronology_bootstrap_contract(issue_census),
        )
        write_json(stage / "output_schema_contract.json", output_schema_contract())
        binding = source_binding(source_rows)
        write_json(stage / "source_binding.json", binding)
        card = gate_a_card(
            estimator_rows, latent_rows, detector_grid, forecasts, selection_count
        )
        write_json(stage / "gate_a_card.json", card)
        (stage / "README.md").write_text(
            "# #190 Gate A — sparse independent-model vs handicap divergence\n\n"
            "This immutable package freezes the full outcome-unexposed sparse detector frontier. "
            "The controlling independent estimator is exact #180 `T1_DEEP_TEAM` / `TEAM_PRIMARY`. "
            "Its seven pure-team component intensities and score-difference distributions, plus the "
            "reconciled T1 log-pool distribution, reproduce every accepted p3/p1/p0 row. #179 and all "
            "#180 TL market-derived branches are explicitly excluded from independent evidence.\n\n"
            "`HANDICAP_CONSENSUS` is the no-vig inverse of the frozen target-safe predicted BJ SP vector. "
            "Three-way prices do not identify a unique raw expected margin, so `delta_mu` is explicitly "
            "unavailable and executes no policies. `delta_p` and model-vs-line `line_residual_mu` are "
            "separate controlling axes and are never blended.\n\n"
            "The exact complete-issue N7 candidate universe contains 348 issues, 189 participating issues, "
            "424 candidate identities and 1,558 unique matches. All frozen candidate matches have native line "
            "0; the -2/-1/+1/+2 report strata are retained with zero forecast coverage.\n\n"
            "No target outcome, final/winning SP, payout, tax, ROI or settlement data is present. Gate B, "
            "production and betting are not authorized.\n"
            ,
            encoding="utf-8",
        )
        shutil.copy2(Path(__file__).resolve(), stage / "freeze_runner.py")
        shutil.copy2(
            ROOT / "scripts" / "bj190_sparse_divergence_core.py",
            stage / "bj190_sparse_core.py",
        )
        shutil.copy2(
            ROOT / "scripts" / "bj180_team_matchup_core.py",
            stage / "accepted_bj180_team_matchup_core.py",
        )

        manifest = manifest_for(stage)
        write_json(stage / "SHA256SUMS.json", manifest)
        content_identity = {
            "package": output.name,
            "contract": CONTRACT,
            "version": VERSION,
            "manifest_sha256": sha256_file(stage / "SHA256SUMS.json"),
            "source_binding_sha256": sha256_file(stage / "source_binding.json"),
            "gate_a_card_sha256": sha256_file(stage / "gate_a_card.json"),
            "detector_grid_sha256": sha256_file(stage / "detector_grid.csv"),
            "policy_issue_selection_sha256": sha256_file(
                stage / "policy_issue_selection_freeze.csv.gz"
            ),
            "estimator_match_freeze_sha256": sha256_file(
                stage / "estimator_match_freeze.csv.gz"
            ),
            "poisson_latent_reconciliation_sha256": sha256_file(
                stage / "poisson_latent_reconciliation.csv.gz"
            ),
            "counts": card["cohort"],
            "policy_count": len(detector_grid),
            "selection_row_count": selection_count,
            "outcome_access": False,
        }
        write_json(stage / "CONTENT_IDENTITY.json", content_identity)
        os.replace(stage, output)
        return {
            "output": str(output),
            "manifest_sha256": sha256_file(output / "SHA256SUMS.json"),
            "content_identity_sha256": sha256_file(output / "CONTENT_IDENTITY.json"),
            "payload_count": len(manifest),
            "policy_count": len(detector_grid),
            "selection_row_count": selection_count,
            "coverage_min": card["detector_grid"]["minimum_selected_issue_count"],
            "coverage_max": card["detector_grid"]["maximum_selected_issue_count"],
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=locate_database())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    receipt = atomic_generate(args.output, args.database.resolve())
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
