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
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


ISSUE = 190
CONTRACT = "BJ-HIST-SPARSE-DIVERGENCE-N7-001"
VERSION = "bj190-gate-a-preoutcome-v3r1"
PACKAGE_NAME = "bj190_gate_a_preoutcome_v3r1"
BASE_MAIN_COMMIT = "7b3c55fd6a490a3e4147b94b7df944535b80b88f"
FULL_TICKETS = 3**7
FULL_STAKE_YUAN = 2 * FULL_TICKETS
SOURCE_ISSUE_INSTANCES = 348
CANONICAL_ISSUES = 344
SOURCE_B0_PARTICIPATING_ISSUES = 189
ELIGIBLE_MATCHES = 101_970
EXCLUDED_MISSING_NATIVE_LINE_MATCHES = 252
CUTOFF_REGRESSION_ANCHORS = {
    "21062": {
        "reporting_year": 2021,
        "cutoff_ts": "2021-06-08 23:59:00",
        "market_training_rows": 126_468,
        "market_training_max_ts": "2021-06-08 08:30:00",
    },
    "24121": {
        "reporting_year": 2024,
        "cutoff_ts": "2024-11-29 16:35:00",
        "market_training_rows": 183_741,
        "market_training_max_ts": "2024-11-29 09:00:00",
    },
}
CLEAN_HISTORY_REBUILD_ISSUES = {
    "20122": {
        "market_training_rows": 116_389,
        "market_training_max_ts": "2020-12-01 07:00:00",
    },
    **{
        issue: {
            "market_training_rows": values["market_training_rows"],
            "market_training_max_ts": values["market_training_max_ts"],
        }
        for issue, values in CUTOFF_REGRESSION_ANCHORS.items()
    },
}
# Retained only by superseded v1 read helpers; the executable v2 path below
# binds the full 344-issue / 102,222-match universe instead.
COHORT_ISSUES = 348
PARTICIPATING_ISSUES = 189
CANDIDATE_IDENTITIES = 424
UNIQUE_MATCHES = 1_558
SOURCE_DB_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
SOURCE_180_CORE_SHA256 = (
    "4d65b08609162644394dfe83e632073ad092b9bfd058dc74368b9ceef4908890"
)
SOURCE_180_RUNNER_SHA256 = (
    "f715dfb3ea976cc311fea6aacf79c648fce0209d79b071cd9233e769978994fc"
)
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
DEFAULT_OUTPUT = ROOT / "results" / PACKAGE_NAME
DB_REPOSITORY_PATH = Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite")
DB_ENVIRONMENT_VARIABLE = "BJ190_SOURCE_DATABASE"

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

try:
    import bj190_sparse_divergence_core as core190
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bj190_sparse_core as core190  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class IssueSpec:
    issue: str
    year: int
    fold: str
    issue_instance: str
    source_issue_instances: tuple[str, ...]
    cutoff_ts: str
    eligible_match_count: int
    b0_status: str
    b0_portfolio_id: str
    b0_identity_fingerprint: str
    b0_match_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchRecord:
    match_id: str
    issue: str
    issue_instance: str
    match_idx: int
    kickoff_ts: str
    year: int
    league: str
    line: float | None
    line_stratum: str
    min_history_n: int
    market_breadth: str
    market_dispersion: str
    market_uncertainty: float
    fundamental_p: tuple[float, float, float]
    calibrated_p: tuple[float, float, float]
    consensus_p: tuple[float, float, float]
    fundamental_delta: tuple[float, float, float]
    calibrated_delta: tuple[float, float, float]
    fundamental_z: tuple[float, float, float]
    calibrated_z: tuple[float, float, float]
    t1_expected_margin: float
    line_residual_mu: float
    line_residual_z: float


@dataclass(frozen=True, slots=True)
class DetectorMetric:
    record: MatchRecord
    magnitude: float
    abs_z: float
    favored_code: str
    omitted_code: str
    estimator_source: str
    allocation_p: tuple[float, float, float]


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


def locate_database(explicit: Path | None = None) -> Path:
    """Resolve the canonical DB without binding replay to checkout placement.

    ``--database`` is authoritative when supplied, followed by the documented
    environment variable.  Repository-ancestry discovery remains a local
    convenience only.  ``atomic_generate`` verifies the frozen SHA-256 before
    any source read regardless of which path resolved.
    """

    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_file():
            raise RuntimeError(f"explicit source database unavailable: {candidate}")
        return candidate
    environment_path = os.environ.get(DB_ENVIRONMENT_VARIABLE)
    if environment_path:
        candidate = Path(environment_path).expanduser().resolve()
        if not candidate.is_file():
            raise RuntimeError(
                f"{DB_ENVIRONMENT_VARIABLE} source database unavailable: {candidate}"
            )
        return candidate
    for base in (ROOT, *ROOT.parents):
        candidate = base / DB_REPOSITORY_PATH
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(
        "canonical source database unavailable; pass --database or set "
        f"{DB_ENVIRONMENT_VARIABLE}"
    )


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
    if (
        sha256_file(ROOT / "scripts" / "bj180_team_matchup_core.py")
        != SOURCE_180_CORE_SHA256
    ):
        raise RuntimeError("accepted #180 core hash drift")
    if (
        sha256_file(ROOT / "scripts" / "freeze_bj180_team_matchup_gate_a.py")
        != SOURCE_180_RUNNER_SHA256
    ):
        raise RuntimeError("accepted #180 runner hash drift")
    return rows


