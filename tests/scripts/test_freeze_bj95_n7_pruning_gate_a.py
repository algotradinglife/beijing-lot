from __future__ import annotations

import importlib.util
import itertools
import hashlib
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj95_n7_pruning_gate_a.py"
EURO_INPUT_SCRIPT = ROOT / "scripts" / "freeze_bj95_euro_safe_input.py"


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load():
    return load_script("bj95_pruning", SCRIPT)


def load_euro_input():
    return load_script("bj95_euro_input", EURO_INPUT_SCRIPT)


def assert_raises_runtime_error(callback):
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def card_without_runtime(card: dict[str, object]) -> dict[str, object]:
    copied = json.loads(json.dumps(card))
    compression = copied["compression_contract"]
    assert isinstance(compression, dict)
    compression.pop("runtime")
    return copied


def assert_replay_equivalence(mod, replay: Path, committed: Path, *, force_runtime_mismatch: bool) -> None:
    replay_card = json.loads((replay / "preoutcome_card.json").read_text())
    committed_card = json.loads((committed / "preoutcome_card.json").read_text())
    replay_runtime = replay_card["compression_contract"]["runtime"]
    committed_runtime = committed_card["compression_contract"]["runtime"]
    same_runtime = replay_runtime == committed_runtime and not force_runtime_mismatch
    if same_runtime:
        assert (replay / "SHA256SUMS.json").read_bytes() == (committed / "SHA256SUMS.json").read_bytes()
        return

    # Gzip byte streams vary between zlib implementations even at fixed mtime.
    # Across runtimes, verify the stable card/non-gzip data and decompressed
    # payloads rather than pretending compressor-specific bytes are portable.
    assert card_without_runtime(replay_card) == card_without_runtime(committed_card)
    for name in ("availability_census.csv", "freeze_runner.py"):
        assert (replay / name).read_bytes() == (committed / name).read_bytes()
    expected = committed_card["compression_contract"]["canonical_decompressed_sha256"]
    assert replay_card["compression_contract"]["canonical_decompressed_sha256"] == expected
    for name, digest in expected.items():
        assert mod.canonical_content_sha256(replay / name) == digest
        assert mod.canonical_content_sha256(committed / name) == digest


def leg(position: int, calibrated: tuple[float, float, float], euro: tuple[float, float, float]):
    return {
        "group_id": "PRIMARY-N7-test", "position": position,
        "calibrated_probability": dict(zip(("3", "1", "0"), calibrated)),
        "euro_probability": dict(zip(("3", "1", "0"), euro)),
        "predicted_sp": {"3": 2.0, "1": 3.0, "0": 4.0},
        "sp5": {"3": 2.0, "1": 3.0, "0": 4.0},
        "handicap_line_norm": "0.0",
    }


def test_analytic_allowed_sets_enumerate_to_the_declared_k():
    mod = load()
    legs = [leg(position, (0.60, 0.30, 0.10), (0.55, 0.35, 0.10)) for position in range(1, 8)]
    order, unavailable = mod.deletion_order(legs, "CAL_MIN_P")
    assert unavailable is None
    for depth in range(8):
        deleted = {item["leg"]["position"]: item["code"] for item in order[:depth]}
        allowed = [tuple(code for code in mod.CODES if code != deleted.get(position)) for position in range(1, 8)]
        sequences = list(itertools.product(*allowed))
        assert len(sequences) == 2**depth * 3**(7 - depth)
        assert len(set(sequences)) == len(sequences)
        identities = [(f"m{position}", "i", str(position), "fold") for position in range(1, 8)]
        assert mod.descriptor("PRIMARY-N7-test", "CAL_MIN_P", depth, allowed, identities) == mod.descriptor(
            "PRIMARY-N7-test", "CAL_MIN_P", depth, allowed, identities
        )


def test_model_market_agree_is_unavailable_only_after_eligible_removals():
    mod = load()
    legs = [leg(position, (0.5, 0.3, 0.2), (0.5, 0.2, 0.3)) for position in range(1, 8)]
    for position in (1, 2, 3):
        legs[position - 1]["euro_probability"] = {"3": 0.5, "1": 0.3, "0": 0.2}
    order, unavailable = mod.deletion_order(legs, "MODEL_MARKET_AGREE")
    assert unavailable == "UNAVAILABLE_BY_RULE"
    assert len(order) == 3
    assert all(item["code"] == "0" for item in order)


def selected_pairs(order):
    return [(item["leg"]["position"], item["code"]) for item in order]


