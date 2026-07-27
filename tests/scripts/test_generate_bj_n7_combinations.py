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
CONFIG = ROOT / "evidence/bj_n7_compress_001/freeze_config_v1.json"
SAFE_INPUT = ROOT / "evidence/bj_n7_compress_001/safe_input_v1.csv"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_bj_n7_combinations", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _csv_bytes(rows: list[dict[str, str]], fields: tuple[str, ...]) -> bytes:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def test_generator_rejects_alternate_config_and_same_named_input(tmp_path: Path) -> None:
    mod = _load_module()
    source = tmp_path / "safe_input_v1.csv"
    source.write_text("issue,match_idx,match_id,official_result_code\n26071,1,a,x\n", encoding="utf-8")
    config_path = tmp_path / "freeze_config_v1.json"
    config_path.write_text(json.dumps({
        "experiment": mod.EXPERIMENT,
        "safe_input_filename": source.name,
        "safe_input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "safe_input_schema": list(mod.SAFE_SCHEMA),
        "source_sha256": mod.AUTHORIZED_SOURCE_SHA256,
    }), encoding="utf-8")
    with pytest.raises(mod.FreezeError, match="unauthorized freeze config"):
        mod.read_config(config_path)

    config = mod.read_config(CONFIG)
    with pytest.raises(mod.FreezeError, match="safe input SHA-256 mismatch"):
        mod.read_safe_projection(source, config)


@pytest.mark.parametrize("raw", ["NaN", "inf", "-inf"])
def test_generator_rejects_non_finite_sp(raw: str) -> None:
    mod = _load_module()
    row = {f"quoted_sp_{code}": "3.0" for code in mod.CODE_ORDER}
    row["quoted_sp_3"] = raw
    with pytest.raises(mod.FreezeError, match="invalid safe input row"):
        mod._parse_sp(row)


def test_ratio_quota_exact_floor_and_lexical_tie_break() -> None:
    mod = _load_module()
    # This synthetic pool contains no real issue data.  Both candidates meet the
    # one-ticket 35% floors; identical score makes lower rank win deterministically.
    first = mod.Candidate(("3", "3", "3", "0", "0", "0", "1"), (0,), (3, 3, 1), 0.5, 1.0, 1.3)
    second = mod.Candidate(("3", "3", "3", "0", "0", "0", "1"), (1,), (3, 3, 1), 0.5, 1.0, 1.3)
    chosen = mod._best_exact_quota([second, first], 1)
    assert chosen == [first]
    assert mod.quota_targets(1) == (3, 3, 1)


def test_non_uniform_full_universe_k256_is_stable(
    capfd: pytest.CaptureFixture[str],
) -> None:
    mod = _load_module()
    prices = (
        (3.75, 3.98, 4.09),
        (4.38, 3.98, 4.34),
        (2.56, 3.43, 4.39),
        (3.80, 4.30, 2.73),
        (3.44, 2.99, 3.59),
        (3.65, 2.53, 2.93),
        (3.06, 4.33, 4.03),
    )
    legs = tuple(
        mod.Leg("26071", idx, f"synthetic_non_uniform_{idx}", "k", "c", "s", sp)
        for idx, sp in enumerate(prices, 1)
    )
    pool = mod.candidates(legs, universe="SP_BAND_ONLY")
    assert len(pool) == 2187
    first = mod._best_exact_quota(pool, 256)
    second = mod._best_exact_quota(pool, 256)
    assert first is not None and second is not None
    assert [item.sequence for item in first] == [item.sequence for item in second]
    assert len({item.sequence for item in first}) == 256
    need3, need0, _need1 = mod.quota_targets(256)
    assert sum(item.counts[0] for item in first) >= need3
    assert sum(item.counts[1] for item in first) >= need0
    assert capfd.readouterr() == ("", "")


