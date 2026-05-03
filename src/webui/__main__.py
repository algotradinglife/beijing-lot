"""Entry point: ``python -m src.webui``.

Binds to 127.0.0.1:8000 (localhost-only — single-user tool, no auth).
"""
from __future__ import annotations

import argparse
import os

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="src.webui")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--live-db", default=os.environ.get(
        "BEIDAN_LIVE_DB", "data/beidan_live.db"))
    parser.add_argument("--webui-db", default=os.environ.get(
        "BEIDAN_WEBUI_DB", "data/webui.db"))
    parser.add_argument("--plans-dir", default=os.environ.get(
        "BEIDAN_PLANS_DIR", "data/phase5a_plans"))
    parser.add_argument("--pnl-log", default=os.environ.get(
        "BEIDAN_PNL_LOG", "data/phase5a_pnl/pnl.csv"))
    args = parser.parse_args()

    app = create_app(
        live_db=args.live_db,
        webui_db=args.webui_db,
        plans_dir=args.plans_dir,
        pnl_log=args.pnl_log,
    )
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
