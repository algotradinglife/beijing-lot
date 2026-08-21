# Issue #292 — dynamic joint optimizer and low-N/tail barbell

## Five-minute decision summary

Issue #292 completes the 2019–2023 development-only experiment and keeps
2024+ sealed. It does **not** establish a deployable policy.

The owner's preferred payoff shape is scientifically plausible but is not yet
learned by the present model. A low-N `N3–N6` core did not approach break-even:
the always-active learned core returned `−92.17%`, and the predicted-mean gates
from `−5%` through `0%` returned about `−99%` to `−100%`. A separately learned
high-N tail returned `+265.39%`, but only one of five years was positive, the
bootstrap lower bound was `−100%`, the longest losing run was 217 issues, and
removing its one winning issue changed P&L to `−CNY4,288`. It learned a lottery,
not when to buy the lottery.

The best capped combination had `+8.03%` total ROI with a 10.73% aggregate tail
allocation and a hard 20% per-issue cap. Its core was still about `−99%`, it had
only one positive year, and ex-largest P&L was `−CNY14,406.71`. The tail jackpot
therefore hid rather than repaired the core loss.

Several fixed actions look positive after searching the full surface—especially
`N7/K16/WR`, `N8/K32/WR` and `N10/K512/WR`—but seed-by-seed settlement shows
large sign reversals. They remain hypotheses for a better sparse activation
model, not accepted baselines.

Decision: `NO_PROMOTION`; retain cash, keep 2024+ sealed, and preserve the
low-N-core/high-N-tail architecture as a target shape. The next improvement
must learn sparse activation and ticket-level payoff calibration rather than
selecting a global fixed winner.

## Data, time and physical contract

- The independent unit is one Beijing issue; action and ticket replicas are
  nested observations.
- The pre-event issue tensor covers 2014–2023. Expanding OOF decisions cover
  2019–2023: training uses years `< test_year−1`, the immediately preceding
  year selects the model family, and the current year is untouched test data.
- 2024+ outcomes were never opened.
- The complete feasible surface has `N=3…10`,
  `K={8,16,32,64,128,256,512}`, and `TOP_VALUE`, `WEIGHTED_WR`,
  `WEIGHTED_WOR`, plus cash: 169 actions per normal issue. Issue `20031` has
  only seven matches, so N8–N10 are physically unavailable rather than
  missing.
- Every active ticket costs CNY2. The 0.65 Beijing coefficient is applied once
  to a complete winning N-fold, never per leg.
- Five deterministic ticket-stream seeds form each issue/action training
  label. Three model seeds are averaged.

## Model and selection semantics

The model consumes pre-event issue state plus explicit action parameters. It
uses maintained scikit-learn components: logistic and MLP hit classifiers,
histogram gradient boosting for positive payoff, non-positive loss and the
downside quantile. The immediately preceding year selects between logistic and
MLP by ex-largest tuning P&L before total P&L. Logistic won all five folds.

Realized P&L is joined only after an action is selected. Predicted losses are
bounded by the physical `−stake` floor. Cash, fixed N7/K8/TOP, previous-action
continuation, and the #291 primary/challenger paths remain named competitors.
The low-N core and high-N tail are selected separately. Combined barbell rows
only admit a real supported tail K whose stake is no more than 10% or 20% of
combined issue stake; no fractional ticket scaling is used.

## Matched policy results

All ROI values are pre-tax. Bootstrap intervals use 50,000 issue-level
resamples; the CNY100,000 capital path is ordered issue by issue.

| Policy | Funded issues | Stake | P&L | ROI | Ex-largest P&L | Positive years | Bootstrap ROI p2.5 | Longest loss run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cash | 0 | 0 | 0 | 0.00% | 0 | 0 | 0.00% | 0 |
| Fixed N7/K8/TOP | 269 | 4,304 | −3,734.08 | −86.76% | −4,288.00 | 0 | −100.00% | 204 |
| Dynamic full, active | 269 | 25,680 | −16,608.20 | −64.67% | −22,641.29 | 1 | −100.00% | 155 |
| Dynamic full, cash gate | 257 | 25,152 | −16,080.20 | −63.93% | −22,113.29 | 1 | −100.00% | 93 |
| Low-N core, always active | 269 | 15,328 | −14,128.52 | −92.17% | −14,588.34 | 0 | −98.22% | 170 |
| Low-N core, predicted EV ≥ −5% | 152 | 13,456 | −13,334.27 | −99.10% | −13,407.57 | 0 | −100.00% | 40 |
| High-N tail, predicted EV ≥ 0% | 269 | 4,304 | +11,422.51 | +265.39% | −4,288.00 | 1 | −100.00% | 217 |
| Best 20%-cap barbell | 135 | 14,640 | +1,175.80 | +8.03% | −14,406.71 | 1 | −100.00% | 29 |
| #291 primary B64 comparator | 269 | 34,432 | +103,270.26 | +299.93% | +61,116.73 | 4 | −3.19% | 112 |

