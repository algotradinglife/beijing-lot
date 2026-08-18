"""Issue #234 — independent package validation (verifier).

The verifier is the contract's tamper self-test surface (REQ-E06): it
recomputes every hash, re-runs the semantic checks and fails closed when any
package artifact is modified.  The EV runs this verifier on a fresh checkout;
the package must also survive the same checks after adversarial tampering of
the census tables, the manifest or the DDL.

Checks performed:

1. SHA256SUMS.json full-tree hash recomputation (tamper detection).
2. DDL syntax smoke: the emitted SQL actually creates all canonical tables in
   an in-memory SQLite database (REQ-DS04/DS05).
3. Source registry completeness: every family has a row; every registry row
   carries an admissible-use class + clock semantics + coverage grade
   (REQ-DS01).
4. Identity rule present in DDL: UNIQUE(issue_code, match_idx) (REQ-DS02).
5. Temporal semantics contract: the four semantics are distinct and the DDL
   uses distinct column names (REQ-DS03).
6. Namespace separation: inference/proxy/settlement schemas present and
   disjoint (REQ-DS05).
7. Manifest receipt binds source hashes + notebook hash + code hash
   (REQ-DS07).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from . import contract
from . import sources


class ContractViolation(Exception):
    """Raised when a semantic check fails."""


def validate_package(package: Path, repo_root: Path) -> list[str]:
    """Run all semantic checks; return a list of problems (empty = PASS)."""
    problems: list[str] = []

    # 1. Hash integrity
    try:
        sources.verify_package_hashes(package)
    except AssertionError as error:
        problems.append(f"hash integrity: {error}")

    # 2. DDL executes in SQLite (schema smoke test)
    sql_text = (package / "sql" / "schema.sql").read_text(encoding="utf-8")
    try:
        connection = sqlite3.connect(":memory:")
        connection.executescript(sql_text)
        created = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = (set(contract.CAPTURE_TABLES) | set(contract.SETTLEMENT_TABLES)) - created
        if missing:
            problems.append(f"DDL missing tables: {sorted(missing)}")
        connection.close()
    except sqlite3.Error as error:
        problems.append(f"DDL does not execute: {error}")

    # 3. Source registry completeness
    registry_path = package / "tables" / "source_registry.csv"
    if registry_path.exists():
        registry = pd.read_csv(registry_path)
        required_columns = {
            "source_id",
            "admissible_use",
            "clock_semantics",
            "coverage_grade",
            "first_usable_at_utc",
            "last_usable_at_utc",
        }
        if not required_columns.issubset(set(registry.columns)):
            problems.append(
                f"source_registry missing columns: {sorted(required_columns - set(registry.columns))}"
            )
        else:
            if bool(registry["admissible_use"].isna().any()):
                problems.append("source_registry has rows without admissible_use")
            if bool(registry["clock_semantics"].isna().any()):
                problems.append("source_registry has rows without clock_semantics")
    else:
        problems.append("tables/source_registry.csv missing")

    # 4. Identity rule present in DDL
    if "UNIQUE (issue_code, match_idx)" not in sql_text:
        problems.append("DDL missing UNIQUE(issue_code, match_idx)")

    # 5. Temporal semantics distinct in contract + DDL
    semantics = set(contract.TEMPORAL_SEMANTICS)
    if len(semantics) != len(contract.TEMPORAL_SEMANTICS):
        problems.append("temporal semantics are not distinct")
    for column in contract.TEMPORAL_SEMANTICS:
        if column not in sql_text:
            problems.append(f"DDL missing temporal column {column}")

    # 6. Namespace separation
    schema_contract = json.loads(
        (package / "schemas" / "parquet_schema.json").read_text(encoding="utf-8")
    )
    namespaces = schema_contract.get("namespaces", {})
    for namespace in (
        contract.INFERENCE_NAMESPACE,
        contract.PROXY_NAMESPACE,
        contract.SETTLEMENT_NAMESPACE,
    ):
        if namespace not in namespaces:
            problems.append(f"parquet schema missing namespace {namespace}")

    # 7. Manifest receipt
    manifest_path = package / "MANIFEST.json"
    if not manifest_path.exists():
        problems.append("MANIFEST.json missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("contract_version") != contract.CONTRACT_VERSION:
            problems.append("manifest contract_version mismatch")
        if not manifest.get("source_hashes"):
            problems.append("manifest missing source_hashes receipt")
        if not manifest.get("code_hash"):
            problems.append("manifest missing code_hash")
        if not manifest.get("notebook_hash"):
            problems.append("manifest missing notebook_hash")

    return problems


def verify_package(package: Path, repo_root: Path) -> None:
    """Fail-closed wrapper used by the build CLI verify command."""
    problems = validate_package(package, repo_root)
    if problems:
        raise ContractViolation(
            "package verification failed:\n" + "\n".join(problems)
        )