def test_full_generate_k256_is_byte_identical_and_enforces_constraints(tmp_path: Path) -> None:
    mod = _load_module()
    legs = [
        mod.Leg("26071", idx, f"synthetic_{idx}", "k", "c", "s", (3.0, 3.0, 3.0))
        for idx in range(1, 8)
    ]
    combinations_one, summary_one = mod.generate(legs)
    combinations_two, summary_two = mod.generate(legs)
    assert _csv_bytes(combinations_one, tuple(combinations_one[0])) == _csv_bytes(
        combinations_two, tuple(combinations_two[0])
    )
    assert _csv_bytes(summary_one, tuple(summary_one[0])) == _csv_bytes(
        summary_two, tuple(summary_two[0])
    )

    selected = mod.select_legs(legs, "26071")
    assert selected and all(len(leg.band_codes()) == 3 for leg in selected)
    k256 = [
        row for row in combinations_one
        if row["issue"] == "26071"
        and row["arm"] == "TOPK_RATIO_CONSTRAINED"
        and row["k"] == "256"
    ]
    assert len(k256) == 256
    assert len({row["combination_id"] for row in k256}) == 256
    assert len({row["sequence"] for row in k256}) == 256
    assert all(
        all(
            2.5 <= leg.price(code) <= 4.5
            for leg, code in zip(selected, row["sequence"])
        )
        for row in k256
    )
    need3, need0, _need1 = mod.quota_targets(256)
    assert sum(int(row["n3"]) for row in k256) >= need3
    assert sum(int(row["n0"]) for row in k256) >= need0

    capped = [
        row for row in combinations_one
        if row["issue"] == "26071"
        and row["arm"] == "TOPK_RATIO_PAYOUT_CAPPED"
        and row["k"] == "256"
    ]
    assert len(capped) == 256
    assert all(float(row["gross_pre_tax_payout_yuan"]) <= mod.PAYOUT_CAP for row in capped)
    diagnostic = [
        row for row in summary_one
        if row["issue"] == "26071"
        and row["arm"] == "MARKET_IMPLIED_COVERAGE_DIAGNOSTIC"
    ]
    assert diagnostic
    assert all(row["disposition"] == "DIAGNOSTIC" for row in diagnostic)
    assert all(row["diagnostic_only"] == "YES" for row in diagnostic)

    for output, combinations, summary in (
        (tmp_path / "one", combinations_one, summary_one),
        (tmp_path / "two", combinations_two, summary_two),
    ):
        mod.write_freeze(
            output,
            combinations,
            summary,
            git_head="a" * 40,
        )
    assert (tmp_path / "one" / "SHA256SUMS").read_bytes() == (tmp_path / "two" / "SHA256SUMS").read_bytes()
    assert (tmp_path / "one" / "manifest.json").read_bytes() == (tmp_path / "two" / "manifest.json").read_bytes()
    manifest = json.loads((tmp_path / "one" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["experiment"] == mod.EXPERIMENT
    assert manifest["source_sha256"] == mod.AUTHORIZED_SOURCE_SHA256
    assert manifest["safe_input_sha256"] == mod.AUTHORIZED_SAFE_INPUT_SHA256
    assert manifest["config_sha256"] == mod.AUTHORIZED_CONFIG_SHA256
    assert manifest["safe_input_schema"] == list(mod.SAFE_SCHEMA)


def test_committed_safe_artifact_digest_schema_and_r1_selector_sets() -> None:
    mod = _load_module()
    assert hashlib.sha256(CONFIG.read_bytes()).hexdigest() == mod.AUTHORIZED_CONFIG_SHA256
    assert hashlib.sha256(SAFE_INPUT.read_bytes()).hexdigest() == mod.AUTHORIZED_SAFE_INPUT_SHA256
    config = mod.read_config(CONFIG)
    legs = mod.read_safe_projection(SAFE_INPUT, config)
    expected = {
        "26071": (4, 6, 7, 8, 11, 13, 14),
        "26072": (8, 9, 14, 18, 23, 47, 67),
        "26073": (3, 4, 5, 6, 7, 8, 10),
        "26074": (1, 16, 23, 27, 53, 58, 65),
        "26075": (1, 2, 3, 6, 8, 10, 17),
        "26076": (1, 7, 16, 24, 68, 81, 82),
        "26077": (15, 26, 32, 44, 50, 55, 57),
    }
    for issue, match_indices in expected.items():
        selected = mod.select_legs(legs, issue)
        assert selected is not None
        assert tuple(leg.match_idx for leg in selected) == match_indices
