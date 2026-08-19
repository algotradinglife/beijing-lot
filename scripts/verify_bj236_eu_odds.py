#!/usr/bin/env python3
"""Fail-closed verifier for #236's external historical-proxy view."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    workbook = args.data_root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
    package = args.data_root / "derived" / "bj236" / "eu_odds_proxy_v1"
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["contract"] == "BJ-UNIFIED-EU-ODDS-TIMESERIES-001"
    assert manifest["source_sha256"] == sha256(workbook), "raw workbook hash mismatch"
    for relative, expected in manifest["parts"].items():
        assert sha256(package / relative) == expected, f"part hash mismatch: {relative}"
    probabilities = pd.concat([pd.read_parquet(p) for p in sorted((package / "probabilities").glob("*.parquet"))], ignore_index=True)
    assert set(probabilities["market_type"]) == {"euro_1x2"}, "European proxy relabelled"
    assert set(probabilities["causal_grade"]) == {"RETROSPECTIVE_RELATIVE_PROXY"}, "proxy silently pooled with strict data"
    assert probabilities["probability"].between(0.0, 1.0).all(), "probability domain violation"
    sums = probabilities.groupby(["canonical_fixture_key", "snapshot_kind"])["probability"].sum()
    assert ((sums - 1.0).abs() < 1e-12).all(), "probability triplet violation"
    translations = pd.concat([pd.read_parquet(p) for p in sorted((package / "translation_readiness").glob("*.parquet"))], ignore_index=True)
    assert not translations["translation_status"].eq("AVAILABLE_NONZERO_LINE").any(), "unidentifiable non-zero translation accepted"
    print(f"VERIFIED {package}: {len(manifest['parts'])} parts, {len(probabilities)} probability rows")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
