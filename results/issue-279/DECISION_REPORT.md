# Issue #279 decision report

- Development support: 620 independent issues, 2014–2023.
- Action-feature surface: 30,368 lawful issue/action rows.
- 2024+ outcomes opened: 0.
- 2023 replay: dynamic -CNY1,161.34; fixed N7/K8 -CNY848.00;
  matched incremental loss -CNY313.34.
- Two N5/K128 TOP_VALUE decisions contribute -CNY480 matched delta.
- N changes at K8 contribute +CNY166.66 in aggregate; this is exploratory
  realized attribution, not stable causal Edge.
- Raw oracle argmax is invalid as a parameter label because K exposure and
  multiple-action hindsight push it toward N7/K512.
- All 30,368 action outcomes are now normalized to a matched CNY16 reference
  budget.  The budget-matched best action distribution is broad: K8/32/128/512
  account for 20.3%/27.3%/30.3%/20.5% of issue-level maxima, while 10 issues
  prefer NO_BET.  This supports learning parameters as a function of issue
  Data; it does not support one globally fixed K.
- Budget-matched returns remain extremely skewed.  For example, N5/K8 WR has
  the best all-development mean (+CNY7.24 per CNY16), but a -CNY16 median and
  only 13.1% positive issues; removing its single largest issue turns its mean
  negative (-CNY2.92).  A mean-only learner would therefore be unsafe.
- 2023 now has 43,599 cell rows, 265 Top-B action rows, 3,264 complete ticket
  rows and 20,208 leg rows frozen without settlement fields.  Chosen and fixed
  ticket structures can be compared directly.
- The new trace identifies final-portfolio match/outcome changes.  It does not
  call these pure Stage-1/Stage-2 effects because WR/WOR and K also change the
  portfolio coverage at Stage 3.  Separate stage effects and causal PnL remain
  non-identifiable/non-additive: one N-fold ticket pays only when every leg
  hits.

Decision: #279's data and target contract is ready for PI review.  The next
joint model should learn a conditional return distribution, positive-return
probability and downside quantile, retain Top-B actions, and estimate a smooth
marginal-K stopping curve.  It must not imitate the hindsight oracle or optimize
an unnormalized mean.
