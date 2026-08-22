Closes #306

# Issue #306 — state-dependent expert composition and dynamic funding intensity

## Verdict: EXPERT_VALUE_SIGNAL / NO PROMOTION

Dynamic policy (Stage A keep/skip + Stage C composition + Stage C intensity):
2023 terminal **CNY112,357.91 (+12.36%)** vs exact B0_BEST_FULL
**CNY79,248.96 (-20.75%)** → matched lift **+33.11pp / +33,108.94 CNY**;
beats cash, #299 residual, static mixture, issue-block shuffle and
expert-identity shuffle on identical 227-issue support.

**Decomposition** (the interesting finding):

- Stage A keep/skip alone: **+13,639 CNY** — the #305 frozen
  expert-label-invariant head funds 8/35 active 2023 issues and reproduces
  the delivered #305 -7.11% path exactly
- Composition at a *fixed* intensity: **+0 CNY** — the fixed funding fraction
  selected on earlier expanding OOF folds collapses to **0%**, exactly
  reproducing #302's "global funding scalar → zero" result
- **Dynamic (state-dependent) intensity: +19,470 CNY** — the learned
  state-dependent funding fraction deploys non-zero exposure on favorable
  issues and is where the expert layer adds value

**Falsification**: exact executed-exposure null percentile **0.758 < 0.95**
barrier; the same bundle copies placed randomly beat the primary in the tail.
No promotion, no #210 access, 2024+ stays sealed.

## Stage A

`stage_a_source = FROM_305_OUTPUT` — the delivery uses the **real frozen #305
keep/skip head** (`results/issue-305/policy_decisions.csv`, DEDICATED_MLP
condition), loaded by the contract layer. Integration verified: Stage-A-only
2023 path lands at -7.11%, matching the delivered #305 decision exactly.

## Deliverables

- Executed notebook: `notebooks/research/issue-306/bj306_dynamic_moe.ipynb`
- Package: `src/issue306/` (panel / stage_a / value_model / portfolio /
  evaluation / controls / experiment)
- Focused tests: `tests/issue306/` — 15 passed incl. Stage-A invariance and
  tamper self-tests (manifest hash drift, settlement tamper, sealed 2024)
- Artifacts: `results/issue-306/` (28 files, manifest-verified)
- Decision report: `docs/research/Issue-306-State-Dependent-Expert-Composition.md`
- Roadmap update: `docs/research/roadmap.md`

## PI adjudication request

PR #308's roadmap direction note proposes treating #306 as "within-issue
ticket composition (no learned issue skip)". This delivery implements the
**issue-body contract** (BJ-UNIFIED-DYNAMIC-MOE-001): state-dependent expert
composition and dynamic funding intensity, with #305 keep/skip as frozen
Stage A. The two framings differ; please adjudicate whether the issue-body
contract or the roadmap direction governs the accepted output.