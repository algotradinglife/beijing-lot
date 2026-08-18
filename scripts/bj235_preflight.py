#!/usr/bin/env python3
"""BJ-235 preflight/coverage: verify the deliverable is complete and consistent.

Checks:
  1. canonical SQLite exists, WAL mode, all 10 canonical tables present
  2. source_registry rows for all 8 registered sources
  3. market_observation + market_quote counts > 0 for STRICT_CAUSAL sources
  4. as_of_selection complete rows exist; no probability rows joined to settlement
  5. no 0.65 quote
  6. Parquet snapshot + MANIFEST + SHA256SUMS present and hash-consistent
  7. re-run tamper self-tests (REQ-E06)
Exit 0 = ready for EV Review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CANONICAL_TABLES = (
    "source_registry", "ingestion_batch", "fixture", "market_observation",
    "market_quote", "decision_epoch", "as_of_selection", "probability_estimate",
    "settlement", "exclusion_ledger", "relative_horizon_panel",
)
REQUIRED_SOURCES = 8


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", type=Path,
                    default=ROOT / "data" / "derived" / "bj235" / "bj_sp_canonical.sqlite")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "bj235_bj_sp_timeseries_v2")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--proxy-only", action="store_true",
                    help="validate the v2 historical proxy package without replaying live sources")
    args = ap.parse_args()

    problems: list[str] = []
    ok = lambda msg: print(f"  [PASS] {msg}")  # noqa: E731
    bad = lambda msg: problems.append(msg) or print(f"  [FAIL] {msg}")  # noqa: E731

    print("== 1. canonical store ==")
    canon = args.canonical
    if not canon.exists():
        bad(f"canonical db missing: {canon}")
        return _finish(problems)
    con = sqlite3.connect(f"file:{canon}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    if mode != "wal":
        bad(f"journal_mode={mode} (expected wal)")
    else:
        ok(f"journal_mode=wal ({canon.stat().st_size/1e9:.1f} GB)")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = [t for t in CANONICAL_TABLES if t not in tables]
    if missing:
        bad(f"missing tables: {missing}")
    else:
        ok(f"all {len(CANONICAL_TABLES)} canonical tables present")

    print("== 2. source registry ==")
    n_src = con.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
    if n_src >= REQUIRED_SOURCES:
        ok(f"{n_src} sources registered (>= {REQUIRED_SOURCES})")
    else:
        bad(f"only {n_src} sources registered (< {REQUIRED_SOURCES})")

    print("== 3. strict-causal observations ==")
    if args.proxy_only:
        ok("proxy-only scope: strict live-source replay intentionally not run")
    else:
        for sid in ("beidan_live_500", "bjdc_500_xml_34"):
            n = con.execute(
                "SELECT COUNT(*) FROM market_observation WHERE source_id=?", (sid,)
            ).fetchone()[0]
            nq = con.execute(
                """SELECT COUNT(*) FROM market_quote q
                   JOIN market_observation mo ON mo.observation_id=q.observation_id
                   WHERE mo.source_id=? AND q.quote_status='present'""", (sid,)
            ).fetchone()[0]
            if n > 0 and nq > 0:
                ok(f"{sid}: {n:,} observations, {nq:,} present quotes")
            else:
                bad(f"{sid}: empty ({n} obs / {nq} quotes)")

    print("== 4. as-of + probability separation ==")
    n_comp = con.execute("SELECT COUNT(*) FROM as_of_selection WHERE complete=1").fetchone()[0]
    if args.proxy_only:
        ok("proxy-only scope: strict as-of replay intentionally not run")
    elif n_comp > 0:
        ok(f"{n_comp:,} complete as-of selections")
    else:
        bad("zero complete as-of selections")
    bad_join = con.execute(
        """SELECT COUNT(*) FROM probability_estimate pe
           JOIN settlement s ON s.fixture_id=pe.fixture_id"""
    ).fetchone()[0]
    if bad_join == 0:
        ok("probability_estimate physically separate from settlement")
    else:
        bad(f"{bad_join} probability rows joined to settlement")

    print("== 5. no 0.65 in inference ==")
    n065 = con.execute("SELECT COUNT(*) FROM market_quote WHERE decimal_odds=0.65").fetchone()[0]
    n065p = con.execute("SELECT COUNT(*) FROM probability_estimate WHERE probability=0.65").fetchone()[0]
    n065panel = con.execute(
        "SELECT COUNT(*) FROM relative_horizon_panel WHERE decimal_odds=0.65"
    ).fetchone()[0]
    if n065 == 0 and n065p == 0 and n065panel == 0:
        ok("no 0.65 in quotes/probabilities/panel")
    else:
        bad(f"0.65 present: quotes={n065} probs={n065p} panel={n065panel}")

    print("== 5b. relative-horizon panel (REQ-BJ09) ==")
    n_panel = con.execute("SELECT COUNT(*) FROM relative_horizon_panel").fetchone()[0]
    n_present = con.execute(
        "SELECT COUNT(*) FROM relative_horizon_panel WHERE availability='present'"
    ).fetchone()[0]
    n_issues = con.execute(
        "SELECT COUNT(DISTINCT issue_code) FROM relative_horizon_panel"
    ).fetchone()[0]
    if n_panel > 0 and n_present > 0:
        ok(f"panel {n_panel:,} cells ({n_present:,} present) across {n_issues} issues")
    else:
        bad(f"panel empty: cells={n_panel} present={n_present} issues={n_issues}")
    try:
        from src.bj_sp_timeseries.panel import relative_horizon_view_df, verify_panel_provenance

        view = relative_horizon_view_df(con)
        if set(view.columns).isdisjoint({"winning_sp", "settled_at_utc"}):
            ok(f"relative_horizon_view M×3 settlement-free ({len(view):,} rows)")
        else:
            bad("relative_horizon_view leaks settlement columns")
        if bool(view["availability"].isin(["present", "missing"]).all()):
            ok("availability mask is explicit")
        else:
            bad("invalid availability values")
        provenance = verify_panel_provenance(con)
        if provenance["mismatches"] == 0:
            ok(f"panel provenance hashes verify ({provenance['checked']:,} rows)")
        else:
            bad(f"{provenance['mismatches']} panel provenance mismatches")
    except Exception as exc:
        bad(f"relative_horizon_view error: {exc}")

    print("== 6. package artifacts ==")
    out = args.out
    for f in ("MANIFEST.json", "SHA256SUMS.json", "RECOVERABILITY_REPORT.json",
              "ISSUE_SUPPORT.csv", "tables/relative_horizon_view.parquet"):
        if (out / f).exists():
            ok(f"{f} present")
        else:
            bad(f"{f} missing")
    if (out / "SHA256SUMS.json").exists():
        sums = json.loads((out / "SHA256SUMS.json").read_text(encoding="utf-8"))
        mismatches = 0
        for rel, want in sums.items():
            fp = out / rel
            if not fp.exists():
                mismatches += 1
                continue
            h = hashlib.sha256(fp.read_bytes()).hexdigest()
            if h != want:
                mismatches += 1
        if mismatches == 0:
            ok(f"SHA256SUMS consistent ({len(sums)} files)")
        else:
            bad(f"{mismatches} hash mismatches in SHA256SUMS")

    print("== 7. tamper self-tests ==")
    r = subprocess.run(
        [args.python, "-m", "pytest", "tests/test_bj235_asof.py", "tests/test_bj235_tamper.py",
         "tests/test_bj235_panel.py", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True, timeout=600,
    )
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    if r.returncode == 0:
        ok("pytest asof+tamper green")
    else:
        bad(f"pytest failed ({r.returncode}): {' | '.join(tail)}")

    con.close()
    return _finish(problems)


def _finish(problems: list[str]) -> int:
    if problems:
        print(f"\nPREFLIGHT FAIL — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nPREFLIGHT PASS — ready for EV Review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
