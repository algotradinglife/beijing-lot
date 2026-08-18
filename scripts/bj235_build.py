#!/usr/bin/env python3
"""BJ-235 build: causal Beijing handicap + pre-event SP timeseries recovery.

Usage:
    python scripts/bj235_build.py --data-root <repo-data> --out <results-dir>

    --data-root   path to the repo data/ directory (contains beidan_live.db,
                   derived/500_bjdc/500_bjdc.sqlite, beidan_history.db,
                   derived/beidan_xlsm/beidan_xlsm.sqlite)
    --bundles     results/data_collection root (multimarket_sp_capture_v1)
    --out         results output dir (default results/bj235_bj_sp_timeseries_v1)
    --canonical   canonical SQLite path (default data/derived/bj235/bj_sp_canonical.sqlite)
    --skip-xlsm   skip slow 6.8GB xlsm profiling (default: profile only summary)

Build steps: register sources -> ingest beidan_live + 500 xml34 + bundles +
settlement history -> decision epochs -> as-of replay -> probabilities ->
recoverability report -> parquet export -> manifest + hashes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bj_sp_timeseries.asof import (  # noqa: E402
    build_decision_epochs,
    build_probability_estimates,
    run_asof_replay,
)
from src.bj_sp_timeseries.export import export_parquet  # noqa: E402
from src.bj_sp_timeseries.ingest import (  # noqa: E402
    connect_canonical,
    ingest_beidan_live,
    ingest_multimarket_bundles,
    ingest_settlement_history,
    ingest_500_xml34,
    register_sources,
)
from src.bj_sp_timeseries.recover import (  # noqa: E402
    build_waterfall_report,
    issue_level_support,
    write_exclusion_ledger_from_analysis,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True, type=Path)
    ap.add_argument("--bundles", type=Path, default=None)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "bj235_bj_sp_timeseries_v2")
    ap.add_argument("--canonical", type=Path,
                    default=ROOT / "data" / "derived" / "bj235" / "bj_sp_canonical.sqlite")
    ap.add_argument("--skip-xlsm", action="store_true", default=False)
    ap.add_argument("--proxy-only", action="store_true",
                    help="build only the v2 historical relative-proxy panel")
    args = ap.parse_args()

    t0 = time.time()
    data_root: Path = args.data_root
    canonical: Path = args.canonical

    con = connect_canonical(canonical)
    register_sources(con)

    live_db = data_root / "beidan_live.db"
    bjdc_db = data_root / "derived" / "500_bjdc" / "500_bjdc.sqlite"
    hist_db = data_root / "beidan_history.db"
    bundles = args.bundles or (ROOT / "results" / "data_collection")

    steps = {}

    if not args.proxy_only:
        if live_db.exists():
            steps["beidan_live"] = ingest_beidan_live(con, live_db)
        else:
            print(f"[warn] missing {live_db}", file=sys.stderr)

        if bjdc_db.exists():
            steps["500_xml34"] = ingest_500_xml34(con, bjdc_db)
        else:
            print(f"[warn] missing {bjdc_db}", file=sys.stderr)

        if bundles.exists():
            steps["bundles"] = ingest_multimarket_bundles(con, bundles / "multimarket_sp_capture_v1")
        else:
            print(f"[warn] missing bundles root {bundles}", file=sys.stderr)

        if hist_db.exists():
            steps["settlement_history"] = ingest_settlement_history(con, hist_db)
        else:
            print(f"[warn] missing {hist_db}", file=sys.stderr)

    from src.bj_sp_timeseries.panel import (
        ingest_xlsm_panel,
        panel_support,
        verify_panel_provenance,
    )

    xlsm = data_root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
    xlsm_profile = None
    panel_counts = None
    if xlsm.exists() and not args.skip_xlsm:
        xlsm_profile = _profile_xlsm(xlsm)
        panel_counts = ingest_xlsm_panel(con, xlsm)

    if not args.proxy_only:
        steps["decision_epochs"] = build_decision_epochs(con)
        steps["asof"] = run_asof_replay(con)
        steps["probabilities"] = build_probability_estimates(con)
    steps["exclusions"] = write_exclusion_ledger_from_analysis(con)

    report = build_waterfall_report(con)
    report["build_steps"] = {k: v for k, v in steps.items() if v}
    report["xlsm_profile"] = xlsm_profile
    report["panel_ingestion"] = panel_counts
    if panel_counts:
        report["panel_support"] = panel_support(con)
        report["panel_provenance"] = verify_panel_provenance(con)
    report["amendment"] = ("v2 2026-08-17: relative-proxy M×3 panel is a "
                           "positive delivery (REQ-BJ09); strict-causal "
                           "historical support stays zero and is never pooled")
    report["execution_scope"] = "historical_proxy_only" if args.proxy_only else "full"
    report["wall_seconds"] = round(time.time() - t0, 1)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "RECOVERABILITY_REPORT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    (out / "ISSUE_SUPPORT.csv").write_text(
        _issue_support_csv(con), encoding="utf-8"
    )
    export = export_parquet(con, out)

    print(json.dumps({"steps": steps, "report": report, "export": export},
                     indent=2, ensure_ascii=False, default=str))
    con.close()
    return 0


def _profile_xlsm(xlsm: Path) -> dict:
    import sqlite3
    con = sqlite3.connect(f"file:{xlsm}?mode=ro", uri=True)
    profile = {
        "path": str(xlsm),
        "size_gb": round(xlsm.stat().st_size / 1e9, 1),
        "consensus_bucket_rows": con.execute(
            "SELECT snapshot, COUNT(*) FROM market_consensus "
            "WHERE market='euro_1x2' GROUP BY snapshot ORDER BY 2 DESC"
        ).fetchall()[:8],
        "markets": con.execute(
            "SELECT market, COUNT(*) FROM market_consensus GROUP BY market ORDER BY 2 DESC"
        ).fetchall()[:8],
        "issue_range": con.execute(
            "SELECT MIN(issue), MAX(issue), COUNT(DISTINCT issue), COUNT(*) "
            "FROM matches WHERE issue IS NOT NULL"
        ).fetchone(),
        "padding_rows": con.execute(
            "SELECT COUNT(*) FROM matches WHERE issue IS NULL OR match_idx IS NULL"
        ).fetchone()[0],
    }
    con.close()
    return profile


def _issue_support_csv(con) -> str:
    import io

    import pandas as pd

    support = issue_level_support(con)
    buf = io.StringIO()
    pd.DataFrame(support["per_issue"]).to_csv(buf, index=False)
    return buf.getvalue()


if __name__ == "__main__":
    raise SystemExit(main())
