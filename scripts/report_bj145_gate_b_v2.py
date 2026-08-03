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
    lines += [
        "",
        "Q-based weighting creates the highest same-window peaks, especially under WOR, but the large number of tested cells and unstable concentration views prevent promotion. Blends and market/model weights do not show a uniformly superior surface.",
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
    lines += [
        "",
        "WOR raises distinct-code coverage relative to WR at equal M, while WR naturally retains duplicate stake. Residual and capped repeats trade duplicate concentration for closer proportional allocation; changing the cap moves exposure and concentration but does not create a cap whose result is stable across weights, seeds, years and folds.",
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
    holm_positive = sum(
        float(row["holm_p"]) < 0.05 for row in multiple if row["holm_p"]
    )
    lines += [
        "",
        f"Issue bootstrap has {len(boot_primary):,} pre-tax comparisons: {positive_ci:,} have a lower 95% bound above zero and {crossing:,} cross zero. Holm-adjusted paired issue sign tests below 0.05: {holm_positive:,}/{len(multiple):,}. These counts describe the frozen surface; they do not convert same-window cells into independent validation.",
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
        "## Drawdown and accounting conventions",
        "",
        "- Stake is `selected_identity_count × M × ¥2`; every WR duplicate is an independent ¥2 ticket.",
        "- Gross retention and capital utilization are reported separately; lowering stake is not itself an edge.",
        "- Tax is 20% only when each individual winning ticket gross is at least ¥10,000. There is no ticket, issue, policy or claimant pooling.",
        "- Hit tickets, winning-identity multiplicity, gross top-issue share, HHI, longest miss streak and chronological tax-net max drawdown are all present in `mechanism_weight_surface_summary.csv` for ALL/YEAR/FOLD/LOYO.",
        "",
        "## Terminal interpretation",
        "",
        "`DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION` remains the only supported decision. Allocation mechanism, cap and M materially change coverage, duplicate exposure, capital use and payout concentration. The strongest same-window Q-WOR cells do not survive the full multiplicity/concentration/seed/LOYO interpretation as promotion evidence. Any positive candidate still requires strict independent EV and genuinely held-out or forward validation.",
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
