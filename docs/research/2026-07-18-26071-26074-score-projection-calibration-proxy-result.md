# 26071–26074 score-projection calibration proxy result

Status: `research_only_post_hoc_proxy_non_executable_non_selectable_roi_unauthorized`.

This is small-sample, post-hoc, proxy evidence only—never promotion evidence.
It uses the locked three-issue fit (`26071–26073`) and one final untouched
`26074` evaluation.  The result does not authorize a strategy, selection,
execution, or ROI claim.

The [candidate-grid lock](2026-07-18-26071-26073-score-projection-calibration-lock.md)
was hashed before the holdout label was parsed.  Its deterministic aggregate
draw-Brier rule chose `G1_logit_L2_1`: intercept `0.036789`, slope `0.961091`,
four Newton iterations, fitted on 93 rows.  G0 and uncalibrated G1 are both
reported as no-change baselines.

All values below are lower-is-better binary draw Brier, binary draw log loss,
and 10-bin draw ECE. `n/draws` gives the sample count and observed handicap
draw count.

| Issue | n/draws | Candidate | Brier | Log loss | Draw ECE |
| --- | ---: | --- | ---: | ---: | ---: |
| 26071 | 16/4 | G0 no-change | 0.186054 | 0.559001 | 0.045431 |
| 26071 | 16/4 | G1 no-change | 0.189759 | 0.567372 | 0.098557 |
| 26071 | 16/4 | locked G1 calibration | 0.189591 | 0.566748 | 0.062294 |
| 26072 | 67/15 | G0 no-change | 0.174339 | 0.531626 | 0.065975 |
| 26072 | 67/15 | G1 no-change | 0.171969 | 0.526850 | 0.040154 |
| 26072 | 67/15 | locked G1 calibration | 0.172782 | 0.529184 | 0.039143 |
| 26073 | 10/5 | G0 no-change | 0.305979 | 0.821493 | 0.219065 |
| 26073 | 10/5 | G1 no-change | 0.320001 | 0.860340 | 0.315008 |
| 26073 | 10/5 | locked G1 calibration | 0.312585 | 0.839667 | 0.302913 |
| 26074 holdout | 65/21 | G0 no-change | 0.217896 | 0.627384 | 0.045372 |
| 26074 holdout | 65/21 | G1 no-change | 0.221618 | 0.636379 | 0.078512 |
| 26074 holdout | 65/21 | locked G1 calibration | 0.219470 | 0.630927 | 0.082174 |

| Aggregate | n/draws | Candidate | Brier | Log loss | Draw ECE |
| --- | ---: | --- | ---: | ---: | ---: |
| Fit, 26071–26073 | 93/24 | G0 no-change | 0.190509 | 0.567504 | 0.031791 |
| Fit, 26071–26073 | 93/24 | G1 no-change | 0.190947 | 0.569681 | 0.015504 |
| Fit, 26071–26073 | 93/24 | locked G1 calibration | 0.190706 | 0.569032 | 0.010807 |
| Holdout, 26074 | 65/21 | G0 no-change | 0.217896 | 0.627384 | 0.045372 |
| Holdout, 26074 | 65/21 | G1 no-change | 0.221618 | 0.636379 | 0.078512 |
| Holdout, 26074 | 65/21 | locked G1 calibration | 0.219470 | 0.630927 | 0.082174 |
| Descriptive, all four issues | 158/45 | G0 no-change | 0.201776 | 0.592139 | 0.031116 |
| Descriptive, all four issues | 158/45 | G1 no-change | 0.203565 | 0.597120 | 0.041425 |
| Descriptive, all four issues | 158/45 | locked G1 calibration | 0.202539 | 0.594495 | 0.040167 |

On the holdout, the locked calibration is worse than G0 no-change by
`+0.001574` Brier, `+0.003543` log loss, and `+0.036803` ECE.  Relative to raw
G1 it improves Brier and log loss, but worsens ECE.  Therefore 26074 does
**not** support transfer of this calibration as an improvement over the
no-change G0 reference.

The complete non-executable result is
[`result.json`](../../results/research/score_projection_26071_26074_posthoc_proxy_v1/result.json).
It allowlists only frozen replay identity, G0/G1 probability, and settled
handicap-label fields.  Terminal correct-score odds, ROI, tickets, payouts,
production API/frontend/collector/scheduler, release manifests, formal
strategy, and shared SQLite are excluded.
