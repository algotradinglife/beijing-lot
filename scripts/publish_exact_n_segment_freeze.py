#!/usr/bin/env python3
"""Freeze immutable BJ-BET-FREEZE-001 exact-N alternatives from one input snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import estimate_segment_betting_plan as plan  # noqa: E402
from scripts import replay_rolling_segment_n_tickets as rolling  # noqa: E402

HKT = ZoneInfo("Asia/Hong_Kong")
N_VALUES = (3, 4, 5, 6, 7)


def digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def now_hkt(value: str) -> datetime:
    current = datetime.fromisoformat(value) if value else datetime.now(timezone.utc)
    return (current if current.tzinfo else current.replace(tzinfo=HKT)).astimezone(HKT)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--issue", required=True)
    p.add_argument("--segment", type=int, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--structured-csv", type=Path, required=True)
    p.add_argument("--db", type=Path, default=ROOT / "data/derived/500_bjdc/500_bjdc.sqlite")
    p.add_argument("--output-root", type=Path, default=ROOT / "results/exact_n_segment_freeze")
    p.add_argument("--now-hkt", default="")
    p.add_argument("--sample-attempts", type=int, default=12000)
    p.add_argument("--sample-seed", type=int, default=20260707)
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text())
    declared_manifest_sha = str(manifest.get("manifest_sha256") or "")
    manifest_without_hash = dict(manifest)
    manifest_without_hash.pop("manifest_sha256", None)
    if (manifest.get("issue") != str(args.issue) or not declared_manifest_sha
            or digest(manifest_without_hash) != declared_manifest_sha):
        raise SystemExit("fail closed: invalid natural-day manifest identity")
    seg = next((x for x in manifest["segments"] if int(x["segment_idx"]) == args.segment), None)
    if not seg:
        raise SystemExit("fail closed: requested segment absent from manifest")
    freeze_at = datetime.fromisoformat(seg["freeze_at"])
    generated_at = now_hkt(args.now_hkt)
    if generated_at >= freeze_at:
        raise SystemExit("MISSED_FREEZE: refusing to backfill an exact-N artifact after absolute freeze")
    source_bytes = args.structured_csv.read_bytes()
    input_sha = hashlib.sha256(source_bytes).hexdigest()
    legs = rolling.load_legs(args.structured_csv, args.db, issue=args.issue)
    expected = tuple(int(v) for v in seg["match_indices"])
    by_idx = {leg.match_idx: leg for leg in legs}
    if set(by_idx) != set(manifest["denominator_match_indices"]) or any(i not in by_idx for i in expected):
        raise SystemExit("fail closed: decision input does not exactly cover manifest denominator")
    selected_legs = [by_idx[i] for i in expected]
    metrics = [item for leg in selected_legs if (item := plan.leg_metrics(leg, "active")) is not None]
    common = {"capability_id": "BJ-BET-FREEZE-001", "issue": str(args.issue), "segment_idx": args.segment,
              "segment_match_indices": list(expected), "segment_manifest_sha256": manifest["manifest_sha256"],
              "decision_input_sha256": input_sha, "decision_input_path": str(args.structured_csv),
              "freeze_at": freeze_at.isoformat(timespec="seconds"), "generated_at_hkt": generated_at.isoformat(timespec="seconds"),
              "segment_budget_yuan": 1000, "stake_yuan_per_ticket": 2, "exact_n": True}
    stamp = generated_at.strftime("%Y%m%dT%H%M%S%z")
    dest = args.output_root / str(args.issue) / f"segment_{args.segment}" / stamp
    if dest.exists():
        raise SystemExit("fail closed: immutable destination already exists")
    stage = Path(tempfile.mkdtemp(prefix="exact_n_freeze_", dir=str(dest.parent if dest.parent.exists() else args.output_root)))
    try:
        payloads = []
        budget_units = 500.0
        for requested_n in N_VALUES:
            candidates = plan.generate_candidates(metrics=metrics, segment_idx=args.segment, arm="active", n_value=requested_n,
                                                   budget_units=budget_units, sample_attempts=args.sample_attempts,
                                                   seed=plan.stable_seed(args.sample_seed, args.segment, "active", requested_n))
            candidates = [x for x in candidates if len(x.match_indices) == requested_n]
            selected = plan.select_bundles(candidates, budget_units=budget_units, max_overlap=max(0, requested_n - 2), positive_ev_only=True, max_bundle_cost_units=200.0)
            staked, cost, stake_reason = plan.apply_stake_mode(selected, budget_units=budget_units, stake_mode="scale_to_budget", max_bundle_cost_units=200.0)
            tickets = [{"match_indices": list(x.candidate.match_indices), "leg_codes": list(x.candidate.leg_codes), "actual_n": len(x.candidate.match_indices), "stake_multiplier": x.stake_multiplier, "cost_yuan": x.candidate.cost_units * x.stake_multiplier * 2} for x in staked]
            if any(t["actual_n"] != requested_n for t in tickets):
                raise SystemExit("fail closed: exact-N ticket-leg mismatch")
            status = "FROZEN_EXACT_N" if tickets else "UNAVAILABLE_EXACT_N"
            payload = {**common, "plan_id": f"{args.issue}_s{args.segment}_exact_n{requested_n}_{stamp}", "requested_n": requested_n,
                       "artifact_n": requested_n, "recommended_n": requested_n, "status": status,
                       "tickets": tickets, "ticket_count": len(tickets), "base_cost_yuan": sum(x.candidate.cost_units * 2 for x in staked),
                       "budget_cost_yuan": cost * 2, "reason": stake_reason if tickets else "no_eligible_exact_n_candidate_or_budgeted_bundle"}
            payload["sha256"] = digest(payload)
            name = f"exact_n_{requested_n}.json"
            (stage / name).write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            payloads.append({"file": name, "sha256": payload["sha256"], "status": status, "requested_n": requested_n})
        # Correct score has no complete, fresh p42 model/market package.  This is
        # intentionally an unavailable paper record, never a ticket proposal.
        score = {**common, "artifact_type": "correct_score_paper", "status": "UNAVAILABLE_CORRECT_SCORE_PLAN", "execution_enabled": False,
                 "frontend_selectable": False, "roi_authorized": False, "included_matches": [],
                 "excluded_matches": [{"match_idx": i, "reason": "no_verified_fresh_complete_p42_snapshot_and_calibrated_correct_score_contract"} for i in expected]}
        score["sha256"] = digest(score)
        (stage / "correct_score_paper.json").write_text(json.dumps(score, sort_keys=True, separators=(",", ":")) + "\n")
        payloads.append({"file": "correct_score_paper.json", "sha256": score["sha256"], "status": score["status"]})
        top = {**common, "schema_version": "exact_n_segment_freeze_v1", "artifacts": payloads,
               "manifest_input_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(), "immutable": True}
        top["sha256"] = digest(top)
        (stage / "manifest.json").write_text(json.dumps(top, sort_keys=True, separators=(",", ":")) + "\n")
        sums = [f"{hashlib.sha256((stage / item['file']).read_bytes()).hexdigest()}  {item['file']}" for item in payloads]
        sums.append(f"{hashlib.sha256((stage / 'manifest.json').read_bytes()).hexdigest()}  manifest.json")
        (stage / "SHA256SUMS").write_text("\n".join(sums) + "\n")
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage, dest)
        print(json.dumps({"destination": str(dest), "sha256": top["sha256"], "statuses": [(x.get("requested_n", "correct_score"), x["status"]) for x in payloads]}))
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
