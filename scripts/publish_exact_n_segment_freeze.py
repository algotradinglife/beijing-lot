#!/usr/bin/env python3
"""Append-only exact-N freeze publisher for BJ-BET-FREEZE-001.

Segment 1's original files remain historical pre-freeze evidence.  This command
is for prospective segments only: one invocation makes one manual/automatic
freeze event and a second invocation for the same event key fails closed.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, os, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import estimate_segment_betting_plan as plan  # noqa: E402
from scripts import replay_rolling_segment_n_tickets as rolling  # noqa: E402

HKT = ZoneInfo("Asia/Hong_Kong")
N_VALUES, BUDGETS = (3, 4, 5, 6, 7), (512, 768, 1024)
DEFAULT_LEDGER = ROOT / "results/research/exact_n_segment_freeze_v1/ledger"
DEFAULT_SCORE_ROOT = ROOT / "results/data_collection/correct_score_price_history_v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: object) -> str: return hashlib.sha256(canonical(value)).hexdigest()
def file_hash(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def hkt(value: str) -> datetime:
    d = datetime.fromisoformat(value) if value else datetime.now(timezone.utc)
    return (d if d.tzinfo else d.replace(tzinfo=HKT)).astimezone(HKT)


def score_audit(root: Path, issue: str, indices: tuple[int, ...], decision_at: datetime) -> tuple[dict[str, object], list[dict[str, object]]]:
    batches = sorted((root / issue).glob("*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not batches:
        return {"capture_status": "missing_capture_bundle"}, [{"match_idx": i, "eligible": False, "reasons": ["missing_p42_capture_bundle"]} for i in indices]
    manifest_path = batches[0]; batch = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    rows: dict[int, dict[str, str]] = {}
    snapshots = batch / "snapshots.csv"
    if snapshots.exists():
        with snapshots.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                idx = int(row["match_idx"])
                # Latest pre-decision observation is the only candidate.
                try: observed = hkt(row.get("snapshot_ts_hkt", ""))
                except ValueError: continue
                if observed <= decision_at and (idx not in rows or observed > hkt(rows[idx].get("snapshot_ts_hkt", ""))): rows[idx] = row
    audits: list[dict[str, object]] = []
    for idx in indices:
        row, reasons = rows.get(idx), []
        if not row: reasons.append("missing_predecision_p42_snapshot")
        else:
            for column, reason, wanted in (("complete", "incomplete_market", "1"), ("exact_score_complete", "incomplete_exact_score_catalogue", "1"), ("phase", "non_prematch_phase", "pregame")):
                if row.get(column) != wanted: reasons.append(reason)
            if not row.get("raw_payload_sha256"): reasons.append("missing_raw_payload_hash")
            raw = batch / row.get("raw_file", "")
            if not raw.exists(): reasons.append("missing_raw_payload")
            elif row.get("raw_payload_sha256") != file_hash(raw): reasons.append("raw_payload_hash_mismatch")
            # This capture schema has no immutable sale/cutoff clock or calibrated
            # score-model input; do not infer either from a three-way artifact.
            reasons.extend(["missing_sale_or_cutoff_clock", "missing_calibrated_correct_score_model_input"])
        audits.append({"match_idx": idx, "eligible": not reasons, "reasons": reasons,
                       "snapshot_id": row.get("snapshot_id", "") if row else "", "snapshot_ts_hkt": row.get("snapshot_ts_hkt", "") if row else "",
                       "raw_payload_sha256": row.get("raw_payload_sha256", "") if row else ""})
    return {"capture_manifest": str(manifest_path), "capture_manifest_sha256": file_hash(manifest_path), "capture_batch_id": manifest.get("capture_batch_id", "")}, audits


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--issue", required=True); p.add_argument("--segment", type=int, required=True)
    p.add_argument("--manifest", type=Path, required=True); p.add_argument("--structured-csv", type=Path, required=True)
    p.add_argument("--db", type=Path, default=ROOT / "data/derived/500_bjdc/500_bjdc.sqlite")
    p.add_argument("--output-root", type=Path, default=ROOT / "results/exact_n_segment_freeze")
    p.add_argument("--ledger-root", type=Path, default=DEFAULT_LEDGER); p.add_argument("--correct-score-root", type=Path, default=DEFAULT_SCORE_ROOT)
    p.add_argument("--decision-at-hkt", default="", help="manual freeze time; defaults to now")
    p.add_argument("--sample-attempts", type=int, default=12000); p.add_argument("--sample-seed", type=int, default=20260707)
    a = p.parse_args(); decision_at = hkt(a.decision_at_hkt)
    manifest = json.loads(a.manifest.read_text()); claimed = manifest.pop("manifest_sha256", "")
    if manifest.get("issue") != str(a.issue) or claimed != digest(manifest): raise SystemExit("fail closed: invalid natural-day manifest")
    seg = next((x for x in manifest["segments"] if int(x["segment_idx"]) == a.segment), None)
    if not seg: raise SystemExit("fail closed: segment absent from manifest")
    scheduled = hkt(seg["freeze_at"])
    if decision_at > scheduled: raise SystemExit("MISSED_FREEZE: decision is after absolute freeze")
    expected = tuple(int(x) for x in seg["match_indices"]); source_sha = file_hash(a.structured_csv)
    event_key = digest({"issue": str(a.issue), "segment_idx": a.segment, "manual_frozen_at": decision_at.isoformat(timespec="seconds"), "manifest_sha256": claimed, "decision_input_sha256": source_sha})
    ledger = a.ledger_root / f"{event_key}.json"
    if ledger.exists(): raise SystemExit(f"fail closed: freeze event already bound: {event_key}")
    legs = rolling.load_legs(a.structured_csv, a.db, issue=a.issue); by_idx = {x.match_idx: x for x in legs}
    if set(by_idx) != set(manifest["denominator_match_indices"]) or any(i not in by_idx for i in expected): raise SystemExit("fail closed: input membership mismatch")
    metrics = [x for leg in (by_idx[i] for i in expected) if (x := plan.leg_metrics(leg, "active")) is not None]
    common = {"capability_id": "BJ-BET-FREEZE-001", "issue": str(a.issue), "segment_idx": a.segment, "segment_match_indices": list(expected), "segment_manifest_sha256": claimed, "decision_input_sha256": source_sha, "scheduled_freeze_at": scheduled.isoformat(timespec="seconds"), "manual_frozen_at": decision_at.isoformat(timespec="seconds"), "effective_decision_at": decision_at.isoformat(timespec="seconds"), "event_key": event_key, "exact_n": True}
    a.output_root.mkdir(parents=True, exist_ok=True); stage = Path(tempfile.mkdtemp(prefix="exact_n_", dir=a.output_root)); payloads = []
    try:
        for budget in BUDGETS:
            for n in N_VALUES:
                units = budget / 2; candidates = plan.generate_candidates(metrics=metrics, segment_idx=a.segment, arm="active", n_value=n, budget_units=units, sample_attempts=a.sample_attempts, seed=plan.stable_seed(a.sample_seed, a.segment, budget, n))
                selected = plan.select_bundles([x for x in candidates if len(x.match_indices) == n], budget_units=units, max_overlap=max(0, n-2), positive_ev_only=True, max_bundle_cost_units=units * .4)
                staked, cost, reason = plan.apply_stake_mode(selected, budget_units=units, stake_mode="scale_to_budget", max_bundle_cost_units=units * .4)
                tickets = [{"match_indices": list(x.candidate.match_indices), "leg_codes": list(x.candidate.leg_codes), "actual_n": len(x.candidate.match_indices), "stake_multiplier": x.stake_multiplier, "cost_yuan": x.candidate.cost_units*x.stake_multiplier*2} for x in staked]
                if any(t["actual_n"] != n for t in tickets): raise SystemExit("fail closed: exact-N mismatch")
                actual = cost*2; payload = {**common, "plan_id": f"{a.issue}_s{a.segment}_n{n}_b{budget}_{event_key[:12]}", "requested_n": n, "artifact_n": n, "recommended_n": n, "requested_budget_yuan": budget, "actual_budget_yuan": actual, "unused_budget_yuan": budget-actual, "budget_utilization": actual/budget if budget else 0, "status": "FROZEN_EXACT_N" if tickets else "UNAVAILABLE_EXACT_N", "tickets": tickets, "reason": reason if tickets else "no_eligible_exact_n_candidate_or_budgeted_bundle"}; payload["sha256"] = digest(payload)
                name = f"exact_n_{n}_budget_{budget}.json"; (stage/name).write_bytes(canonical(payload)+b"\n"); payloads.append({"file": name, "sha256": payload["sha256"], "requested_n": n, "requested_budget_yuan": budget, "status": payload["status"]})
        score_meta, match_audit = score_audit(a.correct_score_root, str(a.issue), expected, decision_at)
        score = {**common, **score_meta, "artifact_type": "correct_score_paper", "status": "UNAVAILABLE_CORRECT_SCORE_PLAN", "execution_enabled": False, "frontend_selectable": False, "roi_authorized": False, "per_match_audit": match_audit}; score["sha256"] = digest(score)
        (stage/"correct_score_audit.json").write_bytes(canonical(score)+b"\n"); payloads.append({"file":"correct_score_audit.json","sha256":score["sha256"],"status":score["status"]})
        top = {**common, "schema_version":"exact_n_budget_matrix_freeze_v2", "artifacts":payloads, "immutable":True}; top["sha256"] = digest(top)
        (stage/"manifest.json").write_bytes(canonical(top)+b"\n")
        (stage/"SHA256SUMS").write_text("\n".join(f"{file_hash(stage/x['file'])}  {x['file']}" for x in payloads)+f"\n{file_hash(stage/'manifest.json')}  manifest.json\n")
        destination = a.output_root / str(a.issue) / f"segment_{a.segment}" / event_key; destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists(): raise SystemExit("fail closed: content-addressed output exists")
        os.replace(stage, destination); a.ledger_root.mkdir(parents=True, exist_ok=True)
        ledger.write_bytes(canonical({"schema_version":"exact_n_freeze_ledger_v1", **common, "artifact_manifest":str(destination/'manifest.json'), "artifact_manifest_sha256":file_hash(destination/'manifest.json')})+b"\n")
        print(json.dumps({"event_key":event_key,"destination":str(destination),"variants":15,"ledger":str(ledger)}))
    except BaseException: shutil.rmtree(stage, ignore_errors=True); raise

if __name__ == "__main__": main()
