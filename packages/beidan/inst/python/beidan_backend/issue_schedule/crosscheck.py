"""Align issue schedules by the source-validated issue and within-issue slot.

Team spellings remain provenance, not an identity gate. Provider ID namespaces
remain separate; canonical match fields continue to come from Nowscore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .contract import (
    IDENTITY_MATCH_METHODS,
    classify_match_status,
    classify_sale_state,
    resolve_kickoff_at,
    to_utc,
)
from .sources import ProviderRow

#: A real score is ``home-away`` with plain digits on both sides. Anything else
#: (``析 亚 欧``, ``-``, empty, free text) is *not* a score and is reported as
#: ``None``; no anonymous "unverified" string is ever substituted for it.
_SCORE_RE = re.compile(r"^\d{1,3}-\d{1,3}$")


def pick_score(candidate: "ProviderRow | None") -> str | None:
    """Return only the primary row's valid score; never use a secondary result."""
    if candidate is None:
        return None
    text = (candidate.score or "").strip()
    return text if _SCORE_RE.fullmatch(text) else None


class CrossSourceError(ValueError):
    """The two sources cannot be reconciled under the evidence rules."""


@dataclass
class IdentityVerdict:
    """The outcome of comparing one slot across both sources."""

    method: str
    note: str
    verified: bool


def identity_candidates(
    rows_500: list[ProviderRow], rows_nowscore: list[ProviderRow]
) -> dict[int, tuple[ProviderRow | None, ProviderRow | None]]:
    """Pair rows by the within-issue slot; source parsers validate issue identity.

    @param rows_500 Rows from 500.
    @param rows_nowscore Rows from nowscore.
    @return Mapping slot -> ``(row_500, row_nowscore)``; either side may be
        ``None`` for a slot only one source published.
    @raises CrossSourceError when a single source publishes the same slot twice:
        the canonical key is ``(issue_id, slot)``, so a duplicate is a source
        defect that must be surfaced rather than silently collapsed to one row.
    """
    by_slot_500 = _index_by_slot(rows_500, "500")
    by_slot_nowscore = _index_by_slot(rows_nowscore, "nowscore")
    slots = sorted(set(by_slot_500) | set(by_slot_nowscore))
    return {slot: (by_slot_500.get(slot), by_slot_nowscore.get(slot)) for slot in slots}


def _index_by_slot(rows: list[ProviderRow], provider: str) -> dict[int, ProviderRow]:
    indexed: dict[int, ProviderRow] = {}
    for row in rows:
        if row.slot in indexed:
            raise CrossSourceError(
                f"{provider} published slot {row.slot} more than once; the canonical "
                "key is (issue_id, slot) and a duplicate cannot be resolved silently"
            )
        indexed[row.slot] = row
    return indexed


def reconcile_identity(
    row_500: ProviderRow | None, row_nowscore: ProviderRow | None
) -> IdentityVerdict:
    """Align two rows by slot after each source page passed issue validation.

    Both rows with the same slot are aligned regardless of team spelling or
    handicap. Names stay in source columns; handicap discrepancies remain
    separate data diagnostics. A missing source is explicitly single-source.
    Different slots raise CrossSourceError instead of asserting alignment.
    """
    if row_500 is not None and row_nowscore is not None:
        if row_500.slot != row_nowscore.slot:
            raise CrossSourceError("cannot align different issue slots")
        return IdentityVerdict("slot", "same validated issue and slot", verified=True)
    if row_500 is not None:
        return IdentityVerdict(
            "provider_id", "only 500 published this slot; single-source, unverified", verified=False
        )
    if row_nowscore is not None:
        return IdentityVerdict(
            "provider_id",
            "only nowscore published this slot; single-source, unverified",
            verified=False,
        )
    return IdentityVerdict("unresolved", "no source published this slot", verified=False)


