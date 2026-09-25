"""Cross-source identity reconciliation, driven by measured evidence.

The frozen 26098 snapshot is the specification. Measured there:

* Both sources expose exactly 146 rows with slots 1..146, so slot is a usable
  *candidate* join key — but slot alone is not identity, so it is always checked
  against at least one independent signal before a match is called verified.
* Provider IDs are unrelated (500 uses ``fid``, nowscore ``Panlu.aspx?id=``), so
  they can never be compared across sources; they only order rows *within* one.
* The handicap agrees on all 146 slots.
* Team names still differ on 25 of 146 slots (``克鲁比`` vs
  ``赫尔辛基预备队``), and those differences are *not* decoration. An earlier
  rule stripped ``女足``/``U21``/``预备队``/``青年队`` and accepted directional
  containment; that rule would equate a men's side with the women's, senior with
  reserve, and U19 with U21 — different teams. It is deleted, not tuned.

So the strategy is deliberately narrow: **exact names modulo whitespace,
punctuation, width and case** may verify a slot. Everything else stays
``unresolved`` with a visible diagnostic. A wrong "verified" is far more
expensive than an unresolved row: the canonical table keeps both providers'
original spellings in their own columns, and only the primary source's fields
(nowscore by default) are ever promoted to the canonical values.
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

#: Punctuation, width and spacing only. Deliberately *not* a list of football
#: words: removing ``预备队``/``U21``/``女足`` changes which team a name denotes.
_PUNCTUATION_RE = re.compile(r"[\s·．.。\-—_()（）\[\]【】]")

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


def normalize_team_name(name: str) -> str:
    """Build a comparison key by removing punctuation/width/spacing only.

    @param name Raw team name from either source.
    @return A comparison key. This is *only* a comparison key — the canonical
        table keeps each source's original spelling in its own column.
    @details The key never drops a word that carries team identity: a name that
        differs by ``预备队``, ``U21``, ``女足`` or ``青年队`` produces different
        keys, because those are different teams.
    """
    text = (name or "").strip()
    text = text.replace("（", "(").replace("）", ")")
    text = _PUNCTUATION_RE.sub("", text)
    return text.upper()


def name_agreement(left: str, right: str) -> tuple[bool, str]:
    """Decide whether two team names denote the same club.

    @param left One source's spelling.
    @param right The other source's spelling.
    @return ``(agrees, note)``. Agreement is raw equality, or equality after
        removing punctuation/width/spacing. No containment, no edit distance and
        no decoration stripping: measured 26098 differences such as
        ``克鲁比``/``赫尔辛基预备队`` are *not* agreement and must stay visible.
    """
    if not left or not right:
        return False, "one source published an empty name"
    raw_left, raw_right = left.strip(), right.strip()
    if raw_left == raw_right:
        return True, "exact"
    norm_left, norm_right = normalize_team_name(raw_left), normalize_team_name(raw_right)
    if not norm_left or not norm_right:
        return False, "name normalized to empty"
    if norm_left == norm_right:
        return True, "normalized-equal"
    return False, "normalized-names-disagree"


def identity_candidates(
    rows_500: list[ProviderRow], rows_nowscore: list[ProviderRow]
) -> dict[int, tuple[ProviderRow | None, ProviderRow | None]]:
    """Pair rows by slot without asserting identity.

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
    """Reconcile one slot across sources and report the method used.

    @param row_500 The 500 row, or ``None``.
    @param row_nowscore The nowscore row, or ``None``.
    @return An ``IdentityVerdict`` naming the evidence that was used.
    @details Rules:
        · both sides present, *both* names agree exactly modulo
          punctuation/width/spacing, and the handicaps agree ->
          ``normalized_name``, verified.
        · both sides present but a name or handicap disagrees -> ``conflict``,
          not verified. This is the normal outcome for a provider abbreviation
          such as ``克鲁比`` vs ``赫尔辛基预备队``: it stays visible.
        · only one side present -> ``provider_id`` for that side alone, *not*
          verified, because a single source cannot corroborate itself.
        · neither side present -> ``unresolved``.
    """
    if row_500 is not None and row_nowscore is not None:
        home_ok, home_note = name_agreement(row_500.home_name, row_nowscore.home_name)
        away_ok, away_note = name_agreement(row_500.away_name, row_nowscore.away_name)
        handicap_ok = row_500.handicap == row_nowscore.handicap
        if home_ok and away_ok and handicap_ok:
            note = "home=" + home_note + ";away=" + away_note + ";handicap=equal"
            return IdentityVerdict("normalized_name", note, verified=True)
        problems = []
        if not home_ok:
            problems.append(f"home: {home_note}")
        if not away_ok:
            problems.append(f"away: {away_note}")
        if not handicap_ok:
            problems.append(
                f"handicap: {row_500.handicap!r} != {row_nowscore.handicap!r}"
            )
        return IdentityVerdict("conflict", ";".join(problems), verified=False)
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
        if verdict.method == "conflict":
            diagnostics.append(f"slot {slot}: identity conflict ({verdict.note})")
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
                # The raw column keeps the *display string* the source published,
                # whatever it was (``完场``/``截止``/``23:25``/empty). It is a copy
                # of the display, never a second, differently-classified status,
                # so a mixed sale display can never be read as match status.
                "match_status_raw": display_nowscore if match_status != "unknown" else None,
                "sale_state": sale_state,
                "sale_end_at": sale_end_at,
                "sale_end_raw": (right.sale_end_raw if right else None)
                or (left.sale_end_raw if left else None),
                "sale_end_date_source": "title-attribute" if sale_end_at else "absent",
                "score": pick_score(right),
                "provider_id": picked.provider_match_id if picked else "",
                "provider_id_500": left.provider_match_id if left else "",
                "provider_id_nowscore": right.provider_match_id if right else "",
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
