# Niche Analysis Summary

**Date:** 2026-05-02

Run on **113,469** match-option observations from **37,823** historical 北单 matches (DB + user CSV).

## Pipeline status

- Niches scored (n≥50, k≥5): **533**
- Pass P(EV>1.05) ≥ 0.7 on full data: **4**
- Pass on TRAIN (first 100 issues): **6**
- OOS survivors (test EV > 1.05 AND test P(EV>1.05) ≥ 0.5): **0**

## Top 3 niches (full data, by P(EV>1.05))

- **option_type=3, league_tier=Other, prob_bucket=>.85**: n=75, k=43, hit=0.573, implied=0.885, post μ=0.751 [0.696, 0.803], P(EV>1.05)=0.92, point EV=0.853
- **option_type=0, handicap_class=h2plus, prob_bucket=.55-.70**: n=96, k=29, hit=0.302, implied=0.673, post μ=0.491 [0.433, 0.550], P(EV>1.05)=0.91, point EV=0.717
- **handicap_class=h2plus, league_tier=Other, prob_bucket=.55-.70**: n=124, k=28, hit=0.226, implied=0.671, post μ=0.424 [0.371, 0.479], P(EV>1.05)=0.89, point EV=0.618

## Verdict

No niche survives the OOS test. The signals visible in-sample are consistent with multiple-comparison noise overlaid on a globally calibrated avg_eu. The Bayesian filter (P(EV>1.05)≥0.7) reduces but does not eliminate winner's curse over ~hundreds of strata.

## Caveats

1. avg_eu de-vig is approximate (sensitivity reported in HTML).
2. Implied prob varies within niches; mean-prob is the comparator.
3. Filtering induces winner's curse — OOS is the only honest corrector.
4. avg_eu mispricing != 北单 SP mispricing (retail tracks avg_eu).
5. n≥50 niches have ±10pp posterior width — read with skepticism.
