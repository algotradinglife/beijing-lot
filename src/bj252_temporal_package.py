"""Immutable #252 temporal evidence-package writer and semantic verifier."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from source_schema import publication
from temporal_semantics import (
    ACCEPTED_PROXY_HORIZONS,
    PROXY_GRADE,
    PROXY_SEMANTICS,
    STRICT_GRADE,
    STRICT_SEMANTICS,
    build_issue_view,
    validate_observations,
)

CONTRACT_VERSION = "BJ-UNIFIED-TEMPORAL-SEMANTICS-001"
PACKAGE_SCHEMA = "bj252_temporal_evidence_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rehash_package(package: Path) -> None:
    """Write the mechanical checksum closure (used only after a complete build)."""
    sums = {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    publication.atomic_write_json(package / "SHA256SUMS.json", sums)


def _populate(
    staging: Path,
    strict_rows: pd.DataFrame,
    proxy_coverage: pd.DataFrame,
    source_receipt: Mapping[str, str],
) -> None:
    (staging / "tables").mkdir(parents=True, exist_ok=True)
    strict = validate_observations(strict_rows, namespace="strict_forward")
    views: list[pd.DataFrame] = []
    for issue_code, group in strict.groupby("issue_code", sort=True):
        # This package's generic issue-level receipt declares its policy rather
        # than smuggling a wall-clock choice: one hour before the first kickoff.
        epoch = group["kickoff_at_utc"].min() - pd.Timedelta(hours=1)
        views.append(build_issue_view(group, issue_code=str(issue_code), decision_at_utc=epoch))
    selection = pd.concat(views, ignore_index=True)
    coverage = (
        selection.assign(available=selection["drop_reason"].eq("AVAILABLE"))
        .groupby(["issue_code", "decision_at_utc"], as_index=False)
        .agg(total_fixture_count=("fixture_id", "size"), available_fixture_count=("available", "sum"))
    )
    proxy = proxy_coverage.copy()
    required_proxy = {"snapshot_horizon", "fixture_count"}
    if not required_proxy <= set(proxy.columns):
        raise ValueError(f"proxy coverage missing columns: {sorted(required_proxy - set(proxy.columns))}")
    if (~proxy["snapshot_horizon"].isin(ACCEPTED_PROXY_HORIZONS)).any():
        raise ValueError("proxy coverage contains unaccepted horizon")
    proxy["time_semantics"] = PROXY_SEMANTICS
    proxy["causal_grade"] = PROXY_GRADE
    publication.atomic_write_csv(selection, staging / "tables" / "strict_selection.csv")
    publication.atomic_write_csv(coverage, staging / "tables" / "issue_coverage.csv")
    publication.atomic_write_csv(proxy, staging / "tables" / "proxy_horizon_coverage.csv")
    manifest = {
        "schema": PACKAGE_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "strict_namespace": "strict_forward",
        "proxy_namespace": "historical_proxy",
        "source_receipt": dict(source_receipt),
        "policy": "issue cutoff = earliest kickoff minus 60 minutes",
    }
    publication.atomic_write_json(staging / "MANIFEST.json", manifest)
    rehash_package(staging)


def write_package(
    package: Path,
    *,
    strict_rows: pd.DataFrame,
    proxy_coverage: pd.DataFrame,
    source_receipt: Mapping[str, str],
) -> Path:
    """Atomically publish a small, semantically verified evidence package."""
    return publication.atomic_publish_directory(
        package,
        lambda staging: _populate(staging, strict_rows, proxy_coverage, source_receipt),
        force=True,
    )


def _verify_hashes(package: Path) -> None:
    recorded = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if recorded != actual:
        raise AssertionError("hash closure mismatch")


def verify_package(package: Path) -> dict[str, object]:
    """Check both checksum closure and recomputed causal-selection semantics."""
    _verify_hashes(package)
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != PACKAGE_SCHEMA or manifest.get("contract_version") != CONTRACT_VERSION:
        raise AssertionError("contract identity mismatch")
    if not manifest.get("source_receipt"):
        raise AssertionError("source receipt missing")
    selection = pd.read_csv(package / "tables" / "strict_selection.csv")
    coverage = pd.read_csv(package / "tables" / "issue_coverage.csv")
    proxy = pd.read_csv(package / "tables" / "proxy_horizon_coverage.csv")
    required_selection = {
        "fixture_id", "issue_code", "kickoff_at_utc", "decision_at_utc",
        "selected_observed_at_utc", "staleness_minutes", "drop_reason",
        "snapshot_horizon", "time_semantics", "causal_grade", "source_id", "availability_mask",
    }
    if not required_selection <= set(selection.columns):
        raise AssertionError("selection ledger schema mismatch")
    if selection["fixture_id"].duplicated().any():
        raise AssertionError("selection ledger fixture identity duplicate")
    selection["kickoff_at_utc"] = pd.to_datetime(selection["kickoff_at_utc"], utc=True, errors="raise")
    selection["decision_at_utc"] = pd.to_datetime(selection["decision_at_utc"], utc=True, errors="raise")
    selection["selected_observed_at_utc"] = pd.to_datetime(selection["selected_observed_at_utc"], utc=True, errors="coerce")
    available = selection["drop_reason"].eq("AVAILABLE")
    if selection.loc[available, "selected_observed_at_utc"].isna().any():
        raise AssertionError("available selection lacks observation")
    if (~available & selection["selected_observed_at_utc"].notna()).any():
        raise AssertionError("dropped selection retains observation")
    if not selection.loc[available, "time_semantics"].eq(STRICT_SEMANTICS).all():
        raise AssertionError("available selection has non-strict time semantics")
    if not selection.loc[available, "causal_grade"].eq(STRICT_GRADE).all():
        raise AssertionError("available selection has non-strict causal grade")
    if not selection.loc[available, "availability_mask"].astype(bool).all():
        raise AssertionError("available selection has false availability mask")
    if (selection.loc[available, "selected_observed_at_utc"] > selection.loc[available, "decision_at_utc"]).any():
        raise AssertionError("future observation in strict selection")
    if (selection["decision_at_utc"] >= selection["kickoff_at_utc"]).any():
        raise AssertionError("cutoff is not pre-kickoff")
    expected_staleness = (
        (selection.loc[available, "decision_at_utc"] - selection.loc[available, "selected_observed_at_utc"])
        .dt.total_seconds() / 60.0
    )
    if not expected_staleness.round(9).equals(
        pd.to_numeric(selection.loc[available, "staleness_minutes"], errors="raise").round(9)
    ):
        raise AssertionError("staleness value disagrees with selected observation")
    if manifest.get("policy") != "issue cutoff = earliest kickoff minus 60 minutes":
        raise AssertionError("unknown strict selection policy")
    expected_epochs = selection.groupby("issue_code")["kickoff_at_utc"].transform("min") - pd.Timedelta(hours=1)
    if not selection["decision_at_utc"].equals(expected_epochs):
        raise AssertionError("strict selection cutoff disagrees with declared policy")
    computed = (
        selection.assign(available=available)
        .groupby(["issue_code", "decision_at_utc"], as_index=False)
        .agg(total_fixture_count=("fixture_id", "size"), available_fixture_count=("available", "sum"))
    )
    normalized = coverage.copy()
    normalized["decision_at_utc"] = pd.to_datetime(normalized["decision_at_utc"], utc=True, errors="raise")
    if not computed.equals(normalized[computed.columns]):
        raise AssertionError("coverage table disagrees with strict selection ledger")
    if set(proxy["snapshot_horizon"]) - set(ACCEPTED_PROXY_HORIZONS):
        raise AssertionError("proxy horizon outside frozen vocabulary")
    if not proxy["time_semantics"].eq(PROXY_SEMANTICS).all() or not proxy["causal_grade"].eq(PROXY_GRADE).all():
        raise AssertionError("proxy namespace semantics mismatch")
    return {"status": "PASS", "strict_selection_rows": len(selection), "proxy_rows": len(proxy)}
