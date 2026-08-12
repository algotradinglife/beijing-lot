"""Durability checks for #154's independent EV package."""
from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results/bj154_independent_ev_v1"
MANIFEST = "f81146959fd734c3d15a2579a3921b2afc86d6f633e174c8294763279f9937c5"


def test_manifest_is_immutable_and_complete() -> None:
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {name: hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() for name in manifest}
    assert manifest == actual
    assert hashlib.sha256((PACKAGE / "SHA256SUMS.json").read_bytes()).hexdigest() == MANIFEST
    card = json.loads((PACKAGE / "validation_card.json").read_text(encoding="utf-8"))
    assert card["target_head"] == "e7cb6ece9bbc4f2722d7eccc33419a6debc72aee"
    assert card["gate_a_manifest"] == "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"
    assert card["gate_b_manifest"] == "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2"
    assert card["outcome_payload"] == "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
    assert card["sampler_namespace_verified"] is True
    assert card["package_surface_mismatches"] == 0
    assert Decimal(card["independent_full_no_tax_roi"]).quantize(Decimal("0.000000000001")) == Decimal("-0.157696718701")


def test_independent_m64_and_nearby_cluster_values() -> None:
    card = json.loads((PACKAGE / "validation_card.json").read_text(encoding="utf-8"))
    assert {key: Decimal(value).quantize(Decimal("0.000000000001")) for key, value in card["m64_no_tax_roi_by_seed"].items()} == {
        "137001": Decimal("0.163755668115"), "137002": Decimal("0.117735771069"), "137003": Decimal("0.026680342104")
    }
    nearby = {key: Decimal(value).quantize(Decimal("0.000000000001")) for key, value in card["nearby_mean_no_tax_roi"].items()}
    assert nearby == {"48": Decimal("0.053029857212"), "64": Decimal("0.102723927096"), "80": Decimal("0.042926037147"), "128": Decimal("0.008607767181")}


def test_curve_support_and_bootstrap_are_complete() -> None:
    with (PACKAGE / "wor_dense_curve.csv").open(newline="", encoding="utf-8") as handle:
        curve = list(csv.DictReader(handle))
    assert len(curve) == 171
    assert {row["seed"] for row in curve} == {"137001", "137002", "137003"}
    assert len({int(row["M"]) for row in curve}) == 57
    with (PACKAGE / "m64_issue_metrics.csv").open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 762
    with (PACKAGE / "m64_scope_metrics.csv").open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 63
    with (PACKAGE / "m64_bootstrap.csv").open(newline="", encoding="utf-8") as handle:
        bootstrap = list(csv.DictReader(handle))
    assert len(bootstrap) == 3
    assert {row["replicates"] for row in bootstrap} == {"1000"}
