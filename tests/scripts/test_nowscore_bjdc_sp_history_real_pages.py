"""Real pages for Nowscore's SP history parser. No network.

Every other example for this module builds the page inline, which is how a parser can be wrong
about the source for as long as nobody fetches one: the fixture is the author's idea of the page.
These are the bytes the history endpoint actually served, kept gzipped with their digests, and a
findings page is included whose history the source has purged -- it must be refused, not read as
an empty or stale vector set.
"""
import gzip
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.nowscore_bjdc_sp_history import (  # noqa: E402
    NowscoreHistoryError,
    parse_history_page,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nowscore_sp_history"
CASES = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))["cases"]
HKT = timezone(timedelta(hours=8))
# the issue's own last kickoff, so relative timestamps on the page resolve as they did in use
KICKOFF = {"26092": datetime(2026, 9, 21, 19, 30, tzinfo=HKT),
           "21082": datetime(2021, 8, 6, 19, 45, tzinfo=HKT)}


def _page(case: dict) -> bytes:
    path = FIXTURES / case["page"]
    assert path.exists(), f"missing preserved page {case['page']}"
    return gzip.open(path, "rb").read()


def test_real_page_evidence_is_recorded_with_digests() -> None:
    """Provenance is required, not optional."""
    assert CASES, "no cases recorded"
    for case in CASES:
        assert case.get("sha256"), case["page"]
        assert case.get("source_bytes"), case["page"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["page"].split(".")[0])
def test_preserved_page_matches_its_recorded_digest(case: dict) -> None:
    payload = _page(case)
    assert hashlib.sha256(payload).hexdigest() == case["sha256"]


@pytest.mark.parametrize("case", [c for c in CASES if c["has_vectors"]],
                         ids=lambda c: c["page"].split(".")[0])
def test_a_real_history_page_parses_to_its_recorded_vectors(case: dict) -> None:
    """The values a real page yields, pinned so a decode or selector change is visible."""
    labels, vectors = parse_history_page(_page(case), case["typeid"], KICKOFF[case["issue"]])
    assert labels == ("0球", "1球", "2球", "3球", "4球", "5球", "6球", "7+球")
    assert len(vectors) == 234
    first = vectors[0]
    assert first.source_ts_hkt == "2026-09-04T10:20+08:00"
    assert first.values == (0.0, 0.0, 0.0, 3.0, 3.0, 3.0, 0.0, 0.0)
    # the last vector is the most recent, which is what an as-of selection consumes
    assert vectors[-1].source_ts_hkt > first.source_ts_hkt


@pytest.mark.parametrize("case", [c for c in CASES if not c["has_vectors"]],
                         ids=lambda c: c["page"].split(".")[0])
def test_a_real_page_without_vectors_is_refused(case: dict) -> None:
    """An old issue's history is purged; that is not the same as an empty history."""
    with pytest.raises(NowscoreHistoryError, match="no vectors"):
        parse_history_page(_page(case), case["typeid"], KICKOFF[case["issue"]])


@pytest.mark.parametrize("case", [c for c in CASES if c["has_vectors"]],
                         ids=lambda c: c["page"].split(".")[0])
def test_the_preserved_page_is_that_issue(case: dict) -> None:
    """A page that is not this issue's must not be read as its history."""
    text = _page(case).decode("utf-8", errors="replace")
    assert case["issue"] in text, f"{case['page']} does not mention issue {case['issue']}"


@pytest.mark.parametrize("case", [c for c in CASES if c["has_vectors"]],
                         ids=lambda c: c["page"].split(".")[0])
def test_an_unsupported_market_is_refused_for_a_real_page(case: dict) -> None:
    """The gate must hold on real input, not only on constructed input."""
    with pytest.raises((NowscoreHistoryError, ValueError)):
        parse_history_page(_page(case), 99, KICKOFF[case["issue"]])


@pytest.mark.parametrize("case", [c for c in CASES if c["has_vectors"]],
                         ids=lambda c: c["page"].split(".")[0])
def test_a_real_page_read_as_another_market_is_refused(case: dict) -> None:
    """A real page whose headers belong to a different market must not be read as this one.

    Without this, the header gate could be dropped and every example would still pass, because
    each preserved page happens to match the market it is filed under.
    """
    other = 5 if case["typeid"] != 5 else 6
    with pytest.raises(NowscoreHistoryError, match="header mismatch"):
        parse_history_page(_page(case), other, KICKOFF[case["issue"]])
