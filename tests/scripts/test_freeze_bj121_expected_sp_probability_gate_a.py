"""Contract tests for #121's outcome-unexposed Gate-A freeze."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/freeze_bj121_expected_sp_probability_gate_a.py"
PACKAGE = ROOT / "results/bj121_gate_a_preoutcome_v3"


def load():
    spec = importlib.util.spec_from_file_location("bj121_gatea", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def test_expected_sp_is_probability_weighted_sum() -> None:
    module = load()
    rows = [
        {"candidate_code": "3", "p_cal": "0.50", "predicted_sp": "1.80"},
        {"candidate_code": "1", "p_cal": "0.30", "predicted_sp": "3.40"},
        {"candidate_code": "0", "p_cal": "0.20", "predicted_sp": "5.00"},
    ]
    feature = module.outcome_unexposed_feature(rows)
    assert feature["e_sp"] == 0.5 * 1.8 + 0.3 * 3.4 + 0.2 * 5.0
    assert feature["argmin_code"] == "0"
    assert feature["argmax_code"] == "3"


def test_probability_threshold_assigns_full_double_and_banker_roles() -> None:
    module = load()
    rule = {"low_p_max": 0.25, "banker_p_max_min": 0.50}
    full = {"p_min": 0.27, "p_max": 0.45, "argmin_code": "0", "argmax_code": "3"}
    double = {"p_min": 0.24, "p_max": 0.46, "argmin_code": "0", "argmax_code": "3"}
    banker = {"p_min": 0.18, "p_max": 0.55, "argmin_code": "0", "argmax_code": "3"}
    assert module.role_for("MIXED", full, rule) == ("FULL", "310", "")
    assert module.role_for("MIXED", double, rule) == ("DOUBLE", "31", "0")
    assert module.role_for("MIXED", banker, rule) == ("SINGLE", "3", "10")
    assert module.role_for("PRUNE", banker, rule) == ("DOUBLE", "31", "0")


def test_complete_native_pool_denominator_and_deterministic_matrix() -> None:
    module = load()
    counts: Counter[tuple[str, str]] = Counter()
    pool_ids: set[str] = set()
    with gzip.open(PACKAGE / "portfolio_frontier.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            counts[(row["variant_id"], row["arm"])] += 1
            pool_ids.add(row["pool_id"])
    assert len(counts) == len(module.VARIANTS) * len(module.ARMS)
    assert set(counts.values()) == {2659}
    assert len(pool_ids) == 2659
    assert sum(counts.values()) == 9 * 13 * 2659


def test_frozen_package_has_every_role_and_no_outcome_source() -> None:
    roles: Counter[str] = Counter()
    with gzip.open(PACKAGE / "candidate_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            roles[row["role"]] += 1
    assert all(roles[role] > 0 for role in ("FULL", "DOUBLE", "SINGLE"))
    source = (PACKAGE / "runner.py").read_text(encoding="utf-8")
    for prohibited in ("bj95_gate_b", "canonical_outcome", "settlement_runner", "final_sp_product"):
        assert prohibited not in source
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["gate_b"].startswith("NOT_RUN and NOT_AUTHORIZED")
    assert card["features"].startswith("Per-match E_SP=sum_code")


def test_manifest_complete_and_replay_portable_content_identical(tmp_path: Path) -> None:
    module = load()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        item.name: file_hash(item)
        for item in PACKAGE.iterdir()
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    assert manifest == actual
    replay = tmp_path / "replay"
    module.freeze(replay)
    committed_identity = json.loads((PACKAGE / "CONTENT_IDENTITY.json").read_text())
    replay_identity = json.loads((replay / "CONTENT_IDENTITY.json").read_text())
    assert replay_identity == committed_identity
    replay_manifest = json.loads((replay / "SHA256SUMS.json").read_text())
    for name, expected_hash in committed_identity["non_compressed_controls"].items():
        assert replay_manifest[name] == expected_hash == manifest[name]
