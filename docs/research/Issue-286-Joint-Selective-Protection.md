# Issue #286 — joint base-ticket and selective-protection learning

## Decision summary

The experiment completes the requested joint action vector
`(N, selector, outcome mode, generator, K, protection policy)` without opening
2024+ outcomes. It does **not** establish a stable positive Edge.

The central finding is sharper than a generic negative result:

1. Data-aware base-action selection can find a large gross historical payoff,
   but the apparent gain is entirely tail-dependent.
2. The learned protection ranker loses less than random, continuation, or the
   fixed adverse-divergence heuristic at the same final unique-ticket budget.
3. Nevertheless, every tested protection method is inferior to leaving the
   selected base portfolio unprotected. Protection has not crossed the cash
   opportunity-cost boundary.

The correct successor is therefore not a larger protection grid. Retain the
pre-event protection score as an auxiliary feature, keep `NO_PROTECTION` as the
default, and improve the base selector/value model before considering a later
candidate-grade protection head.

## Frozen data and physical boundary

The label-free process used the #238 `10h` relative-horizon inference view and
the frozen #284 subset profile. It emitted:

| Manifest | Rows |
| --- | ---: |
| Base tickets | 1,188,800 |
| Unique single-flip candidates | 12,801,489 |
| Same-stream continuation tickets | 1,188,800 |
| Beijing issues | 620 |

619 issues support all 48 thin-factorial base actions. Issue `20031` supports
only eight because the frozen #284 profile has no feasible N8/N9 subset there;
the pipeline does not manufacture missing support.

The manifest contains no outcome, final-SP, hit, or settlement field. The
three Parquet files were content-hashed before a separate process opened the
2014–2023 settlement namespace. A mutation test verifies that changing a
separate result/SP object cannot change any manifest identity. 2024+ remains
sealed.

The settlement process excluded 664 issue-action cells whose fixed subset had
non-finite winning SP. It did not convert missing SP into a losing ticket.
Every valid unique ticket costs CNY2, and the Beijing coefficient is applied
once to the winning complete N-fold:

`gross = 2 × 0.65 × product(winning leg SP)`.

## Experimental action and models

The thin factorial contains:

- `N={7,8,9}` and `K={16,64}`;
- UNIFORM and DIVERGENCE_WEIGHTED fixed-subset selectors;
- MARKET_PROBABILITY and DIVERGENCE_VALUE outcome surfaces;
- TOP_VALUE and weighted distinct-ticket generators;
- protection shares `{0,10%,25%,50%,100%}` with an explicit cash/no-protection
  action.

Every base ticket exposes both alternatives on every leg. Candidate identities
already present in the base portfolio are removed, and remaining candidates
are deduplicated before stake is computed. The next K tickets from the same
ordered base stream provide the exact-budget continuation control.

Two expanding-year OOF controls were run over 2019–2023:

- `ACTION_RIDGE`: action identity only;
- `DATA_HGB`: action identity plus issue M×3 distribution summaries and
  ticket/leg/candidate features.

Each training issue has aggregate weight one. The candidate training sample
keeps every winner plus a deterministic negative sample with inverse-sampling
weight. Funding requires positive predicted incremental P&L; the model is free
to choose cash and no protection.

## Main capital results

All figures below are pre-tax paper economics using actual CNY2 ticket stake.

| Model/policy | Turnover | P&L | ROI | End capital | Ex-largest P&L | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ACTION_RIDGE joint | 8,608 | −8,608 | −100.00% | 91,392 | −8,576 | 8.61% |
| DATA_HGB base only | 20,320 | +17,186.63 | +84.58% | 117,186.63 | **−17,196.65** | 10.03% |
| DATA_HGB learned joint | 36,126 | +9,975.98 | +27.61% | 109,975.98 | **−24,279.30** | 13.82% |
| Same-budget random | 36,126 | +2,517.36 | +6.97% | 102,517.36 | −31,737.92 | 18.65% |
| Same-budget continuation | 36,126 | +3,555.38 | +9.84% | 103,555.38 | −30,699.90 | 17.82% |
| Same-budget adverse heuristic | 36,126 | +6,692.53 | +18.53% | 106,692.53 | −27,562.76 | 18.05% |
| Unattainable same-budget oracle | 36,126 | +93,157.84 | +257.87% | 193,157.84 | +58,902.56 | 2.70% |
| Formal #282 N7/K8 reference | 4,304 | +4,738.61 | +110.10% | 104,738.61 | +2,980.06 | 1.27% |