def build_canonical_rows(
    *,
    issue_id: str,
    rows_500: list[ProviderRow],
    rows_nowscore: list[ProviderRow],
    observed_at_iso: str,
    observed_at_utc,
    source_url_500: str,
    source_url_nowscore: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Reconcile both sources into validated canonical rows.

    @param issue_id Issue identifier.
    @param rows_500 Parsed 500 rows.
    @param rows_nowscore Parsed nowscore rows.
    @param observed_at_iso The shared observation instant, ISO-8601.
    @param observed_at_utc The same instant as an aware UTC datetime.
    @param source_url_500 URL the 500 bytes came from.
    @param source_url_nowscore URL the nowscore bytes came from.
    @return ``(canonical_rows, diagnostics)``. Diagnostics name every conflict
        and every unresolved kickoff; they never replace a field with a guess.
    @details Only the primary source contributes kickoff, status, score and sale
        instants. The other source contributes *provenance only* (its own names,
        IDs and raw display), so an unverified cross-source claim can never leak
        into a canonical value.
    """
    candidates = identity_candidates(rows_500, rows_nowscore)
    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for slot, (left, right) in candidates.items():
        picked = right
        if picked is None:
            diagnostics.append(
                f"slot {slot}: primary source nowscore published no row; "
                "slot is retained from the other source only"
            )
        verdict = reconcile_identity(left, right)
        if left is not None and right is not None and left.handicap != right.handicap:
            diagnostics.append(f"slot {slot}: handicap differs (500={left.handicap}, nowscore={right.handicap}); primary nowscore retained")
        home_name = picked.home_name if picked else (left or right).home_name
        away_name = picked.away_name if picked else (left or right).away_name
        handicap = picked.handicap if picked else (left or right).handicap
        kickoff_hhmm = picked.kickoff_hhmm if picked else None
        group_date = picked.schedule_date if picked else None
        js_date = picked.kickoff_js_date if picked else None
        closing_beijing = right.sale_end_at if right is not None else None
        kickoff_beijing, date_source, kickoff_note = resolve_kickoff_at(
            js_kickoff_date=js_date,
            clock_text=kickoff_hhmm,
            closing_at=closing_beijing,
        )
        kickoff_at = to_utc(kickoff_beijing)
        note = verdict.note
        if kickoff_note:
            note += ";" + kickoff_note
            diagnostics.append(f"slot {slot}: {kickoff_note}")
        sale_end_beijing = right.sale_end_at if right is not None else None
        sale_end_at = to_utc(sale_end_beijing)
        display_nowscore = (right.status_token if right else "") or ""
        if right is not None:
            match_status = classify_match_status(
                nowscore_token=display_nowscore,
                nowscore_score=right.score,
                can_sale=right.can_sale,
            )
            state_code = right.extras.get("status_code")
            if state_code is not None:
                # MatchState in the source bdLive.js defines these codes.
                state_token = {0: "未开赛", 1: "上", 2: "中场", 3: "下", 4: "完场",
                    5: "点", -1: "完场", -10: "取消", -99: "取消", -11: "待定",
                    -12: "腰斩", -13: "中断", -14: "推迟"}.get(state_code, "")
                coded_status = classify_match_status(nowscore_token=state_token,
                    nowscore_score=None, can_sale=None)
                if match_status != "unknown" and coded_status != "unknown" and match_status != coded_status:
                    raise CrossSourceError(f"slot {slot}: conflicting nowscore state code/display")
                match_status = coded_status
                note += f";match-status-source=M[{slot}][4]"
        else:
            match_status = "unknown"
            note += ";match-status-absent (500 publishes no match status)"
        sale_state = classify_sale_state(
            picked.can_sale if picked else None, sale_end_beijing, observed_at_utc
        )
        rows.append(
            {
                "issue_id": issue_id,
                "slot": slot,
                "fixture_key": f"{issue_id}:{slot}",
                "home_name": home_name,
                "away_name": away_name,
                "handicap": handicap,
                "kickoff_at": kickoff_at,
                "kickoff_hhmm": kickoff_hhmm,
                "kickoff_group_date": group_date,
                "kickoff_date_source": date_source,
                "match_status": match_status,
                # Preserve the exact state-code evidence when supplied; the
                # independent raw_display_nowscore retains the mixed sale cell.
                "match_status_raw": (f"M[{slot}][4]={right.extras['status_code']}"
                    if right and right.extras.get("status_code") is not None
                    else display_nowscore if match_status != "unknown" else None),
                "sale_state": sale_state,
                "sale_end_at": sale_end_at,
                "sale_end_raw": (right.sale_end_raw if right else None)
                or (left.sale_end_raw if left else None),
                # Each provider's own sale cutoff is preserved verbatim and
                # separately: 500's ``endTime`` and nowscore's ``截止时间：``
                # title are *different* sales cutoffs, never one kickoff estimate
                # and never merged into a single agreement claim.
                "sale_end_raw_500": left.sale_end_raw if left else None,
                "sale_end_raw_nowscore": right.sale_end_raw if right else None,
                "sale_end_date_source": "title-attribute" if sale_end_at else "absent",
                "score": pick_score(right),
                "provider_id": picked.provider_match_id if picked else "",
                "provider_id_500": left.provider_match_id if left else "",
                "provider_id_nowscore": right.provider_match_id if right else "",
                "home_display_500": left.extras.get("home_display", "") if left else "",
                "home_title_500": left.extras.get("home_title", "") if left else "",
                "away_display_500": left.extras.get("away_display", "") if left else "",
                "away_title_500": left.extras.get("away_title", "") if left else "",
                "league_500": left.league if left else "",
                "home_display_nowscore": right.extras.get("home_display", "") if right else "",
                "home_title_nowscore": right.extras.get("home_title", "") if right else "",
                "away_display_nowscore": right.extras.get("away_display", "") if right else "",
                "away_title_nowscore": right.extras.get("away_title", "") if right else "",
                "league_nowscore": right.league if right else "",
                "home_500": left.home_name if left else "",
                "away_500": left.away_name if left else "",
                "home_nowscore": right.home_name if right else "",
                "away_nowscore": right.away_name if right else "",
                "identity_method": verdict.method,
                "identity_note": note,
                "observed_at": observed_at_utc,
                "source_url_500": source_url_500,
                "source_url_nowscore": source_url_nowscore,
                "raw_display_nowscore": display_nowscore,
                "raw_display_500": (left.status_token if left else "") or "",
            }
        )
    return rows, diagnostics


def identity_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count rows per identity method.

    @param rows Canonical rows.
    @return Mapping method -> count, including zero counts for unused methods.
    """
    summary = {method: 0 for method in IDENTITY_MATCH_METHODS}
    for row in rows:
        summary[row["identity_method"]] = summary.get(row["identity_method"], 0) + 1
    return summary
