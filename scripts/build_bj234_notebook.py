#!/usr/bin/env python3
"""Build the issue-234 source-schema notebook (JSON), then execute it.

The notebook is a thin readable orchestration layer: it runs the reusable
``src/source_schema`` package top-to-bottom, renders every committed
machine-readable table/figure and verifies the immutable package.  All
durable evidence lives in ``results/bj234_source_schema_v1/``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks/research/issue-234/bj234_source_schema.ipynb"


def build_nb() -> list[dict]:
    def md(src):
        return nbformat.v4.new_markdown_cell(src)

    def code(src):
        return nbformat.v4.new_code_cell(src)

    return [
        md("""\
# Issue #234 — canonical source registry, identity and temporal store schema

**Contract:** BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (PI-user design freeze, 2026-08-16)
**Audit mode:** candidate
**Owner role:** Engineer · Project: BJ Data Platform · Milestone: M1 · Parent: #232

This notebook is a thin orchestration layer: it runs the reusable
`src/source_schema` package top-to-bottom, renders every committed
machine-readable table and verifies the immutable package. All durable
evidence lives in `results/bj234_source_schema_v1/`.

What is frozen here:
- source registry (every source gets admissible-use class with evidence, REQ-DS01)
- canonical fixture identity (unique within `issue_code x match_idx`, REQ-DS02)
- decision-epoch / observed / received / kickoff semantics (REQ-DS03)
- normalized tables and key/domain constraints rejecting duplicate/invalid M×3 cells (REQ-DS04)
- inference / proxy / settlement namespaces physically distinguishable (REQ-DS05)
- SQLite WAL + pandas/PyArrow + measured scale/concurrency justification (REQ-DS06)
- notebook tables bind machine-readable outputs and source hashes (REQ-DS07)
- handoff names exact interfaces for #235/#236/#237/#238 (REQ-DS08)
"""),
        code("""\
import json
import sys
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "src").exists() else Path("/home/drwho1985/beijing-lot-234")
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import pyarrow as pa

from source_schema import contract, crosswalk, feasibility, profiler, publication, schemas
"""),
        md("""\
## 1. Profile every existing source database (read-only)

The issue contract names four databases plus the #203/#214/#229 immutable
packages.  We profile each: tables, row counts, keys, timestamp ranges,
nulls, duplicates and journal mode.  All probes are read-only
(`PRAGMA query_only=ON`).
"""),
        code("""\
profile = profiler.profile_all()
rows = []
for db, info in profile.items():
    if not info.get("present"):
        rows.append({"database": db, "size_mb": None, "journal_mode": None,
                     "tables": "MISSING", "identity_dup": None})
        continue
    rows.append({
        "database": db,
        "size_mb": info.get("size_mb"),
        "journal_mode": info.get("journal_mode"),
        "tables": ",".join(t["name"] for t in info.get("tables", [])),
        "identity_dup": info.get("identity_dup"),
    })
pd.DataFrame(rows)
"""),
        md("""\
## 2. Timestamp clock probes — the causal-admissibility evidence

The critical finding: `beidan_xlsm.sqlite` `market_snapshots.snapshot` holds
*labels* (`initial` / `10h` / `1h` / `final`), not exact timestamps; the
`beidan_history.db` settlement table has no settled-timestamp column; and
`beidan_features.db` kickoff formats are mixed (time-only `08:00:00` strings
sort before dates).  Only `beidan_live.db` carries native ISO-8601 `Z`
snapshot timestamps prospectively from 2026-05.
"""),
        code("""\
clocks = profiler.classify_source_clocks(profile)
pd.DataFrame(clocks)[["source", "family", "admissible_use", "clock_semantics"]]
"""),
        code("""\
# Exact timestamp ranges from the probe (machine-readable evidence)
for db, info in profile.items():
    if not info.get("present"):
        continue
    print(f"--- {db}")
    for key in ("kickoff_range", "snapshot_range", "settled_range",
                "snapshot_labels", "settle_range_endtime", "settle_fetched_range"):
        if info.get(key):
            print(f"  {key}: {info[key]}")
"""),
        md("""\
## 3. Versioned SQL DDL + PyArrow schemas + domain dictionary

The DDL is the frozen interface for all #232 recovery branches.  It is
rendered deterministically from `src/source_schema/contract.py`; the SQL and
PyArrow schemas therefore cannot drift apart.  Physical namespaces:
`capture` (append-only control tables), `inference` (market observations /
quotes / probability estimates) and a physically separate `settlement` table.
"""),
        code("""\
