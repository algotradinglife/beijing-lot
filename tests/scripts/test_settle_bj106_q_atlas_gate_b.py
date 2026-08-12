from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj106_q_atlas_gate_b.py"
PACKAGE = ROOT / "results" / "bj106_gate_b_outcome_settlement_v1"


def load():
    spec = importlib.util.spec_from_file_location("bj106_gate_b", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bootstrap_rng_and_bh_are_deterministic():
    mod = load()
    assert list(mod.stable_bootstrap_indices("frozen", 7, 8)) == list(
        mod.stable_bootstrap_indices("frozen", 7, 8)
    )
    assert mod.benjamini_hochberg(
        {"a": mod.Decimal("0.01"), "b": mod.Decimal("0.04"), "c": mod.Decimal("0.03")}
    ) == {"a": mod.Decimal("0.03"), "b": mod.Decimal("0.04"), "c": mod.Decimal("0.04")}


def test_comparison_eligibility_is_frozen_and_has_no_factor_threshold():
    mod = load()
    eligible = {
        "nomination_eligible": "TRUE", "stratum_support": "500",
        "stratum_year_count": "3", "fallback_level": "L1_EXACT_HANDICAP",
    }
    assert mod.comparison_eligible(eligible)
    assert not mod.comparison_eligible({**eligible, "fallback_level": "L5_CODE_ONLY"})
    assert not mod.comparison_eligible({**eligible, "stratum_support": "499"})


def test_committed_package_is_complete_and_manifest_bound():
    mod = load()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    actual = {
        path.name: mod.sha256(path)
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert manifest == actual
    card = json.loads((PACKAGE / "settlement_card.json").read_text())
    assert card["rows"] == {"comparison_family": 14, "frozen_atlas": 143457, "settled": 140406, "unavailable": 3051}
    assert card["factor_boundary"].startswith("0.65 is absent")
    with gzip.open(PACKAGE / "settled_q_atlas.csv.gz", "rt", newline="") as handle:
        rows = csv.DictReader(handle)
        status = {"SETTLED": 0, "UNAVAILABLE_CANONICAL_OUTCOME": 0}
        for row in rows:
            status[row["outcome_status"]] += 1
    assert status == {"SETTLED": 140406, "UNAVAILABLE_CANONICAL_OUTCOME": 3051}


def test_packaged_runner_replays_portably_to_same_content_identity():
    with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
        temp = Path(temporary)
        runner = temp / "settlement_runner.py"
        shutil.copy2(PACKAGE / "settlement_runner.py", runner)
        replay = temp / "replay"
        subprocess.run(
            [
                sys.executable, str(runner), "--output", str(replay), "--gate-a",
                str(ROOT / "results" / "bj106_gate_a_preoutcome_v2r1"),
                "--canonical-outcomes", str(ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"),
            ],
            cwd=temp, check=True, timeout=180,
        )
        assert (replay / "CONTENT_IDENTITY.json").read_bytes() == (
            PACKAGE / "CONTENT_IDENTITY.json"
        ).read_bytes()
        assert hashlib.sha256((replay / "SHA256SUMS.json").read_bytes()).hexdigest() == hashlib.sha256(
            (PACKAGE / "SHA256SUMS.json").read_bytes()
        ).hexdigest()