The `0%`, `10%` and `25%` tail gates all make the same choice. Predicted tail
EV is therefore not calibrated enough to create different activation regimes.
The tail chooses `N10/K8/WEIGHTED_WR` in 268 of 269 issues and wins in only one
issue. The full dynamic policy instead chooses N10 in 268 issues, mostly K64,
and loses in four of five OOF years. It over-generalizes the historical high-N
payoff tail rather than learning its regime.

The best barbell respects its maximum 20% issue-level tail cap and uses 10.73%
of aggregate stake for the tail. That proves the physical allocation interface,
but the positive total comes from the same single tail event. The tail does not
hedge the core; it merely changes the terminal total.

## Fixed-action clues and nuisance falsification

Searching all 168 active actions gives attractive post-hoc means:

- `N6/K8/WOR`: total ROI `+32.82%`, four positive averaged years, but
  ex-largest P&L `−CNY348.89`;
- `N7/K16/WR`: ROI `+108.18%`, five positive averaged years and ex-largest
  `+CNY4,864.75`;
- `N8/K32/WR`: ROI `+57.23%`, four positive averaged years and ex-largest
  `+CNY5,895.88`;
- `N10/K512/WR`: ROI `+127.61%`, but only two positive averaged years.

Those averages conceal ticket-stream instability:

| Action | Positive seeds | Positive ex-largest seeds | Seed ROI range | Median seed ROI |
| --- | ---: | ---: | ---: | ---: |
| N6/K8/WOR | 1/5 | 1/5 | −55.20% to +277.53% | −24.33% |
| N7/K16/WR | 3/5 | 2/5 | −100.00% to +478.60% | +63.58% |
| N8/K32/WR | 3/5 | 1/5 | −74.10% to +231.75% | +52.33% |
| N10/K512/WR | 3/5 | 2/5 | −50.78% to +415.52% | +122.00% |

The N6 row is the closest observed shape to a low-N core plus jackpot, but four
of five independent ticket streams lose. The apparently stable N7 averaged
year count is also a consequence of averaging seeds inside issue/action before
annual aggregation; one seed loses every ticket. None is a robust fixed action.

## Relationship to #291

The #291 primary B64 path remains the strongest frozen comparator in total and
ex-largest P&L. Its 50,000-draw issue bootstrap lower bound is `−3.19%`, close
to the earlier 5,000-draw `−2.37%`; the difference is Monte Carlo precision,
not a scientific reversal. The asynchronous #291 EV finding about equal-year
rather than equal-issue probability metrics does not alter its ticket
settlement path.

#292 does not independently reproduce the #291 ticket-level ranking under new
negative-sampling refits. More importantly, the broader action-level learner
does not generalize that candidate into a profitable dynamic policy. Therefore
the #291 row remains a post-selected candidate signal, not a promoted baseline.

## Adversarial review

1. **Could the positive tail be called the requested strategy?** No. Removing
   one issue loses the entire stake, only one year is positive, and the model
   activates every issue. It has the desired skew but no learned timing.
2. **Did lowering N solve the holdability problem?** No. N3–N5 fixed rows are
   about −22% to −38%; the learned low-N policy mostly selects N5 TOP tickets
   and performs worse. N6 supplies a clue, not a stable core.
3. **Did the barbell cap work?** Mechanically yes: maximum tail fraction is at
   most the declared 10%/20%. Scientifically no: positive combined P&L is
   jackpot dependence over a deeply negative core.
4. **Is N7/K16/WR already an Edge?** No. It was selected after inspecting 168
   actions and changes sign across nuisance seeds. Its five positive averaged
   years are not five independent confirmations.
5. **Would opening 2024 settle the question?** It would spend held-out data on
   a policy that already loses to cash in development OOF. The activation model
   should first improve without touching 2024+.

## Decision and next learning target

`NO_PROMOTION`. Cash remains the controlling decision and no live bankroll is
authorized. The useful advance is architectural:

- preserve separate core and tail sleeves with physical capital caps;
- make sparse issue activation the main target;
- move from coarse issue/action averages to ticket-level calibrated
  `P(hit) × E(gross | hit) − stake` inputs before aggregating actions;
- train the gate against cash and continuation, with explicit calibration of
  predicted activation rates;
- use N6/K8/WOR, N7/K16/WR and N8/K32/WR only as preregistered challengers in a
  future development-only experiment, never as selected truths;
- do not open #210/2024+ until one learned policy beats cash and its matched
  control with positive ex-largest P&L and nuisance stability.

Artifacts, the executed notebook and the overview figure are stored alongside
this report under `docs/research/artifacts/issue-292`,
`notebooks/Issue-292-Dynamic-Joint-Optimizer.ipynb`, and
`docs/research/figures/issue_292_dynamic_barbell.png`.
