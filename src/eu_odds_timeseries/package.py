"""Atomic package writer and semantic verifier for #236 evidence bundles."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from source_schema import publication

from .core import CAUSAL_GRADE, MARKET_TYPE, SOURCE_ROLE, derive_proxy_probabilities, translation_readiness

CONTRACT = "BJ-UNIFIED-EU-ODDS-TIMESERIES-001"
_TABLES = ("raw_quotes", "probabilities", "translation_readiness", "exclusion_ledger")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(root: Path, *, source_sha256: str) -> None:
    files = {str(p.relative_to(root)): _sha256(p) for p in sorted(root.rglob("*")) if p.is_file() and p.name not in {"MANIFEST.json", "MANIFEST.sha256"}}
    manifest = {
        "contract": CONTRACT,
        "source_role": SOURCE_ROLE,
        "market_type": MARKET_TYPE,
        "causal_grade": CAUSAL_GRADE,
        "source_sha256": source_sha256,
        "files": files,
    }
    publication.atomic_write_json(root / "MANIFEST.json", manifest)
    publication.atomic_write_text(root / "MANIFEST.sha256", _sha256(root / "MANIFEST.json") + "\n")


def rebuild_manifest(package: Path) -> None:
    """Test helper mirroring an attacker who remanifests altered package bytes."""
    existing = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    _write_manifest(package, source_sha256=str(existing["source_sha256"]))


def build_proxy_package(target: Path, raw_rows: pd.DataFrame, *, source_sha256: str) -> Path:
    """Atomically publish a compact, source-hash-bound proxy evidence package."""
    probabilities, raw_quotes, ledger = derive_proxy_probabilities(raw_rows)
    readiness = translation_readiness(probabilities, raw_rows)

    def populate(staging: Path) -> None:
        tables = staging / "tables"
        tables.mkdir()
        raw_quotes.to_parquet(tables / "raw_quotes.parquet", index=False)
        probabilities.to_parquet(tables / "probabilities.parquet", index=False)
        readiness.to_parquet(tables / "translation_readiness.parquet", index=False)
        ledger.to_parquet(tables / "exclusion_ledger.parquet", index=False)
        facts = {
            "raw_quote_rows": int(len(raw_quotes)),
            "probability_rows": int(len(probabilities)),
            "matched_fixture_count": int(probabilities["canonical_fixture_key"].nunique()) if not probabilities.empty else 0,
            "horizons": sorted(probabilities["snapshot_kind"].unique().tolist()) if not probabilities.empty else [],
            "strict_forward_rows": 0,
            "proxy_rows": int(len(probabilities)),
            "translation_status_counts": readiness["translation_status"].value_counts().sort_index().to_dict(),
        }
        publication.atomic_write_json(staging / "report_facts.json", facts)
        _write_manifest(staging, source_sha256=source_sha256)

    return publication.atomic_publish_directory(target, populate, force=True)


def _verify_closure(package: Path, manifest: dict) -> None:
    assert _sha256(package / "MANIFEST.json") == (package / "MANIFEST.sha256").read_text().strip(), "manifest checksum mismatch"
    actual = {str(p.relative_to(package)): _sha256(p) for p in sorted(package.rglob("*")) if p.is_file() and p.name not in {"MANIFEST.json", "MANIFEST.sha256"}}
    assert actual == manifest["files"], "package file inventory or hashes differ from manifest"


def _wide_raw(raw_quotes: pd.DataFrame) -> pd.DataFrame:
    expected = {"canonical_fixture_key", "issue_code", "match_idx", "source_match_id", "snapshot_kind", "bookmaker_id", "outcome_code", "decimal_odds", "native_handicap_line", "market_type", "causal_grade", "source_role", "quote_status"}
    assert expected <= set(raw_quotes.columns), "semantic raw quote schema mismatch"
    assert set(raw_quotes.market_type) == {MARKET_TYPE}, "semantic market label mismatch"
    assert set(raw_quotes.causal_grade) == {CAUSAL_GRADE}, "semantic causal grade mismatch"
    assert set(raw_quotes.source_role) == {SOURCE_ROLE}, "semantic source role mismatch"
    pivot = raw_quotes.pivot(index=["issue_code", "match_idx", "source_match_id", "snapshot_kind", "bookmaker_id", "native_handicap_line"], columns="outcome_code", values="decimal_odds").reset_index()
    assert set(("3", "1", "0")) <= set(pivot.columns), "semantic raw quote outcome triplet missing"
    return pivot.rename(columns={"3": "v1", "1": "v2", "0": "v3"})


def verify_proxy_package(package: Path, *, expected_source_sha256: str) -> None:
    """Fail closed on cryptographic or semantic package tampering."""
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest.get("contract") == CONTRACT, "manifest contract mismatch"
    assert manifest.get("source_sha256") == expected_source_sha256, "source hash does not match trusted input receipt"
    _verify_closure(package, manifest)
    raw = pd.read_parquet(package / "tables" / "raw_quotes.parquet")
    actual_probabilities = pd.read_parquet(package / "tables" / "probabilities.parquet")
    expected_probabilities, _, expected_ledger = derive_proxy_probabilities(_wide_raw(raw))
    order = ["canonical_fixture_key", "snapshot_kind", "outcome_code"]
    try:
        assert_frame_equal(
            actual_probabilities.sort_values(order).reset_index(drop=True),
            expected_probabilities.sort_values(order).reset_index(drop=True),
            check_like=False,
        )
    except AssertionError as exc:
        raise AssertionError(f"probabilities semantic recomputation failed: {exc}") from exc
    actual_ledger = pd.read_parquet(package / "tables" / "exclusion_ledger.parquet")
    try:
        assert_frame_equal(
            actual_ledger.sort_values(["canonical_fixture_key", "snapshot_kind", "bookmaker_id"]).reset_index(drop=True),
            expected_ledger.sort_values(["canonical_fixture_key", "snapshot_kind", "bookmaker_id"]).reset_index(drop=True),
            check_like=False,
        )
    except AssertionError as exc:
        raise AssertionError(f"ledger semantic recomputation failed: {exc}") from exc
    readiness = pd.read_parquet(package / "tables" / "translation_readiness.parquet")
    expected_readiness = translation_readiness(expected_probabilities, _wide_raw(raw))
    try:
        assert_frame_equal(
            readiness.sort_values(["canonical_fixture_key", "snapshot_kind"]).reset_index(drop=True),
            expected_readiness.sort_values(["canonical_fixture_key", "snapshot_kind"]).reset_index(drop=True),
            check_like=False,
        )
    except AssertionError as exc:
        raise AssertionError(f"translation semantic recomputation failed: {exc}") from exc
