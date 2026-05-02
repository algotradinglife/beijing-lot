"""CLI entry point for the historical backfill scraper.

Usage:
    python -m src.backfill.main                     # last 2 years (auto)
    python -m src.backfill.main --issues 26049 26050
    python -m src.backfill.main --since 24001
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import db
from .parser import parse_issue_html
from .scraper import fetch_issue_html, fetch_issue_list, make_session, polite_iter

DEFAULT_DB = Path("data/beidan_history.db")
LOG = logging.getLogger("backfill")


def run(
    db_path: Path,
    issues: list[str] | None,
    rate: float,
    skip_done: bool,
) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    sess = make_session()

    if not issues:
        LOG.info("Fetching issue list from projectlist…")
        all_issues = fetch_issue_list(sess)
        # default = last ~2 years.  YYNNN with YY in {current-2, current-1, current}.
        # Just take the last 2 calendar years' worth which translates to YY >= max-2.
        if all_issues:
            max_yy = max(int(x[:2]) for x in all_issues)
            issues = [x for x in all_issues if int(x[:2]) >= max_yy - 2]
        else:
            LOG.error("Empty issue list — aborting.")
            return 1

    LOG.info("Target issue range: %d issues (%s..%s)", len(issues), issues[0], issues[-1])

    with db.session(db_path) as conn:
        done = db.already_done_issues(conn) if skip_done else set()
        todo = [i for i in issues if i not in done]
        LOG.info("%d already done, %d to fetch", len(done), len(todo))

        ok = 0
        empty = 0
        err = 0
        total_rows = 0
        for issue in polite_iter(todo, rate_per_sec=rate):
            try:
                html = fetch_issue_html(sess, issue)
            except Exception as e:
                LOG.warning("issue=%s fetch error: %s", issue, e)
                db.log_scrape(conn, issue, 0, f"error:{type(e).__name__}")
                err += 1
                continue

            rows = parse_issue_html(html, issue)
            if not rows:
                LOG.info("issue=%s no rows parsed (likely unsold/empty)", issue)
                db.log_scrape(conn, issue, 0, "empty")
                empty += 1
                continue

            inserted = db.insert_matches(conn, [r.to_dict() for r in rows])
            db.log_scrape(conn, issue, len(rows), "ok")
            total_rows += inserted
            ok += 1
            if ok % 10 == 0:
                LOG.info(
                    "[progress] ok=%d empty=%d err=%d rows=%d",
                    ok, empty, err, total_rows,
                )

        LOG.info(
            "Done. ok=%d empty=%d err=%d new_rows=%d", ok, empty, err, total_rows
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--issues", nargs="+", help="explicit issue ids")
    p.add_argument("--rate", type=float, default=0.5, help="req/sec (default 0.5)")
    p.add_argument("--no-skip-done", action="store_true",
                   help="Re-fetch already-OK issues")
    args = p.parse_args(argv)

    return run(
        db_path=args.db,
        issues=args.issues,
        rate=args.rate,
        skip_done=not args.no_skip_done,
    )


if __name__ == "__main__":
    sys.exit(main())
