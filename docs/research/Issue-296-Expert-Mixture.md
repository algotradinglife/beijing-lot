# Issue #296 — Candidate-warm-start expert mixture

## Five-minute decision summary

The experiment returns **NO_PROMOTION**, but it validates the value of treating
strategy construction as a learned portfolio problem instead of choosing one
fixed parameter tuple.

The raw candidate-warm neural ensemble grew a CNY100,000 bankroll to
**CNY307,811 in the 2023 development replay (+207.81%)**. That headline cannot be
used as an Edge claim:

- the same frozen model reduced CNY100,000 to **CNY5,478 in 2022 validation**;
- all five fixed model seeds were positive in 2023, but every seed was negative
  after removing its largest issue; median seed growth was **+93.18%**;
- the raw ensemble's maximum drawdown was **77.03%** and its longest losing run
  was **20 issues**;
- after removing its largest winning issue, cumulative 2023 P&L was
  **-CNY68,484**.

The user-mandated safety rule therefore worked: when the neural proposal failed
the pre-2023 validation comparison, the executable policy fell back to the
frozen static allocation. That guarded path ended 2023 at **CNY104,143
(+4.14%)**, equal to the static control. It did not adopt the lucky raw neural
path.

This is a useful negative result rather than a dead end. Candidate identity
carried a strong development signal—the raw warm ensemble beat neutral
initialization by **153.70 percentage points**, while identity-shuffled
initialization returned **+29.07%**—but the signal reverses in validation and is
too concentrated to fund.

## Question and experimental unit

The question was whether historically interesting but differently shaped
strategies can act as experts, while a causal issue-level model learns the
bankroll weights of each expert and cash.

One Beijing issue is the independent unit. Ticket rows and nuisance seeds are
nested observations. The chronology is:

- train: 2019–2021;
- validation and fallback decision: 2022;
- frozen development replay: 2023;
- 2024+ rows: unopened by the #296 runner.

Historical candidate identities were themselves found using outcomes. They are
therefore explicitly treated as outcome-informed priors. The 2023 replay is a
development comparison, not an unbiased held-out claim.

## Expert library

| Expert | Source | Role | Learning status |
|---|---:|---|---|
| `FULL_CONTROL` | #176 | matched FULL control | eligible |
| `SMOOTH_M512` | #176 | high-hit smoother core | eligible |
| `Q_TAIL_M192` | #176 | convex Q tail | eligible |
| `Q_WOR_M64` | #151 | distinct-sampling challenger | eligible; nuisance-seed mean |
| `DIVERGENCE_Z100_K1` | #190 | sparse direction signal | eligible |
| `RARE_LOGIT_TOP64` | #291 | rare-jackpot tail | eligible |
| `N7_K16_WR` | #292 | positive fixed-action candidate | **ineligible: summary only** |

The common feature calendar contains 269 issues. The #176/#151/#190 experts
have trusted ledger support for 227 of them; their 42 absent rows are marked
unavailable and routed to cash, not converted to artificial losses. The #291
expert has 269 issue rows. A valid zero-stake ledger row remains a real frozen
NO_BET.

### Baseline ladder

The accepted historical references remain visible rather than being silently
replaced. #127's selected FULL reference was -8.35% pre-tax turnover ROI and
the #167 accepted `BEST_FULL` ladder reference was -9.47%. They are not directly
matched to #296 because their support and stake construction differ. On the
#296 2023 common calendar, the unscaled FULL unit ledger is -13.35% turnover
ROI. The +4.14% static result below is a CNY100,000 capital-growth diagnostic,
not a new accepted baseline. `baseline_ladder.csv` preserves these distinctions.

## Model and capital semantics

The nonlinear challenger is a small package-backed PyTorch gate:

`18 causal issue features -> 16 tanh units -> 6 expert logits + cash -> softmax`

Its loss maximizes mean issue-level log wealth on 2019–2021. Five fixed seeds
are nuisance replicates and are averaged; the best seed is never selected.
Candidate-warm, neutral and identity-shuffled conditions share the same data,
features, architecture and compute budget. A scikit-learn Ridge gate is the
interpretable control.

Predicted bankroll weights are converted into integer copies of each frozen
expert bundle. An issue cannot stake more than opening capital, and there is no
arbitrary maximum issue stake. The primary view is pre-tax CNY100,000 capital,
not turnover ROI.

