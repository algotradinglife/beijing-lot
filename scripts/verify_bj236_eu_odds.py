#!/usr/bin/env python3
"""Fail-closed verifier for #236's external historical-proxy view."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import jsonschema
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parquet_rows(package: Path, table: str) -> int:
    return sum(
        pq.ParquetFile(path).metadata.num_rows
        for path in sorted((package / table).glob("*.parquet"))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    workbook = args.data_root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
    package = args.data_root / "derived" / "bj236" / "eu_odds_proxy_v1"
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    facts_path = package / "report_facts.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    assert manifest["contract"] == "BJ-UNIFIED-EU-ODDS-TIMESERIES-001"
    assert manifest["source_sha256"] == sha256(workbook), "raw workbook hash mismatch"
    assert manifest["report_facts_sha256"] == sha256(facts_path), "report facts hash mismatch"
    actual_parts = {
        str(path.relative_to(package)): sha256(path)
        for path in sorted(package.rglob("*.parquet"))
    }
    assert actual_parts == manifest["parts"], "Parquet inventory or hashes differ from manifest"
    for relative, expected in manifest["parts"].items():
        assert sha256(package / relative) == expected, f"part hash mismatch: {relative}"
    probabilities = pd.concat([pd.read_parquet(p) for p in sorted((package / "probabilities").glob("*.parquet"))], ignore_index=True)
    assert set(probabilities["market_type"]) == {"euro_1x2"}, "European proxy relabelled"
    assert set(probabilities["causal_grade"]) == {"RETROSPECTIVE_RELATIVE_PROXY"}, "proxy silently pooled with strict data"
    assert probabilities["probability"].between(0.0, 1.0).all(), "probability domain violation"
    assert set(probabilities["availability_mask"]) <= {"0", "1"}, "availability mask domain violation"
    assert set(probabilities["translation_availability_mask"]) <= {"0", "1"}, "translation mask domain violation"
    sums = probabilities.groupby(["canonical_fixture_key", "snapshot_kind"])["probability"].sum()
    assert ((sums - 1.0).abs() < 1e-12).all(), "probability triplet violation"
    triplet_sizes = probabilities.groupby(["canonical_fixture_key", "snapshot_kind"])["outcome_code"].nunique()
    assert triplet_sizes.eq(3).all(), "outcome triplet cardinality violation"
    translations = pd.concat([pd.read_parquet(p) for p in sorted((package / "translation_readiness").glob("*.parquet"))], ignore_index=True)
    assert not translations["translation_status"].eq("AVAILABLE_NONZERO_LINE").any(), "unidentifiable non-zero translation accepted"
    available = translations.translation_status.eq("AVAILABLE_ZERO_LINE_IDENTITY")
    assert translations.loc[available, "native_handicap_line"].eq(0.0).all(), "zero-line identity has non-zero normalized line"
    assert translations.loc[available, "availability_mask"].eq("1").all(), "available translation is masked"
    unavailable = ~available
    assert translations.loc[unavailable, "availability_mask"].eq("0").all(), "unavailable translation is exposed"
    assert facts["probability_rows"] == len(probabilities), "probability row count receipt mismatch"
    assert facts["translation_rows"] == len(translations), "translation row count receipt mismatch"
    assert facts["trace_rows"] == parquet_rows(package, "source_trace"), "source-trace row count receipt mismatch"
    assert facts["exclusion_rows"] == parquet_rows(package, "exclusion_ledger"), "exclusion-ledger row count receipt mismatch"
    assert facts["matched_fixture_count"] == probabilities.canonical_fixture_key.nunique(), "fixture receipt mismatch"
    assert facts["strict_forward_rows"] == 0, "strict-forward namespace contamination"

    schema = json.loads(
        (ROOT / "schemas" / "bj236_eu_odds_proxy_handoff_v1.schema.json").read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft202012Validator(schema)
    probability_sample = probabilities.groupby(
        ["snapshot_kind", "outcome_code", "translation_status"], sort=False
    ).head(1)
    translation_sample = translations.groupby(
        ["snapshot_kind", "translation_status"], sort=False
    ).head(1)
    for record in json.loads(probability_sample.to_json(orient="records")):
        validator.validate(record)
    for record in json.loads(translation_sample.to_json(orient="records")):
        validator.validate(record)
    print(f"VERIFIED {package}: {len(manifest['parts'])} parts, {len(probabilities)} probability rows")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
