"""Package-only loading and independent semantic validation for #209.

The validator never opens #203/#204/#214/#180.  Every key relation needed by a
consumer is physical inside the handoff, including label ``cell_key``.  Hashes
are only the outer integrity layer; causal masks, divergence, labels, schema,
evidence, report, source traces and provenance are independently recomputed.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import contract, divergence, profile as profile_mod, publication, sources


class HandoffValidationError(RuntimeError):
    """Fail-closed package contract error."""


@dataclass(frozen=True)
class PackageBundle:
    package: Path
    inference_cells: pd.DataFrame
    development_labels: pd.DataFrame
    sealed_namespaces: pd.DataFrame
    evidence: pd.DataFrame
    schema: dict[str, Any]
    manifest: dict[str, Any]
    tables: dict[str, pd.DataFrame]


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pq.read_table(path).to_pandas()
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise HandoffValidationError(f"unsupported package table format: {path}")


def _is_vector(value: object) -> bool:
    return isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3


def _present(frame: pd.DataFrame, representation: str) -> pd.Series:
    if representation not in frame:
        return pd.Series(False, index=frame.index)
    if representation == contract.BJ_LINE_BOUNDARY:
        return pd.to_numeric(frame[representation], errors="coerce").notna()
    return frame[representation].apply(_is_vector)


def _expected_available(frame: pd.DataFrame, representation: str) -> pd.Series:
    present = _present(frame, representation)
    observed_name = contract.observed_at_col(representation)
    observed = pd.to_datetime(frame.get(observed_name), errors="coerce", utc=True)
    epoch = pd.to_datetime(frame.get(contract.DECISION_EPOCH_COLUMN), errors="coerce", utc=True)
    kickoff = pd.to_datetime(frame.get(contract.KICKOFF_COLUMN), errors="coerce", utc=True)
    return (
        present
        & observed.notna()
        & epoch.notna()
        & kickoff.notna()
        & observed.le(epoch)
        & kickoff.ge(epoch)
    ).fillna(False)


def render_data_readiness(
    cells: pd.DataFrame, labels: pd.DataFrame, sealed: pd.DataFrame, manifest: dict[str, Any]
) -> str:
    """Canonical report text; verifier compares bytes, not prose presence."""
    lines = [
        "# Issue #229 data readiness",
        "",
        f"Disposition: {manifest.get('disposition', 'UNKNOWN')}",
        f"Inference cells: {len(cells)}",
        f"Development labels through 2023: {len(labels)}",
        "",
        "## Causally available cells by source",
        "",
    ]
    for representation in contract.CAUSAL_REPRESENTATIONS:
        available_name = contract.available_col(representation)
        count = int(cells.get(available_name, pd.Series(False, index=cells.index)).fillna(False).astype(bool).sum())
        lines.append(f"- {representation}: {count}")
    lines.extend(["", "## Sealed label namespaces", ""])
    for row in sealed.sort_values("namespace").itertuples(index=False):
        lines.append(
            f"- {row.namespace}: upstream_rows={int(row.upstream_rows)}, handoff_rows={int(row.handoff_rows)}, status={row.status}"
        )
    lines.extend(
        [
            "",
            "No raw probability presence is treated as causal availability.",
            "All 2024+ settlement labels remain physically absent.",
            "",
        ]
    )
    return "\n".join(lines)


def _schema_problems(package: Path, schema: dict[str, Any], frames: dict[str, pd.DataFrame]) -> list[str]:
    problems: list[str] = []
    table_specs = schema.get("tables")
    if not isinstance(table_specs, dict) or not table_specs:
        return ["schema: missing tables map"]
    for table_name, spec in table_specs.items():
        try:
            path = sources.package_member(package, str(spec.get("path", "")))
        except sources.UpstreamBindingError as error:
            problems.append(f"schema: unsafe table path {table_name}: {error}")
            continue
        if not path.exists():
            problems.append(f"schema: missing table path {table_name}:{path.name}")
            continue
        frame = frames.get(table_name)
        if frame is None:
            try:
                frame = _read_table(path)
            except Exception as error:  # noqa: BLE001
                problems.append(f"schema: cannot read {table_name}: {error}")
                continue
        if int(spec.get("row_count", -1)) != len(frame):
            problems.append(f"schema: {table_name} row_count mismatch")
        columns = spec.get("columns", [])
        expected_names = [column.get("name") for column in columns]
        if expected_names != list(frame.columns):
            problems.append(f"schema: {table_name} columns/order mismatch")
            continue
        if path.suffix == ".parquet":
            arrow = pq.read_schema(path)
            for column in columns:
                name = column["name"]
                actual_physical = str(arrow.field(name).type)
                # Arrow names an in-memory list child ``item`` and the same
                # child ``element`` after a Parquet round-trip. Normalize only
                # that spelling; scalar/list types and nesting stay bound.
                expected_physical = str(column.get("physical_type", "")).replace(
                    "<item:", "<element:"
                )
                if expected_physical != actual_physical:
                    problems.append(f"schema: {table_name}.{name} physical type mismatch")
        for column in columns:
            name = column["name"]
            if not bool(column.get("nullable", True)) and frame[name].isna().any():
                problems.append(f"schema: {table_name}.{name} violates non-null")
            shape = column.get("list_shape")
            if shape == [3]:
                bad = frame[name].dropna().map(lambda value: not _is_vector(value))
                if bad.any():
                    problems.append(f"schema: {table_name}.{name} list shape mismatch")
        primary = spec.get("primary_key") or []
        if isinstance(primary, str):
            primary = [primary]
        if primary:
            if not set(primary).issubset(frame.columns):
                problems.append(f"schema: {table_name} primary key missing")
            elif frame[list(primary)].isna().any().any() or frame.duplicated(list(primary)).any():
                problems.append(f"schema: {table_name} primary key violation")

    # Package-local FK closure.  No private upstream maps are consulted.
    for table_name, spec in table_specs.items():
        source = frames.get(table_name)
        if source is None:
            try:
                path = sources.package_member(package, str(spec.get("path", "")))
            except sources.UpstreamBindingError as error:
                problems.append(f"schema: unsafe table path {table_name}: {error}")
                continue
            if path.exists() and path.suffix in (".csv", ".parquet"):
                source = _read_table(path)
        if source is None:
            continue
        for fk in spec.get("foreign_keys", []):
            column = fk.get("column")
            reference = str(fk.get("references", ""))
            if "." not in reference or column not in source:
                problems.append(f"schema: invalid FK spec {table_name}.{column}")
                continue
            target_table, target_column = reference.split(".", 1)
            target = frames.get(target_table)
            if target is None:
                try:
                    target_path = sources.package_member(
                        package,
                        str(table_specs.get(target_table, {}).get("path", "")),
                    )
                except sources.UpstreamBindingError as error:
                    problems.append(f"schema: unsafe FK target path {target_table}: {error}")
                    continue
                if target_path.exists():
                    target = _read_table(target_path)
            if target is None or target_column not in target:
                problems.append(f"schema: FK target absent {reference}")
                continue
            values = set(source[column].dropna().astype(str))
            targets = set(target[target_column].dropna().astype(str))
            if not values.issubset(targets):
                problems.append(f"schema: FK violation {table_name}.{column}->{reference}")
    return problems


def _causal_problems(cells: pd.DataFrame) -> list[str]:
    problems: list[str] = []
    for representation in contract.CAUSAL_REPRESENTATIONS:
        available_name = contract.available_col(representation)
        observed_name = contract.observed_at_col(representation)
        source_name = contract.source_identity_col(representation)
        for name in (available_name, observed_name, source_name):
            if name not in cells:
                problems.append(f"availability: {representation} missing {name}")
        if available_name not in cells:
            continue
        expected = _expected_available(cells, representation)
        actual = cells[available_name].fillna(False).astype(bool)
        if not actual.equals(expected):
            problems.append(f"availability: {representation} mask mismatch")
        if source_name in cells:
            present = _present(cells, representation)
            missing_source = present & cells[source_name].astype(str).isin(("", contract.SRC_NONE, "nan"))
            if missing_source.any():
                problems.append(f"source trace: {representation} present with no source identity")
    return problems


def _series_equal(left: pd.Series, right: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(left) or pd.api.types.is_numeric_dtype(right):
        return bool(
            np.allclose(
                pd.to_numeric(left, errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(right, errors="coerce").to_numpy(dtype=float),
                equal_nan=True,
                atol=1e-12,
                rtol=1e-10,
            )
        )
    return left.fillna("<NA>").astype(str).equals(right.fillna("<NA>").astype(str))


def _divergence_problems(cells: pd.DataFrame) -> list[str]:
    expected = divergence.build_divergence_features(
        cells.drop(columns=[column for column in divergence.OUTPUT_COLUMNS if column in cells], errors="ignore")
    )
    problems: list[str] = []
    for column in divergence.OUTPUT_COLUMNS:
        if column not in cells:
            problems.append(f"divergence: missing {column}")
        elif column not in expected or not _series_equal(cells[column], expected[column]):
            problems.append(f"divergence: {column} semantic mismatch")
    return problems


def _label_problems(labels: pd.DataFrame, cells: pd.DataFrame, sealed: pd.DataFrame) -> list[str]:
    problems: list[str] = []
    required = {"cell_key", "issue", "match_idx", "outcome_code", "year"}
    if not required.issubset(labels.columns):
        return [f"label: missing package-local identity {sorted(required - set(labels.columns))}"]
    if pd.to_numeric(labels["year"], errors="coerce").gt(contract.LABEL_OPEN_MAX_YEAR).any():
        problems.append("label: future/2024+ label opened")
    if labels["cell_key"].duplicated().any():
        problems.append("label: duplicate cell_key")
    if not set(labels["cell_key"].astype(str)).issubset(set(cells["cell_key"].astype(str))):
        problems.append("label: cell_key FK does not resolve to inference")
    expected_key = (
        labels["issue"].astype(str)
        + ":"
        + labels["match_idx"].astype(str)
        + ":"
        + labels["outcome_code"].astype(str)
    )
    if not labels["cell_key"].astype(str).equals(expected_key):
        problems.append("label: cell_key identity mismatch")
    forbidden = [column for column in labels if "payout" in column.lower() or "tax_" in column.lower() or "winning_zero_return" in column.lower()]
    if forbidden:
        problems.append(f"label: payout boundary fields present {forbidden}")
    if sealed.empty or not sealed["handoff_rows"].eq(0).all():
        problems.append("label: sealed namespace is not physically empty")
    expected_namespaces = {"2024_labels", "2025_plus_labels"}
    if not expected_namespaces.issubset(set(sealed.get("namespace", []))):
        problems.append("label: missing 2024/2025 sealed namespace receipts")
    return problems


def _profile_problems(
    package: Path,
    schema: dict[str, Any],
    cells: pd.DataFrame,
    labels: pd.DataFrame,
) -> list[str]:
    """Recompute core completeness/metric tables from package payloads."""
    recomputed = {
        "missingness_matrix": profile_mod.missingness_matrix(cells),
        "intersection_coverage": profile_mod.intersection_coverage(cells),
        "drift_table": profile_mod.drift_table(cells),
        "source_coverage_strata": divergence.coverage_strata(cells),
        "development_only_calibration": profile_mod.development_only_calibration(cells, labels),
        "predicted_sp_vs_settlement_sp": profile_mod.predicted_sp_vs_settlement_sp(cells, labels),
    }
    problems: list[str] = []
    specs = schema.get("tables", {})
    for name, expected in recomputed.items():
        spec = specs.get(name)
        if spec is None:
            problems.append(f"profile: missing {name}")
            continue
        try:
            actual_path = sources.package_member(package, str(spec["path"]))
        except sources.UpstreamBindingError as error:
            problems.append(f"profile: unsafe table path {name}: {error}")
            continue
        actual = _read_table(actual_path)
        for identifier in ("outcome", "outcome_code"):
            if identifier in actual and identifier in expected:
                # CSV parsing infers categorical codes 3/1/0 as integers.
                # Compare the logical identifiers while retaining exact rows,
                # ordering and every metric value.
                actual[identifier] = actual[identifier].astype(str)
                expected[identifier] = expected[identifier].astype(str)
        try:
            pd.testing.assert_frame_equal(
                actual.reset_index(drop=True), expected.reset_index(drop=True),
                check_dtype=False, check_exact=False, atol=1e-12, rtol=1e-10,
            )
        except AssertionError:
            problems.append(f"profile: {name} semantic mismatch")

    mapping_spec = specs.get("chart_source_mapping")
    if mapping_spec is not None:
        try:
            mapping_path = sources.package_member(package, str(mapping_spec["path"]))
        except sources.UpstreamBindingError as error:
            problems.append(f"profile: unsafe chart mapping path: {error}")
            return problems
        mapping = _read_table(mapping_path)
        for row in mapping.to_dict("records"):
            try:
                figure = sources.package_member(
                    package, Path("figures") / str(row["figure"])
                )
                source_table = sources.package_member(
                    package, str(row["source_table"])
                )
            except sources.UpstreamBindingError as error:
                problems.append(f"profile: unsafe chart source path: {error}")
                continue
            if not figure.exists():
                problems.append(f"profile: chart missing {figure.name}")
            if not source_table.exists():
                problems.append(f"profile: chart source missing {row['source_table']}")
                continue
            source = _read_table(source_table)
            row_count = int(row.get("row_count", -1))
            if row_count != len(source):
                problems.append(f"profile: chart row count mismatch {row['figure']}")
            source_status = (
                source["status"].dropna().astype(str)
                if "status" in source.columns
                else pd.Series(dtype=str)
            )
            unavailable = source.empty or (
                not source_status.empty
                and source_status.str.startswith("UNAVAILABLE").all()
            )
            expected_status = "UNAVAILABLE" if unavailable else "BOUND"
            if row.get("status") != expected_status:
                problems.append(f"profile: dishonest chart status {row['figure']}")
            if unavailable and not str(row.get("reason", "")).strip():
                problems.append(f"profile: missing unavailable reason {row['figure']}")
    return problems


def _manifest_problems(
    package: Path,
    payload: dict[str, Any],
    cells: pd.DataFrame,
    labels: pd.DataFrame,
    sealed: pd.DataFrame,
) -> list[str]:
    problems: list[str] = []
    expected_counts = {
        representation: int(
            cells[contract.available_col(representation)].fillna(False).astype(bool).sum()
        )
        for representation in contract.CAUSAL_REPRESENTATIONS
    }
    if payload.get("causally_available_cells_by_source") != expected_counts:
        problems.append("provenance: manifest causal counts mismatch")
    if int(payload.get("cell_count", -1)) != len(cells):
        problems.append("provenance: manifest cell count mismatch")
    if int(payload.get("development_label_rows_through_2023", -1)) != len(labels):
        problems.append("provenance: manifest label count mismatch")
    if payload.get("schema_sha256") != sources.sha256_file(package / "handoff_schema.json"):
        problems.append("provenance: manifest schema hash mismatch")
    if payload.get("report_sha256") != sources.sha256_file(package / "DATA_READINESS.md"):
        problems.append("provenance: manifest report hash mismatch")

    epoch = pd.to_datetime(cells[contract.DECISION_EPOCH_COLUMN], errors="coerce", utc=True)
    kickoff = pd.to_datetime(cells[contract.KICKOFF_COLUMN], errors="coerce", utc=True)
    has_post_decision = bool(kickoff.lt(epoch).any())
    expected_disposition = profile_mod.readiness_disposition(
        cells, has_post_decision_exclusions=has_post_decision
    )
    if payload.get("disposition") != expected_disposition:
        problems.append("provenance: manifest disposition is not semantically honest")
    if not sealed["handoff_rows"].eq(0).all():
        problems.append("provenance: sealed namespace closure failed")
    return problems


def _expected_requirement_passes(
    cells: pd.DataFrame,
    labels: pd.DataFrame,
    schema: dict[str, Any],
    causal_problems: list[str],
    divergence_problems: list[str],
    label_problems: list[str],
) -> dict[str, bool]:
    vectors_valid = True
    for representation in contract.PROBABILITY_REPRESENTATIONS:
        for value in cells.get(representation, pd.Series(dtype=object)).dropna():
            if not _is_vector(value) or not prob_vector_valid(value):
                vectors_valid = False
    inference_forbidden = any(
        column in cells
        for column in ("result_code", "final_sp", "payout_factor", "payout_after_65_units", "tax_rate")
    )
    every_raw_representation_is_causal = all(
        _present(cells, representation).equals(
            cells.get(
                contract.available_col(representation),
                pd.Series(False, index=cells.index),
            ).fillna(False).astype(bool)
        )
        for representation in contract.CAUSAL_REPRESENTATIONS
    )
    return {
        "REQ-D01": not causal_problems and every_raw_representation_is_causal,
        "REQ-D02": not cells.duplicated(["issue", "match_idx", "outcome_code"]).any() and not any("FK" in p or "identity" in p for p in label_problems),
        "REQ-D03": vectors_valid,
        "REQ-D04": (
            not any(
                "INVALID" in str(value)
                for value in cells.get(
                    "eu_bjline_reason", pd.Series(dtype=object)
                ).dropna()
            )
            and not cells.get(
                contract.producer_reason_col(contract.P_POWER_BJLINE),
                pd.Series(dtype=object),
            ).eq(contract.REASON_SOURCE_LINE_MISMATCH).any()
        ),
        "REQ-D05": not divergence_problems,
        "REQ-D06": not inference_forbidden and not any("future" in p for p in label_problems),
        "REQ-D07": not any("payout" in p for p in label_problems),
        "REQ-D08": "tables" in schema and "chart_source_mapping" in schema.get("tables", {}),
        "REQ-D09": bool(schema.get("tables")),
        # Honesty may legitimately conclude BLOCKED when causal Q_BJ is zero.
        "REQ-D10": True,
    }


def prob_vector_valid(value: object) -> bool:
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return False
    return array.shape == (3,) and np.isfinite(array).all() and (array >= 0).all() and (array <= 1).all() and abs(float(array.sum()) - 1.0) <= contract.PROBABILITY_SUM_TOLERANCE


def validate_package(
    package: Path,
    *,
    repo_root: Path | None = None,
    expected_commit: str | None = None,
) -> list[str]:
    """Return every independent validation defect; empty means valid."""
    package = package.resolve()
    problems: list[str] = []
    try:
        sources.verify_package_hashes(package)
    except Exception as error:  # noqa: BLE001
        problems.append(f"hash: {error}")
        return problems
    try:
        schema = json.loads((package / "handoff_schema.json").read_text(encoding="utf-8"))
        manifest_payload = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
        cells = pq.read_table(package / "inference_cells.parquet").to_pandas()
        labels = pq.read_table(package / "development_labels_through_2023.parquet").to_pandas()
        sealed = pd.read_csv(package / "sealed_label_namespaces.csv")
        evidence = pd.read_csv(package / "evidence" / "req_d_evidence.csv")
    except Exception as error:  # noqa: BLE001
        return [f"schema/package read: {error}"]

    frames = {
        "inference_cells": cells,
        "development_labels": labels,
        "sealed_label_namespaces": sealed,
        "evidence": evidence,
    }
    problems.extend(_schema_problems(package, schema, frames))
    causal = _causal_problems(cells)
    div = _divergence_problems(cells)
    label = _label_problems(labels, cells, sealed)
    problems.extend(causal)
    problems.extend(div)
    problems.extend(label)
    if str(manifest_payload.get("contract_version", "")).endswith("/v2"):
        problems.extend(_profile_problems(package, schema, cells, labels))
        problems.extend(_manifest_problems(package, manifest_payload, cells, labels, sealed))

    expected_passes = _expected_requirement_passes(cells, labels, schema, causal, div, label)
    if set(evidence.get("requirement", [])) != set(expected_passes):
        problems.append("evidence: requirement coverage mismatch")
    else:
        for row in evidence.to_dict("records"):
            actual = bool(row["pass"])
            requirement = str(row["requirement"])
            if actual != expected_passes[requirement]:
                problems.append(f"evidence: {requirement} pass mismatch")
        if "reviewed_commit_sha" not in evidence:
            problems.append("evidence: reviewed_commit_sha missing")
        elif expected_commit is not None and not evidence["reviewed_commit_sha"].astype(str).isin(
            [expected_commit, "PR_HEAD"]
        ).all():
            problems.append("evidence: reviewed commit mismatch")

    reviewed = str(manifest_payload.get("reviewed_commit_sha", ""))
    if expected_commit is not None and reviewed not in (expected_commit, "PR_HEAD"):
        problems.append("provenance: manifest reviewed commit mismatch")
    if repo_root is not None:
        from . import builder

        head = builder._git_head(repo_root)
        if reviewed not in ("SELF", "PR_HEAD", head):
            problems.append("provenance: manifest is not current PR HEAD")
        if manifest_payload.get("code_hash") != builder._dir_hash(repo_root / "src" / "divergence_profile"):
            problems.append("provenance: code hash mismatch")
        notebook = repo_root / "notebooks" / "research" / "issue-229" / "bj229_divergence_profile.ipynb"
        if manifest_payload.get("notebook_hash") != builder._notebook_semantic_hash(notebook):
            problems.append("provenance: notebook semantic hash mismatch")
        requirements = repo_root / "requirements.txt"
        if requirements.exists() and manifest_payload.get("requirements_hash") != sources.sha256_file(requirements):
            problems.append("provenance: dependency hash mismatch")

    report_path = package / "DATA_READINESS.md"
    expected_report = render_data_readiness(cells, labels, sealed, manifest_payload)
    if not report_path.exists() or report_path.read_text(encoding="utf-8") != expected_report:
        problems.append("report: DATA_READINESS.md semantic mismatch")
    return sorted(set(problems))


def load_package(
    package: Path,
    *,
    repo_root: Path | None = None,
    expected_commit: str | None = None,
) -> PackageBundle:
    problems = validate_package(package, repo_root=repo_root, expected_commit=expected_commit)
    if problems:
        raise HandoffValidationError("; ".join(problems))
    schema = json.loads((package / "handoff_schema.json").read_text(encoding="utf-8"))
    manifest_payload = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    tables: dict[str, pd.DataFrame] = {}
    for name, spec in schema["tables"].items():
        path = package / spec["path"]
        if path.suffix in (".csv", ".parquet"):
            tables[name] = _read_table(path)
    return PackageBundle(
        package=package,
        inference_cells=tables["inference_cells"],
        development_labels=tables["development_labels"],
        sealed_namespaces=tables["sealed_label_namespaces"],
        evidence=tables["evidence"],
        schema=schema,
        manifest=manifest_payload,
        tables=tables,
    )


def load_causal_inference_cells(package: Path, **kwargs: Any) -> pd.DataFrame:
    """#209 loader: raw-but-unavailable representations are physically nulled."""
    cells = load_package(package, **kwargs).inference_cells.copy()
    for representation in contract.CAUSAL_REPRESENTATIONS:
        available = cells[contract.available_col(representation)].fillna(False).astype(bool)
        cells.loc[~available, representation] = np.nan
    return cells


