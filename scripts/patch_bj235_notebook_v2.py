#!/usr/bin/env python3
"""Make the #235 notebook reflect the v2 relative-proxy delivery contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "research" / "issue-235" / "bj235_bj_sp_timeseries.ipynb"


def source(lines: list[str]) -> list[str]:
    return [line if line.endswith("\n") else f"{line}\n" for line in lines]


def main() -> int:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cells = notebook["cells"]
    cells[0]["source"] = source([
        "# BJ-235 — Beijing native line and 3/1/0 SP time series",
        "",
        "Contract: `BJ-UNIFIED-BJ-SP-TIMESERIES-001 / v1` with PI amendment v2 (2026-08-17).",
        "",
        "The primary historical delivery is the explicit `RETROSPECTIVE_RELATIVE_PROXY`",
        "M×3 panel at initial/10h/1h/final buckets. It does not fabricate exact clocks",
        "and must not be labelled unrecoverable solely for lacking them.",
    ])
    cells[2]["source"] = source([
        "import json, os, sys, sqlite3",
        "from pathlib import Path",
        "",
        "ROOT = Path.cwd().resolve()",
        "sys.path.insert(0, str(ROOT))",
        "CANON = Path(os.environ.get('BJ235_CANONICAL', ROOT / 'data' / 'derived' / 'bj235' / 'bj_sp_canonical.sqlite'))",
        "OUT = Path(os.environ.get('BJ235_OUT', ROOT / 'results' / 'bj235_bj_sp_timeseries_v2'))",
        "report_path = OUT / 'RECOVERABILITY_REPORT.json'",
        "con = sqlite3.connect(f'file:{CANON}?mode=ro', uri=True)",
        "con.row_factory = sqlite3.Row",
        "report = json.loads(report_path.read_text(encoding='utf-8'))",
        "print('canonical db:', CANON)",
        "print('report loaded:', report_path)",
    ])
    cells[8]["source"] = source([
        "support = report['issue_support']",
        "print('ISSUE-LEVEL SUPPORT BY COHORT:')",
        "for cohort, values in support['by_cohort'].items():",
        "    print(' ', cohort, values)",
        "pd.DataFrame(support['per_issue']).tail(15)",
    ])
    cells[9]["source"] = source([
        "## 4. Historical proxy panel and strict-clock boundary (REQ-BJ06/BJ08/BJ09)",
        "",
        "The strict-clock historical subset remains zero. The separately labelled relative",
        "proxy panel is a positive delivery; it has source/issue/fixture/native-line/outcome/",
        "bucket/availability provenance and never substitutes settlement or later data.",
    ])
    cells[10]["source"] = source([
        "hist = report['historical']",
        "panel = hist['panel']",
        "print('DISPOSITION:', hist['disposition'])",
        "print('strict historical causal support:', hist['strict_historical_causal_support'])",
        "print('proxy cells / present / missing:', panel['cells_total'], panel['cells_present'], panel['cells_missing'])",
        "print('proxy issues / fixtures:', panel['issues_covered'], panel['fixtures_covered'])",
        "print('buckets:', panel['buckets_profiled'])",
        "pd.DataFrame([{'snapshot_bucket': key, **value} for key, value in hist['historical_panel'].items()])",
    ])
    cells[14]["source"] = source([
        "pe = report['build_steps'].get('probabilities', {})",
        "print('probability rows built:', pe.get('probability_rows', 0))",
        "bad_065 = con.execute(\"SELECT COUNT(*) FROM market_quote WHERE decimal_odds=0.65\").fetchone()[0]",
        "panel_065 = con.execute(\"SELECT COUNT(*) FROM relative_horizon_panel WHERE decimal_odds=0.65\").fetchone()[0]",
        "print('0.65 quote rows:', bad_065, 'panel rows:', panel_065)",
    ])
    cells[17]["source"] = source([
        "## 8. Package integrity and common v2 handoff",
        "",
        "The immutable package includes the canonical table export, the common `relative_horizon_view`",
        "long M×3 parquet required by #238, a manifest, and SHA-256 coverage.",
    ])
    cells[19]["source"] = source([
        "## 9. Acceptance trace",
        "",
        "| REQ | Evidence |",
        "|---|---|",
        "| BJ01 | source registry plus source/issue/fixture/native-line/outcome/bucket/provenance hash |",
        "| BJ02 | finite positive quotes or explicit `availability=missing` cells |",
        "| BJ03 | strict as-of replay remains separate and rejects post-decision/post-kickoff rows |",
        "| BJ04 | native line is bound to every panel cell; no cross-line replay join |",
        "| BJ05 | no settlement fields or 0.65 in inference/panel view |",
        "| BJ06 | strict historical, retrospective proxy, and prospective support are separate |",
        "| BJ07 | deterministic panel ids and idempotent `INSERT OR IGNORE` ingestion |",
        "| BJ08 | positive `HISTORICAL_RELATIVE_PROXY_PANEL` disposition with limits |",
        "| BJ09 | issue/horizon coverage and `relative_horizon_view.parquet` |",
    ])
    NOTEBOOK.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"patched {NOTEBOOK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
