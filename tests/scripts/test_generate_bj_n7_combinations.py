from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/generate_bj_n7_combinations.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_bj_n7_combinations", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_safe_projection(path: Path, mod) -> str:
    rows = []
    for idx in range(1, 8):
        rows.append({
            "issue": "26071", "match_idx": str(idx), "match_id": f"26071_{idx:03d}",
            "kickoff_ts": "2026-01-01T00:00:00Z", "decision_cutoff_ts": "2025-12-31T20:00:00Z",
            "snapshot_ts": "2025-12-31T19:00:00Z", "quoted_sp_3": "3.00000000",
            "quoted_sp_1": "3.00000000", "quoted_sp_0": "3.00000000",
        })
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=mod.SAFE_SCHEMA, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config(path: Path, sha: str, mod) -> None:
    path.write_text(json.dumps({"safe_input_filename": "safe_input_v1.csv", "safe_input_sha256": sha, "safe_input_schema": list(mod.SAFE_SCHEMA)}, sort_keys=True), encoding="utf-8")


def test_generator_rejects_forbidden_schema_before_rows_are_used(tmp_path: Path) -> None:
    mod = _load_module()
    source = tmp_path / "safe_input_v1.csv"
    source.write_text("issue,match_idx,match_id,official_result_code\n26071,1,a,x\n", encoding="utf-8")
    config_path = tmp_path / "config.json"; _config(config_path, hashlib.sha256(source.read_bytes()).hexdigest(), mod)
    with pytest.raises(mod.FreezeError, match="schema mismatch"):
        mod.read_safe_projection(source, mod.read_config(config_path))


def test_ratio_quota_exact_floor_and_lexical_tie_break() -> None:
    mod = _load_module()
    # This synthetic pool contains no real issue data.  Both candidates meet the
    # one-ticket 35% floors; identical score makes lower rank win deterministically.
    first = mod.Candidate(("3", "3", "3", "0", "0", "0", "1"), (0,), (3, 3, 1), 0.5, 1.0, 1.3)
    second = mod.Candidate(("3", "3", "3", "0", "0", "0", "1"), (1,), (3, 3, 1), 0.5, 1.0, 1.3)
    chosen = mod._best_exact_quota([second, first], 1)
    assert chosen == [first]
    assert mod.quota_targets(1) == (3, 3, 1)


def test_output_is_byte_identical_and_asserts_band_uniqueness_and_k(tmp_path: Path) -> None:
    mod = _load_module()
    safe = tmp_path / "safe_input_v1.csv"; sha = _write_safe_projection(safe, mod)
    config = tmp_path / "config.json"; _config(config, sha, mod)
    legs = mod.read_safe_projection(safe, mod.read_config(config))
    selected = mod.select_legs(legs, "26071")
    assert selected and all(len(leg.band_codes()) == 3 for leg in selected)
    pool = mod.candidates(selected, universe="SP_BAND_ONLY")
    assert len(pool) == len({item.sequence for item in pool}) == 2187
    top = mod.candidate_order(pool)[:32]
    assert len(top) == 32
    assert all(all(2.5 <= leg.price(code) <= 4.5 for leg, code in zip(selected, item.sequence)) for item in top)
    ids = mod._append_combinations([], "26071", "MARKET_IMPLIED_COVERAGE_DIAGNOSTIC", "32", selected, top)
    assert len(ids.splitlines()) == 32
    rows = [mod._row("26071", "MARKET_IMPLIED_COVERAGE_DIAGNOSTIC", "32", "PASS", top, diagnostic=False, selected_ids=ids)]
    for output in (tmp_path / "one", tmp_path / "two"):
        mod.write_freeze(output, [], rows, input_path=safe, config_path=config, git_head="a" * 40)
    assert (tmp_path / "one" / "SHA256SUMS").read_bytes() == (tmp_path / "two" / "SHA256SUMS").read_bytes()
    assert (tmp_path / "one" / "manifest.json").read_bytes() == (tmp_path / "two" / "manifest.json").read_bytes()