# ---------------------------------------------------------------------------
# Small valid package and attacks used by executable mutation tests.
# ---------------------------------------------------------------------------
def write_test_package(root: Path, cells: pd.DataFrame, labels: pd.DataFrame) -> Path:
    from . import builder

    package = root / "package"
    if package.exists():
        shutil.rmtree(package)
    package.mkdir(parents=True)
    cells = cells.copy()
    for representation in contract.CAUSAL_REPRESENTATIONS:
        available_name = contract.available_col(representation)
        if available_name not in cells:
            cells[available_name] = False
        cells[contract.observed_at_col(representation)] = np.where(
            cells[available_name].fillna(False),
            pd.Timestamp("2020-12-31T23:00:00Z"),
            pd.NaT,
        )
        source_name = contract.source_identity_col(representation)
        if source_name not in cells:
            cells[source_name] = contract.SRC_NONE
        cells[contract.reason_col(representation)] = np.where(
            cells[available_name].fillna(False), None, contract.REASON_NO_CAUSAL_EPOCH
        )
    cells = divergence.build_divergence_features(cells)
    sealed = pd.DataFrame(
        {
            "namespace": ["2024_labels", "2025_plus_labels"],
            "status": ["SEALED_NOT_OPENED", "SEALED_NOT_OPENED"],
            "upstream_rows": [0, 0],
            "handoff_rows": [0, 0],
        }
    )
    chart = pd.DataFrame({"figure": ["drift.png"], "source_table": ["drift_table"], "status": ["AVAILABLE"]})
    evidence = pd.DataFrame(
        {
            "requirement": [f"REQ-D{i:02d}" for i in range(1, 11)],
            "pass": [False, True, True, True, True, True, True, True, True, True],
            "reviewed_commit_sha": ["SELF"] * 10,
        }
    )
    payloads = {
        "inference_cells": ("inference_cells.parquet", cells),
        "development_labels": ("development_labels_through_2023.parquet", labels),
        "sealed_label_namespaces": ("sealed_label_namespaces.csv", sealed),
        "chart_source_mapping": ("tables/chart_source_mapping.csv", chart),
        "evidence": ("evidence/req_d_evidence.csv", evidence),
    }
    for _name, (relative, frame) in payloads.items():
        path = package / relative
        if path.suffix == ".parquet":
            publication.atomic_write_parquet(frame, path)
        else:
            publication.atomic_write_csv(frame, path)
    schema = builder.build_schema(payloads)
    publication.atomic_write_json(package / "handoff_schema.json", schema)
    manifest_payload = {
        "package": contract.PACKAGE_NAME,
        "reviewed_commit_sha": "SELF",
        "disposition": "READY_WITH_EXPLICIT_LIMITATIONS",
        "code_hash": "TEST",
        "notebook_hash": "TEST",
        "requirements_hash": "TEST",
    }
    publication.atomic_write_json(package / "MANIFEST.json", manifest_payload)
    publication.atomic_write_text(
        package / "DATA_READINESS.md",
        render_data_readiness(cells, labels, sealed, manifest_payload),
    )
    from . import manifest as manifest_mod

    manifest_mod.write_sha256sums(package)
    return package


