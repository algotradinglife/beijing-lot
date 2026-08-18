#!/usr/bin/env python3
"""Create the immutable #137 v3r1 report-only derivative from v3 evidence.

This runner never reads the Gate-A freeze, ticket generator, or outcome source.
It verifies and reads only the immutable v3 common-support package, summarising
already-settled rows for the PI-requested user-facing parameter-surface report.
Its staging directory is under ``results/``; it never uses ``/tmp``.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results" / "bj137_gate_b_outcome_settlement_v3_common_support"
PARENT_MANIFEST = "fe55b7bdd8508a2b19bba2a57ecde9c7238feab1000a15a78ac24689cf89fb31"
PARENT_CONTENT = "be2012567f0aa1690be8e50711afe00233f8686fc5baa9423c400637e9a35f5f"
MATRIX = PARENT / "common_support_effects.csv.gz"
FRAGILITY = PARENT / "candidate_fragility.csv"
DECISION = PARENT / "decision.json"
OUTPUT = ROOT / "results" / "bj137_gate_b_outcome_settlement_v3r1_reporting_correction"

NUMERIC_SEEDS = ("137001", "137002", "137003")
PRIMARY = ("NO_GATE", "K4", "Q_INFORMED_WOR_DISTINCT", "Q_WEIGHT")
PRIMARY_MS = ("32", "64", "128", "256")
SECONDARY_GATES = ("ESP300_GM290", "ESP300_GM300", "ESP300_GM305")
SECONDARY = ("K8", "Q_INFORMED_WOR_DISTINCT", "Q_WEIGHT", "128")

CURVE_FIELDS = (
    "gate_id", "top_k_id", "sampler_id", "probability_vector", "mechanism", "M", "seed",
    "matched_settled_issue_count", "candidate_no_tax_roi", "baseline_no_tax_roi", "no_tax_roi_delta",
    "candidate_tax_adjusted_roi", "baseline_tax_adjusted_roi", "tax_adjusted_roi_delta",
    "worst_loyo_no_tax_roi_delta",
)
MECHANISM_FIELDS = (
    "probability_vector", "mechanism", "seed_rule", "surface_groups", "all_seed_positive_delta_groups",
    "loyo_stable_delta_groups", "absolute_pre_tax_edge_groups",
)
ATTRIBUTION_FIELDS = (
    "effect", "gate_id", "top_k_id", "sampler_id", "probability_vector", "M", "seed",
    "candidate_settled_issue_count", "baseline_settled_issue_count", "matched_settled_issue_count",
    "candidate_no_tax_roi", "baseline_no_tax_roi", "no_tax_roi_delta",
    "candidate_tax_adjusted_roi", "baseline_tax_adjusted_roi", "tax_adjusted_roi_delta", "interpretation",
)
SOURCE_FIELDS = ("source", "role", "manifest_sha256", "content_identity_sha256", "payload", "payload_sha256", "join_status")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ratio(value: float | None) -> str:
    return "" if value is None else f"{value:.12f}"


def verify_parent() -> None:
    if not PARENT.is_dir():
        raise RuntimeError(f"missing immutable v3 parent: {PARENT}")
    if sha(PARENT / "SHA256SUMS.json") != PARENT_MANIFEST:
        raise RuntimeError("v3 parent manifest identity mismatch")
    if sha(PARENT / "CONTENT_IDENTITY.json") != PARENT_CONTENT:
        raise RuntimeError("v3 parent content identity mismatch")
    manifest = json.loads((PARENT / "SHA256SUMS.json").read_text(encoding="utf-8"))
    mismatched = [name for name, expected in manifest.items() if sha(PARENT / name) != expected]
    if mismatched:
        raise RuntimeError(f"v3 parent payload hash mismatch: {mismatched}")


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@dataclass
class SamplerGroup:
    all_rows: dict[str, dict[str, str]] = field(default_factory=dict)
    loyo_deltas: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def add(self, row: dict[str, str]) -> None:
        if row["scope"] == "ALL":
            self.all_rows[row["seed"]] = row
        elif row["scope"] == "LEAVE_ONE_YEAR_OUT":
            self.loyo_deltas[row["seed"]].append(float(row["no_tax_roi_delta"]))

    def seed_rule(self) -> str:
        return "DETERMINISTIC_NO_SEED" if set(self.all_rows) == {"NA"} else "THREE_FROZEN_SEEDS"

    def all_positive(self) -> bool:
        expected = {"NA"} if self.seed_rule() == "DETERMINISTIC_NO_SEED" else set(NUMERIC_SEEDS)
        return set(self.all_rows) == expected and all(float(row["no_tax_roi_delta"]) > 0.0 for row in self.all_rows.values())

    def loyo_stable(self) -> bool:
        return self.all_positive() and all(values and all(value > 0.0 for value in values) for values in self.loyo_deltas.values())

    def absolute_edge(self) -> bool:
        return self.loyo_stable() and all(float(row["candidate_no_tax_roi"]) > 0.0 for row in self.all_rows.values())


def common_fields(row: dict[str, str], worst_loyo: float | None = None) -> dict[str, object]:
    return {
        "gate_id": row["gate_id"], "top_k_id": row["top_k_id"], "sampler_id": row["sampler_id"],
        "probability_vector": row["probability_vector"], "mechanism": row["mechanism"], "M": row["M"],
        "seed": row["seed"], "matched_settled_issue_count": row["matched_settled_issue_count"],
        "candidate_no_tax_roi": row["candidate_no_tax_roi"], "baseline_no_tax_roi": row["baseline_no_tax_roi"],
        "no_tax_roi_delta": row["no_tax_roi_delta"], "candidate_tax_adjusted_roi": row["candidate_tax_adjusted_roi"],
        "baseline_tax_adjusted_roi": row["baseline_tax_adjusted_roi"], "tax_adjusted_roi_delta": row["tax_adjusted_roi_delta"],
        "worst_loyo_no_tax_roi_delta": ratio(worst_loyo),
    }


def scan_surface() -> dict[str, object]:
    groups: dict[tuple[str, str, str, str, str], SamplerGroup] = defaultdict(SamplerGroup)
    primary_all: dict[tuple[str, str], dict[str, str]] = {}
    primary_loyo: dict[tuple[str, str], list[float]] = defaultdict(list)
    secondary_all: dict[tuple[str, str], dict[str, str]] = {}
    secondary_loyo: dict[tuple[str, str], list[float]] = defaultdict(list)
    selector_groups: dict[tuple[str, str], SamplerGroup] = defaultdict(SamplerGroup)
    selector_k1: dict[str, str] | None = None
    raw_max: dict[str, str] | None = None
    with gzip.open(MATRIX, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            effect = row["effect"]
            if effect == "SAMPLER_VS_EXACT_K_FULL_COMMON_SUPPORT":
                group_key = (row["gate_id"], row["top_k_id"], row["sampler_id"], row["probability_vector"], row["M"])
                groups[group_key].add(row)
                if row["scope"] == "ALL" and (raw_max is None or float(row["no_tax_roi_delta"]) > float(raw_max["no_tax_roi_delta"])):
                    raw_max = row
                if (row["gate_id"], row["top_k_id"], row["sampler_id"], row["probability_vector"]) == PRIMARY and row["M"] in PRIMARY_MS:
                    if row["scope"] == "ALL":
                        primary_all[(row["M"], row["seed"])] = row
                    elif row["scope"] == "LEAVE_ONE_YEAR_OUT":
                        primary_loyo[(row["M"], row["seed"])].append(float(row["no_tax_roi_delta"]))
                if row["gate_id"] in SECONDARY_GATES and (row["top_k_id"], row["sampler_id"], row["probability_vector"], row["M"]) == SECONDARY:
                    if row["scope"] == "ALL":
                        secondary_all[(row["gate_id"], row["seed"])] = row
                    elif row["scope"] == "LEAVE_ONE_YEAR_OUT":
                        secondary_loyo[(row["gate_id"], row["seed"])].append(float(row["no_tax_roi_delta"]))
            elif effect == "SELECTOR_VS_K_ALL_FULL_COMMON_SUPPORT":
                key = (row["gate_id"], row["top_k_id"])
                selector_groups[key].add(row)
                if row["scope"] == "ALL" and key == ("NO_GATE", "K1"):
                    selector_k1 = row
    if raw_max is None or selector_k1 is None:
        raise RuntimeError("expected matched surface rows missing")

    primary_curve = [
        common_fields(primary_all[(m, seed)], min(primary_loyo[(m, seed)]))
        for m in PRIMARY_MS for seed in NUMERIC_SEEDS
    ]
    secondary_curve = [
        common_fields(secondary_all[(gate, seed)], min(secondary_loyo[(gate, seed)]))
        for gate in SECONDARY_GATES for seed in NUMERIC_SEEDS
    ]
    family: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for group in groups.values():
        exemplar = next(iter(group.all_rows.values()))
        key = (exemplar["probability_vector"], exemplar["mechanism"], group.seed_rule())
        family[key]["surface_groups"] += 1
        family[key]["all_seed_positive_delta_groups"] += int(group.all_positive())
        family[key]["loyo_stable_delta_groups"] += int(group.loyo_stable())
        family[key]["absolute_pre_tax_edge_groups"] += int(group.absolute_edge())
    family_rows = [
        {
            "probability_vector": key[0], "mechanism": key[1], "seed_rule": key[2],
            "surface_groups": values["surface_groups"],
            "all_seed_positive_delta_groups": values["all_seed_positive_delta_groups"],
            "loyo_stable_delta_groups": values["loyo_stable_delta_groups"],
            "absolute_pre_tax_edge_groups": values["absolute_pre_tax_edge_groups"],
        }
        for key, values in sorted(family.items())
    ]
    selector_all_positive = sum(group.all_positive() for group in selector_groups.values())
    selector_loyo_stable = sum(group.loyo_stable() for group in selector_groups.values())
    raw_group_key = (raw_max["gate_id"], raw_max["top_k_id"], raw_max["sampler_id"], raw_max["probability_vector"], raw_max["M"])
    raw_group = groups[raw_group_key]
    return {
        "primary_curve": primary_curve,
        "secondary_curve": secondary_curve,
        "family_rows": family_rows,
        "selector_all_positive_count": selector_all_positive,
        "selector_loyo_stable_count": selector_loyo_stable,
        "selector_k1": selector_k1,
        "raw_max": {
            "row": common_fields(raw_max),
            "all_seed_positive": raw_group.all_positive(),
            "loyo_stable": raw_group.loyo_stable(),
            "absolute_pre_tax_edge": raw_group.absolute_edge(),
        },
    }


def percentage(value: str) -> str:
    return f"{float(value) * 100:+.2f}%" if value else "—"


def pp(value: str) -> str:
    return f"{float(value) * 100:+.2f}pp" if value else "—"


def compact_triplet(rows: list[dict[str, object]], field: str) -> str:
    return " / ".join(percentage(str(row[field])) for row in rows)


def report_markdown(summary: dict[str, object], fragility: list[dict[str, str]]) -> str:
    primary = summary["primary_curve"]
    secondary = summary["secondary_curve"]
    primary_by_m = {m: [row for row in primary if row["M"] == m] for m in PRIMARY_MS}
    secondary_by_gate = {gate: [row for row in secondary if row["gate_id"] == gate] for gate in SECONDARY_GATES}
    raw = summary["raw_max"]
    raw_row = raw["row"]
    k1 = summary["selector_k1"]
    lines = [
        "# #137 Gate B v3r1 — report-only common-support correction",
        "",
        "This immutable derivative reads and verifies the v3 parent package only. It does not reopen Gate A, resample tickets, alter the v2r1 ledger, recompute common-support effects, or change the candidate rule.",
        "",
        "## Primary economic scale and attribution",
        "",
        "All rankings below use pre-tax `no_tax_roi` / `no_tax_roi_delta`: the Beijing Single Match 0.65 factor is already included in gross payout, while the per-ticket 20% tax remains a secondary execution sensitivity. The selector comparison is FULL K versus same-gate K_ALL FULL; sampler attribution is the sampler versus exact-K FULL on exact common settled complete-issue support.",
        "",
        f"NO_GATE/K1 FULL versus K_ALL FULL has candidate/baseline/common support {k1['candidate_settled_issue_count']}/{k1['baseline_settled_issue_count']}/{k1['matched_settled_issue_count']}; pre-tax delta {pp(k1['no_tax_roi_delta'])}, tax-adjusted delta {pp(k1['tax_adjusted_roi_delta'])}. Across all selector groups, {summary['selector_all_positive_count']} are ALL positive and {summary['selector_loyo_stable_count']} are LOYO-stable; selection alone is not a promoted edge.",
        "",
        "## Primary candidate: Q-informed WOR, NO_GATE/K4",
        "",
        "`NO_GATE / K4 / Q_INFORMED_WOR_DISTINCT / M64` is the sole all-seed positive absolute pre-tax candidate. It has 254 matched complete issue instances per seed and remains a strict-independent-EV candidate only; it has no promotion authority.",
        "",
        "| M | seed 137001: ROI / delta | seed 137002: ROI / delta | seed 137003: ROI / delta | worst LOYO delta |",
        "| ---: | --- | --- | --- | ---: |",
    ]
    for m in PRIMARY_MS:
        rows = primary_by_m[m]
        cells = [f"{percentage(str(row['candidate_no_tax_roi']))} / {pp(str(row['no_tax_roi_delta']))}" for row in rows]
        worst = min(float(str(row["worst_loyo_no_tax_roi_delta"])) for row in rows)
        lines.append(f"| {m} | {cells[0]} | {cells[1]} | {cells[2]} | {worst * 100:+.2f}pp |")
    lines.extend([
        "",
        "The M64 pre-tax ROI is +16.38% / +11.77% / +2.67%, with matched sampler-minus-FULL lift +32.15pp / +27.54pp / +18.44pp. Its tax-adjusted ROI remains secondary: +5.06% / +5.95% / -3.02%.",
        "",
        "## Secondary ESP300/GM*/K8/Q/M128 sensitivity",
        "",
        "This is a lower-concentration, near-break-even diagnostic only, not a replacement candidate. Its concentration is not available in v3 `candidate_fragility.csv`, which was contractually emitted for absolute-edge candidates only.",
        "",
        "| gate | matched support by seed | pre-tax ROI (137001/2/3) | matched pre-tax lift (137001/2/3) | worst LOYO lift |",
        "| --- | --- | --- | --- | ---: |",
    ])
    for gate in SECONDARY_GATES:
        rows = secondary_by_gate[gate]
        support = " / ".join(str(row["matched_settled_issue_count"]) for row in rows)
        worst = min(float(str(row["worst_loyo_no_tax_roi_delta"])) for row in rows)
        lines.append(f"| {gate} | {support} | {compact_triplet(rows, 'candidate_no_tax_roi')} | {compact_triplet(rows, 'no_tax_roi_delta')} | {worst * 100:+.2f}pp |")
    lines.extend([
        "",
        "## Probability-vector and draw-mechanism surface",
        "",
        "Counts below are distinct gate × K × sampler × M groups in the sampler-minus-exact-FULL surface. `ALL positive` requires every frozen seed (or the deterministic no-seed row) to have a positive pre-tax delta; `LOYO stable` additionally requires every leave-one-year-out row to be positive; `absolute edge` also requires positive pre-tax ROI in every required seed.",
        "",
        "| vector | mechanism | seed rule | groups | ALL positive | LOYO stable | absolute edge |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for row in summary["family_rows"]:
        lines.append(f"| {row['probability_vector']} | {row['mechanism']} | {row['seed_rule']} | {row['surface_groups']} | {row['all_seed_positive_delta_groups']} | {row['loyo_stable_delta_groups']} | {row['absolute_pre_tax_edge_groups']} |")
    lines.extend([
        "",
        "The raw ALL-scope maximum is deliberately not promoted: "
        f"{raw_row['gate_id']}/{raw_row['top_k_id']}/{raw_row['sampler_id']}/M{raw_row['M']}/seed {raw_row['seed']} has pre-tax delta {pp(str(raw_row['no_tax_roi_delta']))}, but all-seed={raw['all_seed_positive']}, LOYO-stable={raw['loyo_stable']}, absolute-edge={raw['absolute_pre_tax_edge']}. It is a one-row maximum, not the controlling rule outcome.",
        "",
        "## Concentration and uncertainty of the primary candidate",
        "",
        "| seed | top issue share | ex-largest absolute pre-tax ROI | ex-largest matched delta | worst leave-one-issue-out delta | bootstrap 95% delta interval |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ])
    for row in fragility:
        lines.append(
            f"| {row['seed']} | {percentage(row['candidate_gross_top_issue_share'])} | {percentage(row['candidate_ex_largest_issue_no_tax_roi'])} | {pp(row['ex_largest_issue_no_tax_roi_delta'])} | {pp(row['worst_leave_one_issue_out_no_tax_roi_delta'])} | {pp(row['bootstrap_no_tax_roi_delta_p025'])} to {pp(row['bootstrap_no_tax_roi_delta_p975'])} |"
        )
    lines.extend([
        "",
        "Two ex-largest absolute ROIs are negative; seed 137002 is essentially break-even positive (+0.08%), not negative. All issue-bootstrap intervals cross zero. This is why the correct tier is positive-but-concentrated and strict independent EV is required before any interpretation beyond historical research.",
    ])
    return "\n".join(lines) + "\n"


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    verify_parent()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj137_gateb_v3r1_", dir=output.parent))
    try:
        summary = scan_surface()
        with FRAGILITY.open(newline="", encoding="utf-8") as handle:
            fragility = list(csv.DictReader(handle))
        if {row["seed"] for row in fragility} != set(NUMERIC_SEEDS):
            raise RuntimeError("missing primary-candidate fragility seeds")
        write_csv(stage / "primary_candidate_curve.csv", CURVE_FIELDS, summary["primary_curve"])
        write_csv(stage / "secondary_esp300_k8_q_m128.csv", CURVE_FIELDS, summary["secondary_curve"])
        write_csv(stage / "mechanism_summary.csv", MECHANISM_FIELDS, summary["family_rows"])
        k1 = summary["selector_k1"]
        attribution = [
            {
                "effect": "SELECTOR_VS_K_ALL_FULL_COMMON_SUPPORT", "gate_id": k1["gate_id"], "top_k_id": k1["top_k_id"],
                "sampler_id": k1["sampler_id"], "probability_vector": k1["probability_vector"], "M": k1["M"], "seed": k1["seed"],
                "candidate_settled_issue_count": k1["candidate_settled_issue_count"], "baseline_settled_issue_count": k1["baseline_settled_issue_count"],
                "matched_settled_issue_count": k1["matched_settled_issue_count"], "candidate_no_tax_roi": k1["candidate_no_tax_roi"],
                "baseline_no_tax_roi": k1["baseline_no_tax_roi"], "no_tax_roi_delta": k1["no_tax_roi_delta"],
                "candidate_tax_adjusted_roi": k1["candidate_tax_adjusted_roi"], "baseline_tax_adjusted_roi": k1["baseline_tax_adjusted_roi"],
                "tax_adjusted_roi_delta": k1["tax_adjusted_roi_delta"], "interpretation": "common-support selector diagnostic; not LOYO-stable",
            }
        ]
        for row in summary["primary_curve"]:
            if row["M"] == "64":
                attribution.append({
                    "effect": "SAMPLER_VS_EXACT_K_FULL_COMMON_SUPPORT", "gate_id": row["gate_id"], "top_k_id": row["top_k_id"],
                    "sampler_id": row["sampler_id"], "probability_vector": row["probability_vector"], "M": row["M"], "seed": row["seed"],
                    "candidate_settled_issue_count": row["matched_settled_issue_count"], "baseline_settled_issue_count": row["matched_settled_issue_count"],
                    "matched_settled_issue_count": row["matched_settled_issue_count"], "candidate_no_tax_roi": row["candidate_no_tax_roi"],
                    "baseline_no_tax_roi": row["baseline_no_tax_roi"], "no_tax_roi_delta": row["no_tax_roi_delta"],
                    "candidate_tax_adjusted_roi": row["candidate_tax_adjusted_roi"], "baseline_tax_adjusted_roi": row["baseline_tax_adjusted_roi"],
                    "tax_adjusted_roi_delta": row["tax_adjusted_roi_delta"], "interpretation": "sole absolute pre-tax candidate; strict independent EV required",
                })
        write_csv(stage / "attribution_summary.csv", ATTRIBUTION_FIELDS, attribution)
        report = report_markdown(summary, sorted(fragility, key=lambda row: row["seed"]))
        (stage / "reporting_interpretation.md").write_text(report, encoding="utf-8")
        summary_payload = {
            "issue": 137,
            "stage": "GATE_B_V3R1_REPORTING_CORRECTION",
            "parent_package": str(PARENT.relative_to(ROOT)),
            "parent_manifest_sha256": PARENT_MANIFEST,
            "parent_content_identity_sha256": PARENT_CONTENT,
            "decision_inherited": json.loads(DECISION.read_text(encoding="utf-8")),
            "primary_candidate": "NO_GATE/K4/Q_INFORMED_WOR_DISTINCT/M64",
            "report_summary": summary,
            "fragility_source": "candidate_fragility.csv from v3 parent; no new concentration computation",
            "scope": "report-only derivative; historical paper research; no purchase, production, or promotion authority",
        }
        (stage / "reporting_summary.json").write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [{
            "source": "bj137_gate_b_outcome_settlement_v3_common_support", "role": "immutable common-support effects, decision and candidate fragility parent",
            "manifest_sha256": PARENT_MANIFEST, "content_identity_sha256": PARENT_CONTENT,
            "payload": "common_support_effects.csv.gz; candidate_fragility.csv; decision.json",
            "payload_sha256": sha(MATRIX),
            "join_status": "full parent manifest verified; read-only report aggregation only",
        }])
        lineage = {
            "parent_package": str(PARENT.relative_to(ROOT)), "parent_manifest_sha256": PARENT_MANIFEST,
            "parent_content_identity_sha256": PARENT_CONTENT,
            "correction": "User-facing reporting correction only: add primary M curve, secondary ESP300/GM/K8/Q/M128 sensitivity, vector/mechanism summaries, raw-max classification, and correct the ex-largest ROI wording.",
            "invariants": ["No Gate-A read", "No ticket resampling", "No v2r1 ledger change", "No common-support matrix change", "No candidate-rule change"],
        }
        (stage / "NUMERIC_LINEAGE.json").write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "reporting_runner.py")
        (stage / "README.md").write_text("# #137 Gate B v3r1 reporting correction\n\nImmutable report-only derivative of v3. It reuses verified v3 evidence without reading pre-outcome sources, resampling tickets, or changing any effect matrix or rule.\n", encoding="utf-8")
        content = {"contract_version": "bj137-gate-b-v3r1-reporting-v1", "non_compressed_controls": {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file()}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha(output / "SHA256SUMS.json"), "content_identity_sha256": sha(output / "CONTENT_IDENTITY.json"), "primary_curve_rows": len(summary["primary_curve"]), "secondary_rows": len(summary["secondary_curve"]), "mechanism_rows": len(summary["family_rows"])}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