The safety layer compares the complete executable 2022 path with the frozen
static allocation. It can only use the learned weights when terminal capital is
no worse and maximum drawdown is no greater. All three neural conditions failed
that rule and fell back before 2023 was read.

## Main results

### Frozen 2023 replay

| Policy | End capital | Growth | Max DD | Longest losing run | Ex-largest P&L |
|---|---:|---:|---:|---:|---:|
| Cash | CNY100,000 | 0.00% | 0.00% | 0 | CNY0 |
| Static train-log-growth | CNY104,143 | +4.14% | 52.70% | 19 | -CNY98,019 |
| Raw candidate-warm | CNY307,811 | +207.81% | 77.03% | 20 | -CNY68,484 |
| Raw neutral | CNY154,106 | +54.11% | 76.52% | 10 | -CNY157,760 |
| Raw identity-shuffled | CNY129,071 | +29.07% | 75.79% | 18 | -CNY157,882 |
| Guarded candidate-warm | CNY104,143 | +4.14% | 52.70% | 19 | -CNY98,019 |

The raw candidate-warm ensemble retained an average **63.70% cash** in 2023.
The remaining mean weights were 11.64% FULL, 10.51% sparse divergence, 6.06%
smooth core, 4.00% Q tail, 2.08% WOR and 2.01% rare-event tail. Thus the model
did not simply put the whole bankroll into the historical jackpot candidate.

Its largest issue was 23061, contributing approximately **CNY276,295**. FULL
and the rare-event expert supplied most of that gain. Removing that one issue
turns the entire raw path negative, so the result fails the preregistered
concentration test.

### Initialization stability

Candidate-warm individual seed growth was approximately **+93.18%, +606.56%,
+78.09%, +44.58%, and +136.49%**. The apparent cross-seed sign stability is a
real improvement over earlier experiments, but every seed remains negative
after removing its largest issue, and the 2022 validation path loses 94.52%.
More seeds would measure tail sensitivity more precisely; they would not cure
the chronology reversal.

### Core–tail and dependence findings

A fixed smooth-core/rare-tail mixture that deploys the full bankroll is ruinous
across the tested fractions. The useful learned behavior is therefore not a
magic tail ratio; it is the large, issue-varying cash allocation.

Several expert pairs have low or mildly negative issue-return correlation. The
lowest observed examples are Q-tail versus smooth core (-0.086) and Q-WOR
versus rare-event (-0.049). This leaves theoretical diversification space, but
joint positive issues are scarce and joint-loss rates remain material. Low
correlation alone is not sufficient to create a holdable portfolio.

## Adversarial interpretation

If challenged, the positive raw result can be explained without a persistent
Edge:

1. candidate identities are historically selected and therefore favorable
   priors are not independent discoveries;
2. the 2023 gain is dominated by one issue;
3. validation performance is catastrophic;
4. most model seeds lose money;
5. the sample is only 269 issues, with partial support for five experts;
6. source ledgers are aggregated, so exact cross-expert ticket-identity
   consolidation cannot be reconstructed for every expert. Linear repeated
   stakes are economically represented, but identity-level proof is absent.

The strongest defensible statement is therefore: **candidate-aware dynamic
allocation contains a potentially useful direction, but the current mapping is
too unstable and tail-dependent to replace the frozen control.**

## Implications for the unified model

The next model should retain the expert-mixture interface but change the
learning target from unconstrained realized log wealth to a better identified
two-part problem:

1. estimate each expert's conditional payout probability and downside from
   pre-event features;
2. allocate only when uncertainty-adjusted value beats cash and the frozen
   baseline;
3. train the risk/cash gate separately from expert relative weights;
4. use expanding chronological folds and out-of-fold predictions before a new
   2024+ held-out check;
5. retain the hard baseline fallback.

This gives #210 a clearer successor identity, but #210 should not be activated
until the PI and user agree that this risk-first decomposition is the intended
next contract.

## Reproduction

```bash
PYTHONPATH=src python scripts/run_bj296_expert_mixture.py
PYTHONPATH=src pytest tests/issue296 -q
```

The executed notebook is
`notebooks/research/issue-296/bj296_expert_mixture.ipynb`. Compact machine
artifacts, figures, input hashes and output hashes are under
`results/issue-296/`.