def test_all_deterministic_pruning_arms_have_independent_orders_and_tie_breaks():
    mod = load()
    calibrated = (
        (0.10, 0.60, 0.30),  # position tie at 0.10 is resolved before p2
        (0.60, 0.10, 0.30),
        (0.50, 0.30, 0.20),
        (0.20, 0.40, 0.40),
        (0.40, 0.30, 0.30),  # equal code score resolves to code 1, not 0
        (0.40, 0.30, 0.30),
        (0.40, 0.40, 0.20),
    )
    euro = (
        (0.50, 0.30, 0.20),
        (0.10, 0.50, 0.40),
        (0.40, 0.40, 0.20),
        (0.40, 0.10, 0.50),
        (0.30, 0.30, 0.40),  # equal code score resolves to code 3
        (0.50, 0.25, 0.25),
        (0.50, 0.30, 0.20),
    )
    rule_legs = [leg(position, calibrated[position - 1], euro[position - 1]) for position in range(1, 8)]

    cal_order, cal_unavailable = mod.deletion_order(rule_legs, "CAL_MIN_P")
    assert cal_unavailable is None
    assert selected_pairs(cal_order) == [(1, "3"), (2, "1"), (3, "0"), (4, "3"), (7, "0"), (5, "1"), (6, "1")]

    euro_order, euro_unavailable = mod.deletion_order(rule_legs, "EURO_MIN_P")
    assert euro_unavailable is None
    assert selected_pairs(euro_order) == [(2, "3"), (4, "1"), (1, "0"), (3, "0"), (7, "0"), (6, "1"), (5, "3")]

    pxsp5_legs = [leg(position, (1 / 3, 1 / 3, 1 / 3), euro[position - 1]) for position in range(1, 8)]
    for position, sp5 in enumerate(((3, 6, 9), (6, 3, 9), (9, 6, 3), (3, 6, 9), (6, 3, 9), (9, 6, 3), (3, 3, 9)), start=1):
        pxsp5_legs[position - 1]["sp5"] = dict(zip(("3", "1", "0"), sp5))
    pxsp5_order, pxsp5_unavailable = mod.deletion_order(pxsp5_legs, "MIN_PXSP5")
    assert pxsp5_unavailable is None
    assert selected_pairs(pxsp5_order) == [(1, "3"), (2, "1"), (3, "0"), (4, "3"), (5, "1"), (6, "0"), (7, "3")]

    agree_legs = [leg(position, (0.50, 0.30, 0.20), (0.50, 0.20, 0.30)) for position in range(1, 8)]
    for position in (1, 2, 3):
        agree_legs[position - 1]["euro_probability"] = {"3": 0.50, "1": 0.30, "0": 0.20}
    agree_order, unavailable = mod.deletion_order(agree_legs, "MODEL_MARKET_AGREE")
    assert unavailable == "UNAVAILABLE_BY_RULE"
    assert selected_pairs(agree_order) == [(1, "0"), (2, "0"), (3, "0")]


def test_model_market_depth_boundary_uses_shared_k_and_stake_contract():
    mod = load()
    for depth in range(1, 8):
        disposition, formula_k, selected_count, stake_yuan = mod.depth_contract(depth, 3, "UNAVAILABLE_BY_RULE")
        assert formula_k == 2**depth * 3**(7 - depth)
        if depth <= 3:
            assert (disposition, selected_count, stake_yuan) == ("AVAILABLE", formula_k, 2 * formula_k)
        else:
            assert (disposition, selected_count, stake_yuan) == ("UNAVAILABLE_BY_RULE", 0, 0)


def test_nonfinite_and_invalid_numeric_ingress_is_fail_closed_before_ranking():
    mod = load()
    valid_euro = {"match_id": "m", "euro_3_10h": "2.0", "euro_1_10h": "3.0", "euro_0_10h": "4.0"}
    for bad in ("nan", "inf", "-inf", "1.0", "0", "-1"):
        row = dict(valid_euro)
        row["euro_1_10h"] = bad
        assert_raises_runtime_error(lambda row=row: mod.no_vig_probabilities(row))
    for bad in ("nan", "inf", "-inf", "0", "-1"):
        assert_raises_runtime_error(lambda bad=bad: mod.finite_positive(bad, "test"))
    assert_raises_runtime_error(lambda: mod.valid_probability_vector({"3": float("nan"), "1": 0.5, "0": 0.5}, "test"))
    bad_sp5 = [leg(position, (0.5, 0.3, 0.2), (0.5, 0.3, 0.2)) for position in range(1, 8)]
    bad_sp5[0]["sp5"]["3"] = float("inf")
    assert_raises_runtime_error(lambda: mod.deletion_order(bad_sp5, "MIN_PXSP5"))
    bad_predicted_sp = [leg(position, (0.5, 0.3, 0.2), (0.5, 0.3, 0.2)) for position in range(1, 8)]
    bad_predicted_sp[0]["predicted_sp"]["1"] = 0.0
    assert_raises_runtime_error(lambda: mod.deletion_order(bad_predicted_sp, "CAL_MIN_P"))


