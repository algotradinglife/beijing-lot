"""Scraper + collector tests using monkey-patched HTTP."""
from pathlib import Path

import pytest
from conftest import fixture

from live_collector.db import Database
from live_collector.scheduler import Collector, _merge_snapshots
from live_collector.parser import MatchSnapshot
from live_collector.scraper import Scraper


class FakeScraper(Scraper):
    """Returns canned HTML strings — no network."""

    def __init__(self, *, bjdc: str = "", zgzcw: str = "", kaijiang: str = ""):
        # don't call super().__init__ — we don't want a Session
        self._bjdc = bjdc
        self._zgzcw = zgzcw
        self._kaijiang = kaijiang
        self.calls = []

    def fetch_bjdc_500(self, issue=None):
        self.calls.append(("bjdc", issue))
        return self._bjdc

    def fetch_zgzcw_bet(self):
        self.calls.append(("zgzcw", None))
        return self._zgzcw

    def fetch_kaijiang_500(self, issue):
        self.calls.append(("kaijiang", issue))
        return self._kaijiang


@pytest.fixture()
def tmp_db(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


def test_collector_poll_once_full_cycle(tmp_db):
    s = FakeScraper(
        bjdc=fixture("bjdc500_26051.html"),
        zgzcw=fixture("zgzcw_bet_lottery200.html"),
    )
    c = Collector(tmp_db, s)
    n = c.poll_once(issue="26051")
    assert n >= 5  # plenty of matches
    assert tmp_db.count_matches(issue="26051") >= 5
    assert tmp_db.count_snapshots(issue="26051") >= 5


def test_collector_poll_once_idempotent(tmp_db, monkeypatch):
    s = FakeScraper(
        bjdc=fixture("bjdc500_26051.html"),
        zgzcw=fixture("zgzcw_bet_lottery200.html"),
    )
    c = Collector(tmp_db, s)
    # freeze ts so two polls collide
    import live_collector.scheduler as sch
    real_dt = sch.datetime
    class _DT:
        @staticmethod
        def now(tz):
            from datetime import datetime, timezone
            return datetime(2026, 5, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(sch, "datetime", _DT)
    n1 = c.poll_once(issue="26051")
    n2 = c.poll_once(issue="26051")
    assert n1 > 0
    assert n2 == 0  # all duplicates


def test_collector_settle_issue(tmp_db):
    s = FakeScraper(kaijiang=fixture("kaijiang_500_26051.html"))
    # seed the matches first
    snap = MatchSnapshot(issue="26051", match_idx=1, home="博德闪耀", away="斯达")
    tmp_db.upsert_match(snap)
    c = Collector(tmp_db, s)
    n = c.settle_issue("26051")
    assert n >= 1


def test_merge_fills_gaps():
    a = MatchSnapshot(issue="26051", match_idx=1, league="挪超", sp_3=None)
    b = MatchSnapshot(issue="26051", match_idx=1, league=None, sp_3=1.76)
    c = MatchSnapshot(issue="26051", match_idx=2, home="X")
    merged = _merge_snapshots([a], [b, c])
    by_idx = {m.match_idx: m for m in merged}
    assert by_idx[1].league == "挪超"
    assert by_idx[1].sp_3 == 1.76
    assert by_idx[2].home == "X"
