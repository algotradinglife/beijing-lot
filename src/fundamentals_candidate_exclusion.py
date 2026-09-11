"""Fixed input exclusion for the exposed consensus portfolio experiment."""
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def exclude_zero_top2_disagreement(frame, *, cutoffs):
    """Return filtered prediction frame and sealed exclusion ledger.

    Exclude iff home handicap == 0 and baseline/market Top2 outcome SETS
    differ. Ties use existing W,D,L index order. Other columns/order preserved.
    Explicit native fixture cutoffs validated upstream. No labels, fitting,
    mutation or I/O. Empty retained pool fails clearly (no silent fallback).
    """
    _,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    dropped=[]
    for row in frame.to_dict("records"):
        p=sorted(range(3),key=lambda j:(-row["p_"+"WDL"[j]],j))[:2]
        q=sorted(range(3),key=lambda j:(-row["q_"+"WDL"[j]],j))[:2]
        if row["handicap"]==0 and set(p)!=set(q):
            dropped.append(int(row["slot"]))
    retained=frame.loc[~frame.slot.isin(dropped)].copy()
    if retained.empty:
        raise ValueError("No retained candidates after explicit exclusion")
    receipt=dict(rule="EXCLUDE_ZERO_HANDICAP_DIFFERENT_TOP2_SETS",cutoffs=bound,
        input_sha256=stable_json_hash(frame.sort_values("slot").to_json(orient="records")),
        retained_sha256=stable_json_hash(retained.sort_values("slot").to_json(orient="records")),
        dropped_slots=sorted(dropped),input_count=len(frame),retained_count=len(retained),
        historical_admission=False)
    return retained,dict(receipt=receipt,seal=stable_json_hash(receipt))