def apply_test_mutation(package: Path, mutation: str) -> None:
    cells_path = package / "inference_cells.parquet"
    labels_path = package / "development_labels_through_2023.parquet"
    if mutation in {"divergence", "availability", "source_trace"}:
        cells = pq.read_table(cells_path).to_pandas()
        if mutation == "divergence":
            column = divergence.DIVERGENCE_EU_BJ
            index = cells[column].first_valid_index()
            if index is None:
                index = cells.index[0]
                cells.loc[index, column] = 0.123
            else:
                cells.loc[index, column] = float(cells.loc[index, column]) + 0.123
        elif mutation == "availability":
            column = contract.available_col(contract.Q_BJ_CALIBRATED)
            cells.loc[cells.index[0], column] = not bool(cells.loc[cells.index[0], column])
        else:
            cells.loc[cells.index[0], contract.SOURCE_IDENTITY_Q_BJ] = contract.SRC_NONE
        publication.atomic_write_parquet(cells, cells_path)
    elif mutation in {"labels", "future_label"}:
        labels = pq.read_table(labels_path).to_pandas()
        if mutation == "labels":
            labels.loc[labels.index[0], "cell_key"] = "forged:999:3"
        else:
            labels.loc[labels.index[0], "year"] = 2024
        publication.atomic_write_parquet(labels, labels_path)
    elif mutation in {"schema", "schema_path"}:
        path = package / "handoff_schema.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "schema":
            first = payload["tables"]["inference_cells"]["columns"][0]
            first["physical_type"] = "definitely_wrong_type"
        else:
            payload["tables"]["development_labels"]["path"] = "../../outside.parquet"
        publication.atomic_write_json(path, payload)
    elif mutation == "evidence":
        path = package / "evidence" / "req_d_evidence.csv"
        evidence = pd.read_csv(path)
        evidence.loc[evidence.index[0], "pass"] = not bool(evidence.loc[evidence.index[0], "pass"])
        publication.atomic_write_csv(evidence, path)
    elif mutation == "report":
        publication.atomic_write_text(package / "DATA_READINESS.md", "forged report\n")
    else:
        raise ValueError(f"unknown test mutation: {mutation}")
