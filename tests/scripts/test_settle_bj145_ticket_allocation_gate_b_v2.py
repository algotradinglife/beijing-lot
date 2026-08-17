"""Focused integrity and semantics checks for the #145 Gate-B v2 package."""

from __future__ import annotations

import csv
import ctypes
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj145_gate_b_outcome_settlement_v2"
V1 = ROOT / "results" / "bj145_gate_b_outcome_settlement_v1"
GATE_A = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
EXPECTED_ATLAS_ROWS = 2_892 * 2_187
TOLERANCE = Decimal("0.00000001")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def _engine():
    path = GATE_A / "bj145_allocation_engine.py"
    spec = importlib.util.spec_from_file_location("bj145_v2_test_engine", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _atlas_paths() -> list[Path]:
    paths = sorted(PACKAGE.glob("outcome_code_frequency*.csv.gz"))
    assert paths
    return paths


def test_v2_manifest_is_complete_and_v1_is_unchanged():
    assert (
        _sha256(V1 / "SHA256SUMS.json")
        == "ec330f834fee3a47b8af70738a3ca0b532a35c75b383a580a0de236af80fc1d0"
    )
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name: _sha256(path)
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert declared == actual
    assert not list(PACKAGE.glob("*.sqlite"))
    assert not list(PACKAGE.glob("*.db"))
    assert not (PACKAGE / "mechanism_surface_median.svg").exists()


def test_corrected_support_complete_surface_and_high_m_controls():
    card = json.loads((PACKAGE / "settlement_card.json").read_text(encoding="utf-8"))
    assert card["surface"] == {
        "issue_rows": 1_006_416,
        "configuration_count": 2_892,
        "summary_rows": 63_624,
        "full_control_delta_rows": 63_360,
        "mechanism_pairwise_rows": 12_960,
        "bootstrap_rows": 5_760,
        "holm_rows": 2_880,
        "tax_reconciliation_rows": 2_892,
        "leave_one_issue_out_rows": 2_892,
        "largest_issue_exclusion_rows": 2_892,
        "outcome_code_rows": EXPECTED_ATLAS_ROWS,
        "codes_per_configuration": 2_187,
    }
    assert card["decision"] == "DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION"
    assert card["promotion_authorized"] is False
    assert card["charts"] == [
        "roi_vs_m_cap.svg",
        "matched_pre_tax_comparison.svg",
        "uncertainty_stability.svg",
    ]
    index = json.loads(
        (PACKAGE / "outcome_code_frequency.index.json").read_text(encoding="utf-8")
    )
    assert index["total_rows"] == EXPECTED_ATLAS_ROWS
    assert index["configuration_count"] == 2_892
    assert index["codes_per_configuration"] == 2_187
    assert index["part_count"] == 8
    assert card["outcome_code_files"] == [part["file"] for part in index["parts"]]
    assert all(part["bytes"] < 95_000_000 for part in index["parts"])

    all_rows = [
        row
        for row in _rows(PACKAGE / "mechanism_weight_surface_summary.csv")
        if row["scope"] == "ALL"
    ]
    assert len(all_rows) == 2_892
    full = [row for row in all_rows if row["mechanism"] == "FULL_ENUMERATED"]
    assert len(full) == 12
    assert {row["coverage_hit_rate"] for row in full} == {"1.000000000000"}
    assert {
        (row["arm_id"], int(row["coverage_denominator_issue_count"])) for row in full
    } == {
        ("PRIMARY_NO_GATE_K4", 254),
        ("SECONDARY_ESP300_GM290_K8", 191),
    }
    qwor = next(
        row
        for row in all_rows
        if row["arm_id"] == "PRIMARY_NO_GATE_K4"
        and row["weight_source"] == "Q_WEIGHT"
        and row["mechanism"] == "WOR_DISTINCT"
        and row["M"] == "16"
        and row["seed"] == "137002"
    )
    assert qwor["coverage_hits"] == "13"
    assert qwor["coverage_denominator_issue_count"] == "254"
    assert qwor["coverage_hit_rate"] == "0.051181102362"

    pairwise = list(_rows(PACKAGE / "mechanism_pairwise_deltas.csv"))
    assert len(pairwise) == 12_960
    assert {int(row["M"]) for row in pairwise} == set(range(16, 257, 16)) | {
        512,
        1024,
        1458,
        2187,
    }
    loio = list(_rows(PACKAGE / "leave_one_issue_out_summary.csv"))
    assert len(loio) == 2_892
    assert all(
        row["leave_one_roi_min_issue_instance"]
        and row["leave_one_roi_max_issue_instance"]
        for row in loio
    )
    assert len(list(_rows(PACKAGE / "largest_issue_exclusion.csv"))) == 2_892

    report = (PACKAGE / "report.md").read_text(encoding="utf-8")
    for phrase in (
        "Correct support denominator",
        "Weighting surface",
        "Concentration and path risk",
        "Seed dispersion",
        "YEAR / FOLD / LOYO",
        "DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION",
    ):
        assert phrase in report
    for chart in card["charts"]:
        payload = (PACKAGE / chart).read_text(encoding="utf-8")
        assert payload.startswith("<svg")
        assert "pre-tax" in payload


def test_complete_outcome_code_atlas_mass_and_support_semantics():
    fields = {
        "ticket_code",
        "settled_issue_count",
        "identity_count",
        "draw_count",
        "target_mass_mean",
        "allocated_draw_count",
        "realized_frequency",
        "frequency_delta",
        "actual_outcome_identity_count",
        "actual_outcome_hit_ticket_count",
        "actual_hit_frequency",
    }
    expected_support = {
        "PRIMARY_NO_GATE_K4": (254, 1_016),
        "SECONDARY_ESP300_GM290_K8": (191, 1_528),
    }
    current = None
    codes: set[str] = set()
    target = realized = delta = Decimal(0)
    allocated = actual_identities = 0
    row_count = config_count = 0

    def audit() -> None:
        nonlocal config_count
        if current is None:
            return
        config_count += 1
        assert len(codes) == 2_187
        assert abs(target - 1) <= TOLERANCE
        assert abs(realized - 1) <= TOLERANCE
        assert abs(delta) <= TOLERANCE
        assert allocated == current[2]
        assert actual_identities == current[1]

    for path in _atlas_paths():
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            assert fields <= set(reader.fieldnames or ())
            for row in reader:
                key = tuple(
                    row[name]
                    for name in (
                        "arm_id",
                        "weight_source",
                        "mechanism",
                        "sampling_role",
                        "cap",
                        "M",
                        "seed",
                    )
                )
                support = expected_support[row["arm_id"]]
                assert (
                    int(row["settled_issue_count"]),
                    int(row["identity_count"]),
                ) == support
                if current is None or key != current[0]:
                    audit()
                    current = (key, int(row["identity_count"]), int(row["draw_count"]))
                    codes = set()
                    target = realized = delta = Decimal(0)
                    allocated = actual_identities = 0
                assert row["frequency_delta"] != ""
                assert row["actual_outcome_identity_count"] != ""
                assert row["actual_outcome_hit_ticket_count"] != ""
                codes.add(row["ticket_code"])
                target += Decimal(row["target_mass_mean"])
                realized += Decimal(row["realized_frequency"])
                delta += Decimal(row["frequency_delta"])
                allocated += int(row["allocated_draw_count"])
                actual_identities += int(row["actual_outcome_identity_count"])
                row_count += 1
    audit()
    assert row_count == EXPECTED_ATLAS_ROWS
    assert config_count == 2_892


def test_complete_marginal_accelerator_matches_frozen_allocator():
    engine = _engine()
    scratch = ROOT / ".scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".bj145-v2-parity-", dir=scratch
    ) as directory:
        library_path = Path(directory) / "bj145_fast_alloc.so"
        subprocess.run(
            (
                "g++",
                "-O3",
                "-std=c++17",
                "-shared",
                "-fPIC",
                str(ROOT / "scripts" / "bj145_fast_alloc.cpp"),
                "-o",
                str(library_path),
            ),
            check=True,
        )
        library = ctypes.CDLL(str(library_path))
        aggregate = library.bj145_code_aggregate_grid
        aggregate.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_longlong),
            ctypes.POINTER(ctypes.c_longlong),
            ctypes.POINTER(ctypes.c_longlong),
        ]
        weights = engine.golden_weights(2_187)
        flat = (ctypes.c_double * 2_187)(*weights)
        truths = (ctypes.c_int * 1)(137)
        signatures = (ctypes.c_char_p * 1)(b"bj145-v2-parity")
        cases = (
            ("WR_DUPLICATE_STAKE", 0, "137001", (16, 64, 256)),
            ("WOR_DISTINCT", 1, "137002", (16, 64, 256)),
            ("RESIDUAL_SYSTEMATIC", 2, "NA", (16, 64, 256)),
            ("CAPPED_REPEAT", 3, "NA", (16, 64, 256)),
            ("DETERMINISTIC_TOP_MASS", 4, "NA", (16, 64, 256)),
            ("FULL_ENUMERATED", 5, "NA", (2_187,)),
        )
        for mechanism, code, seed, ms in cases:
            m_values = (ctypes.c_int * len(ms))(*ms)
            allocated = (ctypes.c_longlong * (len(ms) * 2_187))()
            actual_identity = (ctypes.c_longlong * (len(ms) * 2_187))()
            actual_hit = (ctypes.c_longlong * (len(ms) * 2_187))()
            cap = 2 if mechanism == "CAPPED_REPEAT" else 0
            aggregate(
                flat,
                1,
                2_187,
                truths,
                signatures,
                code,
                cap,
                seed.encode(),
                m_values,
                len(ms),
                allocated,
                actual_identity,
                actual_hit,
            )
            for index, m in enumerate(ms):
                expected = engine.allocate(
                    mechanism,
                    weights,
                    m,
                    seed=seed,
                    identity_signature="bj145-v2-parity",
                    cap=cap or None,
                )
                assert list(allocated[index * 2_187 : (index + 1) * 2_187]) == list(
                    expected
                )
                assert sum(actual_identity[index * 2_187 : (index + 1) * 2_187]) == 1
                assert actual_identity[index * 2_187 + 137] == 1
                assert actual_hit[index * 2_187 + 137] == expected[137]
