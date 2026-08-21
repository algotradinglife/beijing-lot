# Unified Learning: joint base-ticket and selective-protection policy

Contract ID: `BJ-UNIFIED-JOINT-PROTECTION-001`
Mode: `exploration`
Decision owner and executor: PI
Parent: Issue #285
Milestone: M3 — Decision and Portfolio Paper Evaluation

## Scientific question

Can the unified model jointly choose the base-ticket parameters and a sparse
set of protection actions from pre-event Data, such that protection improves
matched issue-level capital after its full incremental cost?

Issue #285 found that adverse signed divergence approximately doubles wrong-leg
localization and correct single-flip frequency relative to random, while a
blanket protection policy remains negative. The successor therefore learns
**when not to protect**, as well as what to protect.

## Joint action vector

The model action is:

`a = (N, selector, outcome_mode, generator, K, protection_policy)`

where `protection_policy` contains:

- no protection versus protection;
- which base tickets receive protection;
- protected leg;
- alternative outcome;
- protection confidence/advantage threshold;
- maximum protection share of the selected issue portfolio.

Specific sampled subset identity and random stream seed are nuisance replicas,
not optimizable parameters. “Protect this ticket/leg” is a per-ticket model
output; global thresholds and budget share are policy parameters.

## Thin action boundary

The first executable cycle is intentionally bounded:

- `N = 7, 8, 9`;
- `K = 16, 64`;
- selector = DIVERGENCE_WEIGHTED or UNIFORM;
- outcome mode = MARKET/CELL alias represented once or DIVERGENCE_VALUE;
- generator = TOP_VALUE or weighted distinct-ticket order;
- protection = no protection or exactly one SINGLE_FLIP candidate;
- every leg exposes its two alternative outcomes, at most `2N` candidates per
  base ticket;
- no multi-leg Cartesian protection in the first cycle.

This is a joint factorial action space. The implementation must not freeze the
historically best N/K/base action first and optimize protection afterward.

## Learning row and target

Each row is a pre-event base ticket plus one candidate action. Inputs may
include:

- issue-level M×3 probability, SP and divergence distribution summaries;
- base-action N/K/selector/outcome-mode/generator identity;
- ticket probability/value/product and within-portfolio rank;
- selected-leg probability, signed divergence, divergence rank/gap, entropy
  and proposal margin;
- alternative-outcome probability/value/divergence;
- overlap and expected incremental portfolio concentration;
- upstream base-ticket selection outputs.

The primary label is the candidate's counterfactual incremental P&L:

`incremental_gross_from_unique_rescue - incremental_unique_ticket_stake`.

No-protection has label zero. Duplicate protection tickets are removed at the
complete issue-portfolio level before final stake and settlement. A near-miss
indicator may be an auxiliary target only; it cannot replace the monetary
label or be conditioned on at decision time.

## Model and optimizer

Start with maintained-library Ridge/logistic and histogram gradient boosting
controls. Add a small sklearn MLP only if the nonlinear model improves
chronological OOF prediction and funded policy value over those controls.

The optimizer receives predicted incremental value distributions and chooses
base tickets plus protection tickets under one issue budget. Protection tickets
must compete with:

1. cash/no protection;
2. the next unprotected tickets from the same base stream;
3. the frozen fallback base portfolio.

Only actions whose conservative predicted incremental advantage exceeds zero
may be funded. There is no obligation to use the protection budget.

## Time, nesting and settlement

- independent unit: Beijing issue;
- ticket/action rows, subsets and seeds are nested within issue;
- expanding chronological OOF on 2014–2023 development outcomes;
- 2024+ remains sealed;
- no outcome, final SP or settlement field in model inputs;
- CNY2 per unique ticket;
- 0.65 applied once per winning complete N-fold ticket.

Issue-normalized training weights prevent issues with more matches, tickets or
candidate flips from becoming artificial extra history.

## #284 inheritance guard

The post-merge #284 audit is binding on this successor:

- the primary matched control is the live Issue-named #282
  `N7/K8 MARKET TOP` action; K128/K512 rows are diagnostic controls only;
- CASH/NO_PROTECTION is an explicit lawful action, not a funded fallback;
- primary capital paths use actual CNY2-per-unique-ticket stake, including
  protection; standardized CNY100 paths are secondary and separately labeled;
- subsets with non-finite winning SP are excluded until authoritative
  settlement semantics exist;
- the source snapshot and every upstream artifact are content-hash bound;
- compact action labels, OOF selected-action rows, issue attribution and
  receipts are retained for asynchronous replay.

The post-merge #285 audit adds a second inheritance guard:

- localization rates and uncertainty use equal issue weight; ticket-weighted
  rates are auxiliary only;
- the inherited adverse-divergence effect is approximately +3.93pp at K16 and
  +4.16pp at K64 versus random, not a twofold effect and not economic Edge;
- monetary random and continuation controls match exact final unique-ticket
  stake after deduplication;
- capital paths are ordered by `(issue_year, numeric issue)` with a monotonicity
  assertion;
- a label-free base/protection manifest is frozen and hashed before a separate
  outcome/SP settlement join; outcome/SP mutation cannot change pre-settlement
  identities;
- this Issue is a bounded exploration authorized by the later PI amendment. It
  does not inherit satisfaction of #285 candidate predicates.

## Required controls

- frozen unprotected base policy;
- same base with no protection;
- #285 adverse-divergence heuristic;
- same-budget random protected leg/outcome;
- same-budget unprotected stream continuation;
- action-only model versus Data+action model;
- learned model versus simplest fixed threshold;
- oracle near-miss protection as an unattainable upper bound only.

## Primary outputs

- absolute and matched issue-level pre-tax capital paths from CNY100,000;
- protection-funded fraction and incremental stake;
- rescue frequency, wrong-leg localization and alternative-outcome accuracy;
- base-action and protection-action distributions by issue/year;
- model calibration for incremental value and protected/no-protection choice;
- matched lift versus base, random and continuation controls;
- ex-largest, issue bootstrap, positive years, drawdown, consecutive losing
  issues, rolling 5/10/20 issue losses and recovery time;
- ablations showing whether Data changes decisions beyond a global action prior;
- executed Jupyter notebook, compact result tables, figures and decision report.

## Falsifying observations

The joint protection hypothesis is not supported if any of the following
controls:

- the model funds almost every ticket, reproducing blanket protection;
- it funds almost none and adds no matched value;
- action-only performance matches Data+action performance;
- lift disappears against same-budget continuation or random protection;
- one issue/year/seed/subset explains the result;
- the learned policy changes N/K only to alter nominal stake rather than
  matched value;
- the conservative safety gate cannot fund any action OOF.

This is paper research only. It confers no live-betting or production authority.
