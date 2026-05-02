"""The 16 OOS-survived niches from `docs/research/niche_analysis_real_sp.html`
section 5. Encoded here as a frozen list so downstream code is deterministic
and the analysis module does not have to re-run the survival pipeline.

Each niche is a dict with the filter columns set; missing dimensions mean
"any value". `id` is a short stable label used in plots/tables.
"""
from __future__ import annotations

# (id, label, stratum)  — stratum keys map to long-format columns produced by
# `sp_native.to_long`: option (string '0'/'1'/'3'), sp_bucket, handicap_class,
# league_tier.
SURVIVED_16 = [
    dict(id="N01", label="opt=1, sp=5-8, lg=Other",
         stratum=dict(option="1", sp_bucket="5-8", league_tier="Other")),
    dict(id="N02", label="opt=0, sp=5-8, lg=Top5EU",
         stratum=dict(option="0", sp_bucket="5-8", league_tier="Top5EU")),
    dict(id="N03", label="opt=0, sp=5-8, hc=h1",
         stratum=dict(option="0", sp_bucket="5-8", handicap_class="h1")),
    dict(id="N04", label="sp=5-8, lg=Top5EU",
         stratum=dict(sp_bucket="5-8", league_tier="Top5EU")),
    dict(id="N05", label="sp=5-8, hc=h1",
         stratum=dict(sp_bucket="5-8", handicap_class="h1")),
    dict(id="N06", label="opt=0, sp=5-8, lg=LowerEU",
         stratum=dict(option="0", sp_bucket="5-8", league_tier="LowerEU")),
    dict(id="N07", label="sp=5-8, hc=h_unknown, lg=LowerEU",
         stratum=dict(sp_bucket="5-8", handicap_class="h_unknown",
                      league_tier="LowerEU")),
    dict(id="N08", label="sp=5-8, lg=LowerEU",
         stratum=dict(sp_bucket="5-8", league_tier="LowerEU")),
    dict(id="N09", label="opt=0, hc=h2plus, lg=Top5EU",
         stratum=dict(option="0", handicap_class="h2plus",
                      league_tier="Top5EU")),
    dict(id="N10", label="sp=5-8 (all)",
         stratum=dict(sp_bucket="5-8")),
    dict(id="N11", label="opt=0, sp=3-5, hc=h1",
         stratum=dict(option="0", sp_bucket="3-5", handicap_class="h1")),
    dict(id="N12", label="opt=0, sp=5-8",
         stratum=dict(option="0", sp_bucket="5-8")),
    dict(id="N13", label="sp=5-8, hc=h_unknown",
         stratum=dict(sp_bucket="5-8", handicap_class="h_unknown")),
    dict(id="N14", label="opt=3, sp=3-5, hc=h_unknown",
         stratum=dict(option="3", sp_bucket="3-5", handicap_class="h_unknown")),
    dict(id="N15", label="opt=0, sp=3-5, lg=LowerEU",
         stratum=dict(option="0", sp_bucket="3-5", league_tier="LowerEU")),
    dict(id="N16", label="opt=0, sp=3-5",
         stratum=dict(option="0", sp_bucket="3-5")),
]


def filter_long_by_stratum(long_df, stratum):
    """Return rows of `long_df` matching every key in `stratum`."""
    import numpy as np
    mask = np.ones(len(long_df), dtype=bool)
    for col, val in stratum.items():
        mask &= (long_df[col].astype(str).values == str(val))
    return long_df[mask]
