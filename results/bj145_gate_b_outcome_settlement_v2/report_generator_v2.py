#!/usr/bin/env python3
"""Generate the detailed #145 Gate-B v2 terminal research report."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def med(values) -> float:
    values = [float(value) for value in values if value not in (None, "")]
    return statistics.median(values) if values else float("nan")


def pct(value: float) -> str:
    return f"{100 * value:+.2f}%"


def yuan(value: float) -> str:
    return f"¥{value:,.2f}"


def markdown_table(headers: list[str], body: list[list[object]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
        *("| " + " | ".join(str(cell) for cell in row) + " |" for row in body),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    summary = read(package / "mechanism_weight_surface_summary.csv")
    weight_pairs = read(package / "weight_pairwise_deltas.csv")
    mechanism_pairs = read(package / "mechanism_pairwise_deltas.csv")
    bootstrap = read(package / "issue_bootstrap.csv")
    multiple = read(package / "multiple_comparison.csv")
    loio = read(package / "leave_one_issue_out_summary.csv")
    largest = read(package / "largest_issue_exclusion.csv")
    all_rows = [row for row in summary if row["scope"] == "ALL"]
    arms = ("PRIMARY_NO_GATE_K4", "SECONDARY_ESP300_GM290_K8")
    full = {
        (row["arm_id"], row["weight_source"]): row
        for row in all_rows
        if row["mechanism"] == "FULL_ENUMERATED"
    }
    lines = [
        "# #145 Gate B v2 — calibrated ticket allocation settlement",
        "",
        "This report is the terminal descriptive analysis for the immutable Gate-A v8 allocation surface. Pre-tax `no_tax_roi` is primary; per-ticket tax is secondary. Nothing in this package authorizes purchase, production, betting, or promotion.",
        "",
        "## Bindings and complete surface",
        "",
        "- Gate-A manifest: `da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c`.",
        "- Canonical outcome manifest/payload: `fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc` / `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`.",
        "- Complete surface: 2 arms × 6 weights × WR/WOR/residual/capped/top-mass/FULL mechanisms × frozen cap/M/seed grid = 2,892 configurations; 63,624 ALL/YEAR/FOLD/LOYO summary rows.",
        "- The complete 2,187-code marginal atlas contains one row per configuration/code, with target mass, allocated copy frequency, delta, and actual outcome hits kept separate.",
        "- `mechanism_pairwise_deltas.csv` covers the full M grid through 512/1024/1458/2187. `leave_one_issue_out_summary.csv` and `largest_issue_exclusion.csv` provide explicit concentration sensitivities.",
        "",
        "## Correct support denominator",
        "",
        "Coverage and wager miss streak use only settled positive-stake issue rows. Gate-A no-bets and canonical-outcome-unavailable rows remain visible as separate availability counts and are never counted as misses. Drawdown is chronological cumulative tax-adjusted net over that same settled positive-stake support.",
        "",
    ]
    support_rows = []
    for arm in arms:
        full_row = full[(arm, "Q_WEIGHT")]
        qwor = next(
            row
            for row in all_rows
            if row["arm_id"] == arm
            and row["weight_source"] == "Q_WEIGHT"
            and row["mechanism"] == "WOR_DISTINCT"
            and row["M"] == "16"
            and row["seed"] == "137002"
        )
        support_rows.append(
            [
                arm,
                full_row["settled_issue_count"],
                f"{full_row['coverage_hits']}/{full_row['coverage_denominator_issue_count']}",
                pct(float(full_row["coverage_hit_rate"])),
                f"{qwor['coverage_hits']}/{qwor['coverage_denominator_issue_count']}",
                pct(float(qwor["coverage_hit_rate"])),
                full_row["unavailable_outcome_issue_count"],
                full_row["frozen_no_bet_issue_count"],
            ]
        )
    lines += markdown_table(
        [
            "arm",
            "settled support",
            "FULL hits",
            "FULL coverage",
            "Q-WOR M16 hits",
            "Q-WOR coverage",
            "outcome unavailable",
            "Gate-A no-bet",
        ],
        support_rows,
    )
    lines += [
        "",
        "The FULL regression is exactly 100% on both common settled supports, while the primary Q-WOR M16 seed 137002 correction is 13/254 = 5.1181% rather than 13/348.",
        "",
        "## FULL economic controls",
        "",
    ]
    control_rows = []
    for arm in arms:
        row = full[(arm, "Q_WEIGHT")]
        control_rows.append(
            [
                arm,
                row["settled_issue_count"],
                yuan(float(row["stake_yuan"])),
                pct(float(row["no_tax_roi"])),
                pct(float(row["tax_adjusted_roi"])),
                pct(float(row["coverage_hit_rate"])),
                row["longest_miss_streak"],
                yuan(float(row["max_drawdown_yuan"])),
            ]
        )
    lines += markdown_table(
        [
            "arm",
            "issues",
            "stake",
            "pre-tax ROI",
            "tax ROI",
            "coverage",
            "longest miss",
            "tax-net max drawdown",
        ],
        control_rows,
    )
    lines += [
        "",
        "Both exact-K FULL controls are negative. All apparent gains below are therefore interpreted as capital-allocation effects on a negative historical base, not as proof of positive expected value.",
        "",
        "## Weighting surface",
        "",
    ]
    weight_rows = []
    for arm in arms:
        for weight in (
            "MODEL_P_CAL",
            "MARKET_WF_CAL",
            "BLEND_A25",
            "BLEND_A50",
            "BLEND_A75",
            "Q_WEIGHT",
        ):
            values = [
                row
                for row in all_rows
                if row["arm_id"] == arm
                and row["weight_source"] == weight
                and row["mechanism"] != "FULL_ENUMERATED"
            ]
            weight_rows.append(
                [
                    arm,
                    weight,
                    pct(med(row["no_tax_roi"] for row in values)),
                    pct(max(float(row["no_tax_roi"]) for row in values)),
                    f"{sum(float(row['no_tax_roi']) > 0 for row in values)}/{len(values)}",
                    pct(med(row["coverage_hit_rate"] for row in values)),
                    pct(med(row["duplicate_ticket_ratio"] for row in values)),
                ]
            )
    lines += markdown_table(
        [
            "arm",
            "weight",
            "median ROI",
            "max descriptive ROI",
            "positive cells",
            "median coverage",
            "median duplicate ratio",
        ],
        weight_rows,
    )
    weight_comparators = (
        "MODEL_P_CAL",
        "MARKET_WF_CAL",
        "BLEND_A25",
        "BLEND_A50",
        "BLEND_A75",
    )
    matched_weight_rows = []
    q_weight_aggregate: dict[str, tuple[list[float], int, int, int]] = {}
    for arm in arms:
        aggregate: list[float] = []
        for comparator in weight_comparators:
            values = [
                row
                for row in weight_pairs
                if row["arm_id"] == arm
                and row["weight_source"] == f"{comparator}_VS_Q_WEIGHT"
            ]
            roi = [
                -float(row["no_tax_roi_delta_left_minus_right"]) for row in values
            ]
            coverage = [
                -float(row["coverage_hit_rate_delta_left_minus_right"])
                for row in values
            ]
            duplicate = [
                -float(row["duplicate_ratio_delta_left_minus_right"])
                for row in values
            ]
            aggregate.extend(roi)
            matched_weight_rows.append(
                [
                    arm,
                    f"Q_WEIGHT − {comparator}",
                    len(roi),
                    pct(med(roi)),
                    f"{sum(value > 0 for value in roi)}/{len(roi)}",
                    f"{sum(value < 0 for value in roi)}/{len(roi)}",
                    f"{sum(value == 0 for value in roi)}/{len(roi)}",
                    pct(med(coverage)),
                    pct(med(duplicate)),
                ]
            )
        q_weight_aggregate[arm] = (
            aggregate,
            sum(value > 0 for value in aggregate),
            sum(value < 0 for value in aggregate),
            sum(value == 0 for value in aggregate),
        )
    matched_wor_weight_rows = []
    q_wor_aggregate: dict[str, tuple[list[float], int, int, int]] = {}
    for arm in arms:
        aggregate = []
        for comparator in weight_comparators:
            values = [
                row
                for row in weight_pairs
                if row["arm_id"] == arm
                and row["weight_source"] == f"{comparator}_VS_Q_WEIGHT"
                and row["left_mechanism"] == "WOR_DISTINCT"
            ]
            roi = [
                -float(row["no_tax_roi_delta_left_minus_right"]) for row in values
            ]
            aggregate.extend(roi)
            matched_wor_weight_rows.append(
                [
                    arm,
                    f"Q_WEIGHT − {comparator}",
                    len(roi),
                    pct(med(roi)),
                    f"{sum(value > 0 for value in roi)}/{len(roi)}",
                    f"{sum(value < 0 for value in roi)}/{len(roi)}",
                    f"{sum(value == 0 for value in roi)}/{len(roi)}",
                ]
            )
        q_wor_aggregate[arm] = (
            aggregate,
            sum(value > 0 for value in aggregate),
            sum(value < 0 for value in aggregate),
            sum(value == 0 for value in aggregate),
        )
    lines += [
        "",
        "Q-based weighting creates the highest same-window peaks, especially under WOR, but the large number of tested cells and unstable concentration views prevent promotion. Blends and market/model weights do not show a uniformly superior surface.",
        "",
        "### Matched weighting attribution",
        "",
        "The all-mechanism table below holds arm, mechanism, cap, M, seed, issue support and stake fixed. Positive delta favors Q-based value weighting.",
        "",
    ]
    lines += markdown_table(
        [
            "arm",
            "matched contrast",
            "cells",
            "median pre-tax Δ",
            "Q better",
            "Q worse",
            "ties",
            "median coverage Δ",
            "median duplicate Δ",
        ],
        matched_weight_rows,
    )
    lines += [
        "",
        "The main WOR slice is the preregistered value-weighting contrast:",
        "",
    ]
    lines += markdown_table(
        ["arm", "matched WOR contrast", "cells", "median pre-tax Δ", "Q better", "Q worse", "ties"],
        matched_wor_weight_rows,
    )
    primary_q = q_weight_aggregate["PRIMARY_NO_GATE_K4"]
    secondary_q = q_weight_aggregate["SECONDARY_ESP300_GM290_K8"]
    primary_q_wor = q_wor_aggregate["PRIMARY_NO_GATE_K4"]
    secondary_q_wor = q_wor_aggregate["SECONDARY_ESP300_GM290_K8"]
    q_wor_primary_medians = [
        float(row[3].rstrip("%")) / 100
        for row in matched_wor_weight_rows
        if row[0] == "PRIMARY_NO_GATE_K4"
    ]
    q_wor_secondary_medians = [
        float(row[3].rstrip("%")) / 100
        for row in matched_wor_weight_rows
        if row[0] == "SECONDARY_ESP300_GM290_K8"
    ]
    lines += [
        "",
        f"Across all frozen mechanisms, Q_WEIGHT has a {pct(med(primary_q[0]))} primary median pre-tax delta (better/worse/tie {primary_q[1]}/{primary_q[2]}/{primary_q[3]} of {len(primary_q[0])}) and a {pct(med(secondary_q[0]))} secondary delta ({secondary_q[1]}/{secondary_q[2]}/{secondary_q[3]} of {len(secondary_q[0])}). On the main WOR slice specifically, the aggregate Q_WEIGHT delta is {pct(med(primary_q_wor[0]))} primary ({primary_q_wor[1]}/{primary_q_wor[2]}/{primary_q_wor[3]} of {len(primary_q_wor[0])}) and {pct(med(secondary_q_wor[0]))} secondary ({secondary_q_wor[1]}/{secondary_q_wor[2]}/{secondary_q_wor[3]} of {len(secondary_q_wor[0])}): a small/mixed matched lift, not a universal winner.",
        "",
        "## Mechanism, coverage, stake and gross retention",
        "",
    ]
    mech_groups: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in all_rows:
        if row["mechanism"] == "FULL_ENUMERATED":
            continue
        label = (
            row["mechanism"]
            if row["mechanism"] != "CAPPED_REPEAT"
            else f"CAPPED_REPEAT cap={row['cap']}"
        )
        mech_groups[(row["arm_id"], label)].append(row)
    mech_rows = []
    for (arm, label), values in sorted(mech_groups.items()):
        gross_retention = []
        for row in values:
            baseline = full[(arm, row["weight_source"])]
            if float(baseline["gross_pre_tax_yuan"]):
                gross_retention.append(
                    float(row["gross_pre_tax_yuan"])
                    / float(baseline["gross_pre_tax_yuan"])
                )
        mech_rows.append(
            [
                arm,
                label,
                pct(med(row["no_tax_roi"] for row in values)),
                yuan(med(row["stake_yuan"] for row in values)),
                f"{med(row['planned_draw_count'] for row in values):,.0f}",
                f"{med(row['unique_ticket_draw_count'] for row in values):,.0f}",
                f"{med(row['duplicate_ticket_draw_count'] for row in values):,.0f}",
                pct(med(row["coverage_hit_rate"] for row in values)),
                pct(med(row["capital_utilization_vs_full"] for row in values)),
                pct(med(row["unique_ticket_coverage"] for row in values)),
                pct(med(row["duplicate_ticket_ratio"] for row in values)),
                pct(med(gross_retention)),
                f"{sum(int(row['hit_ticket_count']) for row in values):,}",
                f"{sum(int(row['winning_identity_count']) for row in values):,}",
            ]
        )
    lines += markdown_table(
        [
            "arm",
            "mechanism",
            "median ROI",
            "stake",
            "draws",
            "unique draws",
            "duplicate draws",
            "coverage",
            "capital use",
            "unique ratio",
            "duplicate ratio",
            "gross retention",
            "hit tickets",
            "winning identities",
        ],
        mech_rows,
    )

    def matched_contrast(
        arm: str,
        left_mechanism: str,
        left_cap: str,
        right_mechanism: str,
        right_cap: str,
    ) -> dict[str, object]:
        values = [
            row
            for row in mechanism_pairs
            if row["arm_id"] == arm
            and row["left_mechanism"] == left_mechanism
            and row["left_cap"] == left_cap
            and row["right_mechanism"] == right_mechanism
            and row["right_cap"] == right_cap
        ]
        sign = 1.0
        if not values:
            values = [
                row
                for row in mechanism_pairs
                if row["arm_id"] == arm
                and row["left_mechanism"] == right_mechanism
                and row["left_cap"] == right_cap
                and row["right_mechanism"] == left_mechanism
                and row["right_cap"] == left_cap
            ]
            sign = -1.0
        if not values:
            raise RuntimeError(
                f"missing matched mechanism contrast: {arm}: "
                f"{left_mechanism}/{left_cap} vs {right_mechanism}/{right_cap}"
            )
        roi = [
            sign * float(row["no_tax_roi_delta_left_minus_right"])
            for row in values
        ]
        coverage = [
            sign * float(row["coverage_hit_rate_delta_left_minus_right"])
            for row in values
        ]
        duplicate = [
            sign * float(row["duplicate_ratio_delta_left_minus_right"])
            for row in values
        ]
        return {
            "cells": len(roi),
            "roi": roi,
            "roi_median": med(roi),
            "favorable": sum(value > 0 for value in roi),
            "negative": sum(value < 0 for value in roi),
            "ties": sum(value == 0 for value in roi),
            "coverage_median": med(coverage),
            "duplicate_median": med(duplicate),
        }

    contrast_specs = (
        ("WOR − WR", "WOR_DISTINCT", "NA", "WR_DUPLICATE_STAKE", "NA"),
        (
            "WR − residual",
            "WR_DUPLICATE_STAKE",
            "NA",
            "RESIDUAL_SYSTEMATIC",
            "NA",
        ),
        (
            "WOR − residual",
            "WOR_DISTINCT",
            "NA",
            "RESIDUAL_SYSTEMATIC",
            "NA",
        ),
        ("cap1 − residual", "CAPPED_REPEAT", "1", "RESIDUAL_SYSTEMATIC", "NA"),
        ("cap2 − residual", "CAPPED_REPEAT", "2", "RESIDUAL_SYSTEMATIC", "NA"),
        ("cap4 − residual", "CAPPED_REPEAT", "4", "RESIDUAL_SYSTEMATIC", "NA"),
        ("cap8 − residual", "CAPPED_REPEAT", "8", "RESIDUAL_SYSTEMATIC", "NA"),
        ("cap1 − WOR", "CAPPED_REPEAT", "1", "WOR_DISTINCT", "NA"),
        ("cap2 − WOR", "CAPPED_REPEAT", "2", "WOR_DISTINCT", "NA"),
        ("cap4 − WOR", "CAPPED_REPEAT", "4", "WOR_DISTINCT", "NA"),
        ("cap8 − WOR", "CAPPED_REPEAT", "8", "WOR_DISTINCT", "NA"),
        ("cap1 − WR", "CAPPED_REPEAT", "1", "WR_DUPLICATE_STAKE", "NA"),
        ("cap2 − WR", "CAPPED_REPEAT", "2", "WR_DUPLICATE_STAKE", "NA"),
        ("cap4 − WR", "CAPPED_REPEAT", "4", "WR_DUPLICATE_STAKE", "NA"),
        ("cap8 − WR", "CAPPED_REPEAT", "8", "WR_DUPLICATE_STAKE", "NA"),
    )
    mechanism_contrast_stats: dict[tuple[str, str], dict[str, object]] = {}
    mechanism_contrast_rows = []
    for arm in arms:
        for label, left_mechanism, left_cap, right_mechanism, right_cap in contrast_specs:
            stats = matched_contrast(
                arm,
                left_mechanism,
                left_cap,
                right_mechanism,
                right_cap,
            )
            mechanism_contrast_stats[(arm, label)] = stats
            mechanism_contrast_rows.append(
                [
                    arm,
                    label,
                    stats["cells"],
                    pct(float(stats["roi_median"])),
                    f"{stats['favorable']}/{stats['cells']}",
                    f"{stats['negative']}/{stats['cells']}",
                    f"{stats['ties']}/{stats['cells']}",
                    pct(float(stats["coverage_median"])),
                    pct(float(stats["duplicate_median"])),
                ]
            )
    lines += [
        "",
        "WOR raises distinct-code coverage relative to WR at equal M, while WR naturally retains duplicate stake. Residual and capped repeats trade duplicate concentration for closer proportional allocation; changing the cap moves exposure and concentration but does not create a cap whose result is stable across weights, seeds, years and folds.",
        "",
        "### Matched mechanism and cap attribution",
        "",
        "Every contrast holds arm, weight, M and issue-level stake fixed. Randomized comparisons also retain the frozen seed. Positive values favor the mechanism named first.",
        "",
    ]
    lines += markdown_table(
        [
            "arm",
            "matched contrast",
            "cells",
            "median pre-tax Δ",
            "first better",
            "first worse",
            "ties",
            "median coverage Δ",
            "median duplicate Δ",
        ],
        mechanism_contrast_rows,
    )
    primary_wor = mechanism_contrast_stats[("PRIMARY_NO_GATE_K4", "WOR − WR")]
    secondary_wor = mechanism_contrast_stats[
        ("SECONDARY_ESP300_GM290_K8", "WOR − WR")
    ]
    primary_wr_residual = mechanism_contrast_stats[
        ("PRIMARY_NO_GATE_K4", "WR − residual")
    ]
    secondary_wr_residual = mechanism_contrast_stats[
        ("SECONDARY_ESP300_GM290_K8", "WR − residual")
    ]
    primary_cap_wor = {
        cap: mechanism_contrast_stats[("PRIMARY_NO_GATE_K4", f"cap{cap} − WOR")]
        for cap in ("1", "2", "4", "8")
    }
    secondary_cap_wor = {
        cap: mechanism_contrast_stats[
            ("SECONDARY_ESP300_GM290_K8", f"cap{cap} − WOR")
        ]
        for cap in ("1", "2", "4", "8")
    }
    primary_cap_wr = {
        cap: mechanism_contrast_stats[("PRIMARY_NO_GATE_K4", f"cap{cap} − WR")]
        for cap in ("1", "2", "4", "8")
    }
    secondary_cap_wr = {
        cap: mechanism_contrast_stats[
            ("SECONDARY_ESP300_GM290_K8", f"cap{cap} − WR")
        ]
        for cap in ("1", "2", "4", "8")
    }
    lines += [
        "",
        f"Matched WOR−WR attribution is directionally favorable to WOR: primary median {pct(float(primary_wor['roi_median']))} with {primary_wor['favorable']}/{primary_wor['cells']} favorable cells and secondary {pct(float(secondary_wor['roi_median']))} with {secondary_wor['favorable']}/{secondary_wor['cells']}. WOR's median duplicate-ratio delta is {pct(float(primary_wor['duplicate_median']))} / {pct(float(secondary_wor['duplicate_median']))} while its settled coverage delta is {pct(float(primary_wor['coverage_median']))} / {pct(float(secondary_wor['coverage_median']))}.",
        f"WR versus residual is not common-direction evidence: primary median {pct(float(primary_wr_residual['roi_median']))} ({primary_wr_residual['favorable']}/{primary_wr_residual['cells']} favorable) versus secondary {pct(float(secondary_wr_residual['roi_median']))} ({secondary_wr_residual['favorable']}/{secondary_wr_residual['cells']} favorable), while WR adds about {pct(float(primary_wr_residual['duplicate_median']))} / {pct(float(secondary_wr_residual['duplicate_median']))} duplicate ratio.",
        f"Against WOR, cap1/cap8 median ROI deltas are {pct(float(primary_cap_wor['1']['roi_median']))}/{pct(float(primary_cap_wor['8']['roi_median']))} primary and {pct(float(secondary_cap_wor['1']['roi_median']))}/{pct(float(secondary_cap_wor['8']['roi_median']))} secondary; cap2/cap4 are also negative. Against WR, cap1 is mixed ({pct(float(primary_cap_wr['1']['roi_median']))}/{pct(float(secondary_cap_wr['1']['roi_median']))}), while cap2/4/8 are negative in both arms. Relative to residual, the same monotone concentration pattern remains; no repeat cap improves the frozen tradeoff stably.",
        "",
        "## Concentration and path risk",
        "",
    ]
    concentration_rows = []
    for (arm, label), values in sorted(mech_groups.items()):
        concentration_rows.append(
            [
                arm,
                label,
                pct(med(row["gross_top_issue_share"] for row in values)),
                f"{med(row['gross_issue_hhi'] for row in values):.4f}",
                yuan(med(row["largest_issue_gross_yuan"] for row in values)),
                yuan(med(row["max_drawdown_yuan"] for row in values)),
                f"{med(row['longest_miss_streak'] for row in values):.0f}",
            ]
        )
    lines += markdown_table(
        [
            "arm",
            "mechanism",
            "top-issue share",
            "gross HHI",
            "largest issue gross",
            "tax-net max drawdown",
            "longest wager miss",
        ],
        concentration_rows,
    )
    lines += [
        "",
        "The concentration/path table uses the same settled positive-stake denominator as wagering coverage and miss streak; unavailable canonical outcomes and Gate-A no-bets are not converted into losses.",
        "",
        "## Seed dispersion and stability",
        "",
    ]
    seed_ranges: defaultdict[tuple[str, str], list[float]] = defaultdict(list)
    randomized = [
        row
        for row in all_rows
        if row["mechanism"] in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"}
    ]
    by_cell: defaultdict[tuple[str, str, str, str, str], list[float]] = defaultdict(
        list
    )
    for row in randomized:
        by_cell[
            (
                row["arm_id"],
                row["weight_source"],
                row["mechanism"],
                row["cap"],
                row["M"],
            )
        ].append(float(row["no_tax_roi"]))
    for key, values in by_cell.items():
        if len(values) == 3:
            seed_ranges[(key[0], key[2])].append(max(values) - min(values))
    seed_rows = [
        [
            arm,
            mechanism,
            pct(med(values)),
            pct(sorted(values)[min(len(values) - 1, round(0.95 * (len(values) - 1)))]),
            len(values),
        ]
        for (arm, mechanism), values in sorted(seed_ranges.items())
    ]
    lines += markdown_table(
        ["arm", "mechanism", "median seed range", "p95 seed range", "matched cells"],
        seed_rows,
    )
    boot_primary = [row for row in bootstrap if row["metric"] == "no_tax_roi_delta"]
    positive_ci = sum(float(row["ci95_low"]) > 0 for row in boot_primary)
    crossing = sum(
        float(row["ci95_low"]) <= 0 <= float(row["ci95_high"]) for row in boot_primary
    )
    holm_significant = [
        row for row in multiple if row["holm_p"] and float(row["holm_p"]) < 0.05
    ]
    holm_positive_majority = sum(
        int(row["positive_issue_count"]) > int(row["negative_issue_count"])
        for row in holm_significant
    )
    holm_negative_majority = sum(
        int(row["negative_issue_count"]) > int(row["positive_issue_count"])
        for row in holm_significant
    )
    lines += [
        "",
        f"Issue bootstrap has {len(boot_primary):,} pre-tax comparisons: {positive_ci:,} have a lower 95% bound above zero and {crossing:,} cross zero. Holm-adjusted paired issue sign tests below 0.05 total {len(holm_significant):,}/{len(multiple):,}, but direction matters: {holm_negative_majority:,} have a negative-issue majority and only {holm_positive_majority:,} have a positive-issue majority.",
        "The paired sign statistic is per-issue candidate-minus-FULL ROI and mainly records coverage/miss direction, not payout magnitude. A cell can therefore have positive aggregate ROI from a few large wins while most issue-level signs are negative; 1,983 significance flags are not 1,983 favorable discoveries.",
        "",
        "### Binding to the prior #151/#154 cluster",
        "",
    ]
    m64_rows = sorted(
        (
            row
            for row in all_rows
            if row["arm_id"] == "PRIMARY_NO_GATE_K4"
            and row["weight_source"] == "Q_WEIGHT"
            and row["mechanism"] == "WOR_DISTINCT"
            and row["M"] == "64"
        ),
        key=lambda row: row["seed"],
    )
    m64_binding_rows = []
    for row in m64_rows:
        ex_largest = next(
            value
            for value in largest
            if value["arm_id"] == row["arm_id"]
            and value["weight_source"] == row["weight_source"]
            and value["mechanism"] == row["mechanism"]
            and value["cap"] == row["cap"]
            and value["M"] == row["M"]
            and value["seed"] == row["seed"]
        )
        boot = next(
            value
            for value in boot_primary
            if value["arm_id"] == row["arm_id"]
            and value["weight_source"] == row["weight_source"]
            and value["mechanism"] == row["mechanism"]
            and value["cap"] == row["cap"]
            and value["M"] == row["M"]
            and value["seed"] == row["seed"]
        )
        m64_binding_rows.append(
            [
                row["seed"],
                pct(float(row["no_tax_roi"])),
                pct(float(ex_largest["no_tax_roi_excluding_largest"])),
                f"[{pct(float(boot['ci95_low']))}, {pct(float(boot['ci95_high']))}]",
            ]
        )
    lines += markdown_table(
        ["seed", "Q-WOR M64 ROI", "ex-largest ROI", "bootstrap Δ vs FULL 95% CI"],
        m64_binding_rows,
    )
    m64_scope_rows = [
        row
        for row in summary
        if row["arm_id"] == "PRIMARY_NO_GATE_K4"
        and row["weight_source"] == "Q_WEIGHT"
        and row["mechanism"] == "WOR_DISTINCT"
        and row["M"] == "64"
    ]
    scope_stability = {}
    for scope in ("YEAR", "FOLD", "LOYO"):
        values = [
            float(row["no_tax_roi"])
            for row in m64_scope_rows
            if row["scope"] == scope and row["no_tax_roi"]
        ]
        scope_stability[scope] = (
            len(values),
            sum(value > 0 for value in values),
            sum(value < 0 for value in values),
            med(values),
        )
    m16_values = [
        float(row["no_tax_roi"])
        for row in all_rows
        if row["arm_id"] == "PRIMARY_NO_GATE_K4"
        and row["weight_source"] == "Q_WEIGHT"
        and row["mechanism"] == "WOR_DISTINCT"
        and row["M"] == "16"
    ]
    lines += [
        "",
        "The primary Q-WOR/M64 values are the already-reproduced #151/#154 historical cluster, not a new #145 discovery. All three bootstrap intervals cross zero; excluding each seed's largest gross issue changes the three ROIs to about -11.47%, +0.08% and -9.46%, matching the prior validation warning.",
        f"Within the frozen M64 slices, YEAR and FOLD are each positive in {scope_stability['YEAR'][1]}/{scope_stability['YEAR'][0]} rows (median {pct(float(scope_stability['YEAR'][3]))}); LOYO is positive in {scope_stability['LOYO'][1]}/{scope_stability['LOYO'][0]} (median {pct(float(scope_stability['LOYO'][3]))}). This is mixed, not uniform stability.",
        f"The M16/seed137002 +84.76% peak is a seed outlier: the three primary Q-WOR M16 seed ROIs are -42.54%, +84.76% and -29.30%, with a cross-seed median of {pct(med(m16_values))}.",
        "",
        "## YEAR / FOLD / LOYO and concentration",
        "",
    ]
    scope_rows = []
    for scope in ("YEAR", "FOLD", "LOYO"):
        values = [row for row in summary if row["scope"] == scope and row["no_tax_roi"]]
        scope_rows.append(
            [
                scope,
                len(values),
                len({row["scope_value"] for row in values}),
                f"{sum(float(row['no_tax_roi']) > 0 for row in values):,}",
                pct(med(row["no_tax_roi"] for row in values)),
                pct(
                    med(
                        row["gross_top_issue_share"]
                        for row in values
                        if row["gross_top_issue_share"]
                    )
                ),
            ]
        )
    lines += markdown_table(
        [
            "scope",
            "rows",
            "scope values",
            "positive rows",
            "median ROI",
            "median top-issue gross share",
        ],
        scope_rows,
    )
    top = sorted(
        (row for row in all_rows if row["mechanism"] != "FULL_ENUMERATED"),
        key=lambda row: float(row["no_tax_roi"]),
        reverse=True,
    )[:12]
    loio_map = {
        (
            row["arm_id"],
            row["weight_source"],
            row["mechanism"],
            row["cap"],
            row["M"],
            row["seed"],
        ): row
        for row in loio
    }
    largest_map = {
        (
            row["arm_id"],
            row["weight_source"],
            row["mechanism"],
            row["cap"],
            row["M"],
            row["seed"],
        ): row
        for row in largest
    }
    top_rows = []
    for row in top:
        key = (
            row["arm_id"],
            row["weight_source"],
            row["mechanism"],
            row["cap"],
            row["M"],
            row["seed"],
        )
        loio_row = loio_map[key]
        largest_row = largest_map[key]
        top_rows.append(
            [
                row["arm_id"],
                row["weight_source"],
                row["mechanism"],
                row["cap"],
                row["M"],
                row["seed"],
                pct(float(row["no_tax_roi"])),
                pct(float(largest_row["no_tax_roi_excluding_largest"])),
                pct(float(largest_row["no_tax_roi_delta_excluding_largest_vs_full"])),
                pct(float(loio_row["leave_one_roi_min"])),
                loio_row["leave_one_roi_min_issue_instance"],
                pct(float(loio_row["leave_one_roi_max"])),
                loio_row["leave_one_roi_max_issue_instance"],
                pct(float(row["gross_top_issue_share"])),
            ]
        )
    lines += [""] + markdown_table(
        [
            "arm",
            "weight",
            "mechanism",
            "cap",
            "M",
            "seed",
            "ROI",
            "ex-largest ROI",
            "ex-largest Δ vs FULL",
            "LOIO min",
            "min removed issue",
            "LOIO max",
            "max removed issue",
            "top issue share",
        ],
        top_rows,
    )
    lines += [
        "",
        "The high historical cells are sensitive to issue concentration and seed. Ex-largest and leave-one-issue-out results are reported in pre-tax units so payout concentration is not obscured by tax mechanics.",
        "",
        "## Five terminal questions",
        "",
        f"1. **Matched value of probability/value weighting:** On the main WOR slice, Q_WEIGHT has comparator medians ranging {pct(min(q_wor_primary_medians))} to {pct(max(q_wor_primary_medians))} in primary ({primary_q_wor[1]}/{len(primary_q_wor[0])} favorable overall) and {pct(min(q_wor_secondary_medians))} to {pct(max(q_wor_secondary_medians))} in secondary ({secondary_q_wor[1]}/{len(secondary_q_wor[0])} favorable overall). The lift is small/mixed and does not establish a universal weighting winner; across all mechanisms the pooled medians are {pct(med(primary_q[0]))}/{pct(med(secondary_q[0]))}.",
        f"2. **Matched WOR effect:** WOR−WR has median pre-tax deltas of {pct(float(primary_wor['roi_median']))} primary and {pct(float(secondary_wor['roi_median']))} secondary, favorable in {primary_wor['favorable']}/{primary_wor['cells']} and {secondary_wor['favorable']}/{secondary_wor['cells']} matched cells. WOR improves distinct coverage and removes WR duplicate exposure, so the mechanism has a plausible historical attribution, but this is not promotion evidence.",
        f"3. **Matched WR/residual effect:** WR−residual is {pct(float(primary_wr_residual['roi_median']))} primary ({primary_wr_residual['favorable']}/{primary_wr_residual['cells']} favorable) and {pct(float(secondary_wr_residual['roi_median']))} secondary ({secondary_wr_residual['favorable']}/{secondary_wr_residual['cells']} favorable), with roughly +4.4pp duplicate ratio. The direction changes by arm; neither WR nor residual is a stable winner.",
        f"4. **Repeat-cap tradeoff:** cap1 is the near-identity distinct control. Relative to WOR, cap1/cap8 median deltas are {pct(float(primary_cap_wor['1']['roi_median']))}/{pct(float(primary_cap_wor['8']['roi_median']))} primary and {pct(float(secondary_cap_wor['1']['roi_median']))}/{pct(float(secondary_cap_wor['8']['roi_median']))} secondary; cap2/cap4 are also negative. Relative to WR, cap1 is mixed ({pct(float(primary_cap_wr['1']['roi_median']))}/{pct(float(secondary_cap_wr['1']['roi_median']))}) and cap2/4/8 are negative in both arms. Coverage falls and duplicate concentration rises as cap loosens; no cap improves the tradeoff stably.",
        f"5. **Stable sweet spot:** none. The prior Q-WOR/M64 cluster is positive across its three pooled seeds but all three bootstrap intervals cross zero and ex-largest ROIs are -11.47%, +0.08% and -9.46%; YEAR/FOLD are positive in {scope_stability['YEAR'][1]}/{scope_stability['YEAR'][0]} and LOYO in {scope_stability['LOYO'][1]}/{scope_stability['LOYO'][0]}. Across the whole surface only {positive_ci}/{len(boot_primary)} bootstrap lower bounds are positive, {crossing}/{len(boot_primary)} intervals cross zero, and Holm direction is {holm_positive_majority} positive-majority versus {holm_negative_majority} negative-majority. The M16 peak is a seed outlier, not a sweet spot.",
        "",
        "## Drawdown and accounting conventions",
        "",
        "- Stake is `selected_identity_count × M × ¥2`; every WR duplicate is an independent ¥2 ticket.",
        "- Gross retention and capital utilization are reported separately; lowering stake is not itself an edge.",
        "- Tax is 20% only when each individual winning ticket gross is at least ¥10,000. There is no ticket, issue, policy or claimant pooling.",
        "- Hit tickets, winning-identity multiplicity, gross top-issue share, HHI, longest miss streak and chronological tax-net max drawdown are all present in `mechanism_weight_surface_summary.csv` for ALL/YEAR/FOLD/LOYO.",
        "",
        "## Terminal interpretation",
        "",
        "`DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION` remains the only supported decision. Allocation mechanism, cap and M materially change coverage, duplicate exposure, capital use and payout concentration. Matched attribution supports WOR as the most plausible distinct-coverage mechanism and binds its mid-M positive cluster to #151/#154, but attribution is not promotion: the strongest same-window Q-WOR cells do not survive the full multiplicity/concentration/seed/LOYO interpretation. WR, residual and repeat caps likewise have no common stable advantage. Any positive candidate still requires strict independent EV and genuinely held-out or forward validation.",
        "",
        "Charts: `roi_vs_m_cap.svg`, `matched_pre_tax_comparison.svg`, and `uncertainty_stability.svg`. The full numeric surfaces remain the authoritative evidence.",
        "",
    ]
    (package / "report.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8"
    )
    print(package / "report.md")


if __name__ == "__main__":
    main()
