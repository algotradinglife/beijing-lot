#!/usr/bin/env python3
"""Rebuild #145 derived analyses from the completed indexed settlement stage."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import statistics
import sys
from decimal import Decimal
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "bj145_rebuild_runner",
    Path(__file__).with_name("settle_bj145_ticket_allocation_gate_b.py"),
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

LOIO_FIELDS = (
    "scope",
    "scope_value",
    "arm_id",
    "weight_source",
    "mechanism",
    "sampling_role",
    "cap",
    "M",
    "seed",
    "support_issue_count",
    "removed_issue_count",
    "leave_one_roi_min",
    "leave_one_roi_min_issue_instance",
    "leave_one_roi_p50",
    "leave_one_roi_max",
    "leave_one_roi_max_issue_instance",
    "leave_one_positive_count",
    "leave_one_nonnegative_count",
    "sensitivity_rule",
)
EXCLUDE_FIELDS = (
    "scope",
    "scope_value",
    "arm_id",
    "weight_source",
    "mechanism",
    "sampling_role",
    "cap",
    "M",
    "seed",
    "support_issue_count",
    "largest_issue_instance",
    "largest_issue_gross_yuan",
    "no_tax_roi",
    "no_tax_roi_excluding_largest",
    "no_tax_roi_delta_excluding_largest_vs_full",
    "sensitivity_rule",
)
COHORT_ARMS = ("PRIMARY_NO_GATE_K4", "SECONDARY_ESP300_GM290_K8")


def rows_for(conn: sqlite3.Connection, config: str) -> list[dict[str, str]]:
    rows = [
        json.loads(v[0])
        for v in conn.execute(
            "SELECT payload FROM issue_rows WHERE config=? ORDER BY year,issue_instance",
            (config,),
        )
    ]
    if len(rows) != 348:
        raise RuntimeError((config, len(rows)))
    return rows


def wagered(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        r
        for r in rows
        if r["settlement_status"] == "SETTLED"
        and MOD.decimal(r["planned_stake_yuan"], "stake") > 0
    ]


def roi(rows: list[dict[str, str]]) -> Decimal | None:
    support = wagered(rows)
    stake = sum(
        (MOD.decimal(r["planned_stake_yuan"], "stake") for r in support), Decimal(0)
    )
    net = sum((MOD.decimal(r["pre_tax_net_yuan"], "net") for r in support), Decimal(0))
    return net / stake if stake else None


def sensitivity(
    rows: list[dict[str, str]],
) -> tuple[int, Decimal | None, str, Decimal | None, Decimal | None, str, int, int]:
    support = wagered(rows)
    candidates = [
        (row["issue_instance"], roi(support[:index] + support[index + 1 :]))
        for index, row in enumerate(support)
    ]
    candidates = [(issue, value) for issue, value in candidates if value is not None]
    if not candidates:
        return len(support), None, "", None, None, "", 0, 0
    minimum = min(candidates, key=lambda item: (item[1], item[0]))
    maximum = min(candidates, key=lambda item: (-item[1], item[0]))
    values = [value for _, value in candidates]
    return (
        len(support),
        minimum[1],
        minimum[0],
        Decimal(str(statistics.median(float(value) for value in values))),
        maximum[1],
        maximum[0],
        sum(value > 0 for value in values),
        sum(value >= 0 for value in values),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", type=Path)
    ap.add_argument(
        "--package",
        type=Path,
        default=MOD.ROOT / "results" / "bj145_gate_b_outcome_settlement_v2",
    )
    args = ap.parse_args()
    conn = sqlite3.connect(args.stage / "issue_allocation_index.sqlite")
    package = args.package
    try:
        config_rows = list(
            conn.execute(
                "SELECT DISTINCT config,arm_id,weight_source,mechanism,sampling_role,cap,m_value,seed FROM issue_rows ORDER BY arm_id,weight_source,mechanism,sampling_role,cap,m_value,seed"
            )
        )
        summaries: list[dict[str, object]] = []
        payload_by_config: dict[str, list[dict[str, str]]] = {}
        for config, *_ in config_rows:
            payloads = rows_for(conn, config)
            payload_by_config[config] = payloads
            summaries.extend(
                MOD.summary(scope, value, subset)
                for scope, value, subset in MOD.grouped_scopes(payloads)
            )
        summaries.sort(
            key=lambda r: (
                r["arm_id"],
                r["weight_source"],
                r["mechanism"],
                str(r["cap"]),
                int(r["M"]),
                r["seed"],
                r["scope"],
                r["scope_value"],
            )
        )
        MOD.write_csv(
            package / "mechanism_weight_surface_summary.csv",
            MOD.SUMMARY_FIELDS,
            summaries,
        )
        full_index = {
            (r["scope"], r["scope_value"], r["arm_id"], r["weight_source"]): r
            for r in summaries
            if r["mechanism"] == "FULL_ENUMERATED"
        }
        full_deltas = []
        for r in summaries:
            if r["mechanism"] == "FULL_ENUMERATED":
                continue
            b = full_index[
                (r["scope"], r["scope_value"], r["arm_id"], r["weight_source"])
            ]
            b = {
                **b,
                "full_unique_ticket_coverage": b["unique_ticket_coverage"],
                "full_duplicate_ticket_ratio": b["duplicate_ticket_ratio"],
            }

            def d(field):
                return (
                    MOD.ratio(Decimal(r[field]) - Decimal(b[field]))
                    if r[field] and b[field]
                    else ""
                )

            full_deltas.append(
                {
                    "scope": r["scope"],
                    "scope_value": r["scope_value"],
                    "arm_id": r["arm_id"],
                    "weight_source": r["weight_source"],
                    "sampling_role": r["sampling_role"],
                    "mechanism": r["mechanism"],
                    "cap": r["cap"],
                    "M": r["M"],
                    "seed": r["seed"],
                    "baseline_mechanism": "FULL_ENUMERATED",
                    "baseline_M": MOD.FULL_TICKETS,
                    "support_issue_count": r["settled_issue_count"],
                    "no_tax_roi": r["no_tax_roi"],
                    "full_no_tax_roi": b["no_tax_roi"],
                    "no_tax_roi_delta": d("no_tax_roi"),
                    "tax_adjusted_roi": r["tax_adjusted_roi"],
                    "full_tax_adjusted_roi": b["tax_adjusted_roi"],
                    "tax_adjusted_roi_delta": d("tax_adjusted_roi"),
                    "coverage_hit_rate": r["coverage_hit_rate"],
                    "full_coverage_hit_rate": b["coverage_hit_rate"],
                    "coverage_hit_rate_delta": d("coverage_hit_rate"),
                    "unique_ticket_coverage": r["unique_ticket_coverage"],
                    "full_unique_ticket_coverage": b["full_unique_ticket_coverage"],
                    "unique_ticket_coverage_delta": d("unique_ticket_coverage"),
                    "duplicate_ticket_ratio": r["duplicate_ticket_ratio"],
                    "full_duplicate_ticket_ratio": b["full_duplicate_ticket_ratio"],
                    "duplicate_ticket_ratio_delta": d("duplicate_ticket_ratio"),
                    "wagered_support_issue_count": r["wagered_support_issue_count"],
                    "full_wagered_support_issue_count": b[
                        "wagered_support_issue_count"
                    ],
                    "coverage_denominator_issue_count": r[
                        "coverage_denominator_issue_count"
                    ],
                    "full_coverage_denominator_issue_count": b[
                        "coverage_denominator_issue_count"
                    ],
                    "coverage_denominator_rule": r["coverage_denominator_rule"],
                    "comparison_rule": "same arm/weight/scope and exact frozen issue support; FULL stake is the K=2187 economic control",
                }
            )
        MOD.write_csv(
            package / "full_control_deltas.csv", MOD.FULL_DELTA_FIELDS, full_deltas
        )
        all_summary = {
            (
                r["arm_id"],
                r["weight_source"],
                r["mechanism"],
                r["sampling_role"],
                r["cap"],
                r["M"],
                r["seed"],
            ): r
            for r in summaries
            if r["scope"] == "ALL"
        }
        pair_rows = []
        mechanisms = (
            "WR_DUPLICATE_STAKE",
            "WOR_DISTINCT",
            "RESIDUAL_SYSTEMATIC",
            "CAPPED_REPEAT",
            "DETERMINISTIC_TOP_MASS",
        )
        m_grid = tuple(range(16, 257, 16)) + (512, 1024, 1458, 2187)
        for arm in COHORT_ARMS:
            for weight in MOD.WEIGHT_SOURCES:
                for m in m_grid:
                    variants = []
                    for mech in mechanisms:
                        caps = (
                            ("NA",) if mech != "CAPPED_REPEAT" else ("1", "2", "4", "8")
                        )
                        seeds = (
                            ("NA",)
                            if mech not in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"}
                            else ("137001", "137002", "137003")
                        )
                        for cap in caps:
                            for seed in seeds:
                                r = next(
                                    v
                                    for k, v in all_summary.items()
                                    if k[0] == arm
                                    and k[1] == weight
                                    and k[2] == mech
                                    and k[4] == cap
                                    and int(k[5]) == m
                                    and k[6] == seed
                                )
                                variants.append((mech, cap, seed, r))
                    for left, right in __import__("itertools").combinations(
                        variants, 2
                    ):
                        if left[2] != "NA" and right[2] != "NA" and left[2] != right[2]:
                            continue
                        left_row, right_row = left[3], right[3]
                        pair_rows.append(
                            {
                                "scope": "ALL",
                                "scope_value": "ALL",
                                "arm_id": arm,
                                "weight_source": weight,
                                "M": m,
                                "left_mechanism": left[0],
                                "left_cap": left[1],
                                "left_seed": left[2],
                                "right_mechanism": right[0],
                                "right_cap": right[1],
                                "right_seed": right[2],
                                "support_issue_count": min(
                                    int(left_row["settled_issue_count"]),
                                    int(right_row["settled_issue_count"]),
                                ),
                                "left_no_tax_roi": left_row["no_tax_roi"],
                                "right_no_tax_roi": right_row["no_tax_roi"],
                                "no_tax_roi_delta_left_minus_right": MOD.ratio(
                                    Decimal(left_row["no_tax_roi"])
                                    - Decimal(right_row["no_tax_roi"])
                                )
                                if left_row["no_tax_roi"] and right_row["no_tax_roi"]
                                else "",
                                "left_tax_adjusted_roi": left_row["tax_adjusted_roi"],
                                "right_tax_adjusted_roi": right_row["tax_adjusted_roi"],
                                "tax_adjusted_roi_delta_left_minus_right": MOD.ratio(
                                    Decimal(left_row["tax_adjusted_roi"])
                                    - Decimal(right_row["tax_adjusted_roi"])
                                )
                                if left_row["tax_adjusted_roi"]
                                and right_row["tax_adjusted_roi"]
                                else "",
                                "coverage_hit_rate_delta_left_minus_right": MOD.ratio(
                                    Decimal(left_row["coverage_hit_rate"])
                                    - Decimal(right_row["coverage_hit_rate"])
                                ),
                                "duplicate_ratio_delta_left_minus_right": MOD.ratio(
                                    Decimal(left_row["duplicate_ticket_ratio"] or 0)
                                    - Decimal(right_row["duplicate_ticket_ratio"] or 0)
                                ),
                                "comparison_rule": "equal arm/weight/M and issue-level stake; deterministic cells are compared against each frozen randomized seed",
                            }
                        )
        MOD.write_csv(
            package / "mechanism_pairwise_deltas.csv", MOD.PAIR_FIELDS, pair_rows
        )
        weight_rows = []
        for arm in COHORT_ARMS:
            keys = {
                (r["mechanism"], r["sampling_role"], r["cap"], r["M"], r["seed"])
                for r in summaries
                if r["scope"] == "ALL" and r["mechanism"] != "FULL_ENUMERATED"
            }
            for mech, role, cap, m, seed in keys:
                for lw, rw in __import__("itertools").combinations(
                    MOD.WEIGHT_SOURCES, 2
                ):
                    left_row, right_row = (
                        all_summary[(arm, lw, mech, role, cap, m, seed)],
                        all_summary[(arm, rw, mech, role, cap, m, seed)],
                    )
                    weight_rows.append(
                        {
                            "scope": "ALL",
                            "scope_value": "ALL",
                            "arm_id": arm,
                            "weight_source": f"{lw}_VS_{rw}",
                            "M": m,
                            "left_mechanism": mech,
                            "left_cap": cap,
                            "left_seed": seed,
                            "right_mechanism": mech,
                            "right_cap": cap,
                            "right_seed": seed,
                            "support_issue_count": min(
                                int(left_row["settled_issue_count"]),
                                int(right_row["settled_issue_count"]),
                            ),
                            "left_no_tax_roi": left_row["no_tax_roi"],
                            "right_no_tax_roi": right_row["no_tax_roi"],
                            "no_tax_roi_delta_left_minus_right": MOD.ratio(
                                Decimal(left_row["no_tax_roi"])
                                - Decimal(right_row["no_tax_roi"])
                            )
                            if left_row["no_tax_roi"] and right_row["no_tax_roi"]
                            else "",
                            "left_tax_adjusted_roi": left_row["tax_adjusted_roi"],
                            "right_tax_adjusted_roi": right_row["tax_adjusted_roi"],
                            "tax_adjusted_roi_delta_left_minus_right": MOD.ratio(
                                Decimal(left_row["tax_adjusted_roi"])
                                - Decimal(right_row["tax_adjusted_roi"])
                            )
                            if left_row["tax_adjusted_roi"]
                            and right_row["tax_adjusted_roi"]
                            else "",
                            "coverage_hit_rate_delta_left_minus_right": MOD.ratio(
                                Decimal(left_row["coverage_hit_rate"])
                                - Decimal(right_row["coverage_hit_rate"])
                            ),
                            "duplicate_ratio_delta_left_minus_right": MOD.ratio(
                                Decimal(left_row["duplicate_ticket_ratio"] or 0)
                                - Decimal(right_row["duplicate_ticket_ratio"] or 0)
                            ),
                            "comparison_rule": "equal arm/mechanism/cap/M/seed and issue-level stake; weight-source effect only",
                        }
                    )
        MOD.write_csv(
            package / "weight_pairwise_deltas.csv", MOD.PAIR_FIELDS, weight_rows
        )
        # Explicit leave-one-issue-out summaries and pre-tax largest-issue removal.
        loio = []
        excl = []
        for r in summaries:
            if r["scope"] != "ALL":
                continue
            config = "|".join(
                (
                    r["arm_id"],
                    r["weight_source"],
                    r["mechanism"],
                    r["sampling_role"],
                    r["cap"],
                    str(r["M"]),
                    r["seed"],
                )
            )
            payloads = payload_by_config[config]
            support = wagered(payloads)
            n, lo, lo_issue, med, hi, hi_issue, pos, nonneg = sensitivity(support)
            loio.append(
                {
                    "scope": "ALL",
                    "scope_value": "ALL",
                    "arm_id": r["arm_id"],
                    "weight_source": r["weight_source"],
                    "mechanism": r["mechanism"],
                    "sampling_role": r["sampling_role"],
                    "cap": r["cap"],
                    "M": r["M"],
                    "seed": r["seed"],
                    "support_issue_count": n,
                    "removed_issue_count": n,
                    "leave_one_roi_min": MOD.ratio(lo),
                    "leave_one_roi_min_issue_instance": lo_issue,
                    "leave_one_roi_p50": MOD.ratio(med),
                    "leave_one_roi_max": MOD.ratio(hi),
                    "leave_one_roi_max_issue_instance": hi_issue,
                    "leave_one_positive_count": pos,
                    "leave_one_nonnegative_count": nonneg,
                    "sensitivity_rule": "each settled positive-stake issue removed once; unavailable/no-bet rows excluded; lexicographically smallest issue_instance retained for tied extrema",
                }
            )
            largest = (
                max(
                    support,
                    key=lambda x: (
                        MOD.decimal(x["gross_pre_tax_yuan"], "gross"),
                        -int(x["issue"]),
                    ),
                )
                if support
                else None
            )
            reduced = [x for x in support if x is not largest] if largest else support
            eroi = roi(reduced)
            gross = (
                MOD.decimal(largest["gross_pre_tax_yuan"], "gross")
                if largest
                else Decimal(0)
            )
            full = full_index[("ALL", "ALL", r["arm_id"], r["weight_source"])]
            fconfig = "|".join(
                (
                    full["arm_id"],
                    full["weight_source"],
                    full["mechanism"],
                    full["sampling_role"],
                    full["cap"],
                    str(full["M"]),
                    full["seed"],
                )
            )
            frows = payload_by_config[fconfig]
            f_support = wagered(frows)
            f_reduced = (
                [
                    x
                    for x in f_support
                    if x["issue_instance"] != largest["issue_instance"]
                ]
                if largest
                else f_support
            )
            f_roi = roi(f_reduced)
            excl.append(
                {
                    "scope": "ALL",
                    "scope_value": "ALL",
                    "arm_id": r["arm_id"],
                    "weight_source": r["weight_source"],
                    "mechanism": r["mechanism"],
                    "sampling_role": r["sampling_role"],
                    "cap": r["cap"],
                    "M": r["M"],
                    "seed": r["seed"],
                    "support_issue_count": n,
                    "largest_issue_instance": largest["issue_instance"]
                    if largest
                    else "",
                    "largest_issue_gross_yuan": MOD.money(gross),
                    "no_tax_roi": r["no_tax_roi"],
                    "no_tax_roi_excluding_largest": MOD.ratio(eroi),
                    "no_tax_roi_delta_excluding_largest_vs_full": MOD.ratio(
                        eroi - f_roi
                    )
                    if eroi is not None and f_roi is not None
                    else "",
                    "sensitivity_rule": "remove the largest gross-pre-tax issue in this matched configuration; compare pre-tax ROI with the matched FULL control",
                }
            )
        MOD.write_csv(package / "leave_one_issue_out_summary.csv", LOIO_FIELDS, loio)
        MOD.write_csv(package / "largest_issue_exclusion.csv", EXCLUDE_FIELDS, excl)
        print(
            json.dumps(
                {
                    "configs": len(config_rows),
                    "summaries": len(summaries),
                    "pair_rows": len(pair_rows),
                    "weight_rows": len(weight_rows),
                    "loio_rows": len(loio),
                    "exclude_rows": len(excl),
                }
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
