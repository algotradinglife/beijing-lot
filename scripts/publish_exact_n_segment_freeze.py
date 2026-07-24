#!/usr/bin/env python3
"""Append-only exact-N freeze publisher for BJ-BET-FREEZE-001.

Segment 1's original files remain historical pre-freeze evidence.  This command
is for prospective segments only: one invocation makes one manual/automatic
freeze event and a second invocation for the same event key fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import estimate_segment_betting_plan as plan  # noqa: E402
from scripts import replay_rolling_segment_n_tickets as rolling  # noqa: E402
from scripts.manage_correct_score_price_history import (  # noqa: E402
    CAPTURE_SCHEMA,
    read_capture_bundles,
    verify_correct_score_bundle,
)
from scripts.verify_exact_n_freeze import (  # noqa: E402
    verify_directory as verify_exact_n_directory,
)
from src.correct_score_price_history import (  # noqa: E402
    CorrectScorePriceError,
    select_latest_complete,
)
from src.natural_day_manifest import (  # noqa: E402
    NaturalDayManifestError,
    load_published_manifest,
    segment_membership,
    verify_manifest,
    verify_operational_windows,
)
from src.structured_input_receipt import (  # noqa: E402
    receipt_path,
    verify_receipt,
)

HKT = ZoneInfo("Asia/Hong_Kong")
N_VALUES, BUDGETS = (3, 4, 5, 6, 7), (512, 768, 1024)
OPEN_SALE_STATES = frozenset({"OPEN", "ON_SALE", "OPEN_PREGAME"})
REQUIRED_SCORE_CODES = frozenset(
    {f"{home}-{away}" for home in range(5) for away in range(5)}
    | {"home_other", "draw_other", "away_other"}
)
DEFAULT_LEDGER = ROOT / "results/research/exact_n_segment_freeze_v1/ledger"
DEFAULT_SCORE_ROOT = ROOT / "results/data_collection/correct_score_price_history_v1"


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hkt(value: str) -> datetime:
    d = datetime.fromisoformat(value) if value else datetime.now(timezone.utc)
    return (d if d.tzinfo else d.replace(tzinfo=HKT)).astimezone(HKT)


def require_pre_freeze_wall_clock(
    scheduled: datetime, observed_at: datetime | None = None
) -> datetime:
    """Return the trusted invocation clock, refusing any post-deadline backfill."""
    observed = (observed_at or datetime.now(timezone.utc)).astimezone(HKT)
    if observed > scheduled:
        raise ValueError("MISSED_FREEZE: publisher wall clock is after absolute freeze")
    return observed


def require_canonical_segment_contract(
    db_path: Path,
    *,
    issue: str,
    supplied_manifest: dict[str, object],
) -> dict[str, object]:
    """Bind manual and automatic publication to the SQLite source of truth."""
    supplied_sha = verify_manifest(supplied_manifest)
    with sqlite3.connect(db_path) as connection:
        published = load_published_manifest(connection, str(issue))
        if published is None:
            raise NaturalDayManifestError(
                "canonical natural-day publication is missing"
            )
        verify_operational_windows(connection, published)
    if (
        str(supplied_manifest.get("issue")) != str(issue)
        or supplied_sha != str(published["manifest_sha256"])
        or segment_membership(supplied_manifest) != segment_membership(published)
        or [
            int(value)
            for value in supplied_manifest.get("denominator_match_indices", [])
        ]
        != [int(value) for value in published["denominator_match_indices"]]
    ):
        raise NaturalDayManifestError(
            "supplied manifest differs from canonical SQLite publication"
        )
    return published


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(payload) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def promote_verified_package(
    *,
    stage: Path,
    destination: Path,
    ledger: Path,
    ledger_payload: dict[str, object],
) -> dict[str, object]:
    """Verify before reservation and again before making the ledger authoritative."""
    staged_verification = verify_exact_n_directory(stage)
    if staged_verification.get("status") != "PASS":
        raise RuntimeError("fail closed: staged exact-N package verification failed")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError("fail closed: content-addressed output exists")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    reserved = {
        **ledger_payload,
        "state": "RESERVED",
        "staged_package_verification": staged_verification,
    }
    fd = os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(reserved) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())

    os.replace(stage, destination)
    try:
        visible_verification = verify_exact_n_directory(destination)
        if (
            visible_verification.get("status") != "PASS"
            or visible_verification != staged_verification
        ):
            raise ValueError("visible verification differs from staged receipt")
    except Exception as exc:
        _atomic_write_json(
            ledger,
            {
                **ledger_payload,
                "state": "VERIFICATION_FAILED",
                "verification_phase": "VISIBLE_PACKAGE",
                "verification_error": f"{type(exc).__name__}: {exc}",
                "staged_package_verification": staged_verification,
            },
        )
        raise RuntimeError(
            "fail closed: visible exact-N package verification failed"
        ) from exc

    _atomic_write_json(
        ledger,
        {
            **ledger_payload,
            "state": "PUBLISHED",
            "artifact_manifest_sha256": file_hash(destination / "manifest.json"),
            "package_sha256s_sha256": file_hash(destination / "SHA256SUMS"),
            "package_verification": visible_verification,
        },
    )
    return visible_verification


def _predecision_fetch(row: dict[str, object], decision_at: datetime) -> bool:
    try:
        fetched = datetime.fromisoformat(str(row.get("fetched_at_utc") or ""))
    except ValueError:
        return False
    if fetched.tzinfo is None:
        return False
    return fetched.astimezone(timezone.utc) <= decision_at.astimezone(timezone.utc)


def score_audit(
    root: Path, issue: str, indices: tuple[int, ...], decision_at: datetime
) -> tuple[dict[str, object], list[dict[str, object]]]:
    required = {
        "manifest.json",
        "snapshots.csv",
        "prices.csv",
        "mapping_inventory.csv",
        "page_inventory.csv",
        "SHA256SUMS",
    }
    bundles: list[Path] = []
    bundle_receipts: list[dict[str, object]] = []
    for candidate in sorted((root / issue).glob("*/manifest.json")):
        batch = candidate.parent
        if not required.issubset(
            {path.name for path in batch.iterdir() if path.is_file()}
        ):
            continue
        try:
            bound_files = {
                line.split("  ", 1)[1]
                for line in (batch / "SHA256SUMS")
                .read_text(encoding="utf-8")
                .splitlines()
                if "  " in line
            }
        except OSError:
            continue
        if not (required - {"SHA256SUMS"}).issubset(bound_files):
            continue
        try:
            verification = verify_correct_score_bundle(
                batch, expected_schema=CAPTURE_SCHEMA
            )
        except (OSError, ValueError, CorrectScorePriceError):
            continue
        manifest = verification["manifest"]
        if (
            manifest.get("provider") != "nowscore"
            or manifest.get("bookmaker_key") != "crown"
        ):
            continue
        bundles.append(batch)
        bundle_receipts.append(
            {
                "path": str(batch.expanduser().resolve()),
                "capture_batch_id": str(manifest.get("capture_batch_id") or ""),
                "manifest_sha256": file_hash(candidate),
                "sha256s_sha256": str(verification["sha256s_sha256"]),
            }
        )
    if not bundles:
        return {
            "capture_status": "no_strict_sha256_verified_capture_bundle",
            "verified_capture_bundles": [],
            "selection_rule": (
                "latest complete pregame vector per match across all verified "
                "bundles at or before effective_decision_at"
            ),
        }, [
            {
                "match_idx": idx,
                "eligible": False,
                "reasons": ["no_strict_sha256_verified_capture_bundle"],
                "complete_price_vector": [],
            }
            for idx in indices
        ]

    snapshots, prices, _pages, _metadata = read_capture_bundles(bundles)
    snapshots = [row for row in snapshots if row.get("issue") == issue]
    audits: list[dict[str, object]] = []
    for idx in indices:
        all_candidates = [
            row for row in snapshots if int(row.get("match_idx") or 0) == idx
        ]
        candidates = [
            row for row in all_candidates if _predecision_fetch(row, decision_at)
        ]
        selected, reason = select_latest_complete(candidates, decision_at)
        if selected is None:
            if all_candidates and not candidates:
                reason = "no_snapshot_with_predecision_fetch_clock"
            audits.append(
                {
                    "match_idx": idx,
                    "eligible": False,
                    "reasons": [reason or "missing_predecision_p42_snapshot"],
                    "complete_price_vector": [],
                }
            )
            continue
        vector = [
            {
                "outcome_code": row["outcome_code"],
                "outcome_group": row["outcome_group"],
                "outcome_label": row["outcome_label"],
                "sp": row["sp"],
            }
            for row in prices
            if row.get("snapshot_id") == selected.get("snapshot_id")
            and row.get("_capture_bundle") == selected.get("_capture_bundle")
        ]
        vector.sort(key=lambda row: str(row["outcome_code"]))
        reasons: list[str] = []
        if len(vector) != int(selected.get("outcome_count") or 0):
            reasons.append("incomplete_price_vector")
        vector_codes = [str(row["outcome_code"]) for row in vector]
        if (
            len(vector_codes) != len(set(vector_codes))
            or set(vector_codes) != REQUIRED_SCORE_CODES
        ):
            reasons.append("incomplete_required_price_vector")
        sale_state = str(
            selected.get("sale_state") or selected.get("market_sale_state") or ""
        )
        if not sale_state:
            reasons.append("missing_source_sale_state")
        elif sale_state.upper() not in OPEN_SALE_STATES:
            reasons.append("source_sale_state_not_open")
        model_input = {
            "issue": issue,
            "match_idx": idx,
            "snapshot_id": selected["snapshot_id"],
            "outcome_schema_sha256": selected["outcome_schema_sha256"],
            "prices": vector,
        }
        audits.append(
            {
                "match_idx": idx,
                "eligible": not reasons,
                "reasons": reasons,
                "snapshot_id": selected["snapshot_id"],
                "snapshot_ts_hkt": selected["snapshot_ts_hkt"],
                "source_time_raw": selected["source_time_raw"],
                "source_timestamp_scope": selected.get("source_timestamp_scope", ""),
                "fetched_at_utc": selected["fetched_at_utc"],
                "sale_state": sale_state or "UNKNOWN_NOT_SOURCE_OBSERVED",
                "phase": selected["phase"],
                "raw_payload_sha256": selected["raw_payload_sha256"],
                "raw_row_sha256": selected["raw_row_sha256"],
                "capture_batch_id": selected["capture_batch_id"],
                "capture_bundle": selected["_capture_bundle"],
                "capture_bundle_sha256s_sha256": selected["_capture_bundle_sha"],
                "outcome_schema_sha256": selected["outcome_schema_sha256"],
                "complete_price_vector": vector,
                "correct_score_model_input_sha256": digest(model_input),
            }
        )
    return {
        "capture_status": "verified_cross_bundle_asof",
        "verified_capture_bundles": bundle_receipts,
        "selection_rule": (
            "latest complete pregame vector per match across all verified "
            "bundles at or before effective_decision_at"
        ),
    }, audits


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--issue", required=True)
    p.add_argument("--segment", type=int, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--structured-csv", type=Path, required=True)
    p.add_argument(
        "--input-receipt",
        type=Path,
        help="generator receipt; defaults beside --structured-csv",
    )
    p.add_argument(
        "--db", type=Path, default=ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
    )
    p.add_argument(
        "--output-root", type=Path, default=ROOT / "results/exact_n_segment_freeze"
    )
    p.add_argument("--ledger-root", type=Path, default=DEFAULT_LEDGER)
    p.add_argument("--correct-score-root", type=Path, default=DEFAULT_SCORE_ROOT)
    p.add_argument("--sample-attempts", type=int, default=12000)
    p.add_argument("--sample-seed", type=int, default=20260707)
    a = p.parse_args()
    manifest = json.loads(a.manifest.read_text())
    try:
        manifest = require_canonical_segment_contract(
            a.db,
            issue=str(a.issue),
            supplied_manifest=manifest,
        )
        claimed = verify_manifest(manifest)
    except (NaturalDayManifestError, sqlite3.Error) as exc:
        raise SystemExit(
            "fail closed: manifest is not the canonical DB publication"
        ) from exc
    seg = next(
        (x for x in manifest["segments"] if int(x["segment_idx"]) == a.segment), None
    )
    if not seg:
        raise SystemExit("fail closed: segment absent from manifest")
    scheduled = hkt(seg["freeze_at"])
    try:
        decision_at = require_pre_freeze_wall_clock(scheduled)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    expected = tuple(int(x) for x in seg["match_indices"])
    source_sha = file_hash(a.structured_csv)
    input_receipt_path = a.input_receipt or receipt_path(a.structured_csv)
    try:
        source_receipt = verify_receipt(
            a.structured_csv, input_receipt_path, issue=str(a.issue)
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit("fail closed: invalid structured input receipt") from exc
    input_generated_at = source_receipt["generated_at"].astimezone(HKT)
    input_generated_at_text = input_generated_at.isoformat(timespec="microseconds")
    final_refresh_opens_at = scheduled - timedelta(minutes=30)
    if not (final_refresh_opens_at <= input_generated_at <= decision_at):
        raise SystemExit(
            "fail closed: decision input was not generated during the target "
            "segment final legal refresh window"
        )
    # A segment can be frozen only once.  The identity deliberately excludes
    # wall-clock time so retrying with a different timestamp cannot mint a new
    # freeze identity for the same issue/segment.
    event_key = digest({"issue": str(a.issue), "segment_idx": a.segment})
    ledger = a.ledger_root / f"{event_key}.json"
    if ledger.exists():
        raise SystemExit(f"fail closed: freeze event already bound: {event_key}")
    legs = rolling.load_legs(a.structured_csv, a.db, issue=a.issue)
    by_idx = {x.match_idx: x for x in legs}
    if set(by_idx) != set(manifest["denominator_match_indices"]) or any(
        i not in by_idx for i in expected
    ):
        raise SystemExit("fail closed: input membership mismatch")
    metrics = [
        x
        for leg in (by_idx[i] for i in expected)
        if (x := plan.leg_metrics(leg, "active")) is not None
    ]
    input_manifest = {
        "schema_version": "exact_n_decision_input_v1",
        "issue": str(a.issue),
        "segment_idx": a.segment,
        "segment_manifest_sha256": claimed,
        "structured_csv": str(a.structured_csv),
        "structured_csv_sha256": source_sha,
        "structured_csv_size_bytes": a.structured_csv.stat().st_size,
        "denominator_match_indices": [
            int(value) for value in manifest["denominator_match_indices"]
        ],
        "generator_receipt": str(input_receipt_path),
        "generator_receipt_sha256": source_receipt["sha256"],
        "input_generated_at": input_generated_at_text,
        "input_observed_at": decision_at.isoformat(timespec="seconds"),
        "final_refresh_opens_at": final_refresh_opens_at.isoformat(timespec="seconds"),
        "effective_decision_at": decision_at.isoformat(timespec="seconds"),
    }
    input_manifest_sha256 = digest(input_manifest)
    common = {
        "capability_id": "BJ-BET-FREEZE-001",
        "issue": str(a.issue),
        "segment_idx": a.segment,
        "segment_match_indices": list(expected),
        "segment_manifest_sha256": claimed,
        "decision_input_sha256": source_sha,
        "decision_input_manifest_sha256": input_manifest_sha256,
        "decision_input_generated_at": input_generated_at_text,
        "scheduled_freeze_at": scheduled.isoformat(timespec="seconds"),
        "manual_frozen_at": decision_at.isoformat(timespec="seconds"),
        "effective_decision_at": decision_at.isoformat(timespec="seconds"),
        "event_key": event_key,
        "exact_n": True,
    }
    a.output_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="exact_n_", dir=a.output_root))
    payloads = []
    try:
        (stage / "structured_input.csv").write_bytes(a.structured_csv.read_bytes())
        (stage / "structured_input_receipt.json").write_bytes(
            canonical(
                {
                    key: (
                        value.isoformat(timespec="microseconds")
                        if key == "generated_at"
                        else value
                    )
                    for key, value in source_receipt.items()
                    if key != "generated_at"
                }
            )
            + b"\n"
        )
        payloads.extend(
            [
                {
                    "file": "structured_input.csv",
                    "sha256": source_sha,
                    "artifact_type": "decision_input_bytes",
                },
                {
                    "file": "structured_input_receipt.json",
                    "sha256": source_receipt["sha256"],
                    "artifact_type": "decision_input_generation_receipt",
                },
            ]
        )
        (stage / "decision_input_manifest.json").write_bytes(
            canonical({**input_manifest, "sha256": input_manifest_sha256}) + b"\n"
        )
        payloads.append(
            {
                "file": "decision_input_manifest.json",
                "sha256": input_manifest_sha256,
                "artifact_type": "decision_input",
            }
        )
        for budget in BUDGETS:
            for n in N_VALUES:
                units = budget / 2
                candidates = plan.generate_candidates(
                    metrics=metrics,
                    segment_idx=a.segment,
                    arm="active",
                    n_value=n,
                    budget_units=units,
                    sample_attempts=a.sample_attempts,
                    seed=plan.stable_seed(a.sample_seed, a.segment, budget, n),
                )
                selected = plan.select_bundles(
                    [x for x in candidates if len(x.match_indices) == n],
                    budget_units=units,
                    max_overlap=max(0, n - 2),
                    positive_ev_only=True,
                    max_bundle_cost_units=units * 0.4,
                )
                staked, cost, reason = plan.apply_stake_mode(
                    selected,
                    budget_units=units,
                    stake_mode="scale_to_budget",
                    max_bundle_cost_units=units * 0.4,
                )
                tickets = [
                    {
                        "match_indices": list(x.candidate.match_indices),
                        "leg_codes": list(x.candidate.leg_codes),
                        "actual_n": len(x.candidate.match_indices),
                        "stake_multiplier": x.stake_multiplier,
                        "base_cost_yuan": x.candidate.cost_units * 2,
                        "cost_yuan": x.candidate.cost_units * x.stake_multiplier * 2,
                    }
                    for x in staked
                ]
                if any(t["actual_n"] != n for t in tickets):
                    raise SystemExit("fail closed: exact-N mismatch")
                actual = cost * 2
                base_cost = sum(x.candidate.cost_units * 2 for x in staked)
                payload = {
                    **common,
                    "plan_id": f"{a.issue}_s{a.segment}_n{n}_b{budget}_{event_key[:12]}",
                    "requested_n": n,
                    "artifact_n": n,
                    "recommended_n": n,
                    "requested_budget_yuan": budget,
                    "base_cost_yuan": base_cost,
                    "actual_cost_yuan": actual,
                    "unused_budget_yuan": budget - actual,
                    "budget_utilization": actual / budget if budget else 0,
                    "status": "FROZEN_EXACT_N_BUDGET"
                    if tickets
                    else "UNAVAILABLE_EXACT_N_BUDGET",
                    "tickets": tickets,
                    "reason": reason
                    if tickets
                    else "no_eligible_exact_n_candidate_or_budgeted_bundle",
                }
                payload["sha256"] = digest(payload)
                name = f"exact_n_{n}_budget_{budget}.json"
                (stage / name).write_bytes(canonical(payload) + b"\n")
                payloads.append(
                    {
                        "file": name,
                        "sha256": payload["sha256"],
                        "requested_n": n,
                        "requested_budget_yuan": budget,
                        "status": payload["status"],
                    }
                )
        score_meta, match_audit = score_audit(
            a.correct_score_root, str(a.issue), expected, decision_at
        )
        score = {
            **common,
            **score_meta,
            "artifact_type": "correct_score_paper",
            "status": "UNAVAILABLE_CORRECT_SCORE_PLAN",
            "execution_enabled": False,
            "frontend_selectable": False,
            "roi_authorized": False,
            "per_match_audit": match_audit,
            "budget_statuses": [
                {
                    "requested_budget_yuan": b,
                    "status": "UNAVAILABLE_SCORE_STAKING_RULE",
                    "actual_cost_yuan": 0,
                    "reason": "no_preregistered_correct_score_staking_rule",
                }
                for b in BUDGETS
            ],
        }
        score["sha256"] = digest(score)
        (stage / "correct_score_audit.json").write_bytes(canonical(score) + b"\n")
        payloads.append(
            {
                "file": "correct_score_audit.json",
                "sha256": score["sha256"],
                "status": score["status"],
            }
        )
        top = {
            **common,
            "schema_version": "exact_n_budget_matrix_freeze_v2",
            "artifacts": payloads,
            "immutable": True,
        }
        top["sha256"] = digest(top)
        (stage / "manifest.json").write_bytes(canonical(top) + b"\n")
        (stage / "SHA256SUMS").write_text(
            "".join(
                f"{file_hash(path)}  {path.name}\n"
                for path in sorted(stage.iterdir())
                if path.is_file() and path.name != "SHA256SUMS"
            )
        )
        destination = (
            a.output_root / str(a.issue) / f"segment_{a.segment}" / event_key
        )
        verification = promote_verified_package(
            stage=stage,
            destination=destination,
            ledger=ledger,
            ledger_payload={
                "schema_version": "exact_n_freeze_ledger_v1",
                **common,
                "artifact_manifest": str(destination / "manifest.json"),
            },
        )
        print(
            json.dumps(
                {
                    "event_key": event_key,
                    "destination": str(destination),
                    "variants": 15,
                    "ledger": str(ledger),
                    "verification": verification,
                }
            )
        )
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
