#!/usr/bin/env python3
"""Outcome-unexposed Gate B freeze for #76 (BJ-N7-V771-TOPMASS-001).

This program is intentionally limited to the four groups accepted in the G1
source card.  It opens only the pre-kickoff odds surfaces used by V7.7.1 and
the identity/kickoff columns needed to validate them.  In particular it never
opens a result, settlement, final-SP, completed-page, or outcome artifact.

The supplied V7.7.1 manual fixes two previously ambiguous implementation
choices.  They are recorded separately in ``v771_variant_contracts.json``:
the score-other allocation changes the score distribution; the mid-band
auxiliary-board comparison is post-distribution and consequently cannot alter
the N7 3/1/0 probability vectors.  We do not manufacture a second numerical
top-mass arm for a rule that cannot change its inputs or outputs.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT.parents[1]
LIVE_DB = SHARED / "data/beidan_live.db"
MARKET_DB = SHARED / "data/derived/500_bjdc/500_bjdc.sqlite"
V771_ROOT = SHARED
GATE_A = ROOT / "results/bj76_g1_native_line_source_card_v1"
OUT = ROOT / "results/bj76_gateb_preoutcome_freeze_v2"
EXPECTED_GROUPS = ("26076-G01", "26077-G01", "26079-G01", "26079-G02")
TARGET_MASS = (0.50, 0.60, 0.70, 0.80)
SP_BAND = (2.5, 4.5)
TAX_FACTOR = 0.65
FRESHNESS = timedelta(hours=24)
UTC = timezone.utc
NUMERICAL_VARIANT = "V771_SCORE_OTHER_TAIL_PROPORTIONAL__AUX_MIDBAND_PAIR_SUM"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_gate_a() -> tuple[dict[str, Any], list[dict[str, str]], dict[str, str]]:
    """Check every Gate-A file before accepting its group identities."""
    listed: dict[str, str] = {}
    for raw in (GATE_A / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = raw.split("  ", 1)
        listed[name] = digest
    actual = {path.name: sha256(path) for path in GATE_A.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    if listed != actual:
        raise RuntimeError("Gate A SHA256SUMS does not exactly cover current source-card files")
    card = json.loads((GATE_A / "source_card.json").read_text(encoding="utf-8"))
    if card["disposition"] != "G1_SOURCE_CAPACITY_LT5_NO_CROSS_ISSUE_MANUFACTURE":
        raise RuntimeError("unexpected Gate A disposition")
    with (GATE_A / "potential_groups.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups = tuple(dict.fromkeys(row["group_id"] for row in rows))
    if groups != EXPECTED_GROUPS or len(rows) != 28:
        raise RuntimeError(f"Gate A group mismatch: {groups!r}, rows={len(rows)}")
    if any(sum(row["group_id"] == group_id for row in rows) != 7 for group_id in EXPECTED_GROUPS):
        raise RuntimeError("each Gate A group must have seven legs")
    return card, rows, listed


def code_for_handicap(score: tuple[int, int], line: int) -> str:
    """Map a literal V7.7.1 score to BJDC handicap 3/1/0 (home perspective)."""
    adjusted = score[0] - score[1] + line
    return "3" if adjusted > 0 else "1" if adjusted == 0 else "0"


def complete_market(
    market: sqlite3.Connection, match_id: str, playid: int, snapshot_utc: str,
    cache: dict[tuple[str, int], list[sqlite3.Row]] | None = None,
) -> dict[str, float]:
    target = stamp(snapshot_utc)
    if cache is None:
        rows = market.execute(
            """
            SELECT outcome_code, sp, fetched_at_utc, source_updated_at_hkt,
                   capture_classification, sale_status
            FROM live_market_sp_snapshots
            WHERE match_id = ? AND playid = ?
            ORDER BY outcome_code
            """,
            (match_id, playid),
        ).fetchall()
    else:
        rows = cache.get((match_id, playid), [])
    # Gate A serializes timestamps as canonical Z.  The sqlite sources may
    # preserve the same instant using an explicit +00:00 offset, so compare
    # instants rather than their spellings.
    rows = [row for row in rows if row["fetched_at_utc"] and stamp(str(row["fetched_at_utc"])) == target]
    if not rows or any(row["sp"] is None or float(row["sp"]) <= 0 for row in rows):
        raise RuntimeError(f"missing positive p{playid} vector for {match_id} @ {snapshot_utc}")
    fetched = {stamp(str(row["fetched_at_utc"])) for row in rows}
    source = {row["source_updated_at_hkt"] for row in rows}
    if fetched != {target} or len(source) != 1 or None in source:
        raise RuntimeError(f"incoherent p{playid} clocks for {match_id}")
    if stamp(next(iter(source))) > stamp(snapshot_utc) + timedelta(minutes=5):
        raise RuntimeError(f"p{playid} source clock exceeds fetched clock")
    if playid in (40, 42) and any(
        row["capture_classification"] != "forward_complete_open" or row["sale_status"] != "open"
        for row in rows
    ):
        raise RuntimeError(f"p{playid} not an open complete capture")
    return {str(row["outcome_code"]): float(row["sp"]) for row in rows}


def prior_p34(
    market: sqlite3.Connection, match_id: str, before: str,
    cache: dict[tuple[str, int], list[sqlite3.Row]] | None = None,
) -> tuple[str | None, dict[str, float] | None]:
    target = stamp(before)
    if cache is None:
        rows = market.execute(
            """
            SELECT outcome_code, sp, fetched_at_utc, source_updated_at_hkt,
                   capture_classification, sale_status
            FROM live_market_sp_snapshots
            WHERE match_id = ? AND playid = 34
            """,
            (match_id,),
        ).fetchall()
    else:
        rows = cache.get((match_id, 34), [])
    prior = [str(row["fetched_at_utc"]) for row in rows if row["fetched_at_utc"] and stamp(str(row["fetched_at_utc"])) < target]
    if not prior:
        return None, None
    selected = max(prior, key=stamp)
    return iso(stamp(selected)), complete_market(market, match_id, 34, selected, cache)


def source_vectors(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Read exactly Gate-A-selected snapshots and return outcome-free input rows."""
    sys.path.insert(0, str(V771_ROOT))
    # Import here so source-code identity is represented in the manifest before use.
    from src.score_prediction.v771 import MatchOdds, ThreeWayOdds, _poisson_mix, predict  # type: ignore

    live = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
    market = sqlite3.connect(f"file:{MARKET_DB}?mode=ro", uri=True)
    live.row_factory = sqlite3.Row
    market.row_factory = sqlite3.Row
    ids = sorted({row["match_id"] for row in rows})
    placeholders = ",".join("?" for _ in ids)
    market_cache: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    # One bounded scan avoids repeatedly full-scanning the large market table.
    # Only the four pre-result V7.7.1 surfaces and the Gate-A identities enter
    # the cache; no settlement or result column is selected.
    for cached in market.execute(
        f"""
        SELECT match_id, playid, outcome_code, sp, fetched_at_utc,
               source_updated_at_hkt, capture_classification, sale_status
        FROM live_market_sp_snapshots
        WHERE match_id IN ({placeholders}) AND playid IN (34, 40, 42, 51)
        """,
        ids,
    ):
        market_cache[(str(cached["match_id"]), int(cached["playid"]))].append(cached)
    vectors: list[dict[str, Any]] = []
    surface_rows: list[dict[str, Any]] = []
    p34_drift_rows: list[dict[str, Any]] = []
    required_p42 = {
        "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2",
        "0:0", "1:1", "2:2", "3:3", "0:1", "0:2", "1:2", "0:3", "1:3",
        "2:3", "0:4", "1:4", "2:4", "home_other", "draw_other", "away_other",
    }
    score_map = {"home_other": "胜其它", "draw_other": "平其它", "away_other": "负其它"}
    for row in rows:
        match = live.execute(
            """
            SELECT match_id, issue, match_idx, fid, kickoff_ts, home, away, handicap_line
            FROM matches WHERE match_id = ?
            """,
            (row["match_id"],),
        ).fetchone()
        if match is None:
            raise RuntimeError(f"missing selected match {row['match_id']}")
        expected_identity = (str(match["issue"]), str(match["match_idx"]), str(match["fid"]), str(match["home"]), str(match["away"]))
        recorded_identity = (row["issue"], row["match_idx"], row["fid"], row["home"], row["away"])
        if expected_identity != recorded_identity or int(float(match["handicap_line"])) != int(float(row["handicap_line"])):
            raise RuntimeError(f"Gate A identity changed for {row['match_id']}")
        cutoff = stamp(row["common_cutoff_utc"])
        kickoff = stamp(row["kickoff_utc"])
        if cutoff >= kickoff:
            raise RuntimeError(f"non-strict cutoff for {row['match_id']}")

        eu = live.execute(
            """
            SELECT eu_h, eu_d, eu_a, snapshot_ts, source
            FROM snapshots
            WHERE match_id = ? AND snapshot_ts = ? AND source = 'merged'
            """,
            (row["match_id"], row["one_x_two_snapshot_utc"]),
        ).fetchone()
        if eu is None or any(eu[key] is None or float(eu[key]) <= 0 for key in ("eu_h", "eu_d", "eu_a")):
            raise RuntimeError(f"missing selected 1X2 EU vector for {row['match_id']}")
        p34 = complete_market(market, row["match_id"], 34, row["p34_snapshot_utc"], market_cache)
        p40 = complete_market(market, row["match_id"], 40, row["p40_snapshot_utc"], market_cache)
        p42 = complete_market(market, row["match_id"], 42, row["p42_snapshot_utc"], market_cache)
        p51 = complete_market(market, row["match_id"], 51, row["p51_snapshot_utc"], market_cache)
        if not {"3", "1", "0"}.issubset(p34) or not {"0", "1", "2", "3", "4", "5", "6", "7+"}.issubset(p40):
            raise RuntimeError(f"required p34/p40 codes absent for {row['match_id']}")
        if not required_p42.issubset(p42) or not {"3-3", "1-1", "0-0"}.issubset(p51):
            raise RuntimeError(f"required p42/p51 codes absent for {row['match_id']}")
        for name, selected in (
            ("one_x_two", row["one_x_two_snapshot_utc"]), ("p34", row["p34_snapshot_utc"]),
            ("p40", row["p40_snapshot_utc"]), ("p42", row["p42_snapshot_utc"]), ("p51", row["p51_snapshot_utc"]),
        ):
            selected_ts = stamp(selected)
            if selected_ts > cutoff or cutoff - selected_ts > FRESHNESS:
                raise RuntimeError(f"invalid {name} selected age for {row['match_id']}")
            surface_rows.append({
                "group_id": row["group_id"], "match_id": row["match_id"], "surface": name,
                "snapshot_utc": selected, "common_cutoff_utc": row["common_cutoff_utc"],
                "age_seconds": int((cutoff - selected_ts).total_seconds()), "strictly_pre_kickoff": True,
            })
        old_p34_ts, old_p34 = prior_p34(market, row["match_id"], row["p34_snapshot_utc"], market_cache)
        for code in ("3", "1", "0"):
            old = old_p34.get(code) if old_p34 else None
            p34_drift_rows.append({
                "group_id": row["group_id"], "match_id": row["match_id"], "code": code,
                "selected_quote": p34[code], "selected_snapshot_utc": row["p34_snapshot_utc"],
                "selected_age_seconds": int((cutoff - stamp(row["p34_snapshot_utc"])).total_seconds()),
                "prior_snapshot_utc": old_p34_ts or "", "prior_quote": "" if old is None else old,
                "absolute_drift": "" if old is None else p34[code] - old,
                "relative_drift": "" if old is None else (p34[code] / old - 1.0),
            })
        inputs = MatchOdds(
            one_x_two=ThreeWayOdds(float(eu["eu_h"]), float(eu["eu_d"]), float(eu["eu_a"])),
            handicap=ThreeWayOdds(p34["3"], p34["1"], p34["0"]),
            handicap_line=int(float(match["handicap_line"])),
            half_full=ThreeWayOdds(p51["3-3"], p51["1-1"], p51["0-0"]),
            total_goals=tuple(p40[code] for code in ("0", "1", "2", "3", "4", "5", "6", "7+")),
            score_odds={score_map.get(code, code): p42[code] for code in sorted(required_p42)},
        )
        prediction = predict(inputs)
        by_code = {code: 0.0 for code in ("3", "1", "0")}
        for score, probability in prediction.distribution.items():
            by_code[code_for_handicap(score, inputs.handicap_line)] += probability
        if not math.isclose(sum(by_code.values()), 1.0, abs_tol=1e-12):
            raise RuntimeError(f"invalid mapped probability mass for {row['match_id']}")
        raw_grid_mass = sum(
            _poisson_mix(home, prediction.diagnostics.lambda_home) * _poisson_mix(away, prediction.diagnostics.lambda_away)
            for home in range(9) for away in range(9) if home + away <= 8
        )
        vectors.append({
            "group_id": row["group_id"], "issue": row["issue"], "leg_no": int(row["leg_no"]),
            "match_id": row["match_id"], "match_idx": int(row["match_idx"]), "fid": row["fid"],
            "home": row["home"], "away": row["away"], "handicap_line": inputs.handicap_line,
            "kickoff_utc": row["kickoff_utc"], "common_cutoff_utc": row["common_cutoff_utc"],
            "one_x_two": {"3": float(eu["eu_h"]), "1": float(eu["eu_d"]), "0": float(eu["eu_a"])},
            "handicap_quotes": {code: p34[code] for code in ("3", "1", "0")},
            "p3": by_code["3"], "p1": by_code["1"], "p0": by_code["0"],
            "entropy_nats": -sum(probability * math.log(probability) for probability in by_code.values() if probability > 0),
            "top2_mass": sum(sorted(by_code.values(), reverse=True)[:2]),
            "v771_grid_pre_normalization_mass": raw_grid_mass,
            "v771_grid_dropped_mass": 1.0 - raw_grid_mass,
            "diagnostics": {
                key: (value.value if hasattr(value, "value") else value)
                for key, value in prediction.diagnostics.__dict__.items()
            },
            "top15_scores": [
                {"score": candidate.label, "probability": candidate.probability, "bayes_score": candidate.bayes_score, "status": candidate.status}
                for candidate in prediction.candidates
            ],
        })
    live.close()
    market.close()
    return vectors, surface_rows, p34_drift_rows


