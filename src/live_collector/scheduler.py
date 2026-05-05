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
    Settlement,
    compute_result_code,
    find_current_issue,
    parse_bet_page_500,
    parse_bet_page_zgzcw,
    parse_issue_list,
    parse_kaijiang,
    parse_livescore_500_all,
    parse_500_zqdc_issue,
    parse_500_zqdc_score,
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
        """Find the current 北单 issue id.

        Primary path: ``trade.500.com/bjdc/`` (hidden ``expect`` input or
        first option in the dropdown). If that fetch fails or returns no
        recognizable issue marker (site down, layout change, etc.), fall
        back to ``live.500.com/zqdc.php`` which exposes the current issue
        via ``window.live_cur_expect``. The zqdc fallback is independent
        of trade.500.com infrastructure and shares the same source of truth
        already used by the per-match settlement fast-path.
        """
        cur: str | None = None
        try:
            html = self.scraper.fetch_bjdc_500()
            if html:
                cur = find_current_issue(html) or (
                    parse_issue_list(html)[:1] or [None]
                )[0]
        except Exception as e:
            log.warning("issue discovery: trade.500 raised %s", e)
            cur = None

        if cur:
            log.info("issue discovery: %s (source=trade500)", cur)
            return cur

        # Fallback: live.500.com/zqdc.php
        try:
            zhtml = self.scraper.fetch_500_zqdc_index()
            cur = parse_500_zqdc_issue(zhtml) if zhtml else None
        except Exception as e:
            log.warning("issue discovery: zqdc fallback raised %s", e)
            cur = None

        if cur:
            log.info("issue discovery: %s (source=zqdc)", cur)
        else:
            log.error("issue discovery: both trade500 and zqdc failed")
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
                if self.db.insert_settlement(s, source="500_kaijiang"):
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

    # -- per-match settlement (live.500.com fast path)

    def settle_per_match(self, *, max_matches: int = 50) -> int:
        """For each unsettled match that kicked off > 2h ago, fetch its
        livescore page (live.500.com) by ``fid`` and insert settlement.

        500.com's issue-level kaijiang page is published only after the
        whole multi-day issue closes; this per-match path catches late
        matches in near-real-time. ``max_matches`` caps per call so a big
        backlog doesn't stall the daemon.

        NOTE: a former dongqiudi fallback was removed 2026-05-05 after the
        site migrated to a Nuxt JS shell that lazy-fetches data via
        token-protected APIs — no static-HTML parser is feasible. If 500.com
        misses a match (rare; usually publish-delay), it stays unsettled
        until 500 catches up. The 48h-stuck check in autocheck flags this.
        """
        pending = self.db.matches_needing_per_match_settle()[:max_matches]
        if not pending:
            return 0
        log.info("per-match settle: %d candidates", len(pending))

        # Score cache: every live.500 fetch covers ~30 nearby matches; each
        # response contributes scores for all of them, and subsequent pending
        # fids hit the cache instead of triggering another HTTP roundtrip.
        score_by_fid: dict[str, tuple[int, int]] = {}

        # Need handicap for compute_result_code; fetch in bulk
        cur = self.db._conn.cursor()
        # Build map match_id -> handicap_line
        cur.execute("SELECT match_id, handicap_line FROM matches")
        handicap = {r[0]: r[1] for r in cur.fetchall()}

        n = 0
        for m in pending:
            mid = m["match_id"]
            fid = m["fid"]
            hg = ag = None
            source = None

            # Path A: live.500.com livescore (with cross-fid score cache)
            if fid:
                if fid not in score_by_fid:
                    html = self.scraper.fetch_livescore_500(fid)
                    page_scores = parse_livescore_500_all(html)
                    score_by_fid.update(page_scores)
                    score_by_fid.setdefault(fid, None)  # mark "fetched"
                pair = score_by_fid.get(fid)
                if pair is not None:
                    hg, ag = pair
                    source = "live500"

            # Path B: zqdc.php?id=fid (publishes finals faster than kaijiang
            # for some leagues; covers cases where livescore page-bin missed
            # this fid).
            if hg is None and fid:
                try:
                    zhtml = self.scraper.fetch_500_zqdc(fid)
                    parsed = parse_500_zqdc_score(zhtml, fid)
                except Exception as e:
                    log.warning("zqdc fetch failed for %s: %s", fid, e)
                    parsed = None
                if parsed:
                    zhg, zag, zstatus = parsed
                    if zstatus == "4":  # only accept finished
                        hg, ag = zhg, zag
                        source = "zqdc"

            if hg is None:
                continue
            rc = compute_result_code(hg, ag, handicap.get(mid))
            s = Settlement(
                match_id=mid, issue=m["issue"], match_idx=m["match_idx"],
                fthg=hg, ftag=ag, result_code=rc,
            )
            try:
                if self.db.insert_settlement(s, source=source):
                    n += 1
                    log.info("per-match settle %s [%s]: %d-%d rc=%s",
                             mid, source, hg, ag, rc)
            except Exception as e:  # pragma: no cover
                log.warning("insert_settlement failed for %s: %s", mid, e)
        log.info("per-match settle: wrote %d new rows", n)
        return n