The headline HGB gains are not stable. Issue `190703` alone contributes
CNY34,383.29 to the selected base and CNY34,255.29 after protection. Removing
the largest issue changes the base path to −CNY17,196.65 and the joint path to
−CNY24,279.30. Their issue-bootstrap intervals are correspondingly extremely
wide and cross zero.

The formal #282 N7/K8 reference is more robust within the displayed 2019–2023
matched window, but its action was selected using 2014–2022 outcomes. It is a
required reference, not a causal OOF policy for 2019–2022. Its only genuinely
frozen holdout year here is 2023: CNY848 turnover, −CNY280.31 P&L, or
**−33.06% ROI**.

## What protection contributed

The Data-HGB policy funded 7,903 protection tickets. Their incremental stake
was CNY15,806 and their incremental P&L was **−CNY7,210.65 (−45.62%)**.
The model predicted +CNY8,842.60 instead, so its protection value calibration
failed materially.

The action distribution also violates the intended sparse behavior:
142 of 269 OOF issues selected a 100% maximum protection share. Protection was
not merely a few high-confidence exceptions; it often approximated the blanket
sleeve already rejected by #285.

The ordering nevertheless contains information. At the same final funded
ticket count:

`learned protection > adverse heuristic > continuation > random`.

But the economically controlling ordering is:

`no protection > learned protection > adverse > continuation > random`.

Thus #285's weak localization signal survives as a ranking clue, while the
incremental monetary action remains negative.

The unattainable oracle is strongly positive even after removing its largest
issue. This means the ticket universe contains rescue capacity; the failure is
not that protection can never pay. The failure is that current pre-event Data
does not identify the rare winning flips accurately enough. Across the full
candidate universe only 4,499 of 12,801,489 candidates win (0.0351%).

## Adversarial interpretation

If challenged, the apparent positive HGB result fails for four reasons:

1. **Tail dependence:** one issue reverses the conclusion.
2. **Protection miscalibration:** predicted positive protection P&L settles
   strongly negative.
3. **Non-sparse behavior:** the nonlinear model frequently funds the maximum
   sleeve, reproducing a contract falsifier.
4. **Baseline causality:** the attractive multi-year formal-reference curve is
   not a forward policy before 2023 because its identity was selected using
   later development outcomes.

The result does provide genuine learning: model effort should move upstream to
base-action value and tail-risk prediction. Protection should return only after
the model can estimate the probability and payoff of a rescue separately,
calibrate them chronologically, and demonstrate positive ex-largest incremental
P&L versus cash.

Because the protection hypothesis already failed against no protection and the
HGB result failed ex-largest stability, this exploratory cycle stopped before
multiplying the 12.8-million-row candidate panel across additional
subset/stream replicas. Nuisance confirmation remains mandatory if a later
candidate passes these first-line falsifiers.

## Reproduction and artifacts

- Executed notebook:
  [`Issue-286-Joint-Selective-Protection.ipynb`](../../notebooks/Issue-286-Joint-Selective-Protection.ipynb)
- Capital figure:
  [`issue_286_joint_policy.png`](figures/issue_286_joint_policy.png)
- Compact tables:
  [`artifacts/issue-286/`](artifacts/issue-286/)
- Frozen contract:
  [`issue_286_joint_selective_protection_contract.md`](issue_286_joint_selective_protection_contract.md)

Large ticket/candidate ledgers remain outside Git under `results/issue-286/`.
They are reproducible from the committed scripts and source-bound SHA receipts.

This is paper research only. It grants no live-betting or production authority.