def test_random_baseline_is_deterministic_and_outcome_free():
    mod = load()
    legs = [leg(position, (0.5, 0.3, 0.2), (0.4, 0.35, 0.25)) for position in range(1, 8)]
    first, unavailable_first = mod.deletion_order(legs, "RANDOM_HASH_BASELINE")
    second, unavailable_second = mod.deletion_order(legs, "RANDOM_HASH_BASELINE")
    assert unavailable_first is unavailable_second is None
    assert [(item["leg"]["position"], item["code"]) for item in first] == [
        (item["leg"]["position"], item["code"]) for item in second
    ]
    assert "outcome" not in " ".join(mod.LEG_FIELDS + mod.FRONTIER_FIELDS + mod.DELETION_FIELDS).lower()


def test_descriptor_independently_binds_all_identities_and_safe_sources():
    mod = load()
    allowed = [("3", "1"), ("3", "0"), ("1", "0"), mod.CODES, mod.CODES, mod.CODES, mod.CODES]
    identities = [(f"m{position}", "i", str(position), "fold") for position in range(1, 8)]
    payload = {
        "contract": mod.CONTRACT_ID,
        "generator_version": mod.GENERATOR_VERSION,
        "group_id": "PRIMARY-N7-test",
        "arm": "CAL_MIN_P",
        "depth": 3,
        "code_order": mod.CODES,
        "allowed_codes_by_position": allowed,
        "ordered_match_identities": identities,
        "safe_source_payload_sha256": {
            "bj91_outcome_safe_legs.csv.gz": mod.P91_LEGS_SHA,
            "bj95_euro_10h_safe_projection.csv.gz": mod.EURO_INPUT_SHA,
        },
    }
    independent = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert mod.descriptor("PRIMARY-N7-test", "CAL_MIN_P", 3, allowed, identities) == independent
    changed = [*identities]
    changed[0] = ("other-match", "i", "1", "fold")
    assert mod.descriptor("PRIMARY-N7-test", "CAL_MIN_P", 3, allowed, changed) != independent


def test_exact_safe_schemas_reject_extra_columns_in_both_producer_and_consumer():
    mod = load()
    producer = load_euro_input()
    assert_raises_runtime_error(lambda: mod.assert_exact_schema(
        (*mod.EURO_INPUT_FIELDS, "gross"), mod.EURO_INPUT_FIELDS, "consumer EURO"
    ))
    assert_raises_runtime_error(lambda: mod.assert_exact_schema(
        (*mod.P91_SOURCE_FIELDS, "brier"), mod.P91_SOURCE_FIELDS, "consumer #91"
    ))
    assert_raises_runtime_error(lambda: producer.assert_exact_schema(
        [*producer.P89_SOURCE_FIELDS, "net"], producer.P89_SOURCE_FIELDS, "producer #89"
    ))
    assert_raises_runtime_error(lambda: producer.assert_exact_schema(
        [*producer.P91_SOURCE_FIELDS, "gross"], producer.P91_SOURCE_FIELDS, "producer #91"
    ))


def test_manifest_pin_fails_before_attempting_to_parse_untrusted_json():
    mod = load()
    with tempfile.TemporaryDirectory(prefix="bj95_manifest_pin_") as directory:
        bundle = Path(directory)
        (bundle / "SHA256SUMS.json").write_text("not-json\n")
        assert_raises_runtime_error(lambda: mod.manifest_sha(bundle, "0" * 64))


def test_safe_inputs_and_committed_bundle_replay_end_to_end():
    mod = load()
    sources = (
        (mod.P91 / "outcome_safe_legs.csv.gz", mod.P91_SOURCE_FIELDS),
        (mod.EURO_INPUT / "euro_10h_safe_projection.csv.gz", mod.EURO_INPUT_FIELDS),
    )
    for source, expected in sources:
        opener = __import__("gzip").open if source.suffix == ".gz" else open
        with opener(source, "rt", newline="") as handle:
            fieldnames = next(__import__("csv").reader(handle))
        mod.assert_exact_schema(fieldnames, expected, str(source))
    committed = mod.ROOT / "results" / "bj95_gate_a_preoutcome_v5"
    with tempfile.TemporaryDirectory(prefix="bj95_test_replay_") as directory:
        replay = Path(directory) / "bundle"
        mod.build(replay)
        # This machine follows the recorded runtime path and therefore must
        # preserve exact bytes; force the portable path too, to test the
        # zlib-mismatch assertion that a reviewer exercises on CPython 3.14.4.
        assert_replay_equivalence(mod, replay, committed, force_runtime_mismatch=False)
        assert_replay_equivalence(mod, replay, committed, force_runtime_mismatch=True)
