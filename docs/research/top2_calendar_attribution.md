# Top2 calendar profit attribution

Question: why does the independent-window HARD result earn CNY63,881 in111104–120419 while the uniform-calendar HARD result loses CNY6,043? This is a fixed94-issue historical diagnosis, not a calendar selection/tuning exercise.

QMD184 regenerates all four probability/allocation combinations, freezes376 plans before reading settlement, and reproduces both prior endpoints. O is the old independent-window HANDICAP calendar; N is the full-history uniform calendar. The first letter selects probability, the second selects original funded groups and depths. Cross-cells preserve original depth and do not apply a new25% admission test. Thus they are controlled attribution cells, not separately deployable strategies.

| Cell | Net CNY | ROI % |
|---|---:|---:|
| OO | 63,881.01 | 87.99 |
| ON | 28,576.60 | 39.56 |
| NO | -15,103.11 | -20.80 |
| NN | -6,042.58 | -8.36 |

The order-averaged accounting decomposition of the -69,923.59 difference is -56,801.65 probability and -13,121.94 allocation/depth. `n7_freeze_attribution` implements the descriptive identity, with8 contract assertions. It does not fit, rank or select decisions and is not a causal estimate for unseen issues.

Holding old groups and ticket counts fixed, all59 lost original winning groups have actual outcomes excluded by the new Top2 set; none is lost only through purchase depth. Lost gross105,423 is offset by27 added winning groups with gross26,439. Old/new source q values and fixture identities match; source group memberships independently match.

In111110, five original winning groups all contain slots3,12,63. Their actual W/D/D outcomes become third-ranked, eliminating allfive groups and about30,223 gross. The slot3 W probability changes21.51%→21.23%, yet crosses the hard inclusion boundary. This is a discontinuity in the purchase rule coupled with shared-fixture exposure, not evidence that those outcomes should always be selected.

Across7318 fixtures, Top2 hit frequency is71.89% old and71.99% new. Therefore aggregate Top2 accuracy does not explain the large payout change. Changes in the selected combinations and realized payout distribution matter. Preserve old JOINT as reference; any future boundary smoothing or exposure limits require cutoff-safe prior-window parameter selection rather than recovering these known winners by hindsight.

Evidence: `audits/top2-calendar-attribution-v1`, input receipt hashes and allplan source hashes, independent94/376/1708 replay, QMD184/185 clean renders. In this Quarto environment, temporary repository-root symlinks to the canonical `quarto/` entrypoints allow project-root source resolution; remove those symlinks after rendering. QMD185 verifies all frozen outputs and the independent receipt before reporting. No new fitting or data cleaning was performed. Historical label-availability proxies and inherited legacy artifacts retain their diagnostic-only limitations.
