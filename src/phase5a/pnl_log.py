"""Append-only PnL log (CSV).

Schema:
    plan_id, reconciled_at, n_tickets, n_settled_legs, n_winning_tickets,
    total_stake, gross_payout, net_pnl, cumulative_pnl
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List

PNL_FIELDS = [
    "plan_id", "reconciled_at",
    "n_tickets", "n_settled_legs", "n_winning_tickets",
    "total_stake", "gross_payout", "net_pnl", "cumulative_pnl",
]


def read_pnl_log(path: str | Path) -> List[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open() as f:
        return list(csv.DictReader(f))


def append_pnl_row(path: str | Path, row: dict) -> dict:
    """Append a row, computing cumulative_pnl from history. Returns the written row."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    history = read_pnl_log(p)
    cum = sum(float(r.get("net_pnl", 0.0)) for r in history)
    cum += float(row.get("net_pnl", 0.0))
    row = {**row, "cumulative_pnl": cum}
    write_header = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PNL_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in PNL_FIELDS})
    return row
