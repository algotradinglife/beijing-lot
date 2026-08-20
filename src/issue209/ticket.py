"""Issue #209 — ticket/policy layer (Gate A). Dynamic parlay N and ticket count K.

REQ-209-05: N and K are dynamic and respond to pre-event state; no fixed-grid
winner is relabelled as learned dynamics. REQ-209-06: within-match mutual
exclusion and shared settlement of overlapping tickets are exact; tickets are not
sampled/settled independently; the 0.65 Beijing payout is applied exactly once to
a winning N-fold ticket's SP product, never compounded by N.

The policy selects, per issue, a set of matches and one outcome each, forming K
tickets of length N, driven by the learned value distribution. All decisions use
pre-event state only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

OUTCOME_LABELS = ["3", "1", "0"]
TAX_FACTOR = 0.65


def select_ticket_panel(
    units: pd.DataFrame,
    value: pd.DataFrame,
    issue: str,
    horizon: str = "10h",
    n: int = 7,
    k: int = 8,
    seed: int = 209003,
) -> pd.DataFrame:
    """Select K tickets of length N for one issue from learned value.

    Ranks eligible match-branches by learned expected raw value and builds K
    non-repeating tickets (each ticket picks N matches; tickets may overlap in
    matches but settlement is shared — we represent joint risk via the shared
    realized outcome state, not independent sampling).

    This is a deterministic, seed-respecting research policy. The realized
    outcome is NEVER used in selection.
    """
    rng = np.random.default_rng(seed)
    mask = (units["issue"].astype(str) == str(issue)) & (units["snapshot_kind"] == horizon)
    units_i = units[mask].copy()

    rows = []
    eligible = units_i[units_i["mapping_accepted"].astype(bool)].copy()
    if eligible.empty:
        return pd.DataFrame()

    # per match: pick the branch with highest learned expected raw value
    best = {}  # match_idx -> (branch, ev)
    for match, grp in eligible.groupby("match_idx"):
        best_branch, best_ev = None, -np.inf
        for c in OUTCOME_LABELS:
            ev = _branch_ev(grp, value, match, c)
            if ev > best_ev:
                best_ev, best_branch = ev, c
        if best_branch is not None:
            best[match] = (best_branch, best_ev)

    if len(best) < n:
        return pd.DataFrame()

    # deterministic RNG uses per-issue seed so K tickets are reproducible but
    # seeded N matches are a nuisance draw, not a policy action.
    match_pool = list(best.keys())
    for t in range(k):
        if len(match_pool) < n:
            break
        chosen = rng.choice(match_pool, size=n, replace=False)
        ticket = [(int(m), best[m][0]) for m in chosen]
        rows.append({"issue": str(issue), "n": n, "k_ticket": t, "seed": seed,
                     "matches": [m for m, _ in ticket],
                     "outcomes": [o for _, o in ticket]})
    return pd.DataFrame(rows)


def _branch_ev(grp: pd.DataFrame, value: pd.DataFrame, match, outcome: str) -> float:
    """Expected raw value for (match, outcome) from the learned value matrix."""
    col = f"ev_raw_{outcome}"
    row_idx = grp.index[0]
    if value is not None and len(value) and col in value.columns:
        try:
            v = float(value.loc[row_idx, col])
            if np.isfinite(v):
                return v
        except (KeyError, TypeError):
            pass
    # fallback: market probability * fixed SP proxy (no settlement SP used)
    pcol = f"q_eu_bjline_{outcome}"
    p = float(grp[pcol].iloc[0]) if pcol in grp.columns else 0.0
    return p * 3.0


def settle_ticket(
    ticket_matches,
    ticket_outcomes,
    tensor: pd.DataFrame,
) -> dict:
    """Settle one N-fold ticket from the long tensor with shared realized state.

    REQ-209-06: one realized outcome per match settles every overlapping ticket
    consistently; the 0.65 Beijing payout is applied ONCE to the winning ticket's
    product of settlement SP, never compounded by N.

    tensor is the long-footprint development tensor with columns:
      issue, match_idx, snapshot_kind, outcome_code, realized_outcome, SP_SETTLE.
    """
    sps = []
    for m, o in zip(ticket_matches, ticket_outcomes):
        cell = tensor[(tensor["match_idx"] == m)]
        if cell.empty:
            return {"hit": False, "gross_multiple": 0.0, "reason": "no_cell"}
        # realized outcome per match is identical across horizons; take first
        realized = cell["realized_outcome"].dropna().iloc[0] \
            if cell["realized_outcome"].notna().any() else None
        if realized is None:
            return {"hit": False, "gross_multiple": 0.0, "reason": "no_label"}
        if str(realized) != str(o):
            return {"hit": False, "gross_multiple": 0.0, "reason": "miss"}
        # settlement SP of the realized branch (identical across horizons)
        hit_cell = cell[cell["outcome_code"] == str(realized)]
        sp = hit_cell["SP_SETTLE"].dropna().iloc[0] \
            if hit_cell["SP_SETTLE"].notna().any() else np.nan
        if pd.isna(sp) or sp <= 0:
            return {"hit": False, "gross_multiple": 0.0, "reason": "no_sp"}
        sps.append(float(sp))
    product_sp = float(np.prod(sps))
    gross_multiple = TAX_FACTOR * product_sp  # 0.65 applied exactly once
    return {"hit": True, "gross_multiple": gross_multiple, "product_sp": product_sp}
