#!/usr/bin/env python3
"""Thin entry point: offline diagnostics for the #493 Nowscore 3in1 probe.

Reusable logic lives in src/n7_493_probe_analysis.py. Importing this script does
nothing; it reads only already-saved raw bytes and issues no request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.n7_493_probe_analysis import (  # noqa: E402
    YEAR_ASSUMED, build_diagnostic_rows, parse_company_links, selected_company_id,
    write_diagnostics_csv,
)

OUT = ROOT / "results/data_collection/n7_493_3in1_probe_v1"
EPOCH_LOCAL = "2026-08-14 20:00"
VIEWS = {
    "base_no_company": ("companyid=3", "page-anchored default (net3 selected)"),
    "company_1": ("companyid=1", "explicit request"),
    "company_0": ("companyid=0", "UNLISTED probe value, not an identified id"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    out_dir = args.out
    rows = build_diagnostic_rows(VIEWS, out_dir / "raw", EPOCH_LOCAL)
    write_diagnostics_csv(rows, out_dir / "diagnostics.csv")

    base_html = (out_dir / "raw" / "base_no_company.html").read_text("utf-8", "replace")
    anchor = selected_company_id(base_html)
    links = parse_company_links(base_html)
    from src.n7_493_probe import count_historical_attempts, load_ledger
    ledger = load_ledger(out_dir / "requests.jsonl")
    # Reporting only: the delivered ledger is historical evidence, so it is
    # counted by unique attempt id rather than validated for dispatch.
    attempts_total = count_historical_attempts(ledger)
    provenance = json.loads((out_dir / "ledger_provenance.json").read_text(encoding="utf-8"))
    default = {r["market"]: r for r in rows if r["view"] == "companyid=3"}

    manifest = {
        "schema": "n7_493_3in1_probe_v1_result",
        "authorised_by": "hh1985 issue #493 comment 2026-09-23T04:01:22Z",
        "sample": {"issue": "26085", "match_idx": 5,
                   "provider_match_id": "3061587",
                   "title_observed": "卡利亞里VS阿雷素",
                   "kickoff_local": "2026-08-15 00:30",
                   "decision_epoch_local": EPOCH_LOCAL},
        "top_level_requests": {
            "reconstructed": attempts_total, "authorised_max": 10,
            "hop_attempts_total": "UNVERIFIED",
            "hop_attempts_reason": ("redirect_occurrence is UNKNOWN, so the per-hop "
                                    "attempt count is not proven; one hop or several "
                                    "are both consistent with the 3 top-level records"),
            "remaining_budget": "NOT_COMPUTABLE_TREATED_AS_ZERO",
            "remaining_budget_reason": ("the budget is consumed per hop attempt; the "
                                        "numerator is unproven, so no budget may be "
                                        "treated as still available"),
            "ledger": "requests.jsonl",
            "counted_as": ("unique attempt ids in a reconstructed historical ledger; "
                           "not dispatchable"),
            "provenance": "ledger_provenance.json"},
        "wall_clock": {
            "lower_bound_sec": provenance["wall_sec_lower_bound"],
            "inferred_sec": provenance["wall_sec_inferred"],
            "authorised_max_sec": 300.0,
            "measured_exactly": False,
            "upper_limit_compliance": provenance["upper_limit_compliance"],
        },
        "default_view_identity": {
            "companyid": anchor,
            "company_label": dict(links).get(anchor),
            "anchor_evidence": ('raw/base_no_company.html assigns className="selected" '
                                f'to net{anchor}, and net{anchor} maps to '
                                f'?companyid={anchor}'),
            "retraction": ("the earlier claim that the default view was an unlabelled "
                           "aggregate, and the density comparison against a single "
                           "bookmaker, are retracted"),
        },
        "market_label_evidence": {
            "company_selector_entries": len(links),
            "average_string_occurrences": base_html.count("平均"),
            "selector_has_average_entry": False,
            "conclusion": ("this page exposes no euro-average entry; that does not "
                           "establish that no average history exists site-wide"),
        },
        "probe_value_deviation": {
            "companyid": 0, "in_selector": False,
            "deviation": ("requesting companyid=0 departed from the reviewed "
                          "requirement not to guess an average cid; it was a probe "
                          "value with no page basis"),
            "evidential_weight": ("its empty response is NOT evidence about averages "
                                  "and must not be cited as such"),
        },
        "verdicts": {
            "euro_average_history": "NOT_ESTABLISHED",
            "euro_average_history_scope": "this page only; site-wide not determined",
            "over_under_series": "AVAILABLE_PER_COMPANY",
            "timezone": "UNDECIDED_DIAGNOSTIC_ONLY",
            "year": f"ASSUMED_{YEAR_ASSUMED}_DIAGNOSTIC_ONLY",
        },
        "last_before_epoch_diagnostic": {
            "assumption": (f"local clock assumed UTC+8; year assumed {YEAR_ASSUMED}; "
                           "diagnostic only, not verified UTC, and not proof of "
                           "cutoff eligibility"),
            "default_view_companyid3_euro_1x2": default["euro_1x2"][
                f"last_before_epoch_ASSUMED_UTC+8_YEAR_{YEAR_ASSUMED}"],
            "default_view_companyid3_over_under": default["over_under"][
                f"last_before_epoch_ASSUMED_UTC+8_YEAR_{YEAR_ASSUMED}"],
            "note": ("the two markets show different most-recent retrospective "
                     "timestamps; this does not establish what was available before "
                     "the cutoff"),
        },
    }
    (out_dir / "diagnostics_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    lines = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                         f"{path.relative_to(out_dir)}")
    (out_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n")

    print("top_level_requests", attempts_total, "hop_attempts", "UNVERIFIED",
          "| wall lower bound", provenance["wall_sec_lower_bound"],
          "| upper-limit compliance", provenance["upper_limit_compliance"])
    print("default view -> companyid", anchor, dict(links).get(anchor))
    for row in rows:
        print("  %-12s %-15s total=%-4d prematch=%-3d last=%s"
              % (row["view"], row["market"], row["rows_total"],
                 row["rows_prematch"],
                 row[f"last_before_epoch_ASSUMED_UTC+8_YEAR_{YEAR_ASSUMED}"] or "-"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
