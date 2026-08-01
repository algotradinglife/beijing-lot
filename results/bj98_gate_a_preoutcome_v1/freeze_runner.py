#!/usr/bin/env python3
"""Freeze #98 N7 probability-sampling portfolios without settlement inputs.

The generator reads the accepted #95 outcome-safe N7 leg projection only.  It
analytically represents each 7-fold ticket by seven omitted 3/1/0 codes, so
the 128 physical sequences in each pruned ticket are never materialised.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path

CODES = ("3", "1", "0")
SEEDS = tuple(range(10_001, 10_033))
CONTRACT_ID = "BJ-HIST-SAMPLING-001"
GENERATOR_VERSION = "bj98-analytic-omission-v1"
STAKE_PER_SEQUENCE = 2
FULL_K = 3**7
PRUNED_K = 2**7
QUALITY_QUANTILE = 0.75
SOURCE_MANIFEST_SHA = "10b4d6d274aef53e1e1d4abe30cd9f683cf296865ee131f00f5c1e1d16d0725c"
SOURCE_LEGS_SHA = "369c2ab398cb996bcd913f9ff7d3d71431303c957bb349e43b774c87c40e377e"

LEG_FIELDS = (
    "group_id",
    "position",
    "match_id",
    "issue",
    "match_idx",
    "year",
    "fold",
    "handicap_line_norm",
    "p3",
    "p1",
    "p0",
    "euro_p3",
    "euro_p1",
    "euro_p0",
    "predicted_sp_3",
    "predicted_sp_1",
    "predicted_sp_0",
    "sp5_3",
    "sp5_1",
    "sp5_0",
)
FRONTIER_FIELDS = (
    "group_id",
    "issue",
    "year",
    "fold",
    "seed",
    "arm",
    "selection_status",
    "selection_rule",
    "quality_score",
    "prior_quality_q75",
    "omitted_codes",
    "selected_sequence_count",
    "stake_yuan",
    "calibrated_mass",
    "euro_novig_mass",
    "portfolio_descriptor_sha256",
)


def repository_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("could not locate repository root")


ROOT = repository_root(Path(__file__))
SOURCE = ROOT / "results" / "bj95_gate_a_preoutcome_v5"
DEFAULT_OUT = ROOT / "results" / "bj98_gate_a_preoutcome_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decompressed_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("refusing to emit non-finite numeric value")
    return format(value, ".17g")


def positive_probability(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(f"invalid probability {label}: {raw!r}") from error
    if not math.isfinite(value) or value <= 0.0:
        raise RuntimeError(f"invalid probability {label}: {raw!r}")
    return value


def exact_manifest(bundle: Path, expected_sha: str) -> dict[str, str]:
    manifest_path = bundle / "SHA256SUMS.json"
    if sha256(manifest_path) != expected_sha:
        raise RuntimeError("unaccepted #95 source manifest")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = list(bundle.iterdir())
    if not isinstance(declared, dict) or any(not path.is_file() for path in entries):
        raise RuntimeError("#95 source must be an exact flat manifest bundle")
    actual = {
        path.name: sha256(path) for path in entries if path.name != manifest_path.name
    }
    if actual != declared:
        raise RuntimeError("#95 source manifest coverage drift")
    return declared


def assert_schema(fieldnames: Iterable[str] | None) -> None:
    if tuple(fieldnames or ()) != LEG_FIELDS:
        raise RuntimeError(f"unexpected #95 safe-leg schema: {fieldnames}")


def load_groups() -> dict[str, list[dict[str, object]]]:
    manifest = exact_manifest(SOURCE, SOURCE_MANIFEST_SHA)
    path = SOURCE / "outcome_safe_n7_legs.csv.gz"
    if manifest.get(path.name) is None:
        raise RuntimeError("missing #95 safe-leg payload")
    if decompressed_sha256(path) != SOURCE_LEGS_SHA:
        raise RuntimeError("#95 safe-leg canonical content drift")
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert_schema(reader.fieldnames)
        for row in reader:
            probabilities = {
                code: positive_probability(row[f"p{code}"], f"{row['match_id']}:{code}")
                for code in CODES
            }
            euro = {
                code: positive_probability(
                    row[f"euro_p{code}"], f"EURO {row['match_id']}:{code}"
                )
                for code in CODES
            }
            if abs(sum(probabilities.values()) - 1.0) > 1e-9:
                raise RuntimeError(
                    f"invalid calibrated probability sum: {row['match_id']}"
                )
            if abs(sum(euro.values()) - 1.0) > 1e-9:
                raise RuntimeError(f"invalid EURO probability sum: {row['match_id']}")
            groups[row["group_id"]].append(
                {
                    "position": int(row["position"]),
                    "match_id": row["match_id"],
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "year": int(row["year"]),
                    "fold": row["fold"],
                    "p": probabilities,
                    "euro": euro,
                }
            )
    if len(groups) != 6_686 or sum(len(legs) for legs in groups.values()) != 46_802:
        raise RuntimeError("#95 common N7 cohort cardinality drift")
    for group_id, legs in groups.items():
        legs.sort(key=lambda leg: int(leg["position"]))
        if [leg["position"] for leg in legs] != list(range(1, 8)):
            raise RuntimeError(f"invalid frozen N7 positions: {group_id}")
        if (
            len({leg["issue"] for leg in legs}) != 1
            or len({leg["year"] for leg in legs}) != 1
        ):
            raise RuntimeError(f"mixed identity group: {group_id}")
    return groups


def bottom_code(probability: dict[str, float]) -> str:
    return min(CODES, key=lambda code: (probability[code], CODES.index(code)))


def uniform_unit(*parts: object) -> float:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big") / 2**256


def sampled_code(
    probability: dict[str, float], group_id: str, position: int, seed: int, arm: str
) -> str:
    unit = uniform_unit(CONTRACT_ID, group_id, position, seed, arm)
    if arm == "UNIFORM_OMIT":
        return CODES[min(int(unit * len(CODES)), len(CODES) - 1)]
    if arm not in ("WEIGHTED_OMIT", "QUALITY_WEIGHTED_OMIT"):
        raise RuntimeError(f"unsupported sampled arm: {arm}")
    weights = {code: 1.0 - probability[code] for code in CODES}
    total = sum(weights.values())
    cumulative = 0.0
    for code in CODES:
        cumulative += weights[code] / total
        if unit < cumulative:
            return code
    return CODES[-1]


def quality_score(legs: list[dict[str, object]]) -> float:
    return sum(max(leg["p"].values()) for leg in legs) / len(legs)  # type: ignore[union-attr]


def empirical_quantile(values: list[float], quantile: float) -> float:
    if not values or not 0.0 < quantile < 1.0:
        raise RuntimeError("invalid chronological quantile inputs")
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * quantile) - 1]


def thresholds(groups: dict[str, list[dict[str, object]]]) -> dict[int, float | None]:
    by_year: dict[int, list[float]] = defaultdict(list)
    for legs in groups.values():
        by_year[int(legs[0]["year"])].append(quality_score(legs))
    prior: list[float] = []
    output: dict[int, float | None] = {}
    for year in sorted(by_year):
        output[year] = empirical_quantile(prior, QUALITY_QUANTILE) if prior else None
        prior.extend(by_year[year])
    return output


def allowed_mass(
    legs: list[dict[str, object]], omitted: list[str]
) -> tuple[float, float]:
    calibrated = euro = 1.0
    for leg, code in zip(legs, omitted):
        calibrated *= 1.0 - leg["p"][code]  # type: ignore[index]
        euro *= 1.0 - leg["euro"][code]  # type: ignore[index]
    return calibrated, euro


def descriptor(
    group_id: str,
    arm: str,
    seed: str,
    legs: list[dict[str, object]],
    omitted: list[str],
) -> str:
    return canonical_hash(
        {
            "contract": CONTRACT_ID,
            "generator_version": GENERATOR_VERSION,
            "group_id": group_id,
            "arm": arm,
            "seed": seed,
            "code_order": CODES,
            "omitted_codes_by_position": omitted,
            "ordered_identities": [
                (leg["match_id"], leg["issue"], leg["match_idx"], leg["fold"])
                for leg in legs
            ],
            "source_safe_leg_sha256": SOURCE_LEGS_SHA,
        }
    )


def row_for(
    group_id: str,
    legs: list[dict[str, object]],
    arm: str,
    seed: str,
    threshold: float | None,
    omitted: list[str],
) -> dict[str, object]:
    score = quality_score(legs)
    requires_quality = arm.startswith("QUALITY_")
    selected = not requires_quality or threshold is None or score >= threshold
    selection_rule = (
        "ALL_GROUPS_CONTROL"
        if not requires_quality
        else "NO_PRIOR_YEAR_FULL_FALLBACK"
        if threshold is None
        else "PRIOR_YEARS_Q75_MEAN_TOP1"
    )
    first = legs[0]
    if selected:
        mass, euro_mass = allowed_mass(legs, omitted)
        count, stake = PRUNED_K, PRUNED_K * STAKE_PER_SEQUENCE
        status = "SELECTED"
        digest = descriptor(group_id, arm, seed, legs, omitted)
    else:
        mass = euro_mass = 0.0
        count = stake = 0
        status = "NO_BET_BY_CHRONO_QUALITY"
        digest = ""
    return {
        "group_id": group_id,
        "issue": first["issue"],
        "year": first["year"],
        "fold": first["fold"],
        "seed": seed,
        "arm": arm,
        "selection_status": status,
        "selection_rule": selection_rule,
        "quality_score": fmt(score),
        "prior_quality_q75": "" if threshold is None else fmt(threshold),
        "omitted_codes": "|".join(
            f"{index}:{code}" for index, code in enumerate(omitted, start=1)
        ),
        "selected_sequence_count": count,
        "stake_yuan": stake,
        "calibrated_mass": fmt(mass) if selected else "",
        "euro_novig_mass": fmt(euro_mass) if selected else "",
        "portfolio_descriptor_sha256": digest,
    }


def frontier_rows(
    groups: dict[str, list[dict[str, object]]],
) -> Iterator[dict[str, object]]:
    by_year_threshold = thresholds(groups)
    for group_id, legs in sorted(groups.items()):
        year = int(legs[0]["year"])
        full = ["" for _ in legs]
        first = legs[0]
        yield {
            "group_id": group_id,
            "issue": first["issue"],
            "year": first["year"],
            "fold": first["fold"],
            "seed": "CONTROL",
            "arm": "FULL_COVER_CONTROL",
            "selection_status": "SELECTED",
            "selection_rule": "ALL_GROUPS_CONTROL",
            "quality_score": fmt(quality_score(legs)),
            "prior_quality_q75": "",
            "omitted_codes": "",
            "selected_sequence_count": FULL_K,
            "stake_yuan": FULL_K * STAKE_PER_SEQUENCE,
            "calibrated_mass": "1",
            "euro_novig_mass": "1",
            "portfolio_descriptor_sha256": descriptor(
                group_id, "FULL_COVER_CONTROL", "CONTROL", legs, full
            ),
        }
        fixed = [bottom_code(leg["p"]) for leg in legs]  # type: ignore[arg-type]
        yield row_for(group_id, legs, "FIXED_LOWEST_P_OMIT", "FIXED", None, fixed)
        for seed in SEEDS:
            uniform = [
                sampled_code(
                    leg["p"], group_id, int(leg["position"]), seed, "UNIFORM_OMIT"
                )
                for leg in legs
            ]  # type: ignore[arg-type]
            weighted = [
                sampled_code(
                    leg["p"], group_id, int(leg["position"]), seed, "WEIGHTED_OMIT"
                )
                for leg in legs
            ]  # type: ignore[arg-type]
            yield row_for(group_id, legs, "UNIFORM_OMIT", str(seed), None, uniform)
            yield row_for(group_id, legs, "WEIGHTED_OMIT", str(seed), None, weighted)
            yield row_for(
                group_id,
                legs,
                "QUALITY_UNIFORM_OMIT",
                str(seed),
                by_year_threshold[year],
                uniform,
            )
            yield row_for(
                group_id,
                legs,
                "QUALITY_WEIGHTED_OMIT",
                str(seed),
                by_year_threshold[year],
                weighted,
            )


def write_gzip(
    path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]
) -> Counter[tuple[str, str]]:
    census: Counter[tuple[str, str]] = Counter()
    with (
        path.open("wb") as binary,
        gzip.GzipFile(fileobj=binary, mode="wb", mtime=0) as compressed,
        io.TextIOWrapper(compressed, newline="", encoding="utf-8") as handle,
    ):
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            census[(str(row["arm"]), str(row["selection_status"]))] += 1
    return census


def build(out: Path) -> dict[str, object]:
    if out.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {out}")
    groups = load_groups()
    # The system tmpfs can be intentionally small relative to frozen research
    # artifacts.  Stage beside the requested immutable output instead.
    with tempfile.TemporaryDirectory(
        prefix=".bj98_gate_a_", dir=out.parent
    ) as temp_name:
        stage = Path(temp_name)
        census = write_gzip(
            stage / "sampling_frontier.csv.gz", FRONTIER_FIELDS, frontier_rows(groups)
        )
        with (stage / "selection_census.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("arm", "selection_status", "row_count"),
                lineterminator="\n",
            )
            writer.writeheader()
            for (arm, status), count in sorted(census.items()):
                writer.writerow(
                    {"arm": arm, "selection_status": status, "row_count": count}
                )
        decompressed_sha = decompressed_sha256(stage / "sampling_frontier.csv.gz")
        card = {
            "issue": 98,
            "stage": "GATE_A_PREOUTCOME_SAMPLING_FREEZE",
            "contract": CONTRACT_ID,
            "outcome_boundary": "No result, score, winning/final SP, payout, gross, net, ROI, or settlement payload is read or emitted.",
            "source_boundary": {
                "used_bundle": "results/bj95_gate_a_preoutcome_v5",
                "used_manifest_sha256": SOURCE_MANIFEST_SHA,
                "used_safe_leg_payload_sha256": SOURCE_LEGS_SHA,
                "transitive_frozen_inputs": ["#89", "#90", "#91", "#95"],
                "deferred_settlement_controls": [
                    "#91 dynamic-EV",
                    "#95 structured-pruning",
                ],
            },
            "grouping": "exactly the 6,686 chronological PRIMARY N=7 groups frozen by #91/#95; no group is regenerated or filtered.",
            "arms": [
                "FULL_COVER_CONTROL",
                "FIXED_LOWEST_P_OMIT",
                "UNIFORM_OMIT",
                "WEIGHTED_OMIT",
                "QUALITY_UNIFORM_OMIT",
                "QUALITY_WEIGHTED_OMIT",
            ],
            "sampling": {
                "seeds": list(SEEDS),
                "uniform": "one omitted code per leg uniformly over 3/1/0",
                "weighted": "one omitted code per leg with weight 1-p(code), deterministically sampled from SHA-256",
            },
            "match_selection": {
                "quality": "mean seven-leg calibrated top-1 probability",
                "threshold": "empirical 75th percentile of strictly earlier calendar-year groups",
                "first_year": "full-coverage fallback because no earlier fold exists",
            },
            "ticket_contract": "full control K=3^7=2187 and stake=2*K; every selected omission ticket K=2^7=128 and stake=2*K; stake and K are outputs, not eligibility gates.",
            "settlement_contract": "Gate B only: use frozen 0.65 settlement factor and canonical outcome join; no SP5 retroactivity or upstream regeneration.",
            "canonical_decompressed_sha256": {
                "sampling_frontier.csv.gz": decompressed_sha
            },
            "counts": {
                "groups": len(groups),
                "legs": sum(len(legs) for legs in groups.values()),
                "frontier_rows": sum(census.values()),
            },
        }
        (stage / "preoutcome_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copy2(Path(__file__), stage / "freeze_runner.py")
        payload = {
            path.name: sha256(path)
            for path in sorted(stage.iterdir())
            if path.is_file()
        }
        (stage / "SHA256SUMS.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copytree(stage, out)
    return {
        "output": str(out),
        "groups": len(groups),
        "frontier_rows": sum(census.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    print(json.dumps(build(parser.parse_args().output), sort_keys=True))


if __name__ == "__main__":
    main()
