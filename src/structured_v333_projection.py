"""Canonical, vocabulary-neutral projection of the v3.3.3 decision result."""

from __future__ import annotations

import json
from typing import Any, Callable


def canonical_v333_decision_projection(
    row: Any,
    *,
    result_rows: Callable[[dict[str, Any]], list[dict[str, Any]]],
    category_rows: Callable[[dict[str, Any], dict[str, Any]], list[dict[str, Any]]],
    outcome_text: Callable[[str | None, dict[str, Any]], str],
    leg_profit: Callable[[list[str], str | None, float | None], float],
) -> dict[str, Any]:
    """Return decision semantics independently of active/shadow CSV labels."""

    payload = row.payload
    structured = row.structured
    outcomes = result_rows(payload)
    by_code = {str(item["code"]): item for item in outcomes}
    sections = structured["sections"]
    market = sections["market_q_ev"]
    selections = [str(code) for code in structured.get("selection_codes", [])]
    actual = row.result_code
    return {
        "issue": row.issue,
        "match_idx": row.match_idx,
        "match_id": row.match_id,
        "league": row.league,
        "home": row.home,
        "away": row.away,
        "handicap_line": row.handicap_line,
        "score": row.score,
        "actual_code": actual or "",
        "actual_label": outcome_text(actual, payload.get("match", {})) if actual else "",
        "winning_sp": row.winning_sp if row.winning_sp is not None else "",
        "decision_version": structured.get("decision_version", ""),
        "judgment": structured.get("judgment", ""),
        "primary_pick": structured.get("primary_pick") or "",
        "selection_codes": "+".join(selections),
        "stop_flag": int(bool(structured.get("stop_flag"))),
        "primary_hit": "" if not actual else int(structured.get("primary_pick") == actual),
        "coverage_hit": "" if not actual else int(actual in selections),
        "stake": len(selections),
        "profit_proxy": round(leg_profit(selections, actual, row.winning_sp), 4) if actual else "",
        "selection_type": structured.get("selection_type", ""),
        "prob_top": market.get("probability_top_code") or "",
        "q_top": market.get("code") or "",
        "p_3": by_code["3"].get("probability"),
        "p_1": by_code["1"].get("probability"),
        "p_0": by_code["0"].get("probability"),
        "sp_3": by_code["3"].get("sp"),
        "sp_1": by_code["1"].get("sp"),
        "sp_0": by_code["0"].get("sp"),
        "q_3": by_code["3"].get("q"),
        "q_1": by_code["1"].get("q"),
        "q_0": by_code["0"].get("q"),
        "max_q": market.get("q"),
        "risk_tags": ";".join(structured.get("risk_tags", [])),
        "decision_chain_json": json.dumps(structured.get("chain", []), ensure_ascii=False),
        "decision_categories_json": json.dumps(category_rows(structured, payload), ensure_ascii=False),
    }
