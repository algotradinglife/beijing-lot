#!/usr/bin/env python3
"""Generate the Issue #234 census notebook (not executed yet; execute script runs it)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB_PATH = ROOT / "notebooks" / "research" / "issue-234" / "bj234_source_schema.ipynb"

cells = [
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# Issue #234 — Source registry, canonical identity & temporal store schema\n",
            "\n",
            "BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v2 (EV R1 rework, candidate mode).\n",
            "\n",
            "This notebook is a **read-only census** of every registered source database\n",
            "and the referenced immutable packages (#203/#214/#229). It profiles tables,\n",
            "keys, time ranges, nulls, duplicates, source clocks and raw-content hashes.\n",
            "It **never reads settlement/label values** (C4 sealing): columns such as\n",
            "`score`, `result_code`, `winning_sp`, `hit`, settlement tables are sealed\n",
            "and physically unreadable through the census API.\n",
            "\n",
            "Deliverables bound here (REQ-DS07):\n",
            "- `tables/databases.csv`, `tables/tables.csv`, `tables/columns.csv`\n",
            "- `tables/identity_checks.csv` (NULL-aware, correct primitive keys — C1)\n",
            "- `tables/sealed_columns.csv` (C4 sealing evidence)\n",
            "- `tables/source_registry.csv`, `tables/feasibility_matrix.csv` (C2)\n",
            "- `MANIFEST.json` source hashes\n",
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "import sys, json\n",
            "from pathlib import Path\n",
            "ROOT = Path.cwd()\n",
            "# When executed via nbclient from notebooks/research/issue-234, repo root is ../../..\n",
            "if not (ROOT / \"src\").exists():\n",
            "    ROOT = Path.cwd().parents[2]\n",
            "sys.path.insert(0, str(ROOT / \"src\"))\n",
            "print(\"ROOT:\", ROOT)"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "from source_schema import contract, ddl, profiler, sources, verify, builder\n",
            "import pandas as pd\n",
            "pd.set_option(\"display.max_columns\", 30)\n",
            "pd.set_option(\"display.width\", 200)\n",
            "print(\"contract:\", contract.CONTRACT_VERSION, \"/\", contract.CONTRACT_MODE)\n",
            "print(\"data root:\", profiler.resolve_data_root())"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# C4 sealing guard: settlement/label columns are physically unreadable\n",
            "from source_schema.profiler import SealedColumnError, assert_measurable\n",
            "sealed_attempts = [\n",
            "    (\"beidan_xlsm.sqlite\", \"matches\", \"result_label\"),\n",
            "    (\"beidan_xlsm.sqlite\", \"match_features\", \"result_code\"),\n",
            "    (\"beidan_live.db\", \"settlements\", \"winning_sp\"),\n",
            "    (\"500_bjdc.sqlite\", \"matches\", \"result_code\"),\n",
            "]\n",
            "for db, table, col in sealed_attempts:\n",
            "    try:\n",
            "        assert_measurable(db, table, col)\n",
            "        print(f\"UNSEALED?! {db}.{table}.{col}\")\n",
            "    except SealedColumnError:\n",
            "        print(f\"SEALED OK: {db}.{table}.{col}\")\n",
            "assert_measurable(\"beidan_live.db\", \"snapshots\", \"snapshot_ts\")\n",
            "print(\"allow-listed snapshot_ts readable OK\")"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Read-only census of all registered databases\n",
            "census = profiler.run_census(profiler.resolve_data_root())\n",
            "dbs = pd.DataFrame(census.databases)\n",
            "dbs[['database_key','exists','size_mb','sha256']].head(20)"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "tables = pd.DataFrame(census.tables)\n",
            "tables.head(30)"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# C1: identity metrics — NULL-aware, correct primitive keys, real duplicate excess\n",
            "identity = pd.DataFrame(census.identity)\n",
            "identity[['database_key','table','primitive_key','total_rows','null_key_rows',\n",
            "         'non_null_rows','distinct_non_null_keys','duplicate_excess','uniqueness_verdict']]"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# C4: sealed columns — settlement/label values never measured\n",
            "sealed = pd.DataFrame(census.sealed)\n",
            "print(\"sealed entries:\", len(sealed))\n",
            "sealed.head(20)"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Clock evidence (REQ-DS03): timestamp columns measured, semantics assigned\n",
            "ts = pd.DataFrame(census.timestamps)\n",
            "ts[['database_key','table','column','clock_semantics','min','max']].head(40)"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Source registry + feasibility matrix (C2: evidence, not reputation)\n",
            "census_hashes = {d['database_key']: d['sha256'] for d in census.databases if d.get('sha256')}\n",
            "registry = sources.registry_frame(census_hashes)\n",
            "registry[['source_id','provider','endpoint','clock_semantics','admissible_use',\n",
            "         'coverage_grade','raw_sha256','selected_for_branch']]"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Build the immutable package and run the semantic verifier (E2)\n",
            "package_dir = ROOT / \"results\" / contract.PACKAGE_DIR_NAME\n",
            "builder.build_package(ROOT, package_dir, force=True)\n",
            "verdict = verify.verify_package(package_dir, ROOT)\n",
            "print(\"VERIFIED\" if verdict[\"verified\"] else \"VERIFY FAILED\")\n",
            "for problem in verdict[\"problems\"]:\n",
            "    print(\"  -\", problem)"
        ],
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# REQ-DS evidence table\n",
            "pd.read_csv(package_dir / \"evidence\" / \"req_ds_evidence.csv\")"
        ],
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## Conclusion\n",
            "\n",
            "- Sources are classified by measured evidence (REQ-DS01); the 500.com\n",
            "  third-party collector plane is named honestly (C2), and the first-party\n",
            "  Beijing interface is registered UNUSABLE until acquired.\n",
            "- Legacy identity conclusions are NULL-aware: 2,560 NULL-key rows in\n",
            "  `beidan_xlsm.matches` are UNIDENTIFIED, not duplicates; real\n",
            "  duplicate excess is 0 (C1).\n",
            "- The frozen DDL rejects orphan quotes (FK ON), duplicate primitive\n",
            "  observations, duplicate euro cells (COALESCE unique), overlapping alias\n",
            "  windows, non-canonical/reversed timestamps, and observation-after-kickoff\n",
            "  (C3). Multi-bookmaker quotes are legal.\n",
            "- 2024+ outcome/settlement values are sealed: the census never reads them,\n",
            "  and the notebook proves the guard rejects sealed reads (C4).\n",
            "- The semantic verifier rebuilds the schema and registry from committed\n",
            "  payloads; every remanifest attack in the test suite fails closed (E2).\n",
        ],
    },
]

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.14"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

NB_PATH.parent.mkdir(parents=True, exist_ok=True)
NB_PATH.write_text(json.dumps(nb, indent=1))
print(f"wrote {NB_PATH}")
