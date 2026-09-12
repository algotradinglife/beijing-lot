"""Deterministic five-play plans derived only from a sealed issue inventory."""
from datetime import datetime
import math
from pathlib import Path

from src.nowscore_issue_inventory import INVENTORY_SCHEMA, archive_url, canonical, digest
from src.nowscore_settlement import PLAYS, source_url


def make_history_capture_plan(
    inventory: dict, *, issues_per_batch: int, control_issue: str,
    interval_seconds: float, generated_at: str,
) -> dict:
    """Return a source-pure five-play plan; no IO except reading code identity.

    Inventory must have complete candidate coverage and a valid content hash.
    Times are explicit timezone-aware ISO strings. Intervals are seconds.
    Each batch has two additional SPF controls, not counted as data coverage.
    Raises ValueError for incomplete, contradictory, or stale input metadata.
    This function does not fit models or establish historical availability.
    """
    if (
        inventory.get("schema") != INVENTORY_SCHEMA
        or inventory.get("source") != "nowscore"
        or inventory.get("candidate_coverage_complete") is not True
        or inventory.get("production_enabled") is not False
    ):
        raise ValueError("complete source-pure inventory required")
    content = {key: value for key, value in inventory.items() if key != "inventory_sha256"}
    if inventory.get("inventory_sha256") != digest(canonical(content).encode()):
        raise ValueError("inventory content hash mismatch")
    issues = inventory.get("issues")
    empty = inventory.get("source_empty_candidates")
    if not isinstance(issues, list) or not issues or not isinstance(empty, list):
        raise ValueError("inventory issue lists missing or empty")
    for issue in issues + empty:
        archive_url(issue)
    if len(set(issues + empty)) != len(issues) + len(empty):
        raise ValueError("inventory issue domains overlap or contain duplicates")
    if (
        inventory.get("issue_count") != len(issues)
        or inventory.get("source_empty_count") != len(empty)
        or inventory.get("candidate_count") != len(issues) + len(empty)
        or inventory.get("five_play_pages_to_capture") != len(issues) * len(PLAYS)
    ):
        raise ValueError("inventory coverage counts mismatch")
    created = datetime.fromisoformat(generated_at)
    inventoried = datetime.fromisoformat(inventory["generated_at"])
    if created.tzinfo is None or inventoried.tzinfo is None or created < inventoried:
        raise ValueError("plan chronology must follow timezone-aware inventory")
    if type(issues_per_batch) is not int or issues_per_batch <= 0:
        raise ValueError("issues per batch must be a positive integer")
    if isinstance(interval_seconds, bool) or not math.isfinite(interval_seconds) or interval_seconds < 2:
        raise ValueError("request interval must be finite and at least two seconds")
    if control_issue not in issues:
        raise ValueError("control issue must be present in inventory")
    batches = []
    for start in range(0, len(issues), issues_per_batch):
        batch_issues = issues[start:start + issues_per_batch]
        requests = [
            {"issue": issue, "typeid": typeid, "url": source_url(issue, typeid)}
            for issue in batch_issues for typeid in PLAYS
        ]
        batches.append({
            "batch_id": f"plays-{len(batches) + 1:04d}",
            "issues": batch_issues,
            "requests": requests,
            "data_request_count": len(requests),
            "control_request_count": 2,
        })
    implementation = {
        name: digest(Path(__file__).with_name(name).read_bytes())
        for name in ("nowscore_history_plan.py", "nowscore_history_capture.py", "nowscore_history_assembly.py", "nowscore_issue_inventory.py",
                     "nowscore_settlement.py", "nowscore_bjdc_sp_history.py", "multimarket_p0.py")
    }
    plan = {
        "schema": "nowscore_history_capture_plan_v1",
        "source": "nowscore",
        "generated_at": generated_at,
        "inventory_sha256": inventory["inventory_sha256"],
        "inventory_document_sha256": digest(canonical(inventory).encode()),
        "issue_count": len(issues),
        "issues_per_batch": issues_per_batch,
        "control_issue": control_issue,
        "control_url": source_url(control_issue, 5),
        "interval_seconds": interval_seconds,
        "batch_count": len(batches),
        "batches": batches,
        "data_request_count": len(issues) * len(PLAYS),
        "control_request_count": 2 * len(batches),
        "minimum_intra_batch_pacing_seconds": (len(issues) * len(PLAYS) + len(batches)) * interval_seconds,
        "implementation_sha256": implementation,
        "production_enabled": False,
        "historical_coverage_claimed": False,
        "historical_learning_functions": [],
    }
    plan["plan_sha256"] = digest(canonical(plan).encode())
    return plan


def validate_history_capture_plan(plan: dict, inventory: dict) -> None:
    """Rebuild and compare the entire plan, including implementation identities."""
    expected = make_history_capture_plan(
        inventory, issues_per_batch=plan["issues_per_batch"],
        control_issue=plan["control_issue"], interval_seconds=plan["interval_seconds"],
        generated_at=plan["generated_at"],
    )
    if plan != expected:
        raise ValueError("five-play plan differs from inventory, parameters or implementation")
