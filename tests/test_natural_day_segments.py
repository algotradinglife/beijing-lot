from datetime import datetime

from src.natural_day_segments import build_natural_day_segments


class Match:
    def __init__(self, idx: int, kickoff: str):
        self.match_idx = idx
        self.kickoff = datetime.fromisoformat(kickoff)


def test_natural_day_merges_small_leading_and_trailing_groups() -> None:
    matches = [Match(i, "2026-07-24T18:20") for i in range(1, 7)]
    matches += [Match(i, "2026-07-25T23:50") for i in range(7, 64)]
    matches += [Match(i, "2026-07-26T01:20") for i in range(64, 136)]
    matches += [Match(i, "2026-07-27T01:05") for i in range(136, 161)]
    matches += [Match(i, "2026-07-28T06:50") for i in range(161, 174)]
    built = build_natural_day_segments("26078", matches)
    assert [len(item.match_indices) for item in built.segments] == [63, 72, 38]
    assert [item.freeze_at.strftime("%Y-%m-%d %H:%M") for item in built.segments] == ["2026-07-24 17:55", "2026-07-26 00:55", "2026-07-27 00:40"]


def test_insufficient_issue_never_falls_back_to_entire_issue() -> None:
    built = build_natural_day_segments("small", [Match(1, "2026-07-24T18:20")])
    assert not built.segments
    assert built.skipped[0]["reason"] == "skipped_insufficient_issue_matches"