def verify_external_86_if_present() -> None:
    candidates = [
        ROOT / "results",
        ROOT.parent.parent / "results",
        Path(
            "/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/strategy/results"
        ),
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


# Superseded v1 read/replay helpers remain only to explain the rejected artifact's
# provenance.  atomic_generate() cannot call any `_superseded_v1_*` function.
def _superseded_v1_canonical_role_by_match(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
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
        if match_id in output and any(
            output[match_id][field] != row[field] for field in fields
        ):
            raise RuntimeError(f"role-vector probability drift: {match_id}")
        output.setdefault(match_id, row)
    if len(output) != UNIQUE_MATCHES:
        raise RuntimeError(f"canonical role denominator drift: {len(output)}")
    return output


def _superseded_v1_predicted_prices(
    role: Mapping[str, str],
) -> tuple[float, float, float]:
    probability = [float(role[f"p_model{code}"]) for code in CODE_ORDER]
    q = [float(role["e_sp"]) * float(role[f"q_weight{code}"]) for code in CODE_ORDER]
    return tuple(q[index] / probability[index] for index in range(3))  # type: ignore[return-value]


def code_features(delta: Mapping[str, float]) -> dict[str, object]:
    favored = min(
        CODE_ORDER, key=lambda code: (-float(delta[code]), CODE_ORDER.index(code))
    )
    omitted = min(
        CODE_ORDER, key=lambda code: (float(delta[code]), CODE_ORDER.index(code))
    )
    extreme = min(
        CODE_ORDER, key=lambda code: (-abs(float(delta[code])), CODE_ORDER.index(code))
    )
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
    if value in (None, ""):
        return "OTHER"
    number = float(value)
    rounded = round(number)
    if abs(number - rounded) <= 1e-9 and rounded in {-2, -1, 0, 1, 2}:
        return f"+{rounded}" if rounded > 0 else str(rounded)
    return "OTHER"


def ro_connection(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def build_canonical_issue_specs(
    database: Path,
    source: Mapping[str, object],
) -> tuple[list[IssueSpec], dict[str, int]]:
    selections = [
        row
        for row in source["selection"]  # type: ignore[index]
        if row["arm"] == "B0_BEST_FULL"
    ]
    roles = list(source["roles"])  # type: ignore[arg-type]
    if len(selections) != SOURCE_ISSUE_INSTANCES:
        raise RuntimeError("source issue-instance denominator drift")
    by_issue: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in selections:
        by_issue[str(row["issue"])].append(row)
    if len(by_issue) != CANONICAL_ISSUES:
        raise RuntimeError("canonical numeric issue denominator drift")

    roles_by_identity: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(
        list
    )
    for row in roles:
        roles_by_identity[(row["issue_instance"], row["portfolio_id"])].append(row)

    issue_ids = sorted(by_issue, key=lambda value: int(value))
    placeholders = ",".join("?" for _ in issue_ids)
    query = f"""
        SELECT CAST(m.issue AS TEXT) AS issue,
               MIN(m.kickoff_ts) AS cutoff_ts,
               SUM(CASE WHEN m.handicap_line_norm IS NOT NULL THEN 1 ELSE 0 END)
                   AS eligible_match_count
          FROM matches m
          JOIN market_consensus e1
            ON e1.match_id=m.match_id
           AND e1.market='euro_1x2'
           AND e1.snapshot='1h'
         WHERE m.issue IN ({placeholders})
           AND m.kickoff_ts IS NOT NULL
           AND m.home_team_id IS NOT NULL
           AND m.away_team_id IS NOT NULL
           AND e1.n_complete > 0
           AND e1.v1_avg > 1 AND e1.v2_avg > 1 AND e1.v3_avg > 1
         GROUP BY m.issue
         ORDER BY CAST(m.issue AS INTEGER)
    """
    connection = ro_connection(database)
    try:
        census = {
            str(row["issue"]): row for row in connection.execute(query, issue_ids)
        }
        line_query = f"""
            SELECT m.handicap_line_norm, COUNT(*) AS n
              FROM matches m
              JOIN market_consensus e1
                ON e1.match_id=m.match_id
               AND e1.market='euro_1x2'
               AND e1.snapshot='1h'
             WHERE m.issue IN ({placeholders})
               AND m.kickoff_ts IS NOT NULL
               AND m.home_team_id IS NOT NULL
               AND m.away_team_id IS NOT NULL
               AND m.handicap_line_norm IS NOT NULL
               AND e1.n_complete > 0
               AND e1.v1_avg > 1 AND e1.v2_avg > 1 AND e1.v3_avg > 1
             GROUP BY m.handicap_line_norm
        """
        line_counts = {
            "MISSING" if row[0] is None else compact(float(row[0])): int(row[1])
            for row in connection.execute(line_query, issue_ids)
        }
        missing_line_query = f"""
            SELECT COUNT(*)
              FROM matches m
              JOIN market_consensus e1
                ON e1.match_id=m.match_id
               AND e1.market='euro_1x2'
               AND e1.snapshot='1h'
             WHERE m.issue IN ({placeholders})
               AND m.kickoff_ts IS NOT NULL
               AND m.home_team_id IS NOT NULL
               AND m.away_team_id IS NOT NULL
               AND m.handicap_line_norm IS NULL
               AND e1.n_complete > 0
               AND e1.v1_avg > 1 AND e1.v2_avg > 1 AND e1.v3_avg > 1
        """
        excluded_missing_line_count = int(
            connection.execute(missing_line_query, issue_ids).fetchone()[0]
        )
    finally:
        connection.close()
    if set(census) != set(issue_ids):
        raise RuntimeError("eligible full-issue census coverage drift")
    if (
        sum(int(row["eligible_match_count"]) for row in census.values())
        != ELIGIBLE_MATCHES
    ):
        raise RuntimeError("eligible full-issue match denominator drift")
    if min(int(row["eligible_match_count"]) for row in census.values()) < 7:
        raise RuntimeError("full issue has fewer than seven target-safe matches")
    if excluded_missing_line_count != EXCLUDED_MISSING_NATIVE_LINE_MATCHES:
        raise RuntimeError(
            "missing native-line exclusion denominator drift: "
            f"{excluded_missing_line_count}"
        )
    expected_lines = {
        "-2.000000000000": 4_877,
        "-1.000000000000": 24_561,
        "0.000000000000": 61_275,
        "1.000000000000": 9_357,
        "2.000000000000": 1_467,
    }
    if any(line_counts.get(key) != value for key, value in expected_lines.items()):
        raise RuntimeError(f"native line census drift: {line_counts}")
    line_counts["MISSING_EXCLUDED"] = excluded_missing_line_count

    output: list[IssueSpec] = []
    participating = 0
    for issue in issue_ids:
        source_rows = by_issue[issue]
        selected = [
            row for row in source_rows if row["policy_status"] == "SELECTED_PREOUTCOME"
        ]
        if len(selected) > 1:
            raise RuntimeError(f"ambiguous inherited B0 comparator: {issue}")
        canonical_year = max(int(row["year"]) for row in source_rows)
        if selected:
            participating += 1
            row = selected[0]
            key = (row["issue_instance"], row["selected_portfolio_id"])
            frozen_roles = sorted(
                roles_by_identity[key], key=lambda value: int(value["selection_rank"])
            )
            if len(frozen_roles) != 7:
                raise RuntimeError(f"B0 role-count drift: {issue}")
            b0_match_ids = tuple(str(role["match_id"]) for role in frozen_roles)
            status = "SELECTED_PREOUTCOME"
            portfolio = str(row["selected_portfolio_id"])
            fingerprint = str(row["selected_identity_fingerprint"])
        else:
            b0_match_ids = ()
            status = "NO_BET_FROZEN"
            portfolio = ""
            fingerprint = ""
        output.append(
            IssueSpec(
                issue=issue,
                year=canonical_year,
                fold=f"OOS_{canonical_year}",
                issue_instance=f"{issue}@CANONICAL_{canonical_year}",
                source_issue_instances=tuple(
                    sorted(str(row["issue_instance"]) for row in source_rows)
                ),
                cutoff_ts=str(census[issue]["cutoff_ts"]),
                eligible_match_count=int(census[issue]["eligible_match_count"]),
                b0_status=status,
                b0_portfolio_id=portfolio,
                b0_identity_fingerprint=fingerprint,
                b0_match_ids=b0_match_ids,
            )
        )
    if participating != SOURCE_B0_PARTICIPATING_ISSUES:
        raise RuntimeError("B0 comparator participation drift")
    output.sort(key=lambda row: (row.cutoff_ts, int(row.issue)))
    for issue in output:
        cutoff_year = int(issue.cutoff_ts[:4])
        if issue.year - cutoff_year not in (0, 1):
            raise RuntimeError(
                "target-safe cutoff/reporting-year plausibility drift: "
                f"{issue.issue} / {issue.cutoff_ts} / {issue.year}"
            )
    by_output_issue = {issue.issue: issue for issue in output}
    for issue, expected in CUTOFF_REGRESSION_ANCHORS.items():
        actual = by_output_issue[issue]
        if (
            actual.year != expected["reporting_year"]
            or actual.cutoff_ts != expected["cutoff_ts"]
        ):
            raise RuntimeError(
                f"target-safe cutoff regression anchor drift: {issue} / "
                f"{actual.cutoff_ts} / {actual.year}"
            )
    return output, line_counts


def iter_eligible_issue_targets(
    database: Path,
    issue: IssueSpec,
    runner179: ModuleType,
) -> Iterator[dict[str, object]]:
    query = f"""
        SELECT m.match_id, CAST(m.issue AS TEXT) AS issue, m.match_idx,
               m.kickoff_ts, m.league, m.home_team_id, m.away_team_id,
               m.handicap_line_norm,
               {runner179.market_select()}
          FROM matches m
          JOIN match_features mf ON mf.match_id=m.match_id
          {runner179.market_joins()}
         WHERE m.issue=?
           AND m.kickoff_ts IS NOT NULL
           AND m.home_team_id IS NOT NULL
           AND m.away_team_id IS NOT NULL
           AND m.handicap_line_norm IS NOT NULL
           AND e1.n_complete > 0
           AND e1.v1_avg > 1 AND e1.v2_avg > 1 AND e1.v3_avg > 1
         ORDER BY m.match_idx, m.match_id
    """
    connection = ro_connection(database)
    try:
        count = 0
        for row in connection.execute(query, (issue.issue,)):
            target = dict(row)
            target["year"] = issue.year
            target["issue_instance"] = issue.issue_instance
            count += 1
            yield target
    finally:
        connection.close()
    if count != issue.eligible_match_count:
        raise RuntimeError(f"eligible issue row-count drift: {issue.issue}")


def read_issue_match_id_sets(
    database: Path, issues: Sequence[IssueSpec]
) -> dict[str, set[str]]:
    """Return all target-issue match IDs for chronological leakage assertions."""

    issue_ids = [issue.issue for issue in issues]
    placeholders = ",".join("?" for _ in issue_ids)
    query = f"""
        SELECT CAST(issue AS TEXT) AS issue, CAST(match_id AS TEXT) AS match_id
          FROM matches
         WHERE issue IN ({placeholders})
         ORDER BY CAST(issue AS INTEGER), match_id
    """
    output: dict[str, set[str]] = {issue: set() for issue in issue_ids}
    connection = ro_connection(database)
    try:
        for row in connection.execute(query, issue_ids):
            output[str(row["issue"])].add(str(row["match_id"]))
    finally:
        connection.close()
    if any(not output[issue] for issue in issue_ids):
        raise RuntimeError("target issue match-ID census unavailable")
    return output


def rebuild_issue_history_states_without_target(
    database: Path,
    issue: IssueSpec,
    target_match_ids: set[str],
    runner179: ModuleType,
    accepted179: ModuleType,
    runner180: ModuleType,
    accepted180: ModuleType,
) -> tuple[object, object, set[str], set[str], str, str]:
    """Build exact cutoff states while excluding every match in the target issue.

    Most issue snapshots reuse the expanding accumulators.  A small number of
    issues have non-target-safe rows at least 180 minutes before the eligible
    pool's first kickoff.  Those rows are valid history for later issues but
    must not enter their own issue snapshot, so only those snapshots are
    rebuilt from the same accepted historical iterators with an explicit
    target-identity exclusion.
    """

    cutoff = accepted180.parse_ts(issue.cutoff_ts)
    team_state = accepted180.TeamMatchupState()
    team_ids: set[str] = set()
    for row in runner180.historical_rows(database, issue.cutoff_ts):
        if not runner180.history_row_is_available(
            accepted180.parse_ts(row["kickoff_ts"]), cutoff
        ):
            break
        match_id = str(row["match_id"])
        if match_id in target_match_ids:
            continue
        if match_id in team_ids:
            raise RuntimeError(f"duplicate rebuilt team-history match: {match_id}")
        team_state.update(row)
        team_ids.add(match_id)

    market_state = accepted179.HierarchicalLeagueModel(9999)
    market_ids: set[str] = set()
    market_digest = hashlib.sha256()
    market_max_ts = ""
    for row in runner179.historical_rows(database, issue.cutoff_ts):
        if not runner180.history_row_is_available(
            accepted180.parse_ts(row["kickoff_ts"]), cutoff
        ):
            break
        match_id = str(row["match_id"])
        if match_id in target_match_ids:
            continue
        if match_id in market_ids:
            raise RuntimeError(f"duplicate rebuilt market-history match: {match_id}")
        market_state.update(row)
        market_digest.update(core190.canonical_json(row))
        market_digest.update(b"\n")
        market_ids.add(match_id)
        market_max_ts = str(row["kickoff_ts"])
    if target_match_ids.intersection(team_ids) or target_match_ids.intersection(
        market_ids
    ):
        raise RuntimeError(
            f"target issue survived clean history rebuild: {issue.issue}"
        )
    return (
        team_state,
        market_state,
        team_ids,
        market_ids,
        market_digest.hexdigest(),
        market_max_ts,
    )


def build_full_estimator_freeze(
    database: Path,
    issues: Sequence[IssueSpec],
    latent_output: Path,
    estimator_output: Path,
    market_training_output: Path,
) -> tuple[dict[str, tuple[MatchRecord, ...]], dict[str, object]]:
    runner180 = load_module(
        "bj190_v2_accepted_180_runner",
        ROOT / "scripts" / "freeze_bj180_team_matchup_gate_a.py",
    )
    accepted180 = runner180.load_core()
    runner179 = load_module(
        "bj190_v2_accepted_179_runner",
        ROOT / "scripts" / "freeze_bj179_hierarchical_league_gate_a.py",
    )
    accepted179 = runner179.load_core()
    state = accepted180.TeamMatchupState()
    maximum_cutoff = max(issue.cutoff_ts for issue in issues)
    history = iter(runner180.historical_rows(database, maximum_cutoff))
    pending = next(history, None)
    team_history_match_ids: set[str] = set()
    market_state = accepted179.HierarchicalLeagueModel(9999)
    market_history = iter(runner179.historical_rows(database, maximum_cutoff))
    pending_market = next(market_history, None)
    market_history_digest = hashlib.sha256()
    market_history_match_ids: set[str] = set()
    market_training_max_ts = ""
    issue_match_ids = read_issue_match_id_sets(database, issues)
    market_training_rows: list[dict[str, object]] = []
    latent_sink = GzipRowSink(latent_output)
    estimator_sink = GzipRowSink(estimator_output)
    pools: dict[str, tuple[MatchRecord, ...]] = {}
    universe_digest = hashlib.sha256()
    max_reconciliation_error = 0.0
    sign_proxy_disagreement_count = 0
    line_counts: Counter[str] = Counter()
    clean_rebuild_issues: set[str] = set()

    for issue in issues:
        cutoff = accepted180.parse_ts(issue.cutoff_ts)
        while pending is not None and runner180.history_row_is_available(
            accepted180.parse_ts(pending["kickoff_ts"]), cutoff
        ):
            pending_match_id = str(pending["match_id"])
            if pending_match_id in team_history_match_ids:
                raise RuntimeError(f"duplicate team-history match: {pending_match_id}")
            state.update(pending)
            team_history_match_ids.add(pending_match_id)
            pending = next(history, None)
        while pending_market is not None and runner180.history_row_is_available(
            accepted180.parse_ts(pending_market["kickoff_ts"]), cutoff
        ):
            pending_match_id = str(pending_market["match_id"])
            if pending_match_id in market_history_match_ids:
                raise RuntimeError(
                    f"duplicate market-model history match: {pending_match_id}"
                )
            market_state.update(pending_market)
            market_history_digest.update(core190.canonical_json(pending_market))
            market_history_digest.update(b"\n")
            market_history_match_ids.add(pending_match_id)
            market_training_max_ts = str(pending_market["kickoff_ts"])
            pending_market = next(market_history, None)
        available_through = runner180.history_available_through(cutoff)
        target_ids = issue_match_ids[issue.issue]
        raw_team_overlap = team_history_match_ids.intersection(target_ids)
        raw_market_overlap = market_history_match_ids.intersection(target_ids)
        if raw_team_overlap or raw_market_overlap:
            (
                effective_state,
                effective_market_state,
                effective_team_ids,
                effective_market_ids,
                effective_market_digest,
                effective_market_max_ts,
            ) = rebuild_issue_history_states_without_target(
                database,
                issue,
                target_ids,
                runner179,
                accepted179,
                runner180,
                accepted180,
            )
            clean_rebuild_issues.add(issue.issue)
            clean_rebuild_used = 1
        else:
            effective_state = state
            effective_market_state = market_state
            effective_team_ids = team_history_match_ids
            effective_market_ids = market_history_match_ids
            effective_market_digest = market_history_digest.hexdigest()
            effective_market_max_ts = market_training_max_ts
            clean_rebuild_used = 0
        team_target_overlap = effective_team_ids.intersection(target_ids)
        target_overlap = effective_market_ids.intersection(target_ids)
        if team_target_overlap:
            raise RuntimeError(f"team target overlap after snapshot: {issue.issue}")
        if target_overlap:
            raise RuntimeError(
                f"market-model target overlap after snapshot: {issue.issue}"
            )
        if effective_market_max_ts and (
            accepted180.parse_ts(effective_market_max_ts) > available_through
        ):
            raise RuntimeError(
                f"market-model row after frozen cutoff: {issue.issue} / "
                f"{effective_market_max_ts}"
            )
        state_summary = effective_state.summary()
        market_model = effective_market_state.frozen_copy(issue.year)
        if market_model.training_rows != len(effective_market_ids):
            raise RuntimeError(
                f"market-model training denominator drift: {issue.issue}"
            )
        market_summary = {
            key: value
            for key, value in market_model.summary().items()
            if key != "training_rule"
        }
        market_training_rows.append(
            {
                "issue": issue.issue,
                "issue_instance": issue.issue_instance,
                "reporting_year": issue.year,
                "feature_cutoff_ts": issue.cutoff_ts,
                "score_available_through_ts": available_through.isoformat(sep=" "),
                "training_max_kickoff_ts": effective_market_max_ts,
                "training_row_count": market_model.training_rows,
                "team_history_training_row_count": state_summary["training_rows"],
                "model_state_identity_sha256": core190.canonical_hash(
                    {
                        "history_identity_sha256": effective_market_digest,
                        "reporting_year": issue.year,
                        "summary": market_summary,
                    }
                ),
                "history_identity_sha256": effective_market_digest,
                "target_issue_match_count": len(target_ids),
                "raw_team_target_overlap_count": len(raw_team_overlap),
                "raw_market_target_overlap_count": len(raw_market_overlap),
                "team_target_issue_overlap_count": len(team_target_overlap),
                "target_issue_overlap_count": len(target_overlap),
                "post_available_cutoff_row_count": 0,
                "clean_target_exclusion_rebuild_used": clean_rebuild_used,
                "history_rule": "kickoff <= feature_cutoff_ts - 180 minutes (inclusive)",
                "reporting_year_separate_from_training_cutoff": 1,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
        records: list[MatchRecord] = []
        for target in iter_eligible_issue_targets(database, issue, runner179):
            if FORBIDDEN_TARGET_FIELDS.intersection(target):
                raise RuntimeError("full-universe target projection exposes outcome")
            families, diagnostics, captured = core190.capture_family_latents(
                effective_state, target, cutoff, accepted180
            )
            family_distributions: dict[str, dict[int, float]] = {}
            component_errors: dict[str, float] = {}
            component_lambdas: dict[str, dict[str, float]] = {}
            if target["handicap_line_norm"] in (None, ""):
                raise RuntimeError(
                    "missing native handicap entered executable universe"
                )
            handicap = float(target["handicap_line_norm"])
            for family in core190.FAMILY_ORDER:
                raw_home, raw_away, captured_handicap, max_goals = captured[family]
                effective_home = min(6.0, max(0.08, raw_home))
                effective_away = min(6.0, max(0.08, raw_away))
                prior = core190.poisson_difference_distribution(
                    effective_home, effective_away, max_goals=max_goals
                )
                distribution = (
                    core190.h2h_difference_distribution(effective_state, target, prior)
                    if family == "H2H_PRIOR"
                    else prior
                )
                mapped = core190.mapped_probabilities(distribution, captured_handicap)
                component_errors[family] = core190.probability_reconciliation_error(
                    mapped, families[family]
                )
                family_distributions[family] = distribution
                component_lambdas[family] = {
                    "home": effective_home,
                    "away": effective_away,
                }
            primary_weights = accepted180.CONFIGURATIONS[accepted180.PRIMARY_CONFIG][
                "weights"
            ]
            fundamental = accepted180.log_pool(families, primary_weights)
            t1_distribution = core190.group_mass_calibrated_distribution(
                family_distributions, primary_weights, fundamental, handicap
            )
            mapped_fundamental = core190.mapped_probabilities(t1_distribution, handicap)
            reconciliation_error = core190.probability_reconciliation_error(
                mapped_fundamental, fundamental
            )
            max_reconciliation_error = max(
                max_reconciliation_error,
                reconciliation_error,
                max(component_errors.values()),
            )
            if max_reconciliation_error > core190.RECONCILIATION_TOLERANCE:
                raise RuntimeError("T1 score-distribution reconciliation drift")
            t1_expected_margin = core190.expected_margin(t1_distribution)
            weighted_home, weighted_away = core190.weighted_family_intensities(
                captured, primary_weights
            )
            weighted_margin_proxy = weighted_home - weighted_away
            sign_proxy_disagreement_count += int(
                t1_expected_margin * weighted_margin_proxy < 0
            )
            variance = math.fsum(
                (difference - t1_expected_margin) ** 2 * probability
                for difference, probability in t1_distribution.items()
            )
            margin_uncertainty = math.sqrt(
                variance / (int(diagnostics["min_history_n"]) + 12.0)
            )
            line = handicap
            residual = t1_expected_margin + line
            residual_z = residual / max(1e-12, margin_uncertainty)

            euro = accepted179.no_vig(
                [target[f"euro_1h_v{index}"] for index in (1, 2, 3)]
            )
            if euro is None:
                raise RuntimeError("target-safe EURO consensus unexpectedly missing")
            market_families = market_model.family_vectors(target, euro)
            consensus = market_families["EURO_CALIBRATION"]
            calibrated = market_model.probabilities(target, euro)
            signature = accepted179.market_signature(target)
            market_uncertainty = dispersion_se(signature["dispersion"])
            history_n = int(diagnostics["min_history_n"])
            market_n = int(market_model.training_rows)
            fund_delta = tuple(
                fundamental[index] - consensus[index] for index in range(3)
            )
            calibrated_delta = tuple(
                calibrated[index] - consensus[index] for index in range(3)
            )
            fundamental_z = tuple(
                fund_delta[index]
                / math.hypot(
                    math.sqrt(
                        fundamental[index]
                        * (1.0 - fundamental[index])
                        / (history_n + 12.0)
                    ),
                    market_uncertainty,
                )
                for index in range(3)
            )
            calibrated_z = tuple(
                calibrated_delta[index]
                / math.hypot(
                    math.sqrt(
                        calibrated[index]
                        * (1.0 - calibrated[index])
                        / (market_n + 24.0)
                    ),
                    market_uncertainty,
                )
                for index in range(3)
            )
            stratum = line_stratum(line)
            line_counts[stratum] += 1
            match_id = str(target["match_id"])
            record = MatchRecord(
                match_id=match_id,
                issue=issue.issue,
                issue_instance=issue.issue_instance,
                match_idx=int(target["match_idx"]),
                kickoff_ts=str(target["kickoff_ts"]),
                year=issue.year,
                league=str(target["league"] or "__UNKNOWN__"),
                line=line,
                line_stratum=stratum,
                min_history_n=history_n,
                market_breadth=signature["breadth"],
                market_dispersion=signature["dispersion"],
                market_uncertainty=market_uncertainty,
                fundamental_p=tuple(fundamental),
                calibrated_p=tuple(calibrated),
                consensus_p=tuple(consensus),
                fundamental_delta=fund_delta,
                calibrated_delta=calibrated_delta,
                fundamental_z=fundamental_z,
                calibrated_z=calibrated_z,
                t1_expected_margin=t1_expected_margin,
                line_residual_mu=residual,
                line_residual_z=residual_z,
            )
            records.append(record)
            universe_digest.update(
                core190.canonical_json(
                    {
                        "issue": issue.issue,
                        "match_id": match_id,
                        "match_idx": record.match_idx,
                        "kickoff_ts": record.kickoff_ts,
                        "line": compact(line) if line is not None else "",
                    }
                )
            )
            universe_digest.update(b"\n")
            score_identity = core190.canonical_hash(
                {
                    "estimator": "T1_DEEP_TEAM_COHERENT_SCORE_DISTRIBUTION",
                    "distribution": core190.distribution_payload(t1_distribution),
                    "p": [compact(value) for value in fundamental],
                    "expected_margin": compact(t1_expected_margin),
                }
            )
            latent_sink.emit(
                {
                    "match_id": match_id,
                    "issue": issue.issue,
                    "issue_instance": issue.issue_instance,
                    "feature_cutoff_ts": issue.cutoff_ts,
                    "estimator_identity_sha256": score_identity,
                    "component_effective_lambdas_json": core190.canonical_json(
                        component_lambdas
                    ).decode(),
                    "component_max_abs_reconciliation_error": compact(
                        max(component_errors.values())
                    ),
                    "t1_score_difference_distribution_json": core190.canonical_json(
                        core190.distribution_payload(t1_distribution)
                    ).decode(),
                    "t1_mapped_p3": compact(mapped_fundamental[0]),
                    "t1_mapped_p1": compact(mapped_fundamental[1]),
                    "t1_mapped_p0": compact(mapped_fundamental[2]),
                    "t1_accepted_p3": compact(fundamental[0]),
                    "t1_accepted_p1": compact(fundamental[1]),
                    "t1_accepted_p0": compact(fundamental[2]),
                    "t1_expected_raw_margin_from_same_distribution": compact(
                        t1_expected_margin
                    ),
                    "weighted_component_lambda_home_proxy": compact(weighted_home),
                    "weighted_component_lambda_away_proxy": compact(weighted_away),
                    "weighted_component_margin_proxy_diagnostic": compact(
                        weighted_margin_proxy
                    ),
                    "weighted_proxy_controls_direction": 0,
                    "handicap_line_norm": compact(line),
                    "line_residual_mu": compact(residual),
                    "max_goals_inclusive": core190.MAX_GOALS,
                    "tail_policy": "Poisson components exclude joint cells where either score exceeds 12 and normalize retained mass; H2H empirical differences outside [-12,12] clamp to the same-code edge; T1 within-code shape is reconciled to accepted p3/p1/p0",
                    "max_abs_reconciliation_error": compact(reconciliation_error),
                    "reconciliation_status": "PASS",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
            estimator_sink.emit(
                {
                    "match_id": match_id,
                    "issue": issue.issue,
                    "issue_instance": issue.issue_instance,
                    "year": issue.year,
                    "fold": issue.fold,
                    "match_idx": record.match_idx,
                    "kickoff_ts": record.kickoff_ts,
                    "feature_cutoff_ts": issue.cutoff_ts,
                    "league": record.league,
                    "home_team_id": target["home_team_id"],
                    "away_team_id": target["away_team_id"],
                    "native_handicap_line": compact(line),
                    "line_stratum": stratum,
                    "history_training_rows": state_summary["training_rows"],
                    "min_history_n": history_n,
                    "market_signature_breadth": record.market_breadth,
                    "market_signature_dispersion": record.market_dispersion,
                    "market_uncertainty_proxy": compact(market_uncertainty),
                    "target_safe_consensus_status": "AVAILABLE",
                    "target_safe_consensus_identity_sha256": core190.canonical_hash(
                        {
                            "match_id": match_id,
                            "euro_1h": [
                                compact(float(target[f"euro_1h_v{index}"]))
                                for index in (1, 2, 3)
                            ],
                            "consensus": [compact(value) for value in consensus],
                        }
                    ),
                    "euro_1h_odds3": compact(float(target["euro_1h_v1"])),
                    "euro_1h_odds1": compact(float(target["euro_1h_v2"])),
                    "euro_1h_odds0": compact(float(target["euro_1h_v3"])),
                    **{
                        f"consensus_p{code}": compact(consensus[index])
                        for index, code in enumerate(CODE_ORDER)
                    },
                    **{
                        f"fundamental_p{code}": compact(fundamental[index])
                        for index, code in enumerate(CODE_ORDER)
                    },
                    **{
                        f"calibrated_p{code}": compact(calibrated[index])
                        for index, code in enumerate(CODE_ORDER)
                    },
                    **{
                        f"fundamental_delta_p{code}": compact(fund_delta[index])
                        for index, code in enumerate(CODE_ORDER)
                    },
                    **{
                        f"calibrated_delta_p{code}": compact(calibrated_delta[index])
                        for index, code in enumerate(CODE_ORDER)
                    },
                    **{
                        f"fundamental_z{code}": compact(fundamental_z[index])
                        for index, code in enumerate(CODE_ORDER)
                    },
                    **{
                        f"calibrated_z{code}": compact(calibrated_z[index])
                        for index, code in enumerate(CODE_ORDER)
                    },
                    "t1_score_estimator_identity_sha256": score_identity,
                    "t1_expected_raw_margin_from_same_distribution": compact(
                        t1_expected_margin
                    ),
                    "weighted_component_margin_proxy_diagnostic": compact(
                        weighted_margin_proxy
                    ),
                    "weighted_proxy_controls_direction": 0,
                    "line_residual_mu": compact(residual),
                    "line_residual_z": compact(residual_z),
                    "line_residual_status": "AVAILABLE",
                    "delta_mu": "",
                    "delta_mu_status": "UNAVAILABLE_MARKET_3WAY_DOES_NOT_IDENTIFY_RAW_MARGIN",
                    "fundamental_expected_margin_method": "T1_SCORE_DISTRIBUTION_MEAN_SAME_IDENTITY_AS_P_VECTOR",
                    "consensus_mapping": "#179 EURO_CALIBRATION_NATIVE_LINE_ALIGNED_FROM_TARGET_SAFE_1H_EURO",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
        if len(records) != issue.eligible_match_count:
            raise RuntimeError(f"issue estimator count drift: {issue.issue}")
        pools[issue.issue] = tuple(records)
    latent_sink.close()
    estimator_sink.close()
    write_csv(market_training_output, market_training_rows)
    training_by_issue = {str(row["issue"]): row for row in market_training_rows}
    if clean_rebuild_issues != set(CLEAN_HISTORY_REBUILD_ISSUES):
        raise RuntimeError(
            "clean target-exclusion rebuild issue-set drift: "
            f"{sorted(clean_rebuild_issues)}"
        )
    for issue, expected in CLEAN_HISTORY_REBUILD_ISSUES.items():
        row = training_by_issue[issue]
        if (
            int(row["training_row_count"]) != expected["market_training_rows"]
            or row["training_max_kickoff_ts"] != expected["market_training_max_ts"]
            or int(row["clean_target_exclusion_rebuild_used"]) != 1
        ):
            raise RuntimeError(
                f"market-training plausibility regression anchor drift: {issue}"
            )
    expected_match_count = sum(issue.eligible_match_count for issue in issues)
    if (
        latent_sink.count != expected_match_count
        or estimator_sink.count != expected_match_count
    ):
        raise RuntimeError("full estimator freeze denominator drift")
    return pools, {
        "eligible_match_count": expected_match_count,
        "universe_identity_sha256": universe_digest.hexdigest(),
        "max_abs_reconciliation_error": max_reconciliation_error,
        "weighted_proxy_sign_disagreement_count": sign_proxy_disagreement_count,
        "line_strata": dict(sorted(line_counts.items())),
        "market_training_issue_count": len(market_training_rows),
        "market_training_min_rows": min(
            int(row["training_row_count"]) for row in market_training_rows
        ),
        "market_training_max_rows": max(
            int(row["training_row_count"]) for row in market_training_rows
        ),
        "market_training_all_target_overlap_zero": all(
            int(row["target_issue_overlap_count"]) == 0 for row in market_training_rows
        ),
        "team_training_all_target_overlap_zero": all(
            int(row["team_target_issue_overlap_count"]) == 0
            for row in market_training_rows
        ),
        "clean_target_exclusion_rebuild_issues": sorted(clean_rebuild_issues),
    }


def _superseded_v1_build_latent_and_estimator_freeze(
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
            ROOT
            / "results"
            / "bj180_gate_a_preoutcome_v2"
            / "match_probability_freeze.csv.gz"
        )
    }
    accepted179 = {
        row["match_id"]: row
        for row in read_gzip(
            ROOT
            / "results"
            / "bj179_gate_a_preoutcome_v2"
            / "match_probability_freeze.csv.gz"
        )
    }
    canonical_roles = _superseded_v1_canonical_role_by_match(roles)
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
    history = iter(
        runner180.historical_rows(database, maximum_cutoff.isoformat(sep=" "))
    )
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
                raise RuntimeError(
                    f"target projection exposes forbidden field: {match_id}"
                )

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
            line_residual_mu = raw_expected_margin + float(target["handicap_line_norm"])
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
                price_values = _superseded_v1_predicted_prices(role)
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
                        fundamental[code]
                        * (1.0 - fundamental[code])
                        / (history_n + 12.0)
                    )
                    calibrated_model_se = math.sqrt(
                        calibrated[code]
                        * (1.0 - calibrated[code])
                        / (training_n + 24.0)
                    )
                    fund_z[code] = fund_delta[code] / math.hypot(
                        fund_model_se, market_se
                    )
                    calibrated_z[code] = calibrated_delta[code] / math.hypot(
                        calibrated_model_se, market_se
                    )
            fund_features = code_features(fund_delta) if fund_delta else {}
            calibrated_features = (
                code_features(calibrated_delta) if calibrated_delta else {}
            )
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
                    "native_handicap_line": compact(
                        float(target["handicap_line_norm"])
                    ),
                    "line_stratum": line_stratum(target["handicap_line_norm"]),
                    "history_training_rows": summary["training_rows"],
                    "min_history_n": history_n,
                    "market_signature_breadth": market_row["market_signature_breadth"],
                    "market_signature_dispersion": market_row[
                        "market_signature_dispersion"
                    ],
                    "market_uncertainty_proxy": compact(market_se),
                    "target_safe_price_status": "AVAILABLE"
                    if consensus
                    else "UNAVAILABLE",
                    "target_safe_price_unavailable_reason": ""
                    if consensus
                    else "FROZEN_BJ_PREDICTED_SP_SOURCE_INCOMPLETE",
                    "target_safe_price_identity": price_identity,
                    "predicted_sp3": compact(price_values[0]) if price_values else "",
                    "predicted_sp1": compact(price_values[1]) if price_values else "",
                    "predicted_sp0": compact(price_values[2]) if price_values else "",
                    **{
                        f"consensus_p{code}": compact(consensus[code])
                        if consensus
                        else ""
                        for code in CODE_ORDER
                    },
                    **{
                        f"fundamental_p{code}": compact(fundamental[code])
                        for code in CODE_ORDER
                    },
                    **{
                        f"calibrated_p{code}": compact(calibrated[code])
                        for code in CODE_ORDER
                    },
                    **{
                        f"fundamental_delta_p{code}": compact(fund_delta[code])
                        if fund_delta
                        else ""
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
                    "calibrated_favored_code": calibrated_features.get(
                        "favored_code", ""
                    ),
                    "calibrated_omitted_code": calibrated_features.get(
                        "omitted_code", ""
                    ),
                    "calibrated_extreme_code": calibrated_features.get(
                        "extreme_code", ""
                    ),
                    "calibrated_extreme_sign": calibrated_features.get(
                        "extreme_sign", ""
                    ),
                    "calibrated_abs_delta_p": compact(
                        calibrated_features.get("magnitude")
                    )
                    if calibrated_features
                    else "",
                    "calibrated_abs_z": compact(
                        max(
                            (abs(value) for value in calibrated_z.values()),
                            default=math.nan,
                        )
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
                    "fundamental_margin_uncertainty_proxy": compact(margin_uncertainty),
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
    if any(
        float(row["max_abs_reconciliation_error"]) > core190.RECONCILIATION_TOLERANCE
        for row in latent_rows
    ):
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
                                    "policy_id": "DP_"
                                    + core190.canonical_hash(descriptor)[:20],
                                    **descriptor,
                                    "abs_delta_mu_min": "",
                                    "abs_line_residual_mu_min": "",
                                    "availability": "AVAILABLE",
                                    "unavailable_reason": "",
                                    "tie_break": "direct eligible-match divergence magnitude desc, match_idx asc, match_id asc; exact first seven form N7; UNION exact source tie fundamental first; MODEL_AGREEMENT exact weaker-source tie fundamental first",
                                    "no_bet_rule": "fewer than seven base-gated metrics OR threshold failure => zero tickets/stake; K1/K2/K4 require the strongest K of the selected seven to pass; ALL requires all seven",
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
                        "tie_break": "direct eligible-match absolute line residual desc, match_idx asc, match_id asc; exact first seven form N7",
                        "no_bet_rule": "fewer than seven base-gated line-residual metrics OR threshold failure => zero tickets/stake; K1/K2/K4 require the strongest K of the selected seven to pass; ALL requires all seven",
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


def _superseded_v1_detector_metric(
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
        features["abs_z"] = min(float(fundamental["abs_z"]), float(calibrated["abs_z"]))
        features["estimator_source"] = "STRICT_MODEL_AGREEMENT_NO_BLEND"
        return features
    raise RuntimeError(f"unknown estimator variant: {variant}")


def _superseded_v1_metric_passes(
    row: Mapping[str, object],
    metric: Mapping[str, object],
    policy: Mapping[str, object],
) -> bool:
    if float(metric["magnitude"]) <= 1e-15:
        return False
    if policy["detector_family"] == "DELTA_P":
        if float(metric["magnitude"]) + 1e-15 < float(policy["abs_delta_p_min"]):
            return False
    elif policy["detector_family"] == "LINE_RESIDUAL_MU":
        if float(metric["magnitude"]) + 1e-15 < float(
            policy["abs_line_residual_mu_min"]
        ):
            return False
    else:
        raise RuntimeError(
            f"unavailable policy reached execution: {policy['policy_id']}"
        )
    if float(metric["abs_z"]) + 1e-15 < float(policy["abs_z_min"]):
        return False
    if int(row["min_history_n"]) < int(policy["min_history_n"]):
        return False
    if (
        policy["coverage_gate"] == "BROAD_MARKET_AND_TARGET_SAFE_PRICE"
        and row["market_signature_breadth"] != "B05_19"
    ):
        return False
    if (
        policy["uncertainty_gate"] == "MAX_0.12"
        and float(row["market_uncertainty_proxy"]) > 0.12
    ):
        return False
    return True


def _superseded_v1_retained_metrics(
    match_ids: Sequence[str],
    estimator_by_match: Mapping[str, Mapping[str, object]],
    policy: Mapping[str, object],
) -> list[dict[str, object]] | None:
    rows = []
    for match_id in match_ids:
        source = estimator_by_match[match_id]
        metric = _superseded_v1_detector_metric(
            source,
            str(policy["estimator_variant"]),
            str(policy["detector_family"]),
        )
        if metric is not None and _superseded_v1_metric_passes(source, metric, policy):
            rows.append({"match_id": match_id, "match_row": source, **metric})
    rows.sort(key=lambda row: (-float(row["magnitude"]), int(row["match_id"])))
    if policy["top_k"] == "ALL":
        return rows or None
    required = int(policy["top_k"])
    return rows[:required] if len(rows) >= required else None


def tuple_features(delta: Sequence[float]) -> dict[str, object]:
    return code_features(
        {code: float(delta[index]) for index, code in enumerate(CODE_ORDER)}
    )


def metric_for_record(
    record: MatchRecord,
    detector_family: str,
    variant: str,
) -> DetectorMetric | None:
    if detector_family == "LINE_RESIDUAL_MU":
        if (
            not math.isfinite(record.line_residual_mu)
            or abs(record.line_residual_mu) <= 1e-15
        ):
            return None
        favored = "3" if record.line_residual_mu > 0 else "0"
        omitted = "0" if record.line_residual_mu > 0 else "3"
        return DetectorMetric(
            record=record,
            magnitude=abs(record.line_residual_mu),
            abs_z=abs(record.line_residual_z),
            favored_code=favored,
            omitted_code=omitted,
            estimator_source="FUNDAMENTAL_T1_SCORE_DISTRIBUTION",
            allocation_p=record.fundamental_p,
        )
    if detector_family != "DELTA_P":
        return None

    fundamental_features = tuple_features(record.fundamental_delta)
    calibrated_features = tuple_features(record.calibrated_delta)
    fundamental_extreme_index = CODE_ORDER.index(
        str(fundamental_features["extreme_code"])
    )
    calibrated_extreme_index = CODE_ORDER.index(
        str(calibrated_features["extreme_code"])
    )
    fundamental = DetectorMetric(
        record=record,
        magnitude=float(fundamental_features["magnitude"]),
        abs_z=abs(record.fundamental_z[fundamental_extreme_index]),
        favored_code=str(fundamental_features["favored_code"]),
        omitted_code=str(fundamental_features["omitted_code"]),
        estimator_source="FUNDAMENTAL_T1_SCORE_DISTRIBUTION",
        allocation_p=record.fundamental_p,
    )
    calibrated = DetectorMetric(
        record=record,
        magnitude=float(calibrated_features["magnitude"]),
        abs_z=abs(record.calibrated_z[calibrated_extreme_index]),
        favored_code=str(calibrated_features["favored_code"]),
        omitted_code=str(calibrated_features["omitted_code"]),
        estimator_source="CALIBRATED_MARKET_ESTIMATOR",
        allocation_p=record.calibrated_p,
    )
    if variant == "FUNDAMENTAL_INDEPENDENT":
        return fundamental
    if variant == "CALIBRATED_MARKET_ESTIMATOR":
        return calibrated
    if variant == "UNION":
        return min(
            (fundamental, calibrated),
            key=lambda metric: (
                -metric.magnitude,
                0
                if metric.estimator_source == "FUNDAMENTAL_T1_SCORE_DISTRIBUTION"
                else 1,
            ),
        )
    if variant == "MODEL_AGREEMENT":
        if (
            fundamental.favored_code != calibrated.favored_code
            or fundamental.omitted_code != calibrated.omitted_code
        ):
            return None
        weaker = min(
            (fundamental, calibrated),
            key=lambda metric: (
                metric.magnitude,
                0
                if metric.estimator_source == "FUNDAMENTAL_T1_SCORE_DISTRIBUTION"
                else 1,
            ),
        )
        return DetectorMetric(
            record=record,
            magnitude=min(fundamental.magnitude, calibrated.magnitude),
            abs_z=min(fundamental.abs_z, calibrated.abs_z),
            favored_code=weaker.favored_code,
            omitted_code=weaker.omitted_code,
            estimator_source=f"STRICT_AGREEMENT_WEAKER::{weaker.estimator_source}",
            allocation_p=weaker.allocation_p,
        )
    raise RuntimeError(f"unknown estimator variant: {variant}")


def passes_base_gate(record: MatchRecord, policy: Mapping[str, object]) -> bool:
    if record.min_history_n < int(policy["min_history_n"]):
        return False
    if (
        policy["coverage_gate"] == "BROAD_MARKET_AND_TARGET_SAFE_PRICE"
        and record.market_breadth != "B05_19"
    ):
        return False
    if policy["uncertainty_gate"] == "MAX_0.12" and record.market_uncertainty > 0.12:
        return False
    return True


def metric_passes_threshold(
    metric: DetectorMetric,
    policy: Mapping[str, object],
) -> bool:
    if metric.magnitude <= 1e-15:
        return False
    if policy["detector_family"] == "DELTA_P":
        if metric.magnitude + 1e-15 < float(policy["abs_delta_p_min"]):
            return False
    elif policy["detector_family"] == "LINE_RESIDUAL_MU":
        if metric.magnitude + 1e-15 < float(policy["abs_line_residual_mu_min"]):
            return False
    else:
        return False
    return metric.abs_z + 1e-15 >= float(policy["abs_z_min"])


def base_metric_key(policy: Mapping[str, object]) -> tuple[object, ...]:
    return (
        policy["detector_family"],
        policy["estimator_variant"],
        policy["min_history_n"],
        policy["coverage_gate"],
        policy["uncertainty_gate"],
    )


def sorted_base_metrics(
    pool: Sequence[MatchRecord],
    policy: Mapping[str, object],
) -> tuple[DetectorMetric, ...]:
    metrics = []
    for record in pool:
        if not passes_base_gate(record, policy):
            continue
        metric = metric_for_record(
            record,
            str(policy["detector_family"]),
            str(policy["estimator_variant"]),
        )
        if metric is not None:
            metrics.append(metric)
    metrics.sort(
        key=lambda metric: (
            -metric.magnitude,
            metric.record.match_idx,
            int(metric.record.match_id),
        )
    )
    return tuple(metrics)


def threshold_gated_n7(
    metrics: Sequence[DetectorMetric],
    policy: Mapping[str, object],
) -> tuple[DetectorMetric, ...] | None:
    if len(metrics) < 7:
        return None
    selected = tuple(metrics[:7])
    required = 7 if policy["top_k"] == "ALL" else int(policy["top_k"])
    if not all(
        metric_passes_threshold(metric, policy) for metric in selected[:required]
    ):
        return None
    return selected


def identity_payload(
    issue: str,
    match_ids: Sequence[str],
) -> dict[str, object]:
    return {
        "issue": issue,
        "ordered_match_ids": list(match_ids),
    }


def register_identity(
    issue: str,
    match_ids: Sequence[str],
    identity_catalog: dict[str, dict[str, object]],
    selection_rule: str = "DIRECT_TOP7_DIVERGENCE_FROM_COMPLETE_ISSUE_POOL",
) -> str:
    payload = identity_payload(issue, match_ids)
    identity = core190.canonical_hash(payload)
    identity_catalog.setdefault(
        identity,
        {
            "identity_sha256": identity,
            "issue": issue,
            "selection_rule": selection_rule,
            "ordered_match_ids_json": core190.canonical_json(list(match_ids)).decode(),
            "match_count": len(match_ids),
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
    )
    return identity


def vector_sha256(vector: bytes) -> str:
    return hashlib.sha256(vector).hexdigest()


def register_vector(
    vector: bytes,
    vector_catalog: dict[str, bytes],
) -> str:
    vector_hash = vector_sha256(vector)
    existing = vector_catalog.setdefault(vector_hash, vector)
    if existing != vector:
        raise RuntimeError("ticket vector SHA collision")
    return vector_hash


def register_directional_allocation(
    issue: str,
    ordered_records: Sequence[MatchRecord],
    metrics_by_match: Mapping[str, DetectorMetric],
    identity_catalog: dict[str, dict[str, object]],
    allocation_catalog: dict[str, dict[str, object]],
    vector_catalog: dict[str, bytes],
) -> dict[str, object]:
    if len(ordered_records) != 7 or set(metrics_by_match) != {
        record.match_id for record in ordered_records
    }:
        raise RuntimeError("directional allocation identity mismatch")
    ranked = sorted(
        metrics_by_match.values(),
        key=lambda metric: (
            -metric.magnitude,
            metric.record.match_idx,
            int(metric.record.match_id),
        ),
    )
    strongest = ranked[0]
    match_ids = tuple(record.match_id for record in ordered_records)
    delete_leg = match_ids.index(strongest.record.match_id)
    probabilities = [
        metrics_by_match[record.match_id].allocation_p for record in ordered_records
    ]
    sources = [
        metrics_by_match[record.match_id].estimator_source for record in ordered_records
    ]
    allocation_input = {
        "issue": issue,
        "ordered_match_ids": list(match_ids),
        "per_leg_probability_source": sources,
        "per_leg_p3_p1_p0": [
            [compact(value) for value in probability] for probability in probabilities
        ],
        "delete_leg_index_zero_based": delete_leg,
        "omitted_code": strongest.omitted_code,
        "strongest_match_id": strongest.record.match_id,
        "base3_code_order": list(CODE_ORDER),
        "repeat_rank": "joint log probability desc, base-3 ordinal asc",
    }
    allocation_hash = core190.canonical_hash(allocation_input)
    if allocation_hash not in allocation_catalog:
        vector = core190.directional_ticket_multiplicity_vector(
            probabilities,
            delete_leg,
            strongest.omitted_code,
        )
        stats = core190.validate_ticket_multiplicity_vector(
            vector,
            strongest.omitted_code,
            delete_leg,
        )
        vector_hash = register_vector(vector, vector_catalog)
        identity = register_identity(issue, match_ids, identity_catalog)
        ticket_identity = core190.canonical_hash(
            {
                "n7_identity_sha256": identity,
                "multiplicity_vector_sha256": vector_hash,
            }
        )
        allocation_catalog[allocation_hash] = {
            "allocation_input_sha256": allocation_hash,
            "n7_identity_sha256": identity,
            "ticket_identity_sha256": ticket_identity,
            "multiplicity_vector_sha256": vector_hash,
            "ordered_match_ids_json": core190.canonical_json(list(match_ids)).decode(),
            "per_leg_probability_source_json": core190.canonical_json(sources).decode(),
            "per_leg_p3_p1_p0_json": core190.canonical_json(
                allocation_input["per_leg_p3_p1_p0"]
            ).decode(),
            "delete_leg_index_zero_based": delete_leg,
            "strongest_match_id": strongest.record.match_id,
            "omitted_code": strongest.omitted_code,
            **stats,
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
    return allocation_catalog[allocation_hash]


def ticket_ledger_row(
    policy: Mapping[str, object],
    issue: IssueSpec,
    arm: str,
    status: str,
    identity: str = "",
    ticket_identity: str = "",
    vector_hash: str = "",
    allocation_hash: str = "",
) -> dict[str, object]:
    executed = status == "FROZEN_EXECUTABLE"
    directional = arm in {"D_DIRECTION_ONLY", "D_JOINT_SPARSE"}
    return {
        "policy_id": policy["policy_id"],
        "issue": issue.issue,
        "year": issue.year,
        "fold": issue.fold,
        "issue_instance": issue.issue_instance,
        "arm": arm,
        "policy_status": status,
        "n7_identity_sha256": identity,
        "allocation_input_sha256": allocation_hash,
        "multiplicity_vector_sha256": vector_hash,
        "ticket_identity_sha256": ticket_identity,
        "ticket_construction": "ONE_CODE_DELETE_PLUS_729_REPEATS"
        if directional and executed
        else "FULL_ENUMERATED"
        if executed
        else "NO_BET",
        "unique_ticket_count": 1458
        if directional and executed
        else FULL_TICKETS
        if executed
        else 0,
        "executed_ticket_count": FULL_TICKETS if executed else 0,
        "planned_stake_yuan": FULL_STAKE_YUAN if executed else 0,
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def full_ticket_identity(
    identity: str,
    full_vector_hash: str,
) -> str:
    return core190.canonical_hash(
        {
            "n7_identity_sha256": identity,
            "multiplicity_vector_sha256": full_vector_hash,
        }
    )


def build_full_policy_freeze(
    issues: Sequence[IssueSpec],
    pools: Mapping[str, Sequence[MatchRecord]],
    detector_grid: Sequence[Mapping[str, object]],
    stage: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Freeze direct issue-level N7 selections and every exact arm ticket identity."""

    selection_sinks = [
        GzipRowSink(
            stage / f"policy_issue_selection_freeze_part_{index + 1:02d}_of_04.csv.gz"
        )
        for index in range(4)
    ]
    ledger_sinks = {
        arm: GzipRowSink(stage / f"ticket_arm_{arm.lower()}.csv.gz")
        for arm in (
            "B0_BEST_FULL",
            "D_MATCH_ONLY_FULL",
            "D_DIRECTION_ONLY",
            "D_JOINT_SPARSE",
        )
    }
    identity_catalog: dict[str, dict[str, object]] = {}
    allocation_catalog: dict[str, dict[str, object]] = {}
    vector_catalog: dict[str, bytes] = {}
    full_vector = core190.full_ticket_multiplicity_vector()
    full_vector_hash = register_vector(full_vector, vector_catalog)
    records_by_issue = {
        issue.issue: {record.match_id: record for record in pools[issue.issue]}
        for issue in issues
    }
    b0_frozen: dict[str, dict[str, object] | None] = {}
    for issue in issues:
        if not issue.b0_match_ids:
            b0_frozen[issue.issue] = None
            continue
        records = records_by_issue[issue.issue]
        if any(match_id not in records for match_id in issue.b0_match_ids):
            raise RuntimeError(
                f"B0 identity outside target-safe issue pool: {issue.issue}"
            )
        identity = register_identity(
            issue.issue,
            issue.b0_match_ids,
            identity_catalog,
            "INHERITED_B0_COMPARATOR",
        )
        b0_frozen[issue.issue] = {
            "identity": identity,
            "ticket_identity": full_ticket_identity(identity, full_vector_hash),
        }

    base_cache: dict[tuple[str, tuple[object, ...]], tuple[DetectorMetric, ...]] = {}
    directional_cache: dict[str, dict[str, object]] = {}
    forecast_rows: list[dict[str, object]] = []
    strata_rows: list[dict[str, object]] = []

    def frozen_directional(
        issue: IssueSpec,
        ordered_records: Sequence[MatchRecord],
        metrics: Sequence[DetectorMetric],
    ) -> dict[str, object]:
        metrics_by_match = {metric.record.match_id: metric for metric in metrics}
        cache_payload = {
            "issue": issue.issue,
            "ordered_match_ids": [record.match_id for record in ordered_records],
            "metrics": [
                {
                    "match_id": record.match_id,
                    "source": metrics_by_match[record.match_id].estimator_source,
                    "p": [
                        compact(value)
                        for value in metrics_by_match[record.match_id].allocation_p
                    ],
                    "magnitude": compact(metrics_by_match[record.match_id].magnitude),
                    "omitted": metrics_by_match[record.match_id].omitted_code,
                }
                for record in ordered_records
            ],
        }
        cache_key = core190.canonical_hash(cache_payload)
        if cache_key not in directional_cache:
            directional_cache[cache_key] = register_directional_allocation(
                issue.issue,
                ordered_records,
                metrics_by_match,
                identity_catalog,
                allocation_catalog,
                vector_catalog,
            )
        return directional_cache[cache_key]

    for policy_index, policy in enumerate(detector_grid):
        selection_sink = selection_sinks[
            min(3, policy_index * len(selection_sinks) // len(detector_grid))
        ]
        available = policy["availability"] == "AVAILABLE"
        selected_issue_count = 0
        selected_match_count = 0
        changed_from_b0_count = 0
        b0_direction_count = 0
        common_count = 0
        line_direction_matches: Counter[tuple[str, str]] = Counter()
        line_direction_issues: dict[tuple[str, str], set[str]] = defaultdict(set)

        for issue in issues:
            b0 = b0_frozen[issue.issue]
            selection_status = (
                "NO_BET_FROZEN" if available else "DIAGNOSTIC_UNAVAILABLE"
            )
            b0_full_row = (
                ticket_ledger_row(
                    policy,
                    issue,
                    "B0_BEST_FULL",
                    "FROZEN_EXECUTABLE",
                    str(b0["identity"]),
                    str(b0["ticket_identity"]),
                    full_vector_hash,
                )
                if b0 is not None
                else ticket_ledger_row(
                    policy, issue, "B0_BEST_FULL", "NO_BET_INHERITED_B0"
                )
            )
            ledger_sinks["B0_BEST_FULL"].emit(b0_full_row)

            selected: tuple[DetectorMetric, ...] | None = None
            b0_directional: dict[str, object] | None = None
            if available:
                cache_key = (issue.issue, base_metric_key(policy))
                if cache_key not in base_cache:
                    base_cache[cache_key] = sorted_base_metrics(
                        pools[issue.issue], policy
                    )
                selected = threshold_gated_n7(base_cache[cache_key], policy)

                if issue.b0_match_ids:
                    b0_records = tuple(
                        records_by_issue[issue.issue][match_id]
                        for match_id in issue.b0_match_ids
                    )
                    b0_metrics = tuple(
                        metric
                        for record in b0_records
                        if passes_base_gate(record, policy)
                        for metric in [
                            metric_for_record(
                                record,
                                str(policy["detector_family"]),
                                str(policy["estimator_variant"]),
                            )
                        ]
                        if metric is not None
                    )
                    ranked_b0 = tuple(
                        sorted(
                            b0_metrics,
                            key=lambda metric: (
                                -metric.magnitude,
                                metric.record.match_idx,
                                int(metric.record.match_id),
                            ),
                        )
                    )
                    gated_b0 = threshold_gated_n7(ranked_b0, policy)
                    if gated_b0 is not None and len(b0_metrics) == 7:
                        b0_directional = frozen_directional(
                            issue, b0_records, b0_metrics
                        )
                        b0_direction_count += 1

            if selected is None:
                selected_identity = ""
                selected_ticket_identity = ""
                joint = None
            else:
                selected_records = tuple(metric.record for metric in selected)
                selected_ids = tuple(record.match_id for record in selected_records)
                selected_identity = register_identity(
                    issue.issue, selected_ids, identity_catalog
                )
                selected_ticket_identity = full_ticket_identity(
                    selected_identity, full_vector_hash
                )
                joint = frozen_directional(issue, selected_records, selected)
                selected_issue_count += 1
                selected_match_count += 7
                if tuple(issue.b0_match_ids) != selected_ids:
                    changed_from_b0_count += 1
                if b0 is not None and b0_directional is not None:
                    common_count += 1
                for metric in selected:
                    key = (metric.record.line_stratum, metric.favored_code)
                    line_direction_matches[key] += 1
                    line_direction_issues[key].add(issue.issue)

            selection_sink.emit(
                {
                    "policy_id": policy["policy_id"],
                    "issue": issue.issue,
                    "year": issue.year,
                    "fold": issue.fold,
                    "issue_instance": issue.issue_instance,
                    "source_issue_instances_json": core190.canonical_json(
                        list(issue.source_issue_instances)
                    ).decode(),
                    "eligible_match_count": issue.eligible_match_count,
                    "policy_status": selection_status
                    if selected is None
                    else "SELECTED_PREOUTCOME",
                    "selected_n7_identity_sha256": selected_identity,
                    "selected_match_ids_json": core190.canonical_json(
                        [metric.record.match_id for metric in selected]
                    ).decode()
                    if selected
                    else "[]",
                    "strongest_match_id": selected[0].record.match_id
                    if selected
                    else "",
                    "strongest_magnitude": compact(selected[0].magnitude)
                    if selected
                    else "",
                    "strongest_abs_z": compact(selected[0].abs_z) if selected else "",
                    "strongest_favored_code": selected[0].favored_code
                    if selected
                    else "",
                    "strongest_omitted_code": selected[0].omitted_code
                    if selected
                    else "",
                    "strongest_estimator_source": selected[0].estimator_source
                    if selected
                    else "",
                    "joint_allocation_input_sha256": joint["allocation_input_sha256"]
                    if joint
                    else "",
                    "joint_multiplicity_vector_sha256": joint[
                        "multiplicity_vector_sha256"
                    ]
                    if joint
                    else "",
                    "inherited_b0_status": issue.b0_status,
                    "inherited_b0_identity_sha256": str(b0["identity"]) if b0 else "",
                    "identity_changed_from_b0": int(
                        bool(selected)
                        and tuple(metric.record.match_id for metric in selected)
                        != tuple(issue.b0_match_ids)
                    ),
                    "b0_direction_status": "AVAILABLE"
                    if b0_directional
                    else "NO_SIGNAL_OR_NO_B0",
                    "planned_stake_yuan": FULL_STAKE_YUAN if selected else 0,
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )

            ledger_sinks["D_MATCH_ONLY_FULL"].emit(
                ticket_ledger_row(
                    policy,
                    issue,
                    "D_MATCH_ONLY_FULL",
                    "FROZEN_EXECUTABLE" if selected else selection_status,
                    selected_identity,
                    selected_ticket_identity,
                    full_vector_hash if selected else "",
                )
            )
            ledger_sinks["D_DIRECTION_ONLY"].emit(
                ticket_ledger_row(
                    policy,
                    issue,
                    "D_DIRECTION_ONLY",
                    "FROZEN_EXECUTABLE"
                    if b0_directional
                    else selection_status
                    if not available
                    else "NO_BET_DIRECTION_SIGNAL",
                    str(b0_directional["n7_identity_sha256"]) if b0_directional else "",
                    str(b0_directional["ticket_identity_sha256"])
                    if b0_directional
                    else "",
                    str(b0_directional["multiplicity_vector_sha256"])
                    if b0_directional
                    else "",
                    str(b0_directional["allocation_input_sha256"])
                    if b0_directional
                    else "",
                )
            )
            ledger_sinks["D_JOINT_SPARSE"].emit(
                ticket_ledger_row(
                    policy,
                    issue,
                    "D_JOINT_SPARSE",
                    "FROZEN_EXECUTABLE" if joint else selection_status,
                    str(joint["n7_identity_sha256"]) if joint else "",
                    str(joint["ticket_identity_sha256"]) if joint else "",
                    str(joint["multiplicity_vector_sha256"]) if joint else "",
                    str(joint["allocation_input_sha256"]) if joint else "",
                )
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
                "cohort_issue_count": CANONICAL_ISSUES,
                "source_issue_instance_count": SOURCE_ISSUE_INSTANCES,
                "source_b0_participating_issue_count": SOURCE_B0_PARTICIPATING_ISSUES,
                "selected_issue_count": selected_issue_count,
                "no_bet_issue_count": CANONICAL_ISSUES - selected_issue_count,
                "selected_identity_count": selected_issue_count,
                "selected_match_count": selected_match_count,
                "identity_changed_from_b0_count": changed_from_b0_count,
                "b0_direction_available_issue_count": b0_direction_count,
                "factorial_common_issue_count": common_count,
                "native_planned_stake_yuan": selected_issue_count * FULL_STAKE_YUAN,
                "matched_equal_budget_stake_yuan": common_count * FULL_STAKE_YUAN,
                "forecast_status": "AVAILABLE"
                if available
                else "DIAGNOSTIC_UNAVAILABLE",
                "unavailable_reason": policy["unavailable_reason"],
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
                        "forecast_status": "AVAILABLE"
                        if available
                        else "DIAGNOSTIC_UNAVAILABLE",
                        "outcome_boundary": OUTCOME_BOUNDARY,
                    }
                )

    for sink in selection_sinks:
        sink.close()
    for sink in ledger_sinks.values():
        sink.close()
    expected_rows = len(detector_grid) * len(issues)
    if sum(sink.count for sink in selection_sinks) != expected_rows or any(
        sink.count != expected_rows for sink in ledger_sinks.values()
    ):
        raise RuntimeError("policy/arm ledger denominator drift")
    if len(forecast_rows) != len(detector_grid):
        raise RuntimeError("coverage forecast denominator drift")
    if len(strata_rows) != len(detector_grid) * len(LINE_STRATA) * len(
        DIRECTION_STRATA
    ):
        raise RuntimeError("line-direction forecast denominator drift")

    identity_rows = sorted(
        identity_catalog.values(), key=lambda row: row["identity_sha256"]
    )
    allocation_rows = sorted(
        allocation_catalog.values(), key=lambda row: row["allocation_input_sha256"]
    )
    vector_rows = []
    for vector_hash, vector in sorted(vector_catalog.items()):
        if vector_hash == full_vector_hash:
            stats = core190.validate_ticket_multiplicity_vector(vector)
        else:
            stats = core190.validate_ticket_multiplicity_vector(
                vector,
                next(
                    str(row["omitted_code"])
                    for row in allocation_rows
                    if row["multiplicity_vector_sha256"] == vector_hash
                ),
                next(
                    int(row["delete_leg_index_zero_based"])
                    for row in allocation_rows
                    if row["multiplicity_vector_sha256"] == vector_hash
                ),
            )
        vector_rows.append(
            {
                "multiplicity_vector_sha256": vector_hash,
                "encoding": "U8_HEX_BASE3_ORDINAL_3_1_0",
                "multiplicity_vector_hex": vector.hex(),
                **stats,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    write_gzip(stage / "n7_identity_catalog.csv.gz", identity_rows)
    write_gzip(stage / "directional_allocation_input_catalog.csv.gz", allocation_rows)
    write_gzip(stage / "ticket_multiplicity_vector_catalog.csv.gz", vector_rows)
    return (
        forecast_rows,
        strata_rows,
        {
            "selection_row_count": expected_rows,
            "selection_shard_count": len(selection_sinks),
            "selection_shard_row_counts": [sink.count for sink in selection_sinks],
            "arm_ledger_row_count_each": expected_rows,
            "identity_count": len(identity_rows),
            "allocation_input_count": len(allocation_rows),
            "multiplicity_vector_count": len(vector_rows),
            "full_vector_sha256": full_vector_hash,
        },
    )


# Superseded inherited-candidate selector.  The executable v2 path is
# build_full_policy_freeze(), which selects seven matches from each full issue.
def _superseded_v1_build_candidate_membership(
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
        values.sort(
            key=lambda row: (int(row["source_selector_rank"]), row["portfolio_id"])
        )
    return output, by_issue, membership


def _superseded_v1_build_policy_forecasts(
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
                retained = _superseded_v1_retained_metrics(
                    membership[(issue_instance, str(candidate["portfolio_id"]))],
                    estimator_by_match,
                    policy,
                )
                if retained:
                    score = math.fsum(
                        float(row["magnitude"]) for row in retained
                    ) / len(retained)
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
            b0_retained = _superseded_v1_retained_metrics(
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
                        "selected_identity_fingerprint": selected[
                            "identity_fingerprint"
                        ],
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
                        "b0_direction_status": "AVAILABLE"
                        if b0_retained
                        else "NO_SIGNAL",
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
                        "b0_direction_status": "AVAILABLE"
                        if b0_retained
                        else "NO_SIGNAL",
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

    available_policy_count = sum(
        row["availability"] == "AVAILABLE" for row in detector_grid
    )
    selection_sink.close()
    if selection_sink.count != available_policy_count * PARTICIPATING_ISSUES:
        raise RuntimeError(
            f"policy selection denominator drift: {selection_sink.count}"
        )
    if len(forecast_rows) != len(detector_grid):
        raise RuntimeError("policy forecast denominator drift")
    if len(strata_rows) != len(detector_grid) * len(LINE_STRATA) * len(
        DIRECTION_STRATA
    ):
        raise RuntimeError("line-direction forecast denominator drift")
    return forecast_rows, strata_rows, selection_sink.count


def _superseded_v1_build_issue_census(
    source_selection: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
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
                "source_b0_identity_fingerprint": source[
                    "selected_identity_fingerprint"
                ],
                "full_ticket_count": source["ticket_count"],
                "full_planned_stake_yuan": source["planned_stake_yuan"],
                "sparse_no_bet_semantics": "zero qualifying policy => 0 tickets, 0 stake, not a loss",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    if len(rows) != COHORT_ISSUES:
        raise RuntimeError("issue census denominator drift")
    return rows


def build_full_issue_census(issues: Sequence[IssueSpec]) -> list[dict[str, object]]:
    rows = []
    for issue in issues:
        rows.append(
            {
                "issue": issue.issue,
                "year": issue.year,
                "fold": issue.fold,
                "issue_instance": issue.issue_instance,
                "source_issue_instances_json": core190.canonical_json(
                    list(issue.source_issue_instances)
                ).decode(),
                "source_issue_instance_count": len(issue.source_issue_instances),
                "feature_cutoff_ts": issue.cutoff_ts,
                "eligible_target_safe_match_count": issue.eligible_match_count,
                "source_b0_status": issue.b0_status,
                "source_b0_portfolio_id": issue.b0_portfolio_id,
                "source_b0_identity_fingerprint": issue.b0_identity_fingerprint,
                "source_b0_match_ids_json": core190.canonical_json(
                    list(issue.b0_match_ids)
                ).decode(),
                "full_ticket_count": FULL_TICKETS if issue.b0_match_ids else 0,
                "full_planned_stake_yuan": FULL_STAKE_YUAN if issue.b0_match_ids else 0,
                "sparse_no_bet_semantics": "zero qualifying direct N7 => 0 tickets, 0 stake, not a loss",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    if len(rows) != CANONICAL_ISSUES:
        raise RuntimeError("full issue census denominator drift")
    return rows


def build_estimator_registry() -> list[dict[str, object]]:
    return [
        {
            "estimator": "FUNDAMENTAL_INDEPENDENT",
            "frozen_source": "#180 T1_DEEP_TEAM / TEAM_PRIMARY",
            "p_vector": "p3/p1/p0 mapped from one group-mass-reconciled T1 score-difference distribution",
            "expected_margin": "mean of that exact same T1 score-difference distribution",
            "score_distribution": "family score-difference log-pool shape with within-code masses reconciled exactly to T1_DEEP_TEAM p3/p1/p0; this distribution controls both p and margin",
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
            "frozen_source": "#179 accepted primary hierarchical market model from target-safe 1h market features",
            "p_vector": "calibrated_p3/p1/p0",
            "expected_margin": "UNAVAILABLE_MARKET_DERIVED_THREE_WAY_VECTOR",
            "score_distribution": "UNAVAILABLE",
            "independence_status": "MARKET_DERIVED_NOT_INDEPENDENT",
            "detector_role": "CONTROLLING_SEPARATE_VIEW",
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        {
            "estimator": "HANDICAP_CONSENSUS",
            "frozen_source": "#179 EURO_CALIBRATION family aligned to the native handicap from target-safe 1h EURO",
            "p_vector": "consensus_p3/p1/p0",
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
    independent = [row for row in rows if row["estimator"] == "FUNDAMENTAL_INDEPENDENT"]
    forbidden = ("EURO", "ASIAN", "BJ_SP", "LIQUIDITY", "MARKET", "TL_")
    if len(independent) != len(core190.FAMILY_ORDER):
        raise RuntimeError("independent feature-family denominator drift")
    for row in independent:
        serialized = " ".join(
            str(row[field])
            for field in ("source_branch", "feature_family", "feature_definition")
        ).upper()
        if int(row["uses_market_input"]) or any(
            token in serialized for token in forbidden
        ):
            raise RuntimeError(
                "market-derived feature leaked into independent estimator"
            )
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


def chronology_bootstrap_contract(
    issue_census: Sequence[Mapping[str, object]],
) -> dict[str, object]:
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
        "gate_b_row_keys": ["policy_id", "issue", "arm"],
        "gate_a_exact_identity_sources": {
            "policy_issue_selection": "policy_issue_selection_freeze_part_XX_of_04.csv.gz (four policy-contiguous shards)",
            "four_arm_ticket_ledgers": "ticket_arm_<arm>.csv.gz",
            "n7_identity_catalog": "n7_identity_catalog.csv.gz",
            "directional_allocation_catalog": "directional_allocation_input_catalog.csv.gz",
            "multiplicity_vector_catalog": "ticket_multiplicity_vector_catalog.csv.gz",
            "market_model_training_freeze": "market_model_training_freeze.csv",
        },
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
            "cli_contract": "--database PATH",
            "environment_contract": DB_ENVIRONMENT_VARIABLE,
            "resolution_order": "explicit CLI, environment, local repository ancestry",
            "hash_verification": "mandatory before any generation source read",
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


def source_binding_v2(
    source_rows: Sequence[Mapping[str, object]],
    estimator_meta: Mapping[str, object],
    line_counts: Mapping[str, int],
) -> dict[str, object]:
    binding = source_binding(source_rows)
    binding["database"]["target_projection"] = [  # type: ignore[index]
        "every match in each canonical numeric issue with kickoff/team IDs",
        "complete target-safe 1h EURO consensus",
        "non-null native handicap line; missing lines are excluded from executable policies",
        "#179 target-safe market feature projection",
    ]
    binding["eligible_universe"] = {
        "source_issue_instance_count": SOURCE_ISSUE_INSTANCES,
        "canonical_numeric_issue_count": CANONICAL_ISSUES,
        "eligible_match_count": ELIGIBLE_MATCHES,
        "excluded_missing_native_line_match_count": EXCLUDED_MISSING_NATIVE_LINE_MATCHES,
        "minimum_matches_per_issue": 7,
        "canonicalization": "duplicate cross-year issue instances collapse by numeric issue; canonical year=max source outer year; source instances retained",
        "universe_identity_sha256": estimator_meta["universe_identity_sha256"],
        "native_line_exact_counts": dict(sorted(line_counts.items())),
        "selection_boundary": "challenger chooses exact seven directly from every issue target-safe pool; inherited B0 is comparator only",
        "cutoff_rule": "minimum kickoff timestamp in the target-safe outer issue pool; non-eligible raw placeholders cannot define cutoff",
        "cutoff_reporting_year_plausibility": "reporting_year - cutoff_calendar_year must be 0 or 1",
        "cutoff_regression_anchors": CUTOFF_REGRESSION_ANCHORS,
    }
    binding["chronological_market_model"] = {
        "source": "accepted #179 HierarchicalLeagueModel",
        "snapshot_count": estimator_meta["market_training_issue_count"],
        "training_rule": "kickoff <= feature cutoff - 180 minutes (inclusive)",
        "training_min_rows": estimator_meta["market_training_min_rows"],
        "training_max_rows": estimator_meta["market_training_max_rows"],
        "target_issue_overlap_zero": estimator_meta[
            "market_training_all_target_overlap_zero"
        ],
        "team_target_issue_overlap_zero": estimator_meta[
            "team_training_all_target_overlap_zero"
        ],
        "clean_target_exclusion_rebuild_issues": estimator_meta[
            "clean_target_exclusion_rebuild_issues"
        ],
        "binding_file": "market_model_training_freeze.csv",
        "reporting_year": "retained separately; never used as the training cutoff",
    }
    binding["coherent_t1_estimator"] = {
        "probability_source": "mapped p3/p1/p0 of group-mass-reconciled T1 score-difference distribution",
        "expected_margin_source": "mean of the identical score-difference distribution",
        "line_residual": "same-distribution expected margin + native handicap",
        "weighted_lambda_proxy": "diagnostic only; controls_direction=false",
        "weighted_proxy_sign_disagreement_count": estimator_meta[
            "weighted_proxy_sign_disagreement_count"
        ],
        "max_abs_probability_reconciliation_error": compact(
            float(estimator_meta["max_abs_reconciliation_error"])
        ),
    }
    return binding


def directional_ticket_contract_v2(
    policy_meta: Mapping[str, object],
) -> dict[str, object]:
    contract = core190.directional_ticket_accounting()
    contract.update(
        {
            "ticket_ordinal": "base-3 code order 3,1,0; ascending ordinal is the deterministic tie break",
            "delete_leg": "strongest divergence magnitude; ties match_idx then match_id",
            "per_leg_probability_sources": {
                "FUNDAMENTAL_INDEPENDENT": "T1 coherent score-distribution p",
                "CALIBRATED_MARKET_ESTIMATOR": "#179 primary calibrated market p",
                "UNION": "per match, larger-magnitude source; exact tie fundamental first; never blended",
                "MODEL_AGREEMENT": "per match, weaker agreeing source; exact tie fundamental first; never blended",
                "LINE_RESIDUAL_MU": "T1 coherent score-distribution p",
            },
            "identity_layers": [
                "ordered seven-match N7 identity",
                "directional allocation input identity",
                "2187-byte u8 multiplicity-vector SHA-256",
                "combined ticket identity",
            ],
            "ledger_scope": "every frozen policy x canonical issue x each of four arms",
            "ledger_row_count_each": policy_meta["arm_ledger_row_count_each"],
            "allocation_input_count": policy_meta["allocation_input_count"],
            "multiplicity_vector_count": policy_meta["multiplicity_vector_count"],
            "full_vector_sha256": policy_meta["full_vector_sha256"],
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
    )
    return contract


def _superseded_v1_gate_a_card(
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


def gate_a_card_v2(
    detector_grid: Sequence[Mapping[str, object]],
    forecasts: Sequence[Mapping[str, object]],
    estimator_meta: Mapping[str, object],
    policy_meta: Mapping[str, object],
) -> dict[str, object]:
    available = [row for row in forecasts if row["forecast_status"] == "AVAILABLE"]
    selected_counts = [int(row["selected_issue_count"]) for row in available]
    return {
        "issue": ISSUE,
        "contract": CONTRACT,
        "version": VERSION,
        "stage": "GATE_A_OUTCOME_UNEXPOSED",
        "status": "READY_FOR_PI_REVIEW_NO_GATE_B_AUTHORITY",
        "cohort": {
            "source_issue_instance_count": SOURCE_ISSUE_INSTANCES,
            "canonical_numeric_issue_count": CANONICAL_ISSUES,
            "eligible_match_count": ELIGIBLE_MATCHES,
            "excluded_missing_native_line_match_count": EXCLUDED_MISSING_NATIVE_LINE_MATCHES,
            "source_b0_participating_issue_count": SOURCE_B0_PARTICIPATING_ISSUES,
            "source_b0_no_bet_issue_count": CANONICAL_ISSUES
            - SOURCE_B0_PARTICIPATING_ISSUES,
        },
        "expected_margin_resolution": {
            "fundamental_source": "#180 T1_DEEP_TEAM / TEAM_PRIMARY pure-team branch",
            "controlling_probability_and_margin_identity": "ONE_T1_GROUP_MASS_RECONCILED_SCORE_DIFFERENCE_DISTRIBUTION",
            "line_residual_definition": "same-distribution expected raw margin + native handicap",
            "weighted_component_lambda_proxy_status": "DIAGNOSTIC_DOES_NOT_CONTROL_DIRECTION",
            "weighted_proxy_sign_disagreement_count": estimator_meta[
                "weighted_proxy_sign_disagreement_count"
            ],
            "max_abs_probability_reconciliation_error": compact(
                float(estimator_meta["max_abs_reconciliation_error"])
            ),
            "consensus_margin_status": "UNAVAILABLE_NON_IDENTIFIABLE",
            "delta_mu_status": "DIAGNOSTIC_UNAVAILABLE_ALL_MATCHES",
            "delta_p_status": "CONTROLLING",
            "line_residual_mu_status": "CONTROLLING_SEPARATE_AXIS",
        },
        "native_line_coverage": estimator_meta["line_strata"],
        "chronological_market_model": {
            "snapshot_count": estimator_meta["market_training_issue_count"],
            "training_rule": "kickoff <= feature cutoff - 180 minutes (inclusive)",
            "target_issue_overlap_zero": estimator_meta[
                "market_training_all_target_overlap_zero"
            ],
            "team_target_issue_overlap_zero": estimator_meta[
                "team_training_all_target_overlap_zero"
            ],
            "clean_target_exclusion_rebuild_issues": estimator_meta[
                "clean_target_exclusion_rebuild_issues"
            ],
            "binding_file": "market_model_training_freeze.csv",
            "cutoff_rule": "minimum kickoff timestamp in the target-safe outer issue pool",
            "cutoff_regression_anchors": CUTOFF_REGRESSION_ANCHORS,
        },
        "detector_grid": {
            "policy_count": len(detector_grid),
            "available_policy_count": len(available),
            "unavailable_delta_mu_policy_count": len(detector_grid) - len(available),
            "policy_issue_selection_row_count": policy_meta["selection_row_count"],
            "minimum_selected_issue_count": min(selected_counts),
            "maximum_selected_issue_count": max(selected_counts),
            "zero_candidate_policy_count": sum(value == 0 for value in selected_counts),
        },
        "ticket_identity_freeze": dict(policy_meta),
        "arms": [
            "B0_BEST_FULL",
            "D_MATCH_ONLY_FULL",
            "D_DIRECTION_ONLY",
            "D_JOINT_SPARSE",
        ],
        "accounting": {
            "all_selected_arms_ticket_count": FULL_TICKETS,
            "all_selected_arms_stake_yuan": FULL_STAKE_YUAN,
            "directional_unique_ticket_count": 1458,
            "directional_repeated_ticket_count": 729,
            "directional_max_multiplicity": 2,
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
    named_rows: Mapping[str, Sequence[Mapping[str, object]]],
) -> None:
    for name, rows in named_rows.items():
        if not rows:
            raise RuntimeError(f"empty required Gate-A table: {name}")
        fields = {str(field).lower() for field in rows[0]}
        forbidden = fields.intersection(FORBIDDEN_TARGET_FIELDS)
        if forbidden:
            raise RuntimeError(
                f"Gate-A table {name} exposes forbidden fields: {forbidden}"
            )
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


def assert_file_header_outcome_safe(path: Path) -> None:
    opener = gzip.open if path.suffix == ".gz" else Path.open
    if path.suffix == ".gz":
        handle = opener(path, "rt", encoding="utf-8", newline="")
    else:
        handle = opener(path, "r", encoding="utf-8", newline="")
    with handle:
        header = next(csv.reader(handle))
    forbidden = {field.lower() for field in header}.intersection(
        FORBIDDEN_TARGET_FIELDS
    )
    if forbidden:
        raise RuntimeError(
            f"Gate-A file {path.name} exposes forbidden fields: {forbidden}"
        )


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
        runner180 = load_module(
            "bj190_v2_source_180_runner",
            ROOT / "scripts" / "freeze_bj180_team_matchup_gate_a.py",
        )
        source = runner180.load_sources()
        issues, line_counts = build_canonical_issue_specs(database, source)
        pools, estimator_meta = build_full_estimator_freeze(
            database,
            issues,
            stage / "poisson_latent_reconciliation.csv.gz",
            stage / "estimator_match_freeze.csv.gz",
            stage / "market_model_training_freeze.csv",
        )
        detector_grid = build_detector_grid()
        forecasts, strata, policy_meta = build_full_policy_freeze(
            issues,
            pools,
            detector_grid,
            stage,
        )
        issue_census = build_full_issue_census(issues)
        estimators = build_estimator_registry()
        estimator_provenance = build_estimator_provenance_registry()
        arms = build_attribution_arms()
        assert_gate_a_schema(
            {
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

        write_csv(stage / "detector_grid.csv", detector_grid)
        write_gzip(stage / "coverage_forecast.csv.gz", forecasts)
        write_gzip(stage / "line_direction_forecast.csv.gz", strata)
        write_csv(stage / "issue_census.csv", issue_census)
        write_csv(stage / "estimator_registry.csv", estimators)
        write_csv(stage / "estimator_provenance_registry.csv", estimator_provenance)
        write_csv(stage / "attribution_arm_registry.csv", arms)
        write_csv(stage / "source_census.csv", source_rows)
        write_json(
            stage / "directional_ticket_contract.json",
            directional_ticket_contract_v2(policy_meta),
        )
        write_json(
            stage / "chronology_bootstrap_contract.json",
            chronology_bootstrap_contract(issue_census),
        )
        write_json(stage / "output_schema_contract.json", output_schema_contract())
        binding = source_binding_v2(source_rows, estimator_meta, line_counts)
        write_json(stage / "source_binding.json", binding)
        card = gate_a_card_v2(detector_grid, forecasts, estimator_meta, policy_meta)
        write_json(stage / "gate_a_card.json", card)
        (stage / "README.md").write_text(
            "# #190 Gate A — sparse independent-model vs handicap divergence\n\n"
            "This immutable package freezes all 101,970 target-safe matches with an observed native "
            "handicap in 344 canonical numeric "
            "issues (348 source issue instances). Every divergence policy selects its exact seven "
            "matches directly from that issue pool; inherited B0 is a comparator only.\n\n"
            "Issue cutoff is the minimum kickoff in the same target-safe outer source pool; raw "
            "non-eligible placeholders cannot define chronology. The 252 otherwise target-safe rows "
            "with missing native handicap are excluded from every "
            "executable selector and ticket. The #179 market model is snapshotted separately at each "
            "issue's cutoff using only score rows available through cutoff minus 180 minutes; each "
            "snapshot binds its maximum training time, row count, cumulative history hash and zero "
            "target-issue overlap. Reporting year never defines the training cutoff.\n\n"
            "The controlling independent estimator is exact #180 `T1_DEEP_TEAM` / `TEAM_PRIMARY`. "
            "One reconciled score-difference distribution supplies both p3/p1/p0 and expected margin. "
            "The weighted component-lambda margin is diagnostic only and never controls direction. "
            "#179 and all #180 TL market-derived branches remain excluded from independent evidence.\n\n"
            "`HANDICAP_CONSENSUS` is #179's EURO-calibration family on the native handicap using only "
            "target-safe 1h EURO inputs. "
            "Three-way prices do not identify a unique raw expected margin, so `delta_mu` is explicitly "
            "unavailable and executes no policies. `delta_p` and model-vs-line `line_residual_mu` are "
            "separate controlling axes and are never blended.\n\n"
            "Each policy×issue×arm row binds an exact ordered N7 identity and an exact 2,187-byte "
            "ticket multiplicity vector. Directional arms delete one code at the strongest leg, retain "
            "1,458 unique tickets and repeat exactly 729 by joint probability with base-3 ties.\n\n"
            "No target outcome, final/winning SP, payout, tax, ROI or settlement data is present. Gate B, "
            "production and betting are not authorized.\n",
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

        for path in stage.iterdir():
            if path.suffix in {".csv", ".gz"}:
                assert_file_header_outcome_safe(path)

        manifest = manifest_for(stage)
        write_json(stage / "SHA256SUMS.json", manifest)
        content_identity = {
            "package": PACKAGE_NAME,
            "contract": CONTRACT,
            "version": VERSION,
            "manifest_sha256": sha256_file(stage / "SHA256SUMS.json"),
            "source_binding_sha256": sha256_file(stage / "source_binding.json"),
            "gate_a_card_sha256": sha256_file(stage / "gate_a_card.json"),
            "detector_grid_sha256": sha256_file(stage / "detector_grid.csv"),
            "policy_issue_selection_shards": {
                path.name: sha256_file(path)
                for path in sorted(
                    stage.glob("policy_issue_selection_freeze_part_*_of_04.csv.gz")
                )
            },
            "estimator_match_freeze_sha256": sha256_file(
                stage / "estimator_match_freeze.csv.gz"
            ),
            "market_model_training_freeze_sha256": sha256_file(
                stage / "market_model_training_freeze.csv"
            ),
            "poisson_latent_reconciliation_sha256": sha256_file(
                stage / "poisson_latent_reconciliation.csv.gz"
            ),
            "ticket_multiplicity_vector_catalog_sha256": sha256_file(
                stage / "ticket_multiplicity_vector_catalog.csv.gz"
            ),
            "directional_allocation_input_catalog_sha256": sha256_file(
                stage / "directional_allocation_input_catalog.csv.gz"
            ),
            "counts": card["cohort"],
            "policy_count": len(detector_grid),
            "selection_row_count": policy_meta["selection_row_count"],
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
            "selection_row_count": policy_meta["selection_row_count"],
            "coverage_min": card["detector_grid"]["minimum_selected_issue_count"],
            "coverage_max": card["detector_grid"]["maximum_selected_issue_count"],
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help=(
            "canonical SQLite source; alternatively set "
            f"{DB_ENVIRONMENT_VARIABLE}; SHA-256 is always verified"
        ),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    receipt = atomic_generate(args.output, locate_database(args.database))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
