#!/usr/bin/env python3
"""Exact Gate C settlement for the accepted #76 Gate B v2 freeze.

The calculator intentionally treats every Gate-B selection as immutable: it
does not open a modelling input, enumerate a new sequence ranking, or alter a
cutoff.  It reads results only from saved/raw official 500 completed pages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import re
import shutil
import urllib.request
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


URL = "https://zx.500.com/zqdc/kaijiang.php?playid=1&expect={issue}"
GROUPS = ("26076-G01", "26077-G01", "26079-G01", "26079-G02")
ISSUES = ("26076", "26077", "26079")
ARMS = ("V771_TOP_MASS_50", "V771_TOP_MASS_60", "V771_TOP_MASS_70", "V771_TOP_MASS_80", "SP_BAND_ONLY_2_5_4_5_CAP648")
MASS_ARMS = ARMS[:4]
FACTOR = Decimal("0.65")
TICKET = Decimal("2")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canon(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def clean(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ").strip()


def parse_page(page: bytes) -> dict[int, tuple[str, Decimal]]:
    """Use only official completed-page match index, outcome code and final SP."""
    found: dict[int, tuple[str, Decimal]] = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page.decode("gb18030"), re.I | re.S):
        cells = [clean(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)]
        if len(cells) < 10 or not cells[0].isdigit():
            continue
        code = {"胜": "3", "平": "1", "负": "0"}.get(cells[7], cells[7])
        try:
            final_sp = Decimal(cells[9])
        except Exception:
            continue
        if code in {"3", "1", "0"} and final_sp > 0:
            found[int(cells[0])] = (code, final_sp)
    if not found:
        raise RuntimeError("no positive 3/1/0 rows on completed page")
    return found


def checksum_entries(directory: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = raw.split("  ", 1)
        if not digest or not name or name in entries:
            raise RuntimeError("malformed or duplicate Gate B checksum entry")
        entries[name] = digest
    if not entries:
        raise RuntimeError("empty Gate B checksum list")
    return entries


def verify_freeze(freeze: Path) -> dict[str, str]:
    entries = checksum_entries(freeze)
    actual = {name: sha256(freeze / name) for name in entries}
    if actual != entries:
        raise RuntimeError("accepted Gate B v2 checksum verification failed")
    manifest = json.loads((freeze / "manifest.json").read_text(encoding="utf-8"))
    if tuple(manifest["group_ids"]) != GROUPS or manifest["group_count"] != 4 or manifest["leg_count"] != 28:
        raise RuntimeError("Gate B v2 identity/cardinality mismatch")
    return {"SHA256SUMS": sha256(freeze / "SHA256SUMS"), **actual}


def get_pages(issues: tuple[str, ...], source_pages: Path | None, destination: Path) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    destination.mkdir(parents=True, exist_ok=True)
    pages: dict[str, bytes] = {}
    receipts: list[dict[str, str]] = []
    for issue in issues:
        name = f"500_completed_{issue}.html"
        if source_pages is None:
            request = urllib.request.Request(URL.format(issue=issue), headers={"User-Agent": "Mozilla/5.0", "Referer": "https://zx.500.com/zqdc/"})
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"{issue}: HTTP {response.status}")
                page = response.read()
        else:
            page = (source_pages / name).read_bytes()
        parsed = parse_page(page)
        (destination / name).write_bytes(page)
        pages[issue] = page
        receipts.append({"issue": issue, "completed_page_url": URL.format(issue=issue), "http_status": "200", "bytes": str(len(page)), "sha256": hashlib.sha256(page).hexdigest(), "positive_3way_rows": str(len(parsed)), "reproducibility": "initial retrieval uses canonical URL; rerun consumes these byte-identical saved raw pages"})
    return pages, receipts


def group_key(group_id: str) -> tuple[int, int]:
    issue, suffix = group_id.split("-G", 1)
    return int(issue), int(suffix)


def drawdown(rows: list[dict[str, str]]) -> tuple[Decimal, int]:
    cumulative = peak = worst = Decimal("0")
    streak = longest = 0
    for row in sorted(rows, key=lambda r: group_key(r["group_id"])):
        cumulative += Decimal(row["net_yuan"])
        peak = max(peak, cumulative)
        worst = max(worst, peak - cumulative)
        if row["hit"] == "YES":
            streak = 0
        else:
            streak += 1
            longest = max(longest, streak)
    return worst, longest


def aggregate(rows: list[dict[str, str]]) -> dict[str, str]:
    settled = [row for row in rows if row["settlement_status"].startswith("SETTLED")]
    selected = [row for row in settled if row["selection_status"] == "SELECTED"]
    hits = [row for row in selected if row["hit"] == "YES"]
    stake = sum((Decimal(row["stake_yuan"]) for row in selected), Decimal("0"))
    gross = sum((Decimal(row["gross_yuan"]) for row in selected), Decimal("0"))
    after = sum((Decimal(row["after_factor_yuan"]) for row in selected), Decimal("0"))
    net = sum((Decimal(row["net_yuan"]) for row in selected), Decimal("0"))
    dd, longest = drawdown(selected)
    return {"groups_total": str(len(rows)), "groups_settled": str(len(settled)), "groups_unsettled": str(len(rows) - len(settled)), "groups_selected": str(len(selected)), "groups_no_bet_empty": str(sum(row["selection_status"] == "NO_BET_EMPTY" for row in settled)), "hits": str(len(hits)), "hit_rate": f"{len(hits) / len(selected):.10f}" if selected else "NA", "stake_yuan": money(stake), "gross_yuan": money(gross), "after_factor_yuan": money(after), "net_yuan": money(net), "roi": f"{net / stake:.10f}" if stake else "NA", "max_drawdown_yuan": money(dd), "longest_loss_streak": str(longest)}


def ex_best(rows: list[dict[str, str]]) -> dict[str, str]:
    selected = [row for row in rows if row["settlement_status"] == "SETTLED" and row["selection_status"] == "SELECTED"]
    if not selected:
        return {"selected_groups": "0", "excluded_group_id": "", "excluded_after_factor_yuan": "", "roi_excluding_best_payout": "NA", "net_excluding_best_payout_yuan": "0.00"}
    remove = max(selected, key=lambda row: (Decimal(row["after_factor_yuan"]), group_key(row["group_id"])))
    remaining = [row for row in selected if row is not remove]
    stake = sum((Decimal(row["stake_yuan"]) for row in remaining), Decimal("0"))
    net = sum((Decimal(row["net_yuan"]) for row in remaining), Decimal("0"))
    return {"selected_groups": str(len(selected)), "excluded_group_id": remove["group_id"], "excluded_after_factor_yuan": remove["after_factor_yuan"], "roi_excluding_best_payout": f"{net / stake:.10f}" if stake else "NA", "net_excluding_best_payout_yuan": money(net)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, default=Path("results/bj76_gateb_preoutcome_freeze_v2"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-pages", type=Path, help="use source_pages from a first run for deterministic recomputation")
    args = parser.parse_args()
    freeze, output = args.freeze.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit(f"refuse to overwrite output: {output}")
    verified = verify_freeze(freeze)

    summaries = list(csv.DictReader((freeze / "arm_summary.csv").open(encoding="utf-8", newline="")))
    ranks = list(csv.DictReader((freeze / "sequence_rankings.csv").open(encoding="utf-8", newline="")))
    bands = list(csv.DictReader((freeze / "sp_band_selected_sequences.csv").open(encoding="utf-8", newline="")))
    vectors = json.loads((freeze / "selected_input_vectors.json").read_text(encoding="utf-8"))["legs"]
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for leg in vectors:
        by_group[leg["group_id"]].append(leg)
    if tuple(by_group) != GROUPS or any(len(legs) != 7 for legs in by_group.values()):
        raise RuntimeError("frozen leg group set/cardinality changed")
    for legs in by_group.values():
        legs.sort(key=lambda leg: leg["leg_no"])
    rank_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ranks:
        rank_by_group[row["group_id"]].append(row)
    if set(rank_by_group) != set(GROUPS) or any(len(rows) != 2187 for rows in rank_by_group.values()):
        raise RuntimeError("frozen rankings changed")
    for rows in rank_by_group.values():
        rows.sort(key=lambda row: int(row["rank"]))
    selected: dict[tuple[str, str], tuple[int, Decimal, str]] = {}
    for row in summaries:
        if row["group_id"] not in GROUPS or row["arm"] not in ARMS:
            continue
        selected[(row["group_id"], row["arm"])] = (int(row["selected_sequences"]), Decimal(row["probability_mass"]), row["status"])
    if set(selected) != {(group_id, arm) for group_id in GROUPS for arm in ARMS}:
        raise RuntimeError("accepted arm summary does not bind all four groups and five arms")
    band_codes: dict[str, set[str]] = defaultdict(set)
    for row in bands:
        band_codes[row["group_id"]].add(row["codes"])
    for group_id in GROUPS:
        frozen_k, _, status = selected[(group_id, ARMS[-1])]
        if frozen_k != len(band_codes[group_id]) or (status == "NO_BET_EMPTY") != (frozen_k == 0):
            raise RuntimeError("SP-band selection differs from accepted freeze")

    output.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve(), output / "settle_bj76_gatec_outcome_settlement.py")
    pages, page_receipt = get_pages(ISSUES, args.source_pages.resolve() if args.source_pages else None, output / "source_pages")
    official = {issue: parse_page(page) for issue, page in pages.items()}

    leg_rows: list[dict[str, str]] = []
    truth: dict[str, tuple[str, Decimal, bool]] = {}
    retention_rows: list[dict[str, str]] = []
    for group_id in GROUPS:
        realized: list[str] = []
        final_product = Decimal("1")
        complete = True
        for leg in by_group[group_id]:
            outcome = official[str(leg["issue"])].get(int(leg["match_idx"]))
            if outcome is None:
                complete = False
                leg_rows.append({"group_id": group_id, "issue": str(leg["issue"]), "leg_no": str(leg["leg_no"]), "match_id": leg["match_id"], "match_idx": str(leg["match_idx"]), "final_status": "MISSING_RESULT_CODE_OR_POSITIVE_WINNING_SP", "actual_code": "", "final_winning_sp": "", "completed_page_url": URL.format(issue=leg["issue"]), "source_page_sha256": hashlib.sha256(pages[str(leg["issue"])]).hexdigest()})
                continue
            code, final_sp = outcome
            quoted = Decimal(str(leg["handicap_quotes"][code]))
            leg_rows.append({"group_id": group_id, "issue": str(leg["issue"]), "leg_no": str(leg["leg_no"]), "match_id": leg["match_id"], "match_idx": str(leg["match_idx"]), "final_status": "SETTLED", "actual_code": code, "final_winning_sp": decimal_text(final_sp), "completed_page_url": URL.format(issue=leg["issue"]), "source_page_sha256": hashlib.sha256(pages[str(leg["issue"])]).hexdigest()})
            retention_rows.append({"group_id": group_id, "issue": str(leg["issue"]), "leg_no": str(leg["leg_no"]), "match_id": leg["match_id"], "actual_code": code, "prebet_selected_quote": decimal_text(quoted), "final_winning_sp": decimal_text(final_sp), "final_over_prebet_ratio": decimal_text(final_sp / quoted), "prebet_quote_ge_5": "YES" if quoted >= 5 else "NO", "final_sp_ge_5": "YES" if final_sp >= 5 else "NO"})
            realized.append(code)
            final_product *= final_sp
        truth[group_id] = ("".join(realized) if complete else "", final_product if complete else Decimal("0"), complete)
    if len(leg_rows) != 28:
        raise RuntimeError("expected exactly 28 frozen legs")

    group_rows: list[dict[str, str]] = []
    for group_id in GROUPS:
        issue = group_id.split("-", 1)[0]
        realized, final_product, complete = truth[group_id]
        winner_rank = next((int(row["rank"]) for row in rank_by_group[group_id] if row["codes"] == realized), None) if complete else None
        for arm in ARMS:
            frozen_k, mass, status = selected[(group_id, arm)]
            if not complete:
                hit = "NA"
                stake = gross = after = net = Decimal("0")
                settlement_status = "UNAVAILABLE_INCOMPLETE_GROUP"
            elif status == "NO_BET_EMPTY":
                hit = "NA"
                stake = gross = after = net = Decimal("0")
                settlement_status = "SETTLED_NO_BET_EMPTY"
            else:
                is_hit = realized in band_codes[group_id] if arm == ARMS[-1] else bool(winner_rank and winner_rank <= frozen_k)
                hit = "YES" if is_hit else "NO"
                stake = TICKET * frozen_k
                gross = TICKET * final_product if is_hit else Decimal("0")
                after = FACTOR * gross
                net = after - stake
                settlement_status = "SETTLED"
            group_rows.append({"group_id": group_id, "issue": issue, "arm": arm, "selection_status": status, "K_frozen_output": str(frozen_k), "frozen_probability_mass": decimal_text(mass), "settlement_status": settlement_status, "realized_sequence": realized, "winning_sequence_rank_frozen_q": str(winner_rank or ""), "hit": hit, "final_winning_sp_product": decimal_text(final_product) if complete else "", "stake_yuan": money(stake), "gross_yuan": money(gross), "after_factor_yuan": money(after), "net_yuan": money(net), "settlement_factor_once": "0.65"})
    group_rows.sort(key=lambda row: (group_key(row["group_id"]), ARMS.index(row["arm"])))

    aggregate_rows: list[dict[str, str]] = []
    sensitivity_rows: list[dict[str, str]] = []
    for arm in ARMS:
        rows = [row for row in group_rows if row["arm"] == arm]
        aggregate_rows.append({"arm": arm, **aggregate(rows)})
        sensitivity_rows.append({"arm": arm, **ex_best(rows)})
    curve_rows: list[dict[str, str]] = []
    for group_id in GROUPS:
        previous_k = 0
        previous_mass = Decimal("0")
        previous_hit = False
        for arm in MASS_ARMS:
            row = next(row for row in group_rows if row["group_id"] == group_id and row["arm"] == arm)
            hit = row["hit"] == "YES"
            curve_rows.append({"group_id": group_id, "issue": row["issue"], "arm": arm, "K_frozen_output": row["K_frozen_output"], "frozen_probability_mass": row["frozen_probability_mass"], "marginal_K_vs_prior_mass_arm": str(int(row["K_frozen_output"]) - previous_k), "marginal_mass_vs_prior_mass_arm": decimal_text(Decimal(row["frozen_probability_mass"]) - previous_mass), "observed_coverage": row["hit"], "marginal_observed_coverage": "YES" if hit and not previous_hit else "NO", "realized_rank": row["winning_sequence_rank_frozen_q"]})
            previous_k = int(row["K_frozen_output"])
            previous_mass = Decimal(row["frozen_probability_mass"])
            previous_hit = previous_hit or hit
    regression_rows: list[dict[str, str]] = []
    for group_id in GROUPS:
        legs = [row for row in retention_rows if row["group_id"] == group_id]
        high = [row for row in legs if row["prebet_quote_ge_5"] == "YES"]
        avg_ratio = (sum((Decimal(row["final_over_prebet_ratio"]) for row in legs), Decimal("0")) / Decimal(len(legs))) if legs else None
        regression_rows.append({"group_id": group_id, "issue": group_id.split("-", 1)[0], "legs": str(len(legs)), "realized_prebet_quote_ge_5_legs": str(len(high)), "realized_final_sp_ge_5_legs": str(sum(row["final_sp_ge_5"] == "YES" for row in legs)), "mean_final_over_prebet_ratio": decimal_text(avg_ratio) if avg_ratio is not None else "NA", "group_final_winning_sp_product": decimal_text(truth[group_id][1]) if truth[group_id][2] else "", "diagnostic_only": "YES: raw quoted-SP extremes are not a retroactive eligibility rule and SP5 is not applied"})

    write_csv(output / "source_page_receipt.csv", page_receipt, ["issue", "completed_page_url", "http_status", "bytes", "sha256", "positive_3way_rows", "reproducibility"])
    write_csv(output / "outcome_joined_leg_rows.csv", leg_rows, ["group_id", "issue", "leg_no", "match_id", "match_idx", "final_status", "actual_code", "final_winning_sp", "completed_page_url", "source_page_sha256"])
    write_csv(output / "quote_to_final_retention.csv", retention_rows, ["group_id", "issue", "leg_no", "match_id", "actual_code", "prebet_selected_quote", "final_winning_sp", "final_over_prebet_ratio", "prebet_quote_ge_5", "final_sp_ge_5"])
    group_fields = ["group_id", "issue", "arm", "selection_status", "K_frozen_output", "frozen_probability_mass", "settlement_status", "realized_sequence", "winning_sequence_rank_frozen_q", "hit", "final_winning_sp_product", "stake_yuan", "gross_yuan", "after_factor_yuan", "net_yuan", "settlement_factor_once"]
    write_csv(output / "group_arm_settlement.csv", group_rows, group_fields)
    write_csv(output / "aggregate_metrics.csv", aggregate_rows, ["arm", "groups_total", "groups_settled", "groups_unsettled", "groups_selected", "groups_no_bet_empty", "hits", "hit_rate", "stake_yuan", "gross_yuan", "after_factor_yuan", "net_yuan", "roi", "max_drawdown_yuan", "longest_loss_streak"])
    write_csv(output / "coverage_marginal_gain_curve.csv", curve_rows, ["group_id", "issue", "arm", "K_frozen_output", "frozen_probability_mass", "marginal_K_vs_prior_mass_arm", "marginal_mass_vs_prior_mass_arm", "observed_coverage", "marginal_observed_coverage", "realized_rank"])
    write_csv(output / "outlier_ex_best_payout_sensitivity.csv", sensitivity_rows, ["arm", "selected_groups", "excluded_group_id", "excluded_after_factor_yuan", "roi_excluding_best_payout", "net_excluding_best_payout_yuan"])
    write_csv(output / "raw_quote_extreme_vs_final_diagnostic.csv", regression_rows, ["group_id", "issue", "legs", "realized_prebet_quote_ge_5_legs", "realized_final_sp_ge_5_legs", "mean_final_over_prebet_ratio", "group_final_winning_sp_product", "diagnostic_only"])
    verification = {"verification": "PASS", "accepted_gate_b_freeze": freeze.name, "verified_gate_b_sha256sums": verified["SHA256SUMS"], "verified_gate_b_files": verified, "accepted_group_ids": list(GROUPS), "outcome_source": "official 500 completed issue page only; no beidan outcome/result/settlement table or prior derived outcome artifact read", "frozen_selection_rule": "K, probability mass, rankings and SP-band members are read from Gate B v2 unchanged", "economics": "gross on a hit=2*product(final winning SP); after_factor=0.65*gross; net=after_factor-stake. Factor is applied exactly once.", "sp5": "not applied; SP5 starts with #78 and has no retrospective effect here", "mass_value": "descriptive only; no model fit or selection tuning was performed"}
    (output / "preoutcome_verification.json").write_bytes(canon(verification))
    manifest = {"experiment": "BJ-N7-V771-TOPMASS-001", "stage": "GATE_C_OUTCOME_SETTLEMENT", "preoutcome_freeze_sha256sums": verified["SHA256SUMS"], "groups": list(GROUPS), "issues": list(ISSUES), "canonical_source_url_template": URL, "raw_page_hashes": {issue: hashlib.sha256(pages[issue]).hexdigest() for issue in ISSUES}, "calculator": "settle_bj76_gatec_outcome_settlement.py", "files": ["settle_bj76_gatec_outcome_settlement.py", "source_page_receipt.csv", "outcome_joined_leg_rows.csv", "quote_to_final_retention.csv", "group_arm_settlement.csv", "aggregate_metrics.csv", "coverage_marginal_gain_curve.csv", "outlier_ex_best_payout_sensitivity.csv", "raw_quote_extreme_vs_final_diagnostic.csv", "preoutcome_verification.json"], "reproducibility": "rerun with --source-pages <first-bundle>/source_pages; all files must be byte-identical"}
    (output / "manifest.json").write_bytes(canon(manifest))
    entries = [path for path in sorted(output.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"]
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.relative_to(output)}\n" for path in entries), encoding="utf-8")
    final = checksum_entries(output)
    exact = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS"}
    if set(final) != exact or any(sha256(output / name) != digest for name, digest in final.items()):
        raise RuntimeError("output SHA256SUMS lacks exact verified coverage")


if __name__ == "__main__":
    main()
