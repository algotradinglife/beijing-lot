from datetime import datetime

from src.natural_day_segments import build_natural_day_segments, MIN_MATCHES


class Match:
    def __init__(self, idx: int, kickoff: str):
        self.match_idx = idx
        self.kickoff = datetime.fromisoformat(kickoff)


def test_natural_day_merges_small_leading_and_trailing_groups() -> None:
    """26078 fixture: 6+57+72+25+13 → 63/72/38"""
    matches = [Match(i, "2026-07-24T18:20") for i in range(1, 7)]
    matches += [Match(i, "2026-07-25T23:50") for i in range(7, 64)]
    matches += [Match(i, "2026-07-26T01:20") for i in range(64, 136)]
    matches += [Match(i, "2026-07-27T01:05") for i in range(136, 161)]
    matches += [Match(i, "2026-07-28T06:50") for i in range(161, 174)]
    built = build_natural_day_segments("26078", matches)
    assert [len(item.match_indices) for item in built.segments] == [63, 72, 38]
    assert [item.freeze_at.strftime("%Y-%m-%d %H:%M") for item in built.segments] == [
        "2026-07-24 17:55", "2026-07-26 00:55", "2026-07-27 00:40",
    ]


def test_insufficient_issue_never_falls_back_to_entire_issue() -> None:
    """<20 matches → skipped, no segments."""
    built = build_natural_day_segments("small", [Match(1, "2026-07-24T18:20")])
    assert not built.segments
    assert built.skipped[0]["reason"] == "skipped_insufficient_issue_matches"


def test_single_big_day_stays_whole() -> None:
    """A day with >20 matches stays one segment (no max_matches=24 cap)."""
    matches = [Match(i, f"2026-07-26T{(i % 24) + 1:02d}:00") for i in range(1, 73)]
    built = build_natural_day_segments("26078", matches)
    assert len(built.segments) == 1
    assert len(built.segments[0].match_indices) == 72


def test_merge_span_exceeds_36h_skipped() -> None:
    """Small day group that would need >36h span → skipped at segment level."""
    # Day 1: 25 matches (big enough, standalone segment)
    # Day 2: 5 matches at same time (small, tries to merge with Day 3)
    # Day 3: 5 matches at 48h span from Day 2 → merge span >36h
    matches = [Match(i, "2026-07-24T08:00") for i in range(1, 26)]
    matches += [Match(i, "2026-07-25T08:00") for i in range(26, 31)]
    matches += [Match(i, "2026-07-27T08:00") for i in range(31, 36)]
    built = build_natural_day_segments("test", matches)
    # Day 1 stands alone (25). Day 2 (5) forward-merge with Day 3 fails (48h from Day 2 start).
    # Day 2 backward-merges into Day 1 (24h span from Day 1 start ✅).
    # Day 3 backward-merge with Day 1 fails (72h span from Day 1 start).
    # Result: Day 1 has 30 matches (25+5), Day 3 (5) is skipped.
    assert len(built.segments) == 1
    assert len(built.segments[0].match_indices) == 30
    assert any(s["reason"] == "skipped_insufficient_segment_matches" for s in built.skipped)


def test_trailing_small_group_merged_backward() -> None:
    """Small tail day merges backward if span <= 36h."""
    matches = [Match(i, f"2026-07-24T%02d:00" % ((i % 24) + 1)) for i in range(1, 26)]
    matches += [Match(i, "2026-07-25T01:00") for i in range(26, 31)]
    built = build_natural_day_segments("test", matches)
    assert len(built.segments) == 1
    assert len(built.segments[0].match_indices) == 30


def test_trailing_small_group_span_too_wide_skipped() -> None:
    """Small tail day that would exceed 36h backward-merge → skipped."""
    matches = [Match(i, "2026-07-24T00:00") for i in range(1, 26)]
    matches += [Match(i, "2026-07-28T00:00") for i in range(26, 31)]
    built = build_natural_day_segments("test", matches)
    assert len(built.segments) == 1
    assert len(built.segments[0].match_indices) == 25
    assert any(s["reason"] == "skipped_insufficient_segment_matches" for s in built.skipped)


def test_denominator_integrity() -> None:
    """All match indices are covered exactly once (no gaps, no overlap)."""
    matches = [Match(i, "2026-07-24T18:20") for i in range(1, 7)]
    matches += [Match(i, "2026-07-25T23:50") for i in range(7, 64)]
    matches += [Match(i, "2026-07-26T01:20") for i in range(64, 136)]
    matches += [Match(i, "2026-07-27T01:05") for i in range(136, 161)]
    matches += [Match(i, "2026-07-28T06:50") for i in range(161, 174)]
    built = build_natural_day_segments("26078", matches)
    covered = set()
    for seg in built.segments:
        covered.update(seg.match_indices)
    for skip in built.skipped:
        covered.update(skip["match_indices"])
    assert covered == set(range(1, 174))
    assert len(covered) == 173


def test_skip_reason_includes_full_denominator() -> None:
    """Skipped entries contain all required diagnostic fields."""
    built = build_natural_day_segments("test", [Match(1, "2026-07-24T18:20")])
    entry = built.skipped[0]
    assert "match_indices" in entry
    assert "match_count" in entry
    assert "minimum_matches" in entry
    assert entry["minimum_matches"] == MIN_MATCHES
    assert entry["match_count"] == 1
