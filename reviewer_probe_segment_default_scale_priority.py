from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.decision_api import app as appmod


def main() -> int:
    options = [
        {
            "plan_id": "26000_v3.3.3_segment_betting_v0.3.0000_next_segment_scale_to_budget_seed10",
            "label": "v3.3.3",
            "decision_variant_id": appmod.SHADOW_DECISION_VARIANT_ID,
            "betting_strategy_version": "segment_betting_v0.3.0000",
            "planning_scope": "next_segment",
            "decision_time": "2026-07-07 16:00",
            "stake_mode": "scale_to_budget",
            "seed_count": 10,
            "segment_budget_yuan": 1000.0,
            "sample_seed": 10,
        },
        {
            "plan_id": "26000_v3.3.3_segment_betting_v0.3.0000_next_segment_unit_once_seed11",
            "label": "v3.3.3",
            "decision_variant_id": appmod.SHADOW_DECISION_VARIANT_ID,
            "betting_strategy_version": "segment_betting_v0.3.0000",
            "planning_scope": "next_segment",
            "decision_time": "2026-07-07 16:00",
            "stake_mode": "unit_once",
            "seed_count": 11,
            "segment_budget_yuan": 1000.0,
            "sample_seed": 11,
        },
    ]
    default_selected = appmod._select_segment_plan(
        options,
        decision_variant_id=appmod.SHADOW_DECISION_VARIANT_ID,
        planning_scope="next_segment",
        decision_time="2026-07-07 16:00",
    )
    explicit_unit = appmod._select_segment_plan(
        options,
        decision_variant_id=appmod.SHADOW_DECISION_VARIANT_ID,
        planning_scope="next_segment",
        decision_time="2026-07-07 16:00",
        plan_id="26000_v3.3.3_segment_betting_v0.3.0000_next_segment_unit_once_seed11",
    )
    no_scale_selected = appmod._select_segment_plan(
        [options[1]],
        decision_variant_id=appmod.SHADOW_DECISION_VARIANT_ID,
        planning_scope="next_segment",
        decision_time="2026-07-07 16:00",
    )
    missing_scope = appmod._select_segment_plan(
        options,
        decision_variant_id=appmod.SHADOW_DECISION_VARIANT_ID,
        planning_scope="remaining_issue",
        decision_time="2026-07-07 16:00",
    )

    result = {
        "default_selected_plan_id": (default_selected or {}).get("plan_id"),
        "default_selected_stake_mode": (default_selected or {}).get("stake_mode"),
        "explicit_unit_plan_id": (explicit_unit or {}).get("plan_id"),
        "explicit_unit_stake_mode": (explicit_unit or {}).get("stake_mode"),
        "no_scale_fallback_stake_mode": (no_scale_selected or {}).get("stake_mode"),
        "missing_scope_selected": missing_scope,
        "contract_ok": bool(
            default_selected
            and default_selected.get("stake_mode") == "scale_to_budget"
            and explicit_unit
            and explicit_unit.get("stake_mode") == "unit_once"
            and no_scale_selected
            and no_scale_selected.get("stake_mode") == "unit_once"
            and missing_scope is None
        ),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["contract_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
