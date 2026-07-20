"""Immutable, fail-closed input contract for correct-score research.

This module intentionally has no database, network, command-line, selection,
or payout integration.  A caller must provide a complete pre-match odds
snapshot; terminal odds are never an accepted substitute.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

Scoreline = tuple[int, int]


@dataclass(frozen=True)
class CorrectScoreQuote:
    """One raw decimal-odds observation from the immutable market snapshot."""

    scoreline: Scoreline
    decimal_odds: float


@dataclass(frozen=True)
class CorrectScoreOddsSnapshot:
    """A complete provider snapshot, frozen before the decision and kickoff.

    ``required_scorelines`` records the exact finite market coverage used by
    this research run.  It must match the quote set exactly, so a partial odds
    page cannot silently be de-vigged as a complete market.
    """

    snapshot_id: str
    match_id: str
    provider: str
    market_as_of: datetime
    captured_at: datetime
    decision_at: datetime
    kickoff_at: datetime
    required_scorelines: tuple[Scoreline, ...]
    quotes: tuple[CorrectScoreQuote, ...]
    market_phase: str = "pre_match"


@dataclass(frozen=True)
class OddsEligibility:
    """Validation result.  ``eligible=False`` always means no experiment use."""

    eligible: bool
    reasons: tuple[str, ...]


def _utc(value: datetime | None, field: str, reasons: list[str]) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        reasons.append(f"{field}_must_be_timezone_aware")
        return None
    return value.astimezone(timezone.utc)


def validate_snapshot(
    snapshot: CorrectScoreOddsSnapshot,
    *,
    max_staleness: timedelta = timedelta(minutes=10),
    max_capture_lag: timedelta = timedelta(minutes=5),
) -> OddsEligibility:
    """Return eligibility without repairing malformed or late market evidence.

    All four clocks must be timezone-aware.  The allowed order is
    ``market_as_of <= captured_at <= decision_at < kickoff_at``.  A quote at
    kickoff or later is terminal/live evidence and is rejected even when its
    price appears otherwise plausible.
    """

    reasons: list[str] = []
    if max_staleness < timedelta(0) or max_capture_lag < timedelta(0):
        return OddsEligibility(False, ("negative_time_window",))

    market_as_of = _utc(snapshot.market_as_of, "market_as_of", reasons)
    captured_at = _utc(snapshot.captured_at, "captured_at", reasons)
    decision_at = _utc(snapshot.decision_at, "decision_at", reasons)
    kickoff_at = _utc(snapshot.kickoff_at, "kickoff_at", reasons)
    if None not in (market_as_of, captured_at, decision_at, kickoff_at):
        assert market_as_of is not None
        assert captured_at is not None
        assert decision_at is not None
        assert kickoff_at is not None
        if market_as_of > captured_at:
            reasons.append("market_as_of_after_capture")
        if captured_at > decision_at:
            reasons.append("capture_after_decision")
        if decision_at >= kickoff_at:
            reasons.append("decision_not_before_kickoff")
        if market_as_of >= kickoff_at or captured_at >= kickoff_at:
            reasons.append("terminal_or_live_odds")
        if captured_at - market_as_of > max_capture_lag:
            reasons.append("capture_lag_exceeded")
        if decision_at - market_as_of > max_staleness:
            reasons.append("odds_stale_at_decision")

    if snapshot.market_phase != "pre_match":
        reasons.append("market_phase_not_pre_match")
    if not snapshot.snapshot_id or not snapshot.match_id or not snapshot.provider:
        reasons.append("missing_snapshot_identity")

    required = tuple(snapshot.required_scorelines)
    quoted = tuple(quote.scoreline for quote in snapshot.quotes)
    if not required:
        reasons.append("missing_required_scorelines")
    if len(set(required)) != len(required):
        reasons.append("duplicate_required_scoreline")
    if len(set(quoted)) != len(quoted):
        reasons.append("duplicate_quote_scoreline")
    if set(required) != set(quoted):
        reasons.append("incomplete_or_unexpected_market_coverage")
    for quote in snapshot.quotes:
        home_goals, away_goals = quote.scoreline
        if home_goals < 0 or away_goals < 0:
            reasons.append("negative_scoreline")
        if quote.decimal_odds <= 1.0:
            reasons.append("invalid_decimal_odds")

    return OddsEligibility(not reasons, tuple(sorted(set(reasons))))