ddl = schemas.render_ddl()
print(ddl[:1200])
print("...")
print(f"DDL sha256: {schemas.render_ddl_sha256()}")
"""),
        code("""\
# PyArrow schema for one canonical table materializes cleanly
quote_schema = schemas.arrow_schema("market_quote")
quote_schema
"""),
        code("""\
domain = pd.DataFrame(schemas.domain_dictionary())
domain[domain["column"].isin(["outcome_code", "observed_at_utc", "received_at_utc",
                              "kickoff_at_utc", "decision_at_utc", "fixture_id"])]
"""),
        md("""\
## 4. Identity crosswalk (REQ-DS02)

Every legacy database binds to the canonical fixture identity through an
explicit crosswalk — never a silent fuzzy match.  `fixture_id` is unique
within `issue_code x match_idx`.
"""),
        code("""\
cw = pd.DataFrame(crosswalk.identity_crosswalk_rows())
cw
"""),
        code("""\
print(json.dumps(crosswalk.canonical_identity_rule(), indent=1))
"""),
        md("""\
## 5. Source feasibility matrix (REQ-DS01) + migration-free replacement plan

Each candidate source carries acquisition cost / access / licensing /
coverage / clock grade and a concrete selected source per downstream branch
(#235 Beijing SP, #236 EU odds, #237 power features, #238 materializer).
"""),
        code("""\
fm = pd.DataFrame(feasibility.feasibility_matrix())
fm[["source_id", "family", "cost", "access", "licensing", "coverage",
    "clock_grade", "admissible_use", "selected_for"]]
"""),
        code("""\
print(feasibility.REPLACEMENT_PLAN["principle"])
for legacy in feasibility.REPLACEMENT_PLAN["replaced_schemas"]:
    print(f"- {legacy['legacy']} -> {legacy['replacement']}")
"""),
        md("""\
## 6. Immutable package + manifest binding (REQ-DS07)

The build publishes an immutable package with `MANIFEST.json` +
`SHA256SUMS.json` binding every machine-readable artifact and the reviewed
#203/#214/#229 source hashes.  Verification re-hashes the whole package and
re-checks the bound source hashes against the referenced immutable packages.
"""),
        code("""\
PKG = ROOT / "results/bj234_source_schema_v1"
verdict = publication.verify_package(PKG)
print(f"package verified: {verdict['files']} files")
manifest = json.loads((PKG / "MANIFEST.json").read_text())
print(f"contract: {manifest['contract_version']}")
print(f"disposition: {manifest['disposition']}")
print("bound source hashes:")
for rel, h in manifest["source_hashes"].items():
    print(f"  {rel}: {h[:16]}…" if h else f"  {rel}: (absent)")
"""),
        code("""\
# Package census — every artifact the contract commits to
for p in sorted(PKG.rglob("*")):
    if p.is_file():
        print(f"  {p.relative_to(PKG)}  ({p.stat().st_size} B)")
"""),
        md("""\
## 7. Concurrency / scale justification (REQ-DS06)

The design reuses the existing mature stack: SQLite WAL for one-writer
append-only capture/control tables, immutable partitioned Parquet for
research snapshots read by pandas/PyArrow.  No new service/database until
measured concurrency requires it.  Measured scale: `beidan_live.db` = 262 MB /
1.49M snapshots today; `beidan_xlsm.sqlite` = 6.9 GB / 51.5M snapshots as
read-only history.  Both fit the WAL + Parquet split.
"""),
        code("""\
scale = feasibility.REPLACEMENT_PLAN["concurrency_justification"]
print(f"engine: {scale['engine']}")
print(f"rationale: {scale['rationale']}")
for k, v in scale["scale_measurements"].items():
    print(f"  {k}: {v}")
"""),
        md("""\
## 8. Handoff to downstream subissues (REQ-DS08)

Exact interfaces named for #235 (BJ SP timeseries), #236 (EU odds), #237
(power features) and #238 (materializer).  See `replacement_plan.json` and
`source_feasibility_matrix.csv` in the immutable package; the DDL in
`schema.sql` is the contract every recovery branch must consume.
"""),
        code("""\
binding = feasibility.REPLACEMENT_PLAN["acceptance_binding"]
for req, how in binding.items():
    print(f"{req}: {how}")
"""),
    ]


def main() -> int:
    NB.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb["cells"] = build_nb()
    nbformat.validate(nb)
    NB.write_text(nbformat.writes(nb))
    print(f"WROTE {NB}")
    subprocess.run([
        sys.executable, str(ROOT / "scripts/execute_bj234_notebook.py"),
    ], check=True, cwd=ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