def enumerate_group(legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sequences: list[dict[str, Any]] = []
    for choices in itertools.product(("3", "1", "0"), repeat=7):
        q = math.prod(leg[f"p{code}"] for leg, code in zip(legs, choices, strict=True))
        quote = math.prod(leg["handicap_quotes"][code] for leg, code in zip(legs, choices, strict=True))
        sequences.append({
            "codes": "".join(choices), "q": q, "quote_product": quote,
            "r_quote_after_factor": TAX_FACTOR * quote, "er_quote": q * TAX_FACTOR * quote,
            "sp_band_all_legs": all(SP_BAND[0] <= leg["handicap_quotes"][code] <= SP_BAND[1] for leg, code in zip(legs, choices, strict=True)),
        })
    # Exact deterministic tie break does not depend on database row order.
    return sorted(sequences, key=lambda item: (-item["q"], item["codes"]))


def frontiers(all_sequences: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    summary: list[dict[str, Any]] = []
    mass_value: list[dict[str, Any]] = []
    pareto: list[dict[str, Any]] = []
    for group_id, sequences in all_sequences.items():
        cumulative = 0.0
        first_at: dict[float, tuple[int, float]] = {}
        for rank, sequence in enumerate(sequences, 1):
            cumulative += sequence["q"]
            for target in TARGET_MASS:
                if target not in first_at and cumulative >= target:
                    first_at[target] = (rank, cumulative)
        for target in TARGET_MASS:
            rank, mass = first_at[target]
            summary.append({
                "group_id": group_id, "arm": f"V771_TOP_MASS_{int(target * 100)}",
                "selection_rule": "minimum top-q prefix reaching target joint probability mass",
                "selected_sequences": rank, "probability_mass": mass, "stake_yuan": 2 * rank,
                "status": "SELECTED",
            })
        band = [item for item in sequences if item["sp_band_all_legs"]][:648]
        summary.append({
            "group_id": group_id, "arm": "SP_BAND_ONLY_2_5_4_5_CAP648",
            "selection_rule": "all seven selected p34 quotes inclusive in [2.5,4.5], then top joint-q; cap 648",
            "selected_sequences": len(band), "probability_mass": sum(item["q"] for item in band),
            "stake_yuan": 2 * len(band), "status": "NO_BET_EMPTY" if not band else "SELECTED",
        })
        k80, _ = first_at[0.80]
        k80_rows = sequences[:k80]
        for rank, item in enumerate(k80_rows, 1):
            mass_value.append({"group_id": group_id, "rank": rank, **item})
        # Pareto maximizes q and quote-based ER.  Equal points retain the first
        # canonical code exactly once; it is diagnostic, not a selection rule.
        running_best_er = -1.0
        for rank, item in enumerate(k80_rows, 1):
            if item["er_quote"] > running_best_er:
                pareto.append({"group_id": group_id, "rank": rank, **item})
                running_best_er = item["er_quote"]
    return summary, mass_value, pareto


def prospective_receipt() -> dict[str, Any]:
    """One-line outcome-free availability record for the next issue, if present.

    It intentionally reports availability only.  It does not run the model or
    enumerate a portfolio for a future issue.
    """
    live = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
    live.row_factory = sqlite3.Row
    candidates = live.execute(
        """
        SELECT DISTINCT issue FROM matches
        WHERE CAST(issue AS INTEGER) > 26079
        ORDER BY CAST(issue AS INTEGER)
        """
    ).fetchall()
    live.close()
    if not candidates:
        return {"next_issue": "", "status": "NO_NEW_ISSUE_AVAILABLE", "detail": "No issue ID strictly greater than 26079 exists in matches."}
    issue = str(candidates[0]["issue"])
    return {
        "next_issue": issue,
        "status": "AVAILABILITY_UNASSESSED_NO_OUTCOME_JOIN",
        "detail": "A newer issue exists; this Gate-B receipt does not create or enumerate a prospective portfolio.",
    }


def run() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    gate_card, gate_rows, gate_hashes = read_gate_a()
    vectors, surface_rows, drift_rows = source_vectors(gate_rows)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for vector in vectors:
        groups[vector["group_id"]].append(vector)
    if tuple(groups) != EXPECTED_GROUPS or any(len(legs) != 7 for legs in groups.values()):
        raise RuntimeError("selected groups were not preserved")
    for legs in groups.values():
        legs.sort(key=lambda item: item["leg_no"])
    sequences = {group_id: enumerate_group(legs) for group_id, legs in groups.items()}
    summary, mass_value, pareto = frontiers(sequences)
    ranking_rows = [
        {"variant_label": NUMERICAL_VARIANT, "group_id": group_id, "rank": rank, "codes": item["codes"], "q": item["q"]}
        for group_id in EXPECTED_GROUPS for rank, item in enumerate(sequences[group_id], 1)
    ]
    sp_band_selected = [
        {
            "variant_label": NUMERICAL_VARIANT, "group_id": group_id,
            "sp_band_rank": rank, "codes": item["codes"], "q": item["q"],
        }
        for group_id in EXPECTED_GROUPS
        for rank, item in enumerate([row for row in sequences[group_id] if row["sp_band_all_legs"]][:648], 1)
    ]
    for row in summary:
        row["variant_label"] = NUMERICAL_VARIANT
    for row in mass_value:
        row["variant_label"] = NUMERICAL_VARIANT
    for row in pareto:
        row["variant_label"] = NUMERICAL_VARIANT
    leg_fields = [
        "group_id", "issue", "leg_no", "match_id", "match_idx", "fid", "home", "away", "handicap_line",
        "kickoff_utc", "common_cutoff_utc", "p3", "p1", "p0", "entropy_nats", "top2_mass",
        "v771_grid_pre_normalization_mass", "v771_grid_dropped_mass",
    ] + [f"diag_{name}" for name in sorted(vectors[0]["diagnostics"])]
    leg_rows = []
    for item in vectors:
        flat = {key: item[key] for key in leg_fields if key in item}
        flat["variant_label"] = NUMERICAL_VARIANT
        flat.update({f"diag_{key}": value for key, value in item["diagnostics"].items()})
        leg_rows.append(flat)
    auxiliary_non_effect = [
        {
            "distribution_variant_label": "V771_SCORE_OTHER_TAIL_PROPORTIONAL",
            "auxiliary_diagnostic_label": "V771_AUX_MIDBAND_PAIR_SUM_NON_N7",
            "group_id": item["group_id"], "match_id": item["match_id"],
            "auxiliary_mode": item["diagnostics"]["auxiliary_mode"],
            "p3_before_auxiliary": item["p3"], "p1_before_auxiliary": item["p1"], "p0_before_auxiliary": item["p0"],
            "p3_after_auxiliary": item["p3"], "p1_after_auxiliary": item["p1"], "p0_after_auxiliary": item["p0"],
            "exact_vector_equality": True,
            "structural_reason": "V7.7.1 Step 11 auxiliary board is computed after final score distribution and handicap 3/1/0 mapping; it cannot mutate p3/p1/p0.",
        }
        for item in vectors
    ]
    input_vectors = {
        "contract": {
            "outcome_scope": "OUTCOME_UNEXPOSED",
            "allowed_tables": {"beidan_live.db": ["matches", "snapshots"], "500_bjdc.sqlite": ["live_market_sp_snapshots"]},
            "prohibited": ["settlements", "matches score/result fields", "final SP", "500 completed pages", "outcome artifacts"],
            "selection_factor": TAX_FACTOR,
            "sp_band_inclusive": list(SP_BAND),
        },
        "legs": vectors,
    }
    variant_contracts = {
        "V771_SCORE_OTHER_TAIL_PROPORTIONAL": {
            "variant_label": "V771_SCORE_OTHER_TAIL_PROPORTIONAL",
            "manual_reference": "V7.7.1 Step 6 / Step 9 score-other aggregate markets",
            "fixed_rule": "Allocate each other-score market mass over its internal 45-grid scores in proportion to tail-corrected model mass; use equal split only if that internal model mass is zero.",
            "effect_on_n7_probability": "YES",
        },
        "V771_AUX_MIDBAND_PAIR_SUM": {
            "diagnostic_label": "V771_AUX_MIDBAND_PAIR_SUM_NON_N7",
            "manual_reference": "V7.7.1 Step 11, 10% < P_big < 20%",
            "fixed_rule": "Compare the two-score large and small auxiliary candidates by their summed Bayes_Score.",
            "effect_on_n7_probability": "NO; auxiliary board is formed after the final distribution, so this rule cannot change p3/p1/p0 or N7 sequence ranking.",
        },
        "numerical_topmass_variant": NUMERICAL_VARIANT,
        "no_counterfactual_variant": "The supplied manual provides no alternate formula for either rule. A divergent arm would be invented, so none is generated.",
    }
    write_json(OUT / "gate_a_verification.json", {"gate_a_sha256s": gate_hashes, "gate_a_source_card_sha256": sha256(GATE_A / "source_card.json"), "accepted_group_ids": list(EXPECTED_GROUPS), "gate_a_disposition": gate_card["disposition"]})
    write_json(OUT / "v771_variant_contracts.json", variant_contracts)
    write_json(OUT / "selected_input_vectors.json", input_vectors)
    write_json(OUT / "prospective_availability_receipt.json", prospective_receipt())
    write_csv(OUT / "surface_snapshot_audit.csv", surface_rows, ["group_id", "match_id", "surface", "snapshot_utc", "common_cutoff_utc", "age_seconds", "strictly_pre_kickoff"])
    write_csv(OUT / "p34_quote_age_drift.csv", drift_rows, ["group_id", "match_id", "code", "selected_quote", "selected_snapshot_utc", "selected_age_seconds", "prior_snapshot_utc", "prior_quote", "absolute_drift", "relative_drift"])
    write_csv(OUT / "leg_predictions.csv", leg_rows, ["variant_label", *leg_fields])
    write_csv(OUT / "auxiliary_non_effect_check.csv", auxiliary_non_effect, ["distribution_variant_label", "auxiliary_diagnostic_label", "group_id", "match_id", "auxiliary_mode", "p3_before_auxiliary", "p1_before_auxiliary", "p0_before_auxiliary", "p3_after_auxiliary", "p1_after_auxiliary", "p0_after_auxiliary", "exact_vector_equality", "structural_reason"])
    write_csv(OUT / "sequence_rankings.csv", ranking_rows, ["variant_label", "group_id", "rank", "codes", "q"])
    write_csv(OUT / "sp_band_selected_sequences.csv", sp_band_selected, ["variant_label", "group_id", "sp_band_rank", "codes", "q"])
    write_csv(OUT / "arm_summary.csv", summary, ["variant_label", "group_id", "arm", "selection_rule", "selected_sequences", "probability_mass", "stake_yuan", "status"])
    write_csv(OUT / "mass_value_k80.csv", mass_value, ["variant_label", "group_id", "rank", "codes", "q", "quote_product", "r_quote_after_factor", "er_quote", "sp_band_all_legs"])
    write_csv(OUT / "pareto_k80.csv", pareto, ["variant_label", "group_id", "rank", "codes", "q", "quote_product", "r_quote_after_factor", "er_quote", "sp_band_all_legs"])
    shutil.copy2(Path(__file__), OUT / "freeze_bj76_gateb_preoutcome.py")
    source_ref = SHARED / "src/score_prediction/v771.py"
    shutil.copy2(source_ref, OUT / "v771_reference.py")
    files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="utf-8")
    manifest = {
        "issue": 76,
        "gate": "G1_GATE_B_PREOUTCOME_FREEZE",
        "mode": "OUTCOME_UNEXPOSED",
        "group_ids": list(EXPECTED_GROUPS),
        "group_count": 4,
        "leg_count": len(vectors),
        "sequences_per_group": 2187,
        "outcome_attestation": "No results, settlements, final SP, completed pages, matches score/result fields, or outcome artifacts were read.",
        # The manifest cannot truthfully hash itself (or the checksum list
        # which hashes it).  SHA256SUMS below is the exact cover list for both
        # of those files; this field is only the non-self artifact inventory.
        "sha256s_nonself": {
            path.name: sha256(path)
            for path in sorted(OUT.iterdir())
            if path.is_file() and path.name not in {"SHA256SUMS", "manifest.json"}
        },
        "self_hash_rule": "manifest.json and SHA256SUMS are covered by SHA256SUMS only, avoiding a recursive hash claim.",
    }
    write_json(OUT / "manifest.json", manifest)
    # Manifest must itself be included in the final exact cover list.
    files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="utf-8")


if __name__ == "__main__":
    run()
