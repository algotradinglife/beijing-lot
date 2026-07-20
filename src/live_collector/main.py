"""Entry point.

Run forever:

    python -m live_collector
    python -m live_collector --once          # single poll, then exit
    python -m live_collector --duration 300  # run for N seconds, then exit

Logs go to ``data/logs/live_collector.log`` plus stdout. SIGTERM/SIGINT
trigger a clean shutdown after the current poll finishes.
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import random
import signal
import sys
import time
from pathlib import Path

# Allow running as `python src/live_collector/main.py` (no package context).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from live_collector.db import Database
    from live_collector.scheduler import Collector
    from live_collector.scraper import Scraper
else:
    from .db import Database
    from .scheduler import Collector
    from .scraper import Scraper


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "beidan_live.db"
DEFAULT_LOG = REPO_ROOT / "data" / "logs" / "live_collector.log"


def _setup_logging(logfile: Path, verbose: bool = False):
    logfile.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)s %(name)s | %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    fh = logging.handlers.RotatingFileHandler(
        logfile, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter(fmt))
    root.addHandler(fh)
    root.addHandler(sh)


_stop = False


def _on_signal(signum, frame):  # pragma: no cover
    global _stop
    logging.getLogger(__name__).warning("received signal %s — stopping", signum)
    _stop = True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--log", default=str(DEFAULT_LOG))
    p.add_argument("--interval-min", type=int, default=300,
                   help="min seconds between polls (default 300 = 5 min)")
    p.add_argument("--interval-max", type=int, default=900,
                   help="max seconds between polls (default 900 = 15 min)")
    p.add_argument("--once", action="store_true", help="poll once and exit")
    p.add_argument("--duration", type=int, default=0,
                   help="exit after N seconds (0 = run forever)")
    p.add_argument("--no-settle", action="store_true",
                   help="skip kaijiang settlement fetch")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    _setup_logging(Path(args.log), args.verbose)
    log = logging.getLogger("live_collector")
    log.info("starting; db=%s log=%s", args.db, args.log)

    db = Database(args.db)
    scraper = Scraper(min_interval=1.0, max_retries=3)
    coll = Collector(db, scraper)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    started = time.time()
    poll_n = 0
    try:
        while not _stop:
            cycle_started = time.monotonic()
            poll_n += 1
            try:
                coll.poll_once()
                if _stop:
                    break
                if not args.no_settle:
                    # Issue-level kaijiang every cycle — one HTTP request,
                    # cheap; previously gated to %4 caused 20–60min stalls
                    # when kaijiang was published between cycles.
                    coll.settle_pending()
                    # Per-match livescore fallback every 4th cycle (heavier:
                    # multiple HTTP fetches across fids on live.500.com)
                    if poll_n % 4 == 1:
                        coll.settle_per_match()
            except Exception as e:
                log.exception("poll failed: %s", e)

            if args.once:
                break
            if args.duration and (time.time() - started) >= args.duration:
                log.info("duration reached, exiting")
                break

            target_interval = random.randint(args.interval_min, args.interval_max)
            cycle_elapsed = time.monotonic() - cycle_started
            sleep = max(0, target_interval - int(cycle_elapsed))
            log.info(
                "sleeping %ds (target_interval=%ds cycle_elapsed=%.1fs)",
                sleep,
                target_interval,
                cycle_elapsed,
            )
            t0 = time.time()
            while not _stop and (time.time() - t0) < sleep:
                time.sleep(1)
                if args.duration and (time.time() - started) >= args.duration:
                    break
    finally:
        db.close()
        log.info("shutdown complete; total polls=%d", poll_n)


if __name__ == "__main__":
    main()
