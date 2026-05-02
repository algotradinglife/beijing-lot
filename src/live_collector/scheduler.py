"""High-level orchestrator: discover issues, poll, persist, settle.

The orchestration is intentionally a plain while-loop (`run_loop`) because
the requirements are small (one issue active at a time, polls every 5-15
minutes). APScheduler is overkill, and a loop is trivially testable.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, List

from .db import Database
from .parser import (
    MatchSnapshot,
    parse_bet_page_500,
    parse_bet_page_zgzcw,
    parse_issue_list,
    parse_kaijiang,
    find_current_issue,
)
from .scraper import Scraper

log = logging.getLogger(__name__)


def _merge_snapshots(primary: List[MatchSnapshot],
                     secondary: List[MatchSnapshot]) -> List[MatchSnapshot]:
    """Merge zgzcw rows into 500.com rows by match_idx, filling gaps.

    500.com's bjdc is the primary source (it has tzbl/vol_pct columns).
    cp.zgzcw is the secondary source — it has cleaner spArr values when
    500.com hasn't populated SP yet (or has stripped them).
    """
    by_idx = {s.match_idx: s for s in primary}
    for s in secondary:
        if s.match_idx not in by_idx:
            by_idx[s.match_idx] = s
            continue
        p = by_idx[s.match_idx]
        for f in ("league", "kickoff_ts", "home", "away", "handicap_line",
                  "sp_3", "sp_1", "sp_0", "eu_h", "eu_d", "eu_a"):
            if getattr(p, f) in (None, "") and getattr(s, f) is not None:
                setattr(p, f, getattr(s, f))
    return list(by_idx.values())


class Collector:
    def __init__(self, db: Database, scraper: Scraper):
        self.db = db
        self.scraper = scraper

    # ------------------------------------------------------------------
    def discover_current_issue(self) -> str | None:
        html = self.scraper.fetch_bjdc_500()
        if not html:
            return None
        cur = find_current_issue(html) or (parse_issue_list(html)[:1] or [None])[0]
        return cur

    def poll_once(self, issue: str | None = None) -> int:
        """Fetch both bet pages, merge, persist a snapshot row per match.

        Returns the number of (new) snapshot rows inserted.
        """
        issue = issue or self.discover_current_issue()
        if not issue:
            log.warning("poll: no current issue discovered, skipping")
            return 0

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log.info("poll start issue=%s ts=%s", issue, ts)

        html500 = self.scraper.fetch_bjdc_500(issue)
        rows500 = parse_bet_page_500(html500, issue=issue) if html500 else []
        log.info("  500.com bjdc: %d rows", len(rows500))

        htmlz = self.scraper.fetch_zgzcw_bet()
        rowsz = parse_bet_page_zgzcw(htmlz, issue=issue) if htmlz else []
        log.info("  zgzcw bdplay: %d rows", len(rowsz))

        merged = _merge_snapshots(rows500, rowsz)
        log.info("  merged: %d unique matches", len(merged))

        inserted = 0
        for snap in merged:
            if snap.issue is None or snap.issue == "":
                snap.issue = issue
            try:
                if self.db.insert_snapshot(snap, source="merged", snapshot_ts=ts):
                    inserted += 1
            except Exception as e:  # pragma: no cover
                log.warning("insert_snapshot failed for %s: %s", snap.match_id, e)
        log.info("poll done: inserted %d snapshot rows", inserted)
        return inserted

    def settle_issue(self, issue: str) -> int:
        """Fetch kaijiang for an issue and insert settlement rows."""
        html = self.scraper.fetch_kaijiang_500(issue)
        if not html:
            return 0
        rows = parse_kaijiang(html, issue)
        n = 0
        for s in rows:
            if s.result_code is None and s.fthg is None:
                continue  # row not yet settled
            try:
                if self.db.insert_settlement(s):
                    n += 1
            except Exception as e:  # pragma: no cover
                log.warning("insert_settlement failed for %s: %s", s.match_id, e)
        log.info("settle issue=%s wrote %d settlement rows", issue, n)
        return n

    def settle_pending(self) -> int:
        """Run kaijiang fetch for any issue with un-settled matches."""
        total = 0
        for issue in self.db.issues_needing_settlement():
            total += self.settle_issue(issue)
        return total
